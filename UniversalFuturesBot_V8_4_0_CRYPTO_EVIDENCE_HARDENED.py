import json
import os
import threading
import time
import sqlite3
import uuid
import hashlib
import re
from datetime import datetime, timezone
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import ccxt
import numpy as np
import pandas as pd
import requests
import sys
import shutil
from pathlib import Path


# ============================================================
# UNIVERSAL FUTURES BOT - WINDOWS GUI
# Multi-Exchange Futures: Bybit + Binance + Gate.io + Bitget + WEEX
#
# IMPORTANT SL/TP FIXES:
# 1. Entry price is taken from the ACTUAL FILLED POSITION,
#    not from the previous candle close.
# 2. SL/TP are calculated from the actual average entry price.
# 3. Actual position quantity is fetched after entry.
# 4. Exchange-specific trigger parameters are used.
# 5. Every SL/TP order is checked after creation.
# 6. If protection cannot be installed, the bot attempts to
#    close the new position instead of leaving it unprotected.
# 7. Old open orders are cancelled before a new/reversed entry.
# 8. TP1 + TP2 quantities equal the actual position quantity.
#
# SL/TP supports TWO modes:
# 1. PRICE % = percentage movement of market price from actual entry.
# 2. ROI %   = target position ROI, converted to a price trigger using leverage.
# Example at 20x: TP1 ROI 20% -> approximately 1% price movement.
# ROI-mode trigger prices are still submitted as exchange price-based
# conditional orders; the bot converts the requested ROI target to price.
# ============================================================


APP_VERSION = "V8.4.1-CRYPTO-EVIDENCE-HARDENED-AUDITED"
APP_TITLE = "Universal Futures Trading Bot V8.4.1 - Hardened Adaptive Evidence Engine"
AUDIT_BUILD = "V8.4.1-ENGINE-AUDIT-2026-09-21"

# V8.3.3 full engine/strategy/configuration audit and orphan-order recovery hardening.
# Keep the config and trade log beside the executable when packaged with PyInstaller.
# When running the .py directly, keep them beside the script.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_FILE = str(APP_DIR / "config_universal_fixed.json")
LOG_FILE = str(APP_DIR / "universal_trade_logs_fixed.csv")
PROFILE_DIR = APP_DIR / "bot_profiles"
MASTER_DB_FILE = str(APP_DIR / "universal_bot_master.db")
MASTER_CSV_FILE = str(APP_DIR / "universal_bot_master_log.csv")

# V8.2 configuration/runtime contracts.
CONFIG_SCHEMA_VERSION = 7
RUNTIME_SCHEMA_VERSION = 5  # V8.3.3 runtime adds persistent retired managed-order IDs.
OPEN_ORDER_PAGE_LIMIT = 50
SUPPORTED_GRID_MODES = ("OFF", "DIRECT_SHOT", "LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID")
SUPPORTED_SIGNAL_MODES = ("SINGLE_SIGNAL", "ANY_NON_CONFLICTING", "SCORE", "2_SIGNALS", "3_SIGNALS", "4_SIGNALS", "ADAPTIVE_SCORE", "ADAPTIVE_EVIDENCE", "STRICT_ALL_FILTERS")
SUPPORTED_EXCHANGES = ("bybit", "binance", "gate", "bitget", "weex")

# V8.3 hardened strategy/risk contract. Adaptive voting deliberately gives
# less influence to highly correlated indicators and treats VOL/ATR as
# regime gates instead of pretending a candle direction is an independent
# directional signal. This is a quality filter, not a profit guarantee.
ADAPTIVE_MODULE_WEIGHTS = {
    "ST": 1.50, "EMA": 1.00, "EMA_CROSS": 1.25, "MACD": 1.25,
    "RSI": 1.00, "BB": 0.75, "STOCH": 0.75, "VWAP": 1.25,
    "VWAP_DELTA": 1.00, "VIDYA": 1.25, "NWE": 1.00,
    "LIQ_SWING": 1.50, "TRENDLINE": 1.50, "MTF": 2.00,
    "DIVERGENCE": 1.75, "VOL_SR": 1.50, "VOL": 0.50, "ADX": 1.25, "ATR": 0.50,
}
ADAPTIVE_DEFAULT_EDGE = 0.18
ADAPTIVE_DEFAULT_MIN_WEIGHT = 3.50
EVIDENCE_DEFAULT_MIN_FAMILIES = 2
EVIDENCE_DEFAULT_FAMILY_MIN_SCORE = 0.35
EVIDENCE_DEFAULT_REQUIRE_TREND = True
EVIDENCE_DEFAULT_REQUIRE_INDEPENDENT = True
DEFAULT_SIGNAL_MODE = "ADAPTIVE_EVIDENCE"
DEFAULT_ADAPTIVE_EDGE = "0.18"
DEFAULT_ADAPTIVE_MIN_WEIGHT = "3.5"
DEFAULT_USE_MTF = True
DEFAULT_USE_ADX = True
DEFAULT_USE_VOLUME = True
DEFAULT_USE_ATR = False
DEFAULT_GRID_MODE = "OFF"
DEFAULT_RISK_MODE = "EQUITY_RISK_%"
DEFAULT_RISK_PER_TRADE = "1.0"
DEFAULT_POST_SL_OPPOSITE_LOCK = True
DEFAULT_NO_SAME_CANDLE = True
RISK_COST_BUFFER = 1.15
MAX_CONSECUTIVE_CYCLE_ERRORS = 3
MAX_DATA_STALENESS_MULTIPLIER = 2.5
PROFILE_OPERATION_SCHEMA_VERSION = 2  # V8.2.2 explicit current-vs-selected profile controls
# V8.3.0 advanced strategy defaults
DIVERGENCE_INDICATORS = (
    "MACD", "MACD_HIST", "RSI", "STOCH", "CCI",
    "MOMENTUM", "OBV", "VWMACD", "CMF", "MFI",
)

# V8.2.3: normalize GUI symbols before live checkpoint identity checks.


# ============================================================
# V8.3.0 ADVANCED STRATEGY MODULES
# ------------------------------------------------------------
# Divergence source: "Divergence for Many Indicators v4"
# © LonesomeTheBlue — Mozilla Public License 2.0.
# This port intentionally uses CONFIRMED/CAUSAL pivots for live
# and backtest execution. The original "Don't Wait for
# Confirmation" mode is not allowed for trading signals because
# it would introduce a future-data/look-ahead condition.
#
# Volume S/R source: "Volume-based Support & Resistance Zones V2"
# The chart-only line/label objects are not reproduced; their
# volume-confirmed fractal/S/R zone logic is converted into
# numerical strategy states suitable for execution/backtesting.
# ============================================================

DIVERGENCE_INDICATORS = (
    "MACD", "MACD_HIST", "RSI", "STOCH", "CCI",
    "MOMENTUM", "OBV", "VWMACD", "CMF", "MFI",
)

def _safe_div(a, b):
    b = float(b)
    return float(a) / b if np.isfinite(b) and abs(b) > 1e-15 else np.nan

def _calc_cci_series(df, length=10):
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    ma = tp.rolling(int(length)).mean()
    md = tp.rolling(int(length)).apply(
        lambda x: float(np.mean(np.abs(x - np.mean(x)))), raw=True
    )
    return (tp - ma) / (0.015 * md.replace(0, np.nan))

def _calc_obv_series(df):
    delta = df["close"].diff()
    direction = np.sign(delta).fillna(0.0)
    return (direction * df["vol"].astype(float)).cumsum()

def _calc_mfi_series(df, length=14):
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    raw = tp * df["vol"].astype(float)
    direction = np.sign(tp.diff()).fillna(0.0)
    pos = raw.where(direction > 0, 0.0).rolling(int(length)).sum()
    neg = raw.where(direction < 0, 0.0).rolling(int(length)).sum().abs()
    ratio = pos / neg.replace(0, np.nan)
    out = 100.0 - (100.0 / (1.0 + ratio))
    out[(neg == 0) & (pos > 0)] = 100.0
    out[(neg == 0) & (pos == 0)] = 50.0
    return out

def _prepare_divergence_sources(df, cfg):
    x = df.copy()
    if "macd" not in x:
        x = calculate_macd(x, 12, 26, 9)
    if "rsi" not in x:
        x = calculate_rsi(x, 14)
    if "stoch_k" not in x:
        x = calculate_stochastic(x, 14, 3, 3)
    x["div_macd"] = x["macd"]
    x["div_macd_hist"] = x["macd_hist"]
    x["div_rsi"] = x["rsi"]
    x["div_stoch"] = x["stoch_k"]
    x["div_cci"] = _calc_cci_series(x, int(cfg.get("div_cci_len", 10)))
    x["div_momentum"] = x["close"].diff(int(cfg.get("div_mom_len", 10)))
    x["div_obv"] = _calc_obv_series(x)
    vwm_fast = (
        (x["close"] * x["vol"]).rolling(int(cfg.get("div_vwmacd_fast", 12))).sum()
        / x["vol"].rolling(int(cfg.get("div_vwmacd_fast", 12))).sum().replace(0, np.nan)
    )
    vwm_slow = (
        (x["close"] * x["vol"]).rolling(int(cfg.get("div_vwmacd_slow", 26))).sum()
        / x["vol"].rolling(int(cfg.get("div_vwmacd_slow", 26))).sum().replace(0, np.nan)
    )
    x["div_vwmacd"] = vwm_fast - vwm_slow
    hl_range = (x["high"] - x["low"]).replace(0, np.nan)
    cmfm = ((x["close"] - x["low"]) - (x["high"] - x["close"])) / hl_range
    cmfv = cmfm * x["vol"]
    x["div_cmf"] = (
        cmfv.rolling(int(cfg.get("div_cmf_len", 21))).sum()
        / x["vol"].rolling(int(cfg.get("div_cmf_len", 21))).sum().replace(0, np.nan)
    )
    x["div_mfi"] = _calc_mfi_series(x, int(cfg.get("div_mfi_len", 14)))
    return x

def _pivot_high_at(series, p, prd):
    if p - prd < 0 or p + prd >= len(series):
        return False
    v = float(series.iloc[p])
    window = pd.to_numeric(series.iloc[p-prd:p+prd+1], errors="coerce")
    if not np.isfinite(v) or window.isna().any():
        return False
    return v >= float(window.max()) and v > float(series.iloc[p-1]) if prd == 1 else (
        v >= float(window.max())
        and all(v > float(series.iloc[j]) for j in range(p-prd, p))
        and all(v >= float(series.iloc[j]) for j in range(p+1, p+prd+1))
    )

def _pivot_low_at(series, p, prd):
    if p - prd < 0 or p + prd >= len(series):
        return False
    v = float(series.iloc[p])
    window = pd.to_numeric(series.iloc[p-prd:p+prd+1], errors="coerce")
    if not np.isfinite(v) or window.isna().any():
        return False
    return v <= float(window.min()) and v < float(series.iloc[p-1]) if prd == 1 else (
        v <= float(window.min())
        and all(v < float(series.iloc[j]) for j in range(p-prd, p))
        and all(v <= float(series.iloc[j]) for j in range(p+1, p+prd+1))
    )

def _divergence_line_clear(values, current_idx, pivot_idx, bullish=True):
    if pivot_idx >= current_idx - 1:
        return False
    a = float(values.iloc[pivot_idx])
    b = float(values.iloc[current_idx])
    if not np.isfinite(a) or not np.isfinite(b):
        return False
    span = current_idx - pivot_idx
    slope = (b - a) / span
    for j in range(pivot_idx + 1, current_idx):
        v = float(values.iloc[j])
        expected = a + slope * (j - pivot_idx)
        if not np.isfinite(v):
            return False
        # Mirror the source's "virtual line" blocking test:
        # bullish divergences cannot cut below the interpolated line;
        # bearish divergences cannot cut above it.
        if bullish and v < expected:
            return False
        if not bullish and v > expected:
            return False
    return True

def _divergence_scan(values, price_low, price_high, pivot_lows, pivot_highs,
                     i, prd, maxpp, maxbars, search_type):
    """Return (pos_regular, neg_regular, pos_hidden, neg_hidden) lengths."""
    out = [0, 0, 0, 0]
    if i < 2 or not pivot_lows and not pivot_highs:
        return tuple(out)

    start = i - 1  # original script's confirmed mode uses [1]
    if start <= 0:
        return tuple(out)

    lows = list(reversed(pivot_lows))[-int(maxpp):]
    highs = list(reversed(pivot_highs))[-int(maxpp):]

    if search_type in ("Regular", "Regular/Hidden"):
        for p in reversed(pivot_lows[-int(maxpp):]):
            if start - p > int(maxbars) or start - p <= 5:
                continue
            sv = float(values.iloc[start]); pv = float(values.iloc[p])
            sl = float(price_low.iloc[start]); pl = float(price_low.iloc[p])
            if np.isfinite(sv) and np.isfinite(pv) and sl < pl and sv > pv:
                if _divergence_line_clear(values, start, p, True) and _divergence_line_clear(price_low, start, p, True):
                    out[0] = start - p
                    break
        for p in reversed(pivot_highs[-int(maxpp):]):
            if start - p > int(maxbars) or start - p <= 5:
                continue
            sv = float(values.iloc[start]); pv = float(values.iloc[p])
            sh = float(price_high.iloc[start]); ph = float(price_high.iloc[p])
            if np.isfinite(sv) and np.isfinite(pv) and sh > ph and sv < pv:
                if _divergence_line_clear(values, start, p, False) and _divergence_line_clear(price_high, start, p, False):
                    out[1] = start - p
                    break

    if search_type in ("Hidden", "Regular/Hidden"):
        for p in reversed(pivot_lows[-int(maxpp):]):
            if start - p > int(maxbars) or start - p <= 5:
                continue
            sv = float(values.iloc[start]); pv = float(values.iloc[p])
            sl = float(price_low.iloc[start]); pl = float(price_low.iloc[p])
            if np.isfinite(sv) and np.isfinite(pv) and sl > pl and sv < pv:
                if _divergence_line_clear(values, start, p, True) and _divergence_line_clear(price_low, start, p, True):
                    out[2] = start - p
                    break
        for p in reversed(pivot_highs[-int(maxpp):]):
            if start - p > int(maxbars) or start - p <= 5:
                continue
            sv = float(values.iloc[start]); pv = float(values.iloc[p])
            sh = float(price_high.iloc[start]); ph = float(price_high.iloc[p])
            if np.isfinite(sv) and np.isfinite(pv) and sh < ph and sv > pv:
                if _divergence_line_clear(values, start, p, False) and _divergence_line_clear(price_high, start, p, False):
                    out[3] = start - p
                    break
    return tuple(out)

def calculate_divergence_module(df, cfg):
    """Causal port of Divergence for Many Indicators v4.

    Signals are only emitted after the pivot has been confirmed by `prd`
    bars. No current/future pivot is used. The original chart-only labels,
    colors, lines and alerts are intentionally represented as numeric state
    columns for strategy/backtest use.
    """
    x = _prepare_divergence_sources(df, cfg)
    n = len(x)
    prd = int(cfg.get("div_pivot", 5))
    maxpp = int(cfg.get("div_max_pivots", 10))
    maxbars = int(cfg.get("div_max_bars", 100))
    search_type = str(cfg.get("div_type", "Regular"))
    source_mode = str(cfg.get("div_source", "Close")).strip().upper()
    selected = {
        k for k in DIVERGENCE_INDICATORS
        if bool(cfg.get("div_use_" + k.lower(), True))
    }
    if prd < 1 or maxpp < 1 or maxbars < 30:
        raise ValueError("Divergence pivot/max-pivot/max-bars settings are invalid.")

    ph_src = x["close"] if source_mode == "CLOSE" else x["high"]
    pl_src = x["close"] if source_mode == "CLOSE" else x["low"]

    pivot_lows = []
    pivot_highs = []
    pos_reg = np.zeros(n, dtype=int)
    neg_reg = np.zeros(n, dtype=int)
    pos_hid = np.zeros(n, dtype=int)
    neg_hid = np.zeros(n, dtype=int)
    bull_count = np.zeros(n, dtype=int)
    bear_count = np.zeros(n, dtype=int)

    source_cols = {
        "MACD":"div_macd", "MACD_HIST":"div_macd_hist", "RSI":"div_rsi",
        "STOCH":"div_stoch", "CCI":"div_cci", "MOMENTUM":"div_momentum",
        "OBV":"div_obv", "VWMACD":"div_vwmacd", "CMF":"div_cmf", "MFI":"div_mfi",
    }

    for i in range(n):
        # A pivot at p=i-prd becomes known only now.
        p = i - prd
        if p >= prd:
            if _pivot_high_at(ph_src, p, prd):
                pivot_highs.append(p)
                if len(pivot_highs) > maxpp:
                    pivot_highs = pivot_highs[-maxpp:]
            if _pivot_low_at(pl_src, p, prd):
                pivot_lows.append(p)
                if len(pivot_lows) > maxpp:
                    pivot_lows = pivot_lows[-maxpp:]

        if i < prd + 7:
            continue

        for name in selected:
            a,b,c,d = _divergence_scan(
                x[source_cols[name]], pl_src, ph_src,
                pivot_lows, pivot_highs, i, prd, maxpp, maxbars, search_type
            )
            pos_reg[i] += int(a > 0); neg_reg[i] += int(b > 0)
            pos_hid[i] += int(c > 0); neg_hid[i] += int(d > 0)

    x["div_pos_regular"] = pos_reg
    x["div_neg_regular"] = neg_reg
    x["div_pos_hidden"] = pos_hid
    x["div_neg_hidden"] = neg_hid
    x["div_bull_count"] = pos_reg + pos_hid
    x["div_bear_count"] = neg_reg + neg_hid
    x["div_bull_signal"] = x["div_bull_count"] > 0
    x["div_bear_signal"] = x["div_bear_count"] > 0

    # Persistent state is last confirmed divergence direction.
    state = 0
    states = []
    for i in range(n):
        if x["div_bull_signal"].iloc[i] and not x["div_bear_signal"].iloc[i]:
            state = 1
        elif x["div_bear_signal"].iloc[i] and not x["div_bull_signal"].iloc[i]:
            state = -1
        elif x["div_bull_signal"].iloc[i] and x["div_bear_signal"].iloc[i]:
            state = 0
        states.append(state)
    x["divergence_state"] = states
    return x

def _resample_ohlcv(df, rule):
    y = df.copy()
    if "datetime" not in y.columns:
        y["datetime"] = pd.to_datetime(y["time"], unit="ms", utc=True)
    y["datetime"] = pd.to_datetime(y["datetime"], utc=True)
    y = y.set_index("datetime")
    z = y.resample(rule, label="left", closed="left").agg({
        "time":"first", "open":"first", "high":"max", "low":"min",
        "close":"last", "vol":"sum"
    })
    counts = y["close"].resample(rule, label="left", closed="left").count()
    try:
        expected = max(1, int(pd.Timedelta(rule) / pd.Timedelta(pd.infer_freq(y.index) or "1min")))
    except Exception:
        expected = 1
    z["base_count"] = counts
    z = z.dropna(subset=["open","high","low","close","vol"])
    if len(z) > 1:
        # Only retain complete historical buckets. The final bucket is never
        # used by the signal engine, so it can remain as the current bucket.
        z = pd.concat([z.iloc[:-1][z.iloc[:-1]["base_count"] >= expected], z.iloc[-1:]], axis=0)
    return z.reset_index(drop=False)

def _volume_sr_single_tf(frame, vol_threshold=6):
    """Numeric equivalent of the Volume-based S/R Zones V2 fractal logic."""
    x = frame.copy().reset_index(drop=True)
    if len(x) < 10:
        return {"support_low":np.nan,"support_zone":np.nan,"resistance_zone":np.nan,
                "resistance_high":np.nan,"bull":False,"bear":False,
                "fresh_bull":False,"fresh_bear":False}
    vma = x["vol"].rolling(int(vol_threshold)).mean()
    res_hi = np.nan; res_zone = np.nan; sup_lo = np.nan; sup_zone = np.nan
    prev_res_hi = prev_res_zone = prev_sup_lo = prev_sup_zone = np.nan
    fresh_up = fresh_dn = False
    # Process all completed HTF bars; latest bar is treated as unavailable
    # when it is an in-progress bucket.
    # Work only through the latest completed source candle. The final row
    # may be an in-progress candle in live execution.
    last_i = max(5, len(x) - 2)
    for i in range(5, last_i + 1):
        prev_res_hi, prev_res_zone = res_hi, res_zone
        prev_sup_lo, prev_sup_zone = sup_lo, sup_zone
        p = i - 3
        up = (
            float(x.high.iloc[p]) > float(x.high.iloc[p-1]) >
            float(x.high.iloc[p-2])
            and float(x.high.iloc[p+1]) < float(x.high.iloc[p]) >
            float(x.high.iloc[p+2])
            and float(x.vol.iloc[p]) > float(vma.iloc[p])
        )
        dn = (
            float(x.low.iloc[p]) < float(x.low.iloc[p-1]) <
            float(x.low.iloc[p-2])
            and float(x.low.iloc[p+1]) > float(x.low.iloc[p]) <
            float(x.low.iloc[p+2])
            and float(x.vol.iloc[p]) > float(vma.iloc[p])
        )
        if up:
            res_hi = float(x.high.iloc[p])
            res_zone = float(x.close.iloc[p]) if float(x.close.iloc[p]) >= float(x.open.iloc[p]) else float(x.open.iloc[p])
        if dn:
            sup_lo = float(x.low.iloc[p])
            sup_zone = float(x.open.iloc[p]) if float(x.close.iloc[p]) >= float(x.open.iloc[p]) else float(x.close.iloc[p])
    c = float(x.close.iloc[-2]) if len(x) > 1 else float(x.close.iloc[-1])
    pc = float(x.close.iloc[-3]) if len(x) > 2 else c
    # Fresh break uses the confirmed previous zone, preventing a newly-created
    # level from being mistaken for a breakout on the same confirmation bar.
    fresh_up = np.isfinite(prev_res_hi) and pc <= prev_res_hi and c > prev_res_hi
    fresh_dn = np.isfinite(prev_sup_lo) and pc >= prev_sup_lo and c < prev_sup_lo
    bull = bool(fresh_up or (np.isfinite(sup_zone) and c >= sup_zone) or (np.isfinite(res_hi) and c > res_hi))
    bear = bool(fresh_dn or (np.isfinite(res_zone) and c <= res_zone) or (np.isfinite(sup_lo) and c < sup_lo))
    return {"support_low":sup_lo, "support_zone":sup_zone,
            "resistance_zone":res_zone, "resistance_high":res_hi,
            "bull":bull and not bear, "bear":bear and not bull,
            "fresh_bull":bool(fresh_up), "fresh_bear":bool(fresh_dn)}

def calculate_volume_sr_module(frames, cfg):
    """Aggregate the source's four S/R timeframes into one directional module."""
    states=[]
    for tf_name, frame, enabled in frames:
        if not enabled or frame is None or len(frame)<10:
            continue
        st=_volume_sr_single_tf(frame, int(cfg.get("sr_volume_ma",6)))
        st["tf"]=tf_name
        states.append(st)
    if not states:
        return {"bull":False,"bear":False,"fresh_bull":False,"fresh_bear":False,"states":[]}
    mode=str(cfg.get("sr_vote_mode","MAJORITY")).upper()
    bulls=sum(bool(s["bull"]) for s in states); bears=sum(bool(s["bear"]) for s in states)
    fresh_bulls=sum(bool(s["fresh_bull"]) for s in states); fresh_bears=sum(bool(s["fresh_bear"]) for s in states)
    if mode=="ALL":
        bull = bulls == len(states) and bears == 0
        bear = bears == len(states) and bulls == 0
    elif mode=="ANY":
        bull = bulls > 0 and bears == 0
        bear = bears > 0 and bulls == 0
    else:
        bull = bulls > bears
        bear = bears > bulls
    if str(cfg.get("sr_entry_mode","CURRENT_ZONE")).upper()=="FRESH_BREAK":
        bull = fresh_bulls > fresh_bears and fresh_bulls > 0
        bear = fresh_bears > fresh_bulls and fresh_bears > 0
    return {"bull":bool(bull),"bear":bool(bear),
            "fresh_bull":bool(fresh_bulls>fresh_bears and fresh_bulls>0),
            "fresh_bear":bool(fresh_bears>fresh_bulls and fresh_bears>0),
            "states":states}

def _volume_sr_series(frame, vol_threshold=6):
    x = frame.copy().reset_index(drop=True)
    n=len(x)
    bull=np.zeros(n,dtype=bool); bear=np.zeros(n,dtype=bool)
    fresh_bull=np.zeros(n,dtype=bool); fresh_bear=np.zeros(n,dtype=bool)
    res_hi=res_zone=sup_lo=sup_zone=np.nan
    vma=x["vol"].rolling(int(vol_threshold)).mean()
    for i in range(n):
        if i>=5:
            p=i-3
            up=(float(x.high.iloc[p])>float(x.high.iloc[p-1])>float(x.high.iloc[p-2])
                and float(x.high.iloc[p+1])<float(x.high.iloc[p])>float(x.high.iloc[p+2])
                and float(x.vol.iloc[p])>float(vma.iloc[p]))
            dn=(float(x.low.iloc[p])<float(x.low.iloc[p-1])<float(x.low.iloc[p-2])
                and float(x.low.iloc[p+1])>float(x.low.iloc[p])<float(x.low.iloc[p+2])
                and float(x.vol.iloc[p])>float(vma.iloc[p]))
            old_res_hi, old_sup_lo = res_hi, sup_lo
            if up:
                res_hi=float(x.high.iloc[p])
                res_zone=float(x.close.iloc[p]) if float(x.close.iloc[p])>=float(x.open.iloc[p]) else float(x.open.iloc[p])
            if dn:
                sup_lo=float(x.low.iloc[p])
                sup_zone=float(x.open.iloc[p]) if float(x.close.iloc[p])>=float(x.open.iloc[p]) else float(x.close.iloc[p])
            c=float(x.close.iloc[i]); pc=float(x.close.iloc[i-1])
            fresh_bull[i]=bool(np.isfinite(old_res_hi) and pc<=old_res_hi and c>old_res_hi)
            fresh_bear[i]=bool(np.isfinite(old_sup_lo) and pc>=old_sup_lo and c<old_sup_lo)
            b=bool(fresh_bull[i] or (np.isfinite(sup_zone) and c>=sup_zone) or (np.isfinite(res_hi) and c>res_hi))
            s=bool(fresh_bear[i] or (np.isfinite(res_zone) and c<=res_zone) or (np.isfinite(sup_lo) and c<sup_lo))
            bull[i]=b and not s; bear[i]=s and not b
    out=x.copy()
    out["sr_bull"]=bull; out["sr_bear"]=bear
    out["sr_fresh_bull"]=fresh_bull; out["sr_fresh_bear"]=fresh_bear
    return out

def _volume_sr_base_series(df, cfg):
    """Build causal four-timeframe S/R votes aligned to base candles."""
    base=df.copy()
    if "datetime" not in base.columns:
        base["datetime"]=pd.to_datetime(base["time"],unit="ms",utc=True)
    base["datetime"]=pd.to_datetime(base["datetime"],utc=True)
    tf_map={"Chart":None,"1m":"1min","3m":"3min","5m":"5min","15m":"15min",
            "30m":"30min","45m":"45min","1h":"1h","2h":"2h","3h":"3h",
            "4h":"4h","6h":"6h","8h":"8h","12h":"12h","D":"1D","3D":"3D",
            "W":"1W","2W":"2W","1M":"1MS","12M":"12MS","Disable":None}
    tf_names=[cfg.get("sr_tf1","Chart"),cfg.get("sr_tf2","4h"),cfg.get("sr_tf3","D"),cfg.get("sr_tf4","W")]
    aligned=[]
    for slot,tf in enumerate(tf_names,1):
        if tf=="Disable":
            continue
        if tf=="Chart":
            f=base.copy()
        else:
            rule=tf_map.get(tf)
            if not rule:
                continue
            f=_resample_ohlcv(base,rule)
        if len(f)<10:
            continue
        fs=_volume_sr_series(f,int(cfg.get("sr_volume_ma",6)))
        if "datetime" not in fs:
            fs["datetime"]=pd.to_datetime(fs["time"],unit="ms",utc=True)
        fs=fs[["datetime","sr_bull","sr_bear","sr_fresh_bull","sr_fresh_bear"]].copy()
        fs=fs.sort_values("datetime")
        fs["datetime"]=pd.to_datetime(fs["datetime"],utc=True)
        if tf!="Chart":
            try:
                fs["datetime"] = fs["datetime"] + pd.Timedelta(rule)
            except Exception:
                pass
        if tf=="Chart":
            a=fs
        else:
            a=pd.merge_asof(base[["datetime"]].sort_values("datetime"),fs,on="datetime",direction="backward")
        a=a.rename(columns={k:f"{k}_{slot}" for k in ["sr_bull","sr_bear","sr_fresh_bull","sr_fresh_bear"]})
        aligned.append(a.set_index("datetime"))
    if not aligned:
        base["sr_bull"]=False; base["sr_bear"]=False
        base["sr_fresh_bull"]=False; base["sr_fresh_bear"]=False
        return base
    idx=base.set_index("datetime").index
    z=pd.DataFrame(index=idx)
    for a in aligned:
        z=z.join(a,how="left")
    bcols=[c for c in z.columns if c.startswith("sr_bull_")]
    scols=[c for c in z.columns if c.startswith("sr_bear_")]
    fbcols=[c for c in z.columns if c.startswith("sr_fresh_bull_")]
    fscols=[c for c in z.columns if c.startswith("sr_fresh_bear_")]
    mode=str(cfg.get("sr_vote_mode","MAJORITY")).upper()
    bv=z[bcols].astype("boolean").fillna(False).sum(axis=1) if bcols else pd.Series(0,index=z.index)
    sv=z[scols].astype("boolean").fillna(False).sum(axis=1) if scols else pd.Series(0,index=z.index)
    fb=z[fbcols].astype("boolean").fillna(False).sum(axis=1) if fbcols else pd.Series(0,index=z.index)
    fs=z[fscols].astype("boolean").fillna(False).sum(axis=1) if fscols else pd.Series(0,index=z.index)
    n=max(len(bcols),len(scols),1)
    if mode=="ALL":
        bull=(bv==n)&(sv==0); bear=(sv==n)&(bv==0)
    elif mode=="ANY":
        bull=(bv>0)&(sv==0); bear=(sv>0)&(bv==0)
    else:
        bull=bv>sv; bear=sv>bv
    if str(cfg.get("sr_entry_mode","CURRENT_ZONE")).upper()=="FRESH_BREAK":
        bull=(fb>fs)&(fb>0); bear=(fs>fb)&(fs>0)
    base=base.set_index("datetime")
    base["sr_bull"]=bull.reindex(base.index,fill_value=False).astype(bool)
    base["sr_bear"]=bear.reindex(base.index,fill_value=False).astype(bool)
    base["sr_fresh_bull"]=(fb>fs)&(fb>0)
    base["sr_fresh_bear"]=(fs>fb)&(fs>0)
    return base.reset_index()


class StrategyEngine:
    """V8.3 hardened adaptive, pure strategy-decision engine.

    Indicator calculations remain in the existing functions; this class owns
    only the final directional vote contract. It is GUI/exchange independent.
    """

    # Adaptive thresholds are supplied explicitly to each decision call.
    # They must not be mutable class state because multiple bot profiles/workers
    # may run concurrently in the same Python process.
    EVIDENCE_FAMILIES = {
        "TREND": ("ST", "EMA", "EMA_CROSS", "MACD", "VIDYA", "NWE"),
        "MOMENTUM": ("RSI", "STOCH", "DIVERGENCE"),
        "FLOW": ("VWAP", "VWAP_DELTA", "VOL", "VOL_SR"),
        "STRUCTURE": ("LIQ_SWING", "TRENDLINE", "MTF"),
    }
    EVIDENCE_FAMILY_ORDER = ("TREND", "MOMENTUM", "FLOW", "STRUCTURE")
    EVIDENCE_DEFAULT_MIN_FAMILIES = 2
    EVIDENCE_DEFAULT_FAMILY_MIN_SCORE = 0.35

    @classmethod
    def _family_name(cls, module_name):
        name = str(module_name).upper()
        for family, members in cls.EVIDENCE_FAMILIES.items():
            if name in members:
                return family
        return "OPTIONAL"

    @classmethod
    def evidence_summary(cls, directional_modules, min_families=None, family_min_score=None):
        min_families = max(1, int(cls.EVIDENCE_DEFAULT_MIN_FAMILIES if min_families is None else min_families))
        family_min_score = float(cls.EVIDENCE_DEFAULT_FAMILY_MIN_SCORE if family_min_score is None else family_min_score)
        out = {}
        for family in cls.EVIDENCE_FAMILY_ORDER:
            members = [m for m in directional_modules if cls._family_name(m[0]) == family]
            total = sum(float(ADAPTIVE_MODULE_WEIGHTS.get(m[0], 1.0)) for m in members)
            bull = sum(float(ADAPTIVE_MODULE_WEIGHTS.get(m[0], 1.0)) for m in members if bool(m[1]) and not bool(m[2]))
            bear = sum(float(ADAPTIVE_MODULE_WEIGHTS.get(m[0], 1.0)) for m in members if bool(m[2]) and not bool(m[1]))
            out[family] = {"bull": bull, "bear": bear, "total": total, "bull_ratio": bull / total if total else 0.0, "bear_ratio": bear / total if total else 0.0, "active": bool(members)}
        bull_families = [f for f,v in out.items() if v["bull_ratio"] >= family_min_score and v["bull_ratio"] > v["bear_ratio"]]
        bear_families = [f for f,v in out.items() if v["bear_ratio"] >= family_min_score and v["bear_ratio"] > v["bull_ratio"]]
        return out, bull_families, bear_families, min_families

    @staticmethod
    def decide_signal(directional_modules, signal_mode, min_score,
                      atr_pass=True, vol_pass=True, adx_pass=True,
                      mtf_pass_bull=True, mtf_pass_bear=True,
                      adaptive_edge=None, adaptive_min_weight=None, evidence_min_families=None, evidence_family_min_score=None, evidence_require_trend=True, evidence_require_independent=True):
        signal_mode = str(signal_mode).strip().upper()
        min_score = int(min_score)
        if min_score < 1:
            raise ValueError("Minimum signal score must be at least 1.")
        modules = list(directional_modules or [])
        buy_score = sum(1 for _, bull, _ in modules if bool(bull))
        sell_score = sum(1 for _, _, bear in modules if bool(bear))
        count = len(modules)

        if signal_mode == "SINGLE_SIGNAL":
            for _, bull, bear in modules:
                if bool(bull) and not bool(bear):
                    return True, False, buy_score, sell_score
                if bool(bear) and not bool(bull):
                    return False, True, buy_score, sell_score
            return False, False, buy_score, sell_score

        if signal_mode == "ANY_NON_CONFLICTING":
            return (
                count > 0 and buy_score > 0 and sell_score == 0,
                count > 0 and sell_score > 0 and buy_score == 0,
                buy_score, sell_score,
            )

        if signal_mode in ("SCORE", "2_SIGNALS", "3_SIGNALS", "4_SIGNALS"):
            required = {"2_SIGNALS": 2, "3_SIGNALS": 3, "4_SIGNALS": 4}.get(signal_mode, min_score)
            return (
                count > 0 and buy_score >= required and buy_score > sell_score,
                count > 0 and sell_score >= required and sell_score > buy_score,
                buy_score, sell_score,
            )

        if signal_mode == "ADAPTIVE_SCORE":
            weights = ADAPTIVE_MODULE_WEIGHTS
            wb = sum(float(weights.get(name, 1.0)) for name, bull, bear in modules if bool(bull) and not bool(bear))
            ws = sum(float(weights.get(name, 1.0)) for name, bull, bear in modules if bool(bear) and not bool(bull))
            total = wb + ws
            edge = abs(wb - ws) / total if total > 0 else 0.0
            min_weight = max(float(min_score), float(ADAPTIVE_DEFAULT_MIN_WEIGHT if adaptive_min_weight is None else adaptive_min_weight))
            edge_threshold = float(ADAPTIVE_DEFAULT_EDGE if adaptive_edge is None else adaptive_edge)
            buy_ok = wb >= min_weight and wb > ws and edge >= edge_threshold
            sell_ok = ws >= min_weight and ws > wb and edge >= edge_threshold
            buy_ok = buy_ok and bool(atr_pass) and bool(vol_pass) and bool(adx_pass) and bool(mtf_pass_bull)
            sell_ok = sell_ok and bool(atr_pass) and bool(vol_pass) and bool(adx_pass) and bool(mtf_pass_bear)
            return buy_ok, sell_ok, wb, ws

        if signal_mode == "ADAPTIVE_EVIDENCE":
            families, bull_families, bear_families, required_families = StrategyEngine.evidence_summary(modules, evidence_min_families, evidence_family_min_score)
            trend_required = bool(evidence_require_trend)
            independent_required = bool(evidence_require_independent)
            edge_threshold = float(ADAPTIVE_DEFAULT_EDGE if adaptive_edge is None else adaptive_edge)
            bull_total = sum(v["bull_ratio"] for v in families.values()); bear_total = sum(v["bear_ratio"] for v in families.values())
            total = bull_total + bear_total; edge = abs(bull_total - bear_total) / total if total else 0.0
            bull_ok = len(bull_families) >= required_families and bull_total > bear_total and edge >= edge_threshold
            bear_ok = len(bear_families) >= required_families and bear_total > bull_total and edge >= edge_threshold
            if trend_required:
                bull_ok = bull_ok and "TREND" in bull_families; bear_ok = bear_ok and "TREND" in bear_families
            if independent_required:
                bull_ok = bull_ok and any(f in bull_families for f in ("MOMENTUM", "FLOW", "STRUCTURE"))
                bear_ok = bear_ok and any(f in bear_families for f in ("MOMENTUM", "FLOW", "STRUCTURE"))
            bull_ok = bull_ok and bool(atr_pass) and bool(adx_pass)
            bear_ok = bear_ok and bool(atr_pass) and bool(adx_pass)
            return bull_ok, bear_ok, bull_total, bear_total

        if signal_mode != "STRICT_ALL_FILTERS":
            raise ValueError(f"Unknown signal mode: {signal_mode}")

        strict_buy = bool(modules) and all(
            bool(bull) and not bool(bear) for _, bull, bear in modules
        )
        strict_sell = bool(modules) and all(
            bool(bear) and not bool(bull) for _, bull, bear in modules
        )
        return (
            strict_buy and bool(atr_pass) and bool(vol_pass)
            and bool(adx_pass) and bool(mtf_pass_bull),
            strict_sell and bool(atr_pass) and bool(vol_pass)
            and bool(adx_pass) and bool(mtf_pass_bear),
            buy_score, sell_score,
        )


    @staticmethod
    def decision_reason(directional_modules, signal_mode, min_score,
                        atr_pass=True, vol_pass=True, adx_pass=True,
                        mtf_pass_bull=True, mtf_pass_bear=True,
                        adaptive_edge=None, adaptive_min_weight=None, evidence_min_families=None, evidence_family_min_score=None, evidence_require_trend=True, evidence_require_independent=True):
        """Explain why the centralized strategy engine did or did not emit a side."""
        mode = str(signal_mode).strip().upper()
        modules = list(directional_modules or [])
        buy = sum(1 for _, bull, _ in modules if bool(bull))
        sell = sum(1 for _, _, bear in modules if bool(bear))
        if not modules:
            return "NO_ENABLED_DIRECTIONAL_MODULES"
        if mode == "ANY_NON_CONFLICTING":
            if buy > 0 and sell == 0: return "BUY_ANY_NON_CONFLICTING"
            if sell > 0 and buy == 0: return "SELL_ANY_NON_CONFLICTING"
            return f"CONFLICTING_OR_NEUTRAL_B{buy}_S{sell}"
        if mode == "SINGLE_SIGNAL":
            return "SINGLE_SIGNAL_MATCH" if any(bool(bull) != bool(bear) for _, bull, bear in modules) else "NO_UNAMBIGUOUS_SIGNAL"
        if mode in ("2_SIGNALS", "3_SIGNALS", "4_SIGNALS"):
            required = {"2_SIGNALS": 2, "3_SIGNALS": 3, "4_SIGNALS": 4}[mode]
            if buy >= required and buy > sell: return f"BUY_{required}_CONFIRMATIONS"
            if sell >= required and sell > buy: return f"SELL_{required}_CONFIRMATIONS"
            return f"INSUFFICIENT_OR_CONFLICTING_B{buy}_S{sell}_R{required}"
        if mode == "SCORE":
            if buy >= min_score and buy > sell: return f"BUY_SCORE_{buy}_MIN_{min_score}"
            if sell >= min_score and sell > buy: return f"SELL_SCORE_{sell}_MIN_{min_score}"
            return f"INSUFFICIENT_OR_CONFLICTING_B{buy}_S{sell}_R{min_score}"
        if mode == "ADAPTIVE_SCORE":
            weights = ADAPTIVE_MODULE_WEIGHTS
            wb = sum(float(weights.get(name, 1.0)) for name, bull, bear in modules if bool(bull) and not bool(bear))
            ws = sum(float(weights.get(name, 1.0)) for name, bull, bear in modules if bool(bear) and not bool(bull))
            total = wb + ws
            edge = abs(wb - ws) / total if total > 0 else 0.0
            min_weight = max(
                float(min_score),
                float(ADAPTIVE_DEFAULT_MIN_WEIGHT if adaptive_min_weight is None else adaptive_min_weight),
            )
            edge_threshold = float(
                ADAPTIVE_DEFAULT_EDGE if adaptive_edge is None else adaptive_edge
            )
            if wb >= min_weight and wb > ws and edge >= edge_threshold and atr_pass and vol_pass and adx_pass and mtf_pass_bull:
                return f"ADAPTIVE_BUY_W{wb:.2f}_EDGE{edge:.2f}"
            if ws >= min_weight and ws > wb and edge >= edge_threshold and atr_pass and vol_pass and adx_pass and mtf_pass_bear:
                return f"ADAPTIVE_SELL_W{ws:.2f}_EDGE{edge:.2f}"
            return f"ADAPTIVE_BLOCKED_WB{wb:.2f}_WS{ws:.2f}_EDGE{edge:.2f}"
        if mode == "ADAPTIVE_EVIDENCE":
            families, bull_families, bear_families, required = StrategyEngine.evidence_summary(modules, evidence_min_families, evidence_family_min_score)
            bt = sum(v["bull_ratio"] for v in families.values()); st = sum(v["bear_ratio"] for v in families.values()); total = bt + st; edge = abs(bt-st)/total if total else 0.0
            threshold = float(ADAPTIVE_DEFAULT_EDGE if adaptive_edge is None else adaptive_edge)
            if len(bull_families) >= required and bt > st and edge >= threshold and atr_pass and adx_pass: return "EVIDENCE_BUY_" + "+".join(bull_families) + f"_EDGE{edge:.2f}"
            if len(bear_families) >= required and st > bt and edge >= threshold and atr_pass and adx_pass: return "EVIDENCE_SELL_" + "+".join(bear_families) + f"_EDGE{edge:.2f}"
            return f"EVIDENCE_BLOCKED_BF{len(bull_families)}_SF{len(bear_families)}_EDGE{edge:.2f}"
        if mode == "STRICT_ALL_FILTERS":
            if buy == len(modules) and sell == 0 and atr_pass and vol_pass and adx_pass and mtf_pass_bull: return "STRICT_BUY_ALL_FILTERS_PASS"
            if sell == len(modules) and buy == 0 and atr_pass and vol_pass and adx_pass and mtf_pass_bear: return "STRICT_SELL_ALL_FILTERS_PASS"
            failed = [name for name, ok in (("ATR",atr_pass),("VOL",vol_pass),("ADX",adx_pass)) if not ok]
            return "STRICT_BLOCKED" + (f"_FILTERS_{','.join(failed)}" if failed else "_DIRECTION_OR_ALIGNMENT")
        return f"UNKNOWN_SIGNAL_MODE_{mode}"


class UniversalFuturesBotGUI:

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)

        # Responsive Windows sizing:
        # Do not force a 1500x950 window because many PCs use 1366x768,
        # 1440x900, or Windows DPI scaling.  Size the app to the available
        # screen and leave enough room for the controls + execution log.
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            win_w = min(1500, max(900, screen_w - 20))
            win_h = min(900, max(620, screen_h - 40))
            pos_x = max(0, (screen_w - win_w) // 2)
            pos_y = max(0, (screen_h - win_h) // 2)
            self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        except Exception:
            self.root.geometry("1280x720")

        self.root.minsize(900, 620)

        self.is_running = False
        self.bot_thread = None

        # Persistent bot profile / crash-recovery state.
        self.bot_profile_id = "BOT-01"
        self.session_id = None
        self.resume_requested = False
        self.resume_candidate = None
        self.resume_prompt_shown = False
        self.runtime_last_error = ""
        self.runtime_timeframe = ""
        self.runtime_account_mode = ""
        self.runtime_strategy_mode = ""
        self.runtime_strategy_modules = ""
        self.runtime_config_hash = ""
        self.runtime_resumed = False
        self.profile_lock_fd = None

        # Execution log is configured to auto-follow the newest message.
        self.log_autoscroll = True

        self.exchange = None
        self.exchange_id = None
        self.symbol = None

        self.total_trades = 0          # completed trades
        self.opened_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.net_pnl = 0.0
        self.start_balance = 0.0
        self.daily_start_balance = 0.0
        self.daily_start_date = None
        self.daily_peak_equity = 0.0
        self.session_peak_equity = 0.0
        self.consecutive_cycle_errors = 0
        self.last_market_data_ts = 0
        self.trade_pnls = []
        self.active_trade = None
        self.session_started_at = None
        self.session_max_trades = 0

        self.last_protected_position = None
        self.retired_managed_order_ids = set()
        self.tp1_be_enabled = True
        self.tp1_be_done = False
        # Exchange-side protection reconciliation.  A position must never
        # remain live if its protective SL disappears from open orders.
        self.last_protection_reconcile = 0.0
        self.protection_reconcile_interval = 10.0
        self.last_entry_candle_ts = None
        self.last_flat_time = 0.0
        # After a stop-loss / break-even stop exit, optionally require the
        # strategy to produce a valid opposite signal before allowing a
        # same-direction re-entry. This is independent of the in-position
        # reversal-hold rule and is signal-mode aware (1/2/3/4/SCORE).
        self.v_require_opposite_after_exit = None
        self.reentry_direction_lock = None
        self.reentry_lock_reason = ""
        # Optional Hold-All-Reverse SL behavior:
        # when enabled, the configured ROI threshold is NOT an exchange hard
        # stop.  Once the threshold is reached, the bot waits for ALL active
        # directional modules to reverse, then exits by strategy reversal.
        self.hold_sl_wait_reversal = False
        self.hold_sl_threshold_hit = False
        self.hold_sl_threshold_logged = False

        # Separate Grid Trading Engine state. OFF preserves the existing V8 execution path.
        self.grid_state = {
            "active": False, "mode": "OFF", "center": 0.0,
            "entry_orders": {}, "filled_levels": set(), "tp_order_id": None, "sl_order_id": None,
            "last_position_qty": 0.0, "last_position_entry": 0.0,
            "last_grid_reset": 0.0, "session_start_balance": 0.0,
            "peak_equity": 0.0, "paused_until": 0.0,
        }
        # V8.3.0 Volume S/R higher-timeframe cache. Higher-TF data is
        # refreshed only when its bucket can change, avoiding four API calls
        # every 30-second execution cycle.
        self.volume_sr_cache = {}
        self.volume_sr_cache_time = 0.0
        self.last_advanced_signal_log = None

        self._init_csv_log()
        self._init_master_db()
        self._build_ui()
        self.update_estimated_window()
        self.load_settings()
        self._refresh_profile_list(select_profile=self.bot_profile_id)

        # Give Tk time to finish constructing the GUI before showing a
        # recovery question.  A previous RUNNING/CRASHED checkpoint is never
        # resumed silently.
        self.root.after(500, self._check_resume_candidate)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -------------------- LOGGING ----------------------------

    # -------------------- PERSISTENCE / RECOVERY ---------------

    def _sanitize_profile_id(self, value=None):
        raw = str(
            value
            if value is not None
            else getattr(self, "bot_profile_id", "BOT-01")
        ).strip().upper()
        raw = re.sub(r"[^A-Z0-9._-]+", "_", raw)
        raw = raw.strip("._-")
        return raw[:64] or "BOT-01"

    def _profile_paths(self, profile_id=None):
        profile = self._sanitize_profile_id(
            profile_id if profile_id is not None else (
                self.v_bot_id.get() if hasattr(self, "v_bot_id") else self.bot_profile_id
            )
        )
        folder = PROFILE_DIR / profile
        folder.mkdir(parents=True, exist_ok=True)
        return (
            profile,
            folder,
            folder / "config.json",
            folder / "runtime_state.json",
        )

    def _get_config_path(self, profile_id=None, for_save=False):
        profile, folder, path, state_path = self._profile_paths(profile_id)
        if not for_save and path.exists():
            return str(path)
        # Backward compatibility: the original V8 config is imported into
        # BOT-01 on first save. Other profiles are independent.
        if (
            not for_save
            and profile == "BOT-01"
            and os.path.exists(CONFIG_FILE)
            and not path.exists()
        ):
            return CONFIG_FILE
        return str(path)

    def _get_runtime_state_path(self, profile_id=None):
        return str(self._profile_paths(profile_id)[3])

    def _read_json_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _write_json_atomic(self, path, payload):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _config_snapshot_for_recovery(self):
        cfg = self._read_json_file(self._get_config_path())
        if not isinstance(cfg, dict):
            return {}
        # Credentials remain in the normal profile config. Do not duplicate
        # secrets into the crash-recovery state file.
        for key in (
            "api_key", "api_secret", "tele_token", "tele_chat"
        ):
            cfg.pop(key, None)
        return cfg

    def _config_hash(self, cfg=None):
        if cfg is None:
            cfg = self._config_snapshot_for_recovery()
        try:
            raw = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        except Exception:
            return ""

    def _serializable_protected_position(self):
        p = self.last_protected_position
        if not isinstance(p, dict):
            return None
        allowed = (
            "side", "qty", "entry", "sl", "tp1", "tp2",
            "sl_id", "tp1_id", "tp2_id",
            "tp_orders_enabled", "hold_sl_wait_reversal",
        )
        return {k: p.get(k) for k in allowed if k in p}

    def _serializable_grid_state(self):
        gs = dict(self.grid_state or {})
        gs["filled_levels"] = sorted(
            str(x) for x in gs.get("filled_levels", set())
        )
        gs["entry_orders"] = {
            str(k): dict(v)
            for k, v in (gs.get("entry_orders") or {}).items()
        }
        return gs

    def _runtime_state_payload(self, status="RUNNING", last_error=None):
        return {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "status": status,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "bot_id": self._sanitize_profile_id(),
            "session_id": self.session_id,
            "exchange": self.exchange_id,
            "account_mode": self.runtime_account_mode,
            "symbol": self.symbol,
            "timeframe": self.runtime_timeframe,
            "strategy_mode": self.runtime_strategy_mode,
            "strategy_modules": self.runtime_strategy_modules,
            "config_hash": self.runtime_config_hash,
            "resumed": bool(self.runtime_resumed),
            "session_started_at": self.session_started_at,
            "session_max_trades": self.session_max_trades,
            "start_balance": self.start_balance,
            "daily_start_balance": self.daily_start_balance,
            "daily_peak_equity": self.daily_peak_equity,
            "session_peak_equity": self.session_peak_equity,
            "consecutive_cycle_errors": self.consecutive_cycle_errors,
            "last_market_data_ts": self.last_market_data_ts,
            "daily_start_date": (
                self.daily_start_date.isoformat()
                if hasattr(self.daily_start_date, "isoformat")
                else self.daily_start_date
            ),
            "stats": {
                "total_trades": self.total_trades,
                "opened_trades": self.opened_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "trade_pnls": list(self.trade_pnls[-500:]),
                "net_pnl": self.net_pnl,
            },
            "position_state": {
                "active_trade": self.active_trade,
                "retired_managed_order_ids": sorted(str(x) for x in self.retired_managed_order_ids if x),
                "last_protected_position": self._serializable_protected_position(),
                "tp1_be_done": bool(self.tp1_be_done),
                "hold_sl_wait_reversal": bool(self.hold_sl_wait_reversal),
                "hold_sl_threshold_hit": bool(self.hold_sl_threshold_hit),
                "hold_sl_threshold_logged": bool(self.hold_sl_threshold_logged),
                "reentry_direction_lock": self.reentry_direction_lock,
                "reentry_lock_reason": self.reentry_lock_reason,
                "last_entry_candle_ts": self.last_entry_candle_ts,
                "last_flat_time": self.last_flat_time,
            },
            "grid_state": self._serializable_grid_state(),
            "config_snapshot": self._config_snapshot_for_recovery(),
            "last_error": last_error if last_error is not None else self.runtime_last_error,
        }

    def _persist_runtime_state(self, status="RUNNING", last_error=None):
        try:
            if not self.session_id:
                return
            path = self._get_runtime_state_path()
            payload = self._runtime_state_payload(status=status, last_error=last_error)
            self._write_json_atomic(path, payload)
        except Exception as e:
            self.log(f"RUNTIME STATE SAVE WARNING: {e}")

    def _load_runtime_state(self):
        path = self._get_runtime_state_path()
        state = self._read_json_file(path)
        return state if isinstance(state, dict) else None

    def _checkpoint_gui_config(self):
        """Run on Tk's main thread so live GUI edits are safely persisted."""
        try:
            if not self.is_running:
                return
            self.save_settings()
            self.runtime_config_hash = self._config_hash()
            self._persist_runtime_state(status="RUNNING")
        except Exception as e:
            self.log(f"LIVE CONFIG CHECKPOINT WARNING: {e}")

    def _check_resume_candidate(self):
        try:
            if self.resume_prompt_shown or self.is_running:
                return
            self.resume_prompt_shown = True
            state = self._load_runtime_state()
            if not state:
                return
            status = str(state.get("status") or "").upper()
            if status not in ("RUNNING", "CRASHED", "STOPPING", "PAUSED_WITH_POSITION"):
                return
            bot_id = state.get("bot_id", self._sanitize_profile_id())
            exchange = str(state.get("exchange") or "").upper()
            symbol = state.get("symbol") or self.e_symbol.get().strip().upper()
            updated = state.get("updated_at_utc", "unknown")
            position = (state.get("position_state") or {}).get("last_protected_position")
            grid = state.get("grid_state") or {}
            mode = state.get("strategy_mode") or grid.get("mode") or "UNKNOWN"
            detail = (
                f"Previous bot session found.\n\n"
                f"Profile: {bot_id}\n"
                f"Exchange: {exchange or 'UNKNOWN'}\n"
                f"Symbol: {symbol}\n"
                f"Mode: {mode}\n"
                f"Last checkpoint: {updated}\n"
                f"Saved position: "
                f"{(position or {}).get('side', 'NONE') if isinstance(position, dict) else 'NONE'}\n\n"
                "Resume the last saved bot stage?\n\n"
                "YES = restore saved configuration/runtime state and verify it "
                "against the exchange before continuing.\n"
                "NO = start a completely new bot session. Existing exchange "
                "positions/orders will NOT be silently adopted."
            )
            if messagebox.askyesno("Bot Recovery", detail):
                self.resume_candidate = state
                self.resume_requested = True
                self._restore_recovery_config(state)
                self.log("RECOVERY SELECTED: Resume last saved stage.")
            else:
                self.resume_candidate = state
                self.resume_requested = False
                self.log(
                    "RECOVERY SELECTED: Start New Bot. "
                    "The exchange will be checked for existing inventory/orders."
                )
        except Exception as e:
            self.log(f"Recovery prompt error: {e}")

    def _restore_recovery_config(self, state):
        snapshot = state.get("config_snapshot")
        if not isinstance(snapshot, dict):
            return
        try:
            path = self._get_config_path(for_save=True)
            current = self._read_json_file(path) or {}
            # Preserve current credentials/secrets while restoring all
            # strategy/risk/execution configuration from the checkpoint.
            for key, value in snapshot.items():
                if key not in ("api_key", "api_secret", "tele_token", "tele_chat"):
                    current[key] = value
            current["bot_id"] = self._sanitize_profile_id(
                state.get("bot_id", self._sanitize_profile_id())
            )
            self._write_json_atomic(path, current)
            self.load_settings(show_resume=False)
        except Exception as e:
            self.log(f"Recovery configuration restore warning: {e}")

    def _restore_runtime_state(self, state):
        self.session_id = state.get("session_id") or str(uuid.uuid4())
        self.runtime_account_mode = str(state.get("account_mode") or self.v_account_mode.get())
        self.runtime_timeframe = str(state.get("timeframe") or self.v_tf.get()).lower()
        self.runtime_strategy_mode = str(
            state.get("strategy_mode") or self.v_signal_mode.get()
        )
        self.runtime_strategy_modules = str(state.get("strategy_modules") or "")
        self.runtime_config_hash = str(state.get("config_hash") or "")
        self.runtime_resumed = True

        self.session_started_at = state.get("session_started_at") or time.time()
        self.session_max_trades = int(state.get("session_max_trades") or 0)
        self.start_balance = float(state.get("start_balance") or 0.0)
        self.daily_start_balance = float(
            state.get("daily_start_balance") or self.start_balance
        )
        self.daily_peak_equity = float(state.get("daily_peak_equity") or self.daily_start_balance or 0.0)
        self.session_peak_equity = float(state.get("session_peak_equity") or self.start_balance or 0.0)
        self.consecutive_cycle_errors = int(state.get("consecutive_cycle_errors") or 0)
        self.last_market_data_ts = int(state.get("last_market_data_ts") or 0)
        saved_date = state.get("daily_start_date")
        try:
            self.daily_start_date = (
                datetime.fromisoformat(saved_date).date()
                if saved_date else datetime.now().date()            )
        except Exception:
            self.daily_start_date = datetime.now().date()

        stats = state.get("stats") or {}
        self.total_trades = int(stats.get("total_trades") or 0)
        self.opened_trades = int(stats.get("opened_trades") or 0)
        self.winning_trades = int(stats.get("winning_trades") or 0)
        self.losing_trades = int(stats.get("losing_trades") or 0)
        self.trade_pnls = list(stats.get("trade_pnls") or [])
        self.net_pnl = float(stats.get("net_pnl") or 0.0)

        ps = state.get("position_state") or {}
        self.active_trade = ps.get("active_trade")
        self.last_protected_position = ps.get("last_protected_position")
        self.retired_managed_order_ids = set(str(x) for x in (ps.get("retired_managed_order_ids") or []) if x)
        self.tp1_be_done = bool(ps.get("tp1_be_done", False))
        self.hold_sl_wait_reversal = bool(ps.get("hold_sl_wait_reversal", False))
        self.hold_sl_threshold_hit = bool(ps.get("hold_sl_threshold_hit", False))
        self.hold_sl_threshold_logged = bool(ps.get("hold_sl_threshold_logged", False))
        self.reentry_direction_lock = ps.get("reentry_direction_lock")
        self.reentry_lock_reason = str(ps.get("reentry_lock_reason") or "")
        self.last_entry_candle_ts = ps.get("last_entry_candle_ts")
        self.last_flat_time = float(ps.get("last_flat_time") or 0.0)

        gs = dict(state.get("grid_state") or {})
        gs.setdefault("active", False)
        gs.setdefault("mode", "OFF")
        gs.setdefault("center", 0.0)
        gs.setdefault("entry_orders", {})
        gs.setdefault("filled_levels", [])
        gs.setdefault("tp_order_id", None)
        gs.setdefault("sl_order_id", None)
        gs.setdefault("last_position_qty", 0.0)
        gs.setdefault("last_position_entry", 0.0)
        gs.setdefault("last_grid_reset", 0.0)
        gs.setdefault("session_start_balance", self.start_balance)
        gs.setdefault("peak_equity", 0.0)
        gs.setdefault("paused_until", 0.0)
        gs.setdefault("auto_direction", None)
        gs["filled_levels"] = set(str(x) for x in gs.get("filled_levels", []))
        gs["entry_orders"] = dict(gs.get("entry_orders") or {})
        self.grid_state = gs

    def _position_matches_saved(self, current, saved, qty_tolerance=0.02, price_tolerance=0.005):
        if not current or not isinstance(saved, dict):
            return False
        if str(current.get("side")) != str(saved.get("side")):
            return False
        try:
            cq = float(current.get("qty") or 0)
            sq = float(saved.get("qty") or 0)
            ce = float(current.get("entry") or 0)
            se = float(saved.get("entry") or 0)
            if cq <= 0 or sq <= 0 or ce <= 0 or se <= 0:
                return False
            return (
                abs(cq - sq) / max(sq, 1e-12) <= qty_tolerance
                and abs(ce - se) / max(se, 1e-12) <= price_tolerance
            )
        except Exception:
            return False

    def _verify_resume_exchange_state(self):
        if not self.resume_candidate:
            raise RuntimeError("Resume requested but no recovery checkpoint is available.")

        state = self.resume_candidate
        saved_exchange = str(state.get("exchange") or "").lower()
        saved_symbol = str(state.get("symbol") or "").upper()
        if saved_exchange and saved_exchange != self.exchange_id:
            raise RuntimeError(
                f"RESUME BLOCKED: saved exchange={saved_exchange} but current exchange={self.exchange_id}."
            )
        if saved_symbol and saved_symbol != str(self.symbol).upper():
            raise RuntimeError(
                f"RESUME BLOCKED: saved symbol={saved_symbol} but current symbol={self.symbol}."
            )

        current_position = self.fetch_position(self.symbol)
        # Strict read is intentional: an exchange read failure must never look
        # like a clean/flat account during recovery.
        current_orders = self.fetch_open_orders_safe(self.symbol, strict=True)
        current_ids = {
            str(o.get("id"))
            for o in current_orders
            if o.get("id")
        }

        grid_active = bool((state.get("grid_state") or {}).get("active"))
        saved_position = (
            (state.get("position_state") or {}).get("last_protected_position")
        )
        saved_active_trade = (state.get("position_state") or {}).get("active_trade")

        if grid_active:
            known_ids = {
                str(meta.get("id"))
                for meta in self.grid_state.get("entry_orders", {}).values()
                if meta.get("id")
            }
            for oid in (
                self.grid_state.get("tp_order_id"),
                self.grid_state.get("sl_order_id"),
            ):
                if oid:
                    known_ids.add(str(oid))

            grid_fill_evidence = bool(
                saved_position
                or float(self.grid_state.get("last_position_qty") or 0.0) > 0
                or self.grid_state.get("filled_levels")
            )

            # Verify every persisted Grid order individually. Missing from the
            # open-order page is not treated as cancellation/fill.
            for key, meta in list(self.grid_state.get("entry_orders", {}).items()):
                oid = str(meta.get("id") or "")
                if not oid:
                    continue
                order = self._fetch_specific_order(self.symbol, oid)
                if order:
                    status = str(order.get("status") or "").lower()
                    filled = float(order.get("filled") or 0.0)
                    if status in ("closed", "filled") and filled > 0:
                        self.grid_state["filled_levels"].add(key)
                        self.grid_state["entry_orders"].pop(key, None)
                        grid_fill_evidence = True
                    elif status in ("canceled", "cancelled", "rejected", "expired"):
                        self.grid_state["entry_orders"].pop(key, None)
                elif oid not in current_ids:
                    self.log(
                        f"RECOVERY GRID NOTICE: unable to verify order {oid}; "
                        "retaining it locally to prevent duplicate recreation."
                    )

            if current_position:
                if not grid_fill_evidence:
                    raise RuntimeError(
                        "RESUME BLOCKED: exchange has a Grid position but the "
                        "checkpoint contains no evidence that this position was "
                        "created by the saved Grid engine."
                    )
                # A resumed Grid may have filled a level after the last checkpoint.
                # Accept only a side compatible with the persisted Grid direction.
                mode = str(self.grid_state.get("mode") or "").upper()
                allowed_side = {
                    "LONG_GRID": "LONG",
                    "SHORT_GRID": "SHORT",
                }.get(mode)
                auto_direction = self.grid_state.get("auto_direction")
                if mode == "NEUTRAL_GRID" and auto_direction in ("LONG", "SHORT"):
                    allowed_side = auto_direction
                if allowed_side and current_position["side"] != allowed_side:
                    raise RuntimeError(
                        f"RESUME BLOCKED: exchange has {current_position['side']} "
                        f"but saved Grid direction is {allowed_side}."
                    )
                self.grid_state["last_position_qty"] = float(current_position["qty"])
                self.grid_state["last_position_entry"] = float(current_position["entry"])
            elif saved_position:
                # Position disappeared while the bot was offline. Do not invent
                # a fill or PnL; let the Grid rebuild safely from flat state.
                self.log(
                    "RECOVERY GRID: saved position is no longer on the exchange; "
                    "continuing from verified flat state."
                )
                self.grid_state["last_position_qty"] = 0.0
                self.grid_state["last_position_entry"] = 0.0

            unknown_open = current_ids - known_ids
            if unknown_open:
                raise RuntimeError(
                    "RESUME BLOCKED: exchange has unmanaged open Grid order(s): "
                    + ",".join(sorted(list(unknown_open))[:20])
                    + (" ..." if len(unknown_open) > 20 else "")
                )

            self.log(
                f"RECOVERY VERIFIED: Grid state restored | "
                f"Position={'OPEN' if current_position else 'FLAT'} | "
                f"ManagedOpenOrders={len(known_ids & current_ids)}"
            )
            return

        # Normal strategy engine.
        if saved_active_trade or saved_position:
            if current_position:
                # An open exchange position may only be resumed when the
                # checkpoint contains enough identity evidence to prove that it
                # belongs to this bot.  Previously an active_trade without a
                # last_protected_position could allow an unrelated live position
                # to be adopted during recovery.
                saved_identity = saved_position
                if not saved_identity and isinstance(saved_active_trade, dict):
                    saved_identity = saved_active_trade
                if not saved_identity:
                    raise RuntimeError(
                        "RESUME BLOCKED: exchange position exists but the checkpoint "
                        "does not contain a verifiable saved position identity."
                    )
                if not self._position_matches_saved(current_position, saved_identity):
                    raise RuntimeError(
                        "RESUME BLOCKED: exchange position does not match the saved bot position "
                        "(side/quantity/entry mismatch)."
                    )
                if not self.last_protected_position:
                    raise RuntimeError(
                        "RESUME BLOCKED: live position has no saved protection state. "
                        "The bot will not resume an open position without a protection checkpoint."
                    )
                self.last_protected_position["qty"] = current_position["qty"]
                self.last_protected_position["entry"] = current_position["entry"]
                expected_protection_ids = {
                    str(self.last_protected_position.get(key))
                    for key in ("sl_id", "tp1_id", "tp2_id")
                    if self.last_protected_position
                    and self.last_protected_position.get(key)
                }
                unknown_protection_orders = current_ids - expected_protection_ids
                if unknown_protection_orders:
                    raise RuntimeError(
                        "RESUME BLOCKED: live position has unmanaged open order(s): "
                        + ",".join(sorted(list(unknown_protection_orders))[:20])
                        + (" ..." if len(unknown_protection_orders) > 20 else "")
                    )

                # Do not wait for the normal 10-second reconciliation interval
                # after a restart.  A resumed position must leave recovery with
                # verified protection (or the intentional Hold-SL wait mode).
                self.last_protection_reconcile = 0.0
                try:
                    self._reconcile_protection_orders(current_position)
                except Exception as protection_error:
                    raise RuntimeError(
                        f"RESUME BLOCKED: saved position protection could not be "
                        f"verified/rebuilt safely: {protection_error}"
                    ) from protection_error
            else:
                # The trade ended while the process was down. Treat it as an
                # external/protection close and conservatively block same-side
                # re-entry when that safety option is enabled.
                if self.active_trade is not None:
                    try:
                        balance_now = self.fetch_balance_total()
                    except Exception:
                        balance_now = None
                    self._finalize_performance_trade(
                        reason="RECOVERY: POSITION CLOSED WHILE BOT WAS OFFLINE",
                        balance=balance_now,
                    )
                if (
                    self.last_protected_position
                    and self.v_require_opposite_after_exit.get()
                    and self.reentry_direction_lock not in ("LONG", "SHORT")
                ):
                    side = self.last_protected_position.get("side")
                    if side in ("LONG", "SHORT"):
                        self.reentry_direction_lock = side
                        self.reentry_lock_reason = "RECOVERY_EXTERNAL_CLOSE"
                self.last_protected_position = None
                self.tp1_be_done = False
                self.hold_sl_wait_reversal = False
                self.hold_sl_threshold_hit = False
                self.hold_sl_threshold_logged = False
                self.last_protection_reconcile = 0.0
                self.last_flat_time = time.time()
                self.log(
                    "RECOVERY: saved position was already closed while bot was offline. "
                    "Resuming from flat state with conservative re-entry protection."
                )
        elif current_position:
            raise RuntimeError(
                "RESUME BLOCKED: exchange has a position but the saved bot state was flat. "
                "The bot will not silently adopt an unknown/manual position."
            )
        elif current_orders:
            raise RuntimeError(
                "RESUME BLOCKED: exchange has open orders but the saved normal-strategy "
                "state was flat. Clean the orders or restore the correct bot checkpoint."
            )

        self.log(
            f"RECOVERY VERIFIED: Normal strategy state restored | "
            f"Position={'OPEN' if current_position else 'FLAT'} | "
            f"OpenOrders={len(current_orders)}"
        )

    def _mark_recovery_state_stopped(self, reason=""):
        try:
            if not self.session_id:
                return
            current = self._load_runtime_state() or {}
            status = "PAUSED_WITH_POSITION" if self.fetch_position(self.symbol) else "STOPPED"
            if reason:
                current["last_error"] = reason
            current["status"] = status
            current["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
            self._write_json_atomic(self._get_runtime_state_path(), current)
        except Exception as e:
            self.log(f"Recovery stop-state warning: {e}")

    def _acquire_profile_lock(self):
        """Allow only one live process per Bot Profile ID."""
        _, folder, _, _ = self._profile_paths()
        lock_path = folder / "bot.lock"
        payload = {
            "pid": os.getpid(),
            "bot_id": self._sanitize_profile_id(),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        if lock_path.exists():
            old = self._read_json_file(lock_path) or {}
            old_pid = int(old.get("pid") or 0)
            alive = False
            if old_pid:
                try:
                    os.kill(old_pid, 0)
                    alive = True
                except Exception:
                    alive = False
            if alive:
                raise RuntimeError(
                    f"PROFILE LOCKED: Bot Profile {self._sanitize_profile_id()} "
                    f"is already running under PID {old_pid}. "
                    "Use a different Profile ID for another simultaneous bot."
                )
            try:
                lock_path.unlink()
            except Exception:
                pass

        try:
            self.profile_lock_fd = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            os.write(
                self.profile_lock_fd,
                json.dumps(payload).encode("utf-8"),
            )
            return True
        except FileExistsError:
            raise RuntimeError(
                f"PROFILE LOCKED: Bot Profile {self._sanitize_profile_id()} "
                "is already active."
            )
        except Exception as e:
            raise RuntimeError(f"Could not acquire bot profile lock: {e}") from e

    def _release_profile_lock(self):
        try:
            if self.profile_lock_fd is not None:
                try:
                    os.close(self.profile_lock_fd)
                except Exception:
                    pass
                self.profile_lock_fd = None
            _, folder, _, _ = self._profile_paths()
            lock_path = folder / "bot.lock"
            if lock_path.exists():
                old = self._read_json_file(lock_path) or {}
                if int(old.get("pid") or 0) in (0, os.getpid()):
                    lock_path.unlink()
        except Exception as e:
            self.log(f"PROFILE LOCK RELEASE WARNING: {e}")

    def load_profile_from_ui(self):
        """Load exactly the Profile ID typed/selected in the Connection field."""
        if self.is_running:
            messagebox.showwarning(
                "Bot running",
                "Stop the bot before loading another profile."
            )
            return
        try:
            candidate = self._sanitize_profile_id(self.v_bot_id.get())
            candidate_path = self._profile_config_path_only(candidate)
            if not candidate_path.exists() and not (
                candidate == "BOT-01" and Path(CONFIG_FILE).exists()
            ):
                raise RuntimeError(
                    f"No saved configuration exists for profile {candidate}. "
                    "Use Save Profile or Copy Selected Profile first."
                )
            self.bot_profile_id = candidate
            self.v_bot_id.set(candidate)
            self.resume_prompt_shown = False
            self.resume_requested = False
            self.resume_candidate = None
            self.load_settings(show_resume=False)
            self._refresh_profile_list(select_profile=self.bot_profile_id)
            self._check_resume_candidate()
        except Exception as e:
            messagebox.showerror("Profile load failed", str(e))

    def _profile_config_path_only(self, profile_id):
        """Return a profile config path without mutating GUI state."""
        profile = self._sanitize_profile_id(profile_id)
        return PROFILE_DIR / profile / "config.json"

    def _profile_lock_is_active(self, profile_id):
        """Return True when another live process owns the profile lock."""
        profile = self._sanitize_profile_id(profile_id)
        lock_path = PROFILE_DIR / profile / "bot.lock"
        if not lock_path.exists():
            return False
        payload = self._read_json_file(lock_path) or {}
        try:
            pid = int(payload.get("pid") or 0)
        except Exception:
            pid = 0
        if pid and pid == os.getpid():
            return False
        if pid:
            try:
                os.kill(pid, 0)
                return True
            except Exception:
                pass
        # A stale lock is not considered active; _acquire_profile_lock will
        # remove it safely when the profile is actually started.
        return False

    def _profile_strategy_summary(self, cfg):
        labels = [
            ("use_st", "ST"),
            ("use_ema", "EMA"),
            ("use_ema_cross", "EMA Cross"),
            ("use_macd", "MACD"),
            ("use_rsi", "RSI"),
            ("use_bb", "BB"),
            ("use_stoch", "Stoch"),
            ("use_vwap", "VWAP"),
            ("use_vwap_delta", "VWAP Delta"),
            ("use_vidya", "VIDYA"),
            ("use_nwe", "NWE"),
            ("use_liq_swings", "Liquidity"),
            ("use_trendline", "Trendline"),
            ("use_mtf", "4H MTF"),
            ("use_vol", "Volume"),
            ("use_adx", "ADX"),
            ("use_atr", "ATR"),
        ]
        return ", ".join(label for key, label in labels if bool(cfg.get(key))) or "None"

    def _profile_summary_record(self, profile_id):
        """Build a safe, UI-friendly summary for one saved profile."""
        profile = self._sanitize_profile_id(profile_id)
        path = self._profile_config_path_only(profile)
        legacy = PROFILE_DIR / profile / "config.json"
        if not path.exists() and profile == "BOT-01" and Path(CONFIG_FILE).exists():
            path = Path(CONFIG_FILE)
        if not path.exists():
            return None

        cfg = self._read_json_file(path) or {}
        runtime_path = PROFILE_DIR / profile / "runtime_state.json"
        runtime = self._read_json_file(runtime_path) or {}
        status = str(runtime.get("status") or "CONFIGURED").upper()
        if self._profile_lock_is_active(profile):
            status = "RUNNING"
        grid_mode = str(cfg.get("grid_mode") or "OFF").upper()
        signal_mode = str(cfg.get("signal_mode") or "SINGLE_SIGNAL").upper()
        strategy_mode = grid_mode if grid_mode not in ("OFF", "DIRECT_SHOT") else signal_mode
        size_mode = str(cfg.get("size_mode") or "EQUITY_RISK_%")
        qty_display = (
            f"Risk {cfg.get('risk_pct', '1.0')}%"
            if size_mode == "EQUITY_RISK_%"
            else f"Fixed {cfg.get('fixed_qty', '0.001')}"
        )
        updated = runtime.get("updated_at_utc")
        if not updated:
            try:
                updated = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            except Exception:
                updated = ""
        return {
            "profile": profile,
            "exchange": str(cfg.get("exchange") or "").upper(),
            "account": str(cfg.get("account_mode") or ""),
            "symbol": str(cfg.get("symbol") or ""),
            "timeframe": str(cfg.get("timeframe") or ""),
            "leverage": str(cfg.get("leverage") or ""),
            "mode": strategy_mode,
            "signal": signal_mode,
            "qty": qty_display,
            "grid": grid_mode,
            "strategy": self._profile_strategy_summary(cfg),
            "status": status,
            "updated": str(updated).replace("T", " ")[:19],
        }

    def _list_saved_profiles(self):
        """Return all saved profile IDs, including legacy BOT-01."""
        ids = set()
        try:
            if PROFILE_DIR.exists():
                for folder in PROFILE_DIR.iterdir():
                    if folder.is_dir() and (folder / "config.json").exists():
                        ids.add(self._sanitize_profile_id(folder.name))
        except Exception:
            pass
        if Path(CONFIG_FILE).exists():
            ids.add("BOT-01")
        return sorted(ids)

    def _refresh_profile_list(self, select_profile=None):
        tree = getattr(self, "profile_tree", None)
        if tree is None:
            return
        selected = select_profile or self._sanitize_profile_id(self.v_bot_id.get())
        for item in tree.get_children():
            tree.delete(item)
        selected_item = None
        for profile in self._list_saved_profiles():
            rec = self._profile_summary_record(profile)
            if not rec:
                continue
            values = (
                rec["profile"], rec["exchange"], rec["account"], rec["symbol"],
                rec["timeframe"], rec["leverage"], rec["mode"], rec["qty"],
                rec["grid"], rec["status"], rec["updated"],
            )
            item = tree.insert("", "end", values=values)
            if rec["profile"] == selected:
                selected_item = item
        if selected_item:
            tree.selection_set(selected_item)
            tree.focus(selected_item)
            tree.see(selected_item)
            self._show_selected_profile_details()
        elif tree.get_children():
            first = tree.get_children()[0]
            tree.selection_set(first)
            tree.focus(first)
            self._show_selected_profile_details()
        else:
            self._set_profile_details_text("No saved bot profiles found.\n\nSave a profile to create BOT-01 or another profile.")

    def _selected_profile_id(self):
        tree = getattr(self, "profile_tree", None)
        if tree is None:
            return self._sanitize_profile_id(self.v_bot_id.get())
        selection = tree.selection()
        if not selection:
            return self._sanitize_profile_id(self.v_bot_id.get())
        values = tree.item(selection[0], "values")
        return self._sanitize_profile_id(values[0]) if values else self._sanitize_profile_id(self.v_bot_id.get())

    def _set_profile_details_text(self, content):
        box = getattr(self, "profile_details", None)
        if box is None:
            return
        box.configure(state="normal")
        box.delete("1.0", tk.END)
        box.insert("1.0", content)
        box.configure(state="disabled")

    def _profile_details_text(self, profile_id):
        profile = self._sanitize_profile_id(profile_id)
        path = self._profile_config_path_only(profile)
        if not path.exists() and profile == "BOT-01" and Path(CONFIG_FILE).exists():
            path = Path(CONFIG_FILE)
        cfg = self._read_json_file(path) or {}
        if not cfg:
            return f"Profile {profile} has no saved configuration."

        runtime = self._read_json_file(PROFILE_DIR / profile / "runtime_state.json") or {}
        lines_out = [
            f"PROFILE: {profile}",
            "=" * 92,
            "CORE / MARKET",
            f"Exchange       : {cfg.get('exchange', '')}",
            f"Account Mode   : {cfg.get('account_mode', '')}",
            f"Symbol / Pair  : {cfg.get('symbol', '')}",
            f"Timeframe      : {cfg.get('timeframe', '')}",
            f"Leverage       : {cfg.get('leverage', '')}x",
            f"Max Trades     : {cfg.get('max_trades', '')}",
            f"Cooldown        : {cfg.get('cooldown_min', '')} min",
            f"No Same Candle : {cfg.get('no_same_candle', '')}",
            "",
            "STRATEGY",
            f"Signal Mode    : {cfg.get('signal_mode', '')}",
            f"Minimum Score  : {cfg.get('min_score', '')}",
            f"Strategy Modules: {self._profile_strategy_summary(cfg)}",
            f"Hold All Reverse: {cfg.get('hold_until_all_reverse', '')}",
            f"Post-SL Lock   : {cfg.get('require_opposite_after_exit', cfg.get('require_opposite_after_sl', ''))}",
            "",
            "GRID",
            f"Grid Mode      : {cfg.get('grid_mode', '')}",
            f"Levels         : {cfg.get('grid_levels', '')}",
            f"Spacing        : {cfg.get('grid_spacing', '')}%",
            f"Order Size     : {cfg.get('grid_order_size', '')} USDT",
            f"Size Increase  : {cfg.get('grid_size_increase', '')}%",
            f"Grid TP / SL   : {cfg.get('grid_tp', '')}% / {cfg.get('grid_sl', '')}%",
            f"Max Exposure   : {cfg.get('grid_max_exposure', '')} USDT",
            f"Max Grid DD    : {cfg.get('grid_max_dd', '')}%",
            f"Grid Score Min : {cfg.get('grid_score_min', '')}",
            f"Trend Filter   : {cfg.get('grid_trend_filter', '')}",
            f"Recenter       : {cfg.get('grid_recenter', '')} / {cfg.get('grid_recenter_distance', '')}%",
            f"Cooldown       : {cfg.get('grid_cooldown', '')} sec",
            "",
            "POSITION SIZING / PROTECTION",
            f"Size Mode      : {cfg.get('size_mode', '')}",
            f"Risk %         : {cfg.get('risk_pct', '')}%",
            f"Fixed Qty      : {cfg.get('fixed_qty', '')}",
            f"Daily DD       : {cfg.get('max_dd', '')}%",
            f"Emergency Loss : {cfg.get('emergency_capital_pct', '')}%",
            f"SL Mode        : {cfg.get('sl_mode', cfg.get('sltp_mode', ''))}",
            f"TP Mode        : {cfg.get('tp_mode', cfg.get('sltp_mode', ''))}",
            f"SL / TP1 / TP2 : {cfg.get('sl_pct', '')}% / {cfg.get('tp1_pct', '')}% / {cfg.get('tp2_pct', '')}%",
            f"TP Quantity    : {cfg.get('tp_qty_mode', '')}",
            f"TP1 / TP2 Close: {cfg.get('tp1_close', '')} / {cfg.get('tp2_close', '')}",
            f"TP1 Break-Even : {cfg.get('tp1_be', '')}",
            f"Hold-SL ROI    : {cfg.get('hold_sl_roi', '')}%",
            f"Hold-SL Wait   : {cfg.get('hold_sl_wait_reversal', '')}",
            "",
            "ALERTS",
            f"Telegram       : {cfg.get('tele_enable', '')}",
            f"Telegram Chat  : {cfg.get('tele_chat', '')}",
            "",
            "RECOVERY / RUNTIME",
            f"Runtime Status : {runtime.get('status', 'CONFIGURED')}",
            f"Session ID     : {runtime.get('session_id', '')}",
            f"Resumed        : {runtime.get('resumed', False)}",
            f"Last Checkpoint: {runtime.get('updated_at_utc', '')}",
            f"Config Hash    : {runtime.get('config_hash', '')}",
            f"Runtime Symbol : {runtime.get('symbol', '')}",
            f"Runtime Mode   : {runtime.get('strategy_mode', '')}",
            "",
            "ALL SAVED SETTINGS (secrets masked)",
            "-" * 92,
        ]
        secret_keys = {"api_key", "api_secret", "tele_token"}
        for key in sorted(cfg):
            value = cfg.get(key)
            if key in secret_keys:
                if value:
                    text_value = "*" * min(max(len(str(value)), 8), 24)
                else:
                    text_value = ""
            else:
                text_value = str(value)
            lines_out.append(f"{key:30} = {text_value}")
        return "\n".join(lines_out)

    def _show_selected_profile_details(self, _event=None):
        profile = self._selected_profile_id()
        self._set_profile_details_text(self._profile_details_text(profile))

    def _load_selected_profile(self):
        if self.is_running:
            messagebox.showwarning("Bot running", "Stop the bot before loading another profile.")
            return
        profile = self._selected_profile_id()
        path = self._profile_config_path_only(profile)
        if not path.exists() and not (profile == "BOT-01" and Path(CONFIG_FILE).exists()):
            messagebox.showwarning("Profile not found", f"No saved configuration exists for {profile}.")
            return
        self.v_bot_id.set(profile)
        self.load_profile_from_ui()

    def _copy_selected_profile(self):
        if self.is_running:
            messagebox.showwarning("Bot running", "Stop the bot before copying a profile.")
            return
        source = self._selected_profile_id()
        source_path = self._profile_config_path_only(source)
        if not source_path.exists() and source == "BOT-01" and Path(CONFIG_FILE).exists():
            source_path = Path(CONFIG_FILE)
        cfg = self._read_json_file(source_path)
        if not isinstance(cfg, dict):
            messagebox.showerror("Copy Profile", f"Could not read source profile {source}.")
            return

        target = simpledialog.askstring(
            "Copy Bot Profile",
            f"Copy {source} to a new Bot Profile ID.\n\n"
            "All strategy, risk, Grid, exchange and API credential settings will be copied.\n"
            "You can then change Symbol, Quantity/Risk and Leverage before starting.",
            initialvalue=f"{source}-COPY",
            parent=self.root,
        )
        if target is None:
            return
        target = self._sanitize_profile_id(target)
        if target == source:
            messagebox.showwarning("Copy Profile", "Source and target Profile IDs must be different.")
            return

        target_path = self._profile_config_path_only(target)
        if target_path.exists():
            if not messagebox.askyesno(
                "Overwrite Profile?",
                f"{target} already exists. Replace its saved configuration and reset its recovery state?",
                parent=self.root,
            ):
                return
        if self._profile_lock_is_active(target):
            messagebox.showerror("Copy Profile", f"Profile {target} is currently active in another bot process.")
            return

        target_path.parent.mkdir(parents=True, exist_ok=True)
        cfg["bot_id"] = target
        self._write_json_atomic(target_path, cfg)
        target_state = PROFILE_DIR / target / "runtime_state.json"
        try:
            if target_state.exists():
                target_state.unlink()
        except Exception as e:
            self.log(f"PROFILE COPY WARNING: could not reset old runtime state: {e}")

        self.v_bot_id.set(target)
        self.load_settings(show_resume=False)
        self._refresh_profile_list(select_profile=target)
        self.log(
            f"PROFILE COPIED: {source} -> {target} | "
            "All saved settings copied; runtime recovery state reset."
        )
        messagebox.showinfo(
            "Profile Copied",
            f"{target} was created from {source}.\n\n"
            "Now change Symbol/Pair, Quantity or Risk, and Leverage as needed, "
            "then click Save Profile.",
            parent=self.root,
        )

    def _delete_current_profile(self):
        """Delete the profile named in the Bot Profile ID field.

        The top Connection-section Delete Profile button operates on the
        explicit Profile ID field, not the Profile Manager tree selection.
        """
        if self.is_running:
            messagebox.showwarning(
                "Bot running",
                "Stop the bot before deleting a profile.",
                parent=self.root,
            )
            return
        profile = self._sanitize_profile_id(self.v_bot_id.get())
        self._delete_profile_by_id(profile)

    def _delete_selected_profile(self):
        """Delete the profile selected in the Profile Manager tree."""
        profile = self._selected_profile_id()
        self._delete_profile_by_id(profile)

    def _delete_profile_by_id(self, profile):
        """Safely delete a saved bot profile and its recovery state.

        Safety rules:
        - Never delete while any bot is running in this GUI.
        - Never delete a profile owned by another live process.
        - Never delete a profile with a runtime checkpoint that indicates a
          saved/open position or active Grid state.
        - BOT-01 also removes the legacy root config only after the same checks.
        - Trade/session database history is intentionally preserved.
        """
        if self.is_running:
            messagebox.showwarning(
                "Bot running",
                "Stop the bot before deleting a profile.",
                parent=self.root,
            )
            return

        profile = self._sanitize_profile_id(profile)

        if self._profile_lock_is_active(profile):
            messagebox.showerror(
                "Delete Profile",
                f"Profile {profile} is currently active in another bot process.\n\n"
                "Stop that bot first, then delete the profile.",
                parent=self.root,
            )
            return

        profile_dir = PROFILE_DIR / profile
        config_path = self._profile_config_path_only(profile)
        runtime_path = profile_dir / "runtime_state.json"
        runtime = self._read_json_file(runtime_path) or {}

        # A crash/recovery checkpoint is not automatically safe to delete.
        # Only a clearly flat/inactive checkpoint can be removed.
        status = str(runtime.get("status") or "").upper()
        position_state = runtime.get("position_state") or {}
        saved_position = position_state.get("last_protected_position")
        active_trade = position_state.get("active_trade")
        grid_state = runtime.get("grid_state") or {}
        grid_active = bool(grid_state.get("active"))
        filled_levels = grid_state.get("filled_levels") or []
        entry_orders = grid_state.get("entry_orders") or {}

        risky_statuses = {
            "RUNNING",
            "CRASHED",
            "STOPPING",
            "PAUSED_WITH_POSITION",
        }
        has_saved_position = bool(saved_position) or bool(active_trade)
        has_grid_state = (
            grid_active
            or bool(filled_levels)
            or bool(entry_orders)
            or bool(grid_state.get("tp_order_id"))
            or bool(grid_state.get("sl_order_id"))
        )

        if status in risky_statuses or has_saved_position or has_grid_state:
            messagebox.showerror(
                "Delete Profile BLOCKED",
                f"Profile {profile} has recovery/trading state that may represent "
                "an open or unverified exchange position/order.\n\n"
                f"Runtime status: {status or 'UNKNOWN'}\n"
                f"Saved position: {'YES' if has_saved_position else 'NO'}\n"
                f"Grid state: {'YES' if has_grid_state else 'NO'}\n\n"
                "For safety, the profile cannot be deleted until the bot is "
                "confirmed flat and its runtime state is safely stopped.",
                parent=self.root,
            )
            return

        has_profile_files = (
            config_path.exists()
            or runtime_path.exists()
            or profile_dir.exists()
        )
        legacy_path = Path(CONFIG_FILE) if profile == "BOT-01" else None
        has_legacy = bool(legacy_path and legacy_path.exists())

        if not has_profile_files and not has_legacy:
            messagebox.showinfo(
                "Delete Profile",
                f"No saved files were found for profile {profile}.",
                parent=self.root,
            )
            self._refresh_profile_list()
            return

        confirm = messagebox.askyesno(
            "Delete Profile?",
            f"Delete saved profile {profile}?\n\n"
            "This removes its saved configuration and recovery checkpoint.\n"
            "Trade/session history in the master database will NOT be deleted.\n\n"
            "This action cannot be undone.",
            parent=self.root,
        )
        if not confirm:
            return

        try:
            # Re-check the lock immediately before mutation.
            if self._profile_lock_is_active(profile):
                raise RuntimeError(
                    f"Profile {profile} became active before deletion."
                )

            removed = []
            if profile_dir.exists():
                shutil.rmtree(profile_dir)
                removed.append(str(profile_dir))

            # BOT-01 has backward-compatible legacy config storage.
            if legacy_path and legacy_path.exists():
                legacy_path.unlink()
                removed.append(str(legacy_path))

            # If the deleted profile was the current Profile ID, switch the
            # GUI to the first remaining saved profile.  Never leave a deleted
            # ID in the entry field while another profile is selected in the
            # manager tree.
            current_profile = self._sanitize_profile_id(self.bot_profile_id)
            current_field = self._sanitize_profile_id(self.v_bot_id.get())
            if current_profile == profile or current_field == profile:
                remaining = self._list_saved_profiles()
                next_profile = remaining[0] if remaining else "BOT-01"
                self.bot_profile_id = self._sanitize_profile_id(next_profile)
                self.v_bot_id.set(self.bot_profile_id)

            self._refresh_profile_list(select_profile=self.bot_profile_id)
            # If a remaining profile was selected, make the UI identity match
            # the tree selection exactly.
            selected_after = self._selected_profile_id()
            if selected_after and selected_after != self._sanitize_profile_id(self.v_bot_id.get()):
                self.v_bot_id.set(selected_after)
                self.bot_profile_id = selected_after
            self.log(
                f"PROFILE DELETED: {profile} | "
                f"Removed {len(removed)} profile file/location(s); "
                "master trade history preserved."
            )
            messagebox.showinfo(
                "Profile Deleted",
                f"Profile {profile} was deleted.\n\n"
                "Master trade/session history was preserved.",
                parent=self.root,
            )
        except Exception as e:
            self.log(f"PROFILE DELETE ERROR: {e}")
            messagebox.showerror(
                "Delete Profile",
                f"Could not delete profile {profile}:\n\n{e}",
                parent=self.root,
            )

    # -------------------- MASTER TRADE DATABASE ---------------

    def _init_master_db(self):
        try:
            with sqlite3.connect(MASTER_DB_FILE, timeout=30) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("""
                    CREATE TABLE IF NOT EXISTS bot_sessions (
                        session_id TEXT PRIMARY KEY,
                        bot_id TEXT,
                        started_at REAL,
                        ended_at REAL,
                        status TEXT,
                        exchange TEXT,
                        account_mode TEXT,
                        symbol TEXT,
                        timeframe TEXT,
                        strategy_mode TEXT,
                        strategy_modules TEXT,
                        resumed INTEGER,
                        start_balance REAL,
                        end_balance REAL,
                        net_pnl REAL,
                        notes TEXT
                    )
                """)
                db.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        trade_id TEXT PRIMARY KEY,
                        session_id TEXT,
                        bot_id TEXT,
                        exchange TEXT,
                        account_mode TEXT,
                        symbol TEXT,
                        timeframe TEXT,
                        strategy_mode TEXT,
                        grid_mode TEXT,
                        signal_mode TEXT,
                        strategy_modules TEXT,
                        side TEXT,
                        entry_price REAL,
                        exit_price REAL,
                        qty REAL,
                        leverage REAL,
                        sl REAL,
                        tp1 REAL,
                        tp2 REAL,
                        tp1_hit INTEGER,
                        result TEXT,
                        pnl REAL,
                        pnl_method TEXT,
                        started_at REAL,
                        ended_at REAL,
                        duration_sec REAL,
                        reason TEXT,
                        config_hash TEXT
                    )
                """)
                db.commit()
            self._export_master_csv()
        except Exception as e:
            self.log(f"MASTER DB INIT WARNING: {e}")

    def _db_session_start(self):
        try:
            with sqlite3.connect(MASTER_DB_FILE, timeout=30) as db:
                db.execute(
                    """INSERT OR REPLACE INTO bot_sessions
                    (session_id,bot_id,started_at,status,exchange,account_mode,
                     symbol,timeframe,strategy_mode,strategy_modules,resumed,
                     start_balance,end_balance,net_pnl,notes)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        self.session_id,
                        self._sanitize_profile_id(),
                        self.session_started_at,
                        "RUNNING",
                        self.exchange_id,
                        self.runtime_account_mode,
                        self.symbol,
                        self.runtime_timeframe,
                        self.runtime_strategy_mode,
                        self.runtime_strategy_modules,
                        int(self.runtime_resumed),
                        self.start_balance,
                        None,
                        0.0,
                        "Session started/resumed by Universal Futures Bot V8",
                    ),
                )
                db.commit()
        except Exception as e:
            self.log(f"MASTER DB SESSION START WARNING: {e}")
    def _db_session_end(self, status, end_balance=None, notes=""):
        try:
            with sqlite3.connect(MASTER_DB_FILE, timeout=30) as db:
                db.execute(
                    """UPDATE bot_sessions
                       SET ended_at=?, status=?, end_balance=?, net_pnl=?, notes=?
                       WHERE session_id=?""",
                    (
                        time.time(),
                        status,
                        end_balance,
                        (
                            (float(end_balance) - float(self.start_balance))
                            if end_balance is not None else None
                        ),
                        notes,
                        self.session_id,
                    ),
                )
                db.commit()
        except Exception as e:
            self.log(f"MASTER DB SESSION END WARNING: {e}")

    def _strategy_modules_for_log(self):
        modules = []
        checks = [
            ("Supertrend", "v_use_st"),
            ("EMA", "v_use_ema"),
            ("EMA Cross", "v_use_ema_cross"),
            ("MACD", "v_use_macd"),
            ("RSI", "v_use_rsi"),
            ("Bollinger", "v_use_bb"),
            ("Stochastic", "v_use_stoch"),
            ("VWAP", "v_use_vwap"),
            ("VWAP Delta", "v_use_vwap_delta"),
            ("Volumatic VIDYA", "v_use_vidya"),
            ("NWE", "v_use_nwe"),
            ("Liquidity Swings", "v_use_liq_swings"),
            ("Trendline Breakout", "v_use_trendline"),
            ("Multi-TF", "v_use_mtf"),
            ("Volume", "v_use_vol"),
            ("ADX", "v_use_adx"),
            ("ATR", "v_use_atr"),
        ]
        for label, attr in checks:
            try:
                if getattr(self, attr).get():
                    modules.append(label)
            except Exception:
                pass
        return ", ".join(modules) if modules else "None"

    def _db_trade_open(self, trade):
        try:
            with sqlite3.connect(MASTER_DB_FILE, timeout=30) as db:
                db.execute(
                    """INSERT OR REPLACE INTO trades
                    (trade_id,session_id,bot_id,exchange,account_mode,symbol,timeframe,
                     strategy_mode,grid_mode,signal_mode,strategy_modules,side,
                     entry_price,exit_price,qty,leverage,sl,tp1,tp2,tp1_hit,result,
                     pnl,pnl_method,started_at,ended_at,duration_sec,reason,config_hash)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        trade["trade_id"], self.session_id, self._sanitize_profile_id(),
                        self.exchange_id, self.runtime_account_mode, self.symbol,
                        self.runtime_timeframe, self.runtime_strategy_mode,
                        str(self.v_grid_mode.get()),
                        str(self.v_signal_mode.get()),
                        self.runtime_strategy_modules,
                        trade["side"], trade["entry"], None, trade["qty"],
                        float(trade.get("leverage") or 0.0),
                        None, None, None, 0, "OPEN", None, "PENDING",
                        trade["started_at"], None, None, None,
                        self.runtime_config_hash,
                    ),
                )
                db.commit()
        except Exception as e:
            self.log(f"MASTER DB TRADE OPEN WARNING: {e}")

    def _db_trade_close(self, trade, pnl, reason, balance_method):
        try:
            with sqlite3.connect(MASTER_DB_FILE, timeout=30) as db:
                db.execute(
                    """UPDATE trades SET
                       exit_price=?, tp1_hit=?, result=?, pnl=?, pnl_method=?,
                       ended_at=?, duration_sec=?, reason=?
                       WHERE trade_id=?""",
                    (
                        trade.get("exit_price"),
                        int(bool(trade.get("tp1_hit"))),
                        (
                            "WIN" if pnl > 0 else
                            "LOSS" if pnl < 0 else
                            "BREAKEVEN"
                        ),
                        pnl,
                        balance_method,
                        time.time(),
                        max(0.0, time.time() - float(trade.get("started_at") or time.time())),
                        reason,
                        trade.get("trade_id"),
                    ),
                )
                db.commit()
            self._export_master_csv()
        except Exception as e:
            self.log(f"MASTER DB TRADE CLOSE WARNING: {e}")

    def _export_master_csv(self):
        """Export the authoritative SQLite trade table to an Excel-compatible CSV."""
        lock_path = str(Path(MASTER_CSV_FILE).with_suffix(".export.lock"))
        fd = None
        try:
            deadline = time.time() + 5.0
            while True:
                try:
                    fd = os.open(
                        lock_path,
                        os.O_CREAT | os.O_EXCL | os.O_RDWR,
                    )
                    break
                except FileExistsError:
                    if time.time() >= deadline:
                        return
                    time.sleep(0.05)

            with sqlite3.connect(MASTER_DB_FILE, timeout=30) as db:
                df = pd.read_sql_query(
                    "SELECT * FROM trades ORDER BY started_at ASC",
                    db,
                )
            df.to_csv(MASTER_CSV_FILE, index=False)
        except Exception as e:
            self.log(f"MASTER CSV EXPORT WARNING: {e}")
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

    def _init_csv_log(self):
        if not os.path.exists(LOG_FILE):
            df = pd.DataFrame(
                columns=[
                    "Timestamp",
                    "Exchange",
                    "Symbol",
                    "Side",
                    "ActualEntry",
                    "Qty",
                    "SL",
                    "TP1",
                    "TP2",
                    "Notes",
                ]
            )
            df.to_csv(LOG_FILE, index=False)

    def log_trade_csv(
        self,
        timestamp,
        exchange,
        symbol,
        side,
        actual_entry,
        qty,
        sl,
        tp1,
        tp2,
        notes,
    ):
        row = pd.DataFrame(
            [[
                timestamp,
                exchange,
                symbol,
                side,
                actual_entry,
                qty,
                sl,
                tp1,
                tp2,
                notes,
            ]],
            columns=[
                "Timestamp",
                "Exchange",
                "Symbol",
                "Side",
                "ActualEntry",
                "Qty",
                "SL",
                "TP1",
                "TP2",
                "Notes",
            ],
        )
        row.to_csv(LOG_FILE, mode="a", header=False, index=False)

    def _scroll_log_to_bottom(self):
        """Keep the Execution Log pinned to its newest line."""
        try:
            self.log_box.update_idletasks()
            self.log_box.see(tk.END)
            self.log_box.yview_moveto(1.0)
        except Exception:
            pass

    def log(self, msg):
        def write():
            try:
                timestamp = time.strftime("[%H:%M:%S]")
                self.log_box.insert(tk.END, f"{timestamp} {msg}\n")

                if self.log_autoscroll:
                    # Scroll after Tk processes the insertion/layout.
                    self.root.after_idle(self._scroll_log_to_bottom)
                    self.root.after(30, self._scroll_log_to_bottom)
            except Exception:
                pass

        try:
            self.root.after(0, write)
        except Exception:
            pass


    def send_telegram(self, msg):
        if not self.v_tele_enable.get():
            return

        token = self.e_tele_token.get().strip()
        chat_id = self.e_tele_chat.get().strip()

        if not token or not chat_id:
            return

        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg},
                timeout=5,
            )
        except Exception:
            pass

    # -------------------- UI ---------------------------------

    def _build_ui(self):
        """Build the V8 interface.

        This method intentionally reorganizes presentation only.  All existing
        widget names, StringVar/BooleanVar objects, defaults, callbacks and
        configuration fields are preserved so the trading logic and saved
        settings remain compatible.
        """
        title = tk.Label(
            self.root,
            text=f"Universal Futures Trading Bot {APP_VERSION} - Multi-Exchange Futures",
            font=("Arial", 16, "bold"),
        )
        title.pack(pady=(6, 3))

        subtitle = tk.Label(
            self.root,
            text="Configuration • Strategy • Grid • Risk • Protection • Alerts",
            font=("Arial", 9),
            fg="#555555",
        )
        subtitle.pack(pady=(0, 4))

        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=8, pady=4)

        # Main settings area: a scrollable container holding clean tabs.
        settings_host = tk.Frame(main_frame)
        settings_host.pack(side="top", fill="both", expand=True)

        canvas = tk.Canvas(settings_host, highlightthickness=0)
        scrollbar = ttk.Scrollbar(settings_host, orient="vertical", command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _fit_scroll_width(_event=None):
            try:
                canvas.itemconfigure("all", width=max(1, canvas.winfo_width()))
            except Exception:
                pass

        canvas.bind("<Configure>", _fit_scroll_width)

        # Mouse-wheel scrolling over the settings area.
        def _wheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind_all("<MouseWheel>", _wheel)

        notebook = ttk.Notebook(self.scroll_frame)
        notebook.pack(fill="both", expand=True, padx=4, pady=2)

        self.tab_connection = ttk.Frame(notebook)
        self.tab_market = ttk.Frame(notebook)
        self.tab_strategy = ttk.Frame(notebook)
        self.tab_grid = ttk.Frame(notebook)
        self.tab_risk = ttk.Frame(notebook)
        self.tab_monitor = ttk.Frame(notebook)

        notebook.add(self.tab_connection, text="1 • Connection")
        notebook.add(self.tab_market, text="2 • Market")
        notebook.add(self.tab_strategy, text="3 • Strategy & Indicators")
        notebook.add(self.tab_grid, text="4 • Grid Trading")
        notebook.add(self.tab_risk, text="5 • Risk & SL/TP")
        notebook.add(self.tab_monitor, text="6 • Alerts & Dashboard")

        # Each tab gets a clean inner container so the existing controls can
        # keep their original grid geometry and all settings remain visible.
        for tab in (
            self.tab_connection,
            self.tab_market,
            self.tab_strategy,
            self.tab_grid,
            self.tab_risk,
            self.tab_monitor,
        ):
            tab.columnconfigure(0, weight=1)

        # Execution log stays permanently visible below the settings.
        right_frame = tk.LabelFrame(main_frame, text=" Execution Log ")
        right_frame.configure(height=185)
        right_frame.pack(side="bottom", fill="x", pady=(6, 0))
        right_frame.pack_propagate(False)

        log_text_frame = tk.Frame(right_frame)
        log_text_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_box = tk.Text(
            log_text_frame,
            height=9,
            bg="#111111",
            fg="#00ff66",
            font=("Consolas", 9),
            wrap="none",
        )
        self.log_scrollbar = ttk.Scrollbar(
            log_text_frame, orient="vertical", command=self.log_box.yview
        )
        self.log_box.configure(yscrollcommand=self.log_scrollbar.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        self.log_scrollbar.pack(side="right", fill="y")
        self.log_box.bind(
            "<Configure>",
            lambda _event: self.root.after_idle(self._scroll_log_to_bottom),
        )

        # 1. Exchange
        f_api = tk.LabelFrame(
            self.tab_connection,
            text=" 1. Exchange & API Credentials ",
        )
        f_api.pack(fill="x", padx=10, pady=5)

        tk.Label(f_api, text="Exchange:").grid(
            row=0, column=0, sticky="w"
        )

        self.v_exchange = tk.StringVar(value="bybit")
        ttk.OptionMenu(
            f_api,
            self.v_exchange,
            "bybit",
            "bybit",
            "binance",
            "gate",
            "bitget",
            "weex",
        ).grid(row=0, column=1, padx=5, pady=2, sticky="w")

        tk.Label(f_api, text="API Key:").grid(
            row=1, column=0, sticky="w"
        )
        self.e_api_key = tk.Entry(
            f_api,
            width=55,
            show="*",
        )
        self.e_api_key.grid(
            row=1, column=1, padx=5, pady=2
        )

        tk.Label(f_api, text="API Secret:").grid(
            row=2, column=0, sticky="w"
        )
        self.e_api_secret = tk.Entry(
            f_api,
            width=55,
            show="*",
        )
        self.e_api_secret.grid(
            row=2, column=1, padx=5, pady=2
        )

        tk.Label(f_api, text="Account Mode:").grid(
            row=3, column=0, sticky="w"
        )

        self.v_account_mode = tk.StringVar(value="BYBIT_DEMO")

        ttk.OptionMenu(
            f_api,
            self.v_account_mode,
            "BYBIT_DEMO",
            "BYBIT_DEMO",
            "BYBIT_TESTNET",
            "DEMO",
            "TESTNET",
            "LIVE",
        ).grid(
            row=3,
            column=1,
            padx=5,
            pady=2,
            sticky="w",
        )

        tk.Label(f_api, text="Bot Profile ID:").grid(
            row=4, column=0, sticky="w"
        )
        self.v_bot_id = tk.StringVar(value=self.bot_profile_id)
        self.e_bot_id = tk.Entry(f_api, textvariable=self.v_bot_id, width=20)
        self.e_bot_id.grid(row=4, column=1, padx=5, pady=2, sticky="w")
        ttk.Button(
            f_api,
            text="Load Profile ID",
            command=self.load_profile_from_ui,
        ).grid(row=4, column=2, padx=4, pady=2, sticky="w")
        ttk.Button(
            f_api,
            text="Save Profile",
            command=self.save_settings,
        ).grid(row=4, column=3, padx=4, pady=2, sticky="w")
        ttk.Button(
            f_api,
            text="Delete Profile ID",
            command=self._delete_current_profile,
        ).grid(row=4, column=4, padx=4, pady=2, sticky="w")

        tk.Label(
            f_api,
            text=(
                "Use a unique Profile ID for every simultaneous bot. "
                "Recovery state and settings are isolated per profile."
            ),
            fg="#555555",
        ).grid(
            row=5,
            column=0,
            columnspan=6,
            sticky="w",
        )

        # ---------------- PROFILE MANAGER ----------------
        # Shows every saved bot profile in one place and a full safe-details
        # panel for the selected profile. This makes copying BOT-01 to another
        # pair a configuration operation instead of manual re-entry.
        f_profiles = tk.LabelFrame(
            self.tab_connection,
            text=" Saved Bot Profiles / Copy & Details ",
        )
        f_profiles.pack(fill="both", expand=True, padx=10, pady=5)

        profile_buttons = tk.Frame(f_profiles)
        profile_buttons.pack(fill="x", padx=5, pady=(4, 2))

        ttk.Button(
            profile_buttons,
            text="Refresh Profiles",
            command=self._refresh_profile_list,
        ).pack(side="left", padx=2)

        ttk.Button(
            profile_buttons,
            text="Load Selected",
            command=self._load_selected_profile,
        ).pack(side="left", padx=2)

        ttk.Button(
            profile_buttons,
            text="Copy Selected Profile",
            command=self._copy_selected_profile,
        ).pack(side="left", padx=2)
        ttk.Button(
            profile_buttons,
            text="Delete Selected",
            command=self._delete_selected_profile,
        ).pack(side="left", padx=2)

        tk.Label(
            profile_buttons,
            text="Copy keeps strategy/risk/Grid/exchange settings and credentials; edit Pair, Qty/Risk and Leverage afterward.",
            fg="#555555",
        ).pack(side="left", padx=8)

        profile_tree_frame = tk.Frame(f_profiles)
        profile_tree_frame.pack(fill="x", padx=5, pady=2)

        profile_columns = (
            "profile", "exchange", "account", "symbol", "timeframe",
            "leverage", "mode", "qty", "grid", "status", "updated",
        )
        self.profile_tree = ttk.Treeview(
            profile_tree_frame,
            columns=profile_columns,
            show="headings",
            height=7,
            selectmode="browse",
        )
        headings = {
            "profile": "Profile", "exchange": "Exchange", "account": "Account",
            "symbol": "Pair", "timeframe": "TF", "leverage": "Lev",
            "mode": "Mode", "qty": "Qty / Risk", "grid": "Grid",
            "status": "Status", "updated": "Last Update",
        }
        widths = {
            "profile": 90, "exchange": 75, "account": 105, "symbol": 105,
            "timeframe": 45, "leverage": 45, "mode": 120, "qty": 105,
            "grid": 105, "status": 105, "updated": 145,
        }
        for col in profile_columns:
            self.profile_tree.heading(col, text=headings[col])
            self.profile_tree.column(col, width=widths[col], minwidth=45, anchor="w")
        profile_scroll = ttk.Scrollbar(
            profile_tree_frame, orient="horizontal", command=self.profile_tree.xview
        )
        self.profile_tree.configure(xscrollcommand=profile_scroll.set)
        self.profile_tree.pack(fill="x", expand=True)
        profile_scroll.pack(fill="x")
        self.profile_tree.bind("<<TreeviewSelect>>", self._show_selected_profile_details)
        self.profile_tree.bind("<Double-1>", lambda _e: self._load_selected_profile())

        details_label = tk.Label(
            f_profiles,
            text="Selected Profile Details (API key/secret and Telegram token are masked):",
            anchor="w",
        )
        details_label.pack(fill="x", padx=5, pady=(4, 1))
        self.profile_details = tk.Text(
            f_profiles,
            height=12,
            width=120,
            wrap="none",
            font=("Consolas", 8),
            bg="#f7f7f7",
        )
        self.profile_details.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        self.profile_details.configure(state="disabled")

        # 2. Market
        f_market = tk.LabelFrame(
            self.tab_market,
            text=" 2. Market & Execution ",
        )
        f_market.pack(fill="x", padx=10, pady=5)

        tk.Label(
            f_market,
            text="Symbol:",
        ).grid(row=0, column=0, sticky="w")

        self.e_symbol = tk.Entry(
            f_market,
            width=15,
        )
        self.e_symbol.insert(0, "BTC/USDT")
        self.e_symbol.grid(row=0, column=1, padx=5)

        tk.Label(
            f_market,
            text="Timeframe:",
        ).grid(row=0, column=2, sticky="w")

        self.v_tf = tk.StringVar(value="15m")
        ttk.OptionMenu(
            f_market,
            self.v_tf,
            "15m",
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "45m",
            "1h",
            "4h",
        ).grid(row=0, column=3, padx=5)

        tk.Label(
            f_market,
            text="Leverage:",
        ).grid(row=0, column=4, sticky="w")

        self.e_lev = tk.Entry(
            f_market,
            width=7,
        )
        self.e_lev.insert(0, "5")
        self.e_lev.grid(row=0, column=5, padx=5)

        tk.Label(f_market, text="Max Trades:").grid(row=1, column=0, sticky="w")
        self.e_max_trades = tk.Entry(f_market, width=8)
        self.e_max_trades.insert(0, "10")
        self.e_max_trades.grid(row=1, column=1, padx=5, sticky="w")
        tk.Label(f_market, text="0 = Unlimited").grid(row=1, column=2, sticky="w")
        tk.Label(f_market, text="Estimated Window:").grid(row=1, column=3, sticky="e")
        self.lbl_est_time = tk.Label(f_market, text="10 min", font=("Arial", 9, "bold"))
        self.lbl_est_time.grid(row=1, column=4, columnspan=2, padx=5, sticky="w")
        self.v_no_same_candle = tk.BooleanVar(value=True)
        tk.Checkbutton(f_market, text="Safety: No Re-Entry Same Candle", variable=self.v_no_same_candle).grid(row=2, column=0, columnspan=3, sticky="w")
        tk.Label(f_market, text="Prevents instant re-entry after SL/TP/reversal.", fg="#444444").grid(row=2, column=3, columnspan=3, sticky="w")
        tk.Label(f_market, text="Cooldown (min):").grid(row=3, column=0, sticky="w")
        self.e_cooldown_min = tk.Entry(f_market, width=6)
        self.e_cooldown_min.insert(0, "0")
        self.e_cooldown_min.grid(row=3, column=1, padx=5, sticky="w")
        tk.Label(f_market, text="0 = OFF", fg="#444444").grid(row=3, column=2, sticky="w")
        self.v_require_opposite_after_exit = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_market,
            text="Safety: After SL, Require Opposite Signal",
            variable=self.v_require_opposite_after_exit,
        ).grid(row=4, column=0, columnspan=3, sticky="w")
        tk.Label(
            f_market,
            text="After SL/BE stop, block same-direction re-entry until a valid opposite signal appears.",
            fg="#444444",
        ).grid(row=4, column=3, columnspan=4, sticky="w")

        self.e_max_trades.bind("<KeyRelease>", lambda _e: self.update_estimated_window())
        self.v_tf.trace_add("write", lambda *_args: self.update_estimated_window())

        # 3. Strategy
        f_strat = tk.LabelFrame(
            self.tab_strategy,
            text=" 3. Strategy & Indicators ",
        )
        f_strat.pack(fill="x", padx=10, pady=5)

        self.v_use_st = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat,
            text="Supertrend",
            variable=self.v_use_st,
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            f_strat,
            text="ATR Period:",
        ).grid(row=0, column=1, sticky="e")
        self.e_st_len = tk.Entry(
            f_strat,
            width=6,
        )
        self.e_st_len.insert(0, "10")
        self.e_st_len.grid(row=0, column=2, padx=2)

        tk.Label(
            f_strat,
            text="ATR Mult:",
        ).grid(row=0, column=3, sticky="e")
        self.e_st_mult = tk.Entry(
            f_strat,
            width=6,
        )
        # TradingView screenshot supplied by the user uses 2.0.
        self.e_st_mult.insert(0, "2.0")
        self.e_st_mult.grid(row=0, column=4, padx=2)

        tk.Label(
            f_strat,
            text="Source:",
        ).grid(row=0, column=5, sticky="e")
        self.v_st_source = tk.StringVar(value="CLOSE")
        ttk.OptionMenu(
            f_strat,
            self.v_st_source,
            "CLOSE",
            "CLOSE",
            "HL2",
        ).grid(row=0, column=6, padx=2, sticky="w")

        tk.Label(
            f_strat,
            text="ST Entry:",
        ).grid(row=1, column=3, sticky="e")
        self.v_st_entry_mode = tk.StringVar(value="FRESH_FLIP")
        ttk.OptionMenu(
            f_strat,
            self.v_st_entry_mode,
            "FRESH_FLIP",
            "FRESH_FLIP",
            "CURRENT_TREND",
        ).grid(row=1, column=4, padx=5, sticky="w")

        self.v_st_change_atr = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat,
            text="Change ATR Calculation Method ? (ON=RMA, OFF=SMA)",
            variable=self.v_st_change_atr,
        ).grid(row=1, column=5, columnspan=3, sticky="w")

        self.v_use_ema = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat,
            text="EMA Filter",
            variable=self.v_use_ema,
        ).grid(row=1, column=0, sticky="w")

        self.e_ema_len = tk.Entry(
            f_strat,
            width=6,
        )
        self.e_ema_len.insert(0, "200")
        self.e_ema_len.grid(row=1, column=1, padx=2)

        # Optional EMA 9/20 crossover filter.
        # This is independent of the existing EMA Filter above.
        self.v_use_ema_cross = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="EMA 9/20 Crossover Filter",
            variable=self.v_use_ema_cross,
        ).grid(row=2, column=0, sticky="w")

        tk.Label(
            f_strat,
            text="Fast:",
        ).grid(row=2, column=1, sticky="e")

        self.e_ema_fast = tk.Entry(
            f_strat,
            width=6,
        )
        self.e_ema_fast.insert(0, "9")
        self.e_ema_fast.grid(row=2, column=2, padx=2)

        tk.Label(
            f_strat,
            text="Slow:",
        ).grid(row=2, column=3, sticky="e")

        self.e_ema_slow = tk.Entry(
            f_strat,
            width=6,
        )
        self.e_ema_slow.insert(0, "20")
        self.e_ema_slow.grid(row=2, column=4, padx=2)

        tk.Label(
            f_strat,
            text="Entry:",
        ).grid(row=2, column=5, sticky="e")
        self.v_ema_cross_entry_mode = tk.StringVar(value="FRESH_CROSS")
        ttk.OptionMenu(
            f_strat,
            self.v_ema_cross_entry_mode,
            "FRESH_CROSS",
            "FRESH_CROSS",
            "CURRENT_TREND",
        ).grid(row=2, column=6, columnspan=2, padx=2, sticky="w")

        # Optional MACD fresh crossover filter.
        self.v_use_macd = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="MACD Crossover Filter",
            variable=self.v_use_macd,
        ).grid(row=3, column=0, sticky="w")

        tk.Label(
            f_strat,
            text="Fast/Slow/Signal:",
        ).grid(row=3, column=1, sticky="e")

        self.e_macd_fast = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_macd_fast.insert(0, "12")
        self.e_macd_fast.grid(row=3, column=2, padx=2)

        self.e_macd_slow = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_macd_slow.insert(0, "26")
        self.e_macd_slow.grid(row=3, column=3, padx=2)

        self.e_macd_signal = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_macd_signal.insert(0, "9")
        self.e_macd_signal.grid(row=3, column=4, padx=2)

        # RSI filter: reversal zones or fresh RSI/MA crossover.
        self.v_use_rsi = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat, text="RSI Filter", variable=self.v_use_rsi
        ).grid(row=4, column=0, sticky="w")
        tk.Label(f_strat, text="Period:").grid(row=4, column=1, sticky="e")
        self.e_rsi_len = tk.Entry(f_strat, width=5)
        self.e_rsi_len.insert(0, "14")
        self.e_rsi_len.grid(row=4, column=2, padx=2)
        tk.Label(f_strat, text="OB:").grid(row=4, column=3, sticky="e")
        self.e_rsi_ob = tk.Entry(f_strat, width=5)
        self.e_rsi_ob.insert(0, "80")
        self.e_rsi_ob.grid(row=4, column=4, padx=2)
        tk.Label(f_strat, text="OS:").grid(row=4, column=5, sticky="e")
        self.e_rsi_os = tk.Entry(f_strat, width=5)
        self.e_rsi_os.insert(0, "20")
        self.e_rsi_os.grid(row=4, column=6, padx=2)

        tk.Label(f_strat, text="RSI Logic:").grid(row=5, column=0, sticky="w")
        self.v_rsi_logic = tk.StringVar(value="REVERSAL_ZONE")
        ttk.OptionMenu(
            f_strat, self.v_rsi_logic, "REVERSAL_ZONE",
            "REVERSAL_ZONE", "CROSS_MA", "EITHER"
        ).grid(row=5, column=1, padx=2, sticky="w")
        tk.Label(f_strat, text="MA Type:").grid(row=5, column=2, sticky="e")
        self.v_rsi_ma_type = tk.StringVar(value="EMA")
        ttk.OptionMenu(
            f_strat, self.v_rsi_ma_type, "EMA", "SMA", "EMA", "WMA"
        ).grid(row=5, column=3, padx=2, sticky="w")
        tk.Label(f_strat, text="MA Period:").grid(row=5, column=4, sticky="e")
        self.e_rsi_ma_len = tk.Entry(f_strat, width=5)
        self.e_rsi_ma_len.insert(0, "9")
        self.e_rsi_ma_len.grid(row=5, column=5, padx=2, sticky="w")
        tk.Label(f_strat, text="CROSS_MA = RSI crosses above/below MA").grid(
            row=5, column=6, padx=2, sticky="w"
        )

        # Optional Bollinger breakout filter.
        self.v_use_bb = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="Bollinger Breakout",
            variable=self.v_use_bb,
        ).grid(row=6, column=0, sticky="w")

        tk.Label(
            f_strat,
            text="Period:",
        ).grid(row=6, column=1, sticky="e")

        self.e_bb_len = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_bb_len.insert(0, "20")
        self.e_bb_len.grid(row=6, column=2, padx=2)

        tk.Label(
            f_strat,
            text="StdDev:",
        ).grid(row=6, column=3, sticky="e")

        self.e_bb_std = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_bb_std.insert(0, "2")
        self.e_bb_std.grid(row=6, column=4, padx=2)

        # Optional Stochastic fresh crossover filter.
        self.v_use_stoch = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="Stochastic Crossover",
            variable=self.v_use_stoch,
        ).grid(row=7, column=0, sticky="w")

        tk.Label(
            f_strat,
            text="K/D:",
        ).grid(row=7, column=1, sticky="e")

        self.e_stoch_k = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_stoch_k.insert(0, "14")
        self.e_stoch_k.grid(row=7, column=2, padx=2)

        self.e_stoch_smooth = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_stoch_smooth.insert(0, "3")
        self.e_stoch_smooth.grid(row=7, column=3, padx=2)

        self.e_stoch_d = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_stoch_d.insert(0, "3")
        self.e_stoch_d.grid(row=7, column=4, padx=2)

        # Optional rolling VWAP trend filter.
        self.v_use_vwap = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="VWAP Trend Filter",
            variable=self.v_use_vwap,
        ).grid(row=8, column=0, sticky="w")

        tk.Label(
            f_strat,
            text="Period:",
        ).grid(row=8, column=1, sticky="e")

        self.e_vwap_len = tk.Entry(
            f_strat,
            width=5,
        )
        self.e_vwap_len.insert(0, "50")
        self.e_vwap_len.grid(row=8, column=2, padx=2)

        self.v_use_vwap_delta = tk.BooleanVar(value=False)
        tk.Checkbutton(f_strat, text="VWAP Delta", variable=self.v_use_vwap_delta).grid(row=8, column=3, sticky="w")
        tk.Label(f_strat, text="Smooth:").grid(row=8, column=4, sticky="e")
        self.v_vwap_delta_smooth = tk.BooleanVar(value=False)
        tk.Checkbutton(f_strat, variable=self.v_vwap_delta_smooth).grid(row=8, column=5, sticky="w")
        tk.Label(f_strat, text="HMA:").grid(row=8, column=6, sticky="e")
        self.e_vwap_delta_smooth_len = tk.Entry(f_strat, width=5)
        self.e_vwap_delta_smooth_len.insert(0, "21")
        self.e_vwap_delta_smooth_len.grid(row=8, column=7, padx=2)

        tk.Label(f_strat, text="Baseline:").grid(row=9, column=3, sticky="e")
        self.e_vwap_delta_baseline = tk.Entry(f_strat, width=5)
        self.e_vwap_delta_baseline.insert(0, "50")
        self.e_vwap_delta_baseline.grid(row=9, column=4, padx=2)
        tk.Label(f_strat, text="Logic:").grid(row=9, column=5, sticky="e")
        self.v_vwap_delta_logic = tk.StringVar(value="CURRENT_TREND")
        ttk.OptionMenu(f_strat, self.v_vwap_delta_logic, "CURRENT_TREND", "CURRENT_TREND", "CROSS_BASELINE").grid(row=9, column=6, columnspan=2, sticky="w")

        self.v_use_vidya = tk.BooleanVar(value=False)
        tk.Checkbutton(f_strat, text="Volumatic VIDYA", variable=self.v_use_vidya).grid(row=10, column=3, sticky="w")
        tk.Label(f_strat, text="Length:").grid(row=10, column=4, sticky="e")
        self.e_vidya_len = tk.Entry(f_strat, width=5)
        self.e_vidya_len.insert(0, "10")
        self.e_vidya_len.grid(row=10, column=5, padx=2)
        tk.Label(f_strat, text="Momentum:").grid(row=10, column=6, sticky="e")
        self.e_vidya_momentum = tk.Entry(f_strat, width=5)
        self.e_vidya_momentum.insert(0, "20")
        self.e_vidya_momentum.grid(row=10, column=7, padx=2)

        tk.Label(f_strat, text="Band:").grid(row=11, column=3, sticky="e")
        self.e_vidya_band = tk.Entry(f_strat, width=5)
        self.e_vidya_band.insert(0, "2")
        self.e_vidya_band.grid(row=11, column=4, padx=2)
        tk.Label(f_strat, text="Entry:").grid(row=11, column=5, sticky="e")
        self.v_vidya_entry_mode = tk.StringVar(value="CURRENT_TREND")
        ttk.OptionMenu(f_strat, self.v_vidya_entry_mode, "CURRENT_TREND", "CURRENT_TREND", "FRESH_FLIP").grid(row=11, column=6, columnspan=2, sticky="w")

        # Optional LuxAlgo Nadaraya-Watson Envelope (NWE).
        # Trading uses the non-repainting/causal calculation by default.
        self.v_use_nwe = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="Nadaraya-Watson Envelope [LuxAlgo]",
            variable=self.v_use_nwe,
        ).grid(row=12, column=0, columnspan=2, sticky="w")

        tk.Label(f_strat, text="Bandwidth:").grid(row=12, column=2, sticky="e")
        self.e_nwe_bandwidth = tk.Entry(f_strat, width=5)
        self.e_nwe_bandwidth.insert(0, "8")
        self.e_nwe_bandwidth.grid(row=12, column=3, padx=2)

        tk.Label(f_strat, text="Mult:").grid(row=12, column=4, sticky="e")
        self.e_nwe_mult = tk.Entry(f_strat, width=5)
        self.e_nwe_mult.insert(0, "3")
        self.e_nwe_mult.grid(row=12, column=5, padx=2)

        tk.Label(f_strat, text="Entry:").grid(row=12, column=6, sticky="e")
        self.v_nwe_entry_mode = tk.StringVar(value="FRESH_CROSS")
        ttk.OptionMenu(            f_strat, self.v_nwe_entry_mode, "FRESH_CROSS",
            "FRESH_CROSS", "CURRENT_TREND"
        ).grid(row=12, column=7, padx=2, sticky="w")

        tk.Label(f_strat, text="NWE Mode:").grid(row=13, column=2, sticky="e")
        self.v_nwe_repaint = tk.BooleanVar(value=False)
        self.nwe_repaint_check = tk.Checkbutton(
            f_strat,
            variable=self.v_nwe_repaint,
            text="Non-Repainting (fixed)",
            state=tk.DISABLED,
        )
        self.nwe_repaint_check.grid(row=13, column=3, columnspan=3, sticky="w")
        tk.Label(
            f_strat,
            text="NWE is always causal/non-repainting; only completed candles and past data are used.",
            fg="#444444",
        ).grid(row=13, column=6, columnspan=2, sticky="w")

        # Optional ATR volatility filter using the ATR already calculated
        # by the Supertrend engine. Requires ATR/close >= threshold.
        self.v_use_atr = tk.BooleanVar(value=DEFAULT_USE_ATR)
        tk.Checkbutton(
            f_strat,
            text="ATR Volatility Filter",
            variable=self.v_use_atr,
        ).grid(row=14, column=0, sticky="w")
        tk.Label(f_strat, text="Min ATR %:").grid(row=14, column=1, sticky="e")
        self.e_atr_min_pct = tk.Entry(f_strat, width=6)
        self.e_atr_min_pct.insert(0, "0.30")
        self.e_atr_min_pct.grid(row=14, column=2, padx=2)

        self.v_use_vol = tk.BooleanVar(value=DEFAULT_USE_VOLUME)
        tk.Checkbutton(
            f_strat, text="Vol Filter", variable=self.v_use_vol
        ).grid(row=15, column=0, sticky="w")
        self.e_vol_len = tk.Entry(f_strat, width=6)
        self.e_vol_len.insert(0, "20")
        self.e_vol_len.grid(row=15, column=1, padx=2)

        self.v_use_adx = tk.BooleanVar(value=DEFAULT_USE_ADX)
        tk.Checkbutton(
            f_strat, text="ADX Filter", variable=self.v_use_adx
        ).grid(row=16, column=0, sticky="w")
        self.e_adx_thresh = tk.Entry(f_strat, width=6)
        self.e_adx_thresh.insert(0, "20")
        self.e_adx_thresh.grid(row=16, column=1, padx=2)

        self.v_use_mtf = tk.BooleanVar(value=DEFAULT_USE_MTF)
        tk.Checkbutton(
            f_strat,
            text="Multi-TF (4h Confluence)",
            variable=self.v_use_mtf,
        ).grid(row=17, column=0, columnspan=2, sticky="w")

        # Confirmed-pivot Trendline Breakout module.
        # Dedicated rows prevent explanatory labels from covering the controls.
        tk.Label(
            f_strat,
            text="── Trendline Breakout ──",
            font=("Arial", 9, "bold"),
        ).grid(row=24, column=0, columnspan=8, sticky="w", pady=(6, 2))

        self.v_use_trendline = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="Trendline Breakout",
            variable=self.v_use_trendline,
        ).grid(row=25, column=0, columnspan=2, sticky="w")

        tk.Label(f_strat, text="Pivot Lookback:").grid(row=25, column=2, sticky="e")
        self.e_trendline_length = tk.Entry(f_strat, width=6)
        self.e_trendline_length.insert(0, "14")
        self.e_trendline_length.grid(row=25, column=3, padx=2)

        tk.Label(f_strat, text="Min Pivot Distance:").grid(row=25, column=4, sticky="e")
        self.e_trendline_min_distance = tk.Entry(f_strat, width=6)
        self.e_trendline_min_distance.insert(0, "5")
        self.e_trendline_min_distance.grid(row=25, column=5, padx=2)

        tk.Label(f_strat, text="Mode:").grid(row=25, column=6, sticky="e")
        self.v_trendline_entry_mode = tk.StringVar(value="FRESH_BREAK")
        ttk.OptionMenu(
            f_strat, self.v_trendline_entry_mode, "FRESH_BREAK",
            "FRESH_BREAK", "CURRENT_TREND", "BREAK_RETEST"
        ).grid(row=25, column=7, padx=2, sticky="w")

        tk.Label(f_strat, text="Breakout Buffer %:").grid(row=26, column=2, sticky="e")
        self.e_trendline_buffer = tk.Entry(f_strat, width=6)
        self.e_trendline_buffer.insert(0, "0")
        self.e_trendline_buffer.grid(row=26, column=3, padx=2)

        tk.Label(f_strat, text="Retest Candles:").grid(row=26, column=4, sticky="e")
        self.e_trendline_retest = tk.Entry(f_strat, width=6)
        self.e_trendline_retest.insert(0, "3")
        self.e_trendline_retest.grid(row=26, column=5, padx=2)

        tk.Label(
            f_strat,
            text="BUY = completed candle closes above descending resistance | SELL = completed candle closes below ascending support",
            fg="#444444",
        ).grid(row=27, column=0, columnspan=8, sticky="w", pady=1)

        tk.Label(
            f_strat,
            text="Confirmed pivots only; no look-ahead. FRESH_BREAK = new break | CURRENT_TREND = stay with break direction | BREAK_RETEST = break + retest.",
            fg="#444444",
        ).grid(row=28, column=0, columnspan=8, sticky="w", pady=(0, 2))

        tk.Label(
            f_strat,
            text="Liquidity Swings uses selected timeframe OHLCV and completed candles; its Pine Intrabar Precision option is not used.",
            fg="#666666",
        ).grid(row=29, column=0, columnspan=8, sticky="w")


        # Signal decision mode.
        # Kept below the Trendline Breakout block so the Strategy & Indicators
        # tab follows the requested visual order.
        self.v_signal_mode = tk.StringVar(value=DEFAULT_SIGNAL_MODE)
        tk.Label(f_strat, text="Signal Mode:").grid(row=31, column=0, sticky="w")
        ttk.OptionMenu(
            f_strat,
            self.v_signal_mode,
            "SINGLE_SIGNAL",
            "SINGLE_SIGNAL",
            "ANY_NON_CONFLICTING",
            "2_SIGNALS",
            "3_SIGNALS",
            "4_SIGNALS",
            "SCORE",
            "ADAPTIVE_SCORE",
            "ADAPTIVE_EVIDENCE",
            "STRICT_ALL_FILTERS",
        ).grid(row=31, column=1, padx=5, sticky="w")
        tk.Label(
            f_strat,
            text="ANY_NON_CONFLICTING: any enabled module may trigger; BUY/SELL conflicts are blocked.",
            fg="#555555",
        ).grid(row=30, column=0, columnspan=8, sticky="w")

        tk.Label(f_strat, text="Score (SCORE mode):").grid(row=31, column=2, sticky="e")
        self.e_min_score = tk.Entry(f_strat, width=5)
        self.e_min_score.insert(0, "1")
        self.e_min_score.grid(row=31, column=3, padx=2)
        tk.Label(f_strat, text="Adaptive Edge:").grid(row=32, column=4, sticky="e")
        self.e_adaptive_edge = tk.Entry(f_strat, width=6)
        self.e_adaptive_edge.insert(0, DEFAULT_ADAPTIVE_EDGE)
        self.e_adaptive_edge.grid(row=32, column=5, padx=2)
        tk.Label(f_strat, text="Adaptive Min Weight:").grid(row=32, column=6, sticky="e")
        self.e_adaptive_min_weight = tk.Entry(f_strat, width=6)
        self.e_adaptive_min_weight.insert(0, DEFAULT_ADAPTIVE_MIN_WEIGHT)
        self.e_adaptive_min_weight.grid(row=32, column=7, padx=2)
        tk.Label(f_strat, text="Evidence Min Families:").grid(row=35, column=0, sticky="e")
        self.evidence_min_families = tk.Entry(f_strat, width=5)
        self.evidence_min_families.insert(0, str(EVIDENCE_DEFAULT_MIN_FAMILIES))
        self.evidence_min_families.grid(row=35, column=1, padx=2, sticky="w")
        tk.Label(f_strat, text="Family Evidence Min:").grid(row=35, column=2, sticky="e")
        self.evidence_family_min_score = tk.Entry(f_strat, width=6)
        self.evidence_family_min_score.insert(0, str(EVIDENCE_DEFAULT_FAMILY_MIN_SCORE))
        self.evidence_family_min_score.grid(row=35, column=3, padx=2, sticky="w")
        self.evidence_require_trend = tk.BooleanVar(value=EVIDENCE_DEFAULT_REQUIRE_TREND)
        tk.Checkbutton(f_strat, text="Require Trend Family", variable=self.evidence_require_trend).grid(row=35, column=4, sticky="w")
        self.evidence_require_independent = tk.BooleanVar(value=EVIDENCE_DEFAULT_REQUIRE_INDEPENDENT)
        tk.Checkbutton(f_strat, text="Require Independent Family", variable=self.evidence_require_independent).grid(row=35, column=6, columnspan=2, sticky="w")
        tk.Label(f_strat, text="Evidence: TREND | MOMENTUM | FLOW | STRUCTURE. ATR/ADX are regime gates and are not counted as directional evidence.", fg="#555555").grid(row=36, column=0, columnspan=8, sticky="w")

        self.v_hold_until_all_reverse = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat,
            text="Hold Position Until ALL Active Signals Reverse",
            variable=self.v_hold_until_all_reverse,
        ).grid(row=33, column=0, columnspan=4, sticky="w")

        tk.Label(
            f_strat,
            text="ON: open trade waits until every enabled directional module shows the opposite direction. OFF: normal reversal.",
            fg="#444444",
        ).grid(row=34, column=0, columnspan=8, sticky="w")

        tk.Label(
            f_strat,
            text=(
                "SINGLE_SIGNAL = any ONE enabled signal can trade; "
                "2/3/4_SIGNALS = required directional votes; SCORE = custom minimum votes; "
                "STRICT_ALL_FILTERS = original strict mode."
            ),
            fg="#444444",
        ).grid(row=35, column=0, columnspan=8, sticky="w", pady=3)

        # Optional LuxAlgo Liquidity Swings directional module.
        self.v_use_liq_swings = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="Liquidity Swings [LuxAlgo]",
            variable=self.v_use_liq_swings,
        ).grid(row=22, column=0, columnspan=2, sticky="w")

        tk.Label(f_strat, text="Pivot Lookback:").grid(row=22, column=2, sticky="e")
        self.e_liq_length = tk.Entry(f_strat, width=6)
        self.e_liq_length.insert(0, "14")
        self.e_liq_length.grid(row=22, column=3, padx=2)

        tk.Label(f_strat, text="Swing Area:").grid(row=22, column=4, sticky="e")
        self.v_liq_area = tk.StringVar(value="Wick Extremity")
        ttk.OptionMenu(
            f_strat,
            self.v_liq_area,
            "Wick Extremity",
            "Wick Extremity",
            "Full Range",
        ).grid(row=22, column=5, padx=2, sticky="w")

        tk.Label(f_strat, text="Filter:").grid(row=22, column=6, sticky="e")
        self.v_liq_filter = tk.StringVar(value="Count")
        ttk.OptionMenu(
            f_strat,
            self.v_liq_filter,
            "Count",
            "Count",
            "Volume",
        ).grid(row=22, column=7, padx=2, sticky="w")

        tk.Label(f_strat, text="Filter Value:").grid(row=23, column=2, sticky="e")
        self.e_liq_filter_value = tk.Entry(f_strat, width=6)
        self.e_liq_filter_value.insert(0, "0")
        self.e_liq_filter_value.grid(row=23, column=3, padx=2)

        tk.Label(f_strat, text="Entry:").grid(row=23, column=4, sticky="e")
        self.v_liq_entry_mode = tk.StringVar(value="FRESH_BREAK")
        ttk.OptionMenu(
            f_strat,
            self.v_liq_entry_mode,
            "FRESH_BREAK",
            "FRESH_BREAK",
            "CURRENT_TREND",
        ).grid(row=23, column=5, padx=2, sticky="w")


        # 3B. Advanced Divergence + Volume S/R modules
        adv = tk.LabelFrame(
            f_strat,
            text="── Advanced Strategy Modules: Divergence + Volume S/R Zones ──",
        )
        adv.grid(row=36, column=0, columnspan=10, sticky="ew", pady=(8, 3))

        self.v_use_divergence = tk.BooleanVar(value=False)
        tk.Checkbutton(adv, text="Divergence Engine", variable=self.v_use_divergence).grid(row=0, column=0, sticky="w")
        tk.Label(adv, text="Pivot:").grid(row=0, column=1, sticky="e")
        self.e_div_pivot = tk.Entry(adv, width=5); self.e_div_pivot.insert(0, "5"); self.e_div_pivot.grid(row=0, column=2)
        tk.Label(adv, text="Source:").grid(row=0, column=3, sticky="e")
        self.v_div_source = tk.StringVar(value="Close")
        ttk.OptionMenu(adv, self.v_div_source, "Close", "Close", "High/Low").grid(row=0, column=4, sticky="w")
        tk.Label(adv, text="Type:").grid(row=0, column=5, sticky="e")
        self.v_div_type = tk.StringVar(value="Regular")
        ttk.OptionMenu(adv, self.v_div_type, "Regular", "Regular", "Hidden", "Regular/Hidden").grid(row=0, column=6, sticky="w")
        tk.Label(adv, text="Min Div:").grid(row=0, column=7, sticky="e")
        self.e_div_min_count = tk.Entry(adv, width=5); self.e_div_min_count.insert(0, "1"); self.e_div_min_count.grid(row=0, column=8)
        tk.Label(adv, text="Max Pivots:").grid(row=0, column=9, sticky="e")
        self.e_div_max_pivots = tk.Entry(adv, width=5); self.e_div_max_pivots.insert(0, "10"); self.e_div_max_pivots.grid(row=0, column=10)

        tk.Label(adv, text="Max Bars:").grid(row=1, column=1, sticky="e")
        self.e_div_max_bars = tk.Entry(adv, width=5); self.e_div_max_bars.insert(0, "100"); self.e_div_max_bars.grid(row=1, column=2)
        tk.Label(adv, text="CCI:").grid(row=1, column=3, sticky="e")
        self.e_div_cci_len = tk.Entry(adv, width=5); self.e_div_cci_len.insert(0, "10"); self.e_div_cci_len.grid(row=1, column=4)
        tk.Label(adv, text="Momentum:").grid(row=1, column=5, sticky="e")
        self.e_div_mom_len = tk.Entry(adv, width=5); self.e_div_mom_len.insert(0, "10"); self.e_div_mom_len.grid(row=1, column=6)
        tk.Label(adv, text="Entry:").grid(row=1, column=7, sticky="e")
        self.v_div_entry_mode = tk.StringVar(value="FRESH")
        ttk.OptionMenu(adv, self.v_div_entry_mode, "FRESH", "FRESH", "CURRENT_STATE").grid(row=1, column=8, sticky="w")
        tk.Label(adv, text="Confirmed pivots only; no look-ahead.", fg="#555555").grid(row=1, column=9, columnspan=3, sticky="w")

        div_names = [
            ("div_use_macd","MACD"),("div_use_macd_hist","Hist"),("div_use_rsi","RSI"),
            ("div_use_stoch","Stoch"),("div_use_cci","CCI"),("div_use_momentum","MOM"),
            ("div_use_obv","OBV"),("div_use_vwmacd","VWMACD"),("div_use_cmf","CMF"),("div_use_mfi","MFI"),
        ]
        for j,(key,label) in enumerate(div_names):
            setattr(self, key, tk.BooleanVar(value=True))
            tk.Checkbutton(adv, text=label, variable=getattr(self,key)).grid(row=2+j//5, column=(j%5)*2, sticky="w")

        self.v_use_vol_sr = tk.BooleanVar(value=False)
        tk.Checkbutton(adv, text="Volume S/R Zones", variable=self.v_use_vol_sr).grid(row=4, column=0, sticky="w")
        tk.Label(adv, text="Vote:").grid(row=4, column=1, sticky="e")
        self.v_sr_vote_mode = tk.StringVar(value="MAJORITY")
        ttk.OptionMenu(adv, self.v_sr_vote_mode, "MAJORITY", "MAJORITY", "ANY", "ALL").grid(row=4, column=2, sticky="w")
        tk.Label(adv, text="Entry:").grid(row=4, column=3, sticky="e")
        self.v_sr_entry_mode = tk.StringVar(value="CURRENT_ZONE")
        ttk.OptionMenu(adv, self.v_sr_entry_mode, "CURRENT_ZONE", "CURRENT_ZONE", "FRESH_BREAK").grid(row=4, column=4, sticky="w")
        tk.Label(adv, text="Vol MA threshold:").grid(row=4, column=5, sticky="e")
        self.e_sr_volume_ma = tk.Entry(adv, width=5); self.e_sr_volume_ma.insert(0, "6"); self.e_sr_volume_ma.grid(row=4, column=6)

        for idx, (attr, label, default) in enumerate([
            ("sr_tf1","TF1","Chart"),("sr_tf2","TF2","4h"),("sr_tf3","TF3","D"),("sr_tf4","TF4","W")
        ]):
            tk.Label(adv, text=label).grid(row=5, column=idx*3, sticky="e")
            setattr(self, "v_"+attr, tk.StringVar(value=default))
            ttk.OptionMenu(adv, getattr(self, "v_"+attr), default, "Chart","4h","D","W","1h","15m","30m","Disable").grid(row=5, column=idx*3+1, sticky="w")
        tk.Label(
            adv,
            text="V2 parity: volume-confirmed 5-bar fractal S/R zones; chart-only lines/labels are represented as numerical levels/votes for trading and backtesting.",
            fg="#555555",
        ).grid(row=6, column=0, columnspan=12, sticky="w", pady=2)

        # 4. Grid Trading Engine
        f_grid = tk.LabelFrame(self.tab_grid, text=" 4. Grid Trading Engine ")
        f_grid.pack(fill="x", padx=10, pady=5)

        tk.Label(f_grid, text="Grid Mode:").grid(row=0, column=0, sticky="w")
        self.v_grid_mode = tk.StringVar(value=DEFAULT_GRID_MODE)
        ttk.OptionMenu(f_grid, self.v_grid_mode, "OFF", "OFF", "DIRECT_SHOT", "LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID").grid(row=0, column=1, padx=5, sticky="w")
        tk.Label(f_grid, text="Grid Levels:").grid(row=0, column=2, sticky="e")
        self.e_grid_levels = tk.Entry(f_grid, width=6); self.e_grid_levels.insert(0, "5"); self.e_grid_levels.grid(row=0, column=3, padx=3)
        tk.Label(f_grid, text="Spacing %:").grid(row=0, column=4, sticky="e")
        self.e_grid_spacing = tk.Entry(f_grid, width=7); self.e_grid_spacing.insert(0, "1.0"); self.e_grid_spacing.grid(row=0, column=5, padx=3)

        tk.Label(f_grid, text="Order Size USDT:").grid(row=1, column=0, sticky="w")
        self.e_grid_order_size = tk.Entry(f_grid, width=8); self.e_grid_order_size.insert(0, "10"); self.e_grid_order_size.grid(row=1, column=1, padx=5, sticky="w")
        tk.Label(f_grid, text="Size Increase %:").grid(row=1, column=2, sticky="e")
        self.e_grid_size_increase = tk.Entry(f_grid, width=7); self.e_grid_size_increase.insert(0, "0"); self.e_grid_size_increase.grid(row=1, column=3, padx=3)
        tk.Label(f_grid, text="Grid TP %:").grid(row=1, column=4, sticky="e")
        self.e_grid_tp = tk.Entry(f_grid, width=7); self.e_grid_tp.insert(0, "1.0"); self.e_grid_tp.grid(row=1, column=5, padx=3)

        tk.Label(f_grid, text="Global Grid SL %:").grid(row=2, column=0, sticky="w")
        self.e_grid_sl = tk.Entry(f_grid, width=7); self.e_grid_sl.insert(0, "6.0"); self.e_grid_sl.grid(row=2, column=1, padx=5, sticky="w")
        tk.Label(f_grid, text="Max Exposure USDT:").grid(row=2, column=2, sticky="e")
        self.e_grid_max_exposure = tk.Entry(f_grid, width=9); self.e_grid_max_exposure.insert(0, "100"); self.e_grid_max_exposure.grid(row=2, column=3, padx=3)
        tk.Label(f_grid, text="Max Grid DD %:").grid(row=2, column=4, sticky="e")
        self.e_grid_max_dd = tk.Entry(f_grid, width=7); self.e_grid_max_dd.insert(0, "3.0"); self.e_grid_max_dd.grid(row=2, column=5, padx=3)

        tk.Label(f_grid, text="Trend Filter:").grid(row=3, column=0, sticky="w")
        self.v_grid_trend_filter = tk.StringVar(value="OFF")
        ttk.OptionMenu(f_grid, self.v_grid_trend_filter, "OFF", "OFF", "SUPERTREND", "SCORE").grid(row=3, column=1, padx=5, sticky="w")

        tk.Label(f_grid, text="Grid Score Min:").grid(row=3, column=2, sticky="e")
        self.e_grid_score_min = tk.Entry(f_grid, width=7)
        self.e_grid_score_min.insert(0, "1")
        self.e_grid_score_min.grid(row=3, column=3, padx=3, sticky="w")

        tk.Label(f_grid, text="Recenter:").grid(row=3, column=4, sticky="e")
        self.v_grid_recenter = tk.BooleanVar(value=False)
        tk.Checkbutton(f_grid, text="ON", variable=self.v_grid_recenter).grid(row=3, column=5, sticky="w")

        tk.Label(f_grid, text="Recenter Distance %:").grid(row=4, column=0, sticky="w")
        self.e_grid_recenter = tk.Entry(f_grid, width=7)
        self.e_grid_recenter.insert(0, "3.0")
        self.e_grid_recenter.grid(row=4, column=1, padx=5, sticky="w")

        tk.Label(f_grid, text="Cooldown After Grid Stop (min):").grid(row=4, column=2, sticky="e")
        self.e_grid_cooldown = tk.Entry(f_grid, width=7)
        self.e_grid_cooldown.insert(0, "30")
        self.e_grid_cooldown.grid(row=4, column=3, padx=3, sticky="w")

        tk.Label(
            f_grid,
            text="GRID RISK IS INDEPENDENT: Grid Order Size, Size Increase, Grid TP, Global Grid SL, Max Exposure and Max Grid DD are used by the Grid engine. Section 5 Risk Per Trade / Fixed Qty and Section 6 normal Strategy SL/TP are NOT used for Grid entries. Section 5 Max Daily Drawdown and Emergency Capital Loss Stop remain GLOBAL account safety limits and can stop/flatten Grid trading.",
            fg="#444444",
            wraplength=1100,
            justify="left",
        ).grid(row=5, column=0, columnspan=8, sticky="w", pady=2)

        tk.Label(
            f_grid,
            text="SCORE = ALL enabled Section 3 Strategy indicators (ST, EMA, EMA Cross, MACD, RSI, BB, STOCH, VWAP, VWAP Delta, VIDYA, NWE, Liquidity, Trendline, MTF, Volume, ADX, ATR), using their Section 3 parameters and completed-candle logic. NEUTRAL_GRID is AUTO-DIRECTION only: Trend Filter=SUPERTREND follows Supertrend; Trend Filter=SCORE follows all enabled Section 3 indicator votes; Trend Filter=OFF also uses the complete Section 3 score as the automatic direction source. With Min=1, one enabled bullish/bearish vote can authorize that direction, but a tie (for example 1-vs-1) blocks new entries. On a direction change, pending old-side Grid entries are cancelled; an opposite open Grid position is safely closed and the new side is rebuilt. LONG_GRID and SHORT_GRID are unchanged.",
            fg="#444444",
            wraplength=1100,
            justify="left",
        ).grid(row=6, column=0, columnspan=8, sticky="w", pady=2)

        # 5. Risk
        f_risk = tk.LabelFrame(
            self.tab_risk,
            text=" 5. Dynamic Risk & Sizing ",
        )
        f_risk.pack(fill="x", padx=10, pady=5)

        tk.Label(
            f_risk,
            text="Sizing Mode (NORMAL STRATEGY ONLY):",
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            f_risk,
            text="GLOBAL SAFETY: Max Daily Drawdown + Emergency Capital Loss Stop apply to BOTH Normal Strategy and Grid.",
            fg="#444444",
            wraplength=1100,
            justify="left",
        ).grid(row=3, column=0, columnspan=6, sticky="w", pady=(3, 0))

        self.v_size_mode = tk.StringVar(value=DEFAULT_RISK_MODE)

        ttk.OptionMenu(
            f_risk,
            self.v_size_mode,
            "EQUITY_RISK_%",
            "EQUITY_RISK_%",
            "FIXED_QTY",
        ).grid(row=0, column=1, padx=5)

        tk.Label(
            f_risk,
            text="Risk Per Trade (%):",
        ).grid(row=0, column=2, sticky="w")

        self.e_risk_pct = tk.Entry(
            f_risk,
            width=8,
        )
        self.e_risk_pct.insert(0, DEFAULT_RISK_PER_TRADE)
        self.e_risk_pct.grid(row=0, column=3, padx=5)

        tk.Label(
            f_risk,
            text="Fixed Qty:",
        ).grid(row=0, column=4, sticky="w")

        self.e_fixed_qty = tk.Entry(
            f_risk,
            width=10,
        )
        self.e_fixed_qty.insert(0, "0.001")
        self.e_fixed_qty.grid(row=0, column=5, padx=5)

        tk.Label(
            f_risk,
            text="Max Daily Drawdown (%):",
        ).grid(row=1, column=0, sticky="w")

        self.e_max_dd = tk.Entry(
            f_risk,
            width=8,
        )
        self.e_max_dd.insert(0, "5.0")
        self.e_max_dd.grid(row=1, column=1, padx=5)

        tk.Label(f_risk, text="Emergency Capital Loss Stop (%):").grid(row=2, column=0, sticky="w")
        self.e_emergency_capital_pct = tk.Entry(f_risk, width=8)
        self.e_emergency_capital_pct.insert(0, "30.0")
        self.e_emergency_capital_pct.grid(row=2, column=1, padx=5)
        tk.Label(f_risk, text="Emergency Scope:").grid(row=2, column=2, sticky="e")
        self.v_emergency_scope = tk.StringVar(value="BOT_SYMBOL")
        ttk.OptionMenu(f_risk, self.v_emergency_scope, "BOT_SYMBOL", "BOT_SYMBOL", "ALL_ACCOUNT").grid(row=2, column=3, padx=5, sticky="w")
        tk.Label(f_risk, text="BOT_SYMBOL is the safe default; ALL_ACCOUNT is an explicit account-wide kill switch.").grid(row=2, column=4, columnspan=2, sticky="w")

        # 5. SL/TP
        f_sltp = tk.LabelFrame(
            self.tab_risk,
            text=" 6. Stop Loss & Take Profit Protection ",
        )
        f_sltp.pack(fill="x", padx=10, pady=5)

        tk.Label(
            f_sltp,
            text="NORMAL STRATEGY SL/TP ONLY — NOT USED BY GRID",
            font=("Arial", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        tk.Label(f_sltp, text="SL Mode:").grid(row=0, column=2, sticky="w")
        self.v_sl_mode = tk.StringVar(value="PRICE_%")
        ttk.OptionMenu(f_sltp, self.v_sl_mode, "PRICE_%", "PRICE_%", "ROI_%").grid(row=0, column=3, padx=5, sticky="w")

        tk.Label(f_sltp, text="TP Mode:").grid(row=0, column=4, sticky="w")
        self.v_tp_mode = tk.StringVar(value="ROI_%")
        ttk.OptionMenu(f_sltp, self.v_tp_mode, "ROI_%", "PRICE_%", "ROI_%").grid(row=0, column=5, padx=5, sticky="w")

        tk.Label(
            f_sltp,
            text="SL Target (%):",
        ).grid(row=1, column=0, sticky="w")

        self.e_sl_pct = tk.Entry(
            f_sltp,
            width=8,
        )
        self.e_sl_pct.insert(0, "1.5")
        self.e_sl_pct.grid(row=1, column=1, padx=5)

        tk.Label(
            f_sltp,
            text="TP1 Target (%):",
        ).grid(row=1, column=2, sticky="w")

        self.e_tp1_pct = tk.Entry(
            f_sltp,
            width=8,
        )
        self.e_tp1_pct.insert(0, "2.0")
        self.e_tp1_pct.grid(row=1, column=3, padx=5)

        tk.Label(
            f_sltp,
            text="TP2 Target (%):",
        ).grid(row=1, column=4, sticky="w")

        self.e_tp2_pct = tk.Entry(
            f_sltp,
            width=8,
        )
        self.e_tp2_pct.insert(0, "4.0")
        self.e_tp2_pct.grid(row=1, column=5, padx=5)

        # TP1 break-even control gets its own dedicated row.
        # Previous V8 UI placed this checkbox on row 2 while the TP Close Qty
        # controls also used row 2, so Tkinter widgets overlapped and the
        # checkbox became invisible even though the feature existed in code.
        self.v_tp1_be = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_sltp,
            text="Move SL to Break-Even after TP1",
            variable=self.v_tp1_be,
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(2, 0))

        tk.Label(
            f_sltp,
            text="TP Close Qty Mode:",
        ).grid(row=3, column=0, sticky="w")

        self.v_tp_qty_mode = tk.StringVar(value="PERCENT_%")
        ttk.OptionMenu(
            f_sltp,
            self.v_tp_qty_mode,
            "PERCENT_%",
            "PERCENT_%",
            "FIXED_QTY",
        ).grid(row=3, column=1, padx=5, sticky="w")

        tk.Label(
            f_sltp,
            text="TP1 Close (% / Qty):",
        ).grid(row=3, column=2, sticky="w")

        self.e_tp1_close = tk.Entry(
            f_sltp,
            width=8,
        )
        self.e_tp1_close.insert(0, "50")
        self.e_tp1_close.grid(row=3, column=3, padx=5)

        tk.Label(
            f_sltp,
            text="TP2 Close (% / Qty):",
        ).grid(row=3, column=4, sticky="w")

        self.e_tp2_close = tk.Entry(
            f_sltp,
            width=8,
        )
        self.e_tp2_close.insert(0, "50")
        self.e_tp2_close.grid(row=3, column=5, padx=5)

        tk.Label(
            f_sltp,
            text=(
                "PERCENT_%: TP1 + TP2 must = 100% of the position "
                "(recommended).  FIXED_QTY: TP1 + TP2 must = the actual position quantity."
            ),
            fg="#444444",
        ).grid(row=3, column=6, columnspan=3, padx=(8, 0), sticky="w")

        # Dedicated row so the Hold-All-Reverse stop is always clearly visible,
        # including on smaller screens / higher Windows DPI scaling.
        tk.Label(
            f_sltp,
            text="Hold-All-Reverse SL (ROI %):",
            font=("Arial", 9, "bold"),
        ).grid(row=4, column=0, sticky="w", padx=(0, 4))

        self.e_hold_sl_roi = tk.Entry(
            f_sltp,
            width=10,
            justify="center",
        )
        self.e_hold_sl_roi.insert(0, "5.0")
        self.e_hold_sl_roi.grid(row=4, column=1, padx=5, pady=2, sticky="w")

        tk.Label(
            f_sltp,
            text="Used ONLY when Hold-All-Reverse = ON",
            fg="#444444",
        ).grid(row=4, column=2, columnspan=2, sticky="w", padx=(8, 0))

        self.v_hold_sl_wait_reversal = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_sltp,
            text="After Hold SL threshold: WAIT for ALL active signals to reverse",
            variable=self.v_hold_sl_wait_reversal,
        ).grid(row=5, column=0, columnspan=6, sticky="w", pady=(2, 0))

        tk.Label(
            f_sltp,
            text=(
                "OFF = normal exchange SL closes at the ROI threshold.  "
                "ON = threshold is monitored by the bot; no exchange SL is placed, "
                "and the position closes only after ALL active directional signals reverse."
            ),
            fg="#444444",
            wraplength=1150,
            justify="left",
        ).grid(
            row=6,
            column=0,
            columnspan=6,
            sticky="w",
            pady=2,
        )

        tk.Label(
            f_sltp,
            text="PRICE_% = market-price move | ROI_% = position ROI target",
            fg="#444444",
        ).grid(row=7, column=0, columnspan=6, sticky="w", pady=(0, 2))

        # 6. Telegram
        f_tele = tk.LabelFrame(
            self.tab_monitor,
            text=" 7. Alerts & Telegram ",
        )
        f_tele.pack(fill="x", padx=10, pady=5)

        self.v_tele_enable = tk.BooleanVar(value=False)

        tk.Checkbutton(
            f_tele,
            text="Enable Telegram Alerts",
            variable=self.v_tele_enable,
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            f_tele,
            text="Bot Token:",
        ).grid(row=1, column=0, sticky="w")

        self.e_tele_token = tk.Entry(
            f_tele,
            width=45,
        )
        self.e_tele_token.grid(
            row=1,
            column=1,
            padx=5,
        )

        tk.Label(
            f_tele,
            text="Chat ID:",
        ).grid(row=2, column=0, sticky="w")

        self.e_tele_chat = tk.Entry(
            f_tele,
            width=45,
        )
        self.e_tele_chat.grid(
            row=2,
            column=1,
            padx=5,
        )

        # Dashboard
        f_dash = tk.LabelFrame(
            self.tab_monitor,
            text=" Live Performance Analytics ",
        )
        f_dash.pack(
            fill="x",
            padx=10,
            pady=5,
        )

        self.lbl_pnl = tk.Label(
            f_dash,
            text=(
                "Start Balance: $0.00 | Current Balance: $0.00 | "
                "Net PnL: $0.00 | Trades: 0 | Wins: 0 | "
                "Losses: 0 | Win Rate: 0.0%"
            ),
            font=("Arial", 10, "bold"),
            fg="#00ff66",
            bg="#111111",
        )
        self.lbl_pnl.pack(
            fill="x",
            padx=5,
            pady=5,
        )

        # ACTION CONTROLS — visible on EVERY tab.
        # The first set is retained as the canonical button attributes used by
        # the existing start/stop logic; all tab copies call the same methods.
        self.control_buttons = []
        for tab in (
            self.tab_connection,
            self.tab_market,
            self.tab_strategy,
            self.tab_grid,
            self.tab_risk,
            self.tab_monitor,
        ):
            bar = tk.Frame(tab)
            bar.pack(fill="x", padx=10, pady=(8, 5), side="bottom")

            save_btn = tk.Button(
                bar, text="SAVE CONFIG", bg="#007bff", fg="white",
                font=("Arial", 10, "bold"), command=self.save_settings,
            )
            start_btn = tk.Button(
                bar, text="START BOT", bg="#28a745", fg="white",
                font=("Arial", 10, "bold"), command=self.start_bot,
            )
            stop_btn = tk.Button(
                bar, text="STOP BOT", bg="#dc3545", fg="white",
                font=("Arial", 10, "bold"), state="disabled", command=self.stop_bot,
            )
            for btn in (save_btn, start_btn, stop_btn):
                btn.pack(side="left", expand=True, fill="x", padx=3)
            self.control_buttons.append((save_btn, start_btn, stop_btn))

        # Preserve the original public widget attributes used throughout V8.
        self.btn_save, self.btn_start, self.btn_stop = self.control_buttons[0]
        self._set_bot_button_states(running=False)

    def _set_bot_button_states(self, running=None):
        """Synchronize Save/Start/Stop buttons across every GUI tab."""
        if running is None:
            running = bool(self.is_running)
        for save_btn, start_btn, stop_btn in getattr(self, "control_buttons", []):
            try:
                save_btn.config(state="normal")
                start_btn.config(state="disabled" if running else "normal")
                stop_btn.config(state="normal" if running else "disabled")
            except Exception:
                pass

    # -------------------- SETTINGS ---------------------------

    def save_settings(self):
        requested_profile = self._sanitize_profile_id(self.v_bot_id.get())
        if self.is_running:
            # A running worker owns its exchange/symbol/profile identity. Allow
            # live strategy/risk edits, but never save them under a different
            # profile or silently change the exchange/symbol/account context.
            if requested_profile != self._sanitize_profile_id(self.bot_profile_id):
                raise RuntimeError(
                    "Profile ID cannot be changed while the bot is running. "
                    "Stop the bot first, then load/copy another profile."
                )
            current_symbol = str(self.symbol or "").strip().upper()
            raw_requested_symbol = str(self.e_symbol.get()).strip().upper()
            current_exchange = str(self.exchange_id or "").strip().lower()
            requested_exchange = str(self.v_exchange.get()).strip().lower()
            current_account = str(self.runtime_account_mode or "").strip().upper()
            requested_account = str(self.v_account_mode.get()).strip().upper()

            # CCXT uses canonical contract symbols such as OP/USDT:USDT,
            # while the GUI commonly displays/accepts OP/USDT.  Comparing the
            # raw GUI text with the canonical running symbol caused a false
            # "Symbol cannot be changed" error during every live checkpoint.
            # Normalize the requested symbol against the already-connected
            # exchange before deciding whether the symbol actually changed.
            requested_symbol = raw_requested_symbol
            if current_symbol and self.exchange is not None and current_exchange:
                try:
                    requested_symbol = self.normalize_symbol(
                        self.exchange,
                        current_exchange,
                        raw_requested_symbol,
                    )
                except Exception as symbol_error:
                    raise RuntimeError(
                        f"Cannot validate the live symbol '{raw_requested_symbol}': "
                        f"{symbol_error}"
                    ) from symbol_error

            if current_symbol and requested_symbol != current_symbol:
                raise RuntimeError(
                    f"Symbol cannot be changed while the bot is running "
                    f"({current_symbol} is active; requested {requested_symbol}). "
                    f"Stop the bot first."
                )
            if current_exchange and requested_exchange != current_exchange:
                raise RuntimeError(
                    f"Exchange cannot be changed while the bot is running "
                    f"({current_exchange.upper()} is active). Stop the bot first."
                )
            if current_account and requested_account != current_account:
                raise RuntimeError(
                    f"Account Mode cannot be changed while the bot is running "
                    f"({current_account} is active). Stop the bot first."
                )

        self.bot_profile_id = requested_profile
        self.v_bot_id.set(self.bot_profile_id)
        cfg = {
            "config_schema_version": CONFIG_SCHEMA_VERSION,
            "bot_id": self.bot_profile_id,
            "exchange": self.v_exchange.get(),
            "api_key": self.e_api_key.get().strip(),
            "api_secret": self.e_api_secret.get().strip(),
            "account_mode": self.v_account_mode.get(),
            "symbol": self.e_symbol.get().strip().upper(),
            "timeframe": self.v_tf.get(),
            "leverage": self.e_lev.get().strip(),
            "max_trades": self.e_max_trades.get().strip(),
            "no_same_candle": self.v_no_same_candle.get(),
            "cooldown_min": self.e_cooldown_min.get().strip(),
            "require_opposite_after_sl": self.v_require_opposite_after_exit.get(),
            # Keep the old key for backward compatibility with existing configs.
            "require_opposite_after_exit": self.v_require_opposite_after_exit.get(),

            "use_st": self.v_use_st.get(),
            "st_len": self.e_st_len.get().strip(),
            "st_mult": self.e_st_mult.get().strip(),
            "st_source": self.v_st_source.get(),
            "st_change_atr": self.v_st_change_atr.get(),
            "st_entry_mode": self.v_st_entry_mode.get(),

            "use_ema": self.v_use_ema.get(),
            "ema_len": self.e_ema_len.get().strip(),

            "use_ema_cross": self.v_use_ema_cross.get(),
            "ema_fast": self.e_ema_fast.get().strip(),
            "ema_slow": self.e_ema_slow.get().strip(),
            "ema_cross_entry_mode": self.v_ema_cross_entry_mode.get(),

            "use_macd": self.v_use_macd.get(),
            "macd_fast": self.e_macd_fast.get().strip(),
            "macd_slow": self.e_macd_slow.get().strip(),
            "macd_signal": self.e_macd_signal.get().strip(),

            "use_rsi": self.v_use_rsi.get(),
            "rsi_len": self.e_rsi_len.get().strip(),
            "rsi_ob": self.e_rsi_ob.get().strip(),
            "rsi_os": self.e_rsi_os.get().strip(),
            "rsi_logic": self.v_rsi_logic.get(),
            "rsi_ma_type": self.v_rsi_ma_type.get(),
            "rsi_ma_len": self.e_rsi_ma_len.get().strip(),

            "use_bb": self.v_use_bb.get(),
            "bb_len": self.e_bb_len.get().strip(),
            "bb_std": self.e_bb_std.get().strip(),

            "use_stoch": self.v_use_stoch.get(),
            "stoch_k": self.e_stoch_k.get().strip(),
            "stoch_smooth": self.e_stoch_smooth.get().strip(),
            "stoch_d": self.e_stoch_d.get().strip(),

            "use_vwap": self.v_use_vwap.get(),
            "vwap_len": self.e_vwap_len.get().strip(),

            "use_vwap_delta": self.v_use_vwap_delta.get(),
            "vwap_delta_smooth": self.v_vwap_delta_smooth.get(),
            "vwap_delta_smooth_len": self.e_vwap_delta_smooth_len.get().strip(),
            "vwap_delta_baseline": self.e_vwap_delta_baseline.get().strip(),
            "vwap_delta_logic": self.v_vwap_delta_logic.get(),

            "use_vidya": self.v_use_vidya.get(),
            "vidya_len": self.e_vidya_len.get().strip(),
            "vidya_momentum": self.e_vidya_momentum.get().strip(),
            "vidya_band": self.e_vidya_band.get().strip(),
            "vidya_entry_mode": self.v_vidya_entry_mode.get(),

            "use_nwe": self.v_use_nwe.get(),
            "nwe_bandwidth": self.e_nwe_bandwidth.get().strip(),
            "nwe_mult": self.e_nwe_mult.get().strip(),
            "nwe_entry_mode": self.v_nwe_entry_mode.get(),
            "nwe_repaint": False,  # retained for config compatibility; NWE is always non-repainting

            "use_liq_swings": self.v_use_liq_swings.get(),
            "liq_length": self.e_liq_length.get().strip(),
            "liq_area": self.v_liq_area.get(),
            "liq_filter": self.v_liq_filter.get(),
            "liq_filter_value": self.e_liq_filter_value.get().strip(),
            "liq_entry_mode": self.v_liq_entry_mode.get(),

            "use_trendline": self.v_use_trendline.get(),
            "trendline_length": self.e_trendline_length.get().strip(),
            "trendline_min_distance": self.e_trendline_min_distance.get().strip(),
            "trendline_entry_mode": self.v_trendline_entry_mode.get(),
            "trendline_buffer": self.e_trendline_buffer.get().strip(),
            "trendline_retest_candles": self.e_trendline_retest.get().strip(),

            "use_divergence": self.v_use_divergence.get(),
            "div_pivot": self.e_div_pivot.get().strip(),
            "div_source": self.v_div_source.get(),
            "div_type": self.v_div_type.get(),
            "div_min_count": self.e_div_min_count.get().strip(),
            "div_max_pivots": self.e_div_max_pivots.get().strip(),
            "div_max_bars": self.e_div_max_bars.get().strip(),
            "div_cci_len": self.e_div_cci_len.get().strip(),
            "div_mom_len": self.e_div_mom_len.get().strip(),
            "div_entry_mode": self.v_div_entry_mode.get(),
            "div_use_macd": self.div_use_macd.get(),
            "div_use_macd_hist": self.div_use_macd_hist.get(),
            "div_use_rsi": self.div_use_rsi.get(),
            "div_use_stoch": self.div_use_stoch.get(),
            "div_use_cci": self.div_use_cci.get(),
            "div_use_momentum": self.div_use_momentum.get(),
            "div_use_obv": self.div_use_obv.get(),
            "div_use_vwmacd": self.div_use_vwmacd.get(),
            "div_use_cmf": self.div_use_cmf.get(),
            "div_use_mfi": self.div_use_mfi.get(),

            "use_vol_sr": self.v_use_vol_sr.get(),
            "sr_tf1": self.v_sr_tf1.get(),
            "sr_tf2": self.v_sr_tf2.get(),
            "sr_tf3": self.v_sr_tf3.get(),
            "sr_tf4": self.v_sr_tf4.get(),
            "sr_volume_ma": self.e_sr_volume_ma.get().strip(),
            "sr_vote_mode": self.v_sr_vote_mode.get(),
            "sr_entry_mode": self.v_sr_entry_mode.get(),

            "grid_mode": self.v_grid_mode.get(),
            "grid_levels": self.e_grid_levels.get().strip(),
            "grid_spacing": self.e_grid_spacing.get().strip(),
            "grid_order_size": self.e_grid_order_size.get().strip(),
            "grid_size_increase": self.e_grid_size_increase.get().strip(),
            "grid_tp": self.e_grid_tp.get().strip(),
            "grid_sl": self.e_grid_sl.get().strip(),
            "grid_max_exposure": self.e_grid_max_exposure.get().strip(),
            "grid_max_dd": self.e_grid_max_dd.get().strip(),
            "grid_score_min": self.e_grid_score_min.get().strip(),
            "grid_trend_filter": self.v_grid_trend_filter.get(),
            "grid_recenter": self.v_grid_recenter.get(),
            "grid_recenter_distance": self.e_grid_recenter.get().strip(),
            "grid_cooldown": self.e_grid_cooldown.get().strip(),

            "use_atr": self.v_use_atr.get(),
            "atr_min_pct": self.e_atr_min_pct.get().strip(),

            "use_vol": self.v_use_vol.get(),
            "vol_len": self.e_vol_len.get().strip(),

            "use_adx": self.v_use_adx.get(),
            "adx_thresh": self.e_adx_thresh.get().strip(),

            "use_mtf": self.v_use_mtf.get(),

            "signal_mode": self.v_signal_mode.get(),
            "signal_mode_v2_migrated": True,
            "min_score": self.e_min_score.get().strip(),
            "adaptive_edge": self.e_adaptive_edge.get().strip(),
            "adaptive_min_weight": self.e_adaptive_min_weight.get().strip(),
            "evidence_min_families": self.evidence_min_families.get().strip(),
            "evidence_family_min_score": self.evidence_family_min_score.get().strip(),
            "evidence_require_trend": self.evidence_require_trend.get(),
            "evidence_require_independent": self.evidence_require_independent.get(),
            "hold_until_all_reverse": self.v_hold_until_all_reverse.get(),

            "size_mode": self.v_size_mode.get(),
            "risk_pct": self.e_risk_pct.get().strip(),
            "fixed_qty": self.e_fixed_qty.get().strip(),
            "max_dd": self.e_max_dd.get().strip(),
            "emergency_capital_pct": self.e_emergency_capital_pct.get().strip(),
            "emergency_scope": self.v_emergency_scope.get(),

            "sltp_mode": self.v_sl_mode.get(),
            "sl_mode": self.v_sl_mode.get(),
            "tp_mode": self.v_tp_mode.get(),
            "sl_pct": self.e_sl_pct.get().strip(),
            "tp1_pct": self.e_tp1_pct.get().strip(),
            "tp2_pct": self.e_tp2_pct.get().strip(),
            "hold_sl_roi": self.e_hold_sl_roi.get().strip(),
            "hold_sl_wait_reversal": self.v_hold_sl_wait_reversal.get(),
            "tp1_be": self.v_tp1_be.get(),

            "tp_qty_mode": self.v_tp_qty_mode.get(),
            "tp1_close": self.e_tp1_close.get().strip(),
            "tp2_close": self.e_tp2_close.get().strip(),

            "tele_enable": self.v_tele_enable.get(),
            "tele_token": self.e_tele_token.get().strip(),
            "tele_chat": self.e_tele_chat.get().strip(),
        }

        try:
            config_path = self._get_config_path(self.bot_profile_id, for_save=True)
            self._write_json_atomic(config_path, cfg)
            self.log(
                f"Configuration saved | Profile={self.bot_profile_id} | "
                f"File={config_path}"
            )
            self._refresh_profile_list(select_profile=self.bot_profile_id)
        except Exception as e:
            self.log(f"Config save error: {e}")
            if self.is_running:
                raise

    def load_settings(self, show_resume=True):
        self.bot_profile_id = self._sanitize_profile_id(
            self.v_bot_id.get() if hasattr(self, "v_bot_id") else self.bot_profile_id
        )
        self.v_bot_id.set(self.bot_profile_id)
        config_path = self._get_config_path(self.bot_profile_id, for_save=False)
        if not os.path.exists(config_path):
            self.log(f"No saved configuration for profile {self.bot_profile_id}.")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            # Clear every Entry-backed setting before inserting the profile.
            # Without this, repeatedly loading profiles would concatenate API
            # credentials and text fields (e.g. OLDVALUE + NEWVALUE).
            for attr in dir(self):
                if not attr.startswith("e_"):
                    continue
                try:
                    widget = getattr(self, attr)
                    if isinstance(widget, tk.Entry):
                        widget.delete(0, tk.END)
                except Exception:
                    pass

            # The profile folder is the authoritative identity.  Never let a
            # mismatched/stale bot_id stored inside config.json silently move a
            # profile into another profile's namespace.            selected_profile = self._sanitize_profile_id(self.bot_profile_id)
            stored_profile = self._sanitize_profile_id(cfg.get("bot_id", selected_profile))
            if stored_profile != selected_profile:
                self.log(
                    f"PROFILE ID MISMATCH: folder={selected_profile} "
                    f"config.bot_id={stored_profile}; keeping folder identity."
                )
            self.bot_profile_id = selected_profile
            self.v_bot_id.set(self.bot_profile_id)

            self.v_exchange.set(
                cfg.get("exchange", "bybit")
            )

            self.e_api_key.insert(
                0,
                cfg.get("api_key", ""),
            )
            self.e_api_secret.insert(
                0,
                cfg.get("api_secret", ""),
            )

            self.v_account_mode.set(
                cfg.get(
                    "account_mode",
                    "BYBIT_DEMO",
                )
            )

            self.e_symbol.delete(
                0,
                tk.END,
            )
            self.e_symbol.insert(
                0,
                cfg.get(
                    "symbol",
                    "BTC/USDT",
                ),
            )

            self.v_tf.set(
                cfg.get(
                    "timeframe",
                    "15m",
                )
            )

            self.e_lev.delete(
                0,
                tk.END,
            )
            self.e_lev.insert(
                0,
                cfg.get(
                    "leverage",
                    "5",
                ),
            )
            self.v_no_same_candle.set(cfg.get("no_same_candle", DEFAULT_NO_SAME_CANDLE))
            self.e_cooldown_min.delete(0, tk.END)
            self.e_cooldown_min.insert(0, cfg.get("cooldown_min", "0"))
            self.v_require_opposite_after_exit.set(
            cfg.get(
                "require_opposite_after_sl",
                cfg.get("require_opposite_after_exit", DEFAULT_POST_SL_OPPOSITE_LOCK),
            )
        )

            self.e_max_trades.delete(0, tk.END)
            self.e_max_trades.insert(0, cfg.get("max_trades", "10"))
            self.update_estimated_window()

            self.v_use_st.set(
                cfg.get(
                    "use_st",
                    True,
                )
            )
            self.e_st_len.delete(
                0,
                tk.END,
            )
            self.e_st_len.insert(
                0,
                cfg.get(
                    "st_len",
                    "10",
                ),
            )
            self.e_st_mult.delete(
                0,
                tk.END,
            )
            self.e_st_mult.insert(
                0,
                cfg.get(
                    "st_mult",
                    "2.0",
                ),
            )

            self.v_st_source.set(
                cfg.get(
                    "st_source",
                    "CLOSE",
                )
            )
            self.v_st_change_atr.set(
                cfg.get(
                    "st_change_atr",
                    True,
                )
            )

            self.v_st_entry_mode.set(
                cfg.get(
                    "st_entry_mode",
                    "FRESH_FLIP",
                )
            )

            self.v_use_ema.set(
                cfg.get(
                    "use_ema",
                    True,
                )
            )
            self.e_ema_len.delete(
                0,
                tk.END,
            )
            self.e_ema_len.insert(
                0,
                cfg.get(
                    "ema_len",
                    "200",
                ),
            )

            self.v_use_ema_cross.set(
                cfg.get(
                    "use_ema_cross",
                    False,
                )
            )

            self.e_ema_fast.delete(
                0,
                tk.END,
            )
            self.e_ema_fast.insert(
                0,
                cfg.get(
                    "ema_fast",
                    "9",
                ),
            )

            self.e_ema_slow.delete(
                0,
                tk.END,
            )
            self.e_ema_slow.insert(
                0,
                cfg.get(
                    "ema_slow",
                    "20",
                ),
            )
            self.v_ema_cross_entry_mode.set(
                cfg.get(
                    "ema_cross_entry_mode",
                    "FRESH_CROSS",
                )
            )

            self.v_use_macd.set(
                cfg.get(
                    "use_macd",
                    False,
                )
            )

            self.e_macd_fast.delete(0, tk.END)
            self.e_macd_fast.insert(
                0,
                cfg.get(
                    "macd_fast",
                    "12",
                ),
            )

            self.e_macd_slow.delete(0, tk.END)
            self.e_macd_slow.insert(
                0,
                cfg.get(
                    "macd_slow",
                    "26",
                ),
            )

            self.e_macd_signal.delete(0, tk.END)
            self.e_macd_signal.insert(
                0,
                cfg.get(
                    "macd_signal",
                    "9",
                ),
            )

            self.v_use_rsi.set(
                cfg.get(
                    "use_rsi",
                    False,
                )
            )

            self.e_rsi_len.delete(0, tk.END)
            self.e_rsi_len.insert(
                0,
                cfg.get(
                    "rsi_len",
                    "14",
                ),
            )

            self.e_rsi_ob.delete(0, tk.END)
            self.e_rsi_ob.insert(
                0,
                cfg.get(
                    "rsi_ob",
                    "80",
                ),
            )

            self.e_rsi_os.delete(0, tk.END)
            self.e_rsi_os.insert(
                0,
                cfg.get(
                    "rsi_os",
                    "20",
                ),
            )

            self.v_rsi_logic.set(cfg.get("rsi_logic", "REVERSAL_ZONE"))
            self.v_rsi_ma_type.set(cfg.get("rsi_ma_type", "EMA"))
            self.e_rsi_ma_len.delete(0, tk.END)
            self.e_rsi_ma_len.insert(0, cfg.get("rsi_ma_len", "9"))

            self.v_use_bb.set(
                cfg.get(
                    "use_bb",
                    False,
                )
            )

            self.e_bb_len.delete(0, tk.END)
            self.e_bb_len.insert(
                0,
                cfg.get(
                    "bb_len",
                    "20",
                ),
            )

            self.e_bb_std.delete(0, tk.END)
            self.e_bb_std.insert(
                0,
                cfg.get(
                    "bb_std",
                    "2",
                ),
            )

            self.v_use_stoch.set(
                cfg.get(
                    "use_stoch",
                    False,
                )
            )

            self.e_stoch_k.delete(0, tk.END)
            self.e_stoch_k.insert(
                0,
                cfg.get(
                    "stoch_k",
                    "14",
                ),
            )

            self.e_stoch_smooth.delete(0, tk.END)
            self.e_stoch_smooth.insert(
                0,
                cfg.get(
                    "stoch_smooth",
                    "3",
                ),
            )

            self.e_stoch_d.delete(0, tk.END)
            self.e_stoch_d.insert(
                0,
                cfg.get(
                    "stoch_d",
                    "3",
                ),
            )

            self.v_use_vwap.set(
                cfg.get(
                    "use_vwap",
                    False,
                )
            )

            self.e_vwap_len.delete(0, tk.END)
            self.e_vwap_len.insert(
                0,
                cfg.get(
                    "vwap_len",
                    "50",
                ),
            )

            self.v_use_vwap_delta.set(cfg.get("use_vwap_delta", False))
            self.v_vwap_delta_smooth.set(cfg.get("vwap_delta_smooth", False))
            self.e_vwap_delta_smooth_len.delete(0, tk.END)
            self.e_vwap_delta_smooth_len.insert(0, cfg.get("vwap_delta_smooth_len", "21"))
            self.e_vwap_delta_baseline.delete(0, tk.END)
            self.e_vwap_delta_baseline.insert(0, cfg.get("vwap_delta_baseline", "50"))
            self.v_vwap_delta_logic.set(cfg.get("vwap_delta_logic", "CURRENT_TREND"))

            self.v_use_vidya.set(cfg.get("use_vidya", False))
            self.e_vidya_len.delete(0, tk.END)
            self.e_vidya_len.insert(0, cfg.get("vidya_len", "10"))
            self.e_vidya_momentum.delete(0, tk.END)
            self.e_vidya_momentum.insert(0, cfg.get("vidya_momentum", "20"))
            self.e_vidya_band.delete(0, tk.END)
            self.e_vidya_band.insert(0, cfg.get("vidya_band", "2"))
            self.v_vidya_entry_mode.set(cfg.get("vidya_entry_mode", "CURRENT_TREND"))

            self.v_use_nwe.set(cfg.get("use_nwe", False))
            self.e_nwe_bandwidth.delete(0, tk.END)
            self.e_nwe_bandwidth.insert(0, cfg.get("nwe_bandwidth", "8"))
            self.e_nwe_mult.delete(0, tk.END)
            self.e_nwe_mult.insert(0, cfg.get("nwe_mult", "3"))
            self.v_nwe_entry_mode.set(cfg.get("nwe_entry_mode", "FRESH_CROSS"))
            self.v_nwe_repaint.set(False)

            self.v_use_liq_swings.set(cfg.get("use_liq_swings", False))
            self.e_liq_length.delete(0, tk.END)
            self.e_liq_length.insert(0, cfg.get("liq_length", "14"))
            self.v_liq_area.set(cfg.get("liq_area", "Wick Extremity"))
            self.v_liq_filter.set(cfg.get("liq_filter", "Count"))
            self.e_liq_filter_value.delete(0, tk.END)
            self.e_liq_filter_value.insert(0, cfg.get("liq_filter_value", "0"))
            self.v_liq_entry_mode.set(cfg.get("liq_entry_mode", "FRESH_BREAK"))

            self.v_use_trendline.set(cfg.get("use_trendline", False))
            self.e_trendline_length.delete(0, tk.END)
            self.e_trendline_length.insert(0, cfg.get("trendline_length", "14"))
            self.e_trendline_min_distance.delete(0, tk.END)
            self.e_trendline_min_distance.insert(0, cfg.get("trendline_min_distance", "5"))
            self.v_trendline_entry_mode.set(cfg.get("trendline_entry_mode", "FRESH_BREAK"))
            self.e_trendline_buffer.delete(0, tk.END)
            self.e_trendline_buffer.insert(0, cfg.get("trendline_buffer", "0"))
            self.e_trendline_retest.delete(0, tk.END)
            self.e_trendline_retest.insert(0, cfg.get("trendline_retest_candles", "3"))

            self.v_use_divergence.set(cfg.get("use_divergence", False))
            for widget, key, default in (
                (self.e_div_pivot, "div_pivot", "5"),
                (self.e_div_min_count, "div_min_count", "1"),
                (self.e_div_max_pivots, "div_max_pivots", "10"),
                (self.e_div_max_bars, "div_max_bars", "100"),
                (self.e_div_cci_len, "div_cci_len", "10"),
                (self.e_div_mom_len, "div_mom_len", "10"),
            ):
                widget.delete(0, tk.END); widget.insert(0, cfg.get(key, default))
            self.v_div_source.set(cfg.get("div_source", "Close"))
            self.v_div_type.set(cfg.get("div_type", "Regular"))
            self.v_div_entry_mode.set(cfg.get("div_entry_mode", "FRESH"))
            for attr, key in (
                ("div_use_macd","div_use_macd"),("div_use_macd_hist","div_use_macd_hist"),
                ("div_use_rsi","div_use_rsi"),("div_use_stoch","div_use_stoch"),
                ("div_use_cci","div_use_cci"),("div_use_momentum","div_use_momentum"),
                ("div_use_obv","div_use_obv"),("div_use_vwmacd","div_use_vwmacd"),
                ("div_use_cmf","div_use_cmf"),("div_use_mfi","div_use_mfi")
            ):
                getattr(self, attr).set(cfg.get(key, True))

            self.v_use_vol_sr.set(cfg.get("use_vol_sr", False))
            self.v_sr_tf1.set(cfg.get("sr_tf1", "Chart"))
            self.v_sr_tf2.set(cfg.get("sr_tf2", "4h"))
            self.v_sr_tf3.set(cfg.get("sr_tf3", "D"))
            self.v_sr_tf4.set(cfg.get("sr_tf4", "W"))
            self.e_sr_volume_ma.delete(0, tk.END); self.e_sr_volume_ma.insert(0, cfg.get("sr_volume_ma", "6"))
            self.v_sr_vote_mode.set(cfg.get("sr_vote_mode", "MAJORITY"))
            self.v_sr_entry_mode.set(cfg.get("sr_entry_mode", "CURRENT_ZONE"))

            self.v_grid_mode.set(cfg.get("grid_mode", DEFAULT_GRID_MODE))
            for widget, key, default in ((self.e_grid_levels, "grid_levels", "5"), (self.e_grid_spacing, "grid_spacing", "1.0"), (self.e_grid_order_size, "grid_order_size", "10"), (self.e_grid_size_increase, "grid_size_increase", "0"), (self.e_grid_tp, "grid_tp", "1.0"), (self.e_grid_sl, "grid_sl", "6.0"), (self.e_grid_max_exposure, "grid_max_exposure", "100"), (self.e_grid_max_dd, "grid_max_dd", "3.0"), (self.e_grid_score_min, "grid_score_min", "1"), (self.e_grid_recenter, "grid_recenter_distance", "3.0"), (self.e_grid_cooldown, "grid_cooldown", "30")):
                widget.delete(0, tk.END); widget.insert(0, cfg.get(key, default))
            self.v_grid_trend_filter.set(cfg.get("grid_trend_filter", "OFF"))
            self.v_grid_recenter.set(cfg.get("grid_recenter", False))

            self.v_use_atr.set(
                cfg.get(
                    "use_atr",
                    DEFAULT_USE_ATR,
                )
            )

            self.e_atr_min_pct.delete(0, tk.END)
            self.e_atr_min_pct.insert(
                0,
                cfg.get(
                    "atr_min_pct",
                    "0.30",
                ),
            )

            self.v_use_vol.set(
                cfg.get(
                    "use_vol",
                    DEFAULT_USE_VOLUME,
                )
            )
            self.e_vol_len.delete(
                0,
                tk.END,
            )
            self.e_vol_len.insert(
                0,
                cfg.get(
                    "vol_len",
                    "20",
                ),
            )

            self.v_use_adx.set(
                cfg.get(
                    "use_adx",
                    DEFAULT_USE_ADX,
                )
            )
            self.e_adx_thresh.delete(
                0,
                tk.END,
            )
            self.e_adx_thresh.insert(
                0,
                cfg.get(
                    "adx_thresh",
                    "20",
                ),
            )

            self.v_use_mtf.set(
                cfg.get(
                    "use_mtf",
                    DEFAULT_USE_MTF,
                )
            )

            saved_signal_mode = str(
                cfg.get(
                    "signal_mode",
                    "ADAPTIVE_SCORE",
                )
            ).strip().upper()

            legacy_mode_map = {
                "ALL_FILTERS": "STRICT_ALL_FILTERS",
                "1_INDICATOR": "SINGLE_SIGNAL",
                "2_INDICATORS": "2_SIGNALS",
                "3_INDICATORS": "3_SIGNALS",
                "4_INDICATORS": "4_SIGNALS",
            }
            saved_signal_mode = legacy_mode_map.get(
                saved_signal_mode,
                saved_signal_mode,
            )

            # One-time migration from the previous default. If the existing
            # config was created by the older bot and still says strict mode,
            # start the new bot in SINGLE_SIGNAL mode. After the user saves a
            # new selection, that selection is preserved normally.
            if (
                saved_signal_mode == "STRICT_ALL_FILTERS"
                and not cfg.get("signal_mode_v2_migrated", False)
            ):
                saved_signal_mode = "SINGLE_SIGNAL"
                cfg["signal_mode_v2_migrated"] = True

            if saved_signal_mode not in SUPPORTED_SIGNAL_MODES:
                self.log(f"Unknown saved Signal Mode {saved_signal_mode}; falling back to SINGLE_SIGNAL.")
                saved_signal_mode = "SINGLE_SIGNAL"
            self.v_signal_mode.set(saved_signal_mode)
            self.v_hold_until_all_reverse.set(cfg.get("hold_until_all_reverse", True))

            self.e_min_score.delete(0, tk.END)
            self.e_min_score.insert(
                0,
                cfg.get(
                    "min_score",
                    "1",
                ),
            )
            self.e_adaptive_edge.delete(0, tk.END)
            self.e_adaptive_edge.insert(0, cfg.get("adaptive_edge", DEFAULT_ADAPTIVE_EDGE))
            self.e_adaptive_min_weight.delete(0, tk.END)
            self.e_adaptive_min_weight.insert(0, cfg.get("adaptive_min_weight", DEFAULT_ADAPTIVE_MIN_WEIGHT))
            self.evidence_min_families.delete(0, tk.END)
            self.evidence_min_families.insert(0, cfg.get("evidence_min_families", EVIDENCE_DEFAULT_MIN_FAMILIES))
            self.evidence_family_min_score.delete(0, tk.END)
            self.evidence_family_min_score.insert(0, cfg.get("evidence_family_min_score", EVIDENCE_DEFAULT_FAMILY_MIN_SCORE))
            self.evidence_require_trend.set(bool(cfg.get("evidence_require_trend", EVIDENCE_DEFAULT_REQUIRE_TREND)))
            self.evidence_require_independent.set(bool(cfg.get("evidence_require_independent", EVIDENCE_DEFAULT_REQUIRE_INDEPENDENT)))

            self.v_size_mode.set(
                cfg.get(
                    "size_mode",
                    DEFAULT_RISK_MODE,
                )
            )

            self.e_risk_pct.delete(
                0,
                tk.END,
            )
            self.e_risk_pct.insert(
                0,
                cfg.get(
                    "risk_pct",
                    DEFAULT_RISK_PER_TRADE,
                ),
            )

            self.e_fixed_qty.delete(
                0,
                tk.END,
            )
            self.e_fixed_qty.insert(
                0,
                cfg.get(
                    "fixed_qty",
                    "0.001",
                ),
            )

            self.e_max_dd.delete(
                0,
                tk.END,
            )
            self.e_max_dd.insert(
                0,
                cfg.get(
                    "max_dd",
                    "5.0",
                ),
            )
            self.e_emergency_capital_pct.delete(0, tk.END)
            self.e_emergency_capital_pct.insert(0, cfg.get("emergency_capital_pct", "30.0"))
            self.v_emergency_scope.set(cfg.get("emergency_scope", "BOT_SYMBOL"))

            legacy_protection_mode = cfg.get("sltp_mode", "PRICE_%")
            self.v_sl_mode.set(cfg.get("sl_mode", legacy_protection_mode))
            self.v_tp_mode.set(cfg.get("tp_mode", legacy_protection_mode))

            self.e_sl_pct.delete(
                0,
                tk.END,
            )
            self.e_sl_pct.insert(
                0,
                cfg.get(
                    "sl_pct",
                    "1.5",
                ),
            )

            self.e_tp1_pct.delete(
                0,
                tk.END,
            )
            self.e_tp1_pct.insert(
                0,
                cfg.get(
                    "tp1_pct",
                    "2.0",
                ),
            )

            self.e_tp2_pct.delete(
                0,
                tk.END,
            )
            self.e_tp2_pct.insert(
                0,
                cfg.get(
                    "tp2_pct",
                    "4.0",
                ),
            )

            self.e_hold_sl_roi.delete(0, tk.END)
            self.e_hold_sl_roi.insert(
                0,
                cfg.get(
                    "hold_sl_roi",
                    "5.0",
                ),
            )
            self.v_hold_sl_wait_reversal.set(
                cfg.get(
                    "hold_sl_wait_reversal",
                    False,
                )
            )

            self.v_tp1_be.set(
                cfg.get(
                    "tp1_be",
                    True,
                )
            )

            self.v_tp_qty_mode.set(
                cfg.get(
                    "tp_qty_mode",
                    "PERCENT_%",
                )
            )

            self.e_tp1_close.delete(
                0,
                tk.END,
            )
            self.e_tp1_close.insert(
                0,
                cfg.get(
                    "tp1_close",
                    "50",
                ),
            )

            self.e_tp2_close.delete(
                0,
                tk.END,
            )
            self.e_tp2_close.insert(
                0,
                cfg.get(
                    "tp2_close",
                    "50",
                ),
            )

            self.v_tele_enable.set(
                cfg.get(
                    "tele_enable",
                    False,
                )
            )

            self.e_tele_token.delete(
                0,
                tk.END,
            )
            self.e_tele_token.insert(
                0,
                cfg.get(
                    "tele_token",
                    "",
                ),
            )

            self.e_tele_chat.delete(
                0,
                tk.END,
            )
            self.e_tele_chat.insert(
                0,
                cfg.get(
                    "tele_chat",
                    "",
                ),
            )

            self.log(
                "Configuration loaded."
            )

        except Exception as e:
            self.log(
                f"Config load error: {e}"
            )

    # -------------------- EXCHANGE ---------------------------

    def build_exchange(self, exchange_id, api_key, api_secret, account_mode):
        """Build a CCXT futures/swap client for every V8-supported exchange."""
        supported = {
            "bybit": "swap",
            "binance": "future",
            "gate": "swap",
            "bitget": "swap",
            "weex": "swap",
        }
        if exchange_id not in supported:
            raise RuntimeError(f"Unsupported V8 exchange: {exchange_id}")

        # Never silently turn a mismatched account-mode selection into LIVE.
        # The GUI exposes all exchange modes in one dropdown, so switching the
        # exchange can otherwise leave BYBIT_DEMO selected and accidentally make
        # Binance/Gate/Bitget/WEEX run against LIVE.
        allowed_modes = {
            "bybit": {"BYBIT_DEMO", "BYBIT_TESTNET", "LIVE"},
            "binance": {"TESTNET", "LIVE"},
            "gate": {"TESTNET", "LIVE"},
            "bitget": {"DEMO", "LIVE"},
            "weex": {"DEMO", "LIVE"},
        }
        account_mode = str(account_mode or "").strip().upper()
        if account_mode not in allowed_modes[exchange_id]:
            raise RuntimeError(
                f"Invalid Account Mode '{account_mode}' for {exchange_id.upper()}. "
                f"Allowed: {', '.join(sorted(allowed_modes[exchange_id]))}. "
                "The bot will NOT silently fall back to LIVE."
            )

        exchange_class = getattr(ccxt, exchange_id)

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": 20000,
            "options": {
                "defaultType": supported[exchange_id],
            },
        }

        exchange = exchange_class(config)

        # Sandbox/demo must be enabled immediately after construction.
        # Bybit has its dedicated Demo API; Bitget and WEEX expose demo trading
        # through CCXT; Gate exposes a testnet; KuCoin Futures currently has
        # no CCXT sandbox URL, so it is intentionally LIVE-only here.
        if exchange_id == "bybit":
            if account_mode == "BYBIT_DEMO":
                if not hasattr(exchange, "enable_demo_trading"):
                    raise RuntimeError("Installed CCXT does not support Bybit Demo Trading.")
                exchange.enable_demo_trading(True)
                self.log("BYBIT DEMO mode enabled.")
            elif account_mode == "BYBIT_TESTNET":
                exchange.set_sandbox_mode(True)
                self.log("BYBIT TESTNET mode enabled.")
            else:
                self.log("BYBIT LIVE mode selected.")

        elif exchange_id == "binance":
            if account_mode == "TESTNET":
                exchange.set_sandbox_mode(True)
                self.log("BINANCE FUTURES TESTNET mode enabled.")
            else:
                self.log("BINANCE FUTURES LIVE mode selected.")

        elif exchange_id == "gate":
            if account_mode == "TESTNET":
                exchange.set_sandbox_mode(True)
                self.log("GATE.IO FUTURES TESTNET mode enabled.")
            else:
                self.log("GATE.IO FUTURES LIVE mode selected.")

        elif exchange_id == "bitget":
            if account_mode == "DEMO":
                if hasattr(exchange, "enable_demo_trading"):
                    exchange.enable_demo_trading(True)
                else:
                    exchange.set_sandbox_mode(True)
                self.log("BITGET DEMO mode enabled.")
            else:
                self.log("BITGET LIVE mode selected.")

        elif exchange_id == "weex":
            if account_mode == "DEMO":
                exchange.set_sandbox_mode(True)
                self.log("WEEX DEMO mode enabled.")
            else:
                self.log("WEEX LIVE mode selected.")

        exchange.load_markets()
        return exchange

    def normalize_symbol(self, exchange, exchange_id, raw_symbol):
        """Resolve a user-entered symbol to the exchange's unified perpetual symbol."""
        raw_symbol = raw_symbol.strip().upper()

        # Exact match first.
        if raw_symbol in exchange.markets:
            market = exchange.markets[raw_symbol]
            if market.get("swap") or market.get("future") or market.get("contract"):
                return raw_symbol

        # Normalize common forms: BTCUSDT, BTC/USDT, BTC/USDT:USDT.
        compact = raw_symbol.replace("/", "").replace(":", "")
        if compact.endswith("USDT"):
            base = compact[:-4]
            candidates = [
                (sym, market) for sym, market in exchange.markets.items()
                if str(market.get("base") or "").upper() == base
                and str(market.get("quote") or "").upper() == "USDT"
                and (market.get("swap") or market.get("future") or market.get("contract"))
            ]
        else:
            candidates = []

        if not candidates and "/" in raw_symbol:
            base = raw_symbol.split("/")[0]
            quote = raw_symbol.split("/")[1].split(":")[0]
            candidates = [
                (sym, market) for sym, market in exchange.markets.items()
                if str(market.get("base") or "").upper() == base
                and str(market.get("quote") or "").upper() == quote
                and (market.get("swap") or market.get("future") or market.get("contract"))
            ]

        if candidates:
            # Prefer USDT-settled perpetual swaps, then perpetual swaps generally.
            candidates.sort(
                key=lambda item: (
                    0 if item[1].get("swap") else 1,
                    0 if str(item[1].get("settle") or "").upper() == "USDT" else 1,
                    item[0],
                )
            )
            return candidates[0][0]

        # Final case-insensitive exact lookup.
        for sym, market in exchange.markets.items():
            if sym.upper() == raw_symbol and (
                market.get("swap") or market.get("future") or market.get("contract")
            ):
                return sym

        raise RuntimeError(
            f"Perpetual/futures symbol not found on {exchange_id}: {raw_symbol}"
        )

    # -------------------- PRECISION --------------------------
    def safe_amount(self, symbol, qty):
        qty = float(qty)

        if qty <= 0:
            return 0.0

        try:
            qty = float(
                self.exchange.amount_to_precision(
                    symbol,
                    qty,
                )
            )
        except Exception:
            pass

        market = self.exchange.market(symbol)

        min_amount = (
            (market.get("limits") or {})
            .get("amount", {})
            .get("min")
        )

        if (
            min_amount is not None
            and qty < float(min_amount)
        ):
            return 0.0

        return qty

    def safe_price(self, symbol, price):
        try:
            return float(
                self.exchange.price_to_precision(
                    symbol,
                    price,
                )
            )
        except Exception:
            return float(price)

    # -------------------- ACCOUNT / POSITION -----------------

    def fetch_balance_total(self):
        balance = self.exchange.fetch_balance()

        try:
            value = balance["USDT"]["total"]
            if value is not None:
                return float(value)
        except Exception:
            pass

        try:
            return float(
                balance["total"]["USDT"]
            )
        except Exception:
            raise RuntimeError(
                "Could not read USDT total balance."
            )

    def fetch_account_equity(self):
        """Return Bybit account equity; unrealized PnL is included when available."""
        balance = self.exchange.fetch_balance()
        try:
            rows = ((balance.get("info") or {}).get("result") or {}).get("list") or []
            if rows and rows[0].get("totalEquity") is not None:
                return float(rows[0]["totalEquity"])
        except Exception:
            pass
        equity = self.fetch_balance_total()
        try:
            for pos in self.exchange.fetch_positions():
                try:
                    if abs(float(pos.get("contracts") or 0)) <= 0:
                        continue
                except Exception:
                    continue
                upl = pos.get("unrealizedPnl")
                if upl is None:
                    upl = (pos.get("info") or {}).get("unrealisedPnl")
                if upl is not None:
                    equity += float(upl)
        except Exception:
            pass
        return float(equity)

    def _emergency_flatten_all_positions(self, reason, equity, threshold):
        """Fail-closed capital circuit breaker with safe scope selection.

        V8.3 defaults to BOT_SYMBOL so an emergency in this bot cannot silently
        close unrelated manual/other-bot positions on the same account.
        ALL_ACCOUNT remains available only as an explicit configuration choice.
        """
        scope = self.v_emergency_scope.get().strip().upper() if hasattr(self, "v_emergency_scope") else "BOT_SYMBOL"
        if scope not in ("BOT_SYMBOL", "ALL_ACCOUNT"):
            scope = "BOT_SYMBOL"
        self.log(f"CRITICAL CAPITAL CIRCUIT BREAKER: Equity={equity:.8f} <= Threshold={threshold:.8f} | Scope={scope} | {reason}")
        try:
            self.send_telegram(f"CRITICAL CAPITAL CIRCUIT BREAKER: equity {equity:.4f} <= {threshold:.4f}. Scope={scope}. Bot stopped.")
        except Exception:
            pass
        try:
            positions = self.exchange.fetch_positions() if scope == "ALL_ACCOUNT" else ([self.fetch_position(self.symbol)] if self.symbol else [])
        except Exception as e:
            positions = []
            self.log(f"CAPITAL STOP: Could not fetch positions: {e}")
        symbols = {p.get("symbol") for p in positions if p and p.get("symbol")}
        if scope == "BOT_SYMBOL" and self.symbol:
            symbols = {self.symbol}
        for sym in sorted(symbols):
            try:
                if scope == "ALL_ACCOUNT":
                    self.cancel_all_open_orders(sym)
                else:
                    self._cancel_known_managed_orders(sym)
            except Exception as e:
                self.log(f"CAPITAL STOP: Order cleanup failed {sym}: {e}")
        for pos in positions:
            if not pos:
                continue
            sym = pos.get("symbol")
            side = str(pos.get("side") or "").upper()
            try:
                contracts = abs(float(pos.get("contracts") or 0))
            except Exception:
                contracts = 0.0
            if not sym or contracts <= 0 or side not in ("LONG", "SHORT"):
                continue
            qty = self.safe_amount(sym, contracts)
            if qty <= 0:
                continue
            close_side = "sell" if side == "LONG" else "buy"
            try:
                close_params = {"reduceOnly": True}
                if self.exchange_id == "bybit": close_params["positionIdx"] = 0
                self.exchange.create_order(sym, "market", close_side, qty, None, close_params)
                self.log(f"CAPITAL STOP: Closing {side} {sym} Qty={qty}")
            except Exception as e:
                self.log(f"CAPITAL STOP: FAILED to close {side} {sym}: {e}")
        self.is_running = False
        self.log("CAPITAL STOP COMPLETE: Emergency equity limit reached. Bot stopped; no new trades will be opened.")
        try:
            self.root.after(0, lambda: self._set_bot_button_states(running=False))
        except Exception:
            pass

    def fetch_position(self, symbol):
        positions = self.exchange.fetch_positions(            [symbol]
        )

        active_positions = []
        for pos in positions:
            contracts = pos.get("contracts")

            try:
                contracts = abs(
                    float(contracts or 0)
                )
            except Exception:
                contracts = 0.0

            if contracts <= 0:
                continue

            side = str(
                pos.get("side") or ""
            ).lower()

            if side not in ("long", "short"):
                continue

            active_positions.append((pos, contracts))

        # V8.1 is a one-way-position engine.  If the exchange/account returns
        # more than one live position for the symbol (for example hedge mode),
        # guessing which position belongs to the bot is unsafe.
        if len(active_positions) > 1:
            sides = ",".join(
                str(item[0].get("side") or "").upper()
                for item in active_positions
            )
            raise RuntimeError(
                f"MULTIPLE ACTIVE POSITIONS DETECTED for {symbol}: {sides}. "
                "This bot requires one-way/single-position mode; refusing to guess."
            )

        if not active_positions:
            return None

        pos, contracts = active_positions[0]
        side = str(pos.get("side") or "").lower()

        entry = (
            pos.get("entryPrice")
            or pos.get("average")
            or pos.get("avgPrice")
        )

        try:
            entry = float(entry)
        except Exception:
            entry = 0.0

        raw_info = pos.get("info") or {}

        leverage_value = (
            pos.get("leverage")
            or raw_info.get("leverage")
        )
        try:
            leverage_value = float(leverage_value)
        except Exception:
            leverage_value = 0.0

        initial_margin = (
            pos.get("initialMargin")
            or pos.get("initialMarginByMp")
            or raw_info.get("positionIM")
            or raw_info.get("positionIMByMp")
        )
        try:
            initial_margin = float(initial_margin)
        except Exception:
            initial_margin = 0.0

        return {
            "side": side.upper(),
            "qty": contracts,
            "entry": entry,
            "leverage": leverage_value,
            "initial_margin": initial_margin,
            "raw": pos,
        }

        return None

    def wait_for_position(
        self,
        symbol,
        expected_side,
        timeout=10,
    ):
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                pos = self.fetch_position(
                    symbol
                )

                if (
                    pos
                    and pos["side"]
                    == expected_side
                    and pos["qty"] > 0
                    and pos["entry"] > 0
                ):
                    return pos

            except Exception as e:
                self.log(
                    f"Position read warning: {e}"
                )

            time.sleep(0.5)

        return None

    # -------------------- OPEN ORDERS -------------------------

    def fetch_open_orders_safe(self, symbol, strict=False):
        """Read open orders with an explicit Bybit page size.

        A missing order from the first page is never treated as proof that the
        order is gone.  Callers that are making a safety-critical decision can
        pass strict=True so an exchange read failure aborts that decision
        instead of being misinterpreted as an empty book.
        """
        try:
            if self.exchange_id == "bybit":
                rows = self.exchange.fetch_open_orders(symbol, limit=OPEN_ORDER_PAGE_LIMIT)
            else:
                rows = self.exchange.fetch_open_orders(symbol)
            if strict and self.exchange_id == "bybit" and len(rows) >= OPEN_ORDER_PAGE_LIMIT:
                raise RuntimeError(
                    f"Open-order snapshot for {symbol} reached the {OPEN_ORDER_PAGE_LIMIT}-order page limit; "
                    "refusing to assume the inventory is complete."
                )
            return rows
        except Exception as e:
            self.log(f"Open-order read warning: {e}")
            if strict:
                raise RuntimeError(
                    f"Could not read open orders for {symbol}: {e}"
                ) from e
            return []

    def _order_is_still_open(self, symbol, order_id, unknown_is_open=True):
        """Verify one specific order without trusting a partial order snapshot.

        When the exchange cannot prove the state, the default remains fail-open
        for cancellation/duplicate-prevention callers. Safety-critical
        protection reconciliation can request ``unknown_is_open=False`` and
        receive ``None`` so it can pause instead of guessing.
        """
        oid = str(order_id or "")
        if not oid:
            return False

        # Bybit supports querying the realtime order endpoint by orderId.
        # This is preferable for conditional/TP-SL orders, for which a generic
        # fetch_order() call can have exchange-specific history restrictions.
        if self.exchange_id == "bybit":
            try:
                rows = self.exchange.fetch_open_orders(
                    symbol,
                    limit=50,
                    params={"orderId": oid},
                )
                return any(
                    str(order.get("id") or "") == oid
                    for order in rows
                )
            except Exception as e:
                self.log(f"Order-status query warning | ID={oid} | {e}")
                # Fall through to the unified endpoint before declaring failure.

        try:
            order = self.exchange.fetch_order(oid, symbol)
            status = str(order.get("status") or "").lower()
            return status in ("open", "new", "partially_filled", "pending")
        except Exception as e:
            # Fail closed: an inability to prove cancellation/open status must
            # not be used to create a replacement order.
            self.log(f"Order-status verification inconclusive | ID={oid} | {e}")
            return True if unknown_is_open else None

    def _fetch_specific_order(self, symbol, order_id):
        """Fetch one order by ID using venue-specific realtime/history queries."""
        oid = str(order_id or "")
        if not oid:
            return None

        if self.exchange_id == "bybit":
            try:
                rows = self.exchange.fetch_open_orders(
                    symbol,
                    limit=50,
                    params={"orderId": oid},
                )
                if rows:
                    return rows[0]
            except Exception as e:
                self.log(f"Specific open-order query warning | ID={oid} | {e}")

            try:
                rows = self.exchange.fetch_closed_orders(
                    symbol,
                    limit=50,
                    params={"orderId": oid},
                )
                if rows:
                    return rows[0]
            except Exception as e:
                self.log(f"Specific closed-order query warning | ID={oid} | {e}")

        try:
            return self.exchange.fetch_order(oid, symbol)
        except Exception as e:
            self.log(f"Specific order query inconclusive | ID={oid} | {e}")
            return None

    def _remember_managed_order_ids(self, ids):
        """Persist exact exchange order IDs previously created/tracked by this bot."""
        for oid in (ids or set()):
            if oid:
                self.retired_managed_order_ids.add(str(oid))

    def _known_managed_order_ids(self, symbol):
        ids=set()
        p=self.last_protected_position or {}
        for k in ("sl_id","tp1_id","tp2_id"):
            if p.get(k): ids.add(str(p[k]))
        gs=self.grid_state or {}
        for k in ("tp_order_id","sl_order_id"):
            if gs.get(k): ids.add(str(gs[k]))
        for meta in (gs.get("entry_orders") or {}).values():
            if meta.get("id"): ids.add(str(meta["id"]))
        ids.update(str(x) for x in self.retired_managed_order_ids if x)
        return ids

    @staticmethod
    def _checkpoint_managed_order_ids(state):
        """Extract only exact order IDs persisted by this bot profile."""
        ids = set()
        if not isinstance(state, dict):
            return ids
        ps = state.get("position_state") or {}
        lp = ps.get("last_protected_position")
        if isinstance(lp, dict):
            for key in ("sl_id", "tp1_id", "tp2_id"):
                if lp.get(key):
                    ids.add(str(lp[key]))
        retired = ps.get("retired_managed_order_ids") or []
        ids.update(str(x) for x in retired if x)
        gs = state.get("grid_state") or {}
        for key in ("tp_order_id", "sl_order_id"):
            if gs.get(key):
                ids.add(str(gs[key]))
        for meta in (gs.get("entry_orders") or {}).values():
            if isinstance(meta, dict) and meta.get("id"):
                ids.add(str(meta["id"]))
        return ids

    def _cancel_known_managed_orders_from_ids(self, symbol, ids):
        ids = {str(oid) for oid in (ids or set()) if oid}
        for oid in sorted(ids):
            try:
                self.exchange.cancel_order(oid, symbol)
            except Exception as e:
                self.log(f"MANAGED ORDER CANCEL WARNING | ID={oid} | {e}")
        if ids:
            time.sleep(0.25)
            remaining = []
            for oid in sorted(ids):
                state = self._order_is_still_open(symbol, oid, unknown_is_open=False)
                if state is None or state:
                    remaining.append(oid)
            if remaining:
                raise RuntimeError(
                    "Managed orders could not be verified cancelled: "
                    + ",".join(remaining[:20])
                )

    def _cancel_known_managed_orders(self, symbol):
        ids=self._known_managed_order_ids(symbol)
        for oid in sorted(ids):
            try:
                self.exchange.cancel_order(oid, symbol)
            except Exception as e:
                self.log(f"MANAGED ORDER CANCEL WARNING | ID={oid} | {e}")
        if ids:
            time.sleep(0.25)
            remaining=[]
            for oid in sorted(ids):
                try:
                    if self._order_is_still_open(symbol, oid, unknown_is_open=False): remaining.append(oid)
                except Exception:
                    remaining.append(oid)
            if remaining:
                raise RuntimeError("Managed orders could not be verified cancelled: " + ",".join(remaining[:20]))

    def cancel_all_open_orders(self, symbol):
        """Cancel all exchange orders for one symbol, including large order books."""
        cancel_all_ok = False
        if hasattr(self.exchange, "cancel_all_orders"):
            try:
                self.exchange.cancel_all_orders(symbol)
                cancel_all_ok = True
                self.log(f"Cancel-all requested for {symbol}.")
                time.sleep(0.5)
            except Exception as e:
                self.log(f"Cancel-all request warning for {symbol}: {e}")

        # If the exchange does not provide cancel-all, or if cancellation is
        # asynchronous/partial, repeatedly drain visible pages.  This matters
        # for the exact failure mode previously seen with hundreds of Grid
        # orders: cancelling only the first 20/50 is not sufficient.
        for attempt in range(1, 11):
            orders = self.fetch_open_orders_safe(symbol, strict=True)
            if not orders:
                self.log(
                    f"ALL OPEN ORDERS CANCEL VERIFIED | {symbol} | "
                    f"Method={'cancel_all' if cancel_all_ok else 'individual'}"
                )
                return

            for order in orders:
                order_id = order.get("id")
                if not order_id:
                    continue
                try:
                    self.exchange.cancel_order(order_id, symbol)
                    self.log(
                        f"Cancelled remaining order: {order_id} | Pass={attempt}"
                    )
                except Exception as e:
                    self.log(
                        f"Cancel warning {order_id} | Pass={attempt} | {e}"
                    )

            time.sleep(0.35)

        remaining = self.fetch_open_orders_safe(symbol, strict=True)
        if remaining:
            ids = [str(o.get("id")) for o in remaining if o.get("id")]
            raise RuntimeError(
                f"Could not verify cancellation of all open orders on {symbol} "
                f"after 10 passes. Still visible: {', '.join(ids[:20])}"
                + (" ..." if len(ids) > 20 else "")
            )
    # -------------------- ENTRY PRICE ------------------------

    def get_actual_order_price(self, order):
        candidates = [
            order.get("average"),
            order.get("price"),
        ]

        for value in candidates:
            try:
                value = float(value)
                if value > 0:
                    return value
            except Exception:
                pass

        info = order.get("info") or {}

        for key in (
            "avgPrice",
            "averagePrice",
            "avgFillPrice",
            "price",
        ):
            try:
                value = float(
                    info.get(key)
                )
                if value > 0:
                    return value
            except Exception:
                pass

        return None

    # -------------------- POSITION SIZING --------------------

    def calculate_entry_qty(
        self,
        symbol,
        balance,
        reference_price,
        risk_pct,
        sl_price_fraction,
        size_mode,
        fixed_qty,
    ):
        if size_mode == "FIXED_QTY":
            qty = fixed_qty
        else:
            if risk_pct <= 0:
                raise ValueError(
                    "Risk Per Trade must be greater than 0."
                )

            if sl_price_fraction <= 0:
                raise ValueError(
                    "SL price distance must be greater than 0."
                )

            risk_amount = (
                balance * risk_pct
            )

            stop_distance = (
                reference_price * sl_price_fraction
            )

            qty = (
                risk_amount
                / stop_distance
            )

        qty = self.safe_amount(
            symbol,
            qty,
        )

        if qty <= 0:
            raise RuntimeError(
                "Calculated quantity is below "
                "the exchange minimum/precision."
            )

        return qty

    # -------------------- SL / TP CALCULATION ----------------

    def target_to_price_fraction(
        self,
        target_pct,
        protection_mode,
        leverage,
        actual_entry=None,
        position_qty=None,
        position_initial_margin=None,
    ):
        """
        Convert the user-entered target into a market-price movement.

        PRICE_%:
            2.0 means a 2.0% price move from actual entry.

        ROI_%:
            For linear contracts, ROI = P&L / position margin.
            When the exchange exposes the actual position margin, use it
            to calculate the trigger price. This is more accurate than
            simply dividing ROI by leverage, especially in Bybit cross
            margin where the displayed position margin can include the
            closing-fee component.

            Fallback:
                if position margin is unavailable, use:
                price_move ~= ROI / leverage.

        Fees, funding and slippage can make the realized/displayed ROI
        differ slightly from the requested trigger target.
        """
        target_pct = float(target_pct)
        leverage = float(leverage)

        if target_pct <= 0:
            raise RuntimeError(
                "SL/TP targets must be greater than zero."
            )

        if leverage <= 0:
            raise RuntimeError(
                "Leverage must be greater than zero."
            )

        mode = str(protection_mode).upper()

        if mode == "PRICE_%":
            return target_pct / 100.0

        if mode != "ROI_%":
            raise RuntimeError(
                f"Unknown SL/TP protection mode: {protection_mode}"
            )

        # Preferred: use the actual position margin returned by the
        # exchange after the position is filled.
        if (
            actual_entry is not None
            and actual_entry > 0
            and position_qty is not None
            and position_qty > 0
            and position_initial_margin is not None
            and position_initial_margin > 0
        ):
            target_pnl = (
                position_initial_margin
                * (target_pct / 100.0)
            )
            return target_pnl / position_qty / actual_entry

        # Pre-entry sizing fallback.
        return (target_pct / 100.0) / leverage

    def calculate_protection_prices(
        self,
        symbol,
        side,
        actual_entry,
        position_qty,
        position_initial_margin,
        sl_target_pct,
        tp1_target_pct,
        tp2_target_pct,
        sl_mode,
        tp_mode,
        leverage,
    ):
        if actual_entry <= 0:
            raise RuntimeError(
                "Actual entry price is invalid."
            )

        sl_move = self.target_to_price_fraction(
            sl_target_pct,
            sl_mode,
            leverage,
            actual_entry,
            position_qty,
            position_initial_margin,
        )
        tp1_move = self.target_to_price_fraction(
            tp1_target_pct,
            tp_mode,
            leverage,
            actual_entry,
            position_qty,
            position_initial_margin,
        )
        tp2_move = self.target_to_price_fraction(
            tp2_target_pct,
            tp_mode,
            leverage,
            actual_entry,
            position_qty,
            position_initial_margin,
        )

        if side == "LONG":
            sl = actual_entry * (1 - sl_move)
            tp1 = actual_entry * (1 + tp1_move)
            tp2 = actual_entry * (1 + tp2_move)
        else:
            sl = actual_entry * (1 + sl_move)
            tp1 = actual_entry * (1 - tp1_move)
            tp2 = actual_entry * (1 - tp2_move)

        sl = self.safe_price(
            symbol,
            sl,
        )
        tp1 = self.safe_price(
            symbol,
            tp1,
        )
        tp2 = self.safe_price(
            symbol,
            tp2,
        )

        # Validate direction.
        if side == "LONG":
            if not (
                sl < actual_entry
                and tp1 > actual_entry
                and tp2 > tp1
            ):
                raise RuntimeError(
                    "Calculated LONG SL/TP prices are invalid."
                )
        else:
            if not (
                sl > actual_entry
                and tp1 < actual_entry
                and tp2 < tp1
            ):
                raise RuntimeError(
                    "Calculated SHORT SL/TP prices are invalid."
                )

        return sl, tp1, tp2, sl_move, tp1_move, tp2_move

    def _current_market_price(self, symbol):
        """Return the latest exchange price for bot-managed Hold-SL monitoring."""
        ticker = self.exchange.fetch_ticker(symbol)
        last = ticker.get("last") or ticker.get("close")
        if last is None:
            raise RuntimeError("Exchange returned no current market price.")
        return float(last)

    def _manage_hold_sl_wait_reversal(self, position):
        """Monitor the Hold-All-Reverse ROI threshold without an exchange SL.

        When the threshold is reached, the position remains open.  The normal
        all-active-direction reversal logic is then responsible for closing
        the position.  This is deliberately separate from the exchange-side
        SL reconciliation.
        """
        if not position or not self.last_protected_position:
            return False

        protected = self.last_protected_position
        if not protected.get("hold_sl_wait_reversal"):
            return False
        if protected.get("side") != position.get("side"):
            return False
        if self.hold_sl_threshold_hit:
            return True

        threshold = float(protected.get("sl") or 0.0)
        if threshold <= 0:
            return False

        try:
            price = self._current_market_price(self.symbol)
        except Exception as e:
            self.log(f"HOLD-SL PRICE NOTICE: {e}")
            return False

        side = position.get("side")
        hit = (
            price <= threshold if side == "LONG"
            else price >= threshold
        )

        if hit:
            self.hold_sl_threshold_hit = True
            if not self.hold_sl_threshold_logged:
                self.hold_sl_threshold_logged = True
                self.log(
                    f"HOLD-SL THRESHOLD REACHED: {side} | "
                    f"Current={price:.12g} | Threshold={threshold:.12g} | "
                    "POSITION REMAINS OPEN. Waiting for ALL active directional signals to reverse."
                )
        return self.hold_sl_threshold_hit

    # -------------------- PROTECTION ORDERS ------------------

    def create_bybit_trigger(
        self,
        symbol,
        order_type,
        side,
        qty,
        trigger_price,
        trigger_direction,
        label,
    ):
        # IMPORTANT: CCXT uses the unified order type "market" plus
        # triggerPrice for a market trigger/conditional order.
        # Passing exchange-specific strings such as STOP_MARKET or
        # TAKE_PROFIT_MARKET as the CCXT `type` can make CCXT build a
        # regular limit-style request, which Bybit rejects with:
        # "Price or BBO is required for limit orders".
        #
        # Bybit's V5 API then receives a Market order with a triggerPrice,
        # triggerDirection and reduceOnly, which is the correct structure
        # for an independent conditional close order.
        params = {
            "triggerPrice": trigger_price,
            "triggerDirection": trigger_direction,
            "triggerBy": "LastPrice",
            "reduceOnly": True,
            "positionIdx": 0,
        }

        order = self.exchange.create_order(
            symbol,
            "market",
            side,
            qty,
            None,
            params,
        )

        if not order or not order.get("id"):
            raise RuntimeError(
                f"{label} order returned no order ID."
            )

        self.log(
            f"{label} submitted. ID={order['id']}"
        )

        return order

    def create_binance_trigger(
        self,
        symbol,
        order_type,
        side,
        qty,
        trigger_price,
        label,
    ):
        params = {
            "stopPrice": trigger_price,
            "reduceOnly": True,
            "workingType": "CONTRACT_PRICE",
        }

        order = self.exchange.create_order(
            symbol,
            order_type,
            side,
            qty,
            None,
            params,
        )

        if not order or not order.get("id"):
            raise RuntimeError(
                f"{label} order returned no order ID."
            )

        self.log(
            f"{label} submitted. ID={order['id']}"
        )

        return order

    def calculate_tp_close_quantities(
        self,
        symbol,
        position_qty,
        tp_qty_mode,
        tp1_close_value,
        tp2_close_value,
    ):
        """
        Calculate the quantities closed by TP1 and TP2.

        PERCENT_%:
            tp1_close_value / tp2_close_value are percentages of the
            ACTUAL filled position quantity. They must total exactly 100%.

        FIXED_QTY:
            tp1_close_value / tp2_close_value are exchange quantity units.
            Their sum must equal the ACTUAL filled position quantity.

        SL always protects 100% of the actual position.
        """
        qty = self.safe_amount(symbol, position_qty)

        if qty <= 0:
            raise RuntimeError(
                "Actual position quantity is invalid for TP split."
            )

        mode = str(tp_qty_mode).upper()

        if mode == "PERCENT_%":
            tp1_pct = float(tp1_close_value)
            tp2_pct = float(tp2_close_value)

            if tp1_pct <= 0 or tp2_pct <= 0:
                raise RuntimeError(
                    "TP1 and TP2 close percentages must both be greater than 0."
                )

            if abs((tp1_pct + tp2_pct) - 100.0) > 1e-9:
                raise RuntimeError(
                    f"TP1 + TP2 close percentages must equal 100%. "
                    f"Received {tp1_pct:g}% + {tp2_pct:g}%."
                )

            tp1_qty = self.safe_amount(
                symbol,
                qty * tp1_pct / 100.0,
            )

            # Derive TP2 as the exact remaining quantity after precision
            # so TP1 + TP2 always equals the actual position quantity.
            tp2_qty = self.safe_amount(
                symbol,
                qty - tp1_qty,
            )

        elif mode == "FIXED_QTY":
            requested_tp1 = float(tp1_close_value)
            requested_tp2 = float(tp2_close_value)

            if requested_tp1 <= 0 or requested_tp2 <= 0:
                raise RuntimeError(
                    "TP1 and TP2 fixed quantities must both be greater than 0."
                )

            tp1_qty = self.safe_amount(
                symbol,
                requested_tp1,
            )
            tp2_qty = self.safe_amount(
                symbol,
                requested_tp2,
            )

            if tp1_qty <= 0 or tp2_qty <= 0:
                raise RuntimeError(
                    "TP1/TP2 quantity is below the exchange minimum/precision."
                )

            if abs((tp1_qty + tp2_qty) - qty) > 1e-12:
                raise RuntimeError(
                    f"FIXED_QTY TP split must equal actual position quantity "
                    f"({qty:g}). Received TP1={tp1_qty:g} + TP2={tp2_qty:g}. "
                    "If you mean percentages, select PERCENT_% instead."
                )

        else:
            raise RuntimeError(
                f"Unknown TP quantity mode: {tp_qty_mode}"
            )

        if tp1_qty <= 0 or tp2_qty <= 0:
            raise RuntimeError(
                "Position is too small to split into two TP exits."
            )

        return tp1_qty, tp2_qty

    def create_generic_trigger(
        self,
        symbol,
        side,
        qty,
        trigger_price,
        label,
    ):
        """CCXT unified reduce-only trigger with capability fail-closed checks."""
        try:
            if hasattr(self.exchange, "featureValue"):
                trigger_supported = self.exchange.featureValue(
                    symbol, "createOrder", "triggerPrice"
                )
                reduce_only_supported = self.exchange.featureValue(
                    symbol, "createOrder", "reduceOnly"
                )
                if trigger_supported is False:
                    raise RuntimeError(
                        f"{self.exchange_id.upper()} does not report triggerPrice support "
                        f"for {symbol}."
                    )
                if reduce_only_supported is False:
                    raise RuntimeError(
                        f"{self.exchange_id.upper()} does not report reduceOnly support "
                        f"for {symbol}."
                    )
        except RuntimeError:
            raise
        except Exception as capability_error:
            # Some CCXT versions/exchanges do not expose featureValue reliably.
            # Do not invent a negative capability result; the submitted order is
            # still verified after creation and the surrounding safety path fails
            # closed if verification fails.
            self.log(
                f"TRIGGER CAPABILITY CHECK NOTICE | {self.exchange_id.upper()} "
                f"{symbol} | {capability_error}"
            )

        params = {
            "triggerPrice": trigger_price,
            "reduceOnly": True,
        }
        order = self.exchange.create_order(
            symbol,
            "market",
            side,
            qty,
            None,
            params,
        )
        if not order or not order.get("id"):
            raise RuntimeError(f"{label} order returned no order ID.")
        self.log(f"{label} submitted. ID={order['id']}")
        return order

    def create_protection_orders(
        self,
        symbol,
        position_side,
        position_qty,
        sl,
        tp1,
        tp2,
        tp_qty_mode,
        tp1_close_value,
        tp2_close_value,
    ):
        """
        Creates:
            SL  = 100% of actual position
            TP1 = user-selected quantity
            TP2 = user-selected quantity

        TP quantity can be configured as:
            PERCENT_%  -> percentages of actual position
            FIXED_QTY  -> exchange quantity units

        TP1 + TP2 must equal the actual position quantity.
        """
        qty = self.safe_amount(
            symbol,
            position_qty,
        )

        if qty <= 0:
            raise RuntimeError(
                "Actual position quantity is invalid."
            )

        hold_all_reverse = bool(self.v_hold_until_all_reverse.get())
        tp1_qty = 0.0
        tp2_qty = 0.0
        if not hold_all_reverse:
            tp1_qty, tp2_qty = self.calculate_tp_close_quantities(
                symbol,
                qty,
                tp_qty_mode,
                tp1_close_value,
                tp2_close_value,
            )
            self.log(
                f"TP CLOSE MODE: {tp_qty_mode} | "
                f"TP1={tp1_qty:g} | TP2={tp2_qty:g} | "
                f"Total={qty:g}"
            )
        else:
            self.log(
                "REVERSAL HOLD ON: Only the hard SL will be placed. "
                "TP1/TP2 exchange orders are disabled; strategy reversal is the exit."
            )

        close_side = (
            "sell"
            if position_side == "LONG"
            else "buy"
        )

        created = []

        try:
            if self.exchange_id == "bybit":
                # LONG:
                # SL below current -> descending = 2
                # TP above current -> ascending = 1
                #
                # SHORT:
                # SL above current -> ascending = 1
                # TP below current -> descending = 2
                if position_side == "LONG":
                    sl_direction = 2
                    tp_direction = 1
                else:
                    sl_direction = 1
                    tp_direction = 2

                sl_order = self.create_bybit_trigger(
                    symbol,
                    "STOP_MARKET",
                    close_side,
                    qty,
                    sl,
                    sl_direction,
                    "SL",
                )
                created.append(
                    ("SL", sl_order)
                )

                if not hold_all_reverse:
                    tp1_order = self.create_bybit_trigger(
                        symbol,
                        "TAKE_PROFIT_MARKET",
                        close_side,
                        tp1_qty,
                        tp1,
                        tp_direction,
                        "TP1",
                    )
                    created.append(
                        ("TP1", tp1_order)
                    )

                    tp2_order = self.create_bybit_trigger(
                        symbol,
                        "TAKE_PROFIT_MARKET",
                        close_side,
                        tp2_qty,
                        tp2,
                        tp_direction,
                        "TP2",
                    )
                    created.append(
                        ("TP2", tp2_order)
                    )

            elif self.exchange_id == "binance":
                sl_order = self.create_binance_trigger(
                    symbol, "STOP_MARKET", close_side, qty, sl, "SL"
                )
                created.append(("SL", sl_order))

                if not hold_all_reverse:
                    tp1_order = self.create_binance_trigger(
                        symbol, "TAKE_PROFIT_MARKET", close_side, tp1_qty, tp1, "TP1"
                    )
                    created.append(("TP1", tp1_order))
                    tp2_order = self.create_binance_trigger(
                        symbol, "TAKE_PROFIT_MARKET", close_side, tp2_qty, tp2, "TP2"
                    )
                    created.append(("TP2", tp2_order))
            else:
                # Gate / Bitget / WEEX.
                # CCXT maps triggerPrice and reduceOnly to each venue's
                # conditional-order API where supported.
                sl_order = self.create_generic_trigger(
                    symbol, close_side, qty, sl, "SL"
                )
                created.append(("SL", sl_order))

                if not hold_all_reverse:
                    tp1_order = self.create_generic_trigger(
                        symbol, close_side, tp1_qty, tp1, "TP1"
                    )
                    created.append(("TP1", tp1_order))
                    tp2_order = self.create_generic_trigger(
                        symbol, close_side, tp2_qty, tp2, "TP2"
                    )
                    created.append(("TP2", tp2_order))

        except Exception:
            # Never leave a half-created protection set behind.
            for _, order in created:
                try:
                    self.exchange.cancel_order(
                        order["id"],
                        symbol,                    )
                except Exception:
                    pass
            raise

        return created

    def verify_protection_orders(
        self,
        symbol,
        created_orders,
    ):
        """
        Verifies that the exchange still reports every newly
        created order as open.

        We deliberately do NOT declare protection active merely
        because create_order() returned without an exception.
        """

        time.sleep(0.7)

        results = []

        for label, order in created_orders:
            oid = str(order.get("id") or "")
            active = self._order_is_still_open(symbol, oid)

            if active:
                self.log(f"{label} VERIFIED ACTIVE. ID={oid}")
            else:
                self.log(f"{label} NOT FOUND / NOT ACTIVE. ID={oid}")

            results.append((label, active))

        return all(
            active
            for _, active in results
        )

    def _reconcile_protection_orders(self, position):
        """Keep exchange-side SL/TP protection synchronized with the position.

        Bybit displays these as *Conditional* orders.  ``Untriggered`` is
        normal for a pending stop/TP; it means the trigger has not fired yet.
        This routine is specifically for the dangerous case where a live
        position exists but one of the expected protective orders has
        disappeared.  The SL is treated as mandatory.
        """
        if not position or not self.last_protected_position:
            return

        protected = self.last_protected_position
        if protected.get("side") != position.get("side"):
            return

        # In bot-managed Hold-SL wait mode there is intentionally NO exchange
        # SL to reconcile.  The ROI threshold is monitored locally and the
        # strategy reversal closes the position after all active signals reverse.
        if protected.get("hold_sl_wait_reversal"):
            return

        now = time.time()
        if now - self.last_protection_reconcile < self.protection_reconcile_interval:
            return
        self.last_protection_reconcile = now

        sl_id = str(protected.get("sl_id") or "")
        tp1_id = str(protected.get("tp1_id") or "")
        tp2_id = str(protected.get("tp2_id") or "")

        def _is_open(oid):
            if not oid:
                return False
            result = self._order_is_still_open(
                self.symbol,
                oid,
                unknown_is_open=False,
            )
            if result is None:
                raise RuntimeError(
                    f"Could not verify protection order state for ID={oid}; "
                    "refusing to guess."
                )
            return bool(result)

        # When Hold-All-Reverse is ON, strategy reversal is the profit exit.
        # Remove any TP orders that may have been created before the setting was
        # enabled, and make SL the only exchange-side protection order.
        if self.v_hold_until_all_reverse.get():
            for label, oid in (("TP1", tp1_id), ("TP2", tp2_id)):
                if oid and _is_open(oid):
                    try:
                        self.exchange.cancel_order(oid, self.symbol)
                        self.log(f"{label} CANCELLED: Hold-All-Reverse is ON; strategy reversal is the exit.")
                    except Exception as e:
                        self.log(f"{label} CANCEL NOTICE: {e}")
            protected["tp1_id"] = None
            protected["tp2_id"] = None
            return

        expected = []
        if sl_id:
            expected.append(("SL/BE", sl_id))
        if not self.tp1_be_done and tp1_id:
            expected.append(("TP1", tp1_id))
        if tp2_id:
            expected.append(("TP2", tp2_id))

        missing = [(label, oid) for label, oid in expected if not _is_open(oid)]
        if not missing:
            return

        self.log(
            "PROTECTION WARNING: Live position has missing exchange order(s): "
            + ", ".join(label for label, _ in missing)
        )

        # First priority: restore a missing SL immediately.  Never leave a
        # live position relying only on TP orders.
        if sl_id and not _is_open(sl_id):
            try:
                remaining_qty = self.safe_amount(self.symbol, float(position.get("qty") or 0.0))
                sl_price = float(protected.get("sl") or 0.0)
                if remaining_qty > 0 and sl_price > 0:
                    close_side = "sell" if position["side"] == "LONG" else "buy"
                    if self.exchange_id == "bybit":
                        trigger_direction = 2 if position["side"] == "LONG" else 1
                        new_sl = self.create_bybit_trigger(
                            self.symbol, "STOP_MARKET", close_side, remaining_qty,
                            self.safe_price(self.symbol, sl_price),
                            trigger_direction, "SL REPLACEMENT"
                        )
                    elif self.exchange_id == "binance":
                        new_sl = self.create_binance_trigger(
                            self.symbol, "STOP_MARKET", close_side, remaining_qty,
                            self.safe_price(self.symbol, sl_price), "SL REPLACEMENT"
                        )
                    else:
                        new_sl = self.create_generic_trigger(
                            self.symbol, close_side, remaining_qty,
                            self.safe_price(self.symbol, sl_price), "SL REPLACEMENT"
                        )
                    protected["sl_id"] = new_sl.get("id")
                    self.log(
                        f"SL REPLACED ✓ | Price={sl_price:.12g} | Qty={remaining_qty:g}"
                    )
                    return
            except Exception as e:
                self.log(f"SL REPLACEMENT FAILED: {e}")

        # If a TP disappears, do not blindly recreate it if it may already
        # have filled.  _manage_tp1_break_even() remains the authority for
        # TP1 completion.  A missing TP2 while the position is still open can
        # safely be rebuilt from the original TP2 price.
        if tp2_id and not _is_open(tp2_id):
            try:
                remaining_qty = self.safe_amount(self.symbol, float(position.get("qty") or 0.0))
                tp2_price = float(protected.get("tp2") or 0.0)
                if remaining_qty > 0 and tp2_price > 0:
                    # If TP1 is not yet done, preserve the configured TP2
                    # quantity.  After TP1, the remaining position is TP2's
                    # natural quantity.
                    if self.tp1_be_done:
                        tp2_qty = remaining_qty
                    else:
                        tp2_qty = self.safe_amount(self.symbol, float(protected.get("qty") or remaining_qty) * 0.5)
                        if tp2_qty > remaining_qty:
                            tp2_qty = remaining_qty
                    close_side = "sell" if position["side"] == "LONG" else "buy"
                    if self.exchange_id == "bybit":
                        trigger_direction = 1 if position["side"] == "LONG" else 2
                        new_tp2 = self.create_bybit_trigger(
                            self.symbol, "TAKE_PROFIT_MARKET", close_side, tp2_qty,
                            self.safe_price(self.symbol, tp2_price),
                            trigger_direction, "TP2 REPLACEMENT"
                        )
                    elif self.exchange_id == "binance":
                        new_tp2 = self.create_binance_trigger(
                            self.symbol, "TAKE_PROFIT_MARKET", close_side, tp2_qty,
                            self.safe_price(self.symbol, tp2_price), "TP2 REPLACEMENT"
                        )
                    else:
                        new_tp2 = self.create_generic_trigger(
                            self.symbol, close_side, tp2_qty,
                            self.safe_price(self.symbol, tp2_price), "TP2 REPLACEMENT"
                        )
                    protected["tp2_id"] = new_tp2.get("id")
                    self.log(
                        f"TP2 REPLACED ✓ | Price={tp2_price:.12g} | Qty={tp2_qty:g}"
                    )
            except Exception as e:
                self.log(f"TP2 REPLACEMENT FAILED: {e}")

    def _detect_protection_exit_reason(self, protected):
        """Identify which exchange-side protection order caused a flat position.

        Returns one of: ``SL``, ``TP1``, ``TP2``, ``UNKNOWN``.  A break-even
        stop is represented by the current ``sl_id`` and is therefore treated
        as ``SL``.  This check is only made when a previously protected live
        position disappears; it is not polled on every normal loop.
        """
        if not protected:
            return "UNKNOWN"

        sl_id = str(protected.get("sl_id") or "")
        tp1_id = str(protected.get("tp1_id") or "")
        tp2_id = str(protected.get("tp2_id") or "")
        ids = {x for x in (sl_id, tp1_id, tp2_id) if x}
        if not ids:
            return "UNKNOWN"

        # Query the three known protection IDs directly. This avoids missing the
        # triggering order merely because it is outside a recent first-page list.
        for label, oid, reason in (
            ("SL/BE", sl_id, "SL"),
            ("TP1", tp1_id, "TP1"),
            ("TP2", tp2_id, "TP2"),
        ):
            if not oid:
                continue
            order = self._fetch_specific_order(self.symbol, oid)
            if not order:
                continue
            status = str(order.get("status") or "").lower()
            if status in ("closed", "filled", "triggered"):
                self.log(
                    f"EXIT REASON: {label} matched | Order={oid} | "
                    f"Status={status or 'closed'}"
                )
                return reason

        return "UNKNOWN"

    # -------------------- CLOSE / RECOVERY ------------------

    def close_position_market(
        self,
        symbol,
        position_side,
        qty,
    ):
        qty = self.safe_amount(
            symbol,
            qty,
        )

        if qty <= 0:
            return

        side = (
            "sell"
            if position_side == "LONG"
            else "buy"
        )

        self.log(
            "EMERGENCY: Closing unprotected position."
        )

        close_params = {
            "reduceOnly": True,
        }
        if self.exchange_id == "bybit":
            close_params["positionIdx"] = 0

        self.exchange.create_order(
            symbol,
            "market",
            side,
            qty,
            None,
            close_params,
        )

    # -------------------- GRID TRADING ENGINE ----------------

    def _grid_reset_state(self):
        self.grid_state = {"active": False, "mode": "OFF", "center": 0.0, "entry_orders": {}, "filled_levels": set(), "tp_order_id": None, "sl_order_id": None, "last_position_qty": 0.0, "last_position_entry": 0.0, "last_grid_reset": 0.0, "session_start_balance": 0.0, "peak_equity": 0.0, "paused_until": 0.0, "auto_direction": None}

    def _grid_order_qty(self, symbol, price, usdt_size):
        return self.safe_amount(symbol, usdt_size / price) if price > 0 and usdt_size > 0 else 0.0

    def _grid_place_limit(self, symbol, side, qty, price, reduce_only=False, label="GRID"):
        qty = self.safe_amount(symbol, qty); price = self.safe_price(symbol, price)
        if qty <= 0 or price <= 0: raise RuntimeError(f"{label}: invalid qty/price after exchange precision.")
        params = {"timeInForce": "GTC"}
        if reduce_only: params["reduceOnly"] = True
        if self.exchange_id == "bybit": params["positionIdx"] = 0
        order = self.exchange.create_order(symbol, "limit", side, qty, price, params)
        oid = str(order.get("id") or "")
        if not oid: raise RuntimeError(f"{label}: exchange returned no order ID.")
        self.log(f"{label} LIMIT submitted | {side.upper()} Qty={qty:g} Price={price:.12g} ID={oid}")
        return order

    def _grid_order_is_still_open(self, symbol, order_id):
        """Return True only when an order is verified open; fail closed on ambiguity."""
        return self._order_is_still_open(symbol, order_id)

    def _grid_cancel_managed_orders(self, symbol):
        """Cancel all Grid-owned orders and verify cancellation on the exchange."""
        entry_items = list(self.grid_state.get("entry_orders", {}).items())
        entry_ids = {str(meta.get("id")): key for key, meta in entry_items if meta.get("id")}
        protection_ids = {}
        if self.grid_state.get("tp_order_id"):
            protection_ids[str(self.grid_state["tp_order_id"])] = "tp"
        if self.grid_state.get("sl_order_id"):
            protection_ids[str(self.grid_state["sl_order_id"])] = "sl"
        pending_ids = set(entry_ids) | set(protection_ids)

        for attempt in range(1, 4):
            if not pending_ids:
                break
            for oid in list(pending_ids):
                try:
                    self.exchange.cancel_order(oid, symbol)
                    if self.exchange_id == "bybit":
                        time.sleep(0.06)
                    self.log(f"GRID CANCEL requested | ID={oid} | Attempt={attempt}")
                except Exception as e:
                    self.log(f"GRID CANCEL WARNING | ID={oid} | Attempt={attempt} | {e}")
            time.sleep(0.35)
            # Verify each managed ID individually.  A partial open-order
            # snapshot must never be interpreted as proof that an order was
            # cancelled.
            still_open = set()
            for oid in list(pending_ids):
                if self._grid_order_is_still_open(symbol, oid):
                    still_open.add(oid)
            pending_ids = still_open

        for key, meta in list(self.grid_state.get("entry_orders", {}).items()):
            oid = str(meta.get("id") or "")
            if oid and oid not in pending_ids:
                self.grid_state["entry_orders"].pop(key, None)
        tp_id = str(self.grid_state.get("tp_order_id") or "")
        sl_id = str(self.grid_state.get("sl_order_id") or "")
        if tp_id and tp_id not in pending_ids:
            self.grid_state["tp_order_id"] = None
        if sl_id and sl_id not in pending_ids:
            self.grid_state["sl_order_id"] = None

        if pending_ids:
            self.log("GRID CANCEL WARNING: orders still open after 3 attempts | " + ",".join(sorted(pending_ids)))
        else:
            self.log("GRID CANCEL VERIFIED: all managed Grid orders are closed/cancelled.")

    def _grid_cancel_entry_orders(self, symbol):
        """Cancel pending Grid entries while preserving basket TP/SL protection."""
        pending_ids = {
            str(meta.get("id"))
            for meta in self.grid_state.get("entry_orders", {}).values()
            if meta.get("id")
        }
        for attempt in range(1, 4):
            if not pending_ids:
                break
            for oid in list(pending_ids):
                try:
                    self.exchange.cancel_order(oid, symbol)
                    if self.exchange_id == "bybit":
                        time.sleep(0.06)
                    self.log(f"GRID ENTRY CANCEL requested | ID={oid} | Attempt={attempt}")
                except Exception as e:
                    self.log(f"GRID ENTRY CANCEL WARNING | ID={oid} | Attempt={attempt} | {e}")
            time.sleep(0.35)
            # Verify each Grid entry ID individually; do not trust a partial
            # open-order page when deciding that cancellation succeeded.
            still_open = set()
            for oid in list(pending_ids):
                if self._grid_order_is_still_open(symbol, oid):
                    still_open.add(oid)
            pending_ids = still_open

        for key, meta in list(self.grid_state.get("entry_orders", {}).items()):
            oid = str(meta.get("id") or "")
            if oid and oid not in pending_ids:
                self.grid_state["entry_orders"].pop(key, None)
        if pending_ids:
            self.log("GRID ENTRY CANCEL WARNING: entries still open after 3 attempts | " + ",".join(sorted(pending_ids)))
        else:
            self.log("GRID ENTRY CANCEL VERIFIED: all pending Grid entries are cancelled.")

    def _grid_validate_settings(self):
        """Validate Grid settings before startup and before any order is placed."""
        mode = self.v_grid_mode.get().strip().upper()
        if mode not in ("OFF", "DIRECT_SHOT", "LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID"):
            raise ValueError("Invalid Grid Mode.")

        levels = int(self.e_grid_levels.get())
        spacing_pct = float(self.e_grid_spacing.get())
        order_size = float(self.e_grid_order_size.get())
        size_inc_pct = float(self.e_grid_size_increase.get())
        tp_pct = float(self.e_grid_tp.get())
        sl_pct = float(self.e_grid_sl.get())
        max_exp = float(self.e_grid_max_exposure.get())
        max_dd_pct = float(self.e_grid_max_dd.get())
        grid_score_min = float(self.e_grid_score_min.get())
        rec_pct = float(self.e_grid_recenter.get())
        cooldown = float(self.e_grid_cooldown.get())
        filt = self.v_grid_trend_filter.get().strip().upper()

        if not 1 <= levels <= 50:
            raise ValueError("Grid Levels must be 1-50.")
        if spacing_pct <= 0 or spacing_pct > 50:
            raise ValueError("Grid Spacing must be greater than 0% and no more than 50%.")
        if spacing_pct * levels >= 100.0:
            raise ValueError("Grid Spacing × Grid Levels must be less than 100% so LONG/NEUTRAL grid prices never reach zero or become negative.")
        if order_size <= 0:
            raise ValueError("Grid Order Size must be greater than 0 USDT.")
        if size_inc_pct < 0:
            raise ValueError("Grid Size Increase cannot be negative.")
        if tp_pct <= 0:
            raise ValueError("Grid TP must be greater than 0%.")
        if sl_pct <= 0 or sl_pct >= 100:
            raise ValueError("Global Grid SL must be greater than 0% and less than 100%.")

        # Safety: Grid Global SL is calculated from the Grid center.  It must
        # remain beyond the deepest possible Grid entry so that even a single
        # fill at the outermost level has a valid SL < entry (LONG) or
        # SL > entry (SHORT).  This prevents a protection-installation failure
        # at the exact Grid boundary.
        if mode in ("LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID"):
            max_grid_depth_pct = spacing_pct * levels
            if sl_pct <= max_grid_depth_pct:
                raise ValueError(
                    f"Global Grid SL ({sl_pct:g}%) must be greater than "
                    f"Grid Spacing × Levels ({max_grid_depth_pct:g}%) so the "
                    f"Grid stop remains beyond every possible entry level."
                )

        if max_exp <= 0:
            raise ValueError("Grid Max Exposure must be greater than 0 USDT.")
        if max_dd_pct <= 0 or max_dd_pct >= 100:
            raise ValueError("Grid Max DD must be greater than 0% and less than 100%.")
        if grid_score_min <= 0:
            raise ValueError("Grid Score Min must be greater than 0.")

        # Grid SCORE is intentionally tied to Section 3 Strategy & Indicators.
        # There is ONE shared set of enable/disable switches and parameters:
        # the Grid does not maintain a second hidden copy of RSI/EMA/MACD/etc.
        # This keeps the Grid and normal Strategy calculations synchronized.
        enabled_strategy_count = sum(
            1 for enabled in (
                self.v_use_st.get(),
                self.v_use_ema.get(),
                self.v_use_ema_cross.get(),
                self.v_use_macd.get(),
                self.v_use_rsi.get(),
                self.v_use_bb.get(),
                self.v_use_stoch.get(),
                self.v_use_vwap.get(),
                self.v_use_vwap_delta.get(),
                self.v_use_vidya.get(),
                self.v_use_nwe.get(),
                self.v_use_liq_swings.get(),
                self.v_use_trendline.get(),
                self.v_use_mtf.get(),
                self.v_use_divergence.get(),
                self.v_use_vol_sr.get(),
                self.v_use_vol.get(),
                self.v_use_adx.get(),
                self.v_use_atr.get(),
            )
            if bool(enabled)
        )
        if filt == "SCORE":
            if enabled_strategy_count == 0:
                raise ValueError(
                    "Grid Trend Filter = SCORE requires at least one enabled "
                    "Strategy indicator in Section 3."
                )
            if str(self.v_signal_mode.get()).strip().upper() == "ADAPTIVE_SCORE":
                enabled_names = [
                    "ST","EMA","EMA_CROSS","MACD","RSI","BB","STOCH","VWAP","VWAP_DELTA","VIDYA","NWE",
                    "LIQ_SWING","TRENDLINE","MTF","DIVERGENCE","VOL_SR","VOL","ADX","ATR"
                ]
                enabled_flags = [
                    self.v_use_st.get(),self.v_use_ema.get(),self.v_use_ema_cross.get(),self.v_use_macd.get(),self.v_use_rsi.get(),self.v_use_bb.get(),self.v_use_stoch.get(),self.v_use_vwap.get(),self.v_use_vwap_delta.get(),self.v_use_vidya.get(),self.v_use_nwe.get(),self.v_use_liq_swings.get(),self.v_use_trendline.get(),self.v_use_mtf.get(),self.v_use_divergence.get(),self.v_use_vol_sr.get(),self.v_use_vol.get(),self.v_use_adx.get(),self.v_use_atr.get()
                ]
                adaptive_max = sum(ADAPTIVE_MODULE_WEIGHTS.get(n,1.0) for n,e in zip(enabled_names,enabled_flags) if bool(e) and n not in ("VOL","ATR"))
                if grid_score_min > adaptive_max:
                    raise ValueError(f"Grid Score Min cannot be greater than adaptive weighted module capacity ({adaptive_max:.2f}).")
            elif grid_score_min > enabled_strategy_count:
                raise ValueError(
                    f"Grid Score Min cannot be greater than the number of enabled "
                    f"Section 3 Strategy indicators ({enabled_strategy_count})."
                )

        if rec_pct < 0:
            raise ValueError("Grid Recenter Distance cannot be negative.")
        if cooldown < 0:
            raise ValueError("Grid Cooldown cannot be negative.")
        if filt not in ("OFF", "SUPERTREND", "SCORE"):
            raise ValueError("Grid Trend Filter must be OFF, SUPERTREND, or SCORE.")

        # NEUTRAL_GRID is the only Grid mode that can automatically change
        # between LONG and SHORT.  Its direction source is controlled by the
        # Grid Trend Filter:
        #   SUPERTREND -> follow the completed-candle Supertrend direction.
        #   SCORE      -> follow the complete Section 3 directional score.
        #   OFF        -> for NEUTRAL only, use the same complete Section 3
        #                 score as the automatic direction source.
        #
        # LONG_GRID / SHORT_GRID keep their existing behavior unchanged.
        if mode == "NEUTRAL_GRID":
            if filt == "SUPERTREND" and not bool(self.v_use_st.get()):
                raise ValueError(
                    "NEUTRAL_GRID + SUPERTREND requires Supertrend to be enabled in Section 3."
                )
            if filt in ("OFF", "SCORE"):
                if enabled_strategy_count == 0:
                    raise ValueError(
                        "NEUTRAL_GRID requires at least one enabled Section 3 Strategy indicator "
                        "when Trend Filter is OFF/SCORE."
                    )
                if str(self.v_signal_mode.get()).strip().upper() == "ADAPTIVE_SCORE":
                    adaptive_min = float(self.e_adaptive_min_weight.get())
                    if grid_score_min < adaptive_min:
                        grid_score_min = adaptive_min
                elif grid_score_min > enabled_strategy_count:
                    raise ValueError(
                        f"Grid Score Min cannot be greater than the number of enabled "
                        f"Section 3 Strategy indicators ({enabled_strategy_count}) for NEUTRAL_GRID."
                    )

        return {
            "mode": mode, "levels": levels, "spacing": spacing_pct / 100.0,
            "order_size": order_size, "size_inc": size_inc_pct / 100.0,
            "tp_pct": tp_pct / 100.0, "sl_pct": sl_pct / 100.0,
            "max_exposure": max_exp, "max_dd": max_dd_pct / 100.0,
            "score_min": grid_score_min,
            "adaptive_score": str(self.v_signal_mode.get()).strip().upper() == "ADAPTIVE_SCORE",
            "adaptive_min_weight": float(self.e_adaptive_min_weight.get()),
            "trend_filter": filt, "recenter": bool(self.v_grid_recenter.get()),
            "recenter_distance": rec_pct / 100.0, "cooldown": cooldown * 60.0,
        }

    def _grid_initialize(self, symbol, balance, equity):
        cfg = self._grid_validate_settings(); self._grid_reset_state()
        if cfg["mode"] in ("OFF", "DIRECT_SHOT"): return cfg
        if self.fetch_position(symbol): raise RuntimeError("GRID START BLOCKED: an existing position is open on this symbol.")
        if self.fetch_open_orders_safe(symbol): raise RuntimeError("GRID START BLOCKED: existing open orders found on this symbol.")
        center = self._current_market_price(symbol)
        self.grid_state.update({"active":True,"mode":cfg["mode"],"center":center,"session_start_balance":float(balance),"peak_equity":float(equity),"last_grid_reset":time.time()})
        self.log(f"GRID ENGINE STARTED | Mode={cfg['mode']} | Center={center:.12g} | Levels={cfg['levels']} | Spacing={cfg['spacing']*100:g}% | OrderSize={cfg['order_size']:g} USDT | TP={cfg['tp_pct']*100:g}% | GlobalSL={cfg['sl_pct']*100:g}% | MaxExposure={cfg['max_exposure']:g} USDT | TrendFilter={cfg['trend_filter']} | GridScoreMin={cfg['score_min']}")
        return cfg

    def _grid_trend_allowed(self, cfg, st_bull, st_bear, buy_score, sell_score):
        if cfg["trend_filter"] == "OFF":
            return True, True
        if cfg["trend_filter"] == "SUPERTREND":
            return bool(st_bull), bool(st_bear)
        score_min = float(cfg["score_min"])
        if cfg.get("adaptive_score"):
            score_min = max(score_min, float(cfg.get("adaptive_min_weight", ADAPTIVE_DEFAULT_MIN_WEIGHT)))
        return (
            buy_score >= score_min and buy_score > sell_score,
            sell_score >= score_min and sell_score > buy_score,
        )

    def _grid_place_entries(self, symbol, cfg, allow_long=True, allow_short=True, neutral_direction=None):
        center = float(self.grid_state["center"])
        existing = self.grid_state["entry_orders"]
        planned = sum(float(x.get("usdt", 0)) for x in existing.values())
        current_position = self.fetch_position(symbol)
        current_exposure = (
            abs(float(current_position["qty"])) * float(current_position["entry"])
            if current_position else 0.0
        )
        planned_total = current_exposure + planned

        for n in range(1, cfg["levels"] + 1):
            if cfg["mode"] == "SHORT_GRID":
                side = "sell"
                price = center * (1 + cfg["spacing"] * n)
                allowed = allow_short
            elif cfg["mode"] == "NEUTRAL_GRID":
                # NEUTRAL_GRID is an AUTO-DIRECTION grid.  It places only the
                # side selected by the current strategy direction:
                #   LONG  -> BUY orders below the center
                #   SHORT -> SELL orders above the center
                if neutral_direction == "SHORT":
                    side = "sell"
                    price = center * (1 + cfg["spacing"] * n)
                    allowed = allow_short
                else:
                    side = "buy"
                    price = center * (1 - cfg["spacing"] * n)
                    allowed = allow_long
            else:
                side = "buy"
                price = center * (1 - cfg["spacing"] * n)
                allowed = allow_long

            if not allowed:
                continue

            key = f"{side}:{n}"
            if key in existing or key in self.grid_state.get("filled_levels", set()):
                continue

            usdt = cfg["order_size"] * ((1 + cfg["size_inc"]) ** (n - 1))
            if planned_total + usdt > cfg["max_exposure"]:
                break

            qty = self._grid_order_qty(symbol, price, usdt)
            if qty <= 0:
                continue

            order = self._grid_place_limit(
                symbol, side, qty, price, False, f"GRID L{n}"
            )
            existing[key] = {
                "id": str(order["id"]),
                "side": side,
                "price": price,
                "qty": qty,
                "usdt": usdt,
                "level": n,
            }
            planned += usdt
            planned_total += usdt

        # Checkpoint Grid order IDs after the placement batch so a process
        # interruption cannot force the next launch to recreate known levels.
        self._persist_runtime_state(status="RUNNING")

    def _grid_cancel_disallowed_entries(self, symbol, allow_long, allow_short):
        """Cancel pending Grid entries whose direction is currently blocked by the strategy filter."""
        for key, meta in list(self.grid_state.get("entry_orders", {}).items()):
            side = str(meta.get("side", "")).lower()
            allowed = (
                allow_long if side == "buy"
                else allow_short if side == "sell"
                else False
            )
            if allowed:
                continue
            oid = str(meta.get("id") or "")
            if oid:
                try:
                    self.exchange.cancel_order(oid, symbol)
                    if self.exchange_id == "bybit":
                        time.sleep(0.06)
                    time.sleep(0.15)
                    if self._grid_order_is_still_open(symbol, oid):
                        self.log(
                            f"GRID FILTER CANCEL NOT VERIFIED | ID={oid} | "
                            "Keeping local order state to prevent duplicate recreation."
                        )
                        continue
                except Exception as e:
                    self.log(f"GRID FILTER CANCEL WARNING: {e} | ID={oid}")
                    continue
            self.grid_state["entry_orders"].pop(key, None)

    def _grid_sync_orders(self, symbol):
        open_orders = self.fetch_open_orders_safe(symbol)
        open_ids = {str(o.get("id")) for o in open_orders if o.get("id")}
        position = self.fetch_position(symbol)

        for key, meta in list(self.grid_state["entry_orders"].items()):
            oid = str(meta.get("id") or "")
            if not oid or oid in open_ids:
                continue

            # IMPORTANT: fetch_open_orders() can be paged/limited by the
            # exchange.  A missing ID in one page is NOT proof that the order
            # was filled/cancelled.  Verify the individual order before
            # removing it from local Grid state.  This prevents duplicate
            # Grid orders when the open-order snapshot is incomplete.
            try:
                order = self._fetch_specific_order(symbol, oid)
                if not order:
                    self.log(
                        f"GRID SYNC VERIFY NOTICE: no definitive order record for ID={oid}; "
                        "retaining local order state."
                    )
                    continue
                status = str(order.get("status") or "").lower()
                filled = float(order.get("filled") or 0.0)
                if status in ("open", "new", "partially_filled", "pending"):
                    continue

                if status in ("closed", "filled") and filled > 0:
                    self.grid_state["filled_levels"].add(key)
                    self.grid_state["entry_orders"].pop(key, None)
                    continue

                if status in ("canceled", "cancelled", "rejected", "expired"):
                    self.grid_state["entry_orders"].pop(key, None)
                    continue

                # Unknown/inconclusive status: retain local state rather than
                # placing a replacement that could duplicate the exchange order.
                self.log(
                    f"GRID SYNC NOTICE: inconclusive status for ID={oid} "
                    f"({status or 'unknown'}); retaining local order state."
                )
            except Exception as e:
                # Fail closed: an API/read error is not evidence that the Grid
                # order disappeared.
                self.log(
                    f"GRID SYNC VERIFY NOTICE: could not verify ID={oid}: {e}; "
                    "retaining local order state."
                )

    def _grid_manage_protection(self, symbol, cfg, position):
        """Synchronize Grid basket TP/SL without leaving a half-protected position."""
        if not position or float(position.get("qty") or 0) <= 0:
            protection_ids = [
                str(oid)
                for oid in (
                    self.grid_state.get("tp_order_id"),
                    self.grid_state.get("sl_order_id"),
                )
                if oid
            ]
            for oid in protection_ids:
                cancelled = False
                for attempt in range(1, 4):
                    try:
                        self.exchange.cancel_order(oid, symbol)
                        time.sleep(0.2)
                    except Exception as e:
                        self.log(
                            f"GRID FLAT PROTECTION CANCEL WARNING | ID={oid} | "
                            f"Attempt={attempt} | {e}"
                        )
                    if not self._order_is_still_open(symbol, oid):
                        cancelled = True
                        break
                if not cancelled:
                    raise RuntimeError(
                        f"Grid is flat but old protection order {oid} could not be "
                        "verified cancelled; refusing to place a new Grid cycle."
                    )

            self.grid_state["tp_order_id"] = None
            self.grid_state["sl_order_id"] = None
            self.grid_state["last_position_qty"] = 0.0
            self.grid_state["last_position_entry"] = 0.0
            self.grid_state["filled_levels"] = set()
            return

        side = position["side"]
        entry = float(position["entry"])
        qty = self.safe_amount(symbol, position["qty"])
        if qty <= 0 or entry <= 0:
            return

        last_qty = float(self.grid_state.get("last_position_qty") or 0.0)
        last_entry = float(self.grid_state.get("last_position_entry") or 0.0)

        # Do not trust locally stored protection IDs forever.  A Grid TP/SL can
        # disappear because of manual cancellation, exchange-side rejection,
        # or an external order change.  If the position is unchanged, verify
        # both IDs are still open before returning early.
        existing_tp_id = str(self.grid_state.get("tp_order_id") or "")
        existing_sl_id = str(self.grid_state.get("sl_order_id") or "")
        same_position = (
            existing_tp_id
            and existing_sl_id
            and abs(qty - last_qty) <= 1e-12
            and abs(entry - last_entry) <= max(entry * 1e-9, 1e-12)
        )
        if same_position:
            tp_open = self._order_is_still_open(symbol, existing_tp_id)
            sl_open = self._order_is_still_open(symbol, existing_sl_id)
            if tp_open and sl_open:
                return

            missing = []
            if not tp_open:
                missing.append("TP")
            if not sl_open:
                missing.append("SL")
            self.log(
                "GRID PROTECTION REBUILD: missing exchange-side "
                + "/".join(missing)
                + " order(s) detected."
            )

        old_tp_id = self.grid_state.get("tp_order_id")
        old_sl_id = self.grid_state.get("sl_order_id")
        tp = entry * (1 + cfg["tp_pct"]) if side == "LONG" else entry * (1 - cfg["tp_pct"])
        sl = self.grid_state["center"] * (1 - cfg["sl_pct"]) if side == "LONG" else self.grid_state["center"] * (1 + cfg["sl_pct"])
        tp = self.safe_price(symbol, tp)
        sl = self.safe_price(symbol, sl)
        if (side == "LONG" and not (sl < entry < tp)) or (side == "SHORT" and not (tp < entry < sl)):
            raise RuntimeError(f"GRID protection prices invalid after exchange precision: side={side}, entry={entry}, TP={tp}, SL={sl}")

        close_side = "sell" if side == "LONG" else "buy"
        new_sl = None
        new_tp = None
        try:
            # Install SL first; the old protection is deliberately retained until
            # the complete replacement set has been verified.
            if self.exchange_id == "bybit":
                new_sl = self.create_bybit_trigger(
                    symbol, "STOP_MARKET", close_side, qty, sl,
                    2 if side == "LONG" else 1, "GRID GLOBAL SL"
                )
            elif self.exchange_id == "binance":
                new_sl = self.create_binance_trigger(
                    symbol, "STOP_MARKET", close_side, qty, sl, "GRID GLOBAL SL"
                )
            else:
                new_sl = self.create_generic_trigger(
                    symbol, close_side, qty, sl, "GRID GLOBAL SL"
                )

            new_tp = self._grid_place_limit(
                symbol, close_side, qty, tp, True, "GRID BASKET TP"
            )

            time.sleep(0.5)
            new_sl_id = str(new_sl.get("id") or "")
            new_tp_id = str(new_tp.get("id") or "")
            if (
                not self._order_is_still_open(symbol, new_sl_id)
                or not self._order_is_still_open(symbol, new_tp_id)
            ):
                raise RuntimeError("New Grid TP/SL could not be verified as active.")
        except Exception as e:
            # Roll back only newly created orders. The old protection remains.
            for order in (new_tp, new_sl):
                oid = str(order.get("id") or "") if order else ""
                if oid:
                    try:
                        self.exchange.cancel_order(oid, symbol)
                    except Exception:
                        pass
            raise RuntimeError(f"GRID protection installation failed: {e}") from e

        # New protection is confirmed active; obsolete orders can now be removed.
        for oid in (old_tp_id, old_sl_id):
            if oid and oid not in (str(new_tp.get("id")), str(new_sl.get("id"))):
                try:
                    self.exchange.cancel_order(oid, symbol)
                except Exception as e:
                    self.log(f"GRID OLD PROTECTION CANCEL NOTICE: {e} | ID={oid}")

        self.grid_state["tp_order_id"] = str(new_tp["id"])
        self.grid_state["sl_order_id"] = str(new_sl["id"])
        self.grid_state["last_position_qty"] = qty
        self.grid_state["last_position_entry"] = entry
        self.log(f"GRID PROTECTION | {side} Avg={entry:.12g} Qty={qty:g} | TP={tp:.12g} | GlobalSL={sl:.12g}")
        self._persist_runtime_state(status="RUNNING")

    def _grid_stop(self, symbol, reason, cooldown_seconds=0):
        """Stop Grid safely: close inventory before removing its protection."""
        self.log(f"GRID STOP: {reason}")
        self._remember_managed_order_ids(self._known_managed_order_ids(symbol))
        self._grid_cancel_entry_orders(symbol)
        pos = self.fetch_position(symbol)
        close_succeeded = True
        if pos:
            try:
                self.close_position_market(symbol, pos["side"], pos["qty"])
                time.sleep(0.5)
                if self.fetch_position(symbol):
                    close_succeeded = False
                    self.log("GRID STOP WARNING: position still open; keeping TP/SL protection active.")
            except Exception as e:
                close_succeeded = False
                self.log(f"GRID close warning: {e} | Keeping exchange-side Grid protection active.")
        if close_succeeded:
            # Once the Grid symbol is confirmed flat, remove ALL remaining
            # symbol orders. This is deliberately broader than local Grid state
            # so an untracked/duplicate order from a previous failed cycle cannot
            # survive a manual stop.
            try:
                self._cancel_known_managed_orders(symbol)
            except Exception as e:
                self.log(
                    f"GRID STOP SAFETY: symbol-wide order cancellation could not "
                    f"be verified: {e}"
                )
        else:
            self.log("GRID STOP SAFETY: Grid inactive; existing TP/SL were NOT cancelled because the position could not be confirmed flat.")
        self.grid_state["active"] = False
        self.grid_state["paused_until"] = time.time() + cooldown_seconds
        self.grid_state["filled_levels"] = set()

    def _grid_neutral_direction(self, cfg, st_bull, st_bear, buy_score, sell_score):
        """Return LONG, SHORT, or None for NEUTRAL_GRID auto-direction.

        NEUTRAL_GRID is the only Grid mode that interprets the current strategy
        direction and can switch the Grid from one side to the other.
        SUPERTREND follows the Supertrend state. SCORE/OFF use the complete
        Section 3 directional module score already calculated by the strategy
        engine. A tie or insufficient score produces no new Grid entries.
        """
        filt = cfg["trend_filter"]
        if filt == "SUPERTREND":
            if bool(st_bull) and not bool(st_bear):
                return "LONG"
            if bool(st_bear) and not bool(st_bull):
                return "SHORT"
            return None

        score_min = float(cfg["score_min"])
        if cfg.get("adaptive_score"):
            score_min = max(score_min, float(cfg.get("adaptive_min_weight", ADAPTIVE_DEFAULT_MIN_WEIGHT)))
        if buy_score >= score_min and buy_score > sell_score:
            return "LONG"
        if sell_score >= score_min and sell_score > buy_score:
            return "SHORT"
        return None

    def _grid_switch_neutral_direction(self, symbol, cfg, new_direction):
        """Safely switch an active NEUTRAL_GRID between LONG and SHORT.

        Pending entries are cancelled first. If an opposite position already
        exists, it is closed and verified flat before old Grid protection is
        removed. The Grid center is reset to the current market price so the
        newly selected side starts from a coherent basket.
        """
        previous = self.grid_state.get("auto_direction")
        if previous == new_direction:
            return True

        self.log(
            f"NEUTRAL GRID DIRECTION CHANGE | "
            f"{previous or 'NONE'} -> {new_direction or 'NONE'}"
        )

        # Always remove pending entries before changing direction. This prevents
        # an old-side limit order from filling after the strategy has reversed.
        self._grid_cancel_entry_orders(symbol)

        if new_direction is None:
            self.grid_state["auto_direction"] = None
            return True

        position = self.fetch_position(symbol)
        if position:
            desired_side = "LONG" if new_direction == "LONG" else "SHORT"

            if position["side"] == desired_side:
                # The existing inventory is already on the desired side. Do NOT
                # cancel its protection just because the strategy briefly went
                # neutral and then returned to the same direction. Keep the
                # live TP/SL protection and continue managing the basket.
                self.grid_state["auto_direction"] = new_direction
                self.log(
                    f"NEUTRAL GRID DIRECTION RESTORED | Existing "
                    f"{position['side']} position retained."
                )
                return True

            self.log(
                f"NEUTRAL GRID REVERSAL | Existing {position['side']} position "
                f"-> {desired_side}; closing existing Grid inventory first."
            )
            try:
                self.close_position_market(
                    symbol, position["side"], position["qty"]
                )
                time.sleep(0.5)
                position = self.fetch_position(symbol)
            except Exception as e:
                self.log(f"NEUTRAL GRID REVERSAL FAILED: {e}")
                self._grid_stop(
                    symbol,
                    f"Neutral direction switch failed: {e}",
                    cfg["cooldown"],
                )
                return False

            if position:
                self.log(
                    "NEUTRAL GRID REVERSAL SAFETY: opposite position is still "
                    "open; keeping protection active and stopping Grid."
                )
                self._grid_stop(
                    symbol,
                    "Neutral direction switch could not verify flat position",
                    cfg["cooldown"],
                )
                return False

        # Only after the symbol is confirmed flat is it safe to remove old
        # basket TP/SL protection. Retain exact IDs in recovery state first.
        self._remember_managed_order_ids(self._known_managed_order_ids(symbol))
        self._grid_cancel_managed_orders(symbol)
        if self.fetch_position(symbol):
            self.log(
                "NEUTRAL GRID SAFETY: position reappeared after cleanup; "
                "direction switch aborted."
            )
            return False

        self.grid_state["filled_levels"] = set()
        self.grid_state["entry_orders"] = {}
        self.grid_state["tp_order_id"] = None
        self.grid_state["sl_order_id"] = None
        self.grid_state["last_position_qty"] = 0.0
        self.grid_state["last_position_entry"] = 0.0
        self.grid_state["center"] = self._current_market_price(symbol)
        self.grid_state["auto_direction"] = new_direction

        self.log(
            f"NEUTRAL GRID NOW FOLLOWING {new_direction} | "
            f"New Center={self.grid_state['center']:.12g}"
        )
        return True

    def _manage_grid(self, symbol, balance, equity, cfg, st_bull, st_bear, grid_buy_score, grid_sell_score):
        if cfg["mode"] in ("OFF", "DIRECT_SHOT"):
            return False

        # Grid mode owns execution while selected. A Grid stop/cooldown must
        # never fall through into the normal Direct Shot/SCORE entry engine.
        if not self.grid_state.get("active"):
            return True
        if self.grid_state.get("paused_until", 0) > time.time():
            return True

        self.grid_state["peak_equity"] = max(
            self.grid_state.get("peak_equity", equity), equity
        )
        start = max(
            self.grid_state.get("session_start_balance", balance), 1e-12
        )
        peak = max(
            self.grid_state.get("peak_equity", equity), 1e-12
        )
        if max((start - equity) / start, (peak - equity) / peak, 0) >= cfg["max_dd"]:
            self._grid_stop(
                symbol, "Grid drawdown limit reached", cfg["cooldown"]
            )
            return True

        price = self._current_market_price(symbol)
        center = self.grid_state["center"]

        if (
            cfg["recenter"]
            and not self.fetch_position(symbol)
            and center > 0
            and abs(price - center) / center >= cfg["recenter_distance"]
        ):
            self._grid_cancel_managed_orders(symbol)
            self.grid_state["center"] = price
            center = price
            self.log(
                f"GRID RECENTERED | New center={price:.12g}"
            )

        allow_long, allow_short = self._grid_trend_allowed(
            cfg, st_bull, st_bear, grid_buy_score, grid_sell_score
        )

        self._grid_sync_orders(symbol)
        pos = self.fetch_position(symbol)

        # Fixed-direction modes remain exactly as before: they never auto-switch.
        if cfg["mode"] == "LONG_GRID" and pos and pos["side"] != "LONG":
            self._grid_stop(
                symbol,
                "Unexpected SHORT position in LONG_GRID",
                cfg["cooldown"],
            )
            return True

        if cfg["mode"] == "SHORT_GRID" and pos and pos["side"] != "SHORT":
            self._grid_stop(
                symbol,
                "Unexpected LONG position in SHORT_GRID",
                cfg["cooldown"],
            )
            return True

        neutral_direction = None

        if cfg["mode"] == "NEUTRAL_GRID":
            # NEUTRAL_GRID is now the automatic directional Grid:
            # SUPERTREND -> follow Supertrend;
            # SCORE/OFF -> follow the complete Section 3 indicator score.
            neutral_direction = self._grid_neutral_direction(
                cfg, st_bull, st_bear, grid_buy_score, grid_sell_score
            )

            if not self._grid_switch_neutral_direction(
                symbol, cfg, neutral_direction
            ):
                return True

            # Re-read the position after any safe direction transition.
            pos = self.fetch_position(symbol)

            if neutral_direction == "LONG":
                allow_long, allow_short = True, False
            elif neutral_direction == "SHORT":
                allow_long, allow_short = False, True
            else:
                # No consensus: cancel pending entries, but do not forcibly
                # close an existing protected position merely because the
                # indicators are temporarily tied/neutral.
                allow_long, allow_short = False, False

        # Strategy/SCORE and Supertrend filters must also control already-open
        # pending Grid entries. Otherwise an entry blocked by the current
        # strategy state could still fill later and bypass the filter.
        self._grid_cancel_disallowed_entries(
            symbol, allow_long, allow_short
        )

        # Clear stale basket protection before rebuilding a flat grid cycle.
        if not pos:
            self._grid_manage_protection(symbol, cfg, None)

        self._grid_place_entries(
            symbol,
            cfg,
            allow_long,
            allow_short,
            neutral_direction=neutral_direction,
        )
        pos = self.fetch_position(symbol)

        try:
            self._grid_manage_protection(symbol, cfg, pos)
        except Exception as protection_error:
            # IMPORTANT: Grid execution skips the normal Strategy trade
            # recovery block below. Therefore Grid must fail closed here:
            # if a live Grid position cannot obtain verified TP+SL protection,
            # stop Grid and attempt to flatten the inventory immediately.
            self.log(
                f"GRID PROTECTION ERROR: {protection_error} | "
                "Failing closed and stopping Grid."
            )
            self._grid_stop(
                symbol,
                f"Grid protection installation/reconciliation failed: {protection_error}",
                cfg["cooldown"],
            )
            return True

        if pos and abs(float(pos["qty"])) * float(pos["entry"]) > cfg["max_exposure"]:
            self._grid_stop(
                symbol,
                "Maximum grid exposure exceeded",
                cfg["cooldown"],
            )
        return True

    # -------------------- ENTRY ------------------------------

    def open_market_position(
        self,
        symbol,
        signal,
        qty,
    ):
        side = (
            "buy"
            if signal == "BUY"
            else "sell"
        )

        order_params = {}
        if self.exchange_id == "bybit":
            order_params["positionIdx"] = 0

        order = self.exchange.create_order(
            symbol,
            "market",
            side,
            qty,
            None,
            order_params,
        )

        actual_order_price = (
            self.get_actual_order_price(
                order
            )
        )

        if actual_order_price:
            self.log(
                f"Entry order fill/average reported: "
                f"{actual_order_price}"
            )

        expected_side = (
            "LONG"
            if signal == "BUY"
            else "SHORT"
        )

        position = self.wait_for_position(
            symbol,
            expected_side,
            timeout=10,
        )

        if not position:
            raise RuntimeError(
                "Entry order was submitted, but the actual "
                "position could not be confirmed."
            )

        # Position's average entry is the source of truth.
        actual_entry = position["entry"]

        if actual_entry <= 0:
            if actual_order_price:
                actual_entry = actual_order_price
            else:
                raise RuntimeError(
                    "Actual entry price could not be determined."
                )

        return position, actual_entry

    # -------------------- LEVERAGE ---------------------------

    def configure_leverage(
        self,
        symbol,
        leverage,
    ):
        """
        Set leverage before trading.

        Bybit returns error code 110043 ("leverage not modified") when the
        requested leverage is already the current leverage.  That is a
        successful no-op, not a configuration failure, so startup must not
        abort in that case.  Other leverage errors remain fail-closed.
        """
        leverage = int(leverage)
        if leverage <= 0:
            raise ValueError("Leverage must be greater than 0.")

        try:
            result = self.exchange.set_leverage(leverage, symbol)
            self.log(
                f"Leverage set/requested: {leverage}x"
                + (f" | Exchange response={result}" if result else "")
            )
        except Exception as e:
            error_text = str(e)
            error_lower = error_text.lower()

            # Bybit retCode 110043 means the requested leverage is already
            # applied. CCXT may expose it as an exception even though no
            # exchange-side change is required. Treat this as success.
            already_set = (
                self.exchange_id == "bybit"
                and "110043" in error_text
                and "leverage not modified" in error_lower
            )

            if already_set:
                self.log(
                    f"Leverage already {leverage}x for {symbol}; "
                    "Bybit returned 110043 (leverage not modified). "
                    "Continuing startup safely."
                )
                return

            raise RuntimeError(
                f"Could not set leverage to {leverage}x for {symbol}. "
                f"Bot startup aborted for safety. Exchange error: {e}"
            ) from e

    # -------------------- START / STOP ----------------------

    def _validate_v83_preflight(self):
        """Validate cross-module settings before any exchange-side mutation."""
        exchange_id = str(self.v_exchange.get()).strip().lower()
        if exchange_id not in SUPPORTED_EXCHANGES:
            raise ValueError(f"Unsupported exchange: {exchange_id}")
        signal_mode = str(self.v_signal_mode.get()).strip().upper()
        if signal_mode not in SUPPORTED_SIGNAL_MODES:
            raise ValueError(f"Unsupported signal mode: {signal_mode}")
        leverage = int(str(self.e_lev.get()).strip())
        if leverage <= 0:
            raise ValueError("Leverage must be greater than 0.")
        max_trades = int(str(self.e_max_trades.get()).strip())
        if max_trades < 0:
            raise ValueError("Max Trades cannot be negative.")
        min_score = int(str(self.e_min_score.get()).strip())
        if min_score < 1:
            raise ValueError("Minimum Signal Score must be at least 1.")
        adaptive_edge = float(str(self.e_adaptive_edge.get()).strip())
        adaptive_min_weight = float(str(self.e_adaptive_min_weight.get()).strip())
        if not 0.0 < adaptive_edge < 1.0:
            raise ValueError("Adaptive Edge must be between 0 and 1.")
        if adaptive_min_weight <= 0:
            raise ValueError("Adaptive Min Weight must be greater than 0.")
        evidence_min_families = int(str(self.evidence_min_families.get()).strip())
        evidence_family_min_score = float(str(self.evidence_family_min_score.get()).strip())
        if evidence_min_families < 1 or evidence_min_families > 4:
            raise ValueError("Evidence Min Families must be between 1 and 4.")
        if not 0.0 < evidence_family_min_score <= 1.0:
            raise ValueError("Family Evidence Min must be greater than 0 and at most 1.")
        size_mode = str(self.v_size_mode.get()).strip().upper()
        if size_mode not in ("EQUITY_RISK_%", "FIXED_QTY"):
            raise ValueError("Sizing Mode must be EQUITY_RISK_% or FIXED_QTY.")
        risk_pct = float(str(self.e_risk_pct.get()).strip())
        fixed_qty = float(str(self.e_fixed_qty.get()).strip())
        if risk_pct <= 0 or risk_pct >= 100:
            raise ValueError("Risk Per Trade must be greater than 0% and less than 100%.")
        if fixed_qty <= 0:
            raise ValueError("Fixed Qty must be greater than 0.")
        max_dd = float(str(self.e_max_dd.get()).strip())
        emergency_loss = float(str(self.e_emergency_capital_pct.get()).strip())
        if not 0.0 <= max_dd < 100.0:
            raise ValueError("Max Daily Drawdown must be between 0% and less than 100%.")
        if not 0.0 <= emergency_loss < 100.0:
            raise ValueError("Emergency Capital Loss Stop must be between 0% and less than 100%.")
        emergency_scope = str(self.v_emergency_scope.get()).strip().upper()
        if emergency_scope not in ("BOT_SYMBOL", "ALL_ACCOUNT"):
            raise ValueError("Emergency Scope must be BOT_SYMBOL or ALL_ACCOUNT.")
        cooldown = float(str(self.e_cooldown_min.get()).strip())
        if cooldown < 0:
            raise ValueError("Cooldown cannot be negative.")
        self._grid_validate_settings()
        return True

    def start_bot(self):
        if self.is_running:
            return

        try:
            self.save_settings()
            self._validate_v83_preflight()

            # Validate credentials BEFORE acquiring the profile lock.  A missing
            # key/secret must never leave a bot.lock file behind.
            api_key = self.e_api_key.get().strip()
            api_secret = self.e_api_secret.get().strip()
            if not api_key or not api_secret:
                messagebox.showerror(
                    "Missing API credentials",
                    "Enter API Key and API Secret first.",
                )
                return

            self._acquire_profile_lock()

            exchange_id = (
                self.v_exchange.get()
                .strip()
                .lower()
            )

            account_mode = (
                self.v_account_mode.get()
                .strip()
                .upper()
            )

            self.exchange_id = exchange_id

            self.exchange = self.build_exchange(
                exchange_id,
                api_key,
                api_secret,
                account_mode,
            )

            self.log(
                f"{APP_VERSION} MODULAR ENGINE: "
                f"{exchange_id.upper()} | "
                "CCXT unified futures/swap API"
            )

            self.symbol = (
                self.normalize_symbol(
                    self.exchange,
                    exchange_id,
                    self.e_symbol.get(),
                )
            )

            leverage = int(
                self.e_lev.get().strip()
            )

            # Validate Grid controls before touching exchange leverage.
            # Recovery is deliberately a separate path: it restores the saved
            # local state and then verifies the live exchange state instead of
            # rejecting an otherwise recoverable bot position.
            self._grid_validate_settings()
            resume_mode = bool(self.resume_requested and self.resume_candidate)

            try:
                max_trades = int(self.e_max_trades.get().strip())
            except Exception:
                raise ValueError("Max Trades must be a whole number. Use 0 for unlimited.")
            if max_trades < 0:
                raise ValueError("Max Trades cannot be negative.")

            current_balance = self.fetch_balance_total()
            current_equity = self.fetch_account_equity()

            if resume_mode:
                self._restore_runtime_state(self.resume_candidate)
                # The saved session balance is authoritative for resumed
                # drawdown/PnL accounting. If an old checkpoint has no balance,
                # use the current exchange balance as a safe baseline.
                if self.start_balance <= 0:
                    self.start_balance = current_balance
                if self.daily_start_balance <= 0:
                    self.daily_start_balance = current_balance
                self.daily_peak_equity = max(self.daily_peak_equity, current_equity)
                self.session_peak_equity = max(self.session_peak_equity, current_equity, self.start_balance)
                max_trades = int(self.session_max_trades)
                grid_cfg = self._grid_validate_settings()
                self._verify_resume_exchange_state()
            else:
                self.start_balance = current_balance
                self.daily_start_balance = self.start_balance
                self.daily_start_date = datetime.now().date()
                self.daily_peak_equity = current_equity
                self.session_peak_equity = current_equity
                self.consecutive_cycle_errors = 0
                self.last_market_data_ts = 0

                self.total_trades = 0
                self.opened_trades = 0
                self.winning_trades = 0
                self.losing_trades = 0
                self.trade_pnls = []
                self.active_trade = None
                self.last_protected_position = None
                self.retired_managed_order_ids = set()
                self.tp1_be_done = False
                self.reentry_direction_lock = None
                self.reentry_lock_reason = ""
                self.session_started_at = time.time()
                self.session_max_trades = max_trades
                self.session_id = str(uuid.uuid4())
                self.runtime_resumed = False
                self.runtime_last_error = ""
                self.grid_state = {
                    "active": False, "mode": "OFF", "center": 0.0,
                    "entry_orders": {}, "filled_levels": set(),
                    "tp_order_id": None, "sl_order_id": None,
                    "last_position_qty": 0.0, "last_position_entry": 0.0,
                    "last_grid_reset": 0.0, "session_start_balance": 0.0,
                    "peak_equity": 0.0, "paused_until": 0.0,
                    "auto_direction": None,
                }

                grid_cfg = self._grid_initialize(
                    self.symbol,
                    self.start_balance,
                    current_equity,
                )

                # A genuinely new session must never silently adopt an existing
                # position or unknown/manual orders. Exact IDs from the previous
                # checkpoint are the only orders eligible for automatic cleanup.
                if grid_cfg["mode"] in ("OFF", "DIRECT_SHOT"):
                    existing_position = self.fetch_position(self.symbol)
                    existing_orders = self.fetch_open_orders_safe(self.symbol, strict=True)
                    if existing_position:
                        raise RuntimeError(
                            "START BLOCKED: existing position found on this symbol. "
                            "Choose Resume if this inventory belongs to this bot, or "
                            "close/clean the position before starting a new session."
                        )
                    if existing_orders:
                        checkpoint_ids = self._checkpoint_managed_order_ids(self.resume_candidate)
                        open_ids = {str(order.get("id")) for order in existing_orders if order.get("id")}
                        orphan_bot_orders = open_ids & checkpoint_ids
                        unknown_orders = open_ids - checkpoint_ids
                        if orphan_bot_orders and not unknown_orders:
                            self.log(
                                "START CLEANUP: account is flat and all existing open orders "
                                f"are verified as previous bot-managed orders ({len(orphan_bot_orders)}). "
                                "Cancelling them before starting the new session."
                            )
                            self._cancel_known_managed_orders_from_ids(self.symbol, orphan_bot_orders)
                            existing_orders = self.fetch_open_orders_safe(self.symbol, strict=True)
                            if existing_orders:
                                raise RuntimeError("START BLOCKED: previous bot-managed orders could not be fully cancelled.")
                            self.log("START CLEANUP VERIFIED: previous bot-managed orders removed; account is flat.")
                        else:
                            raise RuntimeError(
                                "START BLOCKED: existing position/open orders found on this symbol. "
                                "Unknown/manual orders will never be adopted automatically. "
                                "Cancel/clean them before starting a new session."
                            )

            # Never change leverage on a resumed live position. Use the exchange
            # position's actual leverage for recovery; configure leverage normally
            # when starting flat.
            resume_position = self.fetch_position(self.symbol)
            if resume_mode and resume_position:
                actual_lev = float(resume_position.get("leverage") or 0.0)
                if actual_lev > 0:
                    self.log(
                        f"RECOVERY: exchange position leverage={actual_lev:g}x; "
                        "leverage change skipped while position is open."
                    )
            else:
                self.configure_leverage(self.symbol, leverage)

            if grid_cfg["mode"] not in ("OFF", "DIRECT_SHOT"):
                self.log(
                    f"GRID MODE ACTIVE: {grid_cfg['mode']} | "
                    f"Levels={grid_cfg['levels']} | "
                    f"Spacing={grid_cfg['spacing']*100:g}% | "
                    f"TP={grid_cfg['tp_pct']*100:g}% | "
                    f"GlobalSL={grid_cfg['sl_pct']*100:g}% | "
                    f"MaxExposure={grid_cfg['max_exposure']:g} USDT | "
                    f"MaxGridDD={grid_cfg['max_dd']*100:g}% | "
                    f"TrendFilter={grid_cfg['trend_filter']} | "
                    f"GridScoreMin={grid_cfg['score_min']}"
                )
                self.log(
                    "GRID RISK SCOPE: Grid uses its own Order Size/TP/SL/Max Exposure/Max DD. "
                    "Section 5 Daily DD + Emergency Capital Loss Stop remain GLOBAL."
                )
                if grid_cfg["mode"] == "NEUTRAL_GRID":
                    self.log(
                        f"NEUTRAL GRID AUTO-DIRECTION: {grid_cfg['trend_filter']} | "
                        "SUPERTREND=ST direction | SCORE/OFF=all enabled Section 3 votes | "
                        "direction changes cancel old entries and safely reverse Grid inventory."
                    )

            # Capture/display the exact account balance at BOT START.
            try:
                self.root.after(
                    0,
                    lambda start=self.start_balance,
                    curr=current_balance,
                    pnl=self.net_pnl,
                    trades=self.total_trades,
                    wins=self.winning_trades,
                    losses=self.losing_trades: self.lbl_pnl.config(
                        text=(
                            f"Start Balance: ${start:.4f} | "
                            f"Current Balance: ${curr:.4f} | "
                            f"Net PnL: ${pnl:.2f} | "
                            f"Trades: {trades} | Wins: {wins} | "
                            f"Losses: {losses} | Win Rate: "
                            f"{(wins/(wins+losses)*100 if wins+losses else 0.0):.1f}%"
                        )
                    ),
                )
            except Exception:
                pass

            self.log(
                f"CONNECTED: {exchange_id.upper()} | "
                f"{self.symbol} | "
                f"Balance={self.start_balance:.4f} USDT"
            )

            self.log(
                "SL/TP engine: ACTUAL ENTRY PRICE + ACTUAL POSITION QTY"
            )
            self.log(
                f"SL mode: {self.v_sl_mode.get()} | TP mode: {self.v_tp_mode.get()}"
            )
            self.log(
                f"TRADE SESSION: Max Trades={max_trades if max_trades > 0 else 'UNLIMITED'} | "
                f"Estimated Window={self.lbl_est_time.cget('text')} | "
                f"Actual duration may be longer if signals do not occur every candle."
            )

            enabled_modules = []
            if self.v_use_st.get():
                enabled_modules.append("Supertrend")
            if self.v_use_ema.get():
                enabled_modules.append(f"EMA{self.e_ema_len.get().strip()}")
            if self.v_use_ema_cross.get():
                enabled_modules.append(
                    f"EMA Cross {self.e_ema_fast.get().strip()}/{self.e_ema_slow.get().strip()} "
                    f"({self.v_ema_cross_entry_mode.get().strip().upper()})"
                )
            if self.v_use_macd.get():
                enabled_modules.append(
                    f"MACD {self.e_macd_fast.get().strip()}/{self.e_macd_slow.get().strip()}/{self.e_macd_signal.get().strip()}"
                )
            if self.v_use_rsi.get():
                enabled_modules.append(
                    f"RSI {self.e_rsi_len.get().strip()} "
                    f"({self.v_rsi_logic.get()} | {self.v_rsi_ma_type.get()} {self.e_rsi_ma_len.get().strip()} | "
                    f"OS {self.e_rsi_os.get().strip()} / OB {self.e_rsi_ob.get().strip()})"
                )
            if self.v_use_bb.get():
                enabled_modules.append(
                    f"BB {self.e_bb_len.get().strip()}x{self.e_bb_std.get().strip()}"
                )
            if self.v_use_stoch.get():
                enabled_modules.append(
                    f"Stoch {self.e_stoch_k.get().strip()}/{self.e_stoch_smooth.get().strip()}/{self.e_stoch_d.get().strip()}"
                )
            if self.v_use_vwap.get():
                enabled_modules.append(
                    f"VWAP {self.e_vwap_len.get().strip()}"
                )
            if self.v_use_vwap_delta.get():
                enabled_modules.append(
                    f"VWAP Delta "
                    f"({self.v_vwap_delta_logic.get().strip().upper()} | "
                    f"Baseline {self.e_vwap_delta_baseline.get().strip()} | "
                    f"HMA {'ON' if self.v_vwap_delta_smooth.get() else 'OFF'} "
                    f"{self.e_vwap_delta_smooth_len.get().strip()})"
                )
            if self.v_use_vidya.get():
                enabled_modules.append(
                    f"Volumatic VIDYA "
                    f"({self.v_vidya_entry_mode.get().strip().upper()} | "
                    f"Length {self.e_vidya_len.get().strip()} | "
                    f"Momentum {self.e_vidya_momentum.get().strip()} | "
                    f"Band {self.e_vidya_band.get().strip()})"
                )
            if self.v_use_liq_swings.get():
                enabled_modules.append(
                    f"Liquidity Swings "
                    f"(P{self.e_liq_length.get().strip()} | "
                    f"{self.v_liq_area.get().strip()} | "
                    f"{self.v_liq_filter.get().strip()} {self.e_liq_filter_value.get().strip()} | "
                    f"{self.v_liq_entry_mode.get().strip().upper()})"
                )
            if self.v_use_trendline.get():
                enabled_modules.append(
                    f"Trendline Breakout "
                    f"(P{self.e_trendline_length.get().strip()} | "
                    f"MinDist {self.e_trendline_min_distance.get().strip()} | "
                    f"{self.v_trendline_entry_mode.get().strip().upper()} | "
                    f"Buffer {self.e_trendline_buffer.get().strip()}% | "
                    f"Retest {self.e_trendline_retest.get().strip()})"
                )
            if self.v_use_nwe.get():
                enabled_modules.append(
                    f"NWE "
                    f"({self.v_nwe_entry_mode.get().strip().upper()} | "
                    f"Bandwidth {self.e_nwe_bandwidth.get().strip()} | "
                    f"Mult {self.e_nwe_mult.get().strip()} | "
                    f"Non-Repainting FIXED)"
                )
            if self.v_use_atr.get():
                enabled_modules.append(
                    f"ATR >= {self.e_atr_min_pct.get().strip()}%"
                )
            if self.v_use_vol.get():
                enabled_modules.append(f"Volume {self.e_vol_len.get().strip()}")
            if self.v_use_adx.get():
                enabled_modules.append(f"ADX >= {self.e_adx_thresh.get().strip()}")
            if self.v_use_mtf.get():
                enabled_modules.append("4H MTF")
            if self.v_use_divergence.get():
                enabled_modules.append(
                    f"Divergence {self.v_div_type.get()} | Pivot {self.e_div_pivot.get().strip()} | "
                    f"Min {self.e_div_min_count.get().strip()} | {self.v_div_entry_mode.get().upper()}"
                )
            if self.v_use_vol_sr.get():
                enabled_modules.append(
                    f"Volume S/R Zones {self.v_sr_tf1.get()}/{self.v_sr_tf2.get()}/{self.v_sr_tf3.get()}/{self.v_sr_tf4.get()} | "
                    f"{self.v_sr_entry_mode.get().upper()} | Vote {self.v_sr_vote_mode.get().upper()}"
                )

            self.log(
                "STRATEGY MODULES: "
                + (
                    " | ".join(enabled_modules)
                    if enabled_modules
                    else "None"
                )
            )
            self.log(
                f"RSI ENGINE: {'ON' if self.v_use_rsi.get() else 'OFF'}"
                + (
                    f" | Logic={self.v_rsi_logic.get().strip().upper()}"
                    f" | MA={self.v_rsi_ma_type.get().strip().upper()}"
                    f" {self.e_rsi_ma_len.get().strip()}"
                    if self.v_use_rsi.get()
                    else " | RSI columns not required"
                )
            )

            # Read signal settings here as well as in the worker thread.
            # This prevents the GUI START path from referencing undefined
            # variables before _run_bot_logic() begins.
            signal_mode = self.v_signal_mode.get().strip().upper()
            preset_scores = {
                "SINGLE_SIGNAL": 1,
                "ANY_NON_CONFLICTING": 1,
                "2_SIGNALS": 2,
                "3_SIGNALS": 3,
                "4_SIGNALS": 4,
            }
            if signal_mode in preset_scores:
                min_score = preset_scores[signal_mode]
            elif signal_mode == "ADAPTIVE_SCORE":
                min_score = 1
            else:
                min_score = int(self.e_min_score.get().strip())

            allowed_signal_modes = SUPPORTED_SIGNAL_MODES
            if signal_mode not in allowed_signal_modes:
                raise ValueError(f"Unknown signal mode: {signal_mode}")
            if min_score <= 0:
                raise ValueError("Minimum score must be greater than 0.")

            # V8.3.1 FIX: start_bot() logs Adaptive Score before the worker
            # thread starts. Read/validate these values in this scope so the
            # startup path cannot reference _run_bot_logic() locals.
            adaptive_edge = float(self.e_adaptive_edge.get().strip())
            adaptive_min_weight = float(self.e_adaptive_min_weight.get().strip())
            if not 0.0 < adaptive_edge < 1.0:
                raise ValueError("Adaptive Edge must be between 0 and 1.")
            if adaptive_min_weight <= 0:
                raise ValueError("Adaptive Min Weight must be greater than 0.")

            # Startup/configuration logging must not depend on _run_bot_logic()
            # locals, because those are parsed later in the worker thread.
            # Read the GUI values directly here; _run_bot_logic() performs the
            # authoritative numeric validation before calculating indicators.
            startup_st_len = self.e_st_len.get().strip()
            startup_st_mult = self.e_st_mult.get().strip()
            startup_st_source = self.v_st_source.get().strip().upper()
            startup_st_change_atr = bool(self.v_st_change_atr.get())
            startup_st_entry_mode = self.v_st_entry_mode.get().strip().upper()
            self.log(
                f"SUPERTREND: ATR={startup_st_len} | Mult={startup_st_mult} | "
                f"Source={startup_st_source} | "
                f"ATR Method={'RMA' if startup_st_change_atr else 'SMA(TR)'} | "
                f"Entry={startup_st_entry_mode}"
            )
            self.log(
                f"EMA CROSS ENTRY MODE: {self.v_ema_cross_entry_mode.get().strip().upper()}"
            )

            self.log(
                f"SIGNAL MODE: {signal_mode} | "
                f"Minimum Score={min_score}"
            )
            if signal_mode == "SINGLE_SIGNAL":
                self.log(
                    "SINGLE SIGNAL MODE: ONE enabled signal is enough; "
                    "Volume/ADX/ATR/MTF are NOT required."
                )
            elif signal_mode == "ADAPTIVE_SCORE":
                self.log(
                    f"ADAPTIVE SCORE: correlation-aware weights | Edge>={adaptive_edge:.2f} | "
                    f"MinWeight>={adaptive_min_weight:.2f} | VOL/ATR/ADX/MTF act as regime gates."
                )
            self.log(
                "REVERSAL HOLD: "
                + (
                    "ON | Wait for ALL active directional signals to reverse."
                    if self.v_hold_until_all_reverse.get()
                    else "OFF | Normal signal reversal."
                )
            )
            self.log(
                "POST-SL OPPOSITE LOCK: "
                + (
                    "ON | After SL/BE stop, same-direction re-entry is blocked until a valid opposite signal appears."
                    if self.v_require_opposite_after_exit.get()
                    else "OFF | Same-direction re-entry is allowed after SL/exit (subject to other safety gates)."
                )
            )
            self.log(
                "POST-SL LOCK RULE: If SL/BE closes a trade, the bot waits for a valid opposite signal "
                "using the selected signal mode; TP1/TP2 exits do not create this lock."
            )

            self.log(
                f"SUPERTREND ENTRY MODE: "
                f"{self.v_st_entry_mode.get().strip().upper()}"
            )
            if self.v_hold_until_all_reverse.get():
                self.log(
                    "TP1 BREAK-EVEN: DISABLED BY REVERSAL HOLD | "
                    "No TP1 order is placed while Hold-All-Reverse is ON."
                )
            else:
                self.log(
                    "TP1 BREAK-EVEN: "
                    + (
                        "ON | Remaining SL moves to actual entry after TP1."
                        if self.v_tp1_be.get()
                        else "OFF"
                    )
                )

            # Finalize the session metadata only after every GUI setting has
            # passed startup validation.  This metadata is also persisted so a
            # crash/restart can restore the exact execution context.
            self.runtime_timeframe = self.v_tf.get().strip().lower()
            self.runtime_account_mode = account_mode
            self.runtime_strategy_mode = (
                grid_cfg["mode"]
                if grid_cfg["mode"] not in ("OFF", "DIRECT_SHOT")
                else signal_mode
            )
            self.runtime_strategy_modules = " | ".join(enabled_modules) if enabled_modules else "None"
            self.runtime_config_hash = self._config_hash()
            if not self.session_id:
                self.session_id = str(uuid.uuid4())
            self._db_session_start()
            self._persist_runtime_state(status="RUNNING")

            self.is_running = True

            self._set_bot_button_states(running=True)

            self.bot_thread = threading.Thread(
                target=self._run_bot_logic,
                daemon=True,
            )
            self.bot_thread.start()

        except Exception as e:
            self.log(
                f"START FAILED: {e}"
            )
            self.is_running = False
            self._release_profile_lock()

            messagebox.showerror(
                "Bot start failed",
                str(e),
            )

    def stop_bot(self):
        try:
            self.save_settings()
        except Exception:
            pass
        # Flip the run flag first so the worker cannot begin another execution
        # cycle while Grid shutdown is cleaning up exchange orders/positions.
        self.is_running = False
        try:
            grid_mode = self.v_grid_mode.get().strip().upper()
            if self.symbol and grid_mode in ("LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID"):
                if self.grid_state.get("active"):
                    self._grid_stop(self.symbol, "Manual bot stop", cooldown_seconds=0)
                else:
                    # Retry symbol-wide cleanup even if local Grid state was
                    # already marked inactive. This catches untracked duplicates.
                    if not self.fetch_position(self.symbol):
                        self._cancel_known_managed_orders(self.symbol)
                    else:
                        self.log(
                            "GRID STOP: position still open while Grid is inactive; "
                            "leaving exchange-side protection in place."
                        )
                self.log("GRID ENGINE STOPPED safely.")
        except Exception as e:
            self.log(f"GRID stop cleanup warning: {e}")

        try:
            live_position = self.fetch_position(self.symbol) if self.exchange and self.symbol else None
            stop_status = "PAUSED_WITH_POSITION" if live_position else "STOPPED"
            self._persist_runtime_state(status=stop_status)
            try:
                end_balance = self.fetch_balance_total() if self.exchange else None
            except Exception:
                end_balance = None
            self._db_session_end(
                stop_status,
                end_balance=end_balance,
                notes="Manual bot stop requested.",
            )
        except Exception as e:
            self.log(f"Runtime stop checkpoint warning: {e}")

        self.log(
            "Stopping execution thread..."
        )

        try:
            self.root.after(0, lambda: self._set_bot_button_states(running=False))
        except Exception:
            pass

    def on_close(self):
        if self.is_running:
            if not messagebox.askyesno(
                "Stop bot?",
                "Bot is running. Stop it and close?",
            ):
                return

        # Save the latest GUI configuration before shutting down so a
        # recovery checkpoint contains the exact settings the user was using.
        try:
            self.save_settings()
        except Exception:
            pass

        # Stop Grid safely before GUI exit; do not remove protection from a
        # position unless the position has first been confirmed flat.
        self.is_running = False
        try:
            grid_mode = self.v_grid_mode.get().strip().upper()
            if self.symbol and grid_mode in ("LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID"):
                if self.grid_state.get("active"):
                    self._grid_stop(self.symbol, "GUI shutdown", cooldown_seconds=0)
                else:
                    if not self.fetch_position(self.symbol):
                        self._cancel_known_managed_orders(self.symbol)
                    else:
                        self.log(
                            "GRID SHUTDOWN: position still open while Grid is inactive; "
                            "leaving exchange-side protection in place."
                        )
                self.log("GRID ENGINE SHUTDOWN completed safely.")
        except Exception as e:
            self.log(f"GRID shutdown cleanup warning: {e}")

        try:
            live_position = self.fetch_position(self.symbol) if self.exchange and self.symbol else None
            close_status = "PAUSED_WITH_POSITION" if live_position else "STOPPED"
            self._persist_runtime_state(status=close_status)
            try:
                end_balance = self.fetch_balance_total() if self.exchange else None
            except Exception:
                end_balance = None
            self._db_session_end(
                close_status,
                end_balance=end_balance,
                notes="GUI shutdown.",
            )
        except Exception as e:
            self.log(f"GUI shutdown checkpoint warning: {e}")

        self.root.destroy()

    # -------------------- PERFORMANCE / TRADE ACCOUNTING ----

    def _begin_performance_trade(self, side, entry, qty, balance):
        trade_id = str(uuid.uuid4())
        protected = self.last_protected_position or {}
        try:
            leverage_value = float(self.e_lev.get().strip())
        except Exception:
            leverage_value = 0.0

        self.active_trade = {
            "trade_id": trade_id,
            "side": side,
            "entry": float(entry),
            "qty": float(qty),
            "balance_start": float(balance),
            "started_at": time.time(),
            "tp1_hit": False,
            "leverage": leverage_value,
            "sl": protected.get("sl"),
            "tp1": protected.get("tp1"),
            "tp2": protected.get("tp2"),
            "exit_price": None,
        }
        self.opened_trades += 1
        self._db_trade_open(self.active_trade)
        self._persist_runtime_state(status="RUNNING")

    def _finalize_performance_trade(self, reason="CLOSED", balance=None):
        trade = self.active_trade
        if not trade:
            return
        try:
            if balance is None:
                balance = self.fetch_balance_total()
            pnl = float(balance) - float(trade["balance_start"])

            try:
                trade["exit_price"] = float(
                    self._current_market_price(self.symbol)
                )
            except Exception:
                trade["exit_price"] = None

            self.trade_pnls.append(pnl)
            self.total_trades += 1
            if pnl > 0:
                self.winning_trades += 1
                result = "WIN"
            elif pnl < 0:
                self.losing_trades += 1
                result = "LOSS"
            else:
                result = "BREAKEVEN"

            self._db_trade_close(
                trade,
                pnl,
                reason,
                "ACCOUNT_BALANCE_DELTA",
            )

            self.log(
                f"TRADE CLOSED ✓ | Result={result} | PnL=${pnl:.4f} | "
                f"Reason={reason} | Completed={self.total_trades}"
            )
        except Exception as e:
            self.log(f"Trade result accounting notice: {e}")
        finally:
            self.active_trade = None
            self._persist_runtime_state(status="RUNNING")

    def _mark_tp1_hit_for_stats(self):
        if self.active_trade is not None:
            self.active_trade["tp1_hit"] = True

    # -------------------- SESSION WINDOW ---------------------

    def update_estimated_window(self):
        """Update the estimated candle window for the selected max trades.

        This is only a time estimate based on one potential trade per
        timeframe candle. It does not guarantee that a signal/trade will
        occur on every candle.
        """
        try:
            raw_trades = self.e_max_trades.get().strip()
        except Exception:
            raw_trades = "10"

        try:
            max_trades = int(raw_trades)
        except Exception:
            max_trades = 0

        if max_trades <= 0:
            text_value = "Unlimited"
        else:
            tf = str(self.v_tf.get()).strip().lower()
            tf_minutes = {
                "1m": 1,
                "3m": 3,
                "5m": 5,
                "10m": 10,
                "15m": 15,
                "30m": 30,
                "1h": 60,
                "2h": 120,
                "4h": 240,
                "6h": 360,
                "12h": 720,
                "1d": 1440,
                "45m": 45,
            }.get(tf)

            if tf_minutes is None:
                text_value = "N/A"
            else:
                total_minutes = max_trades * tf_minutes
                if total_minutes < 60:
                    text_value = f"{total_minutes} min"
                elif total_minutes % 60 == 0:
                    hours = total_minutes // 60
                    text_value = (
                        f"{hours} hr" if hours == 1
                        else f"{hours} hrs"
                    )
                else:
                    hours = total_minutes / 60.0
                    text_value = f"{total_minutes} min ({hours:.2f} hrs)"

        try:
            self.lbl_est_time.config(text=text_value)
        except Exception:
            pass

    # -------------------- TP1 -> BREAK-EVEN ------------------

    def _manage_tp1_break_even(self, position):
        """After TP1 actually fills, move the remaining SL to actual entry.

        TP1 completion is confirmed from the exchange order status. The
        existing SL is cancelled and replaced with a reduce-only trigger at
        the actual filled entry price. TP2 is left untouched.
        """
        if self.v_hold_until_all_reverse.get():
            return
        if not self.v_tp1_be.get():
            return
        if self.tp1_be_done:
            return
        if not position:
            return

        protected = self.last_protected_position
        if not protected:
            return

        if protected.get("side") != position.get("side"):
            return

        tp1_id = protected.get("tp1_id")
        old_sl_id = protected.get("sl_id")
        if not tp1_id:
            return

        # Query the specific TP1 ID instead of trusting a partial first page.
        # An inconclusive API response must never move the SL.
        tp1_order = None

        try:
            if self._order_is_still_open(self.symbol, tp1_id):
                return
        except Exception as e:
            self.log(f"TP1 open-order status notice: {e}")

        if tp1_order is None:
            tp1_order = self._fetch_specific_order(self.symbol, tp1_id)

        if tp1_order is None:
            return

        status = str(tp1_order.get("status") or "").lower()
        filled = float(tp1_order.get("filled") or 0.0)

        if status not in ("closed", "filled") or filled <= 0:
            return

        remaining_qty = float(position.get("qty") or 0.0)
        entry_price = float(position.get("entry") or 0.0)

        if remaining_qty <= 0 or entry_price <= 0:
            return

        try:
            self.log(
                f"TP1 ACHIEVED ✓ | Filled Qty={filled:g} | "
                f"Remaining Qty={remaining_qty:g}"
            )
            self._mark_tp1_hit_for_stats()

            be_price = float(
                self.exchange.price_to_precision(
                    self.symbol,
                    entry_price,
                )
            )
            close_side = "sell" if position["side"] == "LONG" else "buy"

            # Create and verify the replacement stop BEFORE cancelling the old
            # stop. This keeps the position protected if BE creation fails.
            if self.exchange_id == "bybit":
                trigger_direction = 2 if position["side"] == "LONG" else 1
                be_order = self.create_bybit_trigger(
                    self.symbol, "STOP_MARKET", close_side, remaining_qty,
                    be_price, trigger_direction, "BREAK-EVEN SL"
                )
            elif self.exchange_id == "binance":
                be_order = self.create_binance_trigger(
                    self.symbol, "STOP_MARKET", close_side, remaining_qty,
                    be_price, "BREAK-EVEN SL"
                )
            else:
                be_order = self.create_generic_trigger(
                    self.symbol, close_side, remaining_qty,
                    be_price, "BREAK-EVEN SL"
                )

            be_id = be_order.get("id")
            if not be_id:
                raise RuntimeError("Break-even SL returned no order ID.")

            verified = self.verify_protection_orders(
                self.symbol,
                [("BREAK-EVEN SL", be_order)],
            )
            if not verified:
                try:
                    self.exchange.cancel_order(be_id, self.symbol)
                except Exception:
                    pass
                raise RuntimeError(
                    "Break-even SL was submitted but could not be verified. Original SL was retained."
                )

            # Only after the replacement is verified do we cancel the old SL.
            if old_sl_id and str(old_sl_id) != str(be_id):
                try:
                    self.exchange.cancel_order(old_sl_id, self.symbol)
                    self.log(f"TP1 ACHIEVED: Cancelled old SL: {old_sl_id}")
                except Exception as e:
                    # Duplicate protection is safer than no protection.
                    self.log(f"TP1 ACHIEVED: old SL cancel notice: {e}")

            protected["sl_id"] = be_id
            protected["sl"] = be_price
            self.tp1_be_done = True

            self.log(
                f"BREAK-EVEN ACTIVE ✓ | Entry={entry_price:.12g} | "
                f"Remaining Qty={remaining_qty:g} | SL={be_price:.12g}"
            )

        except Exception as e:
            self.tp1_be_done = False
            self.log(
                f"TP1 BREAK-EVEN ERROR: {e}"
            )

    # -------------------- TIMEFRAME DATA ---------------------

    def _fetch_strategy_ohlcv(self, timeframe, limit):
        """Fetch strategy candles, including synthetic 45m candles.

        Exchanges supported by CCXT generally provide 1m/3m/5m/15m/30m/1h
        candles but not a native 45m interval. For 45m, build candles from
        completed/current 15m candles aligned to UTC 45-minute boundaries.
        The returned dataframe keeps the current in-progress 45m bucket when
        available; the main loop ALWAYS uses closed_idx=-2, so an in-progress
        45m bucket is never used for a signal.
        """
        timeframe = str(timeframe).strip().lower()
        limit = int(limit)
        if limit <= 0:
            raise ValueError("OHLCV limit must be greater than 0.")

        if timeframe != "45m":
            return self.exchange.fetch_ohlcv(
                self.symbol,
                timeframe=timeframe,
                limit=limit,
            )

        # 45m = three 15m candles. Fetch extra history because aggregation
        # reduces the number of rows by roughly 3x. Multiple batches are used
        # when the exchange caps a single request below the required amount.
        base_interval_ms = 15 * 60 * 1000
        target_base = limit * 3 + 6
        batch_limit = min(1000, max(200, target_base))
        batches = []
        remaining = target_base
        since = None

        while remaining > 0 and len(batches) < 5:
            request_limit = min(batch_limit, remaining)
            kwargs = {
                "symbol": self.symbol,
                "timeframe": "15m",
                "limit": request_limit,
            }
            if since is not None:
                kwargs["since"] = int(since)

            batch = self.exchange.fetch_ohlcv(**kwargs)
            if not batch:
                break

            batches.extend(batch)
            oldest = min(int(row[0]) for row in batch)
            new_since = oldest - base_interval_ms * request_limit
            if since is not None and new_since >= since:
                break
            since = new_since
            remaining = target_base - len(batches)

            if len(batch) < request_limit:
                break

        if not batches:
            raise RuntimeError("No 15m OHLCV data returned for synthetic 45m timeframe.")

        # Deduplicate and sort chronologically.
        unique = {}
        for row in batches:
            unique[int(row[0])] = row
        base = pd.DataFrame(
            [unique[k] for k in sorted(unique)],
            columns=["time", "open", "high", "low", "close", "vol"],
        )
        base["datetime"] = pd.to_datetime(base["time"], unit="ms", utc=True)
        base = base.set_index("datetime")

        # Aggregate exactly three 15m candles per 45m bucket. Incomplete
        # historical buckets are discarded so a missing 15m candle can never
        # masquerade as a completed 45m candle.
        grouped = base.resample(
            "45min", origin="epoch", label="left", closed="left"
        )
        agg = grouped.agg({
            "time": "first",
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "vol": "sum",
        })
        counts = grouped["close"].count()
        agg["base_count"] = counts
        agg = agg.dropna(subset=["open", "high", "low", "close", "vol"])

        # The newest bucket can be in progress. Keep it so the main strategy
        # can use closed_idx=-2 and therefore trade only a fully completed 45m bar.
        # All older buckets must contain exactly 3 base candles.
        if len(agg) > 1:
            older = agg.iloc[:-1]
            newest = agg.iloc[-1:]
            older = older[older["base_count"] == 3]
            agg = pd.concat([older, newest], axis=0)
        agg = agg.reset_index(drop=True)

        # Keep the newest `limit` 45m rows.
        if len(agg) > limit:
            agg = agg.iloc[-limit:].reset_index(drop=True)

        return agg[["time", "open", "high", "low", "close", "vol"]].values.tolist()

    def _refresh_volume_sr_cache(self, base_df, tf_names):
        """Refresh Volume S/R source data with a conservative short cache."""
        now = time.time()
        wanted = [str(x).strip() for x in tf_names if str(x).strip() != "Disable"]
        if not wanted:
            return {"Chart": base_df.copy()}
        # Refresh at most every 60 seconds. HTF candles themselves are
        # confirmed by the numerical module before becoming active.
        if self.volume_sr_cache and now - self.volume_sr_cache_time < 60:
            out = dict(self.volume_sr_cache)
            out["Chart"] = base_df.copy()
            return out
        frames = {"Chart": base_df.copy()}
        tf_ccxt={"15m":"15m","30m":"30m","1h":"1h","4h":"4h","D":"1d","W":"1w"}
        for tf in wanted:
            if tf == "Chart":
                continue
            try:
                api_tf=tf_ccxt.get(tf, tf)
                raw = self.exchange.fetch_ohlcv(self.symbol, timeframe=api_tf, limit=300)
                f = pd.DataFrame(raw, columns=["time","open","high","low","close","vol"])
                if not f.empty:
                    f["datetime"] = pd.to_datetime(f["time"], unit="ms", utc=True)
                    frames[tf] = f
            except Exception as e:
                self.log(f"VOLUME S/R DATA WARNING {tf}: {e}")
        self.volume_sr_cache = frames
        self.volume_sr_cache_time = now
        return frames

    # -------------------- SIGNAL DECISION -------------------

    def _decide_signal(
        self,
        directional_modules,
        signal_mode,
        min_score,
        atr_pass=True,
        vol_pass=True,
        adx_pass=True,
        mtf_pass_bull=True,
        mtf_pass_bear=True,
        adaptive_edge=None,
        adaptive_min_weight=None,
    ):
        """Compatibility wrapper around the modular strategy engine."""
        return StrategyEngine.decide_signal(
            directional_modules,
            signal_mode,
            min_score,
            atr_pass,
            vol_pass,
            adx_pass,
            mtf_pass_bull,
            mtf_pass_bear,
            adaptive_edge,
            adaptive_min_weight,
        )

    # -------------------- MAIN LOOP --------------------------

    def _run_bot_logic(self):
        try:
            timeframe = str(self.v_tf.get()).strip().lower()
            supported_timeframes = {"1m", "3m", "5m", "15m", "30m", "45m", "1h", "4h"}
            if timeframe not in supported_timeframes:
                raise ValueError(
                    f"Unsupported timeframe: {timeframe}. Use 1m, 3m, 5m, 15m, 30m, 45m, 1h or 4h."
                )

            try:
                max_trades = int(self.e_max_trades.get().strip())
            except Exception:
                raise ValueError("Max Trades must be a whole number. Use 0 for unlimited.")
            if max_trades < 0:
                raise ValueError("Max Trades cannot be negative.")
            no_same_candle = self.v_no_same_candle.get()
            try:
                cooldown_min = float(self.e_cooldown_min.get().strip())
            except Exception:
                raise ValueError("Cooldown must be a number of minutes.")
            if cooldown_min < 0:
                raise ValueError("Cooldown cannot be negative.")

            use_st = self.v_use_st.get()
            st_len = int(
                self.e_st_len.get()
            )
            st_mult = float(
                self.e_st_mult.get()
            )
            st_source = self.v_st_source.get().strip().upper()
            st_change_atr = bool(self.v_st_change_atr.get())

            if st_source not in ("CLOSE", "HL2"):
                raise ValueError("Supertrend Source must be CLOSE or HL2.")
            if st_len <= 0 or st_mult <= 0:
                raise ValueError("Supertrend ATR Period and Multiplier must be greater than 0.")

            use_ema = self.v_use_ema.get()
            ema_len = int(
                self.e_ema_len.get()
            )
            if ema_len <= 0:
                raise ValueError("EMA period must be greater than 0.")

            use_ema_cross = self.v_use_ema_cross.get()
            ema_fast_len = int(
                self.e_ema_fast.get()
            )
            ema_slow_len = int(
                self.e_ema_slow.get()
            )

            if ema_fast_len <= 0 or ema_slow_len <= 0:
                raise ValueError(
                    "EMA crossover periods must be greater than 0."
                )

            if ema_fast_len == ema_slow_len:
                raise ValueError(
                    "EMA crossover Fast and Slow periods must be different."
                )

            ema_cross_entry_mode = self.v_ema_cross_entry_mode.get().strip().upper()
            if ema_cross_entry_mode not in ("FRESH_CROSS", "CURRENT_TREND"):
                raise ValueError(
                    "EMA crossover Entry mode must be FRESH_CROSS or CURRENT_TREND."
                )

            use_macd = self.v_use_macd.get()
            macd_fast_len = int(self.e_macd_fast.get())
            macd_slow_len = int(self.e_macd_slow.get())
            macd_signal_len = int(self.e_macd_signal.get())

            if macd_fast_len <= 0 or macd_slow_len <= 0 or macd_signal_len <= 0:
                raise ValueError("MACD periods must be greater than 0.")
            if macd_fast_len >= macd_slow_len:
                raise ValueError("MACD Fast period must be smaller than Slow period.")

            use_rsi = self.v_use_rsi.get()
            rsi_len = int(self.e_rsi_len.get())
            rsi_ob = float(self.e_rsi_ob.get())
            rsi_os = float(self.e_rsi_os.get())
            rsi_logic = self.v_rsi_logic.get().strip().upper()
            rsi_ma_type = self.v_rsi_ma_type.get().strip().upper()
            rsi_ma_len = int(self.e_rsi_ma_len.get())

            if rsi_len <= 0 or rsi_ma_len <= 0:
                raise ValueError("RSI and RSI MA periods must be greater than 0.")
            if not (0 < rsi_os < rsi_ob < 100):
                raise ValueError("RSI must satisfy 0 < Oversold < Overbought < 100.")
            if rsi_logic not in ("REVERSAL_ZONE", "CROSS_MA", "EITHER"):
                raise ValueError("RSI Logic must be REVERSAL_ZONE, CROSS_MA, or EITHER.")
            if rsi_ma_type not in ("SMA", "EMA", "WMA"):
                raise ValueError("RSI MA Type must be SMA, EMA, or WMA.")

            use_bb = self.v_use_bb.get()
            bb_len = int(self.e_bb_len.get())
            bb_std = float(self.e_bb_std.get())

            if bb_len <= 0 or bb_std <= 0:
                raise ValueError("Bollinger period and StdDev must be greater than 0.")

            use_stoch = self.v_use_stoch.get()
            stoch_k_len = int(self.e_stoch_k.get())
            stoch_smooth_len = int(self.e_stoch_smooth.get())
            stoch_d_len = int(self.e_stoch_d.get())

            if stoch_k_len <= 0 or stoch_smooth_len <= 0 or stoch_d_len <= 0:
                raise ValueError("Stochastic periods must be greater than 0.")

            use_vwap = self.v_use_vwap.get()
            vwap_len = int(self.e_vwap_len.get())
            if vwap_len <= 0:
                raise ValueError("VWAP period must be greater than 0.")

            use_vwap_delta = self.v_use_vwap_delta.get()
            vwap_delta_smooth = self.v_vwap_delta_smooth.get()
            vwap_delta_smooth_len = int(self.e_vwap_delta_smooth_len.get())
            vwap_delta_baseline_len = int(self.e_vwap_delta_baseline.get())
            vwap_delta_logic = self.v_vwap_delta_logic.get().strip().upper()
            if vwap_delta_smooth_len <= 0 or vwap_delta_baseline_len <= 0:
                raise ValueError("VWAP Delta lengths must be greater than 0.")
            if vwap_delta_logic not in ("CURRENT_TREND", "CROSS_BASELINE"):
                raise ValueError("VWAP Delta Logic must be CURRENT_TREND or CROSS_BASELINE.")

            use_vidya = self.v_use_vidya.get()
            vidya_len = int(self.e_vidya_len.get())
            vidya_momentum = int(self.e_vidya_momentum.get())
            vidya_band = float(self.e_vidya_band.get())
            vidya_entry_mode = self.v_vidya_entry_mode.get().strip().upper()
            if vidya_len <= 0 or vidya_momentum <= 0 or vidya_band <= 0:
                raise ValueError("VIDYA Length, Momentum and Band must be greater than 0.")
            if vidya_entry_mode not in ("CURRENT_TREND", "FRESH_FLIP"):
                raise ValueError("VIDYA Entry must be CURRENT_TREND or FRESH_FLIP.")

            use_nwe = self.v_use_nwe.get()
            nwe_bandwidth = float(self.e_nwe_bandwidth.get())
            nwe_mult = float(self.e_nwe_mult.get())
            nwe_entry_mode = self.v_nwe_entry_mode.get().strip().upper()
            nwe_repaint = self.v_nwe_repaint.get()
            if nwe_bandwidth <= 0 or nwe_mult < 0:
                raise ValueError("NWE Bandwidth must be > 0 and Mult cannot be negative.")
            if nwe_entry_mode not in ("CURRENT_TREND", "FRESH_CROSS"):
                raise ValueError("NWE Entry must be CURRENT_TREND or FRESH_CROSS.")
            use_liq_swings = self.v_use_liq_swings.get()
            liq_length = int(self.e_liq_length.get())
            liq_area = self.v_liq_area.get().strip()
            liq_filter = self.v_liq_filter.get().strip().title()
            liq_filter_value = float(self.e_liq_filter_value.get())
            liq_entry_mode = self.v_liq_entry_mode.get().strip().upper()
            if liq_length <= 0:
                raise ValueError("Liquidity Swing Pivot Lookback must be greater than 0.")
            if liq_area not in ("Wick Extremity", "Full Range"):
                raise ValueError("Liquidity Swing Area must be Wick Extremity or Full Range.")
            if liq_filter not in ("Count", "Volume"):
                raise ValueError("Liquidity Swing Filter must be Count or Volume.")
            if liq_filter_value < 0:
                raise ValueError("Liquidity Swing Filter Value cannot be negative.")
            if liq_entry_mode not in ("FRESH_BREAK", "CURRENT_TREND"):
                raise ValueError("Liquidity Swing Entry must be FRESH_BREAK or CURRENT_TREND.")

            use_trendline = self.v_use_trendline.get()
            trendline_length = int(self.e_trendline_length.get())
            trendline_min_distance = int(self.e_trendline_min_distance.get())
            trendline_entry_mode = self.v_trendline_entry_mode.get().strip().upper()
            trendline_buffer = float(self.e_trendline_buffer.get())
            trendline_retest_candles = int(self.e_trendline_retest.get())
            if trendline_length <= 0:
                raise ValueError("Trendline Pivot Lookback must be greater than 0.")
            if trendline_min_distance <= 0:
                raise ValueError("Trendline Minimum Pivot Distance must be greater than 0.")
            if trendline_buffer < 0 or trendline_buffer >= 100:
                raise ValueError(
                    "Trendline Breakout Buffer must be >= 0% and less than 100%."
                )
            if trendline_retest_candles <= 0:
                raise ValueError("Trendline Retest Candles must be greater than 0.")
            if trendline_entry_mode not in ("FRESH_BREAK", "CURRENT_TREND", "BREAK_RETEST"):
                raise ValueError("Trendline Entry must be FRESH_BREAK, CURRENT_TREND, or BREAK_RETEST.")

            use_divergence = bool(self.v_use_divergence.get())
            div_pivot = int(self.e_div_pivot.get())
            div_source = self.v_div_source.get().strip()
            div_type = self.v_div_type.get().strip()
            div_min_count = int(self.e_div_min_count.get())
            div_max_pivots = int(self.e_div_max_pivots.get())
            div_max_bars = int(self.e_div_max_bars.get())
            div_entry_mode = self.v_div_entry_mode.get().strip().upper()
            if div_pivot < 1 or div_pivot > 50:
                raise ValueError("Divergence Pivot Period must be 1-50.")
            if div_source not in ("Close", "High/Low"):
                raise ValueError("Divergence Source must be Close or High/Low.")
            if div_type not in ("Regular", "Hidden", "Regular/Hidden"):
                raise ValueError("Divergence Type is invalid.")
            if div_min_count < 1 or div_min_count > 10:
                raise ValueError("Minimum Divergence must be 1-10.")
            if div_max_pivots < 1 or div_max_pivots > 20:
                raise ValueError("Maximum Divergence Pivots must be 1-20.")
            if div_max_bars < 30 or div_max_bars > 200:
                raise ValueError("Maximum Divergence Bars must be 30-200.")
            if div_entry_mode not in ("FRESH", "CURRENT_STATE"):
                raise ValueError("Divergence Entry must be FRESH or CURRENT_STATE.")
            div_use = {
                "div_use_macd": self.div_use_macd.get(),
                "div_use_macd_hist": self.div_use_macd_hist.get(),
                "div_use_rsi": self.div_use_rsi.get(),
                "div_use_stoch": self.div_use_stoch.get(),
                "div_use_cci": self.div_use_cci.get(),
                "div_use_momentum": self.div_use_momentum.get(),
                "div_use_obv": self.div_use_obv.get(),
                "div_use_vwmacd": self.div_use_vwmacd.get(),
                "div_use_cmf": self.div_use_cmf.get(),
                "div_use_mfi": self.div_use_mfi.get(),
            }
            if use_divergence and not any(div_use.values()):
                raise ValueError("Divergence requires at least one source indicator.")
            div_cfg = {
                "div_pivot": div_pivot, "div_source": div_source, "div_type": div_type,
                "div_max_pivots": div_max_pivots, "div_max_bars": div_max_bars,
                "div_cci_len": int(self.e_div_cci_len.get()), "div_mom_len": int(self.e_div_mom_len.get()),
                "div_entry_mode": div_entry_mode, **div_use
            }
            if div_cfg["div_cci_len"] <= 0 or div_cfg["div_mom_len"] <= 0:
                raise ValueError("Divergence CCI/Momentum lengths must be greater than 0.")

            use_vol_sr = bool(self.v_use_vol_sr.get())
            sr_volume_ma = int(self.e_sr_volume_ma.get())
            sr_vote_mode = self.v_sr_vote_mode.get().strip().upper()
            sr_entry_mode = self.v_sr_entry_mode.get().strip().upper()
            sr_tfs = [
                self.v_sr_tf1.get().strip(), self.v_sr_tf2.get().strip(),
                self.v_sr_tf3.get().strip(), self.v_sr_tf4.get().strip()
            ]
            if sr_volume_ma <= 0:
                raise ValueError("Volume S/R Volume MA threshold must be greater than 0.")
            if sr_vote_mode not in ("MAJORITY", "ANY", "ALL"):
                raise ValueError("Volume S/R Vote mode must be MAJORITY, ANY or ALL.")
            if sr_entry_mode not in ("CURRENT_ZONE", "FRESH_BREAK"):
                raise ValueError("Volume S/R Entry mode must be CURRENT_ZONE or FRESH_BREAK.")
            if use_vol_sr and all(tf == "Disable" for tf in sr_tfs):
                raise ValueError("Volume S/R requires at least one enabled timeframe.")

            use_atr = self.v_use_atr.get()
            atr_min_pct = float(self.e_atr_min_pct.get())
            if atr_min_pct < 0:
                raise ValueError("Minimum ATR % cannot be negative.")

            use_vol = self.v_use_vol.get()
            vol_len = int(
                self.e_vol_len.get()
            )
            if vol_len <= 0:
                raise ValueError("Volume MA period must be greater than 0.")

            use_adx = self.v_use_adx.get()
            adx_thresh = float(
                self.e_adx_thresh.get()
            )
            if adx_thresh < 0:
                raise ValueError("ADX threshold cannot be negative.")

            use_mtf = self.v_use_mtf.get()

            signal_mode = self.v_signal_mode.get().strip().upper()

            # Preset modes directly mean "how many directional indicators
            # must agree for this trade". SCORE keeps the existing custom
            # minimum-score concept.
            preset_scores = {
                "SINGLE_SIGNAL": 1,
                "ANY_NON_CONFLICTING": 1,
                "2_SIGNALS": 2,
                "3_SIGNALS": 3,
                "4_SIGNALS": 4,
            }

            if signal_mode in preset_scores:
                min_score = preset_scores[signal_mode]
            else:
                min_score = int(self.e_min_score.get().strip())

            adaptive_edge = float(self.e_adaptive_edge.get())
            adaptive_min_weight = float(self.e_adaptive_min_weight.get())
            if not 0.0 < adaptive_edge < 1.0 or adaptive_min_weight <= 0:
                raise ValueError("Adaptive strategy settings are invalid.")

            # Keep the selected adaptive values visible to the pure engine.
            # The engine uses these values through temporary constants below.
            allowed_signal_modes = SUPPORTED_SIGNAL_MODES

            if signal_mode not in allowed_signal_modes:
                raise ValueError(
                    f"Unknown signal mode: {signal_mode}"
                )

            if min_score <= 0:
                raise ValueError(
                    "Minimum score must be greater than 0."
                )

            size_mode = (
                self.v_size_mode.get()
            )

            risk_pct = (
                float(
                    self.e_risk_pct.get()
                ) / 100.0
            )

            fixed_qty = float(
                self.e_fixed_qty.get()
            )
            if risk_pct <= 0 or risk_pct >= 1.0:
                raise ValueError("Risk Per Trade must be greater than 0% and less than 100%.")
            if fixed_qty <= 0:
                raise ValueError("Fixed Qty must be greater than 0.")

            max_dd = (
                float(
                    self.e_max_dd.get()
                ) / 100.0
            )
            if not 0.0 <= max_dd < 1.0:
                raise ValueError("Max Daily Drawdown must be between 0% and less than 100%. Use 0% to disable it.")
            emergency_capital_loss = float(self.e_emergency_capital_pct.get()) / 100.0
            emergency_scope = self.v_emergency_scope.get().strip().upper()
            if emergency_scope not in ("BOT_SYMBOL", "ALL_ACCOUNT"):
                raise ValueError("Emergency Scope must be BOT_SYMBOL or ALL_ACCOUNT.")
            if not 0.0 <= emergency_capital_loss < 1.0:
                raise ValueError("Emergency Capital Loss Stop must be between 0% and less than 100%.")

            leverage = int(
                self.e_lev.get().strip()
            )

            sl_mode = self.v_sl_mode.get().strip().upper()
            tp_mode = self.v_tp_mode.get().strip().upper()
            if sl_mode not in ("PRICE_%", "ROI_%"):
                raise ValueError(f"Unknown SL mode: {sl_mode}")
            if tp_mode not in ("PRICE_%", "ROI_%"):
                raise ValueError(f"Unknown TP mode: {tp_mode}")

            sl_target_pct = float(
                self.e_sl_pct.get()
            )
            hold_sl_roi_pct = float(
                self.e_hold_sl_roi.get()
            )
            tp1_target_pct = float(
                self.e_tp1_pct.get()
            )
            tp2_target_pct = float(
                self.e_tp2_pct.get()
            )

            tp_qty_mode = (
                self.v_tp_qty_mode.get()
            )

            tp1_close_value = float(
                self.e_tp1_close.get()
            )

            tp2_close_value = float(
                self.e_tp2_close.get()
            )

            # Basic configuration validation.
            if (
                sl_target_pct <= 0
                or hold_sl_roi_pct <= 0
                or tp1_target_pct <= 0
                or tp2_target_pct <= 0
            ):
                raise ValueError(
                    "SL/TP targets and Hold-All-Reverse SL ROI must be greater than 0."
                )

            if leverage <= 0:
                raise ValueError(
                    "Leverage must be greater than 0."
                )

            if sl_mode not in ("PRICE_%", "ROI_%") or tp_mode not in ("PRICE_%", "ROI_%"):
                raise ValueError(f"Unknown SL/TP mode: SL={sl_mode} TP={tp_mode}")

            if tp_qty_mode not in (
                "PERCENT_%",
                "FIXED_QTY",
            ):
                raise ValueError(
                    f"Unknown TP quantity mode: {tp_qty_mode}"
                )

            if tp1_close_value <= 0 or tp2_close_value <= 0:
                raise ValueError(
                    "TP1 and TP2 close values must both be greater than 0."
                )

            if (
                tp_qty_mode == "PERCENT_%"
                and abs((tp1_close_value + tp2_close_value) - 100.0) > 1e-9
            ):
                raise ValueError(
                    "TP1 + TP2 close percentages must equal 100%."
                )

            # Hold-All-Reverse has its own dedicated hard-stop setting.
            # When ON, the stop is ALWAYS interpreted as ROI %, independent
            # of the normal SL Mode / SL Target controls.
            hold_all_reverse = bool(self.v_hold_until_all_reverse.get())
            effective_sl_target_pct = (
                hold_sl_roi_pct if hold_all_reverse else sl_target_pct
            )
            effective_sl_mode = (
                "ROI_%" if hold_all_reverse else sl_mode
            )

            # The sizing engine needs the actual market-price distance
            # of the effective stop.
            sl_price_fraction = (
                self.target_to_price_fraction(
                    effective_sl_target_pct,
                    effective_sl_mode,
                    leverage,
                )
            )

            self.log(
                f"SL mode: {sl_mode} | TP mode: {tp_mode} | "
                f"Leverage={leverage}x"
            )

            self.log(
                f"Targets: SL={sl_target_pct:g}% | "
                f"TP1={tp1_target_pct:g}% | "
                f"TP2={tp2_target_pct:g}%"
            )

            if hold_all_reverse:
                if self.v_hold_sl_wait_reversal.get():
                    self.log(
                        f"HOLD-ALL-REVERSE SL: {hold_sl_roi_pct:g}% ROI | "
                        "WAIT-FOR-ALL-REVERSE mode ON | No exchange SL; "
                        "threshold triggers a wait, then ALL active signals must reverse."
                    )
                else:
                    self.log(
                        f"HOLD-ALL-REVERSE SL: {hold_sl_roi_pct:g}% ROI | "
                        "Normal exchange hard SL is active."
                    )

            self.log(
                f"TP close mode: {tp_qty_mode} | "
                f"TP1={tp1_close_value:g} | "
                f"TP2={tp2_close_value:g}"
            )

            if sl_mode == "ROI_%" or tp_mode == "ROI_%":
                self.log(
                    f"ROI-to-price conversion: "
                    f"SL={sl_price_fraction * 100:.6g}% | "
                    f"TP1={self.target_to_price_fraction(tp1_target_pct, tp_mode, leverage) * 100:.6g}% | "
                    f"TP2={self.target_to_price_fraction(tp2_target_pct, tp_mode, leverage) * 100:.6g}%"
                )

            grid_cfg = self._grid_validate_settings()
            # Fixed execution cadence shared by the normal and Grid loops.
            # Grid previously referenced an undefined `poll_seconds`.
            poll_seconds = 30.0

            while self.is_running:
                cycle_start = time.time()

                try:
                    # ------------------------------------------------
                    # 1. Balance / drawdown
                    # ------------------------------------------------
                    curr_balance = (
                        self.fetch_balance_total()
                    )
                    curr_equity = self.fetch_account_equity()
                    self.session_peak_equity = max(float(self.session_peak_equity or 0.0), float(curr_equity))
                    self.daily_peak_equity = max(float(self.daily_peak_equity or 0.0), float(curr_equity))

                    # Reset the daily drawdown reference at local midnight.
                    # Emergency Capital Loss Stop remains session-based.
                    today = datetime.now().date()
                    if self.daily_start_date != today:
                        self.daily_start_date = today
                        self.daily_start_balance = curr_balance
                        self.daily_peak_equity = curr_equity
                        self.log(
                            f"DAILY RISK RESET: {today.isoformat()} | "
                            f"Daily Start Balance={curr_balance:.4f}"
                        )

                    emergency_threshold = self.start_balance * (1.0 - emergency_capital_loss)
                    if emergency_capital_loss > 0 and curr_equity <= emergency_threshold:
                        self._emergency_flatten_all_positions(
                            reason=f"Emergency Capital Loss Stop {emergency_capital_loss * 100:.2f}% reached",
                            equity=curr_equity,
                            threshold=emergency_threshold,
                        )
                        break

                    drawdown = (
                        (self.daily_peak_equity - curr_equity) / self.daily_peak_equity
                        if self.daily_peak_equity > 0 else 0.0
                    )

                    self.net_pnl = (
                        curr_balance
                        - self.start_balance
                    )

                    if (
                        max_dd > 0
                        and drawdown >= max_dd
                    ):
                        self.log(
                            f"CRITICAL: Max drawdown "
                            f"{max_dd * 100:.2f}% reached. "
                            f"Bot stopped."
                        )

                        self.send_telegram(
                            "Circuit breaker triggered. Bot stopped."
                        )

                        # This code executes in the worker thread. Do not call
                        # stop_bot(), which accesses Tkinter widgets directly.
                        # The worker finally block performs checkpoint/DB close
                        # and releases the profile lock.
                        self.is_running = False
                        break

                    # ------------------------------------------------
                    # 2. Market data
                    # ------------------------------------------------
                    ohlcv = self._fetch_strategy_ohlcv(
                        timeframe=timeframe,
                        limit=600 if (use_nwe or use_liq_swings or use_trendline or use_divergence) else 250,
                    )

                    if timeframe == "45m":
                        self.log(
                            "TIMEFRAME ENGINE: 45m candles are synthetic 45m bars from 15m Bybit candles; only completed 45m bars are traded."
                        )

                    df = pd.DataFrame(
                        ohlcv,
                        columns=[
                            "time",
                            "open",
                            "high",
                            "low",
                            "close",
                            "vol",
                        ],
                    )
                    if len(df) < 30:
                        raise RuntimeError("INSUFFICIENT_MARKET_DATA")
                    latest_ts = int(df["time"].iloc[-1])
                    self.last_market_data_ts = latest_ts
                    tf_minutes = {"1m":1,"3m":3,"5m":5,"15m":15,"30m":30,"45m":45,"1h":60,"4h":240}[timeframe]
                    stale_limit_ms = int(tf_minutes * 60_000 * MAX_DATA_STALENESS_MULTIPLIER)
                    if int(time.time()*1000) - latest_ts > stale_limit_ms:
                        raise RuntimeError(f"STALE_MARKET_DATA latest={latest_ts} age_ms={int(time.time()*1000)-latest_ts}")

                    df = calculate_supertrend(
                        df,
                        length=st_len,
                        multiplier=st_mult,
                        source=st_source,
                        change_atr=st_change_atr,
                    )
                    
                    # All chart indicators below use this SAME selected
                    # strategy timeframe. The only intentional exception is
                    # the optional 4H MTF confirmation, which always uses
                    # completed 4H candles. 45m is synthesized from 15m data.

                    df = calculate_adx(df)

                    df["ema"] = (
                        df["close"].ewm(
                            span=ema_len,
                            adjust=False,
                        ).mean()
                    )

                    # Optional independent EMA crossover filter.
                    # The crossover is evaluated ONLY on completed candles:
                    # -3 = candle before the latest completed candle
                    # -2 = latest completed candle
                    df["ema_fast"] = (
                        df["close"].ewm(
                            span=ema_fast_len,
                            adjust=False,
                        ).mean()
                    )

                    df["ema_slow"] = (
                        df["close"].ewm(
                            span=ema_slow_len,
                            adjust=False,
                        ).mean()
                    )

                    if use_macd:
                        df = calculate_macd(
                            df,
                            fast=macd_fast_len,
                            slow=macd_slow_len,
                            signal=macd_signal_len,
                        )

                    if use_rsi:
                        df = calculate_rsi(
                            df,
                            length=rsi_len,
                        )
                        df = calculate_rsi_ma(
                            df,
                            rsi_ma_type=rsi_ma_type,
                            length=rsi_ma_len,
                        )

                    if use_bb:
                        df = calculate_bollinger(
                            df,
                            length=bb_len,
                            std_mult=bb_std,
                        )

                    if use_stoch:
                        df = calculate_stochastic(
                            df,
                            k_length=stoch_k_len,
                            k_smooth=stoch_smooth_len,
                            d_length=stoch_d_len,
                        )

                    if use_vwap:
                        df = calculate_vwap(
                            df,
                            length=vwap_len,
                        )

                    if use_vwap_delta:
                        df = calculate_vwap_delta(
                            df,
                            smoothing=vwap_delta_smooth,
                            smoothing_length=vwap_delta_smooth_len,
                            baseline_length=vwap_delta_baseline_len,
                        )

                    if use_vidya:
                        df = calculate_vidya(
                            df,
                            vidya_length=vidya_len,
                            vidya_momentum=vidya_momentum,
                            band_distance=vidya_band,
                            atr_length=200,
                            smoothing_length=15,
                        )

                    if use_nwe:
                        df = calculate_nadaraya_watson_envelope(
                            df,
                            bandwidth=nwe_bandwidth,
                            multiplier=nwe_mult,
                            lookback=500,
                            mae_length=499,
                        )

                    if use_liq_swings:
                        df = calculate_liquidity_swings(
                            df,
                            length=liq_length,
                            area=liq_area,
                            filter_options=liq_filter,
                            filter_value=liq_filter_value,
                        )

                    if use_trendline:
                        df = calculate_trendline_breakout(
                            df,
                            length=trendline_length,
                            min_pivot_distance=trendline_min_distance,
                            breakout_buffer_pct=trendline_buffer,                            retest_candles=trendline_retest_candles,
                        )

                    df["vol_ma"] = (
                        df["vol"].rolling(
                            vol_len
                        ).mean()
                    )

                    # V8.3.0 Divergence module. All calculations are causal:
                    # confirmed pivots only, no "don't wait for confirmation".
                    if use_divergence:
                        df = calculate_divergence_module(df, div_cfg)
                    else:
                        df["div_bull_count"] = 0
                        df["div_bear_count"] = 0
                        df["div_bull_signal"] = False
                        df["div_bear_signal"] = False
                        df["divergence_state"] = 0

                    sr_state = {"bull":False,"bear":False,"fresh_bull":False,"fresh_bear":False,"states":[]}
                    if use_vol_sr:
                        sr_frames = self._refresh_volume_sr_cache(
                            df, sr_tfs
                        )
                        sr_state = calculate_volume_sr_module(
                            [(tf, sr_frames.get(tf), tf != "Disable") for tf in sr_tfs],
                            {
                                "sr_volume_ma": sr_volume_ma,
                                "sr_vote_mode": sr_vote_mode,
                                "sr_entry_mode": sr_entry_mode,
                            },
                        )

                    advanced_key = (
                        int(df["div_bull_count"].iloc[-2]) if use_divergence else 0,
                        int(df["div_bear_count"].iloc[-2]) if use_divergence else 0,
                        bool(sr_state.get("fresh_bull")) if use_vol_sr else False,
                        bool(sr_state.get("fresh_bear")) if use_vol_sr else False,
                    )
                    if not any(advanced_key):
                        self.last_advanced_signal_log = None
                    elif advanced_key != self.last_advanced_signal_log:
                        self.log(
                            f"ADVANCED SIGNALS | Divergence B={advanced_key[0]} S={advanced_key[1]} | "
                            f"Volume-SR Fresh B={advanced_key[2]} S={advanced_key[3]}"
                        )
                        self.last_advanced_signal_log = advanced_key

                    # Use the LAST COMPLETED candle.
                    closed_idx = -2

                    close = float(
                        df["close"].iloc[
                            closed_idx
                        ]
                    )

                    # ------------------------------------------------
                    # 3. 4H MTF - also use completed candle
                    # ------------------------------------------------
                    mtf_pass_bull = True
                    mtf_pass_bear = True

                    if use_mtf:
                        ohlcv_4h = (
                            self.exchange.fetch_ohlcv(
                                self.symbol,
                                timeframe="4h",
                                limit=250,
                            )
                        )

                        df_4h = pd.DataFrame(
                            ohlcv_4h,
                            columns=[
                                "time",
                                "open",
                                "high",
                                "low",
                                "close",
                                "vol",
                            ],
                        )

                        df_4h["ema200"] = (
                            df_4h["close"].ewm(
                                span=200,
                                adjust=False,
                            ).mean()
                        )

                        mtf_idx = -2

                        mtf_pass_bull = (
                            df_4h["close"].iloc[
                                mtf_idx
                            ]
                            >
                            df_4h["ema200"].iloc[
                                mtf_idx
                            ]
                        )

                        mtf_pass_bear = (
                            df_4h["close"].iloc[
                                mtf_idx
                            ]
                            <
                            df_4h["ema200"].iloc[
                                mtf_idx
                            ]
                        )

                    # ------------------------------------------------
                    # 4. Strategy signal
                    # ------------------------------------------------
                    st_flip_bull = (
                        not use_st
                        or (
                            not df["trend"].iloc[-3]
                            and df["trend"].iloc[-2]
                        )
                    )

                    st_flip_bear = (
                        not use_st
                        or (
                            df["trend"].iloc[-3]
                            and not df["trend"].iloc[-2]
                        )
                    )

                    st_entry_mode = self.v_st_entry_mode.get().strip().upper()

                    # FRESH_FLIP: only the newly completed candle's flip triggers.
                    # CURRENT_TREND: the current completed Supertrend direction
                    # can trigger even when the trend began earlier.
                    st_trend_bull = bool(df["trend"].iloc[-2])
                    st_trend_bear = not st_trend_bull

                    if st_entry_mode == "CURRENT_TREND":
                        st_entry_bull = st_trend_bull if use_st else True
                        st_entry_bear = st_trend_bear if use_st else True
                    else:
                        st_entry_bull = st_flip_bull
                        st_entry_bear = st_flip_bear

                    ema_bull = (
                        not use_ema
                        or close
                        > df["ema"].iloc[-2]
                    )

                    ema_bear = (
                        not use_ema
                        or close
                        < df["ema"].iloc[-2]
                    )

                    # Optional EMA fast/slow directional module.
                    # FRESH_CROSS: BUY only on a fresh Fast-over-Slow crossover
                    #              on the latest completed candle; SELL only on
                    #              a fresh Fast-under-Slow crossover.
                    # CURRENT_TREND: BUY while Fast > Slow; SELL while Fast < Slow.
                    # This is independent from the existing EMA Filter.
                    ema_cross_up = (
                        df["ema_fast"].iloc[-3]
                        <= df["ema_slow"].iloc[-3]
                        and
                        df["ema_fast"].iloc[-2]
                        > df["ema_slow"].iloc[-2]
                    )
                    ema_cross_down = (
                        df["ema_fast"].iloc[-3]
                        >= df["ema_slow"].iloc[-3]
                        and
                        df["ema_fast"].iloc[-2]
                        < df["ema_slow"].iloc[-2]
                    )
                    ema_cross_trend_bull = (
                        float(df["ema_fast"].iloc[-2])
                        > float(df["ema_slow"].iloc[-2])
                    )
                    ema_cross_trend_bear = (
                        float(df["ema_fast"].iloc[-2])
                        < float(df["ema_slow"].iloc[-2])
                    )

                    if ema_cross_entry_mode == "CURRENT_TREND":
                        ema_cross_bull = (
                            not use_ema_cross or ema_cross_trend_bull
                        )
                        ema_cross_bear = (
                            not use_ema_cross or ema_cross_trend_bear
                        )
                    else:
                        ema_cross_bull = (
                            not use_ema_cross or ema_cross_up
                        )
                        ema_cross_bear = (
                            not use_ema_cross or ema_cross_down
                        )

                    # Optional MACD fresh crossover filter.
                    macd_bull = (
                        not use_macd
                        or (
                            df["macd"].iloc[-3]
                            <= df["macd_signal"].iloc[-3]
                            and
                            df["macd"].iloc[-2]
                            > df["macd_signal"].iloc[-2]
                        )
                    )

                    macd_bear = (
                        not use_macd
                        or (
                            df["macd"].iloc[-3]
                            >= df["macd_signal"].iloc[-3]
                            and
                            df["macd"].iloc[-2]
                            < df["macd_signal"].iloc[-2]
                        )
                    )

                    # RSI trade logic. All calculations use completed candles.
                    # IMPORTANT: when RSI is disabled, do not access df["rsi"] or
                    # df["rsi_ma"], because those columns are intentionally not
                    # calculated. Disabled RSI must never stop the execution cycle.
                    if use_rsi:
                        rsi_reversal_bull = (
                            float(df["rsi"].iloc[-2]) <= rsi_os
                        )
                        rsi_reversal_bear = (
                            float(df["rsi"].iloc[-2]) >= rsi_ob
                        )
                        rsi_cross_bull = (
                            float(df["rsi"].iloc[-3])
                            <= float(df["rsi_ma"].iloc[-3])
                            and
                            float(df["rsi"].iloc[-2])
                            > float(df["rsi_ma"].iloc[-2])
                        )
                        rsi_cross_bear = (
                            float(df["rsi"].iloc[-3])
                            >= float(df["rsi_ma"].iloc[-3])
                            and
                            float(df["rsi"].iloc[-2])
                            < float(df["rsi_ma"].iloc[-2])
                        )

                        if rsi_logic == "CROSS_MA":
                            rsi_bull = rsi_cross_bull
                            rsi_bear = rsi_cross_bear
                        elif rsi_logic == "EITHER":
                            rsi_bull = (
                                rsi_reversal_bull
                                or rsi_cross_bull
                            )
                            rsi_bear = (
                                rsi_reversal_bear
                                or rsi_cross_bear
                            )
                        else:
                            rsi_bull = rsi_reversal_bull
                            rsi_bear = rsi_reversal_bear
                    else:
                        # RSI is disabled: it must not participate in any
                        # signal mode and must not block a trade.
                        rsi_bull = True
                        rsi_bear = True

                    # Bollinger breakout filter.
                    bb_bull = (
                        not use_bb
                        or df["close"].iloc[-2] > df["bb_upper"].iloc[-2]
                    )

                    bb_bear = (
                        not use_bb
                        or df["close"].iloc[-2] < df["bb_lower"].iloc[-2]
                    )

                    # Stochastic fresh K/D crossover.
                    stoch_bull = (
                        not use_stoch
                        or (
                            df["stoch_k"].iloc[-3]
                            <= df["stoch_d"].iloc[-3]
                            and
                            df["stoch_k"].iloc[-2]
                            > df["stoch_d"].iloc[-2]
                        )
                    )

                    stoch_bear = (
                        not use_stoch
                        or (
                            df["stoch_k"].iloc[-3]
                            >= df["stoch_d"].iloc[-3]
                            and
                            df["stoch_k"].iloc[-2]
                            < df["stoch_d"].iloc[-2]
                        )
                    )

                    # Rolling VWAP trend filter.
                    vwap_bull = (
                        not use_vwap
                        or df["close"].iloc[-2] > df["vwap"].iloc[-2]
                    )

                    vwap_bear = (
                        not use_vwap
                        or df["close"].iloc[-2] < df["vwap"].iloc[-2]
                    )

                    if use_vwap_delta:
                        vd_now = float(df["vwap_delta"].iloc[-2])
                        vd_base_now = float(df["vwap_delta_baseline"].iloc[-2])
                        vd_prev = float(df["vwap_delta"].iloc[-3])
                        vd_base_prev = float(df["vwap_delta_baseline"].iloc[-3])
                        if vwap_delta_logic == "CROSS_BASELINE":
                            vwap_delta_bull = vd_prev <= vd_base_prev and vd_now > vd_base_now
                            vwap_delta_bear = vd_prev >= vd_base_prev and vd_now < vd_base_now
                        else:
                            vwap_delta_bull = vd_now > vd_base_now
                            vwap_delta_bear = vd_now < vd_base_now
                    else:
                        vwap_delta_bull = True
                        vwap_delta_bear = True

                    if use_vidya:
                        if vidya_entry_mode == "FRESH_FLIP":
                            vidya_bull = bool(df["vidya_cross_up"].iloc[-2])
                            vidya_bear = bool(df["vidya_cross_down"].iloc[-2])
                        else:
                            vidya_bull = bool(df["vidya_trend_up"].iloc[-2])
                            vidya_bear = not bool(df["vidya_trend_up"].iloc[-2])
                    else:
                        vidya_bull = True
                        vidya_bear = True

                    if use_nwe:
                        nwe_out_now = float(df["nwe_out"].iloc[-2])
                        nwe_out_prev = float(df["nwe_out"].iloc[-3])
                        nwe_upper_now = float(df["nwe_upper"].iloc[-2])
                        nwe_lower_now = float(df["nwe_lower"].iloc[-2])
                        nwe_close_now = float(df["close"].iloc[-2])
                        nwe_close_prev = float(df["close"].iloc[-3])
                        nwe_upper_prev = float(df["nwe_upper"].iloc[-3])
                        nwe_lower_prev = float(df["nwe_lower"].iloc[-3])
                        finite = all(np.isfinite(x) for x in (
                            nwe_out_now, nwe_out_prev, nwe_upper_now,
                            nwe_lower_now, nwe_close_now, nwe_close_prev,
                            nwe_upper_prev, nwe_lower_prev,
                        ))
                        if not finite:
                            nwe_bull = False
                            nwe_bear = False
                        elif nwe_entry_mode == "FRESH_CROSS":
                            nwe_bull = nwe_close_now < nwe_lower_now and nwe_close_prev >= nwe_lower_prev
                            nwe_bear = nwe_close_now > nwe_upper_now and nwe_close_prev <= nwe_upper_prev
                        else:
                            nwe_bull = nwe_out_now > nwe_out_prev
                            nwe_bear = nwe_out_now < nwe_out_prev
                    else:
                        nwe_bull = True
                        nwe_bear = True

                    # LuxAlgo Liquidity Swings directional module.
                    # FRESH_BREAK: only a completed candle breaking the latest
                    # confirmed swing level creates a signal.
                    # CURRENT_TREND: remain bullish after a swing-high breakout
                    # and bearish after a swing-low breakout until the opposite
                    # liquidity level breaks.
                    if use_liq_swings:
                        liq_bull_break = bool(df["liq_swing_high_break"].iloc[-2])
                        liq_bear_break = bool(df["liq_swing_low_break"].iloc[-2])
                        if liq_entry_mode == "CURRENT_TREND":
                            liq_state = int(df["liq_swing_trend"].iloc[-2])
                            liq_bull = liq_state > 0
                            liq_bear = liq_state < 0
                        else:
                            liq_bull = liq_bull_break
                            liq_bear = liq_bear_break
                    else:
                        liq_bull = True
                        liq_bear = True

                    # Confirmed-pivot Trendline Breakout directional module.
                    # FRESH_BREAK: completed candle crosses the active line.
                    # CURRENT_TREND: persist after a breakout until opposite.
                    # BREAK_RETEST: require a later retest of the broken line
                    # and a close back in the breakout direction.
                    if use_trendline:
                        tl_up_break = bool(df["trendline_break_up"].iloc[-2])
                        tl_down_break = bool(df["trendline_break_down"].iloc[-2])
                        tl_up_retest = bool(df["trendline_retest_up"].iloc[-2])
                        tl_down_retest = bool(df["trendline_retest_down"].iloc[-2])
                        tl_state = int(df["trendline_state"].iloc[-2])
                        if trendline_entry_mode == "CURRENT_TREND":
                            trendline_bull = tl_state > 0
                            trendline_bear = tl_state < 0
                        elif trendline_entry_mode == "BREAK_RETEST":
                            trendline_bull = tl_up_retest
                            trendline_bear = tl_down_retest
                        else:
                            trendline_bull = tl_up_break
                            trendline_bear = tl_down_break
                    else:
                        trendline_bull = True
                        trendline_bear = True

                    # ATR volatility filter: ATR as % of price.
                    atr_pct = (
                        float(df["atr"].iloc[-2])
                        / close
                        * 100.0
                        if close > 0
                        else 0.0
                    )

                    atr_pass = (
                        not use_atr
                        or atr_pct >= atr_min_pct
                    )

                    vol_pass = (
                        not use_vol
                        or (
                            df["vol"].iloc[-2]
                            >
                            df["vol_ma"].iloc[-2]
                        )
                    )

                    adx_pass = (
                        not use_adx
                        or (
                            df["adx"].iloc[-2]
                            >= adx_thresh
                        )
                    )

                    # ------------------------------------------------
                    # 5. Signal decision
                    # ------------------------------------------------
                    # Every enabled module can participate in the
                    # 1/2/3/4/SCORE voting system. This includes Volume,
                    # ADX and ATR. Directional indicators provide their own
                    # direction. Non-directional modules get a transparent
                    # directional interpretation when their condition passes:
                    #   Volume -> completed candle direction when volume > MA
                    #   ADX    -> +DI/-DI direction when ADX >= threshold
                    #   ATR    -> completed candle direction when ATR% passes
                    # This makes Supertrend + Volume with 2_SIGNALS mean
                    # both conditions must vote in the same direction.
                    # Supertrend entry mode controls whether ST uses a fresh flip or current trend.
                    directional_modules = []

                    candle_bull = (
                        float(df["close"].iloc[-2])
                        > float(df["open"].iloc[-2])
                    )
                    candle_bear = (
                        float(df["close"].iloc[-2])
                        < float(df["open"].iloc[-2])
                    )

                    if use_st:
                        if st_entry_mode == "CURRENT_TREND":
                            st_score_bull = st_trend_bull
                            st_score_bear = st_trend_bear
                        elif signal_mode == "SCORE":
                            st_score_bull = st_trend_bull
                            st_score_bear = st_trend_bear
                        else:
                            st_score_bull = st_flip_bull
                            st_score_bear = st_flip_bear
                        directional_modules.append(
                            ("ST", st_score_bull, st_score_bear)
                        )

                    if use_ema:
                        directional_modules.append(
                            ("EMA", ema_bull, ema_bear)
                        )

                    if use_ema_cross:
                        directional_modules.append(
                            ("EMA_CROSS", ema_cross_bull, ema_cross_bear)
                        )

                    if use_macd:
                        directional_modules.append(
                            ("MACD", macd_bull, macd_bear)
                        )

                    if use_rsi:
                        directional_modules.append(
                            ("RSI", rsi_bull, rsi_bear)
                        )

                    if use_bb:
                        directional_modules.append(
                            ("BB", bb_bull, bb_bear)
                        )

                    if use_stoch:
                        directional_modules.append(
                            ("STOCH", stoch_bull, stoch_bear)
                        )

                    if use_vwap:
                        directional_modules.append(
                            ("VWAP", vwap_bull, vwap_bear)
                        )

                    if use_vwap_delta:
                        directional_modules.append(
                            ("VWAP_DELTA", vwap_delta_bull, vwap_delta_bear)
                        )

                    if use_vidya:
                        directional_modules.append(
                            ("VIDYA", vidya_bull, vidya_bear)
                        )

                    if use_nwe:
                        directional_modules.append(
                            ("NWE", nwe_bull, nwe_bear)
                        )

                    if use_liq_swings:
                        directional_modules.append(
                            ("LIQ_SWING", liq_bull, liq_bear)
                        )

                    if use_trendline:
                        directional_modules.append(
                            ("TRENDLINE", trendline_bull, trendline_bear)
                        )

                    if use_mtf:
                        directional_modules.append(
                            ("MTF", mtf_pass_bull, mtf_pass_bear)
                        )

                    # V8.3.0 Divergence directional module.
                    if use_divergence:
                        div_bull_count = int(df["div_bull_count"].iloc[-2])
                        div_bear_count = int(df["div_bear_count"].iloc[-2])
                        div_state = int(df["divergence_state"].iloc[-2])
                        if div_entry_mode == "CURRENT_STATE":
                            divergence_bull = div_state > 0 and div_bull_count >= div_min_count
                            divergence_bear = div_state < 0 and div_bear_count >= div_min_count
                        else:
                            divergence_bull = (
                                bool(df["div_bull_signal"].iloc[-2])
                                and div_bull_count >= div_min_count
                            )
                            divergence_bear = (
                                bool(df["div_bear_signal"].iloc[-2])
                                and div_bear_count >= div_min_count
                            )
                        directional_modules.append(
                            ("DIVERGENCE", divergence_bull, divergence_bear)
                        )

                    # V8.3.0 Volume-based Support/Resistance Zones.
                    if use_vol_sr:
                        directional_modules.append(
                            ("VOL_SR", bool(sr_state["bull"]), bool(sr_state["bear"]))
                        )

                    # Volume is a strength/participation measure rather than
                    # a direction by itself. If volume is above its MA, its
                    # vote follows the completed candle direction.
                    if use_vol and vol_pass and signal_mode != "ADAPTIVE_SCORE":
                        directional_modules.append(
                            ("VOL", candle_bull, candle_bear)
                        )

                    # ADX becomes directional through +DI versus -DI, while
                    # the ADX threshold remains the strength requirement.
                    if use_adx and adx_pass:
                        adx_bull = (
                            float(df["plus_di"].iloc[-2])
                            > float(df["minus_di"].iloc[-2])
                        )
                        adx_bear = (
                            float(df["minus_di"].iloc[-2])
                            > float(df["plus_di"].iloc[-2])
                        )
                        directional_modules.append(
                            ("ADX", adx_bull, adx_bear)
                        )

                    # ATR is volatility-only. When the ATR threshold passes,
                    # its vote follows the completed candle direction.
                    if use_atr and atr_pass and signal_mode != "ADAPTIVE_SCORE":
                        directional_modules.append(
                            ("ATR", candle_bull, candle_bear)
                        )

                    buy_score = sum(
                        1 for _, bull, _ in directional_modules
                        if bull
                    )
                    sell_score = sum(
                        1 for _, _, bear in directional_modules
                        if bear
                    )

                    directional_count = len(directional_modules)

                    # ------------------------------------------------
                    # Grid Strategy integration
                    # ------------------------------------------------
                    # IMPORTANT:
                    # Grid SCORE uses the COMPLETE Section 3 Strategy engine.
                    # Every enabled Strategy indicator participates here:
                    #   ST, EMA, EMA Cross, MACD, RSI, BB, STOCH, VWAP,
                    #   VWAP Delta, VIDYA, NWE, Liquidity Swings, Trendline,
                    #   MTF, Volume, ADX and ATR.
                    #
                    # The SAME GUI enable/disable switches and the SAME
                    # indicator parameters are used. There is no reduced
                    # five-indicator Grid-only implementation.
                    #
                    # We intentionally use the already-built directional_modules
                    # unchanged. That means the Grid receives the exact same
                    # completed-candle signal state/entry-mode logic as Section 3.
                    # The only thing that differs is the threshold: Grid Score
                    # Min is independent from the normal Strategy Signal Mode.
                    grid_directional_modules = list(directional_modules)

                    if signal_mode == "ADAPTIVE_SCORE":
                        grid_buy_score = sum(
                            ADAPTIVE_MODULE_WEIGHTS.get(name, 1.0)
                            for name, bull, bear in grid_directional_modules if bull and not bear
                        )
                        grid_sell_score = sum(
                            ADAPTIVE_MODULE_WEIGHTS.get(name, 1.0)
                            for name, bull, bear in grid_directional_modules if bear and not bull
                        )
                        grid_score_count = sum(
                            ADAPTIVE_MODULE_WEIGHTS.get(name, 1.0)
                            for name, _, _ in grid_directional_modules
                        )
                    else:
                        grid_buy_score = sum(1 for _, bull, _ in grid_directional_modules if bull)
                        grid_sell_score = sum(1 for _, _, bear in grid_directional_modules if bear)
                        grid_score_count = len(grid_directional_modules)

                    # Centralized, pure signal decision. Adaptive thresholds
                    # are explicit per-call parameters, preventing cross-profile
                    # races when multiple bots run concurrently.
                    buy_signal, sell_signal, buy_score, sell_score = self._decide_signal(
                        directional_modules,
                        signal_mode,
                        min_score,
                        atr_pass=atr_pass,
                        vol_pass=vol_pass,
                        adx_pass=adx_pass,
                        mtf_pass_bull=mtf_pass_bull,
                        mtf_pass_bear=mtf_pass_bear,
                        adaptive_edge=adaptive_edge,
                        adaptive_min_weight=adaptive_min_weight,
                    )

                    if grid_cfg["mode"] not in ("OFF", "DIRECT_SHOT"):
                        # Grid mode owns execution while selected, including its
                        # post-stop cooldown/inactive state. Never fall through
                        # into the normal signal-entry engine.
                        grid_handled = self._manage_grid(
                            self.symbol, curr_balance, curr_equity, grid_cfg,
                            st_trend_bull, st_trend_bear,
                            grid_buy_score, grid_sell_score
                        )
                        if grid_handled:
                            grid_status = "ACTIVE" if self.grid_state.get("active") else "STOPPED/COOLDOWN"
                            self.log(
                                f"[{self.exchange_id.upper()}] GRID | Mode={grid_cfg['mode']} | "
                                f"Status={grid_status} | Center={self.grid_state.get('center', 0):.12g} | "
                                f"Score=B{grid_buy_score}/S{grid_sell_score} of {grid_score_count} | "
                                f"GridMin={grid_cfg.get('score_min', 0)} | "
                                f"Strategy={','.join(name for name, _, _ in grid_directional_modules) or 'NONE'} | "
                                f"Position={self.fetch_position(self.symbol) or 'NONE'}"
                            )
                            cycle_elapsed = time.time() - cycle_start
                            time.sleep(max(0.5, poll_seconds - cycle_elapsed))
                            continue

                    decision_reason = StrategyEngine.decision_reason(
                        directional_modules, signal_mode, min_score,
                        atr_pass=atr_pass, vol_pass=vol_pass, adx_pass=adx_pass,
                        mtf_pass_bull=mtf_pass_bull, mtf_pass_bear=mtf_pass_bear,
                        adaptive_edge=adaptive_edge, adaptive_min_weight=adaptive_min_weight,
                    )

                    signal = "NONE"

                    if buy_signal:
                        signal = "BUY"
                    elif sell_signal:
                        signal = "SELL"

                    vwap_delta_state = (
                        "BULL"
                        if vwap_delta_bull
                        else "BEAR"
                        if vwap_delta_bear
                        else "NEUTRAL"
                    )
                    vidya_state = (
                        "BULL"
                        if vidya_bull
                        else "BEAR"
                        if vidya_bear
                        else "NEUTRAL"
                    )
                    nwe_state = (
                        "BULL"
                        if nwe_bull
                        else "BEAR"
                        if nwe_bear
                        else "NEUTRAL"
                    )

                    # ------------------------------------------------
                    # 5. Current actual position
                    # ------------------------------------------------
                    position = (
                        self.fetch_position(
                            self.symbol
                        )
                    )

                    if position:
                        pos_type = position["side"]
                        pos_qty = position["qty"]
                        pos_entry = position["entry"]

                        # Check whether TP1 has actually filled before
                        # evaluating the next signal/reversal.
                        self._manage_tp1_break_even(position)

                        # Optional Hold-SL mode: once the configured ROI
                        # threshold is reached, DO NOT close.  Wait for the
                        # all-active-signals reversal logic below.
                        self._manage_hold_sl_wait_reversal(position)

                        # Normal exchange-side protection reconciliation is
                        # skipped when Hold-SL wait mode intentionally has no
                        # exchange stop order.
                        try:
                            self._reconcile_protection_orders(position)
                        except Exception as protection_error:
                            # If protection state cannot be verified, do not
                            # continue generating new strategy entries. Pause
                            # the bot with the position untouched so the user
                            # can inspect/recover it rather than guessing.
                            self.log(
                                f"CRITICAL PROTECTION VERIFICATION ERROR: {protection_error} | "
                                "BOT PAUSED; no new entries will be opened."
                            )
                            try:
                                self.send_telegram(
                                    f"[{self.exchange_id.upper()}] PROTECTION VERIFICATION ERROR "
                                    f"{self.symbol}: bot paused; position was not silently changed."
                                )
                            except Exception:
                                pass
                            self._persist_runtime_state(
                                status="PAUSED_WITH_POSITION",
                                last_error=str(protection_error),
                            )
                            self.is_running = False
                            continue
                    else:
                        # A position disappeared without this loop intentionally
                        # reversing it.  Determine whether the exchange-side
                        # stop (including a TP1-created break-even stop) fired.
                        # The post-exit lock is specifically a STOP lock: TP1/TP2
                        # exits do not force a reversal signal before re-entry.
                        exited_side = None
                        exit_reason = "UNKNOWN"
                        previous_protection = self.last_protected_position
                        if previous_protection:
                            exited_side = previous_protection.get("side")
                            exit_reason = self._detect_protection_exit_reason(
                                previous_protection
                            )

                        # IMPORTANT: once a post-SL lock is created, it must persist
                        # across subsequent flat polling cycles until a valid opposite
                        # signal releases it.  Previously, last_protected_position was
                        # cleared below and the next flat cycle interpreted that as an
                        # UNKNOWN exit, clearing the lock and allowing an immediate
                        # same-direction re-entry.
                        lock_already_active = self.reentry_direction_lock in ("LONG", "SHORT")

                        if not lock_already_active and (
                            exited_side in ("LONG", "SHORT")
                            and self.v_require_opposite_after_exit.get()
                            and exit_reason in ("SL", "UNKNOWN")
                        ):
                            self.reentry_direction_lock = exited_side
                            self.reentry_lock_reason = f"{exit_reason}_EXIT"
                            self.log(
                                f"POST-SL LOCK: {exited_side} re-entry blocked after {exit_reason}. "
                                f"Waiting for a valid opposite signal under {signal_mode}."
                            )
                        elif not lock_already_active:
                            self.reentry_direction_lock = None
                            self.reentry_lock_reason = ""
                            if exit_reason in ("TP1", "TP2"):
                                self.log(
                                    f"POST-EXIT: {exit_reason} completed; no opposite-signal lock."
                                )
                        else:
                            self.log(
                                f"POST-SL LOCK PERSISTING: {self.reentry_direction_lock} re-entry remains blocked "
                                f"until a valid opposite signal under {signal_mode}."
                            )

                        if self.active_trade is not None:
                            try:
                                flat_balance = self.fetch_balance_total()
                            except Exception:
                                flat_balance = None
                            self._finalize_performance_trade(
                                reason="PROTECTION/EXTERNAL CLOSE",
                                balance=flat_balance,
                            )
                        self._remember_managed_order_ids(
                            self._known_managed_order_ids(self.symbol)
                        )
                        pos_type = "NONE"
                        pos_qty = 0.0
                        pos_entry = 0.0
                        self.last_protected_position = None
                        self.tp1_be_done = False
                        self.hold_sl_wait_reversal = False
                        self.hold_sl_threshold_hit = False
                        self.hold_sl_threshold_logged = False
                        self.last_protection_reconcile = 0.0
                        self.last_flat_time = time.time()

                    closed_candle_ts = int(df["time"].iloc[-2])
                    closed_candle_time = time.strftime(
                        "%H:%M:%S", time.gmtime(closed_candle_ts / 1000.0)
                    )
                    self.log(
                        f"[{self.exchange_id.upper()}] "
                        f"TF={timeframe} | "
                        f"Signal={signal} | "
                        f"ClosedCandle={close:.8f} | "
                        f"ClosedCandleTime={closed_candle_time} UTC | "
                        f"EMA_Filter={'ON' if use_ema else 'OFF'} "
                        f"EMA_Cross={'ON' if use_ema_cross else 'OFF'} "
                        f"Mode={ema_cross_entry_mode} "
                        f"Cross={'BULL' if ema_cross_bull and use_ema_cross else 'BEAR' if ema_cross_bear and use_ema_cross else 'NONE'} | "
                        f"STEntry={st_entry_mode} SignalMode={signal_mode} "
                        f"HoldAllReverse={'ON' if self.v_hold_until_all_reverse.get() else 'OFF'} "
                        f"PostSL_Lock={'ON' if self.v_require_opposite_after_exit.get() else 'OFF'} "
                        f"LockSide={self.reentry_direction_lock or 'NONE'} "
                        f"Confirmations={'OFF' if signal_mode in ('SINGLE_SIGNAL','ANY_NON_CONFLICTING','2_SIGNALS','3_SIGNALS','4_SIGNALS','SCORE','ADAPTIVE_SCORE') else 'ON'} "
                         f"States={','.join(name + ':' + ('BULL' if bull and not bear else 'BEAR' if bear and not bull else 'CONFLICT' if bull and bear else 'NEUTRAL') for name, bull, bear in directional_modules) or 'NONE'} "
                         f"Score=B{buy_score}/S{sell_score} "
                         f"Required={({'SINGLE_SIGNAL':1,'ANY_NON_CONFLICTING':1,'2_SIGNALS':2,'3_SIGNALS':3,'4_SIGNALS':4}.get(signal_mode, min_score))} | "
                         f"DecisionReason={decision_reason} | "
                        f"MACD={'ON' if use_macd else 'OFF'} "
                        f"RSI={'ON' if use_rsi else 'OFF'} "
                        f"BB={'ON' if use_bb else 'OFF'} "
                        f"STOCH={'ON' if use_stoch else 'OFF'} "
                        f"VWAP={'ON' if use_vwap else 'OFF'} "
                        f"VWAP_DELTA={'ON' if use_vwap_delta else 'OFF'}"
                        f"({vwap_delta_state}) "
                        f"VIDYA={'ON' if use_vidya else 'OFF'}"
                        f"({vidya_state}) "
                        f"LIQ_SWING={'ON' if use_liq_swings else 'OFF'}"
                        f"({liq_entry_mode if use_liq_swings else 'OFF'}) "
                        f"TRENDLINE={'ON' if use_trendline else 'OFF'}"
                        f"({trendline_entry_mode if use_trendline else 'OFF'}) "
                        f"ATR={'ON' if use_atr else 'OFF'} "
                        f"ATR%={atr_pct:.3f} | "
                        f"Position={pos_type} "
                        f"Qty={pos_qty}"
                    )

                    # ------------------------------------------------
                    # 6. If there is already a position in the same
                    #    direction, do NOT create another position.
                    # ------------------------------------------------
                    desired_side = (
                        "LONG"
                        if signal == "BUY"
                        else "SHORT"
                        if signal == "SELL"
                        else "NONE"
                    )

                    # ------------------------------------------------
                    # 7. New/reversal trade
                    # ------------------------------------------------
                    # Hold-All-Reverse must use PERSISTENT direction states,
                    # not one-bar entry events. Otherwise an indicator using
                    # FRESH_FLIP (EMA crossover, MACD crossover, etc.) could
                    # become neutral on the very next candle and prevent a
                    # legitimate reversal forever.
                    hold_directional_modules = []
                    if use_st:
                        hold_directional_modules.append(("ST", st_trend_bull, st_trend_bear))
                    if use_ema:
                        hold_directional_modules.append(("EMA", close > float(df["ema"].iloc[-2]), close < float(df["ema"].iloc[-2])))
                    if use_ema_cross:
                        # Reversal-hold uses the persistent EMA relationship,
                        # regardless of entry mode. This prevents a fresh
                        # crossover event from becoming neutral one candle later.
                        hold_directional_modules.append(
                            (
                                "EMA_CROSS",
                                ema_cross_trend_bull,
                                ema_cross_trend_bear,
                            )
                        )
                    if use_macd:
                        hold_directional_modules.append(("MACD", float(df["macd"].iloc[-2]) > float(df["macd_signal"].iloc[-2]), float(df["macd"].iloc[-2]) < float(df["macd_signal"].iloc[-2])))
                    if use_rsi:
                        hold_directional_modules.append(("RSI", float(df["rsi"].iloc[-2]) > 50.0, float(df["rsi"].iloc[-2]) < 50.0))
                    if use_bb:
                        hold_directional_modules.append(("BB", close > float(df["bb_mid"].iloc[-2]), close < float(df["bb_mid"].iloc[-2])))
                    if use_stoch:
                        hold_directional_modules.append(("STOCH", float(df["stoch_k"].iloc[-2]) > float(df["stoch_d"].iloc[-2]), float(df["stoch_k"].iloc[-2]) < float(df["stoch_d"].iloc[-2])))
                    if use_vwap:
                        hold_directional_modules.append(("VWAP", close > float(df["vwap"].iloc[-2]), close < float(df["vwap"].iloc[-2])))
                    if use_vwap_delta:
                        hold_directional_modules.append(("VWAP_DELTA", vwap_delta_bull, vwap_delta_bear))
                    if use_vidya:
                        hold_directional_modules.append(("VIDYA", bool(df["vidya_trend_up"].iloc[-2]), not bool(df["vidya_trend_up"].iloc[-2])))
                    if use_nwe:
                        hold_directional_modules.append(("NWE", nwe_out_now > nwe_out_prev, nwe_out_now < nwe_out_prev))
                    if use_liq_swings:
                        hold_directional_modules.append(("LIQ_SWING", bool(df["liq_swing_trend"].iloc[-2] > 0), bool(df["liq_swing_trend"].iloc[-2] < 0)))
                    if use_trendline:
                        hold_directional_modules.append(("TRENDLINE", bool(df["trendline_state"].iloc[-2] > 0), bool(df["trendline_state"].iloc[-2] < 0)))
                    if use_mtf:
                        hold_directional_modules.append(("MTF", mtf_pass_bull, mtf_pass_bear))
                    if use_divergence:
                        div_state = int(df["divergence_state"].iloc[-2])
                        hold_directional_modules.append(("DIVERGENCE", div_state > 0, div_state < 0))
                    if use_vol_sr:
                        hold_directional_modules.append(("VOL_SR", bool(sr_state["bull"]), bool(sr_state["bear"])))
                    if use_vol and vol_pass:
                        hold_directional_modules.append(("VOL", candle_bull, candle_bear))
                    if use_adx and adx_pass:
                        hold_directional_modules.append(("ADX", adx_bull, adx_bear))
                    if use_atr and atr_pass:
                        hold_directional_modules.append(("ATR", candle_bull, candle_bear))

                    reversal_allowed = True
                    if (
                        pos_type in ("LONG", "SHORT")
                        and desired_side != pos_type
                        and self.v_hold_until_all_reverse.get()
                    ):
                        if self.hold_sl_wait_reversal and not self.hold_sl_threshold_hit:
                            reversal_allowed = False
                            self.log(
                                f"HOLD-SL WAIT: {pos_type} remains open because the "
                                "configured Hold-SL ROI threshold has not been reached yet."
                            )
                        # IMPORTANT: a trend/signal change by ONE indicator is NOT
                        # an exit. A live position is closed/reversed by strategy
                        # only after ALL currently active directional modules have
                        # reversed to the opposite side. The hard SL remains an
                        # independent price-protection order and may only close the
                        # trade when its price trigger is reached.
                        opposite_checks = []
                        for name, bull, bear in hold_directional_modules:
                            opposite_checks.append((name, bool(bear if pos_type == "LONG" else bull)))
                        not_reversed = [name for name, is_opposite in opposite_checks if not is_opposite]
                        reversal_allowed = bool(opposite_checks) and not not_reversed
                        if not reversal_allowed:
                            self.log(
                                f"HOLD {pos_type}: signal={desired_side}; waiting for ALL active directional states to reverse. "
                                f"Waiting={', '.join(not_reversed) if not_reversed else 'NONE'}"
                            )
                        else:
                            self.log(
                                f"HOLD {pos_type}: ALL active directional states reversed -> strategy reversal allowed."
                            )

                    if (
                        desired_side in ("LONG", "SHORT")
                        and desired_side != pos_type
                        and reversal_allowed
                    ):
                        # Cancel old protection BEFORE changing side.
                        if pos_type != "NONE":
                            self.log(
                                "Reversal detected. "
                                "Cancelling old protection..."
                            )

                            self._cancel_known_managed_orders(
                                self.symbol
                            )

                            # This is a strategy reversal, not a protective exit.
                            # Do not carry a same-direction post-exit lock into the
                            # intentionally opposite position.
                            self.reentry_direction_lock = None
                            self.reentry_lock_reason = ""

                            self.close_position_market(
                                self.symbol,
                                pos_type,
                                pos_qty,
                            )

                            # Never place the opposite entry on top of a residual
                            # position. Wait briefly and verify the exchange is flat.
                            time.sleep(1.0)
                            if self.fetch_position(self.symbol):
                                self.log(
                                    "REVERSAL ABORTED: previous position is still open "
                                    "after close request; no opposite entry will be submitted."
                                )
                                cycle_elapsed = time.time() - cycle_start
                                time.sleep(max(0.5, poll_seconds - cycle_elapsed))
                                continue
                            try:
                                reversal_balance = self.fetch_balance_total()
                            except Exception:
                                reversal_balance = None
                            self._finalize_performance_trade(
                                reason="REVERSAL",
                                balance=reversal_balance,
                            )
                            self.last_flat_time = time.time()

                        else:
                            # If flat, clean up orphan orders.
                            self._cancel_known_managed_orders(
                                self.symbol
                            )

                        # Safety gates before opening a fresh position.
                        if pos_type == "NONE":
                            current_candle_ts = int(df["time"].iloc[-2])

                            # Post-exit direction lock: a LONG stopped/closed by
                            # protection must not immediately re-enter LONG while
                            # the strategy is still bullish; likewise for SHORT.
                            # The lock is released only when the opposite signal
                            # is actually produced.
                            if self.reentry_direction_lock in ("LONG", "SHORT"):
                                locked_side = self.reentry_direction_lock
                                if desired_side == locked_side:
                                    self.log(
                                        f"ENTRY BLOCKED: Post-SL Opposite Signal Lock is ON | "
                                        f"{locked_side} re-entry blocked until a valid {('SELL' if locked_side == 'LONG' else 'BUY')} signal under {signal_mode}."
                                    )
                                    cycle_elapsed = time.time() - cycle_start
                                    time.sleep(max(0.5, poll_seconds - cycle_elapsed))
                                    continue
                                elif desired_side == ("SHORT" if locked_side == "LONG" else "LONG"):
                                    self.log(
                                        f"POST-SL LOCK RELEASED: Valid opposite signal {signal} detected under {signal_mode}. "
                                        f"{locked_side} re-entry is now allowed again."
                                    )
                                    self.reentry_direction_lock = None
                                    self.reentry_lock_reason = ""

                            if no_same_candle and self.last_entry_candle_ts == current_candle_ts:
                                self.log("ENTRY BLOCKED: No Re-Entry Same Candle is ON.")
                                cycle_elapsed = time.time() - cycle_start
                                time.sleep(max(0.5, poll_seconds - cycle_elapsed))
                                continue
                            if cooldown_min > 0 and self.last_flat_time > 0:
                                remaining = cooldown_min * 60.0 - (time.time() - self.last_flat_time)
                                if remaining > 0:
                                    self.log(f"ENTRY BLOCKED: Cooldown active for {remaining:.0f}s.")
                                    cycle_elapsed = time.time() - cycle_start
                                    time.sleep(max(0.5, poll_seconds - cycle_elapsed))
                                    continue

                        # ------------------------------------------------
                        # Calculate requested entry quantity.
                        # This quantity is ONLY the entry request.
                        # Protection uses actual position qty later.
                        # ------------------------------------------------
                        entry_qty = (
                            self.calculate_entry_qty(
                                self.symbol,
                                curr_balance,
                                close,
                                risk_pct,
                                sl_price_fraction,
                                size_mode,
                                fixed_qty,
                            )
                        )

                        self.log(
                            f"ENTRY {desired_side}: "
                            f"Requested Qty={entry_qty}"
                        )

                        # PRE-ENTRY TP SPLIT SAFETY:
                        # FIXED_QTY means literal exchange quantity, not %.
                        # Validate before sending the market order so a bad
                        # TP split can never create an unprotected position.
                        if not self.v_hold_until_all_reverse.get():
                            if tp_qty_mode == "FIXED_QTY":
                                requested_tp1 = self.safe_amount(
                                    self.symbol,
                                    tp1_close_value,
                                )
                                requested_tp2 = self.safe_amount(
                                    self.symbol,
                                    tp2_close_value,
                                )
                                requested_entry_qty = self.safe_amount(
                                    self.symbol,
                                    entry_qty,
                                )
                                if abs(
                                    (requested_tp1 + requested_tp2)
                                    - requested_entry_qty
                                ) > 1e-12:
                                    raise ValueError(
                                        "FIXED_QTY TP split is invalid BEFORE entry. "
                                        f"Requested entry Qty={requested_entry_qty:g}, "
                                        f"but TP1={requested_tp1:g} + TP2={requested_tp2:g}. "
                                        "Use PERCENT_% with values such as 50 + 50 "
                                        "for a 50/50 split, or set FIXED_QTY values "
                                        "whose sum equals the entry quantity."
                                    )

                        try:
                            new_position, actual_entry = (
                                self.open_market_position(
                                    self.symbol,
                                    signal,
                                    entry_qty,
                                )
                            )

                            actual_qty = (
                                new_position["qty"]
                            )

                            self.log(
                                f"ACTUAL FILL: "
                                f"{desired_side} | "
                                f"Entry={actual_entry:.12g} | "
                                f"Qty={actual_qty}"
                            )

                            actual_position_margin = (
                                new_position.get(
                                    "initial_margin",
                                    0.0,
                                )
                            )

                            actual_position_leverage = (
                                new_position.get(
                                    "leverage",
                                    0.0,
                                )
                            )

                            if actual_position_margin > 0:
                                self.log(
                                    f"ACTUAL POSITION MARGIN: "
                                    f"{actual_position_margin:.12g}"
                                )

                            if actual_position_leverage > 0:
                                self.log(
                                    f"ACTUAL POSITION LEVERAGE: "
                                    f"{actual_position_leverage:.12g}x"
                                )

                            # ------------------------------------------------
                            # Calculate protection from ACTUAL entry.
                            # ------------------------------------------------
                            (
                                sl,
                                tp1,
                                tp2,
                                sl_move,
                                tp1_move,
                                tp2_move,
                            ) = (
                                self.calculate_protection_prices(
                                    self.symbol,
                                    desired_side,
                                    actual_entry,
                                    actual_qty,
                                    new_position.get("initial_margin", 0.0),
                                    effective_sl_target_pct,
                                    tp1_target_pct,
                                    tp2_target_pct,
                                    effective_sl_mode,
                                    tp_mode,
                                    leverage,
                                )
                            )

                            self.log(
                                f"SL MODE: {effective_sl_mode} | TP MODE: {tp_mode}"
                            )

                            if (
                                (sl_mode == "ROI_%" or tp_mode == "ROI_%")
                                and actual_position_margin > 0
                            ):
                                self.log(
                                    "ROI targets converted using "
                                    "ACTUAL POSITION MARGIN."
                                )
                            elif sl_mode == "ROI_%" or tp_mode == "ROI_%":
                                self.log(
                                    "ROI target conversion used configured leverage fallback."
                                )

                            if self.v_hold_until_all_reverse.get():
                                self.log(
                                    f"PROTECTION CALCULATED FROM ACTUAL ENTRY: SL={sl:.12g} | "
                                    f"Hold SL={hold_sl_roi_pct:g}% ROI | "
                                    "TP1/TP2 DISABLED (Hold-All-Reverse ON)"
                                )
                            else:
                                self.log(
                                    f"PROTECTION CALCULATED FROM ACTUAL ENTRY: "
                                    f"SL={sl:.12g} | "
                                    f"TP1={tp1:.12g} | "
                                    f"TP2={tp2:.12g}"
                                )

                            if self.v_hold_until_all_reverse.get():
                                self.log(
                                    f"PRICE MOVE EQUIVALENTS: SL={sl_move * 100:.6g}% | "
                                    "TP1/TP2 disabled"
                                )
                            else:
                                self.log(
                                    f"PRICE MOVE EQUIVALENTS: "
                                    f"SL={sl_move * 100:.6g}% | "
                                    f"TP1={tp1_move * 100:.6g}% | "
                                    f"TP2={tp2_move * 100:.6g}%"
                                )

                            # ------------------------------------------------
                            # Create protection.
                            # ------------------------------------------------
                            hold_wait_reversal = (
                                bool(self.v_hold_until_all_reverse.get())
                                and bool(self.v_hold_sl_wait_reversal.get())
                            )
                            self.hold_sl_wait_reversal = hold_wait_reversal
                            self.hold_sl_threshold_hit = False
                            self.hold_sl_threshold_logged = False

                            if hold_wait_reversal:
                                # Deliberately DO NOT place an exchange-side SL.
                                # The calculated `sl` is retained as the ROI
                                # threshold.  Once reached, the bot waits for
                                # ALL active directional modules to reverse.
                                created = []
                                verified = True
                                self.log(
                                    f"HOLD-SL WAIT MODE ACTIVE: threshold={sl:.12g} "
                                    f"({hold_sl_roi_pct:g}% ROI). NO exchange SL placed. "
                                    "The position will remain open until ALL active signals reverse."
                                )
                            else:
                                created = (
                                    self.create_protection_orders(
                                        self.symbol,
                                        desired_side,
                                        actual_qty,
                                        sl,
                                        tp1,
                                        tp2,
                                        tp_qty_mode,
                                        tp1_close_value,
                                        tp2_close_value,
                                    )
                                )

                                # ------------------------------------------------
                                # Verify protection.
                                # ------------------------------------------------
                                verified = (
                                    self.verify_protection_orders(
                                        self.symbol,
                                        created,
                                    )
                                )

                            if not verified:
                                raise RuntimeError(
                                    "One or more protection orders "
                                    "could not be verified."
                                )

                            # In Hold-SL WAIT mode, `created` is intentionally empty
                            # because there is NO exchange-side SL.  Keep the
                            # protection state valid without requiring an order ID.
                            sl_order = next(
                                (order for label, order in created if label == "SL"),
                                None,
                            )
                            tp1_order = next(
                                (order for label, order in created if label == "TP1"),
                                None,
                            )
                            tp2_order = next(
                                (order for label, order in created if label == "TP2"),
                                None,
                            )

                            self.last_protected_position = {
                                "side": desired_side,
                                "qty": actual_qty,
                                "entry": actual_entry,
                                "sl": sl,
                                "tp1": tp1,
                                "tp2": tp2,
                                "sl_id": sl_order.get("id") if sl_order else None,
                                "tp1_id": tp1_order.get("id") if tp1_order else None,
                                "tp2_id": tp2_order.get("id") if tp2_order else None,
                                "tp_orders_enabled": bool(tp1_order or tp2_order),
                                "hold_sl_wait_reversal": hold_wait_reversal,
                            }

                            self.tp1_be_done = False
                            # A fresh position is now active; any previous post-exit
                            # lock has already been cleared or satisfied.
                            self.reentry_direction_lock = None
                            self.reentry_lock_reason = ""
                            if hold_wait_reversal or self.v_hold_until_all_reverse.get():
                                self.log(
                                    "TP1 BREAK-EVEN: DISABLED BY HOLD-ALL-REVERSE | "
                                    "TP1/TP2 are disabled in this mode."
                                )
                            else:
                                self.log(
                                    "TP1 BREAK-EVEN: "
                                    + (
                                        "ON | TP1 fill will move the remaining SL to actual entry."
                                        if self.v_tp1_be.get()
                                        else "OFF"
                                    )
                                )
                            self.log(
                                "========================================"
                            )
                            self.log(
                                "POSITION MONITORED ✓"
                                if hold_wait_reversal
                                else "POSITION PROTECTED ✓"
                            )
                            self.log(
                                f"{desired_side} Entry = {actual_entry:.12g}"
                            )
                            self.log(
                                f"SL  = {sl:.12g}"
                            )
                            if self.v_hold_until_all_reverse.get():
                                if hold_wait_reversal:
                                    self.log(
                                        "TP1/TP2 = DISABLED | Hold-SL WAIT mode: no exchange SL; "
                                        "ROI threshold is monitored and ALL active signals must reverse to exit."
                                    )
                                else:
                                    self.log(
                                        "TP1/TP2 = DISABLED | Hold-All-Reverse uses strategy reversal as the exit."
                                    )
                            else:
                                self.log(
                                    f"TP1 = {tp1:.12g}"
                                )
                                self.log(
                                    f"TP2 = {tp2:.12g}"
                                )
                                self.log(
                                    f"TP CLOSE = {tp_qty_mode} | "
                                    f"TP1={tp1_close_value:g} | "
                                    f"TP2={tp2_close_value:g}"
                                )
                            self.log(
                                f"Qty = {actual_qty}"
                            )
                            self.log(
                                "========================================"
                            )

                            self.log_trade_csv(
                                time.strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                ),
                                self.exchange_id,
                                self.symbol,
                                "BUY"
                                if desired_side == "LONG"
                                else "SELL",
                                actual_entry,
                                actual_qty,
                                sl,
                                tp1,
                                tp2,
                                (
                                    "Entry + Hold-SL WAIT monitoring | "
                                    if hold_wait_reversal
                                    else "Entry + verified protection | "
                                )
                                + f"SL_MODE={sl_mode} | TP_MODE={tp_mode} | "
                                f"TP_QTY_MODE={tp_qty_mode} | "
                                f"TP1_CLOSE={tp1_close_value:g} | "
                                f"TP2_CLOSE={tp2_close_value:g}",
                            )

                            self.send_telegram(
                                (
                                    f"[{self.exchange_id.upper()}] "
                                    f"{desired_side} {self.symbol}\n"
                                    f"Actual Entry: {actual_entry}\n"
                                    f"Qty: {actual_qty}\n"
                                    f"SL Mode: {sl_mode} | TP Mode: {tp_mode}\n"
                                    f"SL: {sl}\n"
                                    f"TP1: {tp1}\n"
                                    f"TP2: {tp2}\n"
                                    f"TP Close: {tp_qty_mode} "
                                    f"TP1={tp1_close_value:g} "
                                    f"TP2={tp2_close_value:g}\n"
                                    f"Protection: {'WAIT-MONITORED (NO EXCHANGE SL)' if hold_wait_reversal else 'VERIFIED'}"
                                )
                            )

                            self.last_entry_candle_ts = int(df["time"].iloc[-2])
                            self._begin_performance_trade(
                                desired_side, actual_entry, actual_qty, curr_balance
                            )
                            self.log(
                                f"TRADE OPENED | Completed={self.total_trades} | "
                                f"Opened={self.opened_trades}"
                            )

                        except Exception as trade_error:
                            self.log(
                                f"TRADE/PROTECTION ERROR: "
                                f"{trade_error}"
                            )

                            # ------------------------------------------------
                            # SAFETY: If a position exists but protection
                            # failed, cancel orphan orders and close it.
                            # ------------------------------------------------
                            try:
                                recovery_pos = (
                                    self.fetch_position(
                                        self.symbol
                                    )
                                )

                                if recovery_pos:
                                    self.cancel_all_open_orders(
                                        self.symbol
                                    )

                                    self.close_position_market(
                                        self.symbol,
                                        recovery_pos["side"],
                                        recovery_pos["qty"],
                                    )

                                    self.log(
                                        "Unprotected position "
                                        "closed by safety recovery."
                                    )

                            except Exception as recovery_error:
                                self.log(
                                    "!!! CRITICAL RECOVERY ERROR !!! "
                                    f"{recovery_error}"
                                )

                    self.consecutive_cycle_errors = 0

                    # ------------------------------------------------
                    # 8. Update dashboard
                    # ------------------------------------------------
                    decided_trades = self.winning_trades + self.losing_trades
                    win_rate = (
                        self.winning_trades
                        / decided_trades
                        * 100
                        if decided_trades > 0
                        else 0.0
                    )

                    try:
                        self.root.after(
                            0,
                            lambda pnl=self.net_pnl,
                            start=self.start_balance,
                            curr=curr_balance,
                            trades=self.total_trades,
                            wins=self.winning_trades,
                            losses=self.losing_trades,
                            wr=win_rate: self.lbl_pnl.config(
                                text=(
                                    f"Start Balance: ${start:.4f} | "
                                    f"Current Balance: ${curr:.4f} | "
                                    f"Net PnL: ${pnl:.2f} | "
                                    f"Trades: {trades} | "
                                    f"Wins: {wins} | "
                                    f"Losses: {losses} | "
                                    f"Win Rate: {wr:.1f}%"
                                )
                            ),
                        )
                    except Exception:
                        pass

                    if (
                        self.session_max_trades > 0
                        and self.total_trades >= self.session_max_trades
                    ):
                        self.log(
                            f"TRADE LIMIT REACHED: {self.total_trades} completed trades. "
                            "Stopping execution safely."
                        )
                        # This branch runs in the worker thread. stop_bot()
                        # touches Tk widgets and must not be called here.
                        self.is_running = False
                        break

                except Exception as cycle_error:
                    self.consecutive_cycle_errors += 1
                    self.log(
                        f"Execution cycle error #{self.consecutive_cycle_errors}/{MAX_CONSECUTIVE_CYCLE_ERRORS}: "
                        f"{cycle_error}"
                    )
                    if self.consecutive_cycle_errors >= MAX_CONSECUTIVE_CYCLE_ERRORS:
                        self.runtime_last_error = f"Consecutive cycle safety halt: {cycle_error}"
                        self.log("CRITICAL: consecutive cycle error limit reached; bot halted fail-closed.")
                        self.is_running = False
                        break

                # ------------------------------------------------
                # 9. Persistent checkpoint + 30-second scan
                # ------------------------------------------------
                # The checkpoint is written after every completed execution
                # cycle.  If Windows kills the process or an exchange call
                # stalls, the next launch can recover the most recent stage
                # rather than starting from an empty in-memory state.
                if self.is_running:
                    try:
                        # Save the current GUI configuration from Tk's main
                        # thread, then checkpoint the in-memory runtime state.
                        self.root.after(0, self._checkpoint_gui_config)
                    except Exception:
                        self._persist_runtime_state(status="RUNNING")

                elapsed = (
                    time.time()
                    - cycle_start
                )

                remaining = max(
                    0,
                    30 - elapsed,
                )

                end_time = (
                    time.time()
                    + remaining
                )

                while (
                    self.is_running
                    and time.time() < end_time
                ):
                    time.sleep(1)

        except Exception as fatal_error:
            self.runtime_last_error = str(fatal_error)
            self.log(
                f"BOT FATAL ERROR: {fatal_error}"
            )

        finally:
            self.is_running = False

            try:
                live_position = self.fetch_position(self.symbol) if self.exchange and self.symbol else None
                final_status = (
                    "CRASHED"
                    if self.runtime_last_error
                    else ("PAUSED_WITH_POSITION" if live_position else "STOPPED")
                )
                self._persist_runtime_state(
                    status=final_status,
                    last_error=self.runtime_last_error or None,
                )
                try:
                    end_balance = self.fetch_balance_total() if self.exchange else None
                except Exception:
                    end_balance = None
                self._db_session_end(
                    final_status,
                    end_balance=end_balance,
                    notes=self.runtime_last_error or "Bot execution thread halted.",
                )
            except Exception as state_error:
                self.log(f"FINAL RUNTIME STATE WARNING: {state_error}")

            try:
                self.root.after(
                    0,
                    lambda: self._set_bot_button_states(running=False),
                )
            except Exception:
                pass

            self.log(
                "Bot execution thread halted."
            )
            self._release_profile_lock()


# -------------------- MAIN ----------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = UniversalFuturesBotGUI(root)
    root.mainloop()