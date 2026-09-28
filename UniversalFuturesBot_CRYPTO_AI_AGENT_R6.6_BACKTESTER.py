"""
Universal Futures Bot V8.4.2 — Crypto AI-Agent R6.6 Backtester

This backtester is specifically for:
    UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6.py

Design:
    * Public OHLCV data only; no API key is required for backtesting.
    * Completed-candle signals; entry is simulated at the next candle open.
    * Uses the live R6.6 StrategyEngine from the companion production file.
    * Reuses the live indicator functions where available.
    * AI-Agent decision thresholds are identical to the R6.6 recommended preset.
    * AI risk/SL/TP management follows the bounded R6.6 deterministic manager:
        Risk   0.20%–0.50%
        SL     1.50–2.40 ATR
        TP1    1.00–1.50R
        TP2    2.00–3.00R
    * TP1 is partial (50% by default) and moves the remaining SL to break-even.
    * If SL and TP are both touched inside the same candle, SL wins (conservative).
    * No future candle is used to create a signal.
    * Results are written to backtest_results_r6_6/.

Important:
    A historical simulator cannot reproduce every exchange detail such as
    latency, order-book fills, funding, liquidation, trigger semantics or
    network failures. Treat results as research output, not a promise of
    future profitability.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
LIVE_FILE = ROOT / "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6.py"
RESULTS_DIR = ROOT / "backtest_results_r6_6"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

APP_VERSION = "V8.4.2-CRYPTO-AI-AGENT-R6.6-BT"
SUPPORTED_TFS = {"5m", "15m", "30m", "1h", "4h", "1d"}

AI_MIN_FAMILIES = 3
AI_MIN_EDGE = 0.20
AI_MIN_FAMILY_CONFIDENCE = 0.55
AI_REQUIRE_TREND = True
AI_REQUIRE_STRUCTURE = True
AI_MAX_CONFLICTS = 1

AI_MIN_RISK_PCT = 0.20
AI_MAX_RISK_PCT = 0.50
AI_MIN_ATR_SL = 1.50
AI_MAX_ATR_SL = 2.40
AI_MIN_TP1_R = 1.00
AI_MAX_TP1_R = 1.50
AI_MIN_TP2_R = 2.00
AI_MAX_TP2_R = 3.00
AI_HIGH_VOL_ATR_PCT = 1.50
AI_LOW_VOL_ATR_PCT = 0.50

FEE_PCT = 0.04
SLIPPAGE_PCT = 0.01
CAPITAL = 1000.0
RISK_PCT = 0.35
TP1_PCT = 50.0
COOLDOWN_MIN = 15.0
WARMUP = 250


def load_live_module():
    if not LIVE_FILE.exists():
        raise FileNotFoundError(
            f"Companion production file not found: {LIVE_FILE}\n"
            "Keep the R6.6 live engine and this backtester in the same folder."
        )
    spec = importlib.util.spec_from_file_location("crypto_ai_r65_live", LIVE_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load R6.6 production module.")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LIVE = load_live_module()


@dataclass
class Trade:
    side: str
    signal_time: str
    entry_time: str
    exit_time: str = ""
    entry: float = 0.0
    exit_price: float = 0.0
    qty: float = 0.0
    tp1_qty: float = 0.0
    tp2_qty: float = 0.0
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    ai_risk_pct: float = 0.0
    ai_sl_atr: float = 0.0
    ai_tp1_r: float = 0.0
    ai_tp2_r: float = 0.0
    ai_edge: float = 0.0
    ai_confidence: float = 0.0
    ai_conviction: float = 0.0
    ai_families: str = ""
    reason: str = ""
    exit_reason: str = ""
    realized_net: float = 0.0
    fees: float = 0.0


def fetch_ohlcv(exchange_id: str, symbol: str, timeframe: str, start: str, end: str):
    if timeframe not in SUPPORTED_TFS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    exchange_id = exchange_id.lower()
    if exchange_id not in ("bybit", "binance"):
        raise ValueError(
            "This R6.6 standalone backtester supports Bybit and Binance public OHLCV."
        )
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class(
        {"enableRateLimit": True,
         "options": {"defaultType": "swap" if exchange_id == "bybit" else "future"}}
    )

    since = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    until = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    rows = []
    while since < until:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        newest = int(batch[-1][0])
        if newest <= since:
            break
        since = newest + 1

    if not rows:
        raise RuntimeError("No OHLCV data returned.")

    df = pd.DataFrame(
        rows, columns=["time", "open", "high", "low", "close", "vol"]
    )
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    return exchange, df[(df["time"] >= start_ms) & (df["time"] <= end_ms)].copy()


def resample_ohlcv(df, rule):
    x = df.copy()
    x["datetime"] = pd.to_datetime(x["datetime"], utc=True)
    x = x.set_index("datetime")
    out = x.resample(rule, label="left", closed="left").agg(
        {"time": "first", "open": "first", "high": "max", "low": "min",
         "close": "last", "vol": "sum"}
    )
    return out.dropna(subset=["open", "high", "low", "close"]).reset_index()


def build_frame(raw, cfg):
    x = raw.copy()
    x["ema_filter"] = x["close"].ewm(span=200, adjust=False).mean()
    x["ema_fast"] = x["close"].ewm(span=9, adjust=False).mean()
    x["ema_slow"] = x["close"].ewm(span=20, adjust=False).mean()

    x = LIVE.calculate_supertrend(x, 10, 2.0, "CLOSE", True)
    x = LIVE.calculate_adx(x, 14)
    x = LIVE.calculate_macd(x, 12, 26, 9)
    x = LIVE.calculate_rsi(x, 14)
    x = LIVE.calculate_rsi_ma(x, "EMA", 9)
    x = LIVE.calculate_stochastic(x, 14, 3, 3)
    x = LIVE.calculate_vwap(x, 50)
    x = LIVE.calculate_vwap_delta(x, False, 21, 50)
    x = LIVE.calculate_vidya(x, 10, 20, 2.0, 200, 15)
    x = LIVE.calculate_nadaraya_watson_envelope(x, 8.0, 3.0, 500, 499)
    x = LIVE.calculate_liquidity_swings(x, 14, "Wick Extremity", "Count", 0.0)
    x = LIVE.calculate_trendline_breakout(x, 14, 5, 0.0, 3)
    x["vol_ma"] = x["vol"].rolling(20).mean()

    div_cfg = {
        "div_pivot": 5, "div_max_pivots": 10, "div_max_bars": 100,
        "div_type": "Regular", "div_source": "Close", "div_min_count": 1,
        "div_cci_len": 10, "div_mom_len": 10, "div_vwmacd_fast": 12,
        "div_vwmacd_slow": 26, "div_cmf_len": 21, "div_mfi_len": 14,
        "div_use_macd": True, "div_use_macd_hist": True, "div_use_rsi": True,
        "div_use_stoch": True, "div_use_cci": True, "div_use_momentum": True,
        "div_use_obv": True, "div_use_vwmacd": True, "div_use_cmf": True,
        "div_use_mfi": True,
    }
    x = LIVE.calculate_divergence_module(x, div_cfg)

    h4 = resample_ohlcv(raw, "4h")
    h4["ema200_4h"] = h4["close"].ewm(span=200, adjust=False).mean()
    h4["mtf_bull"] = h4["close"] > h4["ema200_4h"]
    h4["mtf_bear"] = h4["close"] < h4["ema200_4h"]
    h4 = h4[["datetime", "mtf_bull", "mtf_bear"]].sort_values("datetime")
    x = pd.merge_asof(
        x.sort_values("datetime"), h4, on="datetime", direction="backward"
    )
    x["mtf_bull"] = x["mtf_bull"].fillna(False)
    x["mtf_bear"] = x["mtf_bear"].fillna(False)
    return x


def make_cfg():
    return {
        "signal_mode": "AI_AGENT", "min_score": 1,
        "adaptive_edge": 0.18, "adaptive_min_weight": 3.5,
        "evidence_min_families": 3, "evidence_family_min_score": 0.35,
        "evidence_require_trend": True, "evidence_require_independent": True,
        "ai_min_families": 3, "ai_min_edge": 0.20, "ai_family_confidence": 0.55,
        "ai_max_conflicts": 1, "ai_require_trend": True, "ai_require_structure": True,
        "st_entry_mode": "FRESH_FLIP", "ema_fast": 9, "ema_slow": 20,
        "ema_cross_entry_mode": "FRESH_CROSS",
        "rsi_logic": "REVERSAL_ZONE", "rsi_ob": 80, "rsi_os": 20,
        "vidya_entry_mode": "CURRENT_TREND", "nwe_entry_mode": "FRESH_CROSS",
        "liq_entry_mode": "FRESH_BREAK", "trendline_entry_mode": "FRESH_BREAK",
        "div_entry_mode": "FRESH", "div_min_count": 1,
        "use_st": True, "use_ema": True, "use_ema_cross": True, "use_macd": True,
        "use_rsi": True, "use_stoch": True, "use_vwap": True,
        "use_vwap_delta": True, "use_vidya": True, "use_nwe": True,
        "use_liq_swings": True, "use_trendline": True, "use_mtf": True,
        "use_divergence": True, "use_vol_sr": False, "use_vol": True,
        "use_adx": True, "use_atr": True, "atr_min_pct": 0.30,
        "adx_thresh": 20.0, "vol_len": 20,
        "risk_pct": RISK_PCT, "atr_tp1_mult": 1.2, "atr_tp2_mult": 2.2,
    }


def module_votes(df, i, cfg):
    if i < 3:
        return [], False, False, False

    p = df.iloc[i - 1]
    c = df.iloc[i]
    close = float(c.close)
    votes = []

    if cfg["use_st"]:
        st_bull = bool(c.trend)
        votes.append(("ST",
                      (not bool(p.trend) and st_bull),
                      (bool(p.trend) and not st_bull)))

    if cfg["use_ema"]:
        votes.append(("EMA", close > float(c.ema_filter), close < float(c.ema_filter)))

    if cfg["use_ema_cross"]:
        up = float(p.ema_fast) <= float(p.ema_slow) and float(c.ema_fast) > float(c.ema_slow)
        dn = float(p.ema_fast) >= float(p.ema_slow) and float(c.ema_fast) < float(c.ema_slow)
        votes.append(("EMA_CROSS", up, dn))

    if cfg["use_macd"]:
        votes.append(("MACD",
                      float(p.macd) <= float(p.macd_signal) and float(c.macd) > float(c.macd_signal),
                      float(p.macd) >= float(p.macd_signal) and float(c.macd) < float(c.macd_signal)))

    if cfg["use_rsi"]:
        votes.append(("RSI",
                      float(c.rsi) <= cfg["rsi_os"],
                      float(c.rsi) >= cfg["rsi_ob"]))

    if cfg["use_stoch"]:
        votes.append(("STOCH",
                      float(p.stoch_k) <= float(p.stoch_d) and float(c.stoch_k) > float(c.stoch_d),
                      float(p.stoch_k) >= float(p.stoch_d) and float(c.stoch_k) < float(c.stoch_d)))

    if cfg["use_vwap"]:
        votes.append(("VWAP", close > float(c.vwap), close < float(c.vwap)))

    if cfg["use_vwap_delta"]:
        votes.append(("VWAP_DELTA",
                      float(c.vwap_delta) > float(c.vwap_delta_baseline),
                      float(c.vwap_delta) < float(c.vwap_delta_baseline)))

    if cfg["use_vidya"]:
        votes.append(("VIDYA", bool(c.vidya_trend_up), not bool(c.vidya_trend_up)))

    if cfg["use_nwe"]:
        votes.append(("NWE",
                      float(c.nwe_out) > float(p.nwe_out),
                      float(c.nwe_out) < float(p.nwe_out)))

    if cfg["use_liq_swings"]:
        votes.append(("LIQ_SWING", bool(c.liq_swing_high_break), bool(c.liq_swing_low_break)))

    if cfg["use_trendline"]:
        votes.append(("TRENDLINE", bool(c.trendline_break_up), bool(c.trendline_break_down)))

    if cfg["use_mtf"]:
        votes.append(("MTF", bool(c.mtf_bull), bool(c.mtf_bear)))

    if cfg["use_divergence"]:
        votes.append(("DIVERGENCE",
                      bool(c.div_bull_signal) and int(c.div_bull_count) >= cfg["div_min_count"],
                      bool(c.div_bear_signal) and int(c.div_bear_count) >= cfg["div_min_count"]))

    vol_pass = float(c.vol) > float(c.vol_ma)
    adx_pass = float(c.adx) >= cfg["adx_thresh"]
    atr_pass = float(c.atr) / close * 100.0 >= cfg["atr_min_pct"] if close > 0 else False

    if cfg["use_vol"] and vol_pass:
        votes.append(("VOL", close > float(c.open), close < float(c.open)))
    if cfg["use_adx"] and adx_pass:
        votes.append(("ADX", float(c.plus_di) > float(c.minus_di), float(c.minus_di) > float(c.plus_di)))
    if cfg["use_atr"] and atr_pass:
        votes.append(("ATR", close > float(c.open), close < float(c.open)))

    return votes, atr_pass, vol_pass, adx_pass


def ai_management(votes, side, atr, entry, cfg):
    r = LIVE.StrategyEngine.ai_agent_decision(
        votes, atr_pass=True, vol_pass=True, adx_pass=True,
        mtf_pass_bull=True, mtf_pass_bear=True,
        min_families=cfg["ai_min_families"], min_edge=cfg["ai_min_edge"],
        min_family_confidence=cfg["ai_family_confidence"],
        require_trend=cfg["ai_require_trend"],
        require_structure=cfg["ai_require_structure"],
        max_conflicting_families=cfg["ai_max_conflicts"],
    )
    fams = list(r["bull_families"] if side == "LONG" else r["bear_families"])
    conf = float(np.mean([r["families"][f]["confidence"] for f in fams])) if fams else 0.0
    edge = float(r["edge"])
    conflicts = len(r["conflicting_families"])

    edge_s = np.clip((edge - cfg["ai_min_edge"]) / max(0.01, 1.0 - cfg["ai_min_edge"]), 0, 1)
    fam_s = np.clip((len(fams) - cfg["ai_min_families"]) / max(1.0, 4.0 - cfg["ai_min_families"]), 0, 1)
    conf_s = np.clip((conf - cfg["ai_family_confidence"]) / max(0.01, 1.0 - cfg["ai_family_confidence"]), 0, 1)
    conflict_pen = np.clip(conflicts / max(1.0, float(cfg["ai_max_conflicts"]) + 1.0), 0, 1)
    conviction = float(np.clip(
        (0.45 * edge_s + 0.30 * fam_s + 0.25 * conf_s) * (1.0 - 0.25 * conflict_pen), 0, 1
    ))

    atr_pct = abs(atr / entry) * 100.0
    if atr_pct >= AI_HIGH_VOL_ATR_PCT:
        vol_factor, sl_floor = 0.75, 2.10
    elif atr_pct <= AI_LOW_VOL_ATR_PCT:
        vol_factor, sl_floor = 1.05, 1.55
    else:
        ratio = (atr_pct - AI_LOW_VOL_ATR_PCT) / max(AI_HIGH_VOL_ATR_PCT - AI_LOW_VOL_ATR_PCT, 0.01)
        vol_factor = 1.05 - 0.30 * ratio
        sl_floor = 1.55 + 0.55 * ratio

    risk = float(np.clip(
        cfg["risk_pct"] * (0.75 + 0.50 * conviction) * vol_factor,
        AI_MIN_RISK_PCT, AI_MAX_RISK_PCT
    ))
    sl_mult = float(np.clip(sl_floor + (2.05 - sl_floor) * conviction, AI_MIN_ATR_SL, AI_MAX_ATR_SL))
    tp1_r = float(np.clip(max(cfg["atr_tp1_mult"], AI_MIN_TP1_R + 0.50 * conviction), AI_MIN_TP1_R, AI_MAX_TP1_R))
    tp2_r = float(np.clip(max(cfg["atr_tp2_mult"], AI_MIN_TP2_R + conviction), AI_MIN_TP2_R, AI_MAX_TP2_R))
    if tp2_r <= tp1_r:
        tp2_r = min(AI_MAX_TP2_R, tp1_r + 0.50)

    return {
        "risk_pct": risk, "sl_mult": sl_mult, "tp1_r": tp1_r, "tp2_r": tp2_r,
        "atr_pct": atr_pct, "edge": edge, "confidence": conf,
        "conviction": conviction, "families": fams
    }


def fee(notional):
    return abs(notional) * FEE_PCT / 100.0


def adverse_entry(price, side):
    slip = SLIPPAGE_PCT / 100.0
    return price * (1.0 + slip) if side == "LONG" else price * (1.0 - slip)


def adverse_exit(price, side):
    slip = SLIPPAGE_PCT / 100.0
    return price * (1.0 - slip) if side == "LONG" else price * (1.0 + slip)


def run(df, cfg, initial_capital):
    equity = float(initial_capital)
    peak = equity
    trades = []
    curve = []
    last_flat_i = -10**9

    for i in range(max(WARMUP, 3), len(df) - 1):
        row = df.iloc[i]
        curve.append({"datetime": str(row.datetime), "equity": equity, "peak": peak})

        if i - last_flat_i < max(1, math.ceil(COOLDOWN_MIN / 15.0)):
            continue

        votes, atr_pass, vol_pass, adx_pass = module_votes(df, i, cfg)
        mtf_bull, mtf_bear = bool(row.mtf_bull), bool(row.mtf_bear)

        bull, bear, _, _ = LIVE.StrategyEngine.decide_signal(
            votes, "AI_AGENT", 1,
            atr_pass=atr_pass, vol_pass=vol_pass, adx_pass=adx_pass,
            mtf_pass_bull=mtf_bull, mtf_pass_bear=mtf_bear,
            ai_min_families=cfg["ai_min_families"],
            ai_min_edge=cfg["ai_min_edge"],
            ai_min_family_confidence=cfg["ai_family_confidence"],
            ai_require_trend=cfg["ai_require_trend"],
            ai_require_structure=cfg["ai_require_structure"],
            ai_max_conflicting_families=cfg["ai_max_conflicts"],
        )
        side = "LONG" if bull and not bear else "SHORT" if bear and not bull else None
        if side is None:
            continue

        next_row = df.iloc[i + 1]
        entry = adverse_entry(float(next_row.open), side)
        atr = float(row.atr)
        if not np.isfinite(atr) or atr <= 0:
            continue

        ai = ai_management(votes, side, atr, entry, cfg)
        sl_distance = atr * ai["sl_mult"]
        risk_amount = equity * ai["risk_pct"] / 100.0
        qty = risk_amount / max(sl_distance, 1e-12)

        if side == "LONG":
            sl = entry - sl_distance
            tp1 = entry + sl_distance * ai["tp1_r"]
            tp2 = entry + sl_distance * ai["tp2_r"]
        else:
            sl = entry + sl_distance
            tp1 = entry - sl_distance * ai["tp1_r"]
            tp2 = entry - sl_distance * ai["tp2_r"]

        q1 = qty * TP1_PCT / 100.0
        q2 = qty - q1
        if q1 <= 0 or q2 <= 0:
            continue

        t = Trade(
            side=side,
            signal_time=str(row.datetime),
            entry_time=str(next_row.datetime),
            entry=entry, qty=qty, tp1_qty=q1, tp2_qty=q2,
            sl=sl, tp1=tp1, tp2=tp2,
            ai_risk_pct=ai["risk_pct"], ai_sl_atr=ai["sl_mult"],
            ai_tp1_r=ai["tp1_r"], ai_tp2_r=ai["tp2_r"],
            ai_edge=ai["edge"], ai_confidence=ai["confidence"],
            ai_conviction=ai["conviction"],
            ai_families=",".join(ai["families"]),
            reason="AI_AGENT_ACCEPTED",
        )

        remaining = qty
        tp1_done = False
        be = False
        exit_i = None

        for j in range(i + 1, len(df)):
            bar = df.iloc[j]
            hi, lo = float(bar.high), float(bar.low)

            sl_hit = lo <= t.sl if side == "LONG" else hi >= t.sl
            if sl_hit:
                px = adverse_exit(t.sl, side)
                gross = (px - entry) * remaining if side == "LONG" else (entry - px) * remaining
                costs = fee(entry * remaining) + fee(px * remaining)
                t.realized_net += gross - costs
                t.fees += costs
                t.exit_price = px
                t.exit_time = str(bar.datetime)
                t.exit_reason = "SL_BE" if be else "SL"
                equity += gross - costs
                exit_i = j
                break

            if not tp1_done:
                tp1_hit = hi >= t.tp1 if side == "LONG" else lo <= t.tp1
                if tp1_hit:
                    px = adverse_exit(t.tp1, side)
                    gross = (px - entry) * q1 if side == "LONG" else (entry - px) * q1
                    costs = fee(entry * q1) + fee(px * q1)
                    t.realized_net += gross - costs
                    t.fees += costs
                    equity += gross - costs
                    remaining -= q1
                    tp1_done = True
                    be = True
                    t.sl = entry

            if remaining > 0 and be:
                be_hit = lo <= entry if side == "LONG" else hi >= entry
                if be_hit:
                    px = adverse_exit(entry, side)
                    gross = (px - entry) * remaining if side == "LONG" else (entry - px) * remaining
                    costs = fee(entry * remaining) + fee(px * remaining)
                    t.realized_net += gross - costs
                    t.fees += costs
                    t.exit_price = px
                    t.exit_time = str(bar.datetime)
                    t.exit_reason = "TP1_BE"
                    equity += gross - costs
                    exit_i = j
                    break

            if remaining > 0:
                tp2_hit = hi >= t.tp2 if side == "LONG" else lo <= t.tp2
                if tp2_hit:
                    px = adverse_exit(t.tp2, side)
                    gross = (px - entry) * remaining if side == "LONG" else (entry - px) * remaining
                    costs = fee(entry * remaining) + fee(px * remaining)
                    t.realized_net += gross - costs
                    t.fees += costs
                    t.exit_price = px
                    t.exit_time = str(bar.datetime)
                    t.exit_reason = "TP2"
                    equity += gross - costs
                    exit_i = j
                    break

        if exit_i is None:
            last = df.iloc[-1]
            px = adverse_exit(float(last.close), side)
            gross = (px - entry) * remaining if side == "LONG" else (entry - px) * remaining
            costs = fee(entry * remaining) + fee(px * remaining)
            t.realized_net += gross - costs
            t.fees += costs
            t.exit_price = px
            t.exit_time = str(last.datetime)
            t.exit_reason = "END"

        trades.append(asdict(t))
        last_flat_i = exit_i if exit_i is not None else len(df) - 1
        peak = max(peak, equity)

    curve.append({"datetime": str(df.iloc[-1].datetime), "equity": equity, "peak": peak})
    return trades, pd.DataFrame(curve), equity


def metrics(trades, equity_curve, initial):
    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
            "net_pnl": 0.0, "return_pct": 0.0, "max_drawdown_pct": 0.0,
            "profit_factor": 0.0,
        }

    d = pd.DataFrame(trades)
    wins = int((d["realized_net"] > 0).sum())
    losses = int((d["realized_net"] <= 0).sum())
    gross_win = float(d.loc[d["realized_net"] > 0, "realized_net"].sum())
    gross_loss = float(-d.loc[d["realized_net"] <= 0, "realized_net"].sum())

    eq = equity_curve["equity"].astype(float)
    running_peak = eq.cummax()
    dd = (eq - running_peak) / running_peak.replace(0, np.nan) * 100.0
    net = float(d["realized_net"].sum())

    return {
        "trades": len(d),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": wins / len(d) * 100.0,
        "net_pnl": net,
        "return_pct": net / initial * 100.0,
        "max_drawdown_pct": float(abs(dd.min())) if not dd.empty else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else float("inf"),
        "avg_trade_pnl": net / len(d),
    }


def main():
    parser = argparse.ArgumentParser(description="Crypto AI-Agent R6.6 Backtester")
    parser.add_argument("--exchange", default="bybit", choices=("bybit", "binance"))
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-09-01")
    parser.add_argument("--capital", type=float, default=CAPITAL)
    args = parser.parse_args()

    cfg = make_cfg()
    _, raw = fetch_ohlcv(args.exchange, args.symbol, args.timeframe, args.start, args.end)
    print(f"{APP_VERSION}")
    print(f"Exchange={args.exchange} Symbol={args.symbol} TF={args.timeframe}")
    print(f"Period={args.start} -> {args.end} Capital={args.capital}")
    print(f"Downloaded {len(raw):,} candles.")

    df = build_frame(raw, cfg)
    trades, curve, ending = run(df, cfg, args.capital)
    m = metrics(trades, curve, args.capital)

    stem = f"{args.symbol.replace('/','_').replace(':','_')}_{args.timeframe}_{args.start}_{args.end}"
    pd.DataFrame(trades).to_csv(RESULTS_DIR / f"trades_{stem}.csv", index=False)
    curve.to_csv(RESULTS_DIR / f"equity_{stem}.csv", index=False)
    (RESULTS_DIR / f"summary_{stem}.json").write_text(
        json.dumps({
            "version": APP_VERSION,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "config": cfg,
            "metrics": m,
            "ending_equity": ending,
        }, indent=2),
        encoding="utf-8",
    )

    print("\n===== RESULT =====")
    for k, v in m.items():
        print(f"{k}: {v}")
    print(f"ending_equity: {ending:.6f}")


if __name__ == "__main__":
    main()
