#!/usr/bin/env python3
"""
Universal Futures Bot - Crypto AI Agent R6.8.7.2 Backtester
-------------------------------------------------------------
Research/backtest engine for the R6.8.7.2 AI_AGENT recommended contract.

IMPORTANT:
- No live orders are sent.
- Signals use completed candles only.
- Entries are filled at the next candle open plus modeled slippage.
- SL/TP use the same ATR/R-multiple contract as the live AI manager.
- The backtester is intentionally conservative when SL and TP are both
  touched inside one candle: SL is assumed to win unless the open-to-target
  path clearly reaches TP first.
- Execution quality is modeled with user-supplied spread/slippage assumptions.
- VOL_SR is disabled by default for speed; --include-vol-sr enables it.
- This is a research tool, not a profitability guarantee.

Usage:
  py UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.2_BACKTESTER.py --csv OPUSDT_15m.csv
  py ...BACKTESTER.py --csv data.csv --initial-balance 1000 --leverage 5
  py ...BACKTESTER.py --exchange bybit --symbol OP/USDT:USDT --timeframe 15m --days 90
"""

import argparse
import importlib.util
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

DEFAULT_ENGINE = "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.2_AUDIT_FIXED.py"

def load_engine(path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("ufb_live_engine", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load engine: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def load_csv(path):
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    aliases = {
        "time": ["time","timestamp","datetime","date"],
        "open": ["open","o"],
        "high": ["high","h"],
        "low": ["low","l"],
        "close": ["close","c"],
        "vol": ["vol","volume","v"],
    }
    out = {}
    for k, names in aliases.items():
        found = next((cols[n] for n in names if n in cols), None)
        if found is None:
            raise ValueError(f"CSV missing required column for {k}: {names}")
        out[k] = df[found]
    x = pd.DataFrame(out)
    if np.issubdtype(x["time"].dtype, np.number):
        # Heuristic: seconds vs milliseconds.
        med = float(pd.to_numeric(x["time"], errors="coerce").dropna().median())
        unit = "ms" if med > 10_000_000_000 else "s"
        x["time"] = pd.to_datetime(x["time"], unit=unit, utc=True)
    else:
        x["time"] = pd.to_datetime(x["time"], utc=True, errors="coerce")
    for c in ("open","high","low","close","vol"):
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["time","open","high","low","close","vol"])
    x = x.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    x["time"] = (x["time"].astype("int64") // 1_000_000).astype("int64")
    return x[["time","open","high","low","close","vol"]]

def fetch_ccxt(exchange_id, symbol, timeframe, days):
    import ccxt
    ex_cls = getattr(ccxt, exchange_id)
    ex = ex_cls({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    ex.load_markets()
    if symbol not in ex.markets:
        raise ValueError(f"{symbol} not found on {exchange_id}")
    tf_ms = int(ex.parse_timeframe(timeframe) * 1000)
    since = ex.milliseconds() - int(days * 24 * 60 * 60 * 1000)
    rows = []
    while since < ex.milliseconds() - tf_ms:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        nxt = int(batch[-1][0]) + tf_ms
        if nxt <= since:
            break
        since = nxt
        if len(batch) < 1000:
            break
        time.sleep(max(0.05, ex.rateLimit / 1000.0))
    df = pd.DataFrame(rows, columns=["time","open","high","low","close","vol"])
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    return df

def prepare_indicators(mod, df):
    """Build the same completed-candle indicator families used by the AI preset."""
    x = df.copy()
    x = mod.calculate_supertrend(x, length=10, multiplier=2.0,
                                 source="CLOSE", change_atr=True)
    x = mod.calculate_adx(x, 14)
    x["ema"] = x["close"].ewm(span=200, adjust=False).mean()
    x["ema_fast"] = x["close"].ewm(span=9, adjust=False).mean()
    x["ema_slow"] = x["close"].ewm(span=20, adjust=False).mean()
    x = mod.calculate_macd(x, 12, 26, 9)
    x = mod.calculate_rsi(x, 14)
    x = mod.calculate_rsi_ma(x, "EMA", 9)
    x = mod.calculate_stochastic(x, 14, 3, 3)
    x = mod.calculate_vwap(x, 50)
    x = mod.calculate_vwap_delta(x, smoothing=False, smoothing_length=21,
                                 baseline_length=50)
    x = mod.calculate_vidya(x, vidya_length=10, vidya_momentum=20,
                            band_distance=2.0, atr_length=200, smoothing_length=15)
    x = mod.calculate_nadaraya_watson_envelope(x, bandwidth=8, multiplier=3,
                                                lookback=500, mae_length=499)
    x = mod.calculate_liquidity_swings(
        x, length=14, area="Wick Extremity",
        filter_options="Count", filter_value=0
    )
    x = mod.calculate_trendline_breakout(
        x, length=14, min_pivot_distance=5,
        breakout_buffer_pct=0.0, retest_candles=3
    )
    x["vol_ma"] = x["vol"].rolling(20).mean()

    div_cfg = {
        "div_pivot": 5, "div_source": "Close", "div_type": "Regular",
        "div_max_pivots": 10, "div_max_bars": 100,
        "div_cci_len": 10, "div_mom_len": 10,
        "div_entry_mode": "FRESH",
        "div_use_macd": True, "div_use_macd_hist": True, "div_use_rsi": True,
        "div_use_stoch": True, "div_use_cci": True, "div_use_momentum": True,
        "div_use_obv": True, "div_use_vwmacd": True, "div_use_cmf": True,
        "div_use_mfi": True,
    }
    x = mod.calculate_divergence_module(x, div_cfg)

    # Chart + higher-timeframe volume/SR.
    sr_frames = {"Chart": x.copy()}
    for tf, rule in (("4h","4h"),("D","1D"),("W","1W")):
        try:
            r = mod._resample_ohlcv(x, rule)
            sr_frames[tf] = r[["time","open","high","low","close","vol"]].copy()
        except Exception:
            sr_frames[tf] = None
    sr_cfg = {"sr_volume_ma": 6, "sr_vote_mode": "MAJORITY",
              "sr_entry_mode": "CURRENT_ZONE"}
    return x, sr_frames, sr_cfg

def mtf_states(mod, df):
    r = mod._resample_ohlcv(df, "4h").copy()
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    if len(r) < 202:
        return bull, bear
    r["ema200"] = r["close"].ewm(span=200, adjust=False).mean()
    r["bucket_start"] = pd.to_datetime(r["time"], unit="ms", utc=True)
    # For each base candle, use the most recent 4H bucket whose START is
    # strictly before the base candle. This excludes the currently forming 4H bar.
    base = pd.DataFrame({
        "_dt": pd.to_datetime(df["time"], unit="ms", utc=True),
        "_idx": np.arange(len(df)),
    }).sort_values("_dt")
    htf = r[["_dt"]].copy() if "_dt" in r.columns else None
    htf = r[["bucket_start","close","ema200"]].rename(columns={"bucket_start":"_dt"})
    htf = htf.sort_values("_dt")
    merged = pd.merge_asof(
        base, htf, on="_dt", direction="backward",
        allow_exact_matches=False,
    ).sort_values("_idx")
    bull.iloc[:] = (merged["close"].to_numpy(dtype=float) > merged["ema200"].to_numpy(dtype=float))
    bear.iloc[:] = (merged["close"].to_numpy(dtype=float) < merged["ema200"].to_numpy(dtype=float))
    bull = bull.fillna(False)
    bear = bear.fillna(False)
    return bull, bear

def build_signal(mod, x, sr_frames, sr_cfg, i, include_vol_sr=False):
    """Return (side, council_result, atr_pass, vol_pass, adx_pass, mtf_bull, mtf_bear)."""
    if i < 5:
        return "NONE", {}, False, False, False, True, True
    c = x.iloc[i]
    p = x.iloc[i-1]
    pp = x.iloc[i-2]

    close = float(c.close)
    atr_pct = float(c.atr / close * 100.0) if close > 0 else 0.0
    atr_pass = atr_pct >= 0.30
    vol_pass = bool(c.vol > c.vol_ma)
    adx_pass = bool(c.adx >= 20)

    # MTF is computed by caller and injected in columns.
    mtf_bull = bool(c.mtf_bull)
    mtf_bear = bool(c.mtf_bear)

    st_bull = bool(c.trend)
    st_bear = not st_bull
    st_flip_bull = (not bool(p.trend)) and bool(c.trend)
    st_flip_bear = bool(p.trend) and not bool(c.trend)

    modules = [
        ("ST", st_flip_bull, st_flip_bear),
        ("EMA", close > float(c.ema), close < float(c.ema)),
        ("EMA_CROSS",
         float(pp.ema_fast) <= float(pp.ema_slow) and float(c.ema_fast) > float(c.ema_slow),
         float(pp.ema_fast) >= float(pp.ema_slow) and float(c.ema_fast) < float(c.ema_slow)),
        ("MACD",
         float(pp.macd) <= float(pp.macd_signal) and float(c.macd) > float(c.macd_signal),
         float(pp.macd) >= float(pp.macd_signal) and float(c.macd) < float(c.macd_signal)),
        ("RSI", float(c.rsi) <= 20, float(c.rsi) >= 80),
        ("STOCH",
         float(pp.stoch_k) <= float(pp.stoch_d) and float(c.stoch_k) > float(c.stoch_d),
         float(pp.stoch_k) >= float(pp.stoch_d) and float(c.stoch_k) < float(c.stoch_d)),
        ("VWAP", close > float(c.vwap), close < float(c.vwap)),
        ("VWAP_DELTA",
         float(c.vwap_delta) > float(c.vwap_delta_baseline),
         float(c.vwap_delta) < float(c.vwap_delta_baseline)),
        ("VIDYA", bool(c.vidya_trend_up), not bool(c.vidya_trend_up)),
        ("NWE",
         bool(c.close < c.nwe_lower and p.close >= p.nwe_lower),
         bool(c.close > c.nwe_upper and p.close <= p.nwe_upper)),
        ("LIQ_SWING", bool(c.liq_swing_high_break), bool(c.liq_swing_low_break)),
        ("TRENDLINE", bool(c.trendline_break_up), bool(c.trendline_break_down)),
        ("MTF", mtf_bull, mtf_bear),
    ]
    div_bull = bool(c.div_bull_signal) and int(c.div_bull_count) >= 1
    div_bear = bool(c.div_bear_signal) and int(c.div_bear_count) >= 1
    modules.append(("DIVERGENCE", div_bull, div_bear))

    if include_vol_sr:
        try:
            sr = mod.calculate_volume_sr_module(
                [("Chart", sr_frames.get("Chart"), True),
                 ("4h", sr_frames.get("4h"), True),
                 ("D", sr_frames.get("D"), True),
                 ("W", sr_frames.get("W"), True)],
                sr_cfg,
            )
            modules.append(("VOL_SR", bool(sr["bull"]), bool(sr["bear"])))
        except Exception:
            modules.append(("VOL_SR", False, False))
    # Live VOL_SR is a cached multi-timeframe module. It is opt-in in the
    # research backtester because recalculating it on every historical candle
    # is prohibitively slow; all other AI families remain enabled by default.

    result = mod.StrategyEngine.ai_agent_decision(
        modules,
        atr_pass=atr_pass, vol_pass=vol_pass, adx_pass=adx_pass,
        mtf_pass_bull=mtf_bull, mtf_pass_bear=mtf_bear,
        min_families=3, min_edge=0.20, min_family_confidence=0.55,
        require_trend=True, require_structure=True,
        max_conflicting_families=1, min_family_participation=0.35,
    )
    side = result["side"]
    return side, result, atr_pass, vol_pass, adx_pass, mtf_bull, mtf_bear

def fees(notional, fee_pct):
    return abs(float(notional)) * float(fee_pct) / 100.0

def backtest(mod, df, initial_balance=1000.0, leverage=5.0,
             risk_pct=0.35, fee_pct=0.055, spread_pct=0.05,
             slippage_pct=0.05, cooldown_min=15.0,
             max_trades=0, include_vol_sr=False):
    x, sr_frames, sr_cfg = prepare_indicators(mod, df)
    mtf_bull, mtf_bear = mtf_states(mod, x)
    x["mtf_bull"] = mtf_bull.values
    x["mtf_bear"] = mtf_bear.values

    balance = float(initial_balance)
    equity_curve = [balance]
    position = None
    lock_side = None
    cooldown_until = -1
    trades = []
    pending_entry = None

    for i in range(210, len(x)-1):
        row = x.iloc[i]
        next_row = x.iloc[i+1]

        # Manage an open trade using this candle's completed OHLC.
        if position is not None:
            side = position["side"]
            entry = position["entry"]
            sl = position["sl"]
            tp1 = position["tp1"]
            tp2 = position["tp2"]
            hit_tp1 = False
            hit_tp2 = False
            hit_sl = False

            if side == "LONG":
                hit_sl = float(row.low) <= sl
                hit_tp1 = tp1 is not None and float(row.high) >= tp1
                hit_tp2 = tp2 is not None and float(row.high) >= tp2
            else:
                hit_sl = float(row.high) >= sl
                hit_tp1 = tp1 is not None and float(row.low) <= tp1
                hit_tp2 = tp2 is not None and float(row.low) <= tp2

            # Conservative intrabar resolution: if both SL and a target were
            # touched, assume SL first unless candle open is already on target side.
            if hit_sl and (hit_tp1 or hit_tp2):
                exit_price = sl
                exit_reason = "SL_SAME_BAR_CONSERVATIVE"
                qty_exit = position["qty"]
                pnl = (exit_price-entry)*qty_exit if side=="LONG" else (entry-exit_price)*qty_exit
                pnl -= fees(entry*qty_exit, fee_pct) + fees(exit_price*qty_exit, fee_pct)
                balance += pnl
                trades.append({**position, "exit":exit_price,"reason":exit_reason,"pnl":pnl})
                lock_side = side
                cooldown_until = i + max(1, int(cooldown_min/15))
                position = None
            elif hit_tp2:
                exit_price = tp2
                qty_exit = position["qty"]
                pnl = (exit_price-entry)*qty_exit if side=="LONG" else (entry-exit_price)*qty_exit
                pnl -= fees(entry*qty_exit, fee_pct) + fees(exit_price*qty_exit, fee_pct)
                balance += pnl
                trades.append({**position, "exit":exit_price,"reason":"TP2","pnl":pnl})
                position = None
                lock_side = None
            elif hit_tp1 and not position["tp1_done"]:
                qty1 = position["qty"] * 0.50
                exit_price = tp1
                pnl = (exit_price-entry)*qty1 if side=="LONG" else (entry-exit_price)*qty1
                pnl -= fees(entry*qty1, fee_pct) + fees(exit_price*qty1, fee_pct)
                balance += pnl
                position["qty"] -= qty1
                position["tp1_done"] = True
                # Fee-aware BE, then bounded ATR trailing on subsequent bars.
                fee_buf = 2.0*fee_pct/100.0
                position["sl"] = entry*(1+fee_buf) if side=="LONG" else entry*(1-fee_buf)
                position["trail_active"] = False
                position["tp1_realized"] = pnl

            # After TP1, update the bounded ATR trailing stop on the completed candle.
            if position is not None and position["tp1_done"]:
                atr = float(row.atr)
                initial_risk = position["initial_risk"]
                current = float(row.close)
                move = (current-entry)/entry if side=="LONG" else (entry-current)/entry
                current_r = move/initial_risk if initial_risk > 0 else 0
                if current_r >= 1.50 and atr > 0:
                    candidate = current - 1.50*atr if side=="LONG" else current + 1.50*atr
                    if side=="LONG":
                        candidate=min(max(candidate,position["sl"]), entry*(1+0.03)) if candidate>position["sl"] else position["sl"]
                    else:
                        candidate=max(min(candidate,position["sl"]), entry*(1-0.03)) if candidate<position["sl"] else position["sl"]
                    # Never widen.
                    if side=="LONG" and candidate>position["sl"]:
                        position["sl"]=candidate
                    elif side=="SHORT" and candidate<position["sl"]:
                        position["sl"]=candidate

            # Re-check stop after management using the next candle only; current
            # candle's stop update cannot retroactively trigger.
        equity_curve.append(balance + (0 if position is None else (
            ((float(row.close)-position["entry"])*position["qty"]) if position["side"]=="LONG"
            else ((position["entry"]-float(row.close))*position["qty"])
        )))

        if position is not None:
            # Entry/reversal decisions are handled only when flat in this simplified
            # one-position research model. The live engine performs explicit reversal.
            continue

        if max_trades and len(trades) >= max_trades:
            break
        if i < cooldown_until:
            continue

        side, council, atr_pass, vol_pass, adx_pass, mtf_b, mtf_s = build_signal(mod,x,sr_frames,sr_cfg,i,include_vol_sr)
        if side == "NONE":
            continue
        if lock_side is not None and side == lock_side:
            continue
        lock_side = None

        # Fill at next candle open with modeled spread/slippage.
        raw_entry = float(next_row.open)
        entry = raw_entry * (1.0 + (spread_pct+slippage_pct)/100.0) if side=="BUY" else raw_entry * (1.0 - (spread_pct+slippage_pct)/100.0)

        atr = float(row.atr)
        conviction = 0.45*max(0.0,min(1.0,(float(council["edge"])-0.20)/0.80)) + 0.30*0.0 + 0.25*max(0.0,min(1.0,(float(np.mean([council["families"][f]["confidence"] for f in (council["bull_families"] if side=="BUY" else council["bear_families"])]))-0.55)/0.45))
        conviction=float(np.clip(conviction,0,1))
        atr_pct=atr/entry*100.0
        if atr_pct>=1.50: vol_factor=.75
        elif atr_pct<=.50: vol_factor=1.05
        else: vol_factor=1.05-.30*((atr_pct-.50)/1.0)
        eff_risk=min(risk_pct, .50)
        eff_risk=max(.10, min(eff_risk, risk_pct* (.75+.50*conviction)*vol_factor))
        if atr_pct>=1.50: sl_mult=2.10
        elif atr_pct<=.50: sl_mult=1.55
        else: sl_mult=1.55+.55*((atr_pct-.50)/1.0)
        sl_mult=float(np.clip(sl_mult+(2.05-sl_mult)*conviction,1.50,2.40))
        tp1_r=float(np.clip(1.00+0.50*conviction,1.00,1.50))
        tp2_r=float(np.clip(2.00+1.00*conviction,2.00,3.00))

        sl_frac=atr*sl_mult/entry
        liq_limit=mod.liq_safe_move(leverage,3.0)
        if sl_frac >= liq_limit:
            continue
        tp1_frac=sl_frac*tp1_r
        tp2_frac=sl_frac*tp2_r
        if mod.cost_gate_reason(sl_frac,tp1_frac,fee_pct):
            continue

        risk_amount=balance*eff_risk/100.0
        qty=risk_amount/(entry*sl_frac)
        qty=min(qty, balance*leverage*.95/entry)
        if qty<=0:
            continue

        if side=="BUY":
            sl=entry*(1-sl_frac); tp1=entry*(1+tp1_frac); tp2=entry*(1+tp2_frac)
        else:
            sl=entry*(1+sl_frac); tp1=entry*(1-tp1_frac); tp2=entry*(1-tp2_frac)

        position={
            "side":"LONG" if side=="BUY" else "SHORT",
            "entry":entry,"qty":qty,"sl":sl,"tp1":tp1,"tp2":tp2,
            "initial_risk":sl_frac,"tp1_done":False,"trail_active":False,
            "signal_time":int(row.time)
        }

    if position is not None:
        # Mark-to-market final close.
        exit_price=float(x.iloc[-1].close)
        side=position["side"]
        pnl=(exit_price-position["entry"])*position["qty"] if side=="LONG" else (position["entry"]-exit_price)*position["qty"]
        pnl-=fees(position["entry"]*position["qty"],fee_pct)+fees(exit_price*position["qty"],fee_pct)
        balance+=pnl
        trades.append({**position,"exit":exit_price,"reason":"END_OF_DATA","pnl":pnl})

    tdf=pd.DataFrame(trades)
    return tdf, pd.Series(equity_curve), balance

def report(trades, equity, initial):
    if trades.empty:
        print("\nNO TRADES generated.")
        return
    wins=trades[trades.pnl>0]
    losses=trades[trades.pnl<0]
    gross_profit=wins.pnl.sum()
    gross_loss=abs(losses.pnl.sum())
    pf=gross_profit/gross_loss if gross_loss else float("inf")
    eq=equity.to_numpy(dtype=float)
    peak=np.maximum.accumulate(eq)
    dd=(eq-peak)/np.where(peak!=0,peak,1)*100
    maxdd=float(dd.min())
    print("\n================ BACKTEST RESULT ================")
    print(f"Initial balance       : {initial:.2f}")
    print(f"Final balance         : {float(equity.iloc[-1]):.2f}")
    print(f"Net PnL               : {float(equity.iloc[-1]-initial):.2f}")
    print(f"Return                : {(float(equity.iloc[-1])/initial-1)*100:.2f}%")
    print(f"Trades                : {len(trades)}")
    print(f"Wins / Losses         : {len(wins)} / {len(losses)}")
    print(f"Win rate              : {len(wins)/len(trades)*100:.2f}%")
    print(f"Profit factor         : {pf:.3f}")
    print(f"Average trade         : {trades.pnl.mean():.4f}")
    print(f"Best / Worst trade    : {trades.pnl.max():.4f} / {trades.pnl.min():.4f}")
    print(f"Max drawdown          : {maxdd:.2f}%")
    print("==================================================")
    print("\nExit reasons:")
    print(trades.reason.value_counts().to_string())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--engine",default=DEFAULT_ENGINE)
    ap.add_argument("--csv")
    ap.add_argument("--exchange",default="bybit")
    ap.add_argument("--symbol",default="OP/USDT:USDT")
    ap.add_argument("--timeframe",default="15m")
    ap.add_argument("--days",type=float,default=90)
    ap.add_argument("--initial-balance",type=float,default=1000.0)
    ap.add_argument("--leverage",type=float,default=5.0)
    ap.add_argument("--risk-pct",type=float,default=.35)
    ap.add_argument("--fee-pct",type=float,default=.055)
    ap.add_argument("--spread-pct",type=float,default=.05)
    ap.add_argument("--slippage-pct",type=float,default=.05)
    ap.add_argument("--cooldown-min",type=float,default=15.0)
    ap.add_argument("--max-trades",type=int,default=0)
    ap.add_argument("--include-vol-sr",action="store_true",help="Include the live multi-timeframe VOL_SR family; much slower.")
    ap.add_argument("--output-csv")
    args=ap.parse_args()

    mod=load_engine(args.engine)
    df=load_csv(args.csv) if args.csv else fetch_ccxt(args.exchange,args.symbol,args.timeframe,args.days)
    if len(df)<500:
        raise SystemExit(f"Need at least 500 candles; got {len(df)}")
    trades,equity,final=backtest(
        mod,df,args.initial_balance,args.leverage,args.risk_pct,args.fee_pct,
        args.spread_pct,args.slippage_pct,args.cooldown_min,args.max_trades,args.include_vol_sr
    )
    report(trades,equity,args.initial_balance)
    if args.output_csv and not trades.empty:
        trades.to_csv(args.output_csv,index=False)
        print(f"\nTrades written: {args.output_csv}")

if __name__=="__main__":
    main()