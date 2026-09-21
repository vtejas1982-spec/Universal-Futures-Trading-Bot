"""V8.4.2-R5 Forex/MT5 production strategy-parity backtester.

Uses the canonical R5 live wrapper and its audited indicator/StrategyEngine
implementations. ATR Dynamic protection uses completed-candle ATR and the
1.50 / 1.20 / 2.20 contract.
"""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

LIVE=Path(__file__).with_name("UniversalForexBot_MT5.py")
sp=importlib.util.spec_from_file_location("fx_r5",str(LIVE)); fx=importlib.util.module_from_spec(sp); sp.loader.exec_module(fx)
base=fx

APP_VERSION="V8.4.2-FOREX-EVIDENCE-BT-R5"
AUDIT_BUILD="V8.4.2-ENGINE-AUDIT-2026-09-21-FOREX-R5"
DEFAULTS={"capital":10000.0,"risk_pct":1.0,"leverage":5.0,"contract_size":100000.0,
"signal_mode":"ADAPTIVE_EVIDENCE","min_score":1,"adaptive_edge":0.18,"adaptive_min_weight":3.5,
"evidence_min_families":2,"evidence_family_min_score":0.35,"evidence_require_trend":True,
"evidence_require_independent":True,"max_trades":10,"max_open_trades":1,
"use_st":True,"st_len":10,"st_mult":3.0,"st_source":"CLOSE","st_change_atr":True,"st_entry":"CURRENT_TREND",
"use_ema":True,"ema_len":50,"use_ema_cross":True,"ema_fast":9,"ema_slow":21,"ema_cross_entry":"CURRENT_TREND",
"use_macd":True,"macd_fast":12,"macd_slow":26,"macd_signal":9,"use_rsi":True,"rsi_len":14,"rsi_ob":70,"rsi_os":30,
"rsi_logic":"CROSS_MA","rsi_ma_type":"EMA","rsi_ma_len":9,"use_stoch":True,"stoch_k":14,"stoch_smooth":3,"stoch_d":3,
"use_vwap":True,"vwap_len":50,"use_vwap_delta":True,"vwap_delta_smooth":True,"vwap_delta_smooth_len":21,
"vwap_delta_baseline":50,"vwap_delta_logic":"CURRENT_TREND","use_vidya":False,"use_nwe":False,
"use_atr":False,"atr_min_pct":0.30,"use_vol":True,"vol_len":20,"use_adx":True,"adx_thresh":20,"use_mtf":True,
"use_liq_swing":True,"liq_len":14,"liq_area":"Wick Extremity","liq_filter":"Count","liq_filter_value":0,
"use_trendline":True,"trend_len":14,"trend_min_dist":5,"trend_buffer":0.0,"trend_retest":3,"trend_entry":"FRESH_BREAK",
"use_divergence":True,"div_pivot":5,"div_max_pivots":10,"div_max_bars":100,"div_type":"Regular/Hidden","div_source":"Close",
"div_use_all":True,"div_cci_len":10,"div_mom_len":10,"div_vwmacd_fast":12,"div_vwmacd_slow":26,"div_cmf_len":21,"div_mfi_len":14,
"use_vol_sr":True,"sr_volume_ma":6,"sr_vote_mode":"MAJORITY","sr_entry_mode":"CURRENT_ZONE",
"sl_mode":"PRICE_%","tp_mode":"ROI_%","sl_pct":1.5,"tp1_pct":2.0,"tp2_pct":4.0,
"use_atr_sl":True,"atr_sl_mult":1.5,"atr_tp1_mult":1.2,"atr_tp2_mult":2.2,"tp1_close":50.0,"tp1_be":True,
"daily_loss_pct":3.0,"max_dd_pct":5.0,"emergency_capital_pct":30.0,"max_loss_streak":3,
"no_same_candle":True,"hold_until_all_reverse":False,"require_opposite_after_sl":True}

def load_ohlcv(df):
    x=df.copy()
    if "datetime" not in x:
        if "time" not in x: raise ValueError("Need datetime or time.")
        raw=pd.to_numeric(x.time,errors="coerce"); unit="ms" if raw.median()>1e11 else "s"
        x["datetime"]=pd.to_datetime(raw,unit=unit,utc=True,errors="coerce")
    else:x["datetime"]=pd.to_datetime(x.datetime,utc=True,errors="coerce")
    if "time" not in x:x["time"]=(x.datetime.astype("int64")//10**6).astype("int64")
    if "vol" not in x:x["vol"]=1.0
    return x.sort_values("datetime").dropna(subset=["datetime","open","high","low","close"]).reset_index(drop=True)

def build_frame(df,c):
    x=df.copy(); x=fx.calculate_supertrend(x,int(c["st_len"]),float(c["st_mult"]),c["st_source"],bool(c["st_change_atr"]))
    x=fx.calculate_adx(x); x["ema"]=x.close.ewm(span=int(c["ema_len"]),adjust=False).mean()
    x["ema_fast"]=x.close.ewm(span=int(c["ema_fast"]),adjust=False).mean(); x["ema_slow"]=x.close.ewm(span=int(c["ema_slow"]),adjust=False).mean()
    if c["use_macd"]:x=fx.calculate_macd(x,int(c["macd_fast"]),int(c["macd_slow"]),int(c["macd_signal"]))
    if c["use_rsi"]:x=fx.calculate_rsi(x,int(c["rsi_len"])); x=fx.calculate_rsi_ma(x,c["rsi_ma_type"],int(c["rsi_ma_len"]))
    if c["use_stoch"]:x=fx.calculate_stochastic(x,int(c["stoch_k"]),int(c["stoch_smooth"]),int(c["stoch_d"]))
    if c["use_vwap"]:x=fx.calculate_vwap(x,int(c["vwap_len"]))
    if c["use_vwap_delta"]:x=fx.calculate_vwap_delta(x,bool(c["vwap_delta_smooth"]),int(c["vwap_delta_smooth_len"]),int(c["vwap_delta_baseline"]))
    x["vol_ma"]=x.vol.rolling(int(c["vol_len"])).mean()
    if c["use_liq_swing"]:x=fx.calculate_liquidity_swings(x,int(c["liq_len"]),c["liq_area"],c["liq_filter"],float(c["liq_filter_value"]))
    if c["use_trendline"]:x=fx.calculate_trendline_breakout(x,int(c["trend_len"]),int(c["trend_min_dist"]),float(c["trend_buffer"]),int(c["trend_retest"]))
    if c["use_divergence"]:x=fx.calculate_divergence_module(x,dict(c))
    if c["use_vol_sr"]:x=fx._volume_sr_base_series(x,dict(c))
    if c["use_mtf"]:
        z=x.set_index("datetime").resample("4h",label="left",closed="left").agg({"open":"first","high":"max","low":"min","close":"last","vol":"sum"}).dropna()
        z["ema200"]=z.close.ewm(span=200,adjust=False).mean(); z["available_at"]=z.index+pd.Timedelta(hours=4); z=z.reset_index()
        x=pd.merge_asof(x.sort_values("datetime"),z[["available_at","close","ema200"]].rename(columns={"close":"mtf_close"}).sort_values("available_at"),left_on="datetime",right_on="available_at",direction="backward")
    return x

def _modules(x,i,c):
    q,p,pp=x.iloc[i],x.iloc[i-1],x.iloc[i-2]; close=float(q.close); mods=[]
    atr_pass=(not c["use_atr"]) or float(q.atr)/close*100>=float(c["atr_min_pct"])
    vol_pass=(not c["use_vol"]) or float(q.vol)>float(q.vol_ma); adx_pass=(not c["use_adx"]) or float(q.adx)>=float(c["adx_thresh"])
    mb=(not c["use_mtf"]) or (np.isfinite(q.get("mtf_close",np.nan)) and q.mtf_close>q.ema200); ms=(not c["use_mtf"]) or (np.isfinite(q.get("mtf_close",np.nan)) and q.mtf_close<q.ema200)
    st=bool(q.trend); mods += [("ST",st if c["st_entry"]=="CURRENT_TREND" else ((not bool(pp.trend)) and st), (not st) if c["st_entry"]=="CURRENT_TREND" else (bool(pp.trend) and not st))]
    if c["use_ema"]:mods.append(("EMA",close>q.ema,close<q.ema))
    if c["use_ema_cross"]:mods.append(("EMA_CROSS",q.ema_fast>q.ema_slow,q.ema_fast<q.ema_slow))
    if c["use_macd"]:mods.append(("MACD",q.macd>q.macd_signal,pd.notna(q.macd) and q.macd<q.macd_signal))
    if c["use_rsi"]:mods.append(("RSI",float(q.rsi)>float(q.rsi_ma),float(q.rsi)<float(q.rsi_ma)))
    if c["use_stoch"]:mods.append(("STOCH",q.stoch_k>q.stoch_d,q.stoch_k<q.stoch_d))
    if c["use_vwap"]:mods.append(("VWAP",close>q.vwap,close<q.vwap))
    if c["use_vwap_delta"]:mods.append(("VWAP_DELTA",q.vwap_delta>q.vwap_delta_baseline,q.vwap_delta<q.vwap_delta_baseline))
    if c["use_liq_swing"]:mods.append(("LIQ_SWING",q.liq_swing_trend>0,q.liq_swing_trend<0))
    if c["use_trendline"]:mods.append(("TRENDLINE",bool(q.trendline_break_up),bool(q.trendline_break_down)))
    if c["use_mtf"]:mods.append(("MTF",mb,ms))
    if c["use_divergence"]:mods.append(("DIVERGENCE",bool(q.div_bull_signal),bool(q.div_bear_signal)))
    if c["use_vol_sr"]:mods.append(("VOL_SR",bool(q.sr_bull),bool(q.sr_bear)))
    if c["use_vol"] and vol_pass:mods.append(("VOL",q.close>q.open,q.close<q.open))
    if c["use_adx"] and adx_pass:mods.append(("ADX",q.plus_di>q.minus_di,q.minus_di>q.plus_di))
    return mods,atr_pass,vol_pass,adx_pass,mb,ms

def signal_at(x,i,c):
    mods,ap,vp,dp,mb,ms=_modules(x,i,c)
    args=(mods,c["signal_mode"],int(c["min_score"]),ap,vp,dp,mb,ms,float(c["adaptive_edge"]),float(c["adaptive_min_weight"]),int(c["evidence_min_families"]),float(c["evidence_family_min_score"]),bool(c["evidence_require_trend"]),bool(c["evidence_require_independent"]))
    b,s,_,_=fx.StrategyEngine.decide_signal(*args)
    return ("BUY" if b else "SELL" if s else "NONE"),mods

def run_backtest(df,config=None):
    c=dict(DEFAULTS); c.update(config or {}); c["max_open_trades"]=1
    x=build_frame(load_ohlcv(df),c); equity=float(c["capital"]); start=equity; pos=None; trades=[]
    for i in range(250,len(x)-1):
        if pos:
            hi,lo=float(x.high.iloc[i]),float(x.low.iloc[i])
            if pos["side"]=="BUY":
                if lo<=pos["sl"]:equity+=(pos["sl"]-pos["entry"])*pos["qty"]*c["contract_size"]; trades.append("SL"); pos=None
                elif hi>=pos["tp2"]:equity+=(pos["tp2"]-pos["entry"])*pos["qty"]*c["contract_size"]; trades.append("TP2"); pos=None
                elif hi>=pos["tp1"] and not pos["tp1_done"]:
                    part=pos["qty"]*.5; equity+=(pos["tp1"]-pos["entry"])*part*c["contract_size"]; pos["qty"]-=part; pos["tp1_done"]=True
                    if c["tp1_be"]:pos["sl"]=pos["entry"]
            else:
                if hi>=pos["sl"]:equity+=(pos["entry"]-pos["sl"])*pos["qty"]*c["contract_size"]; trades.append("SL"); pos=None
                elif lo<=pos["tp2"]:equity+=(pos["entry"]-pos["tp2"])*pos["qty"]*c["contract_size"]; trades.append("TP2"); pos=None
                elif lo<=pos["tp1"] and not pos["tp1_done"]:
                    part=pos["qty"]*.5; equity+=(pos["entry"]-pos["tp1"])*part*c["contract_size"]; pos["qty"]-=part; pos["tp1_done"]=True
                    if c["tp1_be"]:pos["sl"]=pos["entry"]
        if pos is None and (not c["max_trades"] or len(trades)<c["max_trades"]):
            sig,_=_modules_signal=signal_at(x,i,c)
            if sig=="NONE":continue
            entry=float(x.open.iloc[i+1]); atr=float(x.atr.iloc[i])
            if c["use_atr_sl"]:
                sd=atr*c["atr_sl_mult"]; d1=sd*c["atr_tp1_mult"]; d2=sd*c["atr_tp2_mult"]
            else:
                sd=entry*c["sl_pct"]/100; d1=entry*c["tp1_pct"]/100/max(c["leverage"],1); d2=entry*c["tp2_pct"]/100/max(c["leverage"],1)
            qty=max(.01,round((equity*c["risk_pct"]/100)/(sd*c["contract_size"]),2))
            pos={"side":sig,"entry":entry,"qty":qty,"sl":entry-sd if sig=="BUY" else entry+sd,"tp1":entry+d1 if sig=="BUY" else entry-d1,"tp2":entry+d2 if sig=="BUY" else entry-d2,"tp1_done":False}
    return {"starting_equity":start,"ending_equity":equity,"net_pnl":equity-start,"trades":len(trades),"max_open_trades":1}

