"""
Universal Forex / MT5 AI-Agent R6.5 Backtester

The production strategy source of truth is UniversalForexBot_MT5.py.

Parity contract:
- completed-candle strategy decisions
- same Evidence Families and AI-Agent council
- AI thresholds: 3 families / 0.20 edge / 0.55 family confidence /
  Trend ON / Structure ON / max 1 conflict
- bounded AI risk: 0.20%..0.50%
- bounded AI SL: 1.50..2.40 ATR
- bounded AI TP1: 1.00..1.50R
- bounded AI TP2: 2.00..3.00R
- TP1 partial + break-even management
- one simulated open trade
- post-SL opposite-direction lock
- max drawdown and emergency-capital guards

Forex-specific simulation:
- risk sizing uses tick-size/tick-value and MT5-style lots
- spread and slippage are modeled adversely
- commission is configurable
- entry is simulated at the next candle open
- 4H MTF is availability-aligned to avoid future leakage
- Grid Mode is OFF-only in the Forex production contract

This is a research simulator. Broker execution, swaps, latency, fills,
freeze levels, spread history and liquidity can differ from live MT5.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
LIVE_FILE = ROOT / "UniversalForexBot_MT5.py"
RESULT_DIR = ROOT / "backtest_results_forex_r6_5"

AI_MIN_FAMILIES = 3
AI_MIN_EDGE = 0.20
AI_FAMILY_CONFIDENCE = 0.55
AI_REQUIRE_TREND = True
AI_REQUIRE_STRUCTURE = True
AI_MAX_CONFLICTS = 1

AI_MIN_RISK = 0.20
AI_MAX_RISK = 0.50
AI_MIN_SL = 1.50
AI_MAX_SL = 2.40
AI_MIN_TP1 = 1.00
AI_MAX_TP1 = 1.50
AI_MIN_TP2 = 2.00
AI_MAX_TP2 = 3.00

DEFAULT = {
    "signal_mode": "AI_AGENT",
    "timeframe": "15m",
    "max_trades": 10,
    "max_open_trades": 1,
    "no_same_candle": True,
    "cooldown_min": 15,
    "risk_pct": 0.35,
    "grid_mode": "OFF",
    "max_dd_pct": 5.0,
    "emergency_loss_pct": 10.0,

    "use_st": True, "st_len": 10, "st_mult": 2.0, "st_source": "CLOSE",
    "st_change_atr": True, "st_entry_mode": "FRESH_FLIP",
    "use_ema": True, "ema_len": 200,
    "use_ema_cross": True, "ema_fast": 9, "ema_slow": 20,
    "ema_cross_entry_mode": "FRESH_CROSS",
    "use_macd": True, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "use_rsi": True, "rsi_len": 14, "rsi_ob": 80, "rsi_os": 20,
    "rsi_logic": "REVERSAL_ZONE", "rsi_ma_type": "EMA", "rsi_ma_len": 9,
    "use_bb": False, "bb_len": 20, "bb_std": 2.0,
    "use_stoch": True, "stoch_k": 14, "stoch_smooth": 3, "stoch_d": 3,
    "use_vwap": True, "vwap_len": 50,
    "use_vwap_delta": True, "vwap_delta_smooth": False,
    "vwap_delta_smooth_len": 21, "vwap_delta_baseline": 50,
    "vwap_delta_logic": "CURRENT_TREND",
    "use_vidya": True, "vidya_len": 10, "vidya_momentum": 20,
    "vidya_band": 2, "vidya_entry_mode": "CURRENT_TREND",
    "use_nwe": True, "nwe_bandwidth": 8, "nwe_mult": 3,
    "nwe_entry_mode": "FRESH_CROSS", "nwe_repaint": False,
    "use_liq_swing": True, "liq_len": 14, "liq_area": "Wick Extremity",
    "liq_filter": "Count", "liq_filter_value": 0, "liq_entry_mode": "FRESH_BREAK",
    "use_trendline": True, "trend_len": 14, "trend_min_dist": 5,
    "trend_buffer": 0.0, "trend_retest": 3, "trend_entry": "FRESH_BREAK",
    "use_divergence": True, "div_pivot": 5, "div_min_count": 1,
    "div_max_pivots": 10, "div_max_bars": 100, "div_type": "Regular",
    "div_source": "Close", "div_entry_mode": "FRESH",
    "div_use_all": True, "div_cci_len": 10, "div_mom_len": 10,
    "div_vwmacd_fast": 12, "div_vwmacd_slow": 26,
    "div_cmf_len": 21, "div_mfi_len": 14,
    "use_vol_sr": True, "sr_volume_ma": 6, "sr_vote_mode": "MAJORITY",
    "sr_entry_mode": "CURRENT_ZONE", "sr_tf1": "Chart", "sr_tf2": "4h",
    "sr_tf3": "D", "sr_tf4": "W",
    "use_vol": True, "vol_len": 20, "use_adx": True, "adx_len": 14,
    "adx_thresh": 20, "use_atr": True, "atr_min_pct": 0.30, "use_mtf": True,
    "atr_sl_mult": 1.8, "atr_tp1_mult": 1.2, "atr_tp2_mult": 2.2,
    "tp1_close_pct": 50.0, "tp1_be": True,
}

def live_module():
    spec = importlib.util.spec_from_file_location("forex_live_r65", LIVE_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load UniversalForexBot_MT5.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

LIVE = live_module()

def read_csv(path):
    d = pd.read_csv(path)
    cols = {str(c).strip().lower(): c for c in d.columns}
    def pick(*names):
        for name in names:
            if name in cols:
                return cols[name]
        return None
    dt = pick("datetime","date","time","timestamp")
    op = pick("open"); hi = pick("high"); lo = pick("low"); cl = pick("close")
    vol = pick("vol","volume","tick_volume","tickvolume")
    if not all([dt,op,hi,lo,cl]):
        raise ValueError("CSV requires datetime/time + OHLC columns.")
    out = pd.DataFrame({
        "datetime": d[dt], "open": d[op], "high": d[hi],
        "low": d[lo], "close": d[cl],
        "vol": d[vol] if vol else 1.0,
    })
    out["datetime"] = pd.to_datetime(out["datetime"], utc=True, errors="coerce")
    if out["datetime"].isna().all():
        raw = pd.to_numeric(d[dt], errors="coerce")
        unit = "ms" if raw.median() > 1e11 else "s"
        out["datetime"] = pd.to_datetime(raw, unit=unit, utc=True, errors="coerce")
    for c in ["open","high","low","close","vol"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["datetime","open","high","low","close"]).sort_values("datetime")
    out = out.drop_duplicates("datetime").reset_index(drop=True)
    out["time"] = (out["datetime"].astype("int64") // 10**6).astype("int64")
    if len(out) < 500:
        raise ValueError("At least 500 candles are required for R6.5 warm-up.")
    return out

def fetch_mt5(symbol, timeframe, start, end):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    tf_map = {
        "1m": getattr(mt5,"TIMEFRAME_M1",None),
        "3m": getattr(mt5,"TIMEFRAME_M3",None),
        "5m": getattr(mt5,"TIMEFRAME_M5",None),
        "15m": getattr(mt5,"TIMEFRAME_M15",None),
        "30m": getattr(mt5,"TIMEFRAME_M30",None),
        "1h": getattr(mt5,"TIMEFRAME_H1",None),
        "4h": getattr(mt5,"TIMEFRAME_H4",None),
    }
    tf = tf_map.get(str(timeframe).lower())
    if tf is None:
        raise ValueError(f"Unsupported MT5 timeframe: {timeframe}")
    a = pd.Timestamp(start, tz="UTC").to_pydatetime()
    b = pd.Timestamp(end, tz="UTC").to_pydatetime()
    rates = mt5.copy_rates_range(symbol, tf, a, b)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No MT5 history returned: {mt5.last_error()}")
    d = pd.DataFrame(rates)
    d["datetime"] = pd.to_datetime(d["time"], unit="s", utc=True)
    d["time"] = d["time"].astype("int64") * 1000
    d = d.rename(columns={"tick_volume":"vol"})
    if "vol" not in d:
        d["vol"] = 1.0
    return d[["datetime","time","open","high","low","close","vol"]].copy()

def build_frame(raw, c):
    x = raw.copy()
    x = LIVE.calculate_supertrend(x,int(c["st_len"]),float(c["st_mult"]),c["st_source"],bool(c["st_change_atr"]))
    x = LIVE.calculate_adx(x,int(c["adx_len"]))
    x["ema"] = x["close"].ewm(span=int(c["ema_len"]),adjust=False).mean()
    x["ema_fast"] = x["close"].ewm(span=int(c["ema_fast"]),adjust=False).mean()
    x["ema_slow"] = x["close"].ewm(span=int(c["ema_slow"]),adjust=False).mean()
    if c["use_macd"]: x=LIVE.calculate_macd(x,int(c["macd_fast"]),int(c["macd_slow"]),int(c["macd_signal"]))
    if c["use_rsi"]:
        x=LIVE.calculate_rsi(x,int(c["rsi_len"]))
        x=LIVE.calculate_rsi_ma(x,c["rsi_ma_type"],int(c["rsi_ma_len"]))
    if c["use_bb"]: x=LIVE.calculate_bollinger(x,int(c["bb_len"]),float(c["bb_std"]))
    if c["use_stoch"]: x=LIVE.calculate_stochastic(x,int(c["stoch_k"]),int(c["stoch_smooth"]),int(c["stoch_d"]))
    if c["use_vwap"]: x=LIVE.calculate_vwap(x,int(c["vwap_len"]))
    if c["use_vwap_delta"]:
        x=LIVE.calculate_vwap_delta(x,bool(c["vwap_delta_smooth"]),int(c["vwap_delta_smooth_len"]),int(c["vwap_delta_baseline"]))
    if c["use_vidya"]:
        x=LIVE.calculate_vidya(x,int(c["vidya_len"]),int(c["vidya_momentum"]),float(c["vidya_band"]),200,15)
    if c["use_nwe"]:
        x=LIVE.calculate_nadaraya_watson_envelope(x,float(c["nwe_bandwidth"]),float(c["nwe_mult"]),500,499)
    x["vol_ma"]=x["vol"].rolling(int(c["vol_len"])).mean()
    if c["use_liq_swing"]:
        x=LIVE.calculate_liquidity_swings(x,int(c["liq_len"]),c["liq_area"],c["liq_filter"],float(c["liq_filter_value"]))
    if c["use_trendline"]:
        x=LIVE.calculate_trendline_breakout(x,int(c["trend_len"]),int(c["trend_min_dist"]),float(c["trend_buffer"]),int(c["trend_retest"]))
    if c["use_divergence"]:
        x=LIVE.calculate_divergence_module(x,dict(c))
    if c["use_vol_sr"]:
        x=LIVE._volume_sr_base_series(x,dict(c))
    if c["use_mtf"]:
        h=x.set_index("datetime").resample("4h",label="left",closed="left").agg(
            {"open":"first","high":"max","low":"min","close":"last","vol":"sum"}).dropna()
        h["ema200"]=h["close"].ewm(span=200,adjust=False).mean()
        h["available_at"]=h.index+pd.Timedelta(hours=4)
        x=pd.merge_asof(x.sort_values("datetime"),
                        h[["available_at","close","ema200"]].rename(columns={"close":"mtf_close"}).sort_values("available_at"),
                        left_on="datetime",right_on="available_at",direction="backward")
        x["mtf_bull"]=x["mtf_close"]>x["ema200"]
        x["mtf_bear"]=x["mtf_close"]<x["ema200"]
    else:
        x["mtf_bull"]=True; x["mtf_bear"]=True
    x["mtf_bull"]=x["mtf_bull"].astype("boolean").fillna(False).astype(bool)
    x["mtf_bear"]=x["mtf_bear"].astype("boolean").fillna(False).astype(bool)
    return x.reset_index(drop=True)

def votes_at(x,i,c):
    q=x.iloc[i]; p=x.iloc[i-1]; pp=x.iloc[i-2]
    close=float(q.close); votes=[]
    if c["use_st"]:
        b=bool(q.trend); d=not b
        if c["st_entry_mode"]=="CURRENT_TREND":
            votes.append(("ST",b,d))
        else:
            votes.append(("ST",not bool(pp.trend) and b,bool(pp.trend) and not b))
    if c["use_ema"]: votes.append(("EMA",close>q.ema,close<q.ema))
    if c["use_ema_cross"]:
        if c["ema_cross_entry_mode"]=="CURRENT_TREND":
            votes.append(("EMA_CROSS",q.ema_fast>q.ema_slow,q.ema_fast<q.ema_slow))
        else:
            votes.append(("EMA_CROSS",p.ema_fast<=p.ema_slow and q.ema_fast>q.ema_slow,p.ema_fast>=p.ema_slow and q.ema_fast<q.ema_slow))
    if c["use_macd"]: votes.append(("MACD",q.macd>q.macd_signal,q.macd<q.macd_signal))
    if c["use_rsi"]:
        if c["rsi_logic"]=="CROSS_MA":
            votes.append(("RSI",p.rsi<=p.rsi_ma and q.rsi>q.rsi_ma,p.rsi>=p.rsi_ma and q.rsi<q.rsi_ma))
        elif c["rsi_logic"]=="EITHER":
            rb=q.rsi<=c["rsi_os"] or (p.rsi<=p.rsi_ma and q.rsi>q.rsi_ma)
            rs=q.rsi>=c["rsi_ob"] or (p.rsi>=p.rsi_ma and q.rsi<p.rsi_ma)
            votes.append(("RSI",rb,rs))
        else:
            votes.append(("RSI",q.rsi<=c["rsi_os"],q.rsi>=c["rsi_ob"]))
    if c["use_bb"]: votes.append(("BB",close>q.bb_upper,close<q.bb_lower))
    if c["use_stoch"]:
        votes.append(("STOCH",p.stoch_k<=p.stoch_d and q.stoch_k>q.stoch_d,p.stoch_k>=p.stoch_d and q.stoch_k<q.stoch_d))
    if c["use_vwap"]: votes.append(("VWAP",close>q.vwap,close<q.vwap))
    if c["use_vwap_delta"]:
        if c["vwap_delta_logic"]=="CROSS_BASELINE":
            votes.append(("VWAP_DELTA",p.vwap_delta<=p.vwap_delta_baseline and q.vwap_delta>q.vwap_delta_baseline,p.vwap_delta>=p.vwap_delta_baseline and q.vwap_delta<p.vwap_delta_baseline))
        else: votes.append(("VWAP_DELTA",q.vwap_delta>q.vwap_delta_baseline,q.vwap_delta<q.vwap_delta_baseline))
    if c["use_vidya"]:
        votes.append(("VIDYA",bool(q.vidya_cross_up) if c["vidya_entry_mode"]=="FRESH_FLIP" else bool(q.vidya_trend_up),
                      bool(q.vidya_cross_down) if c["vidya_entry_mode"]=="FRESH_FLIP" else bool(not q.vidya_trend_up)))
    if c["use_nwe"]:
        if c["nwe_entry_mode"]=="FRESH_CROSS":
            votes.append(("NWE",q.close<q.nwe_lower and p.close>=p.nwe_lower,q.close>q.nwe_upper and p.close<=p.nwe_upper))
        else: votes.append(("NWE",q.nwe_out>p.nwe_out,q.nwe_out<p.nwe_out))
    if c["use_liq_swing"]:
        if c["liq_entry_mode"]=="FRESH_BREAK":
            votes.append(("LIQ_SWING",bool(q.liq_swing_high_break),bool(q.liq_swing_low_break)))
        else: votes.append(("LIQ_SWING",q.liq_swing_trend>0,q.liq_swing_trend<0))
    if c["use_trendline"]:
        if c["trend_entry"]=="BREAK_RETEST":
            votes.append(("TRENDLINE",bool(q.trendline_retest_up),bool(q.trendline_retest_down)))
        elif c["trend_entry"]=="CURRENT_TREND":
            votes.append(("TRENDLINE",q.trendline_state>0,q.trendline_state<0))
        else: votes.append(("TRENDLINE",bool(q.trendline_break_up),bool(q.trendline_break_down)))
    if c["use_mtf"]: votes.append(("MTF",bool(q.mtf_bull),bool(q.mtf_bear)))
    if c["use_divergence"]:
        cnt=int(c["div_min_count"])
        if c["div_entry_mode"]=="CURRENT_STATE":
            votes.append(("DIVERGENCE",q.divergence_state>0 and int(q.div_bull_count)>=cnt,q.divergence_state<0 and int(q.div_bear_count)>=cnt))
        else:
            votes.append(("DIVERGENCE",bool(q.div_bull_signal) and int(q.div_bull_count)>=cnt,bool(q.div_bear_signal) and int(q.div_bear_count)>=cnt))
    if c["use_vol_sr"]: votes.append(("VOL_SR",bool(q.sr_bull),bool(q.sr_bear)))
    atr_pct=float(q.atr)/close*100 if close else 0
    atr_pass=(not c["use_atr"]) or atr_pct>=float(c["atr_min_pct"])
    vol_pass=(not c["use_vol"]) or float(q.vol)>float(q.vol_ma)
    adx_pass=(not c["use_adx"]) or float(q.adx)>=float(c["adx_thresh"])
    candle_bull=float(q.close)>float(q.open); candle_bear=float(q.close)<float(q.open)
    if c["use_vol"] and vol_pass: votes.append(("VOL",candle_bull,candle_bear))
    if c["use_adx"] and adx_pass: votes.append(("ADX",q.plus_di>q.minus_di,q.minus_di>q.plus_di))
    if c["use_atr"] and atr_pass: votes.append(("ATR",candle_bull,candle_bear))
    return votes,atr_pass,vol_pass,adx_pass,bool(q.mtf_bull),bool(q.mtf_bear)

def ai_manage(votes,side,atr,entry,c):
    return LIVE.UniversalFuturesBotGUI._ai_agent_trade_management(
        SimpleNamespace(),votes,side,float(atr),float(entry),float(c["risk_pct"]),
        float(c["atr_sl_mult"]),float(c["atr_tp1_mult"]),float(c["atr_tp2_mult"]),
        AI_MIN_FAMILIES,AI_MIN_EDGE,AI_FAMILY_CONFIDENCE,AI_REQUIRE_TREND,
        AI_REQUIRE_STRUCTURE,AI_MAX_CONFLICTS)

def lots_for_risk(equity,risk_pct,stop_distance,tick_size,tick_value,min_lot,lot_step,max_lot):
    if stop_distance<=0 or tick_size<=0 or tick_value<=0: return 0.0
    risk_money=equity*float(risk_pct)/100.0
    loss_per_lot=(stop_distance/tick_size)*tick_value
    raw=risk_money/loss_per_lot if loss_per_lot else 0.0
    raw=min(max_lot,max(min_lot,raw))
    q=math.floor(raw/lot_step+1e-12)*lot_step if lot_step>0 else raw
    return round(q,8) if q>=min_lot else 0.0

def run(df,c,args):
    eq=float(args.capital); peak=eq; position=None; trades=[]; last_flat=None; lock_side=None
    cooldown=pd.Timedelta(minutes=float(c["cooldown_min"]))
    curve=[]
    for i in range(450,len(df)-1):
        row=df.iloc[i]; now=pd.Timestamp(row.datetime)
        if peak>0 and (peak-eq)/peak*100>=args.max_dd_pct: break
        if args.capital>0 and (args.capital-eq)/args.capital*100>=args.emergency_loss_pct: break

        if position is not None:
            hi=float(row.high); lo=float(row.low); side=position["side"]; sl=position["sl"]; tp1=position["tp1"]; tp2=position["tp2"]
            sl_hit=(lo<=sl) if side=="LONG" else (hi>=sl)
            if sl_hit:
                px=sl; rem=position["remaining"]; gross=(px-position["entry"] if side=="LONG" else position["entry"]-px)*rem*args.contract_size
                commission=rem*args.commission_per_lot; eq+=gross-commission
                t=position["trade"]; t.realized_net+=gross-commission; t.commission+=commission; t.exit_price=px; t.exit_time=str(now); t.exit_reason="SL_BE" if position["be"] else "SL"
                trades.append(t); lock_side=side; position=None; last_flat=now; peak=max(peak,eq); continue
            if not position["tp1_done"]:
                hit=(hi>=tp1) if side=="LONG" else (lo<=tp1)
                if hit:
                    rem_tp1=position["tp1_lots"]; px=tp1; gross=(px-position["entry"] if side=="LONG" else position["entry"]-px)*rem_tp1*args.contract_size
                    eq+=gross-rem_tp1*args.commission_per_lot; t=position["trade"]; t.realized_net+=gross-rem_tp1*args.commission_per_lot
                    t.tp1_lots=rem_tp1; position["remaining"]-=rem_tp1; position["tp1_done"]=True
                    if c["tp1_be"]: position["sl"]=position["entry"]; position["be"]=True
                    be_hit=(lo<=position["entry"]) if side=="LONG" else (hi>=position["entry"])
                    if position["remaining"]>1e-12 and position["be"] and be_hit:
                        rem=position["remaining"]; px=position["entry"]; gross=0.0; eq-=rem*args.commission_per_lot
                        t.realized_net-=rem*args.commission_per_lot; t.exit_price=px; t.exit_time=str(now); t.exit_reason="TP1_BE"; trades.append(t); lock_side=side; position=None; last_flat=now; peak=max(peak,eq); continue
            if position is not None and position["remaining"]>1e-12:
                hit=(hi>=tp2) if side=="LONG" else (lo<=tp2)
                if hit:
                    rem=position["remaining"]; px=tp2; gross=(px-position["entry"] if side=="LONG" else position["entry"]-px)*rem*args.contract_size
                    eq+=gross-rem*args.commission_per_lot; t=position["trade"]; t.realized_net+=gross-rem*args.commission_per_lot; t.exit_price=px; t.exit_time=str(now); t.exit_reason="TP2"; trades.append(t); position=None; last_flat=now; peak=max(peak,eq); continue
            curve.append({"datetime":str(now),"equity":eq,"peak":peak})

        if position is not None: continue
        if int(c["max_trades"])>0 and len(trades)>=int(c["max_trades"]): break
        if last_flat is not None and now-last_flat<cooldown: continue

        votes,ap,vp,dp,mb,ms=votes_at(df,i,c)
        buy,sell,_,_=LIVE.StrategyEngine.decide_signal(votes,"AI_AGENT",1,atr_pass=ap,vol_pass=vp,adx_pass=dp,mtf_pass_bull=mb,mtf_pass_bear=ms,
            ai_min_families=AI_MIN_FAMILIES,ai_min_edge=AI_MIN_EDGE,ai_min_family_confidence=AI_FAMILY_CONFIDENCE,
            ai_require_trend=AI_REQUIRE_TREND,ai_require_structure=AI_REQUIRE_STRUCTURE,ai_max_conflicting_families=AI_MAX_CONFLICTS)
        side="LONG" if buy and not sell else "SHORT" if sell and not buy else None
        if side is None or (lock_side and side==lock_side): continue

        entry=float(df.iloc[i+1].open) + (args.spread_points*args.point_size + args.slippage_points*args.point_size if side=="LONG" else -(args.spread_points*args.point_size + args.slippage_points*args.point_size))
        mgr=ai_manage(votes,side,float(row.atr),entry,c)
        stop_distance=float(row.atr)*float(mgr["atr_sl_mult"])
        lots=lots_for_risk(eq,mgr["risk_pct"],stop_distance,args.tick_size,args.tick_value,args.min_lot,args.lot_step,args.max_lot)
        if lots<=0: continue
        q1=round(lots*float(c["tp1_close_pct"])/100.0,8); q2=round(lots-q1,8)
        if q1<=0 or q2<=0: continue
        if side=="LONG":
            sl=entry-stop_distance; tp1=entry+stop_distance*float(mgr["tp1_r"]); tp2=entry+stop_distance*float(mgr["tp2_r"])
        else:
            sl=entry+stop_distance; tp1=entry-stop_distance*float(mgr["tp1_r"]); tp2=entry-stop_distance*float(mgr["tp2_r"])
        tr=SimpleNamespace(
            side=side,signal_time=str(now),entry_time=str(df.iloc[i+1].datetime),entry=entry,lots=lots,
            sl=sl,tp1=tp1,tp2=tp2,tp1_lots=q1,tp2_lots=q2,
            ai_risk_pct=mgr["risk_pct"],ai_sl_atr=mgr["atr_sl_mult"],ai_tp1_r=mgr["tp1_r"],ai_tp2_r=mgr["tp2_r"],
            ai_edge=mgr["edge"],ai_confidence=mgr["confidence"],ai_conviction=mgr["conviction"],ai_families=",".join(mgr["families"]),
            realized_net=0.0,commission=0.0,exit_price=0.0,exit_time="",exit_reason="")
        position={"side":side,"entry":entry,"sl":sl,"tp1":tp1,"tp2":tp2,"tp1_lots":q1,"remaining":lots,"tp1_done":False,"be":False,"trade":tr}

        lock_side=None
        peak=max(peak,eq)

    if position is not None:
        row=df.iloc[-1]; px=float(row.close); rem=position["remaining"]
        gross=(px-position["entry"] if position["side"]=="LONG" else position["entry"]-px)*rem*args.contract_size
        eq+=gross-rem*args.commission_per_lot; t=position["trade"]; t.realized_net+=gross-rem*args.commission_per_lot; t.exit_price=px; t.exit_time=str(row.datetime); t.exit_reason="END"; trades.append(t)

    curve_df=pd.DataFrame(curve)
    if curve_df.empty: curve_df=pd.DataFrame([{"datetime":str(df.iloc[-1].datetime),"equity":eq,"peak":eq}])
    curve_df["peak"]=curve_df["equity"].cummax()
    curve_df["dd_pct"]=(curve_df["equity"]-curve_df["peak"])/curve_df["peak"]*100
    return trades,eq,curve_df

def main():
    p=argparse.ArgumentParser(description="Universal Forex MT5 AI-Agent R6.5 backtester")
    p.add_argument("--source",choices=("csv","mt5"),default="csv")
    p.add_argument("--input",type=Path)
    p.add_argument("--symbol",default="EURUSD")
    p.add_argument("--timeframe",default="15m")
    p.add_argument("--start",default="2026-01-01")
    p.add_argument("--end",default="2026-09-01")
    p.add_argument("--capital",type=float,default=1000.0)
    p.add_argument("--tick-size",type=float,default=0.00001)
    p.add_argument("--tick-value",type=float,default=1.0)
    p.add_argument("--contract-size",type=float,default=100000.0)
    p.add_argument("--min-lot",type=float,default=0.01)
    p.add_argument("--max-lot",type=float,default=100.0)
    p.add_argument("--lot-step",type=float,default=0.01)
    p.add_argument("--point-size",type=float,default=0.00001)
    p.add_argument("--spread-points",type=float,default=15.0)
    p.add_argument("--slippage-points",type=float,default=2.0)
    p.add_argument("--commission-per-lot",type=float,default=0.0)
    p.add_argument("--max-dd-pct",type=float,default=5.0)
    p.add_argument("--emergency-loss-pct",type=float,default=10.0)
    a=p.parse_args()
    if str(DEFAULT["grid_mode"]).upper()!="OFF": raise ValueError("Forex R6.5 Grid Mode must be OFF.")
    c=dict(DEFAULT)
    if a.source=="csv":
        if not a.input: raise ValueError("--input is required with --source=csv")
        raw=read_csv(a.input)
    else:
        raw=fetch_mt5(a.symbol,a.timeframe,a.start,a.end)
    raw=raw[(raw.datetime>=pd.Timestamp(a.start,tz="UTC")) & (raw.datetime<=pd.Timestamp(a.end,tz="UTC"))].reset_index(drop=True)
    if len(raw)<500: raise ValueError("Not enough candles after date filtering.")
    frame=build_frame(raw,c)
    trades,ending,curve=run(frame,{**c,"max_dd_pct":a.max_dd_pct,"emergency_loss_pct":a.emergency_loss_pct},
                            SimpleNamespace(capital=a.capital,contract_size=a.contract_size,tick_size=a.tick_size,tick_value=a.tick_value,
                                            min_lot=a.min_lot,max_lot=a.max_lot,lot_step=a.lot_step,point_size=a.point_size,
                                            spread_points=a.spread_points,slippage_points=a.slippage_points,commission_per_lot=a.commission_per_lot,
                                            max_dd_pct=a.max_dd_pct,emergency_loss_pct=a.emergency_loss_pct))
    RESULT_DIR.mkdir(exist_ok=True)
    stem=f"{a.symbol}_{a.timeframe}_{a.start.replace(':','-')}_{a.end.replace(':','-')}"
    rows=[getattr(t,"__dict__",{}) for t in trades]
    pd.DataFrame(rows).to_csv(RESULT_DIR/f"trades_{stem}.csv",index=False)
    curve.to_csv(RESULT_DIR/f"equity_{stem}.csv",index=False)
    net=ending-a.capital; wins=sum(1 for t in trades if getattr(t,"realized_net",0)>0)
    losses=sum(1 for t in trades if getattr(t,"realized_net",0)<=0)
    gross_w=sum(max(0,getattr(t,"realized_net",0)) for t in trades)
    gross_l=sum(max(0,-getattr(t,"realized_net",0)) for t in trades)
    metrics={"version":"V8.4.2-FOREX-AI-AGENT-R6.5-BT","symbol":a.symbol,"timeframe":a.timeframe,
             "trades":len(trades),"wins":wins,"losses":losses,"win_rate_pct":wins/len(trades)*100 if trades else 0,
             "net_pnl":net,"return_pct":net/a.capital*100 if a.capital else 0,
             "max_drawdown_pct":float(abs(curve.dd_pct.min())) if not curve.empty else 0,
             "profit_factor":gross_w/gross_l if gross_l else None,"ending_equity":ending,
             "ai_contract":{"min_families":AI_MIN_FAMILIES,"min_edge":AI_MIN_EDGE,"family_confidence":AI_FAMILY_CONFIDENCE,
                            "require_trend":AI_REQUIRE_TREND,"require_structure":AI_REQUIRE_STRUCTURE,"max_conflicts":AI_MAX_CONFLICTS,
                            "risk_envelope":[AI_MIN_RISK,AI_MAX_RISK],"sl_envelope":[AI_MIN_SL,AI_MAX_SL],
                            "tp1_envelope":[AI_MIN_TP1,AI_MAX_TP1],"tp2_envelope":[AI_MIN_TP2,AI_MAX_TP2]}}
    (RESULT_DIR/f"summary_{stem}.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    print("V8.4.2-FOREX-AI-AGENT-R6.5-BT")
    print(json.dumps(metrics,indent=2))
    print("Results:",RESULT_DIR)

if __name__=="__main__":
    main()
