"""
V8.3.0 UNIVERSAL FUTURES BACKTESTER — HARDENED ADAPTIVE STRATEGY-PARITY EDITION
===============================================================

Historical simulator for Universal Futures Trading Bot V8.3.0.

Design goal:
    Backtest the SAME completed-candle indicator calculations, directional
    modules, signal modes, normal risk/SL/TP logic, Hold-All-Reverse logic,
    post-SL opposite-signal lock, and Grid modes used by the live V8.3.0 bot.

Included:
    * 19 V8 directional modules
    * Every live indicator option and entry mode
    * SINGLE_SIGNAL / ANY_NON_CONFLICTING / SCORE / 2/3/4_SIGNALS /
      ADAPTIVE_SCORE / STRICT_ALL_FILTERS
    * 4H MTF EMA200 filter
    * Normal strategy sizing, cooldown, same-candle protection, max trades,
      daily drawdown and emergency capital-loss stop
    * PRICE_% and ROI_% SL/TP
    * TP1/TP2 split, TP1 break-even
    * Hold-All-Reverse and optional WAIT-FOR-ALL-REVERSE stop threshold
    * Post-SL opposite-signal re-entry lock
    * DIRECT_SHOT / LONG_GRID / SHORT_GRID / NEUTRAL_GRID
    * Grid spacing, levels, size increase, basket TP, global SL, exposure,
      Grid DD, trend filters, score minimum, recenter and cooldown
    * Conservative OHLC ambiguity rule: when SL and TP are both touched in
      one candle, SL is assumed to trigger first.
    * CSV + XLSX export (when openpyxl is installed)
    * Parameter sweep and walk-forward
    * Multi-symbol sequential runs
    * Cached public OHLCV download from Binance/Bybit

Important:
    This is a historical model. Exchange fills, fees, funding, liquidation,
    latency, precision and trigger semantics can differ from live execution.
    No future candle is used to create a signal. Signals are evaluated from
    completed candles and normal entries are simulated at the next candle open.
"""
import itertools
import math
import os
import threading
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MPL = True
except Exception:
    HAS_MPL = False

APP_VERSION = "V8.3.0-BT-PARITY"
APP_TITLE = "Universal Futures Bot V8.3.0 — Strategy-Parity Backtester"
APP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = APP_DIR / "backtest_results"
RESULTS_DIR.mkdir(exist_ok=True)
TIMEFRAMES = {"3m":3*60*1000, "5m":5*60*1000, "15m":15*60*1000, "1h":60*60*1000, "4h":4*60*60*1000}
SUPPORTED_EXCHANGES = ("Binance","Bybit")
SUPPORTED_SIGNAL_MODES = ("SINGLE_SIGNAL","ANY_NON_CONFLICTING","SCORE","2_SIGNALS","3_SIGNALS","4_SIGNALS","ADAPTIVE_SCORE","STRICT_ALL_FILTERS")
SUPPORTED_GRID_MODES = ("OFF","DIRECT_SHOT","LONG_GRID","SHORT_GRID","NEUTRAL_GRID")
ADAPTIVE_MODULE_WEIGHTS={"ST":1.50,"EMA":1.00,"EMA_CROSS":1.25,"MACD":1.25,"RSI":1.00,"BB":0.75,"STOCH":0.75,"VWAP":1.25,"VWAP_DELTA":1.00,"VIDYA":1.25,"NWE":1.00,"LIQ_SWING":1.50,"TRENDLINE":1.50,"MTF":2.00,"DIVERGENCE":1.75,"VOL_SR":1.50,"VOL":0.50,"ADX":1.25,"ATR":0.50}
ADAPTIVE_DEFAULT_EDGE=0.18
ADAPTIVE_DEFAULT_MIN_WEIGHT=3.50
MODULES = ["ST","EMA","EMA_CROSS","MACD","RSI","BB","STOCH","VWAP","VWAP_DELTA","VIDYA","NWE","LIQ_SWING","TRENDLINE","MTF","VOL","ADX","ATR","DIVERGENCE","VOL_SR"]

DEFAULTS = {'exchange': 'Binance', 'symbols': 'BTC/USDT', 'tf': '15m', 'start': '2026-01-01', 'end': '2026-09-01', 'capital': 1000.0, 'leverage': 5, 'no_same_candle': True, 'cooldown_min': 0.0, 'max_trades': 10, 'use_st': True, 'st_len': 10, 'st_mult': 2.0, 'st_source': 'CLOSE', 'st_change_atr': True, 'st_entry_mode': 'FRESH_FLIP', 'use_ema': True, 'ema_len': 200, 'use_ema_cross': False, 'ema_fast': 9, 'ema_slow': 20, 'ema_cross_entry_mode': 'FRESH_CROSS', 'use_macd': False, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'use_rsi': False, 'rsi_len': 14, 'rsi_ob': 80, 'rsi_os': 20, 'rsi_logic': 'REVERSAL_ZONE', 'rsi_ma_type': 'EMA', 'rsi_ma_len': 9, 'use_bb': False, 'bb_len': 20, 'bb_std': 2.0, 'use_stoch': False, 'stoch_k': 14, 'stoch_smooth': 3, 'stoch_d': 3, 'use_vwap': False, 'vwap_len': 50, 'use_vwap_delta': False, 'vwap_delta_smooth': False, 'vwap_delta_smooth_len': 21, 'vwap_delta_baseline': 50, 'vwap_delta_logic': 'CURRENT_TREND', 'use_vidya': False, 'vidya_len': 10, 'vidya_momentum': 20, 'vidya_band': 2.0, 'vidya_entry_mode': 'CURRENT_TREND', 'use_nwe': False, 'nwe_bandwidth': 8.0, 'nwe_mult': 3.0, 'nwe_entry_mode': 'FRESH_CROSS', 'nwe_lookback': 500, 'nwe_mae': 499, 'use_liq_swings': False, 'liq_length': 14, 'liq_area': 'Wick Extremity', 'liq_filter': 'Count', 'liq_filter_value': 0.0, 'liq_entry_mode': 'FRESH_BREAK', 'use_trendline': False, 'trendline_length': 14, 'trendline_min_distance': 5, 'trendline_entry_mode': 'FRESH_BREAK', 'trendline_buffer': 0.0, 'trendline_retest_candles': 3, 'use_atr': False, 'atr_min_pct': 0.3, 'use_vol': True, 'vol_len': 20, 'use_adx': True, 'adx_thresh': 20.0, 'use_mtf': True, 'signal_mode': 'ADAPTIVE_SCORE', 'min_score': 1, 'adaptive_edge': 0.18, 'adaptive_min_weight': 3.5, 'hold_until_all_reverse': True, 'require_opposite_after_sl': True, 'size_mode': 'EQUITY_RISK_%', 'risk_pct': 1.0, 'fixed_qty': 0.001, 'max_dd': 5.0, 'emergency_capital_pct': 30.0, 'sl_mode': 'PRICE_%', 'tp_mode': 'ROI_%', 'sl_pct': 1.5, 'tp1_pct': 2.0, 'tp2_pct': 4.0, 'hold_sl_roi': 5.0, 'hold_sl_wait_reversal': False, 'tp1_be': True, 'tp_qty_mode': 'PERCENT_%', 'tp1_close': 50.0, 'tp2_close': 50.0, 'grid_mode': 'OFF', 'grid_levels': 5, 'grid_spacing': 1.0, 'grid_order_size': 10.0, 'grid_size_increase': 0.0, 'grid_tp': 1.0, 'grid_sl': 6.0, 'grid_max_exposure': 100.0, 'grid_max_dd': 3.0, 'grid_score_min': 1, 'grid_trend_filter': 'OFF', 'grid_recenter': False, 'grid_recenter_distance': 3.0, 'grid_cooldown': 30.0, 'fee_pct': 0.04, 'slippage_pct': 0.01, 'slippage_exit': True, 'warmup': 250, 'exit_on_opposite': False, 'output_trades': True}
DEFAULTS.update({
    'max_configs':250,'wf_split':70,'top_n':1,'combo_one':True,'combo_two':True,'combo_three':True,'combo_four':True,
    'use_divergence':False,'div_pivot':5,'div_source':'Close','div_type':'Regular','div_min_count':1,
    'div_max_pivots':10,'div_max_bars':100,'div_cci_len':10,'div_mom_len':10,'div_vwmacd_fast':12,
    'div_vwmacd_slow':26,'div_cmf_len':21,'div_mfi_len':14,
    'div_entry_mode':'FRESH','div_use_macd':True,'div_use_macd_hist':True,'div_use_rsi':True,'div_use_stoch':True,'div_use_cci':True,
    'div_use_momentum':True,'div_use_obv':True,'div_use_vwmacd':True,'div_use_cmf':True,'div_use_mfi':True,
    'use_vol_sr':False,'sr_tf1':'Chart','sr_tf2':'4h','sr_tf3':'D','sr_tf4':'W',
    'sr_tf1_enabled':True,'sr_tf2_enabled':True,'sr_tf3_enabled':True,'sr_tf4_enabled':True,
    'sr_volume_ma':6,'sr_vote_mode':'MAJORITY','sr_entry_mode':'CURRENT_ZONE','sr_history_bars':40
})



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
    for i in range(5, len(x)):
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

def calculate_rma(series, length):
    """TradingView-style Wilder RMA with SMA seed."""
    length = int(length)
    if length <= 0:
        raise ValueError("RMA length must be greater than 0.")

    x = pd.Series(series, dtype="float64")
    out = pd.Series(np.nan, index=x.index, dtype="float64")

    valid_positions = np.flatnonzero(np.isfinite(x.to_numpy(dtype=float)))
    if len(valid_positions) < length:
        return out

    # TradingView RMA seeds from the SMA of the first `length` valid values.
    seed_positions = valid_positions[:length]
    seed = float(x.iloc[seed_positions].mean())
    seed_pos = int(seed_positions[-1])
    out.iloc[seed_pos] = seed

    alpha = 1.0 / length
    prev = seed
    for pos in valid_positions[length:]:
        value = float(x.iloc[pos])
        prev = alpha * value + (1.0 - alpha) * prev
        out.iloc[pos] = prev

    return out

def calculate_supertrend(
    df,
    length=10,
    multiplier=3.0,
    source="CLOSE",
    change_atr=True,
):
    """TradingView/Kivanc-style Supertrend.

    Matches the TradingView Supertrend inputs:
      - ATR Period
      - Source (Close or HL2)
      - ATR Multiplier
      - Change ATR Calculation Method
        ON  -> Wilder/RMA ATR (TradingView ta.atr)
        OFF -> SMA(True Range, Period)
    """
    df = df.copy()
    length = int(length)
    multiplier = float(multiplier)
    source = str(source).strip().upper()
    change_atr = bool(change_atr)

    if length <= 0:
        raise ValueError("Supertrend ATR Period must be greater than 0.")
    if multiplier <= 0:
        raise ValueError("Supertrend ATR Multiplier must be greater than 0.")
    if source not in ("CLOSE", "HL2"):
        raise ValueError("Supertrend Source must be CLOSE or HL2.")

    df["tr0"] = (df["high"] - df["low"]).abs()
    df["tr1"] = (df["high"] - df["close"].shift(1)).abs()
    df["tr2"] = (df["low"] - df["close"].shift(1)).abs()
    df["tr"] = df[["tr0", "tr1", "tr2"]].max(axis=1)

    # TradingView/Kivanc Supertrend:
    # changeATR=True  -> ta.atr(length), i.e. Wilder/RMA ATR
    # changeATR=False -> sma(tr, length)
    if change_atr:
        # TradingView ta.atr() = Wilder RMA of true range.
        df["atr"] = calculate_rma(df["tr"], length)
    else:
        df["atr"] = df["tr"].rolling(length).mean()

    if source == "CLOSE":
        src = df["close"]
    else:
        src = (df["high"] + df["low"]) / 2.0

    # Pine:
    # up = src - Multiplier * atr
    # dn = src + Multiplier * atr
    df["basic_lb"] = src - multiplier * df["atr"]
    df["basic_ub"] = src + multiplier * df["atr"]

    final_ub = [np.nan] * len(df)
    final_lb = [np.nan] * len(df)
    trend = [True] * len(df)
    supertrend = [np.nan] * len(df)

    for i in range(len(df)):
        # Pine has na values until ATR becomes available. Keep those bars
        # neutral rather than manufacturing an early Supertrend state.
        if not np.isfinite(df["atr"].iloc[i]):
            continue

        basic_ub = float(df["basic_ub"].iloc[i])
        basic_lb = float(df["basic_lb"].iloc[i])

        if i == 0 or not np.isfinite(final_ub[i - 1]):
            up1 = basic_lb
            dn1 = basic_ub
        else:
            up1 = final_lb[i - 1]
            dn1 = final_ub[i - 1]

        if i == 0 or not np.isfinite(final_lb[i - 1]):
            final_lb[i] = basic_lb
            final_ub[i] = basic_ub
            trend[i] = True
            supertrend[i] = final_lb[i]
            continue

        # Exact Kivanc/Pine recurrence:
        # up := close[1] > up1 ? max(up, up1) : up
        # dn := close[1] < dn1 ? min(dn, dn1) : dn
        final_lb[i] = (
            max(basic_lb, up1)
            if float(df["close"].iloc[i - 1]) > up1
            else basic_lb
        )
        final_ub[i] = (
            min(basic_ub, dn1)
            if float(df["close"].iloc[i - 1]) < dn1
            else basic_ub
        )

        prev_trend = trend[i - 1]
        if prev_trend is False and float(df["close"].iloc[i]) > dn1:
            trend[i] = True
        elif prev_trend is True and float(df["close"].iloc[i]) < up1:
            trend[i] = False
        else:
            trend[i] = prev_trend

        supertrend[i] = final_lb[i] if trend[i] else final_ub[i]

    df["supertrend"] = supertrend
    df["trend"] = trend
    return df

def calculate_adx(df, length=14):
    df = df.copy()

    df["up_move"] = df["high"] - df["high"].shift(1)
    df["down_move"] = df["low"].shift(1) - df["low"]

    df["plus_dm"] = df.apply(
        lambda r: (
            r["up_move"]
            if r["up_move"] > r["down_move"] and r["up_move"] > 0
            else 0
        ),
        axis=1,
    )

    df["minus_dm"] = df.apply(
        lambda r: (
            r["down_move"]
            if r["down_move"] > r["up_move"] and r["down_move"] > 0
            else 0
        ),
        axis=1,
    )

    tr_max = df[["tr0", "tr1", "tr2"]].max(axis=1)
    df["atr_adx"] = calculate_rma(tr_max, length)
    plus_rma = calculate_rma(df["plus_dm"], length)
    minus_rma = calculate_rma(df["minus_dm"], length)

    df["plus_di"] = 100 * (plus_rma / df["atr_adx"])
    df["minus_di"] = 100 * (minus_rma / df["atr_adx"])

    denominator = (df["plus_di"] + df["minus_di"]).replace(0, float("nan"))
    df["dx"] = 100 * abs(df["plus_di"] - df["minus_di"]) / denominator
    df["adx"] = calculate_rma(df["dx"], length)

    return df

def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calculate MACD line, signal line and histogram."""
    df = df.copy()

    fast = int(fast)
    slow = int(slow)
    signal = int(signal)

    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError("MACD periods must be greater than 0.")
    if fast >= slow:
        raise ValueError("MACD Fast period must be smaller than Slow period.")

    ema_fast = df["close"].ewm(
        span=fast,
        adjust=False,
    ).mean()

    ema_slow = df["close"].ewm(
        span=slow,
        adjust=False,
    ).mean()

    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(
        span=signal,
        adjust=False,
    ).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    return df

def calculate_rsi(df, length=14):
    """Wilder-style RSI using exponentially smoothed gains/losses."""
    df = df.copy()

    length = int(length)
    if length <= 0:
        raise ValueError("RSI period must be greater than 0.")

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = calculate_rma(gain, length)
    avg_loss = calculate_rma(loss, length)

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    df["rsi"] = 100 - (100 / (1 + rs))

    # Handle the zero-loss case as RSI 100 rather than NaN.
    df.loc[
        (avg_loss == 0) & (avg_gain > 0),
        "rsi",
    ] = 100.0

    # Flat markets have neutral RSI.
    df.loc[
        (avg_gain == 0) & (avg_loss == 0),
        "rsi",
    ] = 50.0

    return df

def calculate_wma(series, length):
    """Linear weighted moving average."""
    length = int(length)
    if length <= 0:
        raise ValueError("WMA period must be greater than 0.")
    weights = list(range(1, length + 1))
    weight_sum = float(sum(weights))

    def _wma(values):
        if len(values) < length:
            return float("nan")
        return float(sum(v * w for v, w in zip(values, weights)) / weight_sum)

    return series.rolling(length).apply(_wma, raw=True)

def calculate_rsi_ma(df, rsi_ma_type="EMA", length=9):
    """Calculate selectable SMA/EMA/WMA on RSI."""
    df = df.copy()
    length = int(length)
    ma_type = str(rsi_ma_type).strip().upper()
    if length <= 0:
        raise ValueError("RSI MA period must be greater than 0.")
    if ma_type == "SMA":
        df["rsi_ma"] = df["rsi"].rolling(length).mean()
    elif ma_type == "EMA":
        df["rsi_ma"] = df["rsi"].ewm(span=length, adjust=False).mean()
    elif ma_type == "WMA":
        df["rsi_ma"] = calculate_wma(df["rsi"], length)
    else:
        raise ValueError("RSI MA type must be SMA, EMA, or WMA.")
    return df

def calculate_hma(series, length):
    length = int(length)
    if length <= 0:
        raise ValueError("HMA length must be greater than 0.")
    half = max(1, length // 2)
    sqrt_len = max(1, int(length ** 0.5))
    return calculate_wma(
        2.0 * calculate_wma(series, half) - calculate_wma(series, length),
        sqrt_len,
    )

def calculate_vwap_delta(df, smoothing=False, smoothing_length=21, baseline_length=50):
    df = df.copy()
    smoothing_length = int(smoothing_length)
    baseline_length = int(baseline_length)
    if smoothing_length <= 0 or baseline_length <= 0:
        raise ValueError("VWAP Delta lengths must be greater than 0.")

    # Session VWAP, reset daily for crypto UTC data.
    session = pd.to_datetime(df["time"], unit="ms", utc=True).dt.floor("D")
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["vol"]
    vwap = pv.groupby(session).cumsum() / df["vol"].groupby(session).cumsum().replace(0, float("nan"))

    raw_o = df["open"] - vwap
    raw_h = df["high"] - vwap
    raw_l = df["low"] - vwap
    raw_c = df["close"] - vwap

    if smoothing:
        d_o = calculate_hma(raw_o, smoothing_length)
        d_h = calculate_hma(raw_h, smoothing_length)
        d_l = calculate_hma(raw_l, smoothing_length)
        d_c = calculate_hma(raw_c, smoothing_length)
    else:
        d_o, d_h, d_l, d_c = raw_o, raw_h, raw_l, raw_c

    df["vwap_delta"] = d_c
    df["vwap_delta_open"] = d_o
    df["vwap_delta_high"] = pd.concat([d_h, d_o, d_c], axis=1).max(axis=1)
    df["vwap_delta_low"] = pd.concat([d_l, d_o, d_c], axis=1).min(axis=1)
    df["vwap_delta_baseline"] = d_c.ewm(span=baseline_length, adjust=False).mean()
    df["vwap_delta_session_vwap"] = vwap
    return df

def calculate_vidya(df, vidya_length=10, vidya_momentum=20, band_distance=2.0,
                    atr_length=200, smoothing_length=15):
    df = df.copy()
    vidya_length = int(vidya_length)
    vidya_momentum = int(vidya_momentum)
    band_distance = float(band_distance)
    if vidya_length <= 0 or vidya_momentum <= 0 or band_distance <= 0:
        raise ValueError("VIDYA Length, Momentum and Band must be greater than 0.")

    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = calculate_rma(tr, int(atr_length))

    momentum = df["close"].diff()
    pos = momentum.clip(lower=0.0)
    neg = (-momentum).clip(lower=0.0)
    sp = pos.rolling(vidya_momentum).sum()
    sn = neg.rolling(vidya_momentum).sum()
    denom = sp + sn
    cmo = (100.0 * (sp - sn).abs() / denom.replace(0, float("nan"))).fillna(0.0)
    alpha = 2.0 / (vidya_length + 1.0)

    raw = []
    previous = None
    for price, c in zip(df["close"].to_numpy(), cmo.to_numpy()):
        price = float(price)
        if previous is None or not np.isfinite(previous):
            previous = price
        k = alpha * float(c) / 100.0
        value = k * price + (1.0 - k) * previous
        raw.append(value)
        previous = value

    vidya = pd.Series(raw, index=df.index, dtype="float64").rolling(int(smoothing_length)).mean()
    upper = vidya + atr * band_distance
    lower = vidya - atr * band_distance

    trend = False
    states = []
    for i in range(len(df)):
        if i > 0:
            if (pd.notna(upper.iloc[i]) and pd.notna(upper.iloc[i-1])
                    and df["close"].iloc[i-1] <= upper.iloc[i-1]
                    and df["close"].iloc[i] > upper.iloc[i]):
                trend = True
            elif (pd.notna(lower.iloc[i]) and pd.notna(lower.iloc[i-1])
                    and df["close"].iloc[i-1] >= lower.iloc[i-1]
                    and df["close"].iloc[i] < lower.iloc[i]):
                trend = False
        states.append(trend)

    trend_s = pd.Series(states, index=df.index, dtype=bool)
    previous_trend = trend_s.shift(1, fill_value=False)
    changed = trend_s.ne(previous_trend)
    smoothed = lower.where(trend_s, upper).mask(changed)
    cross_up = (~previous_trend) & trend_s
    cross_down = previous_trend & (~trend_s)

    up, down = [], []
    uv = dv = 0.0
    for i in range(len(df)):
        if bool(cross_up.iloc[i] or cross_down.iloc[i]):
            uv = dv = 0.0
        else:
            if df["close"].iloc[i] > df["open"].iloc[i]:
                uv += float(df["vol"].iloc[i])
            elif df["close"].iloc[i] < df["open"].iloc[i]:
                dv += float(df["vol"].iloc[i])
        up.append(uv)
        down.append(dv)

    up_s = pd.Series(up, index=df.index)
    down_s = pd.Series(down, index=df.index)
    avg = (up_s + down_s) / 2.0
    delta_pct = ((up_s - down_s) / avg.replace(0, float("nan")) * 100.0).fillna(0.0)

    df["vidya"] = vidya
    df["vidya_atr"] = atr
    df["vidya_upper"] = upper
    df["vidya_lower"] = lower
    df["vidya_smoothed"] = smoothed
    df["vidya_trend_up"] = trend_s
    df["vidya_cross_up"] = cross_up
    df["vidya_cross_down"] = cross_down
    df["vidya_up_volume"] = up_s
    df["vidya_down_volume"] = down_s
    df["vidya_delta_volume_pct"] = delta_pct
    return df

def calculate_nadaraya_watson_envelope(df, bandwidth=8.0, multiplier=3.0, lookback=500, mae_length=499):
    """LuxAlgo Nadaraya-Watson Envelope, causal/end-point bot translation.

    Source supplied by the user: Nadaraya-Watson Envelope [LuxAlgo],
    CC BY-NC-SA 4.0. Visual drawing/repainting objects are omitted.
    Trading calculations use completed candles and past data only.
    """
    df = df.copy()
    bandwidth = float(bandwidth)
    multiplier = float(multiplier)    lookback = int(lookback)
    mae_length = int(mae_length)
    if bandwidth <= 0:
        raise ValueError("NWE Bandwidth must be greater than 0.")
    if multiplier < 0:
        raise ValueError("NWE Multiplier cannot be negative.")
    if lookback <= 0 or mae_length <= 0:
        raise ValueError("NWE Lookback and MAE length must be greater than 0.")
    src = pd.to_numeric(df["close"], errors="coerce").astype(float)
    values = src.to_numpy(dtype=float)
    lags = np.arange(lookback, dtype=float)
    weights = np.exp(-(lags ** 2) / (bandwidth * bandwidth * 2.0))
    nwe_values = np.full(len(values), np.nan, dtype=float)
    for i in range(len(values)):
        length = min(lookback, i + 1)
        window = values[i - length + 1:i + 1][::-1]
        valid = np.isfinite(window)
        if not valid.any():
            continue
        w = np.where(valid, weights[:length], 0.0)
        den = float(w.sum())
        if den > 0:
            nwe_values[i] = float(np.nansum(window * w) / den)
    out = pd.Series(nwe_values, index=df.index, dtype="float64")
    mae = (src - out).abs().rolling(mae_length).mean() * multiplier
    df["nwe_out"] = out
    df["nwe_mae"] = mae
    df["nwe_upper"] = out + mae
    df["nwe_lower"] = out - mae
    df["nwe_crossunder_lower"] = (
        (src < df["nwe_lower"]) &
        (src.shift(1) >= df["nwe_lower"].shift(1))
    )
    df["nwe_crossover_upper"] = (
        (src > df["nwe_upper"]) &
        (src.shift(1) <= df["nwe_upper"].shift(1))
    )
    df["nwe_trend_up"] = out > out.shift(1)
    df["nwe_trend_down"] = out < out.shift(1)
    return df

def calculate_liquidity_swings(
    df,
    length=14,
    area="Wick Extremity",
    filter_options="Count",
    filter_value=0.0,
):
    """LuxAlgo Liquidity Swings [LuxAlgo] calculation for the trading bot.

    Source supplied by the user: Liquidity Swings [LuxAlgo], © LuxAlgo,
    CC BY-NC-SA 4.0. Visual lines/boxes/labels and lower-timeframe
    intrabar-precision drawing are omitted. The trading signal is based on
    confirmed swing-high/swing-low liquidity levels and their price breaks.

    A swing high/low is only known after `length` bars have closed to its
    right, matching ta.pivothigh(length, length) / ta.pivotlow(length, length).
    Break signals are evaluated only on completed candles.
    """
    df = df.copy()
    length = int(length)
    area = str(area).strip()
    filter_options = str(filter_options).strip().title()
    filter_value = float(filter_value)

    if length <= 0:
        raise ValueError("Liquidity Swing Pivot Lookback must be greater than 0.")
    if area not in ("Wick Extremity", "Full Range"):
        raise ValueError("Liquidity Swing Swing Area must be Wick Extremity or Full Range.")
    if filter_options not in ("Count", "Volume"):
        raise ValueError("Liquidity Swing Filter must be Count or Volume.")
    if filter_value < 0:
        raise ValueError("Liquidity Swing Filter Value cannot be negative.")

    n = len(df)
    highs = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    lows = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    opens = pd.to_numeric(df["open"], errors="coerce").to_numpy(dtype=float)
    closes = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    vols = pd.to_numeric(df["vol"], errors="coerce").to_numpy(dtype=float)

    swing_high_event = np.zeros(n, dtype=bool)
    swing_low_event = np.zeros(n, dtype=bool)
    swing_high_level = np.full(n, np.nan, dtype=float)
    swing_low_level = np.full(n, np.nan, dtype=float)
    swing_high_area_bottom = np.full(n, np.nan, dtype=float)
    swing_low_area_top = np.full(n, np.nan, dtype=float)
    swing_high_count = np.zeros(n, dtype=float)
    swing_low_count = np.zeros(n, dtype=float)
    swing_high_volume = np.zeros(n, dtype=float)
    swing_low_volume = np.zeros(n, dtype=float)
    swing_high_break = np.zeros(n, dtype=bool)
    swing_low_break = np.zeros(n, dtype=bool)

    active_high = np.nan
    active_high_bottom = np.nan
    active_high_count = 0.0
    active_high_volume = 0.0
    active_low = np.nan
    active_low_top = np.nan
    active_low_count = 0.0
    active_low_volume = 0.0

    for i in range(n):
        # IMPORTANT: detect breaks against the level that was already known
        # before this candle. A newly confirmed pivot is not allowed to break
        # on the same candle it becomes known.
        prev_high = active_high
        prev_low = active_low
        prev_high_count = active_high_count
        prev_high_volume = active_high_volume
        prev_low_count = active_low_count
        prev_low_volume = active_low_volume

        if i >= 2 * length:
            p = i - length
            high_window = highs[p - length:p + length + 1]
            low_window = lows[p - length:p + length + 1]
            if (
                np.isfinite(highs[p])
                and np.isfinite(high_window).all()
                and highs[p] >= np.max(high_window)
            ):
                swing_high_event[i] = True
                active_high = highs[p]
                active_high_bottom = (
                    max(closes[p], opens[p])
                    if area == "Wick Extremity"
                    else lows[p]
                )
                active_high_count = 0.0
                active_high_volume = 0.0

            if (
                np.isfinite(lows[p])
                and np.isfinite(low_window).all()
                and lows[p] <= np.min(low_window)
            ):
                swing_low_event[i] = True
                active_low = lows[p]
                active_low_top = (
                    min(closes[p], opens[p])
                    if area == "Wick Extremity"
                    else highs[p]
                )
                active_low_count = 0.0
                active_low_volume = 0.0

        # Count/volume filtering follows the supplied LuxAlgo concept:
        # measure candles whose range overlaps the swing area.
        if not swing_high_event[i] and np.isfinite(prev_high) and np.isfinite(active_high_bottom):
            if i >= length:
                j = i - length
                overlaps = lows[j] < prev_high and highs[j] > active_high_bottom
                if overlaps:
                    active_high_count += 1.0
                    active_high_volume += vols[j] if np.isfinite(vols[j]) else 0.0

        if not swing_low_event[i] and np.isfinite(prev_low) and np.isfinite(active_low_top):
            if i >= length:
                j = i - length
                overlaps = lows[j] < active_low_top and highs[j] > prev_low
                if overlaps:
                    active_low_count += 1.0
                    active_low_volume += vols[j] if np.isfinite(vols[j]) else 0.0

        # A liquidity break is a close crossing the latest confirmed swing
        # level. Filter value must also be passed, matching the indicator's
        # Count/Volume filtering purpose.
        high_target = prev_high_count if filter_options == "Count" else prev_high_volume
        low_target = prev_low_count if filter_options == "Count" else prev_low_volume

        if np.isfinite(prev_high) and np.isfinite(closes[i]) and i > 0:
            swing_high_break[i] = (
                closes[i] > prev_high
                and closes[i - 1] <= prev_high
                and high_target > filter_value
            )

        if np.isfinite(prev_low) and np.isfinite(closes[i]) and i > 0:
            swing_low_break[i] = (
                closes[i] < prev_low
                and closes[i - 1] >= prev_low
                and low_target > filter_value
            )

        # Store the current active levels/statistics after this candle.
        swing_high_level[i] = active_high
        swing_high_area_bottom[i] = active_high_bottom
        swing_high_count[i] = active_high_count
        swing_high_volume[i] = active_high_volume
        swing_low_level[i] = active_low
        swing_low_area_top[i] = active_low_top
        swing_low_count[i] = active_low_count
        swing_low_volume[i] = active_low_volume

    # Current-trend interpretation: after a confirmed breakout, keep the
    # directional state until the opposite liquidity level breaks.
    liq_trend = 0
    liq_trend_state = np.zeros(n, dtype=int)
    for i in range(n):
        if swing_high_break[i]:
            liq_trend = 1
        elif swing_low_break[i]:
            liq_trend = -1
        liq_trend_state[i] = liq_trend

    df["liq_swing_high"] = swing_high_level
    df["liq_swing_low"] = swing_low_level
    df["liq_swing_high_area_bottom"] = swing_high_area_bottom
    df["liq_swing_low_area_top"] = swing_low_area_top
    df["liq_swing_high_count"] = swing_high_count
    df["liq_swing_low_count"] = swing_low_count
    df["liq_swing_high_volume"] = swing_high_volume
    df["liq_swing_low_volume"] = swing_low_volume
    df["liq_swing_high_break"] = swing_high_break
    df["liq_swing_low_break"] = swing_low_break
    df["liq_swing_trend"] = liq_trend_state
    return df

def calculate_trendline_breakout(
    df,
    length=14,
    min_pivot_distance=5,
    breakout_buffer_pct=0.0,
    retest_candles=3,
):
    """Confirmed-pivot trendline breakout calculation.

    Trendlines are built only from confirmed swing highs/lows. A pivot at p is
    known only after `length` candles have closed to its right, so the current
    candle never uses future information. Breakouts are evaluated on completed
    candles by the caller (normally iloc[-2]).

    Resistance uses the two latest confirmed swing highs; support uses the two
    latest confirmed swing lows.  The latest two highs must slope downward for
    resistance and the latest two lows must slope upward for support.

    `FRESH_BREAK` is a one-candle crossing event. `CURRENT_TREND` is derived by
    keeping the last breakout direction. `BREAK_RETEST` is represented by the
    same fresh breakout event plus retest state, so the caller can require a
    later candle to retest the broken line and close back in the breakout
    direction.
    """
    df = df.copy()
    length = int(length)
    min_pivot_distance = int(min_pivot_distance)
    breakout_buffer_pct = float(breakout_buffer_pct)
    retest_candles = int(retest_candles)
    if length <= 0:
        raise ValueError("Trendline Pivot Lookback must be greater than 0.")
    if min_pivot_distance <= 0:
        raise ValueError("Trendline Minimum Pivot Distance must be greater than 0.")
    if breakout_buffer_pct < 0:
        raise ValueError("Trendline Breakout Buffer cannot be negative.")
    if retest_candles <= 0:
        raise ValueError("Trendline Retest Candles must be greater than 0.")

    n = len(df)
    highs = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    lows = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    closes = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)

    resistance = np.full(n, np.nan, dtype=float)
    support = np.full(n, np.nan, dtype=float)
    resistance_prev = np.full(n, np.nan, dtype=float)
    support_prev = np.full(n, np.nan, dtype=float)
    pivot_high_event = np.zeros(n, dtype=bool)
    pivot_low_event = np.zeros(n, dtype=bool)
    break_up = np.zeros(n, dtype=bool)
    break_down = np.zeros(n, dtype=bool)
    trend_state = np.zeros(n, dtype=int)
    retest_up = np.zeros(n, dtype=bool)
    retest_down = np.zeros(n, dtype=bool)

    high_pivots = []
    low_pivots = []
    state = 0
    pending_retest = 0
    pending_line = np.nan
    pending_age = 0

    def line_at(points, x, required_slope=None):
        if len(points) < 2:
            return np.nan
        p1, p2 = points[-2], points[-1]
        if p2[0] == p1[0]:
            return np.nan
        slope = (p2[1] - p1[1]) / float(p2[0] - p1[0])
        # Resistance must be descending; support must be ascending.
        if required_slope == "DOWN" and slope >= 0:
            return np.nan
        if required_slope == "UP" and slope <= 0:
            return np.nan
        return p1[1] + (p2[1] - p1[1]) * ((x - p1[0]) / (p2[0] - p1[0]))

    for i in range(n):
        # Use only trendlines that were already known before this candle.
        r_prev = line_at(high_pivots, i, "DOWN")
        s_prev = line_at(low_pivots, i, "UP")
        resistance_prev[i] = r_prev
        support_prev[i] = s_prev

        close_prev = closes[i - 1] if i > 0 else np.nan
        buffer_r = r_prev * (1.0 + breakout_buffer_pct / 100.0) if np.isfinite(r_prev) else np.nan
        buffer_s = s_prev * (1.0 - breakout_buffer_pct / 100.0) if np.isfinite(s_prev) else np.nan

        if np.isfinite(r_prev) and np.isfinite(closes[i]):
            break_up[i] = bool(closes[i] > buffer_r and (not np.isfinite(close_prev) or close_prev <= buffer_r))
        if np.isfinite(s_prev) and np.isfinite(closes[i]):
            break_down[i] = bool(closes[i] < buffer_s and (not np.isfinite(close_prev) or close_prev >= buffer_s))

        # Track a retest after a breakout. The broken line is frozen so a
        # later pivot cannot silently move the retest target.
        if pending_retest != 0:
            pending_age += 1
            if pending_age <= retest_candles and np.isfinite(pending_line):
                if pending_retest > 0:
                    touched = lows[i] <= pending_line <= highs[i]
                    if touched and closes[i] > pending_line:
                        retest_up[i] = True
                        pending_retest = 0
                else:
                    touched = lows[i] <= pending_line <= highs[i]
                    if touched and closes[i] < pending_line:
                        retest_down[i] = True
                        pending_retest = 0
            if pending_age >= retest_candles and pending_retest != 0:
                pending_retest = 0

        if break_up[i]:
            state = 1
            pending_retest = 1
            pending_line = r_prev
            pending_age = 0
        elif break_down[i]:
            state = -1
            pending_retest = -1
            pending_line = s_prev
            pending_age = 0

        trend_state[i] = state

        # Confirm a pivot only after `length` candles to its right have closed.
        if i >= 2 * length:
            p = i - length
            hw = highs[p - length:p + length + 1]
            lw = lows[p - length:p + length + 1]
            if np.isfinite(hw).all() and np.isfinite(highs[p]) and highs[p] >= np.max(hw):
                if not high_pivots or p - high_pivots[-1][0] >= min_pivot_distance:
                    high_pivots.append((p, float(highs[p])))
                    high_pivots = high_pivots[-4:]
                    pivot_high_event[i] = True
            if np.isfinite(lw).all() and np.isfinite(lows[p]) and lows[p] <= np.min(lw):
                if not low_pivots or p - low_pivots[-1][0] >= min_pivot_distance:
                    low_pivots.append((p, float(lows[p])))
                    low_pivots = low_pivots[-4:]

        resistance[i] = line_at(high_pivots, i, "DOWN")
        support[i] = line_at(low_pivots, i, "UP")

    # Recalculate the displayed line only after each pivot becomes known. The
    # breakout arrays above intentionally remain based on pre-candle state.
    df["trendline_resistance"] = resistance
    df["trendline_support"] = support
    df["trendline_resistance_prev"] = resistance_prev
    df["trendline_support_prev"] = support_prev
    df["trendline_pivot_high"] = pivot_high_event
    df["trendline_pivot_low"] = pivot_low_event
    df["trendline_break_up"] = break_up
    df["trendline_break_down"] = break_down
    df["trendline_retest_up"] = retest_up
    df["trendline_retest_down"] = retest_down
    df["trendline_state"] = trend_state
    return df

def calculate_bollinger(df, length=20, std_mult=2.0):
    """Calculate Bollinger middle/upper/lower bands."""
    df = df.copy()

    length = int(length)
    std_mult = float(std_mult)

    if length <= 0:
        raise ValueError("Bollinger period must be greater than 0.")
    if std_mult <= 0:
        raise ValueError("Bollinger standard deviation must be greater than 0.")

    df["bb_mid"] = df["close"].rolling(length).mean()
    df["bb_std"] = df["close"].rolling(length).std(ddof=0)
    df["bb_upper"] = df["bb_mid"] + std_mult * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - std_mult * df["bb_std"]

    return df

def calculate_stochastic(df, k_length=14, k_smooth=3, d_length=3):
    """Calculate Stochastic %K and %D."""
    df = df.copy()

    k_length = int(k_length)
    k_smooth = int(k_smooth)
    d_length = int(d_length)

    if k_length <= 0 or k_smooth <= 0 or d_length <= 0:
        raise ValueError("Stochastic periods must be greater than 0.")

    lowest_low = df["low"].rolling(k_length).min()
    highest_high = df["high"].rolling(k_length).max()

    denominator = (highest_high - lowest_low).replace(0, float("nan"))

    raw_k = (
        100
        * (df["close"] - lowest_low)
        / denominator
    )

    df["stoch_k"] = raw_k.rolling(k_smooth).mean()
    df["stoch_d"] = df["stoch_k"].rolling(d_length).mean()

    return df

def calculate_vwap(df, length=50):
    """Calculate a rolling volume-weighted average price."""
    df = df.copy()

    length = int(length)
    if length <= 0:
        raise ValueError("VWAP period must be greater than 0.")

    typical_price = (
        df["high"] + df["low"] + df["close"]
    ) / 3.0

    pv = typical_price * df["vol"]

    volume_sum = df["vol"].rolling(length).sum()

    df["vwap"] = (
        pv.rolling(length).sum()
        / volume_sum.replace(0, float("nan"))
    )

    return df

class StrategyEngine:
    """V8.2 modular, pure strategy-decision engine.

    Indicator calculations remain in the existing functions; this class owns
    only the final directional vote contract. It is GUI/exchange independent.
    """

    @staticmethod
    def decide_signal(directional_modules, signal_mode, min_score,
                      atr_pass=True, vol_pass=True, adx_pass=True,
                      mtf_pass_bull=True, mtf_pass_bear=True):
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
            wb=sum(float(ADAPTIVE_MODULE_WEIGHTS.get(n,1.0)) for n,b,be in modules if bool(b) and not bool(be))
            ws=sum(float(ADAPTIVE_MODULE_WEIGHTS.get(n,1.0)) for n,b,be in modules if bool(be) and not bool(b))
            total=wb+ws; edge=abs(wb-ws)/total if total else 0.0
            min_weight=max(float(globals().get("cfg_adaptive_min_weight",ADAPTIVE_DEFAULT_MIN_WEIGHT)),float(min_score))
            edge_threshold=float(globals().get("cfg_adaptive_edge",ADAPTIVE_DEFAULT_EDGE))
            buy=wb>=min_weight and wb>ws and edge>=edge_threshold and atr_pass and vol_pass and adx_pass and mtf_pass_bull
            sell=ws>=min_weight and ws>wb and edge>=edge_threshold and atr_pass and vol_pass and adx_pass and mtf_pass_bear
            return buy,sell,wb,ws
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
                        mtf_pass_bull=True, mtf_pass_bear=True):
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
            wb=sum(float(ADAPTIVE_MODULE_WEIGHTS.get(n,1.0)) for n,b,be in modules if bool(b) and not bool(be))
            ws=sum(float(ADAPTIVE_MODULE_WEIGHTS.get(n,1.0)) for n,b,be in modules if bool(be) and not bool(b))
            total=wb+ws; edge=abs(wb-ws)/total if total else 0.0
            min_weight=max(float(cfg_adaptive_min_weight) if 'cfg_adaptive_min_weight' in globals() else ADAPTIVE_DEFAULT_MIN_WEIGHT,float(min_score))
            edge_threshold=float(cfg_adaptive_edge) if 'cfg_adaptive_edge' in globals() else ADAPTIVE_DEFAULT_EDGE
            if wb>=min_weight and wb>ws and edge>=edge_threshold and atr_pass and vol_pass and adx_pass and mtf_pass_bull: return f"ADAPTIVE_BUY_W{wb:.2f}_EDGE{edge:.2f}"
            if ws>=min_weight and ws>wb and edge>=edge_threshold and atr_pass and vol_pass and adx_pass and mtf_pass_bear: return f"ADAPTIVE_SELL_W{ws:.2f}_EDGE{edge:.2f}"
            return f"ADAPTIVE_BLOCKED_WB{wb:.2f}_WS{ws:.2f}_EDGE{edge:.2f}"
        if mode == "STRICT_ALL_FILTERS":
            if buy == len(modules) and sell == 0 and atr_pass and vol_pass and adx_pass and mtf_pass_bull: return "STRICT_BUY_ALL_FILTERS_PASS"
            if sell == len(modules) and buy == 0 and atr_pass and vol_pass and adx_pass and mtf_pass_bear: return "STRICT_SELL_ALL_FILTERS_PASS"
            failed = [name for name, ok in (("ATR",atr_pass),("VOL",vol_pass),("ADX",adx_pass)) if not ok]
            return "STRICT_BLOCKED" + (f"_FILTERS_{','.join(failed)}" if failed else "_DIRECTION_OR_ALIGNMENT")
        return f"UNKNOWN_SIGNAL_MODE_{mode}"


def parse_symbols(s):
    out=[]
    for x in str(s).replace(","," ").split():
        x=x.strip().upper()
        if not x: continue
        if ":" in x: x=x.split(":")[0]
        if "/" not in x and x.endswith("USDT"): x=x[:-4]+"/USDT"
        out.append(x)
    return list(dict.fromkeys(out))

def resolve_symbol(exchange, symbol):
    """Resolve a user symbol to a loaded linear futures/perpetual CCXT symbol.

    CCXT leaves ``exchange.markets`` as None until ``load_markets()`` has
    completed.  The previous backtester assumed markets were already loaded,
    which caused ``TypeError: argument of type 'NoneType' is not a container
    or iterable`` on the first live-data request.  Keep symbol resolution
    self-contained and fail clearly if market metadata cannot be loaded.
    """
    symbol = str(symbol).strip().upper()
    markets = getattr(exchange, "markets", None)
    if not isinstance(markets, dict) or not markets:
        markets = exchange.load_markets()
        if not isinstance(markets, dict):
            markets = getattr(exchange, "markets", None)
    if not isinstance(markets, dict) or not markets:
        raise RuntimeError(f"{exchange.id}: CCXT market metadata could not be loaded.")

    if symbol in markets:
        market = markets[symbol]
        if market.get("swap") or market.get("future"):
            if market.get("linear", True):
                return market.get("symbol", symbol)

    if "/" not in symbol:
        parsed = parse_symbols(symbol)
        if not parsed:
            raise ValueError(f"Invalid futures symbol: {symbol}")
        symbol = parsed[0]
    parts = symbol.split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid futures symbol: {symbol}")
    base, quote = parts[:2]

    candidates=[f"{base}/{quote}:{quote}",f"{base}/{quote}"]
    for c in candidates:
        m = markets.get(c)
        if m and (m.get("swap") or m.get("future")) and m.get("linear", True):
            return m.get("symbol", c)

    for m in markets.values():
        if (m.get("base")==base and m.get("quote")==quote
                and (m.get("swap") or m.get("future"))
                and m.get("linear", True)):
            return m["symbol"]
    raise ValueError(f"{symbol} is not available as a linear futures market on {exchange.id}.")

def make_exchange(name):
    name=str(name).strip().lower()
    if name=="binance":
        return ccxt.binanceusdm({"enableRateLimit":True,"options":{"defaultType":"future"},"timeout":20000})
    if name=="bybit":
        return ccxt.bybit({"enableRateLimit":True,"options":{"defaultType":"linear"},"timeout":20000})
    raise ValueError("Exchange must be Binance or Bybit.")

def date_ms(s,end=False):
    s=str(s).strip()
    if len(s)==10: s += "T23:59:59" if end else "T00:00:00"
    dt=datetime.fromisoformat(s.replace("Z","+00:00"))
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp()*1000)

def fetch_history(exchange,symbol,timeframe,start_ms,end_ms,log=None,history_start_ms=None):
    tf_ms=TIMEFRAMES[timeframe]
    actual_start_ms=int(history_start_ms if history_start_ms is not None else start_ms)
    cache=RESULTS_DIR/f"cache_{exchange.id}_{symbol.replace('/','_').replace(':','_')}_{timeframe}_{actual_start_ms}_{end_ms}.csv"
    if cache.exists():
        try:
            df=pd.read_csv(cache)
            if len(df)>10:
                df["datetime"]=pd.to_datetime(df["datetime"],utc=True)
                if log: log(f"CACHE {symbol} {timeframe}: {len(df):,} candles")
                return df
        except Exception: pass
    out=[]; since=actual_start_ms
    while since<end_ms:
        batch=exchange.fetch_ohlcv(symbol,timeframe=timeframe,since=since,limit=1000)
        if not batch: break
        out.extend(batch); last=batch[-1][0]; nxt=last+tf_ms
        if nxt<=since: break
        since=nxt
        if log: log(f"Downloading {symbol} {timeframe}: {len(out):,} candles...")
        time.sleep(getattr(exchange,"rateLimit",0)/1000 if getattr(exchange,"rateLimit",0) else 0.05)
    if not out: raise RuntimeError(f"No OHLCV returned for {symbol} {timeframe}.")
    df=pd.DataFrame(out,columns=["time","open","high","low","close","vol"])
    df=df[(df.time>=actual_start_ms)&(df.time<end_ms)].drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["datetime"]=pd.to_datetime(df["time"],unit="ms",utc=True)
    df.to_csv(cache,index=False)
    return df

def build_mtf_filter(df):
    # Live V8 uses completed 4H candle close > EMA200 / < EMA200.
    # Resample base OHLCV into UTC 4H bars and align only bars whose close
    # timestamp is <= the current base candle close timestamp.
    x=df.copy()
    x["datetime"]=pd.to_datetime(x["datetime"],utc=True)
    q=x.set_index("datetime")[["open","high","low","close","vol"]].resample("4h",label="right",closed="right").agg(
        {"open":"first","high":"max","low":"min","close":"last","vol":"sum"}
    ).dropna()
    q["ema200"]=q["close"].ewm(span=200,adjust=False).mean()
    base_times=x["datetime"]
    q_times=q.index
    pos=np.searchsorted(q_times.astype("int64"),base_times.astype("int64"),side="right")-1
    bull=np.zeros(len(x),dtype=bool); bear=np.zeros(len(x),dtype=bool)
    valid=pos>=0
    idx=np.where(valid)[0]
    if len(idx):
        vals=q.iloc[pos[idx]]
        bull[idx]=(vals["close"].to_numpy()>vals["ema200"].to_numpy())
        bear[idx]=(vals["close"].to_numpy()<vals["ema200"].to_numpy())
    x["mtf_bull"]=bull; x["mtf_bear"]=bear
    return x

def build_indicators(df,cfg):
    """Build exactly the indicator columns the live V8.2.4 loop would build."""
    x=df.copy()
    x["ema_filter"]=x.close.ewm(span=int(cfg["ema_len"]),adjust=False).mean()
    x["ema_fast"]=x.close.ewm(span=int(cfg["ema_fast"]),adjust=False).mean()
    x["ema_slow"]=x.close.ewm(span=int(cfg["ema_slow"]),adjust=False).mean()
    x=calculate_supertrend(x,int(cfg["st_len"]),float(cfg["st_mult"]),cfg.get("st_source","CLOSE"),bool(cfg.get("st_change_atr",True)))
    # V8 live calculates ADX even when the ADX vote is disabled.
    x=calculate_adx(x,int(cfg.get("adx_len",14)))
    if cfg.get("use_macd",False):
        x=calculate_macd(x,int(cfg["macd_fast"]),int(cfg["macd_slow"]),int(cfg["macd_signal"]))
    if cfg.get("use_rsi",False):
        x=calculate_rsi(x,int(cfg["rsi_len"]))
        x=calculate_rsi_ma(x,cfg.get("rsi_ma_type","EMA"),int(cfg["rsi_ma_len"]))
    if cfg.get("use_bb",False):
        x=calculate_bollinger(x,int(cfg["bb_len"]),float(cfg["bb_std"]))
    if cfg.get("use_stoch",False):
        x=calculate_stochastic(x,int(cfg["stoch_k"]),int(cfg["stoch_smooth"]),int(cfg["stoch_d"]))
    if cfg.get("use_vwap",False):
        x=calculate_vwap(x,int(cfg["vwap_len"]))
    if cfg.get("use_vwap_delta",False):
        x=calculate_vwap_delta(x,bool(cfg.get("vwap_delta_smooth",False)),int(cfg.get("vwap_delta_smooth_len",21)),int(cfg.get("vwap_delta_baseline",50)))
    if cfg.get("use_vidya",False):
        x=calculate_vidya(x,int(cfg["vidya_len"]),int(cfg["vidya_momentum"]),float(cfg["vidya_band"]),200,15)
    if cfg.get("use_nwe",False):
        x=calculate_nadaraya_watson_envelope(x,float(cfg["nwe_bandwidth"]),float(cfg["nwe_mult"]),int(cfg.get("nwe_lookback",500)),int(cfg.get("nwe_mae",499)))
    if cfg.get("use_liq_swings",False):
        x=calculate_liquidity_swings(x,int(cfg["liq_length"]),cfg.get("liq_area","Wick Extremity"),cfg.get("liq_filter","Count"),float(cfg.get("liq_filter_value",0)))
    if cfg.get("use_trendline",False):
        x=calculate_trendline_breakout(x,int(cfg["trendline_length"]),int(cfg["trendline_min_distance"]),float(cfg.get("trendline_buffer",0)),int(cfg.get("trendline_retest_candles",3)))
    x["vol_ma"]=x.vol.rolling(int(cfg.get("vol_len",20))).mean()
    if cfg.get("use_divergence",False):
        x=calculate_divergence_module(x,cfg)
    else:
        x["div_bull_count"]=0; x["div_bear_count"]=0
        x["div_bull_signal"]=False; x["div_bear_signal"]=False; x["divergence_state"]=0
    if cfg.get("use_vol_sr",False):
        x=_volume_sr_base_series(x,cfg)
    else:
        x["sr_bull"]=False; x["sr_bear"]=False; x["sr_fresh_bull"]=False; x["sr_fresh_bear"]=False
    if cfg.get("use_mtf",False):
        x=build_mtf_filter(x)
    else:
        x["mtf_bull"]=True; x["mtf_bear"]=True
    return x

def _b(v): return bool(v) if not pd.isna(v) else False
def _f(v,default=0.0):
    try:
        z=float(v)
        return z if np.isfinite(z) else default
    except Exception:
        return default

def module_votes(df,i,cfg):
    # Returns the exact 17-module directional vote contract used by V8.2.4.
    if i<3: return []
    p2=df.iloc[i-2]; p=df.iloc[i-1]; c=df.iloc[i]
    # V8 live evaluates df.iloc[-2] as the signal candle and -3 as prior.
    close=float(c.close)
    candle_bull=close>float(c.open); candle_bear=close<float(c.open)
    use_st=bool(cfg["use_st"]); use_ema=bool(cfg["use_ema"]); use_ema_cross=bool(cfg["use_ema_cross"])
    use_macd=bool(cfg["use_macd"]); use_rsi=bool(cfg["use_rsi"]); use_bb=bool(cfg["use_bb"]); use_stoch=bool(cfg["use_stoch"])
    use_vwap=bool(cfg["use_vwap"]); use_vd=bool(cfg["use_vwap_delta"]); use_vidya=bool(cfg["use_vidya"])
    use_nwe=bool(cfg["use_nwe"]); use_liq=bool(cfg["use_liq_swings"]); use_tl=bool(cfg["use_trendline"])
    use_mtf=bool(cfg["use_mtf"]); use_vol=bool(cfg["use_vol"]); use_adx=bool(cfg["use_adx"]); use_atr=bool(cfg["use_atr"])
    votes=[]

    if use_st:
        st_bull=bool(c.trend); st_bear=not st_bull
        if str(cfg["st_entry_mode"]).upper()=="CURRENT_TREND" or str(cfg["signal_mode"]).upper()=="SCORE":
            votes.append(("ST",st_bull,st_bear))
        else:
            votes.append(("ST", (not bool(p.trend)) and bool(c.trend), bool(p.trend) and not bool(c.trend)))
    if use_ema:
        votes.append(("EMA", close>_f(c.ema_filter), close<_f(c.ema_filter)))
    if use_ema_cross:
        cross_up=_f(p.ema_fast)<=_f(p.ema_slow) and _f(c.ema_fast)>_f(c.ema_slow)
        cross_dn=_f(p.ema_fast)>=_f(p.ema_slow) and _f(c.ema_fast)<_f(c.ema_slow)
        trend_bull=_f(c.ema_fast)>_f(c.ema_slow); trend_bear=_f(c.ema_fast)<_f(c.ema_slow)
        if str(cfg["ema_cross_entry_mode"]).upper()=="CURRENT_TREND":
            votes.append(("EMA_CROSS",trend_bull,trend_bear))
        else:
            votes.append(("EMA_CROSS",cross_up,cross_dn))
    if use_macd:
        votes.append(("MACD",
            _f(p.macd)<=_f(p.macd_signal) and _f(c.macd)>_f(c.macd_signal),
            _f(p.macd)>=_f(p.macd_signal) and _f(c.macd)<_f(c.macd_signal)))
    if use_rsi:
        cross_b=_f(p.rsi)<=_f(p.rsi_ma) and _f(c.rsi)>_f(c.rsi_ma)
        cross_s=_f(p.rsi)>=_f(p.rsi_ma) and _f(c.rsi)<_f(c.rsi_ma)
        rev_b=_f(c.rsi)<=float(cfg["rsi_os"]); rev_s=_f(c.rsi)>=float(cfg["rsi_ob"])
        logic=str(cfg["rsi_logic"]).upper()
        if logic=="CROSS_MA": rb,rs=cross_b,cross_s
        elif logic=="EITHER": rb,rs=(rev_b or cross_b),(rev_s or cross_s)
        else: rb,rs=rev_b,rev_s
        votes.append(("RSI",rb,rs))
    if use_bb:
        votes.append(("BB",_f(c.close)>_f(c.bb_upper),_f(c.close)<_f(c.bb_lower)))
    if use_stoch:
        votes.append(("STOCH",_f(p.stoch_k)<=_f(p.stoch_d) and _f(c.stoch_k)>_f(c.stoch_d),
                             _f(p.stoch_k)>=_f(p.stoch_d) and _f(c.stoch_k)<_f(c.stoch_d)))
    if use_vwap:
        votes.append(("VWAP",_f(c.close)>_f(c.vwap),_f(c.close)<_f(c.vwap)))
    if use_vd:
        if str(cfg["vwap_delta_logic"]).upper()=="CROSS_BASELINE":
            votes.append(("VWAP_DELTA",_f(p.vwap_delta)<=_f(p.vwap_delta_baseline) and _f(c.vwap_delta)>_f(c.vwap_delta_baseline),
                                          _f(p.vwap_delta)>=_f(p.vwap_delta_baseline) and _f(c.vwap_delta)<_f(c.vwap_delta_baseline)))
        else:
            votes.append(("VWAP_DELTA",_f(c.vwap_delta)>_f(c.vwap_delta_baseline),_f(c.vwap_delta)<_f(c.vwap_delta_baseline)))
    if use_vidya:
        if str(cfg["vidya_entry_mode"]).upper()=="FRESH_FLIP":
            votes.append(("VIDYA",_b(c.vidya_cross_up),_b(c.vidya_cross_down)))
        else:
            votes.append(("VIDYA",_b(c.vidya_trend_up),not _b(c.vidya_trend_up)))
    if use_nwe:
        vals=[c.nwe_out,c.nwe_upper,c.nwe_lower,p.nwe_upper,p.nwe_lower]
        if not all(np.isfinite(_f(v,np.nan)) for v in vals):
            votes.append(("NWE",False,False))
        elif str(cfg["nwe_entry_mode"]).upper()=="FRESH_CROSS":
            votes.append(("NWE",_f(c.close)<_f(c.nwe_lower) and _f(p.close)>=_f(p.nwe_lower),
                              _f(c.close)>_f(c.nwe_upper) and _f(p.close)<=_f(p.nwe_upper)))
        else:
            votes.append(("NWE",_f(c.nwe_out)>_f(p.nwe_out),_f(c.nwe_out)<_f(p.nwe_out)))
    if use_liq:
        if str(cfg["liq_entry_mode"]).upper()=="CURRENT_TREND":
            state=int(_f(c.liq_swing_trend))
            votes.append(("LIQ_SWING",state>0,state<0))
        else:
            votes.append(("LIQ_SWING",_b(c.liq_swing_high_break),_b(c.liq_swing_low_break)))
    if use_tl:
        mode=str(cfg["trendline_entry_mode"]).upper()
        if mode=="CURRENT_TREND":
            state=int(_f(c.trendline_state)); votes.append(("TRENDLINE",state>0,state<0))
        elif mode=="BREAK_RETEST":
            votes.append(("TRENDLINE",_b(c.trendline_retest_up),_b(c.trendline_retest_down)))
        else:
            votes.append(("TRENDLINE",_b(c.trendline_break_up),_b(c.trendline_break_down)))
    if use_mtf:
        votes.append(("MTF",_b(c.mtf_bull),_b(c.mtf_bear)))
    if cfg.get("use_divergence",False):
        div_b=int(_f(c.div_bull_count)); div_s=int(_f(c.div_bear_count)); state=int(_f(c.divergence_state))
        if str(cfg.get("div_entry_mode","FRESH")).upper()=="CURRENT_STATE":
            votes.append(("DIVERGENCE", state>0 and div_b>=int(cfg["div_min_count"]), state<0 and div_s>=int(cfg["div_min_count"])))
        else:
            votes.append(("DIVERGENCE", _b(c.div_bull_signal) and div_b>=int(cfg["div_min_count"]),
                                       _b(c.div_bear_signal) and div_s>=int(cfg["div_min_count"])))
    if cfg.get("use_vol_sr",False):
        votes.append(("VOL_SR",_b(c.sr_bull),_b(c.sr_bear)))
    atr_pct=_f(c.atr)/close*100 if close>0 else 0
    atr_pass=(not use_atr) or atr_pct>=float(cfg["atr_min_pct"])
    vol_pass=(not use_vol) or (_f(c.vol)>_f(c.vol_ma))
    adx_pass=(not use_adx) or (_f(c.adx)>=float(cfg["adx_thresh"]))
    if use_vol and vol_pass and str(cfg["signal_mode"]).upper()!="ADAPTIVE_SCORE": votes.append(("VOL",candle_bull,candle_bear))
    if use_adx and adx_pass: votes.append(("ADX",_f(c.plus_di)>_f(c.minus_di),_f(c.minus_di)>_f(c.plus_di)))
    if use_atr and atr_pass and str(cfg["signal_mode"]).upper()!="ADAPTIVE_SCORE": votes.append(("ATR",candle_bull,candle_bear))
    return votes


def persistent_votes(df,i,cfg):
    """Persistent directional states used by V8 Hold-All-Reverse reversal checks."""
    if i<3: return []
    p=df.iloc[i-1]; c=df.iloc[i]; close=_safe_float(c.close)
    out=[]
    if cfg["use_st"]:
        st=bool(c.trend); out.append(("ST",st,not st))
    if cfg["use_ema"]:
        out.append(("EMA",close>_f(c.ema_filter),close<_f(c.ema_filter)))
    if cfg["use_ema_cross"]:
        out.append(("EMA_CROSS",_f(c.ema_fast)>_f(c.ema_slow),_f(c.ema_fast)<_f(c.ema_slow)))
    if cfg["use_macd"]:
        out.append(("MACD",_f(c.macd)>_f(c.macd_signal),_f(c.macd)<_f(c.macd_signal)))
    if cfg["use_rsi"]:
        out.append(("RSI",_f(c.rsi)>50,_f(c.rsi)<50))
    if cfg["use_bb"]:
        out.append(("BB",close>_f(c.bb_mid),close<_f(c.bb_mid)))
    if cfg["use_stoch"]:
        out.append(("STOCH",_f(c.stoch_k)>_f(c.stoch_d),_f(c.stoch_k)<_f(c.stoch_d)))
    if cfg["use_vwap"]:
        out.append(("VWAP",close>_f(c.vwap),close<_f(c.vwap)))
    if cfg["use_vwap_delta"]:
        out.append(("VWAP_DELTA",_f(c.vwap_delta)>_f(c.vwap_delta_baseline),_f(c.vwap_delta)<_f(c.vwap_delta_baseline)))
    if cfg["use_vidya"]:
        trend=_b(c.vidya_trend_up); out.append(("VIDYA",trend,not trend))
    if cfg["use_nwe"]:
        out.append(("NWE",_f(c.nwe_out)>_f(p.nwe_out),_f(c.nwe_out)<_f(p.nwe_out)))
    if cfg["use_liq_swings"]:
        state=int(_f(c.liq_swing_trend)); out.append(("LIQ_SWING",state>0,state<0))
    if cfg["use_trendline"]:
        state=int(_f(c.trendline_state)); out.append(("TRENDLINE",state>0,state<0))
    if cfg["use_mtf"]:
        out.append(("MTF",_b(c.mtf_bull),_b(c.mtf_bear)))
    if cfg.get("use_divergence",False):
        state=int(_f(c.divergence_state)); out.append(("DIVERGENCE",state>0,state<0))
    if cfg.get("use_vol_sr",False):
        out.append(("VOL_SR",_b(c.sr_bull),_b(c.sr_bear)))
    atr_pct=_f(c.atr)/close*100 if close>0 else 0
    vol_pass=(not cfg["use_vol"]) or _f(c.vol)>_f(c.vol_ma)
    adx_pass=(not cfg["use_adx"]) or _f(c.adx)>=float(cfg["adx_thresh"])
    if cfg["use_vol"] and vol_pass:
        out.append(("VOL",close>_f(c.open),close<_f(c.open)))
    if cfg["use_adx"] and adx_pass:
        out.append(("ADX",_f(c.plus_di)>_f(c.minus_di),_f(c.minus_di)>_f(c.plus_di)))
    if cfg["use_atr"] and atr_pct>=float(cfg["atr_min_pct"]):
        out.append(("ATR",close>_f(c.open),close<_f(c.open)))
    return out

def decide(votes,cfg,atr_pass=True,vol_pass=True,adx_pass=True,mtf_pass_bull=True,mtf_pass_bear=True):
    """Compatibility helper; unlike the old version, it has no undefined df reference."""
    return StrategyEngine.decide_signal(
        votes, str(cfg["signal_mode"]).upper(), int(cfg["min_score"]),
        atr_pass=atr_pass, vol_pass=vol_pass, adx_pass=adx_pass,
        mtf_pass_bull=mtf_pass_bull, mtf_pass_bear=mtf_pass_bear,
    )



def target_to_price_fraction(target_pct, mode, leverage):
    target_pct=float(target_pct); leverage=float(leverage)
    if target_pct<=0 or leverage<=0: raise ValueError("SL/TP target and leverage must be > 0.")
    if str(mode).upper()=="PRICE_%": return target_pct/100.0
    if str(mode).upper()=="ROI_%": return (target_pct/100.0)/leverage
    raise ValueError(f"Unknown protection mode: {mode}")

def _safe_float(v, default=0.0):
    try:
        z=float(v)
        return z if np.isfinite(z) else default
    except Exception:
        return default

def validate_config(cfg):
    c={**DEFAULTS, **cfg}
    if c["signal_mode"] not in SUPPORTED_SIGNAL_MODES: raise ValueError("Unsupported signal mode")
    if not 0.0<float(c.get("adaptive_edge",ADAPTIVE_DEFAULT_EDGE))<1.0: raise ValueError("Adaptive edge must be between 0 and 1")
    if float(c.get("adaptive_min_weight",ADAPTIVE_DEFAULT_MIN_WEIGHT))<=0: raise ValueError("Adaptive min weight must be >0")
    if c["grid_mode"] not in SUPPORTED_GRID_MODES: raise ValueError("Unsupported Grid mode")
    if int(c["leverage"])<=0: raise ValueError("Leverage must be > 0")
    if float(c["risk_pct"])<=0 or float(c["risk_pct"])>=100: raise ValueError("Risk Per Trade must be >0 and <100")
    if float(c["sl_pct"])<=0 or float(c["tp1_pct"])<=0 or float(c["tp2_pct"])<=0 or float(c["hold_sl_roi"])<=0: raise ValueError("SL/TP targets must be >0")
    if c["tp_mode"] not in ("PRICE_%","ROI_%") or c["sl_mode"] not in ("PRICE_%","ROI_%"): raise ValueError("Invalid SL/TP mode")
    if c["tp_qty_mode"] not in ("PERCENT_%","FIXED_QTY"): raise ValueError("Invalid TP quantity mode")
    if c["tp_qty_mode"]=="PERCENT_%" and abs(float(c["tp1_close"])+float(c["tp2_close"])-100)>1e-9: raise ValueError("TP1 + TP2 percentages must equal 100")
    if int(c["grid_levels"])<1 or int(c["grid_levels"])>50: raise ValueError("Grid levels must be 1-50")
    if float(c["grid_spacing"])<=0 or float(c["grid_spacing"])>50: raise ValueError("Grid spacing invalid")
    if float(c["grid_spacing"])*int(c["grid_levels"])>=100: raise ValueError("Grid spacing × levels must be <100%")
    if float(c["grid_order_size"])<=0 or float(c["grid_tp"])<=0: raise ValueError("Grid order size/TP invalid")
    if float(c["grid_sl"])<=float(c["grid_spacing"])*int(c["grid_levels"]) and c["grid_mode"] in ("LONG_GRID","SHORT_GRID","NEUTRAL_GRID"):
        raise ValueError("Grid Global SL must exceed Grid Spacing × Levels")
    if float(c["grid_max_exposure"])<=0 or float(c["grid_max_dd"])<=0 or float(c["grid_max_dd"])>=100: raise ValueError("Grid risk settings invalid")
    if c["grid_trend_filter"] not in ("OFF","SUPERTREND","SCORE"): raise ValueError("Invalid Grid Trend Filter")
    enabled=sum(bool(c[k]) for k in ("use_st","use_ema","use_ema_cross","use_macd","use_rsi","use_bb","use_stoch","use_vwap","use_vwap_delta","use_vidya","use_nwe","use_liq_swings","use_trendline","use_mtf","use_vol","use_adx","use_atr","use_divergence","use_vol_sr"))
    if c["grid_trend_filter"]=="SCORE":
        if enabled==0: raise ValueError("Grid Score Min exceeds enabled strategy modules")
        if c["signal_mode"]=="ADAPTIVE_SCORE":
            names=["ST","EMA","EMA_CROSS","MACD","RSI","BB","STOCH","VWAP","VWAP_DELTA","VIDYA","NWE","LIQ_SWING","TRENDLINE","MTF","DIVERGENCE","VOL_SR","VOL","ADX","ATR"]
            flags=[c[k] for k in ("use_st","use_ema","use_ema_cross","use_macd","use_rsi","use_bb","use_stoch","use_vwap","use_vwap_delta","use_vidya","use_nwe","use_liq_swings","use_trendline","use_mtf","use_divergence","use_vol_sr","use_vol","use_adx","use_atr")]
            cap=sum(ADAPTIVE_MODULE_WEIGHTS.get(n,1.0) for n,e in zip(names,flags) if e and n not in ("VOL","ATR"))
            if float(c["grid_score_min"])>cap: raise ValueError("Grid Score Min exceeds adaptive weighted capacity")
        elif float(c["grid_score_min"])>enabled: raise ValueError("Grid Score Min exceeds enabled strategy modules")
    if c["grid_mode"]=="NEUTRAL_GRID" and c["grid_trend_filter"]=="SUPERTREND" and not c["use_st"]: raise ValueError("NEUTRAL_GRID + SUPERTREND requires Supertrend")
    if c["grid_mode"]=="NEUTRAL_GRID" and c["grid_trend_filter"] in ("OFF","SCORE") and enabled==0: raise ValueError("NEUTRAL_GRID requires valid strategy score")
    if c["grid_mode"]=="NEUTRAL_GRID" and c["grid_trend_filter"] in ("OFF","SCORE") and c["signal_mode"]!="ADAPTIVE_SCORE" and float(c["grid_score_min"])>enabled: raise ValueError("NEUTRAL_GRID requires valid strategy score")
    if int(c["div_pivot"])<1 or int(c["div_pivot"])>50: raise ValueError("Divergence Pivot must be 1-50")
    if c["div_source"] not in ("Close","High/Low"): raise ValueError("Invalid Divergence Source")
    if c["div_type"] not in ("Regular","Hidden","Regular/Hidden"): raise ValueError("Invalid Divergence Type")
    if int(c["div_min_count"])<1 or int(c["div_min_count"])>10: raise ValueError("Divergence minimum count must be 1-10")
    if int(c["div_max_pivots"])<1 or int(c["div_max_pivots"])>20: raise ValueError("Divergence max pivots must be 1-20")
    if int(c["div_max_bars"])<30 or int(c["div_max_bars"])>200: raise ValueError("Divergence max bars must be 30-200")
    if c["div_entry_mode"] not in ("FRESH","CURRENT_STATE"): raise ValueError("Invalid Divergence Entry")
    if c["use_divergence"] and not any(bool(c[k]) for k in ("div_use_macd","div_use_macd_hist","div_use_rsi","div_use_stoch","div_use_cci","div_use_momentum","div_use_obv","div_use_vwmacd","div_use_cmf","div_use_mfi")):
        raise ValueError("Divergence requires at least one source indicator")
    if int(c["div_cci_len"])<=0 or int(c["div_mom_len"])<=0: raise ValueError("Divergence CCI/Momentum lengths must be >0")
    if int(c["sr_volume_ma"])<=0: raise ValueError("Volume S/R MA threshold must be >0")
    if int(c["sr_history_bars"])<10 or int(c["sr_history_bars"])>500: raise ValueError("SR History Bars must be 10-500")
    if c["sr_vote_mode"] not in ("MAJORITY","ANY","ALL"): raise ValueError("Invalid Volume S/R vote mode")
    if c["sr_entry_mode"] not in ("CURRENT_ZONE","FRESH_BREAK"): raise ValueError("Invalid Volume S/R entry mode")
    if c["use_vol_sr"] and all(str(c[k])=="Disable" for k in ("sr_tf1","sr_tf2","sr_tf3","sr_tf4")): raise ValueError("Volume S/R requires a timeframe")
    return c

def build_strategy_columns(df,cfg):
    x=df.copy()
    x=build_indicators(x,cfg)
    return x

def signal_for_bar(df,i,cfg):
    global cfg_adaptive_edge,cfg_adaptive_min_weight
    cfg_adaptive_edge=float(cfg.get("adaptive_edge",ADAPTIVE_DEFAULT_EDGE))
    cfg_adaptive_min_weight=float(cfg.get("adaptive_min_weight",ADAPTIVE_DEFAULT_MIN_WEIGHT))
    votes=module_votes(df,i,cfg)
    if i<3: return ("NONE",votes,0,0,"WARMUP")
    # Recreate the exact filter flags passed into STRICT_ALL_FILTERS.
    c=df.iloc[i]
    close=_safe_float(c.close)
    atr_pct=_safe_float(c.atr)/close*100 if close>0 else 0.0
    atr_pass=(not cfg["use_atr"]) or atr_pct>=float(cfg["atr_min_pct"])
    vol_pass=(not cfg["use_vol"]) or _safe_float(c.vol)>_safe_float(c.vol_ma)
    adx_pass=(not cfg["use_adx"]) or _safe_float(c.adx)>=float(cfg["adx_thresh"])
    mtf_bull=_safe_float(c.mtf_bull,0)>0 if cfg["use_mtf"] else True
    mtf_bear=_safe_float(c.mtf_bear,0)>0 if cfg["use_mtf"] else True
    b,s,bs,ss=StrategyEngine.decide_signal(votes,cfg["signal_mode"],int(cfg["min_score"]),
                                           atr_pass,vol_pass,adx_pass,mtf_bull,mtf_bear)
    reason=StrategyEngine.decision_reason(votes,cfg["signal_mode"],int(cfg["min_score"]),
                                          atr_pass,vol_pass,adx_pass,mtf_bull,mtf_bear)
    return ("BUY" if b else "SELL" if s else "NONE",votes,bs,ss,reason)

def all_reverse(votes, side):
    if not votes: return False
    return all(bool(bear if side=="LONG" else bull) for _,bull,bear in votes)

def calc_metrics(trades,initial,equity_curve=None):
    if not trades:
        return {k:0.0 for k in ["trades","wins","losses","win_rate","net_pnl","return_pct","profit_factor","max_drawdown","avg_trade","avg_win","avg_loss","expectancy","long_trades","short_trades","long_pnl","short_pnl","max_consecutive_losses","fees"]}
    pnl=np.array([float(t["net_pnl"]) for t in trades],dtype=float)
    eq=np.array(equity_curve if equity_curve is not None else initial+np.cumsum(pnl),dtype=float)
    peak=np.maximum.accumulate(np.r_[initial,eq]); dd=np.maximum(0,peak[1:]-eq)
    wins=pnl[pnl>0]; losses=pnl[pnl<0]; gw=wins.sum() if len(wins) else 0; gl=abs(losses.sum()) if len(losses) else 0
    seq=mx=0
    for v in pnl:        if v<=0: seq+=1; mx=max(mx,seq)
        else: seq=0
    longs=[t for t in trades if t["side"]=="LONG"]; shorts=[t for t in trades if t["side"]=="SHORT"]
    fees=sum(float(t.get("fees",0)) for t in trades)
    return {"trades":int(len(pnl)),"wins":int((pnl>0).sum()),"losses":int((pnl<=0).sum()),
            "win_rate":float((pnl>0).mean()*100),"net_pnl":float(pnl.sum()),
            "return_pct":float(pnl.sum()/initial*100 if initial else 0),
            "profit_factor":float(gw/gl) if gl else (999.0 if gw else 0.0),
            "max_drawdown":float(dd.max()) if len(dd) else 0,"avg_trade":float(pnl.mean()),
            "avg_win":float(wins.mean()) if len(wins) else 0,"avg_loss":float(losses.mean()) if len(losses) else 0,
            "expectancy":float(pnl.mean()),"long_trades":len(longs),"short_trades":len(shorts),
            "long_pnl":float(sum(t["net_pnl"] for t in longs)),"short_pnl":float(sum(t["net_pnl"] for t in shorts)),
            "max_consecutive_losses":int(mx),"fees":float(fees)}

def _slip_price(price,side,slip,entry=True):
    # side is LONG/SHORT. Positive slippage is adverse.
    if entry: return price*(1+slip if side=="LONG" else 1-slip)
    return price*(1-slip if side=="LONG" else 1+slip)

def _tp_qtys(qty,cfg):
    if cfg["tp_qty_mode"]=="PERCENT_%":
        q1=qty*float(cfg["tp1_close"])/100.0
        q2=qty-q1
    else:
        q1=float(cfg["tp1_close"]); q2=float(cfg["tp2_close"])
        if abs(q1+q2-qty)>max(1e-12,abs(qty)*1e-9):
            raise ValueError(f"FIXED_QTY TP split {q1}+{q2} != position {qty}")
    if q1<=0 or q2<=0: raise ValueError("TP split leaves a non-positive quantity")
    return q1,q2

def _normal_position_from_entry(entry,side,equity,cfg):
    hold=bool(cfg["hold_until_all_reverse"])
    effective_sl_pct=float(cfg["hold_sl_roi"]) if hold else float(cfg["sl_pct"])
    effective_sl_mode="ROI_%" if hold else cfg["sl_mode"]
    sl_move=target_to_price_fraction(effective_sl_pct,effective_sl_mode,float(cfg["leverage"]))
    tp1_move=target_to_price_fraction(float(cfg["tp1_pct"]),cfg["tp_mode"],float(cfg["leverage"]))
    tp2_move=target_to_price_fraction(float(cfg["tp2_pct"]),cfg["tp_mode"],float(cfg["leverage"]))
    if cfg["size_mode"]=="FIXED_QTY": qty=float(cfg["fixed_qty"])
    else:
        qty=(equity*(float(cfg["risk_pct"])/100.0))/(entry*sl_move)
    qty=max(qty,0.0)
    if side=="LONG": sl=entry*(1-sl_move); tp1=entry*(1+tp1_move); tp2=entry*(1+tp2_move)
    else: sl=entry*(1+sl_move); tp1=entry*(1-tp1_move); tp2=entry*(1-tp2_move)
    q1=q2=0.0
    if not hold:
        q1,q2=_tp_qtys(qty,cfg)
    return {"side":side,"entry":entry,"qty":qty,"remaining_qty":qty,"sl":sl,"tp1":tp1,"tp2":tp2,
            "tp1_qty":q1,"tp2_qty":q2,"tp1_done":False,"tp2_done":False,"be":False,
            "hold_wait":bool(hold and cfg["hold_sl_wait_reversal"]),"hold_threshold_hit":False,
            "signal_time":None,"entry_time":None,"entry_candle":None,"gross_pnl":0.0,"fees":0.0,
            "entry_notional":entry*qty}

def _trade_fee(notional,cfg): return abs(notional)*float(cfg["fee_pct"])/100.0

def _close_piece(pos,qty,exit_price,cfg,reason):
    side=pos["side"]
    raw=(exit_price-pos["entry"])/pos["entry"] if side=="LONG" else (pos["entry"]-exit_price)/pos["entry"]
    notional=pos["entry"]*qty
    gross=notional*raw
    fee=_trade_fee(notional,cfg)+_trade_fee(exit_price*qty,cfg)
    pos["gross_pnl"]+=gross; pos["fees"]+=fee; pos["realized_net"] = pos.get("realized_net",0.0)+gross-fee
    pos["remaining_qty"]-=qty
    return gross-fee

def simulate_position_bar(pos,row,cfg):
    # Returns (event list, closed_all, realized_net_change).
    if not pos: return [],False,0.0
    side=pos["side"]; high=float(row.high); low=float(row.low); events=[]; realized=0.0
    sl_hit=(low<=pos["sl"]) if side=="LONG" else (high>=pos["sl"])
    if sl_hit:
        px=_slip_price(pos["sl"],side,float(cfg["slippage_pct"])/100.0,entry=False) if cfg["slippage_exit"] else pos["sl"]
        q=pos["remaining_qty"]; realized+=_close_piece(pos,q,px,cfg,"SL"); events.append(("SL",q,px))
        pos["remaining_qty"]=0.0
        return events,True,realized

    if not pos["hold_wait"]:
        if not pos["tp1_done"]:
            tp1_hit=(high>=pos["tp1"]) if side=="LONG" else (low<=pos["tp1"])
            if tp1_hit:
                q=pos["tp1_qty"]; px=_slip_price(pos["tp1"],side,float(cfg["slippage_pct"])/100.0,entry=False) if cfg["slippage_exit"] else pos["tp1"]
                realized+=_close_piece(pos,q,px,cfg,"TP1"); pos["tp1_done"]=True; events.append(("TP1",q,px))
                if cfg["tp1_be"] and pos["remaining_qty"]>0:
                    pos["sl"]=pos["entry"]; pos["be"]=True
        if pos["remaining_qty"]>0 and not pos["tp2_done"]:
            tp2_hit=(high>=pos["tp2"]) if side=="LONG" else (low<=pos["tp2"])
            if tp2_hit:
                q=pos["remaining_qty"]; px=_slip_price(pos["tp2"],side,float(cfg["slippage_pct"])/100.0,entry=False) if cfg["slippage_exit"] else pos["tp2"]
                realized+=_close_piece(pos,q,px,cfg,"TP2"); pos["tp2_done"]=True; events.append(("TP2",q,px))
    else:
        # WAIT mode has no exchange-side SL; threshold is monitored and then
        # strategy reversal is responsible for the exit.
        threshold=pos["sl"]
        hit=(low<=threshold) if side=="LONG" else (high>=threshold)
        if hit: pos["hold_threshold_hit"]=True; events.append(("HOLD_THRESHOLD",0,threshold))
    # After TP1, BE stop can be touched later in the same candle. This is
    # deliberately checked after TP1, matching the order-management sequence.
    if pos["remaining_qty"]>0 and pos["be"]:
        be_hit=(low<=pos["sl"]) if side=="LONG" else (high>=pos["sl"])
        if be_hit:
            px=_slip_price(pos["sl"],side,float(cfg["slippage_pct"])/100.0,entry=False) if cfg["slippage_exit"] else pos["sl"]
            q=pos["remaining_qty"]; realized+=_close_piece(pos,q,px,cfg,"SL"); events.append(("SL_BE",q,px)); pos["remaining_qty"]=0.0
            return events,True,realized
    return events,pos["remaining_qty"]<=1e-15,realized

def finalize_trade(pos,exit_time,reason,exit_price=None):
    p=dict(pos)
    p["exit_time"]=str(exit_time); p["reason"]=reason
    p["exit_price"]=exit_price if exit_price is not None else np.nan
    p["net_pnl"]=float(p.get("realized_net",0.0))
    return p

def _grid_direction(cfg,votes,st_bull,st_bear):
    filt=cfg["grid_trend_filter"]
    bs=sum(1 for _,b,_ in votes if b); ss=sum(1 for _,_,s in votes if s)
    if filt=="SUPERTREND":
        return "LONG" if st_bull and not st_bear else "SHORT" if st_bear and not st_bull else None
    need=float(cfg["grid_score_min"])
    return "LONG" if bs>=need and bs>ss else "SHORT" if ss>=need and ss>bs else None

@dataclass
class GridState:
    active: bool=False
    mode: str="OFF"
    center: float=0.0
    direction: str|None=None
    orders: dict=None
    filled_levels: set|None=None
    position_qty: float=0.0
    avg_entry: float=0.0
    session_start_balance: float=0.0
    peak_equity: float=0.0
    paused_until_bar: int=0
    tp: float|None=None
    sl: float|None=None
    realized_pnl: float=0.0
    fees: float=0.0
    started_bar: int=0
    def __post_init__(self):
        if self.orders is None: self.orders={}
        if self.filled_levels is None: self.filled_levels=set()

def _grid_reset(gs):
    gs.orders={}; gs.filled_levels=set(); gs.position_qty=0; gs.avg_entry=0; gs.tp=None; gs.sl=None; gs.direction=None

def _grid_place_orders(gs,cfg,allow_long,allow_short):
    center=gs.center
    planned=sum(float(v["usdt"]) for v in gs.orders.values())
    exposure=gs.position_qty*gs.avg_entry
    for n in range(1,int(cfg["grid_levels"])+1):
        if gs.mode=="SHORT_GRID" or (gs.mode=="NEUTRAL_GRID" and gs.direction=="SHORT"):
            side="SHORT"; price=center*(1+float(cfg["grid_spacing"])/100*n); allowed=allow_short
        else:
            side="LONG"; price=center*(1-float(cfg["grid_spacing"])/100*n); allowed=allow_long
        if not allowed: continue
        key=f"{side}:{n}"
        if key in gs.orders or key in gs.filled_levels: continue
        usdt=float(cfg["grid_order_size"])*((1+float(cfg["grid_size_increase"])/100)**(n-1))
        if exposure+planned+usdt>float(cfg["grid_max_exposure"]): break
        qty=usdt/price
        gs.orders[key]={"side":side,"price":price,"qty":qty,"usdt":usdt,"level":n}
        planned+=usdt

def _grid_mark_to_market(gs,row):
    if gs.position_qty<=0: return 0.0
    px=float(row.close)
    return gs.position_qty*((px-gs.avg_entry) if gs.direction=="LONG" else (gs.avg_entry-px))

def _grid_fill_orders(gs,row,cfg):
    fills=[]
    for key,o in list(gs.orders.items()):
        if o["side"]=="LONG" and float(row.low)<=o["price"]:
            fills.append((key,o))
        elif o["side"]=="SHORT" and float(row.high)>=o["price"]:
            fills.append((key,o))
    for key,o in fills:
        # If both long and short orders somehow coexist, only fill the active direction.
        if gs.direction and o["side"]!=gs.direction: continue
        old_qty=gs.position_qty
        new_qty=o["qty"]
        if old_qty<=0:
            gs.direction=o["side"]; gs.avg_entry=o["price"]; gs.position_qty=new_qty
        else:
            if o["side"]!=gs.direction: continue
            gs.avg_entry=(gs.avg_entry*old_qty+o["price"]*new_qty)/(old_qty+new_qty); gs.position_qty=old_qty+new_qty
        gs.filled_levels.add(key); gs.orders.pop(key,None); fills.append
    return fills

def _grid_update_protection(gs,cfg):
    if gs.position_qty<=0: gs.tp=None; gs.sl=None; return
    side=gs.direction; gs.tp=gs.avg_entry*(1+float(cfg["grid_tp"])/100) if side=="LONG" else gs.avg_entry*(1-float(cfg["grid_tp"])/100)
    gs.sl=gs.center*(1-float(cfg["grid_sl"])/100) if side=="LONG" else gs.center*(1+float(cfg["grid_sl"])/100)

def _grid_exit_bar(gs,row,cfg):
    if gs.position_qty<=0: return None,0.0
    side=gs.direction; high=float(row.high); low=float(row.low)
    slhit=(low<=gs.sl) if side=="LONG" else (high>=gs.sl)
    tphit=(high>=gs.tp) if side=="LONG" else (low<=gs.tp)
    if slhit:
        px=_slip_price(gs.sl,side,float(cfg["slippage_pct"])/100,entry=False) if cfg["slippage_exit"] else gs.sl
        raw=(px-gs.avg_entry)/gs.avg_entry if side=="LONG" else (gs.avg_entry-px)/gs.avg_entry
        gross=gs.avg_entry*gs.position_qty*raw; fee=_trade_fee(gs.avg_entry*gs.position_qty,cfg)+_trade_fee(px*gs.position_qty,cfg)
        net=gross-fee; gs.position_qty=0; gs.avg_entry=0; gs.tp=gs.sl=None; return "GRID_SL",net
    if tphit:
        px=_slip_price(gs.tp,side,float(cfg["slippage_pct"])/100,entry=False) if cfg["slippage_exit"] else gs.tp
        raw=(px-gs.avg_entry)/gs.avg_entry if side=="LONG" else (gs.avg_entry-px)/gs.avg_entry
        gross=gs.avg_entry*gs.position_qty*raw; fee=_trade_fee(gs.avg_entry*gs.position_qty,cfg)+_trade_fee(px*gs.position_qty,cfg)
        net=gross-fee; gs.position_qty=0; gs.avg_entry=0; gs.tp=gs.sl=None; return "GRID_TP",net
    return None,0.0

def _grid_close(gs,price,cfg,reason):
    if gs.position_qty<=0: return 0.0
    side=gs.direction; px=_slip_price(price,side,float(cfg["slippage_pct"])/100,entry=False) if cfg["slippage_exit"] else price
    raw=(px-gs.avg_entry)/gs.avg_entry if side=="LONG" else (gs.avg_entry-px)/gs.avg_entry
    gross=gs.avg_entry*gs.position_qty*raw; fee=_trade_fee(gs.avg_entry*gs.position_qty,cfg)+_trade_fee(px*gs.position_qty,cfg)
    net=gross-fee; gs.position_qty=0; gs.avg_entry=0; gs.tp=gs.sl=None; return net

def run_backtest(df,cfg,logger=None):
    cfg=validate_config(cfg)
    initial=float(cfg["capital"]); equity=initial
    start=max(3,int(cfg["warmup"])); end=len(df)-2
    trades=[]; events=[]; equity_points=[]; pos=None; lock=None; last_entry_i=None; last_flat_i=-10**9
    daily_start=initial; daily_day=None; stopped_reason="END"; completed_trades=0
    grid=GridState(mode=cfg["grid_mode"],session_start_balance=initial,peak_equity=initial,started_bar=start)
    def log(msg):
        if logger: logger(msg)
        events.append(str(msg))
    def finalize_normal(reason,row,price):
        nonlocal pos,equity,last_flat_i,lock,completed_trades
        if not pos: return
        p=finalize_trade(pos,row.datetime,reason,price); trades.append(p); completed_trades+=1
        exited_side=p["side"]; pos=None; last_flat_i=cur_i
        if reason in ("SL","SL_BE","UNKNOWN") and cfg["require_opposite_after_sl"]:
            lock=exited_side
        elif reason not in ("TP1",):
            lock=None
    for cur_i in range(start,end+1):
        row=df.iloc[cur_i]
        day=pd.Timestamp(row.datetime).date()
        if daily_day!=day:
            daily_day=day; daily_start=equity

        # Global emergency stop uses adverse intrabar mark-to-market.
        unreal=0.0
        if pos:
            adverse=float(row.low) if pos["side"]=="LONG" else float(row.high)
            raw=((adverse-pos["entry"])/pos["entry"] if pos["side"]=="LONG" else (pos["entry"]-adverse)/pos["entry"])
            unreal=pos["remaining_qty"]*pos["entry"]*raw + pos.get("realized_net",0.0)
        elif grid.position_qty>0:
            adverse=float(row.low) if grid.direction=="LONG" else float(row.high)
            raw=((adverse-grid.avg_entry)/grid.avg_entry if grid.direction=="LONG" else (grid.avg_entry-adverse)/grid.avg_entry)
            unreal=grid.position_qty*grid.avg_entry*raw
        mark_equity=equity+unreal
        if float(cfg["emergency_capital_pct"])>0 and mark_equity <= initial*(1-float(cfg["emergency_capital_pct"])/100):
            if pos:
                px=float(row.low if pos["side"]=="LONG" else row.high)
                _close_piece(pos,pos["remaining_qty"],px,cfg,"EMERGENCY"); equity+=pos.get("realized_net",0.0); finalize_normal("EMERGENCY",row,px)
            if grid.position_qty>0:
                equity+=_grid_close(grid,float(row.low if grid.direction=="LONG" else row.high),cfg,"EMERGENCY")
                grid.active=False
            stopped_reason="EMERGENCY_CAPITAL_LOSS"; break
        if float(cfg["max_dd"])>0 and daily_start>0 and (daily_start-equity)/daily_start >= float(cfg["max_dd"])/100:
            if pos:
                px=float(row.close); _close_piece(pos,pos["remaining_qty"],px,cfg,"DAILY_DRAWDOWN"); equity+=pos.get("realized_net",0.0); finalize_normal("DAILY_DRAWDOWN",row,px)
            if grid.position_qty>0:
                equity+=_grid_close(grid,float(row.close),cfg,"DAILY_DRAWDOWN")
                grid.active=False
            stopped_reason="DAILY_DRAWDOWN"; break

        # Existing normal position: exchange-side protection.
        if pos:
            before_real=pos.get("realized_net",0.0)
            events_bar,closed,_=simulate_position_bar(pos,row,cfg)
            delta=pos.get("realized_net",0.0)-before_real
            if delta: equity+=delta
            for reason,q,px in events_bar:
                events.append(f"{row.datetime} {pos['side']} {reason} qty={q:g} price={px:.8g}")
            if closed:
                reason=events_bar[-1][0] if events_bar else "UNKNOWN"
                px=events_bar[-1][2] if events_bar else None
                finalize_normal(reason,row,px)
                if completed_trades>=int(cfg["max_trades"])>0:
                    stopped_reason="MAX_TRADES"; break
                continue

        # Strategy signal on the completed candle.
        sig,votes,bs,ss,reason=signal_for_bar(df,cur_i,cfg)
        side_signal="LONG" if sig=="BUY" else "SHORT" if sig=="SELL" else "NONE"
        pvotes=persistent_votes(df,cur_i,cfg)

        # Normal strategy: reversal / legacy opposite exit.
        if pos and side_signal in ("LONG","SHORT") and side_signal!=pos["side"]:
            reversal_allowed=not bool(cfg["hold_until_all_reverse"])
            if cfg["hold_until_all_reverse"]:
                reversal_allowed=all_reverse(pvotes,pos["side"])
                if cfg["hold_sl_wait_reversal"] and not pos["hold_threshold_hit"]:
                    reversal_allowed=False
            if cfg["exit_on_opposite"] and not cfg["hold_until_all_reverse"]:
                reversal_allowed=True
            if reversal_allowed:
                nxt=df.iloc[cur_i+1]
                px=_slip_price(float(nxt.open),pos["side"],float(cfg["slippage_pct"])/100,entry=False) if cfg["slippage_exit"] else float(nxt.open)
                before=pos.get("realized_net",0.0)
                _close_piece(pos,pos["remaining_qty"],px,cfg,"REVERSAL")
                equity+=pos.get("realized_net",0.0)-before
                finalize_normal("REVERSAL",nxt,px)
                # Strategy reversal deliberately clears the post-SL lock.
                lock=None
                if completed_trades>=int(cfg["max_trades"])>0:
                    stopped_reason="MAX_TRADES"; break

        if cfg["grid_mode"] in ("OFF","DIRECT_SHOT") and pos is None and side_signal in ("LONG","SHORT"):
            side=side_signal
            if lock==side:
                # Same-side re-entry remains blocked until a valid opposite signal.
                continue
            if lock in ("LONG","SHORT") and side != lock:
                lock=None
            if cfg["no_same_candle"] and last_entry_i==cur_i:
                continue
            if cfg["cooldown_min"]>0 and (cur_i-last_flat_i)*TIMEFRAMES[cfg["tf"]] < float(cfg["cooldown_min"])*60*1000:
                continue
            nxt=df.iloc[cur_i+1]
            entry=_slip_price(float(nxt.open),side,float(cfg["slippage_pct"])/100,entry=True)
            pos=_normal_position_from_entry(entry,side,equity,cfg)
            pos["signal_time"]=str(row.datetime); pos["entry_time"]=str(nxt.datetime); pos["entry_candle"]=cur_i+1
            pos["signal_reason"]=reason; pos["signal_score"]=f"B{bs}/S{ss}"; last_entry_i=cur_i
            if not pos["hold_wait"] and cfg["tp_qty_mode"]=="FIXED_QTY": _tp_qtys(pos["qty"],cfg)
            # Entry candle protection starts after next-open fill.
            before_real=pos.get("realized_net",0.0)
            events_entry,closed,_=simulate_position_bar(pos,nxt,cfg)
            delta=pos.get("realized_net",0.0)-before_real
            if delta: equity+=delta
            for r,q,px in events_entry: events.append(f"{nxt.datetime} {side} {r} qty={q:g} price={px:.8g}")
            if closed:
                reason2=events_entry[-1][0] if events_entry else "UNKNOWN"; px2=events_entry[-1][2] if events_entry else None
                finalize_normal(reason2,nxt,px2)
                if completed_trades>=int(cfg["max_trades"])>0:
                    stopped_reason="MAX_TRADES"; break

        # GRID ENGINE.
        if cfg["grid_mode"] not in ("OFF","DIRECT_SHOT"):
            if not grid.active:
                grid.active=True; grid.center=float(row.close); grid.started_bar=cur_i; grid.session_start_balance=equity; grid.peak_equity=equity
                log(f"{row.datetime} GRID START mode={grid.mode} center={grid.center:.8g}")

            grid.peak_equity=max(grid.peak_equity,equity)
            gstart=max(grid.session_start_balance,1e-12); gpeak=max(grid.peak_equity,1e-12)
            if max((gstart-equity)/gstart,(gpeak-equity)/gpeak,0)>=float(cfg["grid_max_dd"])/100:
                if grid.position_qty>0:
                    equity+=_grid_close(grid,float(df.iloc[cur_i+1].open),cfg,"GRID_DD")
                grid.orders={}; grid.filled_levels=set(); grid.active=False; stopped_reason="GRID_MAX_DD"
                log(f"{row.datetime} GRID STOP: Grid DD limit reached")
                continue

            st_bull=bool(row.trend) if cfg["use_st"] and "trend" in df.columns else False
            st_bear=not st_bull if cfg["use_st"] and "trend" in df.columns else False
            direction=_grid_direction(cfg,votes,st_bull,st_bear) if cfg["grid_mode"]=="NEUTRAL_GRID" else ("LONG" if cfg["grid_mode"]=="LONG_GRID" else "SHORT")
            allow_long=allow_short=True
            if cfg["grid_trend_filter"]=="SUPERTREND":
                allow_long,allow_short=st_bull,st_bear
            elif cfg["grid_trend_filter"]=="SCORE":
                need=float(cfg["grid_score_min"]); need=max(need,float(cfg.get("adaptive_min_weight",ADAPTIVE_DEFAULT_MIN_WEIGHT))) if cfg.get("signal_mode")=="ADAPTIVE_SCORE" else need; allow_long=bs>=need and bs>ss; allow_short=ss>=need and ss>bs

            if cfg["grid_mode"]=="NEUTRAL_GRID":
                if direction!=grid.direction:
                    grid.orders={}
                    if grid.position_qty>0 and direction in ("LONG","SHORT") and direction!=grid.direction:
                        nxt=df.iloc[cur_i+1]
                        equity+=_grid_close(grid,float(nxt.open),cfg,"NEUTRAL_SWITCH")
                        grid.filled_levels=set()
                    grid.direction=direction
                    if direction: grid.center=float(df.iloc[cur_i+1].open)
                if direction=="LONG": allow_long,allow_short=True,False
                elif direction=="SHORT": allow_long,allow_short=False,True
                else: allow_long=allow_short=False

            if cfg["grid_recenter"] and grid.position_qty<=0 and grid.center>0 and abs(float(row.close)-grid.center)/grid.center >= float(cfg["grid_recenter_distance"])/100:
                grid.orders={}; grid.center=float(df.iloc[cur_i+1].open)

            for key,o in list(grid.orders.items()):
                if (o["side"]=="LONG" and not allow_long) or (o["side"]=="SHORT" and not allow_short):
                    grid.orders.pop(key,None)
            _grid_place_orders(grid,cfg,allow_long,allow_short)

            nxt=df.iloc[cur_i+1]
            # Existing basket protection is evaluated before new limit fills.
            if grid.position_qty>0:
                rg,ng=_grid_exit_bar(grid,nxt,cfg)
                if rg:
                    side_before=grid.direction; entry_before=grid.avg_entry; exit_time=str(nxt.datetime)
                    equity+=ng; trades.append({"symbol":cfg.get("symbol",""),"strategy":"GRID","side":side_before,
                        "signal_time":str(row.datetime),"entry_time":str(row.datetime),"exit_time":exit_time,
                        "entry":entry_before,"exit_price":grid.avg_entry if grid.avg_entry else np.nan,
                        "reason":rg,"gross_pnl":ng,"fees":0.0,"net_pnl":ng})
                    completed_trades+=1
                    grid.filled_levels=set(); grid.orders={}; grid.direction=None
                    if completed_trades>=int(cfg["max_trades"])>0:
                        stopped_reason="MAX_TRADES"; break

            _grid_fill_orders(grid,nxt,cfg)
            _grid_update_protection(grid,cfg)
            if grid.position_qty*grid.avg_entry>float(cfg["grid_max_exposure"]):
                ng=_grid_close(grid,float(nxt.close),cfg,"GRID_MAX_EXPOSURE"); equity+=ng
                trades.append({"symbol":cfg.get("symbol",""),"strategy":"GRID","side":"GRID","signal_time":str(row.datetime),
                    "entry_time":str(row.datetime),"exit_time":str(nxt.datetime),"entry":np.nan,"exit_price":float(nxt.close),
                    "reason":"GRID_MAX_EXPOSURE","gross_pnl":ng,"fees":0.0,"net_pnl":ng}); completed_trades+=1
                grid.orders={}; grid.filled_levels=set(); grid.direction=None
            if grid.position_qty<=0: grid.filled_levels=set()
            if completed_trades>=int(cfg["max_trades"])>0:
                stopped_reason="MAX_TRADES"; break

        equity_points.append({"datetime":row.datetime,"equity":equity,"mark_equity":mark_equity})

    # End-of-data flattening.
    if pos:
        last=df.iloc[-1]; before=pos.get("realized_net",0.0); _close_piece(pos,pos["remaining_qty"],float(last.close),cfg,"END"); equity+=pos.get("realized_net",0.0)-before
        p=finalize_trade(pos,last.datetime,"END",float(last.close)); trades.append(p)
    if grid.position_qty>0:
        last=df.iloc[-1]; ng=_grid_close(grid,float(last.close),cfg,"END"); equity+=ng
        trades.append({"symbol":cfg.get("symbol",""),"strategy":"GRID","side":grid.direction or "GRID","signal_time":str(last.datetime),
            "entry_time":str(last.datetime),"exit_time":str(last.datetime),"entry":grid.avg_entry,"exit_price":float(last.close),
            "reason":"END","gross_pnl":ng,"fees":0.0,"net_pnl":ng})
    eq=[x["equity"] for x in equity_points]
    metrics=calc_metrics(trades,initial,eq)
    metrics["stopped_reason"]=stopped_reason; metrics["ending_equity"]=equity
    return trades,metrics,pd.DataFrame(equity_points),events


def monthly_stats(trades):
    if not trades: return pd.DataFrame()
    d=pd.DataFrame(trades)
    if "exit_time" not in d: return pd.DataFrame()
    d["month"]=pd.to_datetime(d["exit_time"],utc=True).dt.strftime("%Y-%m")
    return d.groupby("month").agg(trades=("net_pnl","size"),net_pnl=("net_pnl","sum"),wins=("net_pnl",lambda s:int((s>0).sum())),losses=("net_pnl",lambda s:int((s<=0).sum()))).reset_index()

def parse_list(text,cast=float):
    out=[]
    for x in str(text).replace("; ",",").split(","):
        x=x.strip()
        if not x: continue
        out.append(cast(x))
    return out

def make_param_grid(base,fields,max_configs=250):
    keys=[]; vals=[]
    for key,text,cast in fields:
        v=parse_list(text,cast)
        if not v: continue
        if len(v)>1 or v[0]!=base[key]: keys.append(key); vals.append(v)
    if not keys:return [base.copy()]
    combos=[]
    for p in itertools.product(*vals):
        combos.append({**base,**dict(zip(keys,p))})
        if len(combos)>=max_configs: break
    return combos

def strategy_combinations(selected, one=True,two=True,three=True,four=True):
    out=[]
    for k,flag in [(1,one),(2,two),(3,three),(4,four)]:
        if flag and len(selected)>=k: out += list(itertools.combinations(selected,k))
    return out



class BacktesterGUI:
    def __init__(self,root):
        self.root=root; self.root.title(APP_TITLE); self.root.geometry("1500x950"); self.root.minsize(1100,700)
        self.vars={}; self.entries={}; self.running=False; self.stop_flag=False; self.last_results=[]
        self.defaults=dict(DEFAULTS)
        self._build()
    def sv(self,k,default=None):
        if k not in self.vars: self.vars[k]=tk.StringVar(value=str(self.defaults.get(k,default)))
        return self.vars[k]
    def bv(self,k,default=False):
        if k not in self.vars: self.vars[k]=tk.BooleanVar(value=bool(self.defaults.get(k,default)))
        return self.vars[k]
    def ent(self,parent,k,label,row,col,width=10):
        ttk.Label(parent,text=label).grid(row=row,column=col,sticky="e",padx=3,pady=2)
        e=ttk.Entry(parent,textvariable=self.sv(k),width=width); e.grid(row=row,column=col+1,sticky="w",padx=3,pady=2); self.entries[k]=e; return e
    def combo(self,parent,k,label,vals,row,col,width=16):
        ttk.Label(parent,text=label).grid(row=row,column=col,sticky="e",padx=3,pady=2)
        c=ttk.Combobox(parent,textvariable=self.sv(k),values=vals,state="readonly",width=width); c.grid(row=row,column=col+1,sticky="w",padx=3,pady=2); return c
    def check(self,parent,k,label,row,col):
        ttk.Checkbutton(parent,text=label,variable=self.bv(k)).grid(row=row,column=col,sticky="w",padx=4,pady=2)
    def _build(self):
        nb=ttk.Notebook(self.root); nb.pack(fill="both",expand=True,padx=6,pady=6)
        self.tabs={}
        for name in ["Market","Strategy","Grid","Risk / SL-TP","Sweep / Walk-Forward","Results"]:
            f=ttk.Frame(nb); nb.add(f,text=name); self.tabs[name]=f
        self._build_market(); self._build_strategy(); self._build_grid(); self._build_risk(); self._build_sweep(); self._build_results()
    def _build_market(self):
        p=self.tabs["Market"]; f=ttk.LabelFrame(p,text="Market / Data"); f.pack(fill="x",padx=8,pady=8)
        self.combo(f,"exchange","Exchange",list(SUPPORTED_EXCHANGES),0,0)
        self.ent(f,"symbols","Symbols",0,2,28); self.combo(f,"tf","Timeframe",list(TIMEFRAMES),0,4)
        self.ent(f,"start","Start UTC",0,6,12); self.ent(f,"end","End UTC",0,8,12)
        self.ent(f,"capital","Initial Capital",1,0); self.ent(f,"leverage","Leverage",1,2)
        self.ent(f,"warmup","Warmup Candles",1,4); self.check(f,"no_same_candle","No Re-Entry Same Candle",1,6)
        self.ent(f,"cooldown_min","Cooldown (min)",2,0); self.ent(f,"max_trades","Max Trades (0=unlimited)",2,2)
        ttk.Label(f,text="Signal is evaluated on a completed candle; normal entry is simulated at the next candle OPEN.").grid(row=3,column=0,columnspan=10,sticky="w",padx=4,pady=4)
        ttk.Button(f,text="Load V8 Bot Config JSON",command=self.import_config).grid(row=4,column=0,columnspan=2,sticky="w",padx=4,pady=4)
        ttk.Button(f,text="Save Backtest Config JSON",command=self.export_config).grid(row=4,column=2,columnspan=2,sticky="w",padx=4,pady=4)
    def _build_strategy(self):
        p=self.tabs["Strategy"]; top=ttk.Frame(p); top.pack(fill="x",padx=8,pady=6)
        lf=ttk.LabelFrame(top,text="19 Directional Modules — V8.3.0 participation"); lf.pack(fill="x")
        for i,m in enumerate(MODULES):
            self.check(lf,"use_"+m,m,i//6,(i%6)*2)
        sf=ttk.LabelFrame(p,text="Signal Engine"); sf.pack(fill="x",padx=8,pady=6)
        self.combo(sf,"signal_mode","Signal Mode",list(SUPPORTED_SIGNAL_MODES),0,0,24); self.ent(sf,"min_score","Minimum Score",0,2); self.ent(sf,"adaptive_edge","Adaptive Edge",1,0); self.ent(sf,"adaptive_min_weight","Adaptive Min Weight",1,2)
        self.check(sf,"hold_until_all_reverse","Hold-All-Reverse",1,0); self.check(sf,"require_opposite_after_sl","Require Opposite After SL/Unknown",1,2)
        ttk.Label(sf,text="Combination Lab:").grid(row=2,column=0,sticky="e",padx=3)
        self.bv("combo_one",True); self.bv("combo_two",True); self.bv("combo_three",True); self.bv("combo_four",True)
        for j,(k,lbl) in enumerate([("combo_one","1-way"),("combo_two","2-way"),("combo_three","3-way"),("combo_four","4-way")]):
            ttk.Checkbutton(sf,text=lbl,variable=self.vars[k]).grid(row=2,column=1+j,sticky="w",padx=3)
        ip=ttk.LabelFrame(p,text="Indicator Settings / Entry Modes"); ip.pack(fill="x",padx=8,pady=6)
        rows=[
            ("st_len","ST ATR Period"),("st_mult","ST Multiplier"),("ema_len","EMA Filter Period"),("ema_fast","EMA Cross Fast"),("ema_slow","EMA Cross Slow"),
            ("macd_fast","MACD Fast"),("macd_slow","MACD Slow"),("macd_signal","MACD Signal"),("rsi_len","RSI Period"),("rsi_ob","RSI OB"),("rsi_os","RSI OS"),("rsi_ma_len","RSI MA Period"),
            ("bb_len","BB Period"),("bb_std","BB Std"),("stoch_k","Stoch K"),("stoch_smooth","Stoch Smooth"),("stoch_d","Stoch D"),("vwap_len","VWAP Period"),
            ("vwap_delta_smooth_len","VWAP Delta Smooth"),("vwap_delta_baseline","VWAP Delta Baseline"),("vidya_len","VIDYA Length"),("vidya_momentum","VIDYA Momentum"),("vidya_band","VIDYA Band"),
            ("nwe_bandwidth","NWE Bandwidth"),("nwe_mult","NWE Mult"),("liq_length","Liquidity Length"),("liq_filter_value","Liquidity Filter Value"),
            ("trendline_length","Trendline Length"),("trendline_min_distance","Trendline Min Distance"),("trendline_buffer","Trendline Buffer %"),("trendline_retest_candles","Trendline Retest Candles"),
            ("atr_min_pct","ATR Minimum %"),("vol_len","Volume MA"),("adx_thresh","ADX Threshold")
        ]
        for i,(k,l) in enumerate(rows): self.ent(ip,k,l,i//8,(i%8)*2,10)
        opts=[
            ("st_source","ST Source",["CLOSE","HL2"]),("st_change_atr","ST Change ATR",[True,False]),("st_entry_mode","ST Entry",["FRESH_FLIP","CURRENT_TREND"]),
            ("ema_cross_entry_mode","EMA Cross Entry",["FRESH_CROSS","CURRENT_TREND"]),("rsi_logic","RSI Logic",["REVERSAL_ZONE","CROSS_MA","EITHER"]),("rsi_ma_type","RSI MA",["EMA","SMA","WMA"]),
            ("vwap_delta_logic","VWAP Delta Logic",["CURRENT_TREND","CROSS_BASELINE"]),("vidya_entry_mode","VIDYA Entry",["CURRENT_TREND","FRESH_FLIP"]),
            ("nwe_entry_mode","NWE Entry",["FRESH_CROSS","CURRENT_TREND"]),("liq_area","Liquidity Area",["Wick Extremity","Full Range"]),("liq_filter","Liquidity Filter",["Count","Volume"]),
            ("liq_entry_mode","Liquidity Entry",["FRESH_BREAK","CURRENT_TREND"]),("trendline_entry_mode","Trendline Entry",["FRESH_BREAK","CURRENT_TREND","BREAK_RETEST"]),
            ("vwap_delta_smooth","VWAP Delta HMA Smoothing",[True,False])
        ]
        rr=5
        for i,(k,l,vals) in enumerate(opts): self.combo(ip,k,l,[str(v) for v in vals],rr+i//4,(i%4)*4,18)
        ttk.Label(ip,text="NWE repaint is always OFF in live V8.2.4. Backtester uses causal/non-repainting NWE with live 500-bar lookback and 499-bar MAE.").grid(row=rr+4,column=0,columnspan=12,sticky="w",padx=4,pady=3)

        adv=ttk.LabelFrame(p,text="Advanced Modules — Divergence + Volume S/R Zones"); adv.pack(fill="x",padx=8,pady=6)
        self.check(adv,"use_divergence","Divergence Engine",0,0)
        self.ent(adv,"div_pivot","Pivot",0,2,7); self.combo(adv,"div_source","Source",["Close","High/Low"],0,4,12)
        self.combo(adv,"div_type","Divergence Type",["Regular","Hidden","Regular/Hidden"],0,6,18)
        self.ent(adv,"div_min_count","Min Divergence",0,8,10); self.ent(adv,"div_max_pivots","Max Pivots",0,10,10)
        self.ent(adv,"div_max_bars","Max Bars",1,0,10); self.ent(adv,"div_cci_len","CCI",1,2,7); self.ent(adv,"div_mom_len","Momentum",1,4,9)
        self.combo(adv,"div_entry_mode","Entry",["FRESH","CURRENT_STATE"],1,6,16)
        divopts=[("div_use_macd","MACD"),("div_use_macd_hist","Hist"),("div_use_rsi","RSI"),("div_use_stoch","Stoch"),("div_use_cci","CCI"),
                 ("div_use_momentum","MOM"),("div_use_obv","OBV"),("div_use_vwmacd","VWMACD"),("div_use_cmf","CMF"),("div_use_mfi","MFI")]
        for j,(k,l) in enumerate(divopts): self.check(adv,k,l,2+(j//5),(j%5)*2)
        self.check(adv,"use_vol_sr","Volume S/R Zones",4,0)
        self.combo(adv,"sr_vote_mode","Vote",["MAJORITY","ANY","ALL"],4,2,14)
        self.combo(adv,"sr_entry_mode","Entry",["CURRENT_ZONE","FRESH_BREAK"],4,4,16)
        self.ent(adv,"sr_volume_ma","Vol MA Threshold",4,6,10); self.ent(adv,"sr_history_bars","SR History Bars",4,8,10)
        for j,(k,l) in enumerate([("sr_tf1","TF1"),("sr_tf2","TF2"),("sr_tf3","TF3"),("sr_tf4","TF4")]):
            self.combo(adv,k,l,["Chart","15m","30m","1h","4h","D","W","Disable"],5,j*2,12)
        ttk.Label(adv,text="Numerical port of the supplied TradingView scripts: chart drawings/alerts are not used as execution signals; only confirmed causal divergence and volume-fractal S/R states are traded.").grid(row=6,column=0,columnspan=12,sticky="w",padx=4,pady=3)

    def _build_grid(self):
        p=self.tabs["Grid"]; f=ttk.LabelFrame(p,text="Grid Engine — same V8.2.4 Grid contract"); f.pack(fill="x",padx=8,pady=8)
        self.combo(f,"grid_mode","Grid Mode",list(SUPPORTED_GRID_MODES),0,0,20); self.combo(f,"grid_trend_filter","Trend Filter",["OFF","SUPERTREND","SCORE"],0,2,16)
        for i,(k,l) in enumerate([("grid_levels","Levels"),("grid_spacing","Spacing %"),("grid_order_size","Order Size USDT"),("grid_size_increase","Size Increase %"),("grid_tp","Basket TP %"),("grid_sl","Global SL %"),("grid_max_exposure","Max Exposure USDT"),("grid_max_dd","Grid Max DD %"),("grid_score_min","Grid Score Min"),("grid_recenter_distance","Recenter Distance %"),("grid_cooldown","Cooldown min")]):
            self.ent(f,k,l,1+i//6,(i%6)*2,11)
        self.check(f,"grid_recenter","Grid Recenter",3,0)
        ttk.Label(f,text="NEUTRAL_GRID: SUPERTREND follows ST; SCORE/OFF uses the complete 17-module strategy score. Direction changes cancel old pending entries and close opposite Grid inventory before rebuilding.").grid(row=4,column=0,columnspan=12,sticky="w",padx=4,pady=4)
    def _build_risk(self):
        p=self.tabs["Risk / SL-TP"]; f=ttk.LabelFrame(p,text="Normal Strategy Sizing / Global Safety"); f.pack(fill="x",padx=8,pady=6)
        self.combo(f,"size_mode","Sizing Mode",["EQUITY_RISK_%","FIXED_QTY"],0,0,18); self.ent(f,"risk_pct","Risk / Trade %",0,2); self.ent(f,"fixed_qty","Fixed Qty",0,4)
        self.ent(f,"max_dd","Max Daily DD %",1,0); self.ent(f,"emergency_capital_pct","Emergency Capital Loss %",1,2)
        s=ttk.LabelFrame(p,text="Normal Strategy SL / TP"); s.pack(fill="x",padx=8,pady=6)
        self.combo(s,"sl_mode","SL Mode",["PRICE_%","ROI_%"],0,0); self.combo(s,"tp_mode","TP Mode",["PRICE_%","ROI_%"],0,2)
        self.ent(s,"sl_pct","SL Target %",1,0); self.ent(s,"tp1_pct","TP1 Target %",1,2); self.ent(s,"tp2_pct","TP2 Target %",1,4)
        self.ent(s,"hold_sl_roi","Hold-All-Reverse SL ROI %",2,0); self.combo(s,"tp_qty_mode","TP Close Mode",["PERCENT_%","FIXED_QTY"],2,2)
        self.ent(s,"tp1_close","TP1 Close % / Qty",3,0); self.ent(s,"tp2_close","TP2 Close % / Qty",3,2)
        self.check(s,"tp1_be","Move SL to Break-Even after TP1",4,0); self.check(s,"hold_sl_wait_reversal","After Hold-SL threshold WAIT for ALL active signals to reverse",5,0)
        e=ttk.LabelFrame(p,text="Backtest Execution Model"); e.pack(fill="x",padx=8,pady=6)
        self.ent(e,"fee_pct","Fee % / side",0,0); self.ent(e,"slippage_pct","Slippage %",0,2); self.check(e,"slippage_exit","Apply slippage on exits",0,4); self.check(e,"exit_on_opposite","Legacy Opposite-Signal Exit",1,0)
        ttk.Label(e,text="Live V8.2.4 does not use funding in its local PnL engine, so this backtester does not invent funding. SL wins when SL+TP are both touched in one candle.").grid(row=2,column=0,columnspan=8,sticky="w",padx=4,pady=3)
    def _build_sweep(self):
        p=self.tabs["Sweep / Walk-Forward"]; f=ttk.LabelFrame(p,text="Parameter Sweep — comma-separated values"); f.pack(fill="x",padx=8,pady=8)
        fields=[("sweep_ema_fast","EMA Cross Fast","int"),("sweep_ema_slow","EMA Cross Slow","int"),("sweep_rsi_len","RSI Period","int"),("sweep_st_len","ST ATR","int"),("sweep_st_mult","ST Mult","float"),("sweep_sl_pct","SL Target","float"),("sweep_tp1_pct","TP1 Target","float"),("sweep_tp2_pct","TP2 Target","float")]
        for i,(k,l,t) in enumerate(fields):
            if k not in self.defaults:self.defaults[k]=self.defaults.get({"sweep_rsi_len":"rsi_len","sweep_sl_pct":"sl_pct","sweep_tp1_pct":"tp1_pct","sweep_tp2_pct":"tp2_pct"}.get(k,k),1)
            self.sv(k,self.defaults[k]); self.ent(f,k,l, i//4,(i%4)*2,16)
        self.ent(f,"max_configs","Max Configurations",2,0,12); self.ent(f,"wf_split","Walk-Forward IS %",2,2,12); self.ent(f,"top_n","Walk-Forward Top N",2,4,12)
        ttk.Label(f,text="Walk-forward optimizes only on IS and evaluates selected configuration(s) on untouched OOS. Results include both IS and OOS metrics.").grid(row=3,column=0,columnspan=10,sticky="w",padx=4,pady=4)
    def _build_results(self):
        p=self.tabs["Results"]; b=ttk.Frame(p); b.pack(fill="x",padx=8,pady=5)
        self.start_btn=ttk.Button(b,text="START BACKTEST",command=lambda:self.launch("backtest")); self.start_btn.pack(side="left",padx=3)
        self.sweep_btn=ttk.Button(b,text="RUN SWEEP",command=lambda:self.launch("sweep")); self.sweep_btn.pack(side="left",padx=3)
        self.wf_btn=ttk.Button(b,text="RUN WALK-FORWARD",command=lambda:self.launch("walkforward")); self.wf_btn.pack(side="left",padx=3)
        self.combo_btn=ttk.Button(b,text="RUN COMBINATION LAB",command=lambda:self.launch("combinations")); self.combo_btn.pack(side="left",padx=3)
        ttk.Button(b,text="STOP",command=self.stop).pack(side="left",padx=3); self.status=tk.StringVar(value="Ready"); ttk.Label(b,textvariable=self.status).pack(side="left",padx=12)
        self.logbox=tk.Text(p,height=18); self.logbox.pack(fill="both",expand=True,padx=8,pady=5)
        self.tree=ttk.Treeview(p,columns=("symbol","mode","trades","win","pnl","ret","pf","dd"),show="headings")
        for c,w in zip(self.tree["columns"],[130,170,80,70,110,90,90,110]): self.tree.heading(c,text=c.upper()); self.tree.column(c,width=w)
        self.tree.pack(fill="x",padx=8,pady=5)
    def log(self,msg):
        def write():
            self.logbox.insert("end",str(msg)+"\n"); self.logbox.see("end")
        try:self.root.after(0,write)
        except Exception: pass
    def stop(self): self.stop_flag=True; self.log("STOP requested.")
    def cfg(self):
        c=dict(DEFAULTS)
        for k,v in self.vars.items():
            if isinstance(v,tk.BooleanVar): c[k]=bool(v.get())
            else:
                val=v.get()
                if k in {"st_len","ema_len","ema_fast","ema_slow","macd_fast","macd_slow","macd_signal","rsi_len","rsi_ob","rsi_os","rsi_ma_len","bb_len","stoch_k","stoch_smooth","stoch_d","vwap_len","vwap_delta_smooth_len","vwap_delta_baseline","vidya_len","vidya_momentum","nwe_lookback","nwe_mae","liq_length","trendline_length","trendline_min_distance","trendline_retest_candles","vol_len","leverage","warmup","max_trades","grid_levels","min_score",
                     "div_pivot","div_min_count","div_max_pivots","div_max_bars","div_cci_len","div_mom_len","sr_volume_ma","sr_history_bars"}:
                    try:c[k]=int(val)
                    except: pass
                elif k in {"st_mult","ema_fast","ema_slow","macd_fast","macd_slow","macd_signal","bb_std","vwap_delta_smooth_len","vwap_delta_baseline","vidya_band","nwe_bandwidth","nwe_mult","liq_filter_value","trendline_buffer","atr_min_pct","adx_thresh","risk_pct","fixed_qty","max_dd","emergency_capital_pct","sl_pct","tp1_pct","tp2_pct","hold_sl_roi","tp1_close","tp2_close","grid_spacing","grid_order_size","grid_size_increase","grid_tp","grid_sl","grid_max_exposure","grid_max_dd","grid_recenter_distance","grid_cooldown","fee_pct","slippage_pct","cooldown_min","capital","adaptive_edge","adaptive_min_weight"}:
                    try:c[k]=float(val)
                    except: pass
                else:c[k]=val
        # alias backtester fields
        return validate_config(c)
    def export_config(self):
        try:
            cfg=self.cfg()
            path=filedialog.asksaveasfilename(
                title="Save Backtest Config",
                defaultextension=".json",
                filetypes=[("JSON","*.json")]
            )
            if not path: return
            import json
            with open(path,"w",encoding="utf-8") as f: json.dump(cfg,f,indent=2)
            self.log(f"CONFIG SAVED: {path}")
        except Exception as e:
            messagebox.showerror("Save Config",str(e))

    def import_config(self):
        path=filedialog.askopenfilename(
            title="Load V8 Bot / Backtest Config",
            filetypes=[("JSON","*.json"),("All files","*.*")]
        )
        if not path: return
        try:
            import json
            with open(path,"r",encoding="utf-8") as f: data=json.load(f)
            if not isinstance(data,dict): raise ValueError("Config JSON must contain an object.")
            known=set(self.defaults)
            # Import live V8 config keys directly. Unknown keys are ignored so
            # runtime credentials/profile/recovery fields do not enter the
            # historical simulator.
            for k,v in data.items():
                if k in known and k in self.vars:
                    var=self.vars[k]
                    if isinstance(var,tk.BooleanVar): var.set(bool(v))
                    else: var.set(str(v))
            self.log(f"CONFIG LOADED: {path}")
        except Exception as e:
            messagebox.showerror("Load Config",str(e))

    def run_combinations(self,sym,df,base):
        selected=[m for m in MODULES if bool(base.get("use_"+m,False))]
        one=bool(base.get("combo_one",True)); two=bool(base.get("combo_two",True))
        three=bool(base.get("combo_three",True)); four=bool(base.get("combo_four",True))
        combos=strategy_combinations(selected,one,two,three,four)
        if not combos:
            self.log(f"COMBINATION LAB {sym}: no combinations selected.")
            return
        rows=[]
        max_configs=int(self.sv("max_configs").get())
        for n,combo in enumerate(combos[:max_configs],1):
            if self.stop_flag: break
            c=dict(base)
            for mod in MODULES: c["use_"+mod]=mod in combo
            k=len(combo)
            c["signal_mode"]="SINGLE_SIGNAL" if k==1 else f"{k}_SIGNALS"
            c["min_score"]=k
            try:
                t,m,eq,events=run_backtest(df,c)
                rows.append({"combo_no":n,"modules":" + ".join(combo),**m})
                self.log(f"COMBO {n}/{min(len(combos),max_configs)} | {sym} | {' + '.join(combo)} | Trades={m['trades']} PnL={m['net_pnl']:.2f} PF={m['profit_factor']:.2f}")
            except Exception as e:
                self.log(f"COMBO {n} ERROR: {e}")
        if rows:
            out=pd.DataFrame(rows).sort_values(["net_pnl","profit_factor"],ascending=False)
            stamp=int(time.time()); stem=f"combinations_{sym.replace('/','_').replace(':','_')}_{stamp}"
            out.to_csv(RESULTS_DIR/f"{stem}.csv",index=False)
            try:
                out.to_excel(RESULTS_DIR/f"{stem}.xlsx",index=False)
            except Exception: pass
            self.log(f"COMBINATION LAB SAVED: {RESULTS_DIR/f'{stem}.csv'}")

    def disable_buttons(self,disabled):
        state="disabled" if disabled else "normal"
        for b in [self.start_btn,self.sweep_btn,self.wf_btn,self.combo_btn]: b.config(state=state)
    def launch(self,mode):
        if self.running:return
        try:c=self.cfg()
        except Exception as e: messagebox.showerror("Configuration",str(e)); return
        self.stop_flag=False; self.running=True; self.disable_buttons(True); self.status.set("Running...")
        threading.Thread(target=self.worker,args=(mode,c),daemon=True).start()
    def worker(self,mode,cfg):
        try:
            symbols=parse_symbols(cfg["symbols"])
            exchange=make_exchange(cfg["exchange"])
            # Load CCXT market metadata once before symbol resolution.
            # resolve_symbol() also self-heals this state, but doing it here
            # gives the user one clear DATA/market-load failure instead of
            # repeating the same symbol-resolution error for every symbol.
            self.log(f"MARKETS {cfg['exchange']}: loading CCXT market metadata...")
            exchange.load_markets()
            if not isinstance(getattr(exchange, "markets", None), dict) or not exchange.markets:
                raise RuntimeError(f"{exchange.id}: CCXT market metadata is empty after load_markets().")
            self.log(f"MARKETS {cfg['exchange']}: {len(exchange.markets):,} markets loaded")
            start_ms=date_ms(cfg["start"]); end_ms=date_ms(cfg["end"],True)
            for symbol in symbols:
                if self.stop_flag: break
                try:
                    sym=resolve_symbol(exchange,symbol); self.log(f"DATA {sym} {cfg['tf']}")
                    tf_ms=TIMEFRAMES[cfg["tf"]]
                    history_ms=int(cfg["warmup"])*tf_ms
                    if cfg.get("use_vol_sr",False):
                        sr_tf_ms={"15m":15*60*1000,"30m":30*60*1000,"1h":60*60*1000,"4h":4*60*60*1000,
                                  "D":24*60*60*1000,"W":7*24*60*60*1000}
                        for sr_tf in (cfg.get("sr_tf1"),cfg.get("sr_tf2"),cfg.get("sr_tf3"),cfg.get("sr_tf4")):
                            if sr_tf in sr_tf_ms:
                                history_ms=max(history_ms,int(cfg.get("sr_history_bars",40))*sr_tf_ms[sr_tf])
                    history_start=max(0,start_ms-history_ms)
                    df=fetch_history(exchange,sym,cfg["tf"],history_start,end_ms,self.log,history_start_ms=history_start)
                    df=build_strategy_columns(df,cfg)
                    if mode=="backtest":
                        trades,metrics,eq,events=run_backtest(df,cfg,self.log)
                        self.last_results.append((sym,cfg,metrics,trades,eq))
                        self.log(f"{sym}: trades={metrics['trades']} net={metrics['net_pnl']:.2f} return={metrics['return_pct']:.2f}% PF={metrics['profit_factor']:.2f} DD={metrics['max_drawdown']:.2f}")
                        self.save_result(sym,cfg,metrics,trades,eq)
                    elif mode=="sweep": self.run_sweep(sym,df,cfg)
                    elif mode=="combinations": self.run_combinations(sym,df,cfg)
                    else: self.run_walkforward(sym,df,cfg)
                except Exception as e:
                    self.log(f"{symbol} ERROR: {e}\n{traceback.format_exc()}")
        finally:
            self.running=False; self.disable_buttons(False); self.status.set("Ready")
            try:self.root.after(0,self.populate_results)
            except:pass
    def run_sweep(self,sym,df,base):
        fields=[("ema_fast",self.sv("sweep_ema_fast").get(),int),("ema_slow",self.sv("sweep_ema_slow").get(),int),("rsi_len",self.sv("sweep_rsi_len").get(),int),("st_len",self.sv("sweep_st_len").get(),int),("st_mult",self.sv("sweep_st_mult").get(),float),("sl_pct",self.sv("sweep_sl_pct").get(),float),("tp1_pct",self.sv("sweep_tp1_pct").get(),float),("tp2_pct",self.sv("sweep_tp2_pct").get(),float)]
        grid=make_param_grid(base,fields,int(self.sv("max_configs").get()))
        rows=[]
        for n,c in enumerate(grid,1):
            if self.stop_flag:break
            try:
                t,m,eq,e=run_backtest(df,c)
                rows.append({**m,"config_no":n,"ema_fast":c["ema_fast"],"ema_slow":c["ema_slow"],"rsi_len":c["rsi_len"],"st_len":c["st_len"],"st_mult":c["st_mult"],"sl_pct":c["sl_pct"],"tp1_pct":c["tp1_pct"],"tp2_pct":c["tp2_pct"]})
            except Exception as e:self.log(f"SWEEP {n} ERROR: {e}")
            if n%10==0:self.log(f"SWEEP {sym}: {n}/{len(grid)}")
        out=pd.DataFrame(rows)
        if not out.empty:
            out=out.sort_values(["net_pnl","profit_factor"],ascending=False)
            path=RESULTS_DIR/f"sweep_{sym.replace('/','_')}_{int(time.time())}.csv"; out.to_csv(path,index=False); self.log(f"SWEEP SAVED {path}")
    def run_walkforward(self,sym,df,base):
        split=float(self.sv("wf_split").get())/100
        cut=int(len(df)*split); is_df=df.iloc[:cut].copy(); oos_df=df.iloc[cut:].copy()
        fields=[("ema_fast",self.sv("sweep_ema_fast").get(),int),("ema_slow",self.sv("sweep_ema_slow").get(),int),("rsi_len",self.sv("sweep_rsi_len").get(),int),("st_len",self.sv("sweep_st_len").get(),int),("st_mult",self.sv("sweep_st_mult").get(),float),("sl_pct",self.sv("sweep_sl_pct").get(),float),("tp1_pct",self.sv("sweep_tp1_pct").get(),float),("tp2_pct",self.sv("sweep_tp2_pct").get(),float)]
        grid=make_param_grid(base,fields,int(self.sv("max_configs").get()))
        scored=[]
        for c in grid:
            if self.stop_flag:break
            try:
                t,m,_,_=run_backtest(is_df,c); scored.append((m["net_pnl"],c,m))
            except Exception:pass
        scored.sort(key=lambda x:x[0],reverse=True); top=scored[:max(1,int(self.sv("top_n").get()))]
        rows=[]
        for rank,(_,c,mi) in enumerate(top,1):
            if self.stop_flag:break
            try:
                # OOS receives only the OOS candles plus warmup history from IS,
                # preventing indicator cold-start distortion without leaking future OOS.
                warm=int(c["warmup"]); oos_input=pd.concat([is_df.tail(warm),oos_df],ignore_index=True)
                _,mo,_,_=run_backtest(oos_input,c)
                rows.append({"rank":rank,"IS_net":mi["net_pnl"],"IS_return":mi["return_pct"],"OOS_net":mo["net_pnl"],"OOS_return":mo["return_pct"],"OOS_PF":mo["profit_factor"],"OOS_DD":mo["max_drawdown"],**{k:c[k] for k in ["ema_fast","ema_slow","rsi_len","st_len","st_mult","sl_pct","tp1_pct","tp2_pct"]}})
            except Exception as e:self.log(f"WF OOS ERROR: {e}")
        if rows:
            out=pd.DataFrame(rows); path=RESULTS_DIR/f"walkforward_{sym.replace('/','_')}_{int(time.time())}.csv"; out.to_csv(path,index=False); self.log(f"WALK-FORWARD SAVED {path}")
    def save_result(self,sym,cfg,metrics,trades,eq):
        stamp=int(time.time()); stem=f"{sym.replace('/','_').replace(':','_')}_{cfg['tf']}_{stamp}"
        pd.DataFrame([metrics]).to_csv(RESULTS_DIR/f"summary_{stem}.csv",index=False)
        if cfg.get("output_trades",True): pd.DataFrame(trades).to_csv(RESULTS_DIR/f"trades_{stem}.csv",index=False)
        pd.DataFrame(eq).to_csv(RESULTS_DIR/f"equity_{stem}.csv",index=False)
        try:
            with pd.ExcelWriter(RESULTS_DIR/f"backtest_{stem}.xlsx",engine="openpyxl") as w:
                pd.DataFrame([metrics]).to_excel(w,index=False,sheet_name="Summary")
                pd.DataFrame(trades).to_excel(w,index=False,sheet_name="Trades")
                pd.DataFrame(eq).to_excel(w,index=False,sheet_name="Equity")
                monthly_stats(trades).to_excel(w,index=False,sheet_name="Monthly")
        except Exception as e:self.log(f"XLSX export skipped: {e}")
    def populate_results(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        for sym,cfg,m,t,e in self.last_results:
            self.tree.insert("", "end", values=(sym,cfg["signal_mode"],m["trades"],f"{m['win_rate']:.1f}%",f"{m['net_pnl']:.2f}",f"{m['return_pct']:.2f}%",f"{m['profit_factor']:.2f}",f"{m['max_drawdown']:.2f}"))

if __name__=="__main__":
    root=tk.Tk(); app=BacktesterGUI(root); root.mainloop()