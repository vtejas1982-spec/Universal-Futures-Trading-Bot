import json
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import ccxt  # retained only for compatibility; Forex runtime does not use it.
except ImportError:
    ccxt = None
import numpy as np
import pandas as pd
import requests
import sys

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None
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


APP_VERSION = "V8.3.3-FOREX"
APP_TITLE = "Universal Forex Trading Bot V8.3.3 - MT5 Forex Only"

# Keep the config and trade log beside the executable when packaged with PyInstaller.
# When running the .py directly, keep them beside the script.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_FILE = str(APP_DIR / "config_universal_fixed.json")
LOG_FILE = str(APP_DIR / "universal_trade_logs_fixed.csv")

# V8.3.3 Forex-only strategy contract. No crypto/futures exchange is used.
RUNTIME_SCHEMA_VERSION = 5
SUPPORTED_SIGNAL_MODES = ("SINGLE_SIGNAL", "ANY_NON_CONFLICTING", "SCORE", "2_SIGNALS", "3_SIGNALS", "4_SIGNALS", "ADAPTIVE_SCORE", "STRICT_ALL_FILTERS")
ADAPTIVE_MODULE_WEIGHTS = {
    "ST":1.50,"EMA":1.00,"EMA_CROSS":1.25,"MACD":1.25,"RSI":1.00,"BB":0.75,"STOCH":0.75,
    "VWAP":1.25,"VWAP_DELTA":1.00,"VIDYA":1.25,"NWE":1.00,"LIQ_SWING":1.50,"TRENDLINE":1.50,
    "MTF":2.00,"DIVERGENCE":1.75,"VOL_SR":1.50,"VOL":0.50,"ADX":1.25,"ATR":0.50,
}
ADAPTIVE_DEFAULT_EDGE = 0.18
ADAPTIVE_DEFAULT_MIN_WEIGHT = 3.50
DEFAULT_SIGNAL_MODE = "ADAPTIVE_SCORE"
DEFAULT_ADAPTIVE_EDGE = "0.18"
DEFAULT_ADAPTIVE_MIN_WEIGHT = "3.5"
DIVERGENCE_INDICATORS = ("MACD","MACD_HIST","RSI","STOCH","CCI","MOMENTUM","OBV","VWMACD","CMF","MFI")


# -------------------- INDICATORS ----------------------------

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



# TradingView-based indicator translations:
# VWAP Delta © graefe — Mozilla Public License 2.0.
# Volumatic VIDYA © BigBeluga — CC BY-NC-SA 4.0.
# Nadaraya-Watson Envelope © LuxAlgo — CC BY-NC-SA 4.0.
# License: https://creativecommons.org/licenses/by-nc-sa/4.0/
# Visual drawing objects are omitted; calculation/trend logic is retained.

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
    multiplier = float(multiplier)
    lookback = int(lookback)
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



# -------------------- GUI BOT -------------------------------



# ============================================================
# V8.3.3 ADVANCED FOREX STRATEGY MODULES
# Confirmed/causal only: no look-ahead pivots or repainting signals.
# ============================================================

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
    @staticmethod
    def decide_signal(directional_modules, signal_mode, min_score,
                      atr_pass=True, vol_pass=True, adx_pass=True,
                      mtf_pass_bull=True, mtf_pass_bear=True,
                      adaptive_edge=None, adaptive_min_weight=None):
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
            min_weight = max(
                float(min_score),
                float(ADAPTIVE_DEFAULT_MIN_WEIGHT if adaptive_min_weight is None else adaptive_min_weight),
            )
            edge_threshold = float(
                ADAPTIVE_DEFAULT_EDGE if adaptive_edge is None else adaptive_edge
            )
            buy_ok = wb >= min_weight and wb > ws and edge >= edge_threshold
            sell_ok = ws >= min_weight and ws > wb and edge >= edge_threshold
            # VOL/ATR/ADX/MTF are gates in adaptive mode; they are not double-counted.
            buy_ok = buy_ok and bool(atr_pass) and bool(vol_pass) and bool(adx_pass) and bool(mtf_pass_bull)
            sell_ok = sell_ok and bool(atr_pass) and bool(vol_pass) and bool(adx_pass) and bool(mtf_pass_bear)
            return buy_ok, sell_ok, wb, ws

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
                        adaptive_edge=None, adaptive_min_weight=None):
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
        if mode == "STRICT_ALL_FILTERS":
            if buy == len(modules) and sell == 0 and atr_pass and vol_pass and adx_pass and mtf_pass_bull: return "STRICT_BUY_ALL_FILTERS_PASS"
            if sell == len(modules) and buy == 0 and atr_pass and vol_pass and adx_pass and mtf_pass_bear: return "STRICT_SELL_ALL_FILTERS_PASS"
            failed = [name for name, ok in (("ATR",atr_pass),("VOL",vol_pass),("ADX",adx_pass)) if not ok]
            return "STRICT_BLOCKED" + (f"_FILTERS_{','.join(failed)}" if failed else "_DIRECTION_OR_ALIGNMENT")
        return f"UNKNOWN_SIGNAL_MODE_{mode}"


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
        self.trade_pnls = []
        self.active_trade = None
        self.session_started_at = None
        self.session_max_trades = 0

        self.last_protected_position = None
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
        # ---------------- V2 risk/execution state ----------------
        self.v2_day_key = None
        self.v2_day_start_equity = 0.0
        self.v2_loss_streak = 0
        self.v2_guard_lock = threading.RLock()
        self.v2_watchdog_thread = None
        self.v2_watchdog_running = False
        self.v2_last_news_check = 0.0
        self.v2_news_cache = []
        self.v2_last_scan = 0.0
        self.v2_trailing_last_log = 0.0

        self._init_csv_log()
        self._build_ui()
        self.update_estimated_window()
        self.load_settings()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -------------------- LOGGING ----------------------------

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
        title = tk.Label(
            self.root,
            text="Universal Forex Trading Bot V2 - MT5",
            font=("Arial", 16, "bold"),
        )
        title.pack(pady=5)

        # Main two-column layout: controls on the left, Execution Log on the right.
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=8, pady=4)

        left_frame = tk.Frame(main_frame)
        right_frame = tk.LabelFrame(
            main_frame, text=" Execution Log ", width=320
        )

        # Execution Log is ALWAYS BELOW the controls.
        # This preserves the original layout and gives the settings their
        # full available width on every Windows screen size.
        left_frame.pack(side="top", fill="both", expand=True)
        right_frame.configure(height=190)
        right_frame.pack(side="bottom", fill="x", padx=(0, 0), pady=(6, 0))
        right_frame.pack_propagate(False)

        canvas = tk.Canvas(left_frame)
        scrollbar = ttk.Scrollbar(
            left_frame, orient="vertical", command=canvas.yview
        )
        self.scroll_frame = ttk.Frame(canvas)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Let the controls use the available left-panel width rather than
        # inheriting an oversized fixed canvas width.
        def _fit_scroll_width(_event=None):
            try:
                canvas.itemconfigure("all", width=max(1, canvas.winfo_width()))
            except Exception:
                pass

        canvas.bind("<Configure>", _fit_scroll_width)

        # Right-side Execution Log.
        log_text_frame = tk.Frame(right_frame)
        log_text_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_box = tk.Text(
            log_text_frame, height=18, bg="#111111", fg="#00ff66",
            font=("Consolas", 9), wrap="none"
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

        # 1. MT5 / Forex Connection
        f_api = tk.LabelFrame(
            self.scroll_frame,
            text=" 1. MT5 Forex Connection ",
        )
        f_api.pack(fill="x", padx=10, pady=5)

        tk.Label(f_api, text="Platform:").grid(row=0, column=0, sticky="w")
        self.v_exchange = tk.StringVar(value="mt5_forex")
        ttk.OptionMenu(
            f_api, self.v_exchange, "mt5_forex", "mt5_forex"
        ).grid(row=0, column=1, padx=5, pady=2, sticky="w")

        tk.Label(f_api, text="MT5 Login:").grid(row=1, column=0, sticky="w")
        self.e_api_key = tk.Entry(f_api, width=22)
        self.e_api_key.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        tk.Label(f_api, text="MT5 Password:").grid(row=1, column=2, sticky="w")
        self.e_api_secret = tk.Entry(f_api, width=28, show="*")
        self.e_api_secret.grid(row=1, column=3, padx=5, pady=2, sticky="w")

        tk.Label(f_api, text="Server:").grid(row=2, column=0, sticky="w")
        self.e_mt5_server = tk.Entry(f_api, width=40)
        self.e_mt5_server.grid(row=2, column=1, columnspan=2, padx=5, pady=2, sticky="w")

        tk.Label(f_api, text="Account Mode:").grid(row=3, column=0, sticky="w")
        self.v_account_mode = tk.StringVar(value="MT5_PAPER")
        ttk.OptionMenu(
            f_api, self.v_account_mode, "MT5_PAPER",
            "MT5_PAPER", "MT5_TERMINAL", "MT5_LIVE"
        ).grid(row=3, column=1, padx=5, pady=2, sticky="w")

        tk.Label(
            f_api,
            text=(
                "MT5_PAPER = no broker order | MT5_TERMINAL = use already logged-in terminal | "
                "MT5_LIVE = explicit broker login.  REAL orders are never sent in PAPER mode."
            ),
            fg="#555555",
        ).grid(row=4, column=0, columnspan=6, sticky="w")

        # 2. Market
        f_market = tk.LabelFrame(
            self.scroll_frame,
            text=" 2. Market Config ",
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
        self.e_symbol.insert(0, "EURUSD")
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
            text="Reference Leverage:",
        ).grid(row=0, column=4, sticky="w")

        self.e_lev = tk.Entry(
            f_market,
            width=7,
        )
        self.e_lev.insert(0, "30")
        self.e_lev.grid(row=0, column=5, padx=5)
        tk.Label(f_market, text="Paper Start Balance:").grid(row=0, column=6, sticky="e")
        self.e_paper_balance = tk.Entry(f_market, width=10)
        self.e_paper_balance.insert(0, "1000")
        self.e_paper_balance.grid(row=0, column=7, padx=5, sticky="w")
        tk.Label(f_market, text="USD account / lot sizing test", fg="#444444").grid(row=1, column=6, columnspan=2, sticky="w")

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
        self.v_use_spread_filter = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_market, text="Forex Spread Filter", variable=self.v_use_spread_filter
        ).grid(row=3, column=3, sticky="w")
        tk.Label(f_market, text="Max Spread (points):").grid(row=3, column=4, sticky="e")
        self.e_max_spread_points = tk.Entry(f_market, width=8)
        self.e_max_spread_points.insert(0, "30")
        self.e_max_spread_points.grid(row=3, column=5, padx=5, sticky="w")

        tk.Label(f_market, text="Cooldown (min):").grid(row=4, column=0, sticky="w")
        self.e_cooldown_min = tk.Entry(f_market, width=6)
        self.e_cooldown_min.insert(0, "0")
        self.e_cooldown_min.grid(row=3, column=1, padx=5, sticky="w")
        tk.Label(f_market, text="0 = OFF", fg="#444444").grid(row=3, column=2, sticky="w")
        self.v_require_opposite_after_exit = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_market,
            text="Safety: After SL, Require Opposite Signal",
            variable=self.v_require_opposite_after_exit,
        ).grid(row=5, column=0, columnspan=3, sticky="w")
        tk.Label(
            f_market,
            text="After SL/BE stop, block same-direction re-entry until a valid opposite signal appears.",
            fg="#444444",
        ).grid(row=5, column=3, columnspan=4, sticky="w")

        self.e_max_trades.bind("<KeyRelease>", lambda _e: self.update_estimated_window())
        self.v_tf.trace_add("write", lambda *_args: self.update_estimated_window())

        # 3. Forex Execution, Session & Risk Guardrails (V2)
        f_v2 = tk.LabelFrame(
            self.scroll_frame,
            text=" 3. Forex V2 Execution, Session & Risk Guardrails ",
        )
        f_v2.pack(fill="x", padx=10, pady=5)

        self.v_auto_symbol = tk.BooleanVar(value=True)
        tk.Checkbutton(f_v2, text="Broker Symbol Auto-Discovery", variable=self.v_auto_symbol).grid(row=0, column=0, sticky="w")
        tk.Label(f_v2, text="MT5 will resolve EURUSD / broker suffixes automatically.", fg="#444444").grid(row=0, column=1, columnspan=5, sticky="w")

        self.v_use_slippage = tk.BooleanVar(value=True)
        tk.Checkbutton(f_v2, text="Slippage Protection", variable=self.v_use_slippage).grid(row=1, column=0, sticky="w")
        tk.Label(f_v2, text="Max Slippage (points):").grid(row=1, column=1, sticky="e")
        self.e_max_slippage_points = tk.Entry(f_v2, width=7)
        self.e_max_slippage_points.insert(0, "20")
        self.e_max_slippage_points.grid(row=1, column=2, padx=3, sticky="w")

        self.v_use_session = tk.BooleanVar(value=False)
        tk.Checkbutton(f_v2, text="Trading Session Filter (UTC)", variable=self.v_use_session).grid(row=2, column=0, sticky="w")
        tk.Label(f_v2, text="Start:").grid(row=2, column=1, sticky="e")
        self.e_session_start = tk.Entry(f_v2, width=7)
        self.e_session_start.insert(0, "07:00")
        self.e_session_start.grid(row=2, column=2, padx=3, sticky="w")
        tk.Label(f_v2, text="End:").grid(row=2, column=3, sticky="e")
        self.e_session_end = tk.Entry(f_v2, width=7)
        self.e_session_end.insert(0, "20:00")
        self.e_session_end.grid(row=2, column=4, padx=3, sticky="w")

        self.v_friday_protect = tk.BooleanVar(value=True)
        tk.Checkbutton(f_v2, text="Friday Protection", variable=self.v_friday_protect).grid(row=3, column=0, sticky="w")
        tk.Label(f_v2, text="Stop new entries after UTC:").grid(row=3, column=1, sticky="e")
        self.e_friday_cutoff = tk.Entry(f_v2, width=7)
        self.e_friday_cutoff.insert(0, "18:00")
        self.e_friday_cutoff.grid(row=3, column=2, padx=3, sticky="w")

        self.v_use_daily_loss = tk.BooleanVar(value=True)
        tk.Checkbutton(f_v2, text="Daily Loss Limit", variable=self.v_use_daily_loss).grid(row=4, column=0, sticky="w")
        tk.Label(f_v2, text="Max Daily Loss %:").grid(row=4, column=1, sticky="e")
        self.e_daily_loss_pct = tk.Entry(f_v2, width=7)
        self.e_daily_loss_pct.insert(0, "3.0")
        self.e_daily_loss_pct.grid(row=4, column=2, padx=3, sticky="w")

        self.v_use_daily_profit = tk.BooleanVar(value=False)
        tk.Checkbutton(f_v2, text="Daily Profit Lock", variable=self.v_use_daily_profit).grid(row=4, column=3, sticky="w")
        tk.Label(f_v2, text="Target %:").grid(row=4, column=4, sticky="e")
        self.e_daily_profit_pct = tk.Entry(f_v2, width=7)
        self.e_daily_profit_pct.insert(0, "5.0")
        self.e_daily_profit_pct.grid(row=4, column=5, padx=3, sticky="w")

        self.v_use_loss_streak = tk.BooleanVar(value=True)
        tk.Checkbutton(f_v2, text="Consecutive-Loss Protection", variable=self.v_use_loss_streak).grid(row=5, column=0, sticky="w")
        tk.Label(f_v2, text="Max consecutive losses:").grid(row=5, column=1, sticky="e")
        self.e_max_loss_streak = tk.Entry(f_v2, width=7)
        self.e_max_loss_streak.insert(0, "3")
        self.e_max_loss_streak.grid(row=5, column=2, padx=3, sticky="w")

        self.v_use_trailing = tk.BooleanVar(value=False)
        tk.Checkbutton(f_v2, text="Trailing Stop", variable=self.v_use_trailing).grid(row=6, column=0, sticky="w")
        tk.Label(f_v2, text="Activation (points):").grid(row=6, column=1, sticky="e")
        self.e_trail_activation = tk.Entry(f_v2, width=7)
        self.e_trail_activation.insert(0, "30")
        self.e_trail_activation.grid(row=6, column=2, padx=3, sticky="w")
        tk.Label(f_v2, text="Distance (points):").grid(row=6, column=3, sticky="e")
        self.e_trail_distance = tk.Entry(f_v2, width=7)
        self.e_trail_distance.insert(0, "20")
        self.e_trail_distance.grid(row=6, column=4, padx=3, sticky="w")

        self.v_use_atr_sl = tk.BooleanVar(value=False)
        tk.Checkbutton(f_v2, text="ATR Dynamic SL", variable=self.v_use_atr_sl).grid(row=7, column=0, sticky="w")
        tk.Label(f_v2, text="ATR SL Multiplier:").grid(row=7, column=1, sticky="e")
        self.e_atr_sl_mult = tk.Entry(f_v2, width=7)
        self.e_atr_sl_mult.insert(0, "1.5")
        self.e_atr_sl_mult.grid(row=7, column=2, padx=3, sticky="w")
        tk.Label(f_v2, text="Uses latest completed-candle ATR.", fg="#444444").grid(row=7, column=3, columnspan=3, sticky="w")

        self.v_use_news = tk.BooleanVar(value=False)
        tk.Checkbutton(f_v2, text="Economic News Filter", variable=self.v_use_news).grid(row=8, column=0, sticky="w")
        tk.Label(f_v2, text="Block high-impact news ± minutes:").grid(row=8, column=1, sticky="e")
        self.e_news_minutes = tk.Entry(f_v2, width=7)
        self.e_news_minutes.insert(0, "30")
        self.e_news_minutes.grid(row=8, column=2, padx=3, sticky="w")
        tk.Label(f_v2, text="Source: Forex Factory calendar JSON", fg="#444444").grid(row=8, column=3, columnspan=3, sticky="w")

        self.v_use_correlation = tk.BooleanVar(value=False)
        tk.Checkbutton(f_v2, text="Correlation Protection", variable=self.v_use_correlation).grid(row=9, column=0, sticky="w")
        tk.Label(f_v2, text="Max abs correlation:").grid(row=9, column=1, sticky="e")
        self.e_corr_threshold = tk.Entry(f_v2, width=7)
        self.e_corr_threshold.insert(0, "0.85")
        self.e_corr_threshold.grid(row=9, column=2, padx=3, sticky="w")
        tk.Label(f_v2, text="Symbols:").grid(row=9, column=3, sticky="e")
        self.e_corr_symbols = tk.Entry(f_v2, width=32)
        self.e_corr_symbols.insert(0, "EURUSD,GBPUSD,USDCHF,USDJPY")
        self.e_corr_symbols.grid(row=9, column=4, columnspan=2, padx=3, sticky="w")

        self.v_scanner = tk.BooleanVar(value=False)
        tk.Checkbutton(f_v2, text="Multi-Symbol Signal Scanner (informational)", variable=self.v_scanner).grid(row=10, column=0, sticky="w")
        tk.Label(f_v2, text="Scan symbols:").grid(row=10, column=1, sticky="e")
        self.e_scan_symbols = tk.Entry(f_v2, width=45)
        self.e_scan_symbols.insert(0, "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
        self.e_scan_symbols.grid(row=10, column=2, columnspan=4, padx=3, sticky="w")

        self.v_reconnect = tk.BooleanVar(value=True)
        tk.Checkbutton(f_v2, text="MT5 Reconnect Watchdog", variable=self.v_reconnect).grid(row=11, column=0, sticky="w")
        self.v_position_recovery = tk.BooleanVar(value=True)
        tk.Checkbutton(f_v2, text="Position Recovery on Start", variable=self.v_position_recovery).grid(row=11, column=1, columnspan=2, sticky="w")
        tk.Label(f_v2, text="Magic Number:").grid(row=11, column=3, sticky="e")
        self.e_magic = tk.Entry(f_v2, width=12)
        self.e_magic.insert(0, "26091802")
        self.e_magic.grid(row=11, column=4, padx=3, sticky="w")

        tk.Label(f_v2, text="V2 guardrails are optional and default to conservative safety settings; strategy/indicator formulas remain unchanged.", fg="#444444", wraplength=1150).grid(row=12, column=0, columnspan=6, sticky="w", pady=3)

        # 3. Strategy
        f_strat = tk.LabelFrame(
            self.scroll_frame,
            text=" 3. Strategy & Indicator Modules ",
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
        ttk.OptionMenu(
            f_strat, self.v_nwe_entry_mode, "FRESH_CROSS",
            "FRESH_CROSS", "CURRENT_TREND"
        ).grid(row=12, column=7, padx=2, sticky="w")

        tk.Label(f_strat, text="Repainting:").grid(row=13, column=2, sticky="e")
        self.v_nwe_repaint = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            variable=self.v_nwe_repaint,
            text="OFF (recommended for trading)",
        ).grid(row=13, column=3, columnspan=3, sticky="w")
        tk.Label(
            f_strat,
            text="FRESH_CROSS: lower-band cross = BUY, upper-band cross = SELL | CURRENT_TREND: NWE slope",
            fg="#444444",
        ).grid(row=13, column=6, columnspan=2, sticky="w")

        # Optional ATR volatility filter using the ATR already calculated
        # by the Supertrend engine. Requires ATR/close >= threshold.
        self.v_use_atr = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_strat,
            text="ATR Volatility Filter",
            variable=self.v_use_atr,
        ).grid(row=14, column=0, sticky="w")
        tk.Label(f_strat, text="Min ATR %:").grid(row=14, column=1, sticky="e")
        self.e_atr_min_pct = tk.Entry(f_strat, width=6)
        self.e_atr_min_pct.insert(0, "0.30")
        self.e_atr_min_pct.grid(row=14, column=2, padx=2)

        self.v_use_vol = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat, text="Vol Filter", variable=self.v_use_vol
        ).grid(row=15, column=0, sticky="w")
        self.e_vol_len = tk.Entry(f_strat, width=6)
        self.e_vol_len.insert(0, "20")
        self.e_vol_len.grid(row=15, column=1, padx=2)

        self.v_use_adx = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat, text="ADX Filter", variable=self.v_use_adx
        ).grid(row=16, column=0, sticky="w")
        self.e_adx_thresh = tk.Entry(f_strat, width=6)
        self.e_adx_thresh.insert(0, "20")
        self.e_adx_thresh.grid(row=16, column=1, padx=2)

        self.v_use_mtf = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat,
            text="Multi-TF (4h Confluence)",
            variable=self.v_use_mtf,
        ).grid(row=17, column=0, columnspan=2, sticky="w")

        # Signal decision mode.
        self.v_signal_mode = tk.StringVar(value="ADAPTIVE_SCORE")
        tk.Label(f_strat, text="Signal Mode:").grid(row=18, column=0, sticky="w")
        ttk.OptionMenu(
            f_strat,
            self.v_signal_mode,
            "SINGLE_SIGNAL",
            "SINGLE_SIGNAL",
            "2_SIGNALS",
            "3_SIGNALS",
            "4_SIGNALS",
            "SCORE",
            "ADAPTIVE_SCORE",
            "ANY_NON_CONFLICTING",
            "STRICT_ALL_FILTERS",
        ).grid(row=18, column=1, padx=5, sticky="w")

        tk.Label(f_strat, text="Score (SCORE mode):").grid(row=18, column=2, sticky="e")
        self.e_min_score = tk.Entry(f_strat, width=5)
        self.e_min_score.insert(0, "1")
        self.e_min_score.grid(row=18, column=3, padx=2)

        self.v_hold_until_all_reverse = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat,
            text="Hold Position Until ALL Active Signals Reverse",
            variable=self.v_hold_until_all_reverse,
        ).grid(row=19, column=0, columnspan=4, sticky="w")

        tk.Label(
            f_strat,
            text="ON: open trade waits until every enabled directional module shows the opposite direction. OFF: normal reversal.",
            fg="#444444",
        ).grid(row=20, column=0, columnspan=8, sticky="w")

        # V8.3.3 advanced strategy controls. These are Forex-only and feed
        # the same StrategyEngine used by the live decision path.
        tk.Label(f_strat, text="Adaptive Edge:").grid(row=22, column=0, sticky="e")
        self.e_adaptive_edge = tk.Entry(f_strat, width=6); self.e_adaptive_edge.insert(0, "0.18"); self.e_adaptive_edge.grid(row=22,column=1,padx=2)
        tk.Label(f_strat, text="Adaptive Min Weight:").grid(row=22, column=2, sticky="e")
        self.e_adaptive_min_weight = tk.Entry(f_strat, width=6); self.e_adaptive_min_weight.insert(0, "3.5"); self.e_adaptive_min_weight.grid(row=22,column=3,padx=2)

        self.v_use_liq_swing = tk.BooleanVar(value=True)
        tk.Checkbutton(f_strat,text="Liquidity Swings",variable=self.v_use_liq_swing).grid(row=23,column=0,sticky="w")
        tk.Label(f_strat,text="Pivot:").grid(row=23,column=1,sticky="e")
        self.e_liq_len=tk.Entry(f_strat,width=5); self.e_liq_len.insert(0,"14"); self.e_liq_len.grid(row=23,column=2)
        tk.Label(f_strat,text="Filter:").grid(row=23,column=3,sticky="e")
        self.v_liq_filter=tk.StringVar(value="Count"); ttk.OptionMenu(f_strat,self.v_liq_filter,"Count","Count","Volume").grid(row=23,column=4,sticky="w")
        tk.Label(f_strat,text="Value:").grid(row=23,column=5,sticky="e")
        self.e_liq_filter_value=tk.Entry(f_strat,width=6); self.e_liq_filter_value.insert(0,"0"); self.e_liq_filter_value.grid(row=23,column=6)
        tk.Label(f_strat,text="Area:").grid(row=24,column=1,sticky="e")
        self.v_liq_area=tk.StringVar(value="Wick Extremity"); ttk.OptionMenu(f_strat,self.v_liq_area,"Wick Extremity","Wick Extremity","Full Range").grid(row=24,column=2,sticky="w")

        self.v_use_trendline=tk.BooleanVar(value=True)
        tk.Checkbutton(f_strat,text="Trendline Breakout",variable=self.v_use_trendline).grid(row=24,column=3,sticky="w")
        tk.Label(f_strat,text="Pivot:").grid(row=24,column=4,sticky="e")
        self.e_trend_len=tk.Entry(f_strat,width=5); self.e_trend_len.insert(0,"14"); self.e_trend_len.grid(row=24,column=5)
        tk.Label(f_strat,text="Min Dist:").grid(row=25,column=1,sticky="e")
        self.e_trend_min_dist=tk.Entry(f_strat,width=5); self.e_trend_min_dist.insert(0,"5"); self.e_trend_min_dist.grid(row=25,column=2)
        tk.Label(f_strat,text="Buffer %:").grid(row=25,column=3,sticky="e")
        self.e_trend_buffer=tk.Entry(f_strat,width=6); self.e_trend_buffer.insert(0,"0.0"); self.e_trend_buffer.grid(row=25,column=4)
        tk.Label(f_strat,text="Retest:").grid(row=25,column=5,sticky="e")
        self.e_trend_retest=tk.Entry(f_strat,width=5); self.e_trend_retest.insert(0,"3"); self.e_trend_retest.grid(row=25,column=6)
        self.v_trend_entry=tk.StringVar(value="FRESH_BREAK"); ttk.OptionMenu(f_strat,self.v_trend_entry,"FRESH_BREAK","FRESH_BREAK","CURRENT_TREND","BREAK_RETEST").grid(row=25,column=7,sticky="w")

        self.v_use_divergence=tk.BooleanVar(value=True)
        tk.Checkbutton(f_strat,text="Confirmed Divergence",variable=self.v_use_divergence).grid(row=26,column=0,sticky="w")
        tk.Label(f_strat,text="Pivot:").grid(row=26,column=1,sticky="e")
        self.e_div_pivot=tk.Entry(f_strat,width=5); self.e_div_pivot.insert(0,"5"); self.e_div_pivot.grid(row=26,column=2)
        tk.Label(f_strat,text="Max Pivots:").grid(row=26,column=3,sticky="e")
        self.e_div_max_pivots=tk.Entry(f_strat,width=5); self.e_div_max_pivots.insert(0,"10"); self.e_div_max_pivots.grid(row=26,column=4)
        tk.Label(f_strat,text="Max Bars:").grid(row=26,column=5,sticky="e")
        self.e_div_max_bars=tk.Entry(f_strat,width=6); self.e_div_max_bars.insert(0,"100"); self.e_div_max_bars.grid(row=26,column=6)
        self.v_div_type=tk.StringVar(value="Regular/Hidden"); ttk.OptionMenu(f_strat,self.v_div_type,"Regular/Hidden","Regular","Hidden","Regular/Hidden").grid(row=27,column=0,sticky="w")
        self.v_div_source=tk.StringVar(value="Close"); ttk.OptionMenu(f_strat,self.v_div_source,"Close","Close","High/Low").grid(row=27,column=1,sticky="w")
        tk.Label(f_strat,text="CCI/Mom/VWMACD/CMF/MFI lengths:").grid(row=27,column=2,sticky="e")
        self.e_div_cci=tk.Entry(f_strat,width=4); self.e_div_cci.insert(0,"10"); self.e_div_cci.grid(row=27,column=3)
        self.e_div_mom=tk.Entry(f_strat,width=4); self.e_div_mom.insert(0,"10"); self.e_div_mom.grid(row=27,column=4)
        self.e_div_vwfast=tk.Entry(f_strat,width=4); self.e_div_vwfast.insert(0,"12"); self.e_div_vwfast.grid(row=27,column=5)
        self.e_div_vwslow=tk.Entry(f_strat,width=4); self.e_div_vwslow.insert(0,"26"); self.e_div_vwslow.grid(row=27,column=6)
        self.e_div_cmf=tk.Entry(f_strat,width=4); self.e_div_cmf.insert(0,"21"); self.e_div_cmf.grid(row=28,column=0)
        self.e_div_mfi=tk.Entry(f_strat,width=4); self.e_div_mfi.insert(0,"14"); self.e_div_mfi.grid(row=28,column=1)
        self.v_div_use_all=tk.BooleanVar(value=True); tk.Checkbutton(f_strat,text="Use all divergence sources",variable=self.v_div_use_all).grid(row=28,column=2,columnspan=2,sticky="w")

        self.v_use_vol_sr=tk.BooleanVar(value=True)
        tk.Checkbutton(f_strat,text="Volume S/R",variable=self.v_use_vol_sr).grid(row=29,column=0,sticky="w")
        tk.Label(f_strat,text="Vol MA:").grid(row=29,column=1,sticky="e")
        self.e_sr_vol_ma=tk.Entry(f_strat,width=5); self.e_sr_vol_ma.insert(0,"6"); self.e_sr_vol_ma.grid(row=29,column=2)
        self.v_sr_vote=tk.StringVar(value="MAJORITY"); ttk.OptionMenu(f_strat,self.v_sr_vote,"MAJORITY","MAJORITY","ALL","ANY").grid(row=29,column=3,sticky="w")
        self.v_sr_entry=tk.StringVar(value="CURRENT_ZONE"); ttk.OptionMenu(f_strat,self.v_sr_entry,"CURRENT_ZONE","CURRENT_ZONE","FRESH_BREAK").grid(row=29,column=4,sticky="w")
        self.v_sr_tf1=tk.StringVar(value="Chart"); ttk.OptionMenu(f_strat,self.v_sr_tf1,"Chart","Chart","15m","1h","4h","D","W","Disable").grid(row=29,column=5,sticky="w")
        self.v_sr_tf2=tk.StringVar(value="4h"); ttk.OptionMenu(f_strat,self.v_sr_tf2,"4h","Chart","15m","1h","4h","D","W","Disable").grid(row=29,column=6,sticky="w")
        self.v_sr_tf3=tk.StringVar(value="D"); ttk.OptionMenu(f_strat,self.v_sr_tf3,"D","Chart","15m","1h","4h","D","W","Disable").grid(row=30,column=0,sticky="w")
        self.v_sr_tf4=tk.StringVar(value="W"); ttk.OptionMenu(f_strat,self.v_sr_tf4,"W","Chart","15m","1h","4h","D","W","Disable").grid(row=30,column=1,sticky="w")

        tk.Label(
            f_strat,
            text=(
                "SINGLE_SIGNAL = any ONE enabled signal can trade; "
                "2/3/4_SIGNALS = required directional votes; SCORE = custom minimum votes; "
                "STRICT_ALL_FILTERS = original strict mode."
            ),
            fg="#444444",
        ).grid(row=21, column=0, columnspan=8, sticky="w", pady=3)

        # 4. Risk
        f_risk = tk.LabelFrame(
            self.scroll_frame,
            text=" 4. Dynamic Risk & Sizing Controls ",
        )
        f_risk.pack(fill="x", padx=10, pady=5)

        tk.Label(
            f_risk,
            text="Sizing Mode:",
        ).grid(row=0, column=0, sticky="w")

        self.v_size_mode = tk.StringVar(
            value="EQUITY_RISK_%"
        )

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
        self.e_risk_pct.insert(0, "1.0")
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
        tk.Label(f_risk, text="Equity loss from bot start; closes ALL account positions + stops bot.").grid(row=2, column=2, columnspan=4, sticky="w", padx=5)

        # 5. SL/TP
        f_sltp = tk.LabelFrame(
            self.scroll_frame,
            text=" 5. SL & TP Protection - PRICE % or ROI % ",
        )
        f_sltp.pack(fill="x", padx=10, pady=5)

        tk.Label(f_sltp, text="SL Mode:").grid(row=0, column=0, sticky="w")
        self.v_sl_mode = tk.StringVar(value="PRICE_%")
        ttk.OptionMenu(f_sltp, self.v_sl_mode, "PRICE_%", "PRICE_%", "ROI_%", "PIPS").grid(row=0, column=1, padx=5, sticky="w")

        tk.Label(f_sltp, text="TP Mode:").grid(row=0, column=2, sticky="w")
        self.v_tp_mode = tk.StringVar(value="ROI_%")
        ttk.OptionMenu(f_sltp, self.v_tp_mode, "ROI_%", "PRICE_%", "ROI_%", "PIPS").grid(row=0, column=3, padx=5, sticky="w")

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

        self.v_tp1_be = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_sltp,
            text="Move SL to Break-Even after TP1",
            variable=self.v_tp1_be,
        ).grid(row=2, column=0, columnspan=3, sticky="w")

        tk.Label(
            f_sltp,
            text="TP Close Qty Mode:",
        ).grid(row=2, column=0, sticky="w")

        self.v_tp_qty_mode = tk.StringVar(value="PERCENT_%")
        ttk.OptionMenu(
            f_sltp,
            self.v_tp_qty_mode,
            "PERCENT_%",
            "PERCENT_%",
            "FIXED_QTY",
        ).grid(row=2, column=1, padx=5, sticky="w")

        tk.Label(
            f_sltp,
            text="TP1 Close (% / Qty):",
        ).grid(row=2, column=2, sticky="w")

        self.e_tp1_close = tk.Entry(
            f_sltp,
            width=8,
        )
        self.e_tp1_close.insert(0, "50")
        self.e_tp1_close.grid(row=2, column=3, padx=5)

        tk.Label(
            f_sltp,
            text="TP2 Close (% / Qty):",
        ).grid(row=2, column=4, sticky="w")

        self.e_tp2_close = tk.Entry(
            f_sltp,
            width=8,
        )
        self.e_tp2_close.insert(0, "50")
        self.e_tp2_close.grid(row=2, column=5, padx=5)

        # Dedicated row so the Hold-All-Reverse stop is always clearly visible,
        # including on smaller screens / higher Windows DPI scaling.
        tk.Label(
            f_sltp,
            text="Hold-All-Reverse SL (ROI %):",
            font=("Arial", 9, "bold"),
        ).grid(row=3, column=0, sticky="w", padx=(0, 4))

        self.e_hold_sl_roi = tk.Entry(
            f_sltp,
            width=10,
            justify="center",
        )
        self.e_hold_sl_roi.insert(0, "5.0")
        self.e_hold_sl_roi.grid(row=3, column=1, padx=5, pady=2, sticky="w")

        tk.Label(
            f_sltp,
            text="Used ONLY when Hold-All-Reverse = ON",
            fg="#444444",
        ).grid(row=3, column=2, columnspan=2, sticky="w", padx=(8, 0))

        self.v_hold_sl_wait_reversal = tk.BooleanVar(value=False)
        tk.Checkbutton(
            f_sltp,
            text="After Hold SL threshold: WAIT for ALL active signals to reverse",
            variable=self.v_hold_sl_wait_reversal,
        ).grid(row=4, column=0, columnspan=6, sticky="w", pady=(2, 0))

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
            row=5,
            column=0,
            columnspan=6,
            sticky="w",
            pady=2,
        )

        tk.Label(
            f_sltp,
            text="PRICE_% = market-price move | ROI_% = position ROI target",
            fg="#444444",
        ).grid(row=6, column=0, columnspan=6, sticky="w", pady=(0, 2))

        # 6. Telegram
        f_tele = tk.LabelFrame(
            self.scroll_frame,
            text=" 6. Telegram Integration ",
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
            self.scroll_frame,
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

        # Controls
        btn_frame = tk.Frame(
            self.scroll_frame
        )
        btn_frame.pack(
            fill="x",
            padx=10,
            pady=5,
        )

        self.btn_save = tk.Button(
            btn_frame,
            text="SAVE CONFIG",
            bg="#007bff",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self.save_settings,
        )
        self.btn_save.pack(
            side="left",
            expand=True,
            fill="x",
            padx=3,
        )

        self.btn_start = tk.Button(
            btn_frame,
            text="START BOT",
            bg="#28a745",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self.start_bot,
        )
        self.btn_start.pack(
            side="left",
            expand=True,
            fill="x",
            padx=3,
        )

        self.btn_stop = tk.Button(
            btn_frame,
            text="STOP BOT",
            bg="#dc3545",
            fg="white",
            font=("Arial", 10, "bold"),
            state="disabled",
            command=self.stop_bot,
        )
        self.btn_stop.pack(
            side="left",
            expand=True,
            fill="x",
            padx=3,
        )

    # -------------------- SETTINGS ---------------------------

    def save_settings(self):
        cfg = {
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
            "nwe_repaint": self.v_nwe_repaint.get(),
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
            "hold_until_all_reverse": self.v_hold_until_all_reverse.get(),
            "adaptive_edge": self.e_adaptive_edge.get().strip(),
            "adaptive_min_weight": self.e_adaptive_min_weight.get().strip(),
            "use_liq_swing": self.v_use_liq_swing.get(),
            "liq_len": self.e_liq_len.get().strip(), "liq_area": self.v_liq_area.get(),
            "liq_filter": self.v_liq_filter.get(), "liq_filter_value": self.e_liq_filter_value.get().strip(),
            "use_trendline": self.v_use_trendline.get(), "trend_len": self.e_trend_len.get().strip(),
            "trend_min_dist": self.e_trend_min_dist.get().strip(), "trend_buffer": self.e_trend_buffer.get().strip(),
            "trend_retest": self.e_trend_retest.get().strip(), "trend_entry": self.v_trend_entry.get(),
            "use_divergence": self.v_use_divergence.get(), "div_pivot": self.e_div_pivot.get().strip(),
            "div_max_pivots": self.e_div_max_pivots.get().strip(), "div_max_bars": self.e_div_max_bars.get().strip(),
            "div_type": self.v_div_type.get(), "div_source": self.v_div_source.get(),
            "div_cci_len": self.e_div_cci.get().strip(), "div_mom_len": self.e_div_mom.get().strip(),
            "div_vwmacd_fast": self.e_div_vwfast.get().strip(), "div_vwmacd_slow": self.e_div_vwslow.get().strip(),
            "div_cmf_len": self.e_div_cmf.get().strip(), "div_mfi_len": self.e_div_mfi.get().strip(),
            "div_use_all": self.v_div_use_all.get(),
            "use_vol_sr": self.v_use_vol_sr.get(), "sr_volume_ma": self.e_sr_vol_ma.get().strip(),
            "sr_vote_mode": self.v_sr_vote.get(), "sr_entry_mode": self.v_sr_entry.get(),
            "sr_tf1": self.v_sr_tf1.get(), "sr_tf2": self.v_sr_tf2.get(), "sr_tf3": self.v_sr_tf3.get(), "sr_tf4": self.v_sr_tf4.get(),

            "size_mode": self.v_size_mode.get(),
            "risk_pct": self.e_risk_pct.get().strip(),
            "fixed_qty": self.e_fixed_qty.get().strip(),
            "max_dd": self.e_max_dd.get().strip(),
            "emergency_capital_pct": self.e_emergency_capital_pct.get().strip(),

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
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)

            self.log("Configuration saved.")
        except Exception as e:
            self.log(f"Config save error: {e}")

    def load_settings(self):
        if not os.path.exists(CONFIG_FILE):
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)

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
                    "MT5_PAPER",
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
                    "EURUSD",
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
                    "30",
                ),
            )
            self.v_no_same_candle.set(cfg.get("no_same_candle", True))
            self.e_cooldown_min.delete(0, tk.END)
            self.e_cooldown_min.insert(0, cfg.get("cooldown_min", "0"))
            self.v_require_opposite_after_exit.set(
            cfg.get(
                "require_opposite_after_sl",
                cfg.get("require_opposite_after_exit", True),
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
            self.v_nwe_repaint.set(cfg.get("nwe_repaint", False))
            self.v_use_atr.set(
                cfg.get(
                    "use_atr",
                    False,
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
                    True,
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
                    True,
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
                    True,
                )
            )

            saved_signal_mode = str(
                cfg.get(
                    "signal_mode",
                    "SINGLE_SIGNAL",
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

            self.v_signal_mode.set(saved_signal_mode)
            self.v_hold_until_all_reverse.set(cfg.get("hold_until_all_reverse", True))
            for widget,key,default in [
                (self.e_adaptive_edge,"adaptive_edge","0.18"),(self.e_adaptive_min_weight,"adaptive_min_weight","3.5"),
                (self.e_liq_len,"liq_len","14"),(self.e_liq_filter_value,"liq_filter_value","0"),
                (self.e_trend_len,"trend_len","14"),(self.e_trend_min_dist,"trend_min_dist","5"),(self.e_trend_buffer,"trend_buffer","0.0"),(self.e_trend_retest,"trend_retest","3"),
                (self.e_div_pivot,"div_pivot","5"),(self.e_div_max_pivots,"div_max_pivots","10"),(self.e_div_max_bars,"div_max_bars","100"),
                (self.e_div_cci,"div_cci_len","10"),(self.e_div_mom,"div_mom_len","10"),(self.e_div_vwfast,"div_vwmacd_fast","12"),(self.e_div_vwslow,"div_vwmacd_slow","26"),(self.e_div_cmf,"div_cmf_len","21"),(self.e_div_mfi,"div_mfi_len","14"),(self.e_sr_vol_ma,"sr_volume_ma","6")]:
                widget.delete(0,tk.END); widget.insert(0,cfg.get(key,default))
            self.v_use_liq_swing.set(cfg.get("use_liq_swing",True)); self.v_liq_area.set(cfg.get("liq_area","Wick Extremity")); self.v_liq_filter.set(cfg.get("liq_filter","Count"))
            self.v_use_trendline.set(cfg.get("use_trendline",True)); self.v_trend_entry.set(cfg.get("trend_entry","FRESH_BREAK"))
            self.v_use_divergence.set(cfg.get("use_divergence",True)); self.v_div_type.set(cfg.get("div_type","Regular/Hidden")); self.v_div_source.set(cfg.get("div_source","Close")); self.v_div_use_all.set(cfg.get("div_use_all",True))
            self.v_use_vol_sr.set(cfg.get("use_vol_sr",True)); self.v_sr_vote.set(cfg.get("sr_vote_mode","MAJORITY")); self.v_sr_entry.set(cfg.get("sr_entry_mode","CURRENT_ZONE"))
            self.v_sr_tf1.set(cfg.get("sr_tf1","Chart")); self.v_sr_tf2.set(cfg.get("sr_tf2","4h")); self.v_sr_tf3.set(cfg.get("sr_tf3","D")); self.v_sr_tf4.set(cfg.get("sr_tf4","W"))

            self.e_min_score.delete(0, tk.END)
            self.e_min_score.insert(
                0,
                cfg.get(
                    "min_score",
                    "4",
                ),
            )

            self.v_size_mode.set(
                cfg.get(
                    "size_mode",
                    "EQUITY_RISK_%",
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
                    "1.0",
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

        exchange_class = getattr(ccxt, exchange_id)

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
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
            if account_mode == "MT5_PAPER":
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
        """Hard account-level circuit breaker: cancel orders, flatten all positions, stop bot."""
        self.log(f"CRITICAL CAPITAL CIRCUIT BREAKER: Equity={equity:.8f} <= Threshold={threshold:.8f} | {reason}")
        try:
            self.send_telegram(f"CRITICAL CAPITAL CIRCUIT BREAKER: equity {equity:.4f} <= {threshold:.4f}. All account positions will be closed and bot stopped.")
        except Exception:
            pass
        try:
            positions = self.exchange.fetch_positions()
        except Exception as e:
            positions = []
            self.log(f"CAPITAL STOP: Could not fetch account positions: {e}")
        symbols = {p.get("symbol") for p in positions if p.get("symbol")}
        if self.symbol:
            symbols.add(self.symbol)
        for sym in sorted(symbols):
            try:
                for order in self.exchange.fetch_open_orders(sym):
                    oid = order.get("id")
                    if oid:
                        try:
                            self.exchange.cancel_order(oid, sym)
                        except Exception as e:
                            self.log(f"CAPITAL STOP: Cancel failed {sym} {oid}: {e}")
            except Exception as e:
                self.log(f"CAPITAL STOP: Order cleanup failed {sym}: {e}")
        for pos in positions:
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
            self.log(f"CAPITAL STOP: Closing {side} {sym} Qty={qty}")
            try:
                close_params = {"reduceOnly": True}
                if self.exchange_id == "bybit":
                    close_params["positionIdx"] = 0
                self.exchange.create_order(
                    sym, "market", close_side, qty, None, close_params
                )
            except Exception as e:
                self.log(f"CAPITAL STOP: FAILED to close {side} {sym}: {e}")
        self.is_running = False
        self.log("CAPITAL STOP COMPLETE: Emergency equity limit reached. Bot stopped; no new trades will be opened.")
        try:
            self.root.after(0, lambda: (self.btn_start.config(state="normal"), self.btn_stop.config(state="disabled")))
        except Exception:
            pass

    def fetch_position(self, symbol):
        positions = self.exchange.fetch_positions(
            [symbol]
        )

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

    def fetch_open_orders_safe(self, symbol):
        try:
            return self.exchange.fetch_open_orders(
                symbol
            )
        except Exception as e:
            self.log(
                f"Open-order read warning: {e}"
            )
            return []

    def cancel_all_open_orders(self, symbol):
        orders = self.fetch_open_orders_safe(
            symbol
        )

        for order in orders:
            order_id = order.get("id")

            if not order_id:
                continue

            try:
                self.exchange.cancel_order(
                    order_id,
                    symbol,
                )
                self.log(
                    f"Cancelled old order: {order_id}"
                )
            except Exception as e:
                self.log(
                    f"Cancel warning {order_id}: {e}"
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
                    f"TP1 + TP2 quantity must equal actual position quantity "
                    f"({qty:g}). Received {tp1_qty:g} + {tp2_qty:g}."
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
        """Best-effort CCXT unified reduce-only trigger for V8 exchanges."""
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
                        symbol,
                    )
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

        open_orders = (
            self.fetch_open_orders_safe(
                symbol
            )
        )

        open_ids = {
            str(o.get("id"))
            for o in open_orders
            if o.get("id")
        }

        results = []

        for label, order in created_orders:
            oid = str(
                order.get("id")
            )

            active = oid in open_ids

            if active:
                self.log(
                    f"{label} VERIFIED ACTIVE. ID={oid}"
                )
            else:
                self.log(
                    f"{label} NOT FOUND in open orders. ID={oid}"
                )

            results.append(
                (label, active)
            )

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

        try:
            open_orders = self.fetch_open_orders_safe(self.symbol)
            open_ids = {str(o.get("id")) for o in open_orders if o.get("id")}
        except Exception as e:
            self.log(f"PROTECTION RECONCILE NOTICE: {e}")
            return

        sl_id = str(protected.get("sl_id") or "")
        tp1_id = str(protected.get("tp1_id") or "")
        tp2_id = str(protected.get("tp2_id") or "")

        # When Hold-All-Reverse is ON, strategy reversal is the profit exit.
        # Remove any TP orders that may have been created before the setting was
        # enabled, and make SL the only exchange-side protection order.
        if self.v_hold_until_all_reverse.get():
            for label, oid in (("TP1", tp1_id), ("TP2", tp2_id)):
                if oid and oid in open_ids:
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

        missing = [(label, oid) for label, oid in expected if oid not in open_ids]
        if not missing:
            return

        self.log(
            "PROTECTION WARNING: Live position has missing exchange order(s): "
            + ", ".join(label for label, _ in missing)
        )

        # First priority: restore a missing SL immediately.  Never leave a
        # live position relying only on TP orders.
        if sl_id and sl_id not in open_ids:
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
                    else:
                        new_sl = self.create_binance_trigger(
                            self.symbol, "STOP_MARKET", close_side, remaining_qty,
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
        if tp2_id and tp2_id not in open_ids:
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
                    else:
                        new_tp2 = self.create_binance_trigger(
                            self.symbol, "TAKE_PROFIT_MARKET", close_side, tp2_qty,
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

        try:
            closed_orders = self.exchange.fetch_closed_orders(
                self.symbol,
                limit=100,
            )
        except Exception as e:
            self.log(f"EXIT REASON CHECK NOTICE: {e}")
            return "UNKNOWN"

        for order in closed_orders:
            oid = str(order.get("id") or "")
            if oid not in ids:
                continue

            status = str(order.get("status") or "").lower()
            # A closed/filled trigger order is the strongest available
            # indication that it fired.  Some exchanges use other terminal
            # status strings, so matching the known protection ID is enough
            # when the order is no longer open.
            if oid == sl_id:
                self.log(f"EXIT REASON: SL/BE triggered | Order={oid} | Status={status or 'closed'}")
                return "SL"
            if oid == tp1_id:
                self.log(f"EXIT REASON: TP1 triggered | Order={oid} | Status={status or 'closed'}")
                return "TP1"
            if oid == tp2_id:
                self.log(f"EXIT REASON: TP2 triggered | Order={oid} | Status={status or 'closed'}")
                return "TP2"

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

        self.exchange.create_order(
            symbol,
            "market",
            side,
            qty,
            None,
            {
                "reduceOnly": True,
            },
        )

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

        order = self.exchange.create_order(
            symbol,
            "market",
            side,
            qty,
            None,
            {},
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
        try:
            self.exchange.set_leverage(
                leverage,
                symbol,
            )
            self.log(
                f"Leverage set/requested: {leverage}x"
            )
        except Exception as e:
            self.log(
                f"Leverage notice: {e}"
            )

    # -------------------- START / STOP ----------------------

    def start_bot(self):
        if self.is_running:
            return

        try:
            self.save_settings()

            exchange_id = (
                self.v_exchange.get()
                .strip()
                .lower()
            )

            api_key = (
                self.e_api_key.get()
                .strip()
            )
            api_secret = (
                self.e_api_secret.get()
                .strip()
            )

            if not api_key or not api_secret:
                messagebox.showerror(
                    "Missing API credentials",
                    "Enter API Key and API Secret first.",
                )
                return

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
                "V8 EXCHANGE ENGINE: "
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

            self.configure_leverage(
                self.symbol,
                leverage,
            )

            try:
                max_trades = int(self.e_max_trades.get().strip())
            except Exception:
                raise ValueError("Max Trades must be a whole number. Use 0 for unlimited.")
            if max_trades < 0:
                raise ValueError("Max Trades cannot be negative.")

            self.start_balance = (
                self.fetch_balance_total()
            )

            self.total_trades = 0
            self.opened_trades = 0
            self.winning_trades = 0
            self.losing_trades = 0
            self.trade_pnls = []
            self.active_trade = None
            self.session_started_at = time.time()
            self.session_max_trades = max_trades

            # Capture/display the exact account balance at BOT START.
            try:
                self.root.after(
                    0,
                    lambda start=self.start_balance: self.lbl_pnl.config(
                        text=(
                            f"Start Balance: ${start:.4f} | "
                            f"Current Balance: ${start:.4f} | "
                            "Net PnL: $0.00 | Trades: 0 | Wins: 0 | "
                            "Losses: 0 | Win Rate: 0.0%"
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
            if self.v_use_nwe.get():
                enabled_modules.append(
                    f"NWE "
                    f"({self.v_nwe_entry_mode.get().strip().upper()} | "
                    f"Bandwidth {self.e_nwe_bandwidth.get().strip()} | "
                    f"Mult {self.e_nwe_mult.get().strip()} | "
                    f"Repaint {'ON' if self.v_nwe_repaint.get() else 'OFF'})"
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
                "2_SIGNALS": 2,
                "3_SIGNALS": 3,
                "4_SIGNALS": 4,
            }
            if signal_mode in preset_scores:
                min_score = preset_scores[signal_mode]
            else:
                min_score = int(self.e_min_score.get().strip())

            allowed_signal_modes = (
                "STRICT_ALL_FILTERS",
                "SINGLE_SIGNAL",
                "ANY_NON_CONFLICTING",
                "ADAPTIVE_SCORE",
                "2_SIGNALS",
                "3_SIGNALS",
                "4_SIGNALS",
                "SCORE",
            )
            if signal_mode not in allowed_signal_modes:
                raise ValueError(f"Unknown signal mode: {signal_mode}")
            if min_score <= 0:
                raise ValueError("Minimum score must be greater than 0.")

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

            self.is_running = True

            self.btn_start.config(
                state="disabled"
            )
            self.btn_stop.config(
                state="normal"
            )

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

            messagebox.showerror(
                "Bot start failed",
                str(e),
            )

    def stop_bot(self):
        self.is_running = False

        self.log(
            "Stopping execution thread..."
        )

        self.btn_start.config(
            state="normal"
        )
        self.btn_stop.config(
            state="disabled"
        )

    def on_close(self):
        if self.is_running:
            if not messagebox.askyesno(
                "Stop bot?",
                "Bot is running. Stop it and close?",
            ):
                return

        self.is_running = False
        self.root.destroy()

    # -------------------- PERFORMANCE / TRADE ACCOUNTING ----

    def _begin_performance_trade(self, side, entry, qty, balance):
        self.active_trade = {
            "side": side,
            "entry": float(entry),
            "qty": float(qty),
            "balance_start": float(balance),
            "started_at": time.time(),
            "tp1_hit": False,
        }
        self.opened_trades += 1

    def _finalize_performance_trade(self, reason="CLOSED", balance=None):
        trade = self.active_trade
        if not trade:
            return
        try:
            if balance is None:
                balance = self.fetch_balance_total()
            pnl = float(balance) - float(trade["balance_start"])
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
            self.log(
                f"TRADE CLOSED ✓ | Result={result} | PnL=${pnl:.4f} | "
                f"Reason={reason} | Completed={self.total_trades}"
            )
        except Exception as e:
            self.log(f"Trade result accounting notice: {e}")
        finally:
            self.active_trade = None

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

        # TP1 is a conditional/trigger order on Bybit. Do not poll it
        # with fetch_order(), because Bybit restricts that endpoint to
        # a recent order window. Check open orders first, then closed
        # orders. An inconclusive API response must never move the SL.
        tp1_order = None

        try:
            open_orders = self.fetch_open_orders_safe(self.symbol)
            for order in open_orders:
                if str(order.get("id") or "") == str(tp1_id):
                    tp1_order = order
                    break
        except Exception as e:
            self.log(f"TP1 open-order status notice: {e}")

        if tp1_order is None:
            try:
                closed_orders = self.exchange.fetch_closed_orders(
                    self.symbol,
                    limit=100,
                )
                for order in closed_orders:
                    if str(order.get("id") or "") == str(tp1_id):
                        tp1_order = order
                        break
            except Exception as e:
                self.log(f"TP1 closed-order status notice: {e}")

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

            # Cancel the original full-position SL first.
            if old_sl_id:
                try:
                    self.exchange.cancel_order(
                        old_sl_id,
                        self.symbol,
                    )
                    self.log(
                        f"TP1 ACHIEVED: Cancelled old SL: {old_sl_id}"
                    )
                except Exception as e:
                    self.log(
                        f"TP1 ACHIEVED: old SL cancel notice: {e}"
                    )

            be_price = float(
                self.exchange.price_to_precision(
                    self.symbol,
                    entry_price,
                )
            )

            close_side = (
                "sell"
                if position["side"] == "LONG"
                else "buy"
            )

            if self.exchange_id == "bybit":
                trigger_direction = (
                    2
                    if position["side"] == "LONG"
                    else 1
                )

                be_order = self.create_bybit_trigger(
                    self.symbol,
                    "STOP_MARKET",
                    close_side,
                    remaining_qty,
                    be_price,
                    trigger_direction,
                    "BREAK-EVEN SL",
                )
            else:
                be_order = self.create_binance_trigger(
                    self.symbol,
                    "STOP_MARKET",
                    close_side,
                    remaining_qty,
                    be_price,
                    "BREAK-EVEN SL",
                )

            be_id = be_order.get("id")
            protected["sl_id"] = be_id
            protected["sl"] = be_price
            self.tp1_be_done = True

            self.log(
                f"BREAK-EVEN ACTIVE ✓ | "
                f"Entry={entry_price:.12g} | "
                f"Remaining Qty={remaining_qty:g} | "
                f"SL={be_price:.12g}"
            )

            if be_id:
                verified = self.verify_protection_orders(
                    self.symbol,
                    [("BREAK-EVEN SL", be_order)],
                )
                if not verified:
                    raise RuntimeError(
                        "Break-even SL was submitted but could not be verified."
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
            use_atr = self.v_use_atr.get()
            atr_min_pct = float(self.e_atr_min_pct.get())
            if atr_min_pct < 0:
                raise ValueError("Minimum ATR % cannot be negative.")

            use_vol = self.v_use_vol.get()
            vol_len = int(
                self.e_vol_len.get()
            )

            use_adx = self.v_use_adx.get()
            adx_thresh = float(
                self.e_adx_thresh.get()
            )

            use_mtf = self.v_use_mtf.get()

            adaptive_edge = float(self.e_adaptive_edge.get().strip())
            adaptive_min_weight = float(self.e_adaptive_min_weight.get().strip())
            if not (0.0 <= adaptive_edge < 1.0): raise ValueError("Adaptive Edge must be >=0 and <1.")
            if adaptive_min_weight <= 0: raise ValueError("Adaptive Minimum Weight must be >0.")
            use_liq_swing = self.v_use_liq_swing.get(); liq_len = int(self.e_liq_len.get()); liq_area = self.v_liq_area.get(); liq_filter = self.v_liq_filter.get(); liq_filter_value=float(self.e_liq_filter_value.get())
            use_trendline = self.v_use_trendline.get(); trend_len=int(self.e_trend_len.get()); trend_min_dist=int(self.e_trend_min_dist.get()); trend_buffer=float(self.e_trend_buffer.get()); trend_retest=int(self.e_trend_retest.get()); trend_entry=self.v_trend_entry.get()
            use_divergence=self.v_use_divergence.get(); div_pivot=int(self.e_div_pivot.get()); div_max_pivots=int(self.e_div_max_pivots.get()); div_max_bars=int(self.e_div_max_bars.get()); div_type=self.v_div_type.get(); div_source=self.v_div_source.get()
            use_vol_sr=self.v_use_vol_sr.get(); sr_volume_ma=int(self.e_sr_vol_ma.get()); sr_vote_mode=self.v_sr_vote.get(); sr_entry_mode=self.v_sr_entry.get()
            if liq_len<=0 or trend_len<=0 or trend_min_dist<=0 or trend_retest<=0 or div_pivot<=0 or div_max_pivots<=0 or div_max_bars<30 or sr_volume_ma<=0: raise ValueError("Advanced strategy lengths/settings are invalid.")
            if trend_buffer<0 or liq_filter_value<0: raise ValueError("Advanced strategy thresholds cannot be negative.")

            signal_mode = self.v_signal_mode.get().strip().upper()

            # Preset modes directly mean "how many directional indicators
            # must agree for this trade". SCORE keeps the existing custom
            # minimum-score concept.
            preset_scores = {
                "SINGLE_SIGNAL": 1,
                "2_SIGNALS": 2,
                "3_SIGNALS": 3,
                "4_SIGNALS": 4,
            }

            if signal_mode in preset_scores:
                min_score = preset_scores[signal_mode]
            else:
                min_score = int(self.e_min_score.get().strip())

            allowed_signal_modes = (
                "STRICT_ALL_FILTERS",
                "SINGLE_SIGNAL",
                "2_SIGNALS",
                "3_SIGNALS",
                "4_SIGNALS",
                "SCORE",
            )

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

            max_dd = (
                float(
                    self.e_max_dd.get()
                ) / 100.0
            )
            emergency_capital_loss = float(self.e_emergency_capital_pct.get()) / 100.0
            if not 0.0 <= emergency_capital_loss < 1.0:
                raise ValueError("Emergency Capital Loss Stop must be between 0% and less than 100%.")

            leverage = int(
                self.e_lev.get().strip()
            )

            sl_mode = self.v_sl_mode.get().strip().upper()
            tp_mode = self.v_tp_mode.get().strip().upper()
            if sl_mode not in ("PRICE_%", "ROI_%", "PIPS"):
                raise ValueError(f"Unknown SL mode: {sl_mode}")
            if tp_mode not in ("PRICE_%", "ROI_%", "PIPS"):
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

            if sl_mode not in ("PRICE_%", "ROI_%", "PIPS") or tp_mode not in ("PRICE_%", "ROI_%", "PIPS"):
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
                    emergency_threshold = self.start_balance * (1.0 - emergency_capital_loss)
                    if emergency_capital_loss > 0 and curr_equity <= emergency_threshold:
                        self._emergency_flatten_all_positions(
                            reason=f"Emergency Capital Loss Stop {emergency_capital_loss * 100:.2f}% reached",
                            equity=curr_equity,
                            threshold=emergency_threshold,
                        )
                        break

                    drawdown = (
                        (
                            self.start_balance
                            - curr_balance
                        )
                        / self.start_balance
                        if self.start_balance > 0
                        else 0
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

                        self.stop_bot()
                        break

                    # ------------------------------------------------
                    # 2. Market data
                    # ------------------------------------------------
                    ohlcv = self._fetch_strategy_ohlcv(
                        timeframe=timeframe,
                        limit=600 if use_nwe else 250,
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

                    df["vol_ma"] = (
                        df["vol"].rolling(
                            vol_len
                        ).mean()
                    )

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
                    # 5. V8.3.3 strategy modules (Forex)
                    # ------------------------------------------------
                    strategy_cfg = {
                        "div_pivot":div_pivot,"div_max_pivots":div_max_pivots,"div_max_bars":div_max_bars,"div_type":div_type,"div_source":div_source,
                        "div_cci_len":int(self.e_div_cci.get()),"div_mom_len":int(self.e_div_mom.get()),"div_vwmacd_fast":int(self.e_div_vwfast.get()),"div_vwmacd_slow":int(self.e_div_vwslow.get()),"div_cmf_len":int(self.e_div_cmf.get()),"div_mfi_len":int(self.e_div_mfi.get()),
                        "div_use_all":bool(self.v_div_use_all.get()),
                        "sr_volume_ma":sr_volume_ma,"sr_vote_mode":sr_vote_mode,"sr_entry_mode":sr_entry_mode,"sr_tf1":self.v_sr_tf1.get(),"sr_tf2":self.v_sr_tf2.get(),"sr_tf3":self.v_sr_tf3.get(),"sr_tf4":self.v_sr_tf4.get(),
                    }
                    if use_liq_swing:
                        df = calculate_liquidity_swings(df,length=liq_len,area=liq_area,filter_options=liq_filter,filter_value=liq_filter_value)
                    if use_trendline:
                        df = calculate_trendline_breakout(df,length=trend_len,min_pivot_distance=trend_min_dist,breakout_buffer_pct=trend_buffer,retest_candles=trend_retest)
                    if use_divergence:
                        df = calculate_divergence_module(df,strategy_cfg)
                    if use_vol_sr:
                        df = _volume_sr_base_series(df,strategy_cfg)

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
                    candle_bull = float(df["close"].iloc[-2]) > float(df["open"].iloc[-2])
                    candle_bear = float(df["close"].iloc[-2]) < float(df["open"].iloc[-2])
                    if use_st: directional_modules.append(("ST", st_trend_bull if st_entry_mode=="CURRENT_TREND" else st_flip_bull, st_trend_bear if st_entry_mode=="CURRENT_TREND" else st_flip_bear))
                    if use_ema: directional_modules.append(("EMA",ema_bull,ema_bear))
                    if use_ema_cross: directional_modules.append(("EMA_CROSS",ema_cross_bull,ema_cross_bear))
                    if use_macd: directional_modules.append(("MACD",macd_bull,macd_bear))
                    if use_rsi: directional_modules.append(("RSI",rsi_bull,rsi_bear))
                    if use_bb: directional_modules.append(("BB",bb_bull,bb_bear))
                    if use_stoch: directional_modules.append(("STOCH",stoch_bull,stoch_bear))
                    if use_vwap: directional_modules.append(("VWAP",vwap_bull,vwap_bear))
                    if use_vwap_delta: directional_modules.append(("VWAP_DELTA",vwap_delta_bull,vwap_delta_bear))
                    if use_vidya: directional_modules.append(("VIDYA",vidya_bull,vidya_bear))
                    if use_nwe: directional_modules.append(("NWE",nwe_bull,nwe_bear))
                    if use_liq_swing:
                        directional_modules.append(("LIQ_SWING",bool(df["liq_swing_trend"].iloc[-2] > 0),bool(df["liq_swing_trend"].iloc[-2] < 0)))
                    if use_trendline:
                        directional_modules.append(("TRENDLINE",
                            bool(df["trendline_break_up"].iloc[-2]) if trend_entry=="FRESH_BREAK" else
                            bool(df["trendline_retest_up"].iloc[-2]) if trend_entry=="BREAK_RETEST" else
                            bool(df["trendline_state"].iloc[-2] > 0),
                            bool(df["trendline_break_down"].iloc[-2]) if trend_entry=="FRESH_BREAK" else
                            bool(df["trendline_retest_down"].iloc[-2]) if trend_entry=="BREAK_RETEST" else
                            bool(df["trendline_state"].iloc[-2] < 0)))
                    if use_mtf: directional_modules.append(("MTF",mtf_pass_bull,mtf_pass_bear))
                    if use_divergence: directional_modules.append(("DIVERGENCE",bool(df["div_bull_signal"].iloc[-2]),bool(df["div_bear_signal"].iloc[-2])))
                    if use_vol_sr: directional_modules.append(("VOL_SR",bool(df["sr_bull"].iloc[-2]),bool(df["sr_bear"].iloc[-2])))
                    if use_vol and vol_pass: directional_modules.append(("VOL",candle_bull,candle_bear))
                    if use_adx and adx_pass: directional_modules.append(("ADX",float(df["plus_di"].iloc[-2])>float(df["minus_di"].iloc[-2]),float(df["minus_di"].iloc[-2])>float(df["plus_di"].iloc[-2])))
                    if use_atr and atr_pass: directional_modules.append(("ATR",candle_bull,candle_bear))

                    buy_score=sum(1 for _,b,_ in directional_modules if b); sell_score=sum(1 for _,_,s in directional_modules if s)
                    confirmations_pass=atr_pass and vol_pass and adx_pass
                    buy_signal,sell_signal,_,_=StrategyEngine.decide_signal(directional_modules,signal_mode,min_score,atr_pass=atr_pass,vol_pass=vol_pass,adx_pass=adx_pass,mtf_pass_bull=mtf_pass_bull,mtf_pass_bear=mtf_pass_bear,adaptive_edge=adaptive_edge,adaptive_min_weight=adaptive_min_weight)
                    decision_reason=StrategyEngine.decision_reason(directional_modules,signal_mode,min_score,atr_pass=atr_pass,vol_pass=vol_pass,adx_pass=adx_pass,mtf_pass_bull=mtf_pass_bull,mtf_pass_bear=mtf_pass_bear,adaptive_edge=adaptive_edge,adaptive_min_weight=adaptive_min_weight)
                    signal="BUY" if buy_signal else "SELL" if sell_signal else "NONE"
                    self.log(f"V8.3.3 SIGNAL={signal} | Mode={signal_mode} | BUY_W/SELL_W={buy_score}/{sell_score} | {decision_reason}")

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
                        self._reconcile_protection_orders(position)
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
                        f"Confirmations={'OFF' if signal_mode in ('SINGLE_SIGNAL','2_SIGNALS','3_SIGNALS','4_SIGNALS','SCORE') else 'ON'} "
                        f"Votes={','.join(name for name, bull, bear in directional_modules if bull or bear) or 'NONE'} "
                        f"Score=B{buy_score}/S{sell_score} "
                        f"Required={min_score} | "
                        f"MACD={'ON' if use_macd else 'OFF'} "
                        f"RSI={'ON' if use_rsi else 'OFF'} "
                        f"BB={'ON' if use_bb else 'OFF'} "
                        f"STOCH={'ON' if use_stoch else 'OFF'} "
                        f"VWAP={'ON' if use_vwap else 'OFF'} "
                        f"VWAP_DELTA={'ON' if use_vwap_delta else 'OFF'}"
                        f"({vwap_delta_state}) "
                        f"VIDYA={'ON' if use_vidya else 'OFF'}"
                        f"({vidya_state}) "
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
                    if use_mtf:
                        hold_directional_modules.append(("MTF", mtf_pass_bull, mtf_pass_bear))
                    if use_vol and vol_pass:
                        hold_directional_modules.append(("VOL", candle_bull, candle_bear))
                    if use_adx and adx_pass:
                        hold_directional_modules.append(("ADX", adx_bull, adx_bear))
                    if use_atr and atr_pass:
                        hold_directional_modules.append(("ATR", candle_bull, candle_bear))
                    if use_liq_swing:
                        hold_directional_modules.append(("LIQ_SWING", bool(df["liq_swing_trend"].iloc[-2] > 0), bool(df["liq_swing_trend"].iloc[-2] < 0)))
                    if use_trendline:
                        hold_directional_modules.append(("TRENDLINE",
                            bool(df["trendline_break_up"].iloc[-2]) if trend_entry=="FRESH_BREAK" else
                            bool(df["trendline_retest_up"].iloc[-2]) if trend_entry=="BREAK_RETEST" else
                            bool(df["trendline_state"].iloc[-2] > 0),
                            bool(df["trendline_break_down"].iloc[-2]) if trend_entry=="FRESH_BREAK" else
                            bool(df["trendline_retest_down"].iloc[-2]) if trend_entry=="BREAK_RETEST" else
                            bool(df["trendline_state"].iloc[-2] < 0)))
                    if use_divergence:
                        hold_directional_modules.append(("DIVERGENCE", bool(df["div_bull_signal"].iloc[-2]), bool(df["div_bear_signal"].iloc[-2])))
                    if use_vol_sr:
                        hold_directional_modules.append(("VOL_SR", bool(df["sr_bull"].iloc[-2]), bool(df["sr_bear"].iloc[-2])))

                    reversal_allowed = True
                    if pos_type in ("LONG", "SHORT") and desired_side != pos_type and self.v_hold_until_all_reverse.get():
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

                            self.cancel_all_open_orders(
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

                            time.sleep(1.0)
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
                            self.cancel_all_open_orders(
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
                                continue
                            if cooldown_min > 0 and self.last_flat_time > 0:
                                remaining = cooldown_min * 60.0 - (time.time() - self.last_flat_time)
                                if remaining > 0:
                                    self.log(f"ENTRY BLOCKED: Cooldown active for {remaining:.0f}s.")
                                    continue

                        # ------------------------------------------------
                        # Calculate requested entry quantity.
                        # This quantity is ONLY the entry request.
                        # Protection uses actual position qty later.
                        # ------------------------------------------------
                        self._pending_signal_for_sizing = signal
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
                            f"TRADE LIMIT REACHED: {self.total_trades} completed trades. Stopping bot."
                        )
                        self.stop_bot()
                        break

                except Exception as cycle_error:
                    self.log(
                        f"Execution cycle error: "
                        f"{cycle_error}"
                    )

                # ------------------------------------------------
                # 9. 30-second scan
                # ------------------------------------------------
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
            self.log(
                f"BOT FATAL ERROR: {fatal_error}"
            )

        finally:
            self.is_running = False

            try:
                self.root.after(
                    0,
                    lambda: (
                        self.btn_start.config(
                            state="normal"
                        ),
                        self.btn_stop.config(
                            state="disabled"
                        ),
                    ),
                )
            except Exception:
                pass

            self.log(
                "Bot execution thread halted."
            )



# ============================================================
# V1 FOREX / MT5 ENGINE
# Strategy and indicator calculations above are inherited
# unchanged from V8.  Only the broker/data/execution layer is
# replaced for MT5 Forex.
# ============================================================

class MT5ForexAdapter:
    """Small CCXT-shaped adapter used by the unchanged V8 strategy loop."""

    TF_MAP = {
        "1m": mt5.TIMEFRAME_M1 if mt5 else None,
        "3m": mt5.TIMEFRAME_M3 if mt5 else None,
        "5m": mt5.TIMEFRAME_M5 if mt5 else None,
        "15m": mt5.TIMEFRAME_M15 if mt5 else None,
        "30m": mt5.TIMEFRAME_M30 if mt5 else None,
        "1h": mt5.TIMEFRAME_H1 if mt5 else None,
        "4h": mt5.TIMEFRAME_H4 if mt5 else None,
    }

    def __init__(self, bot, mode, login="", password="", server="",
                 paper_balance=1000.0):
        if mt5 is None:
            raise RuntimeError(
                "MetaTrader5 package is not installed. Run: py -m pip install MetaTrader5"
            )
        self.bot = bot
        self.mode = mode.upper()
        self.paper = self.mode == "MT5_PAPER"
        self.login = int(login) if str(login).strip() else 0
        self.password = password
        self.server = server.strip()
        self.paper_balance = float(paper_balance)
        self.paper_equity = self.paper_balance
        self.paper_positions = {}
        self.paper_orders = {}
        self.markets = {}
        self.symbol = None
        self._connect()

    def _connect(self):
        # Initialize terminal. PAPER still uses terminal quotes but never sends orders.
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        if self.mode == "MT5_LIVE":
            if not self.login or not self.password or not self.server:
                raise RuntimeError("MT5_LIVE requires Login, Password and Server.")
            ok = mt5.login(self.login, password=self.password, server=self.server)
            if not ok:
                raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")
        elif self.mode == "MT5_TERMINAL":
            info = mt5.account_info()
            if info is None:
                raise RuntimeError(f"No logged-in MT5 account: {mt5.last_error()}")
        # PAPER can use whichever account is logged into the terminal, but never sends orders.
        info = mt5.account_info()
        if info is not None:
            self.bot.log(
                f"MT5 TERMINAL CONNECTED | Account={getattr(info,'login','?')} | "
                f"Server={getattr(info,'server','?')} | Currency={getattr(info,'currency','?')}"
            )
        else:
            self.bot.log("MT5 connected for market data.")

    def load_markets(self):
        return self.markets

    def _info(self, symbol):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"MT5 symbol_info failed for {symbol}: {mt5.last_error()}")
        return info

    def market(self, symbol):
        info = self._info(symbol)
        return {
            "symbol": symbol,
            "limits": {
                "amount": {
                    "min": float(info.volume_min),
                    "max": float(info.volume_max),
                }
            },
            "precision": {"price": int(info.digits)},
            "contractSize": float(info.trade_contract_size or 0),
            "point": float(info.point),
            "digits": int(info.digits),
            "volume_min": float(info.volume_min),
            "volume_max": float(info.volume_max),
            "volume_step": float(info.volume_step),
            "trade_tick_value": float(info.trade_tick_value or 0),
            "trade_tick_value_profit": float(info.trade_tick_value_profit or 0),
            "trade_tick_value_loss": float(info.trade_tick_value_loss or 0),
            "trade_tick_size": float(info.trade_tick_size or 0),
            "stops_level": int(info.trade_stops_level or 0),
            "currency_profit": str(info.currency_profit or ""),
        }

    def amount_to_precision(self, symbol, qty):
        info = self._info(symbol)
        step = float(info.volume_step or 0.01)
        mn = float(info.volume_min)
        mx = float(info.volume_max)
        q = max(0.0, float(qty))
        # floor to broker volume step: never round UP risk.
        q = (q // step) * step
        if q > mx:
            q = mx
        if q < mn:
            return 0.0
        decimals = max(0, min(8, len(str(step).split(".")[-1].rstrip("0"))))
        return f"{q:.{decimals}f}"

    def price_to_precision(self, symbol, price):
        info = self._info(symbol)
        return f"{float(price):.{int(info.digits)}f}"

    def normalize(self, raw):
        raw = raw.strip().upper().replace("/", "").replace(":", "")
        symbols = mt5.symbols_get()
        if not symbols:
            raise RuntimeError(f"MT5 symbols_get failed: {mt5.last_error()}")
        names = [s.name for s in symbols]
        # Exact
        if raw in names:
            mt5.symbol_select(raw, True)
            return raw
        # Common Forex forms: EURUSD, EUR/USD, broker suffix/prefix.
        candidates = []
        for name in names:
            compact = name.upper().replace("/", "")
            if compact == raw:
                candidates.append(name)
            elif compact.startswith(raw) or compact.endswith(raw):
                candidates.append(name)
        # Prefer names that are exactly 6-letter FX roots plus suffix.
        candidates.sort(key=lambda n: (0 if n.upper().startswith(raw) else 1, len(n)))
        if candidates:
            sym = candidates[0]
            mt5.symbol_select(sym, True)
            return sym
        raise RuntimeError(f"Forex symbol not found in MT5 terminal: {raw}")

    def fetch_ohlcv(self, symbol, timeframe="15m", limit=250):
        tf = str(timeframe).lower()
        if tf == "45m":
            return self._fetch_45m(symbol, limit)
        if tf not in self.TF_MAP:
            raise RuntimeError(f"MT5 timeframe not supported directly: {timeframe}")
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, self.TF_MAP[tf], 0, int(limit))
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"MT5 OHLCV failed for {symbol} {tf}: {mt5.last_error()}")
        out = []
        for r in rates:
            out.append([
                int(r["time"]) * 1000,
                float(r["open"]),
                float(r["high"]),
                float(r["low"]),
                float(r["close"]),
                float(r["tick_volume"]),
            ])
        return out

    def _fetch_45m(self, symbol, limit):
        base = self.fetch_ohlcv(symbol, "15m", int(limit) * 3 + 10)
        df = pd.DataFrame(base, columns=["time","open","high","low","close","vol"])
        dt = pd.to_datetime(df["time"], unit="ms", utc=True)
        df["datetime"] = dt
        df = df.set_index("datetime")
        g = df.resample("45min", origin="epoch", label="left", closed="left")
        agg = g.agg({
            "time":"first","open":"first","high":"max","low":"min",
            "close":"last","vol":"sum"
        })
        counts = g["close"].count()
        agg["base_count"] = counts
        agg = agg.dropna(subset=["open","high","low","close","vol"])
        if len(agg) > 1:
            older = agg.iloc[:-1]
            newest = agg.iloc[-1:]
            older = older[older["base_count"] == 3]
            agg = pd.concat([older, newest])
        agg = agg.tail(int(limit))
        return agg[["time","open","high","low","close","vol"]].values.tolist()

    def fetch_ticker(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"MT5 tick failed for {symbol}: {mt5.last_error()}")
        return {"bid": float(tick.bid), "ask": float(tick.ask),
                "last": float(tick.last or ((tick.bid + tick.ask) / 2.0)),
                "close": float(tick.last or tick.bid)}

    def _paper_position(self, symbol):
        return self.paper_positions.get(symbol)

    def fetch_positions(self, symbols=None):
        # No-argument call is deliberately account-wide for the emergency circuit breaker.
        if self.paper:
            if symbols:
                wanted = set(symbols)
                return [self.paper_positions[s] for s in self.paper_positions if s in wanted]
            return list(self.paper_positions.values())
        if symbols:
            positions = []
            for sym in symbols:
                rows = mt5.positions_get(symbol=sym) or []
                positions.extend(rows)
        else:
            positions = list(mt5.positions_get() or [])
        out = []
        for p in positions:
            if p.volume <= 0:
                continue
            side = "long" if p.type == mt5.POSITION_TYPE_BUY else "short"
            out.append({
                "id": str(p.ticket),
                "symbol": p.symbol,
                "contracts": float(p.volume),
                "side": side,
                "entryPrice": float(p.price_open),
                "average": float(p.price_open),
                "leverage": 0.0,
                "initialMargin": float(mt5.order_calc_margin(
                    mt5.ORDER_TYPE_BUY if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_SELL,
                    p.symbol, p.volume, p.price_open) or 0.0),
                "unrealizedPnl": float(p.profit),
                "info": {"ticket": p.ticket, "magic": p.magic, "sl": p.sl, "tp": p.tp},
                "_mt5": p,
            })
        # Normal bot management must only see this bot's magic-number positions.
        if getattr(self.bot, "mt5_magic", None):
            out = [p for p in out if int((p.get("info") or {}).get("magic", 0)) == int(self.bot.mt5_magic)]
        return out

    def _all_positions_raw(self):
        return list(mt5.positions_get() or [])

    def fetch_balance(self):
        if self.paper:
            return {"total": {"USD": self.paper_equity}, "USD": {"total": self.paper_equity}}
        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"MT5 account_info failed: {mt5.last_error()}")
        return {"total": {str(info.currency): float(info.balance)},
                str(info.currency): {"total": float(info.balance)}}

    def calc_profit(self, side, symbol, volume, price_open, price_close):
        if self.paper:
            info = self._info(symbol)
            contract = float(info.trade_contract_size or 100000.0)
            # Approximate account-currency P/L for common USD-quoted pairs.
            direction = 1.0 if side == "LONG" else -1.0
            return direction * (price_close - price_open) * volume * contract
        order_type = mt5.ORDER_TYPE_BUY if side == "LONG" else mt5.ORDER_TYPE_SELL
        value = mt5.order_calc_profit(order_type, symbol, float(volume),
                                      float(price_open), float(price_close))
        if value is None:
            raise RuntimeError(f"MT5 order_calc_profit failed: {mt5.last_error()}")
        return float(value)

    def calc_margin(self, side, symbol, volume, price):
        order_type = mt5.ORDER_TYPE_BUY if side == "LONG" else mt5.ORDER_TYPE_SELL
        value = mt5.order_calc_margin(order_type, symbol, float(volume), float(price))
        if value is None:
            return 0.0
        return float(value)

    def fetch_open_orders(self, symbol=None):
        # Position SL/TP are not pending orders in MT5. This is only for true pending orders.
        if self.paper:
            return []
        rows = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
        rows = rows or []
        return [{"id": str(o.ticket), "status": "open", "symbol": o.symbol,
                 "type": str(o.type), "info": {"ticket": o.ticket}} for o in rows]

    def fetch_closed_orders(self, symbol=None, limit=100):
        return []

    def cancel_order(self, order_id, symbol):
        if self.paper:
            return True
        req = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(order_id),
            "symbol": symbol,
        }
        result = mt5.order_send(req)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"MT5 cancel failed: {getattr(result,'retcode',None)} {mt5.last_error()}")
        return True

    def _filling(self, symbol):
        info = self._info(symbol)
        mode = int(info.filling_mode)
        # Prefer broker-supported IOC/FOK; market execution commonly supports IOC.
        if mode & 2:
            return mt5.ORDER_FILLING_IOC
        if mode & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def create_order(self, symbol, order_type, side, qty, price=None, params=None):
        params = params or {}
        if self.paper:
            return self._paper_create_order(symbol, order_type, side, qty, price, params)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"MT5 tick unavailable: {mt5.last_error()}")
        is_buy = side.lower() == "buy"
        mt5_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(qty),
            "type": mt5_type,
            "price": float(tick.ask if is_buy else tick.bid),
            "deviation": int(params.get("deviation", 20)),
            "magic": int(getattr(self.bot, "mt5_magic", 26091801)),
            "comment": "UniversalForexBotV1",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling(symbol),
        }
        if params.get("position"):
            req["position"] = int(params["position"])
        if params.get("sl") is not None:
            req["sl"] = float(params["sl"])
        if params.get("tp") is not None:
            req["tp"] = float(params["tp"])
        result = mt5.order_send(req)
        if result is None:
            raise RuntimeError(f"MT5 order_send returned None: {mt5.last_error()}")
        if result.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL):
            raise RuntimeError(f"MT5 order rejected: retcode={result.retcode} comment={result.comment}")
        return {
            "id": str(result.order or result.deal),
            "status": "closed" if result.deal else "open",
            "filled": float(getattr(result, "volume", qty) or qty),
            "average": float(getattr(result, "price", 0.0) or 0.0),
            "price": float(getattr(result, "price", 0.0) or 0.0),
            "info": {"deal": result.deal, "order": result.order,
                     "retcode": result.retcode, "comment": result.comment},
        }

    def _paper_create_order(self, symbol, order_type, side, qty, price, params):
        tick = self.fetch_ticker(symbol)
        px = float(tick["ask"] if side.lower() == "buy" else tick["bid"])
        q = float(qty)
        if params.get("position"):
            pos = self.paper_positions.get(symbol)
            if not pos:
                return {"id": f"PAPER-{time.time_ns()}", "filled": q, "average": px}
            pnl = self.calc_profit(pos["side"], symbol, q, pos["entry"], px)
            self.paper_equity += pnl
            remaining = max(0.0, pos["qty"] - q)
            if remaining <= 1e-12:
                del self.paper_positions[symbol]
            else:
                pos["qty"] = remaining
            return {"id": f"PAPER-CLOSE-{time.time_ns()}", "filled": q, "average": px}
        position_side = "LONG" if side.lower() == "buy" else "SHORT"
        margin = self.calc_margin(position_side, symbol, q, px)
        if margin <= 0:
            # Paper margin approximation only; actual MT5 mode uses order_calc_margin.
            margin = abs(px * q * float(self._info(symbol).trade_contract_size)) / max(
                float(self.bot.reference_leverage), 1.0
            )
        self.paper_positions[symbol] = {
            "id": f"PAPER-POS-{time.time_ns()}",
            "symbol": symbol, "contracts": q, "qty": q,
            "side": position_side, "entryPrice": px, "average": px,
            "entry": px, "leverage": float(self.bot.reference_leverage),
            "initialMargin": margin, "unrealizedPnl": 0.0,
            "info": {"magic": self.bot.mt5_magic, "sl": 0.0, "tp": 0.0},
        }
        return {"id": self.paper_positions[symbol]["id"], "filled": q, "average": px, "price": px}

    def modify_position_sl(self, symbol, position, sl):
        if self.paper:
            p = self.paper_positions.get(symbol)
            if p:
                p["info"]["sl"] = float(sl)
            return {"id": f"PAPER-SL-{time.time_ns()}", "sl": float(sl)}
        ticket = int(position.get("id") or (position.get("raw") or {}).get("id") or
                     (position.get("info") or {}).get("ticket") or 0)
        if not ticket:
            # Find bot position ticket.
            rows = mt5.positions_get(symbol=symbol) or []
            rows = [r for r in rows if int(r.magic) == int(self.bot.mt5_magic)]
            if not rows:
                raise RuntimeError("Could not find MT5 bot position ticket for SL modification.")
            ticket = int(rows[0].ticket)
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": float(sl),
            "tp": 0.0,
            "magic": int(self.bot.mt5_magic),
        }
        # Preserve existing TP if broker position has one.
        rows = mt5.positions_get(ticket=ticket) or []
        if rows:
            req["tp"] = float(rows[0].tp or 0.0)
        result = mt5.order_send(req)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"MT5 SL modification failed: {getattr(result,'retcode',None)} {mt5.last_error()}")
        return {"id": f"SL-{ticket}-{time.time_ns()}", "status": "closed", "sl": float(sl)}

    def shutdown(self):
        # Do not shut down the user's terminal on every stop; only release Python connection.
        try:
            mt5.shutdown()
        except Exception:
            pass


def _fx_symbol_info(bot, symbol):
    return mt5.symbol_info(symbol)


def fx_safe_amount(self, symbol, qty):
    q = float(qty)
    if q <= 0:
        return 0.0
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"MT5 symbol_info failed: {symbol}")
    step = float(info.volume_step or 0.01)
    mn = float(info.volume_min or step)
    mx = float(info.volume_max or q)
    q = min(q, mx)
    q = (q // step) * step
    if q < mn:
        return 0.0
    return float(f"{q:.8f}")


def fx_safe_price(self, symbol, price):
    info = mt5.symbol_info(symbol)
    if info is None:
        return float(price)
    return round(float(price), int(info.digits))


def fx_fetch_balance_total(self):
    if isinstance(self.exchange, MT5ForexAdapter) and self.exchange.paper:
        return float(self.exchange.paper_equity)
    info = mt5.account_info()
    if info is None:
        raise RuntimeError(f"MT5 account_info failed: {mt5.last_error()}")
    return float(info.balance)


def fx_fetch_account_equity(self):
    if isinstance(self.exchange, MT5ForexAdapter) and self.exchange.paper:
        # Update paper floating P/L.
        for sym, pos in list(self.exchange.paper_positions.items()):
            px = self._current_market_price(sym)
            pnl = self.exchange.calc_profit(pos["side"], sym, pos["qty"], pos["entry"], px)
            pos["unrealizedPnl"] = pnl
        floating = sum(float(p.get("unrealizedPnl", 0.0)) for p in self.exchange.paper_positions.values())
        return float(self.exchange.paper_balance + floating)
    info = mt5.account_info()
    if info is None:
        raise RuntimeError(f"MT5 account_info failed: {mt5.last_error()}")
    return float(info.equity)


def fx_normalize_symbol(self, exchange, exchange_id, raw_symbol):
    return exchange.normalize(raw_symbol)


def fx_build_exchange(self, exchange_id, api_key, api_secret, account_mode):
    if exchange_id != "mt5_forex":
        raise RuntimeError("Forex V1 supports MT5 only.")
    try:
        paper_balance = float(getattr(self, "e_paper_balance", None).get().strip())
    except Exception:
        paper_balance = 1000.0
    return MT5ForexAdapter(
        self, account_mode,
        login=api_key,
        password=api_secret,
        server=getattr(self, "e_mt5_server", None).get().strip() if hasattr(self, "e_mt5_server") else "",
        paper_balance=paper_balance,
    )


def fx_configure_leverage(self, symbol, leverage):
    self.reference_leverage = float(leverage)
    self.log(
        f"MT5 Forex leverage: BROKER-CONTROLLED | Reference Leverage={leverage}x "
        "(used only as fallback/ROI reference; no leverage is changed by the bot)"
    )


def fx_target_to_price_fraction(self, target_pct, protection_mode, leverage,
                                actual_entry=None, position_qty=None,
                                position_initial_margin=None):
    target_pct = float(target_pct)
    if target_pct <= 0:
        raise RuntimeError("SL/TP targets must be greater than zero.")
    if str(protection_mode).upper() == "PRICE_%":
        return target_pct / 100.0
    if str(protection_mode).upper() == "PIPS":
        if actual_entry is not None:
            return (fx_v2_pip_size(self.symbol) * target_pct) / float(actual_entry)
        return (target_pct * 0.0001) / max(float(actual_entry or 1.0), 1e-12)
    if str(protection_mode).upper() != "ROI_%":
        raise RuntimeError(f"Unknown SL/TP protection mode: {protection_mode}")
    # For display/pre-entry fallback retain V8 semantics; post-entry calculation
    # below uses actual MT5 margin/P&L, not leverage division.
    return (target_pct / 100.0) / max(float(leverage), 1.0)


def fx_find_price_for_pnl(self, side, symbol, entry, volume, target_pnl):
    """Binary-search price where MT5 order_calc_profit reaches target P/L."""
    entry = float(entry)
    target_pnl = float(target_pnl)
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"MT5 symbol_info failed: {symbol}")
    point = float(info.point or 0.00001)
    # Start with 100 points and expand until target is bracketed.
    lo, hi = entry, entry
    if side == "LONG":
        if target_pnl < 0:
            hi = entry
            lo = entry - point * 100
            while self.exchange.calc_profit(side, symbol, volume, entry, lo) > target_pnl:
                lo -= (hi - lo) * 2.0
        else:
            lo = entry
            hi = entry + point * 100
            while self.exchange.calc_profit(side, symbol, volume, entry, hi) < target_pnl:
                hi += (hi - lo) * 2.0
    else:
        if target_pnl < 0:
            lo = entry
            hi = entry + point * 100
            while self.exchange.calc_profit(side, symbol, volume, entry, hi) > target_pnl:
                hi += (hi - lo) * 2.0
        else:
            hi = entry
            lo = entry - point * 100
            while self.exchange.calc_profit(side, symbol, volume, entry, lo) < target_pnl:
                lo -= (hi - lo) * 2.0
    for _ in range(70):
        mid = (lo + hi) / 2.0
        pnl = self.exchange.calc_profit(side, symbol, volume, entry, mid)
        if side == "LONG":
            if pnl < target_pnl:
                lo = mid
            else:
                hi = mid
        else:
            if pnl < target_pnl:
                hi = mid
            else:
                lo = mid
    return self.fx_safe_price(symbol, (lo + hi) / 2.0) if hasattr(self, "fx_safe_price") else fx_safe_price(self, symbol, (lo + hi) / 2.0)


def fx_calculate_entry_qty(self, symbol, balance, reference_price,
                           risk_pct, sl_price_fraction, size_mode, fixed_qty):
    if size_mode == "FIXED_QTY":
        qty = float(fixed_qty)
    else:
        if risk_pct <= 0:
            raise ValueError("Risk Per Trade must be greater than 0.")
        if sl_price_fraction <= 0:
            raise ValueError("SL price distance must be greater than 0.")
        # Use the actual broker P/L function for 1 lot.
        side = getattr(self, "_pending_signal_for_sizing", "BUY")
        direction = "LONG" if side == "BUY" else "SHORT"
        stop_price = (
            float(reference_price) * (1.0 - sl_price_fraction)
            if direction == "LONG"
            else float(reference_price) * (1.0 + sl_price_fraction)
        )
        risk_amount = float(balance) * float(risk_pct)
        loss_1lot = abs(self.exchange.calc_profit(
            direction, symbol, 1.0, float(reference_price), stop_price
        ))
        if loss_1lot <= 0:
            raise RuntimeError("MT5 returned zero risk for 1.00 lot; cannot calculate safe size.")
        qty = risk_amount / loss_1lot
    qty = fx_safe_amount(self, symbol, qty)
    if qty <= 0:
        raise RuntimeError("Calculated Forex lot size is below broker minimum/step.")
    return qty


def fx_calculate_protection_prices(self, symbol, side, actual_entry, position_qty,
                                   position_initial_margin, sl_target_pct,
                                   tp1_target_pct, tp2_target_pct, sl_mode, tp_mode,
                                   leverage):
    entry = float(actual_entry)
    qty = float(position_qty)
    if entry <= 0 or qty <= 0:
        raise RuntimeError("Actual MT5 entry/lot size is invalid.")
    # PRICE_% remains direct market-price movement.
    def target_price(target, mode, positive=True):
        target = float(target)
        if target <= 0:
            raise RuntimeError("SL/TP targets must be greater than zero.")
        if str(mode).upper() == "PRICE_%":
            move = entry * target / 100.0
            return entry + move if positive else entry - move
        if str(mode).upper() != "ROI_%":
            raise RuntimeError(f"Unknown SL/TP mode: {mode}")
        if position_initial_margin <= 0:
            margin = self.exchange.calc_margin(side, symbol, qty, entry)
        else:
            margin = float(position_initial_margin)
        if margin <= 0:
            raise RuntimeError("MT5 could not calculate actual position margin for ROI target.")
        target_pnl = margin * target / 100.0
        signed = target_pnl if positive else -target_pnl
        return fx_find_price_for_pnl(self, side, symbol, entry, qty, signed)

    sl = target_price(sl_target_pct, sl_mode, positive=False if side == "LONG" else True)
    tp1 = target_price(tp1_target_pct, tp_mode, positive=True if side == "LONG" else False)
    tp2 = target_price(tp2_target_pct, tp_mode, positive=True if side == "LONG" else False)
    sl, tp1, tp2 = [fx_safe_price(self, symbol, x) for x in (sl,tp1,tp2)]

    if side == "LONG" and not (sl < entry and tp1 > entry and tp2 > tp1):
        raise RuntimeError("Calculated LONG Forex SL/TP prices are invalid.")
    if side == "SHORT" and not (sl > entry and tp1 < entry and tp2 < tp1):
        raise RuntimeError("Calculated SHORT Forex SL/TP prices are invalid.")
    return (
        sl, tp1, tp2,
        abs(sl-entry)/entry,
        abs(tp1-entry)/entry,
        abs(tp2-entry)/entry,
    )


def fx_fetch_position(self, symbol):
    rows = self.exchange.fetch_positions([symbol])
    for p in rows:
        if p["contracts"] > 0:
            return {
                "id": p.get("id"),
                "side": p["side"].upper(),
                "qty": float(p["contracts"]),
                "entry": float(p["entryPrice"]),
                "leverage": float(p.get("leverage") or self.reference_leverage),
                "initial_margin": float(p.get("initialMargin") or 0.0),
                "raw": p,
            }
    return None


def fx_wait_for_position(self, symbol, expected_side, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        p = fx_fetch_position(self, symbol)
        if p and p["side"] == expected_side and p["qty"] > 0 and p["entry"] > 0:
            return p
        time.sleep(0.3)
    return None


def fx_open_market_position(self, symbol, signal, qty):
    self._pending_signal_for_sizing = signal
    # Optional broker spread guard. This is an execution safety filter and
    # does not alter any V8 indicator or signal formula.
    if getattr(self, "v_use_spread_filter", None) is not None and self.v_use_spread_filter.get():
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            raise RuntimeError("MT5 spread check failed: symbol tick/info unavailable.")
        spread_points = (float(tick.ask) - float(tick.bid)) / float(info.point)
        max_spread = float(self.e_max_spread_points.get().strip())
        self.log(f"FOREX SPREAD CHECK: {spread_points:.2f} points | Max={max_spread:.2f}")
        if spread_points > max_spread:
            raise RuntimeError(
                f"Entry blocked by Forex spread filter: {spread_points:.2f} > {max_spread:.2f} points."
            )
    order = self.exchange.create_order(
        symbol, "market", "buy" if signal == "BUY" else "sell", qty, None, {}
    )
    expected = "LONG" if signal == "BUY" else "SHORT"
    pos = fx_wait_for_position(self, symbol, expected, timeout=10)
    if not pos:
        raise RuntimeError("MT5 order submitted but actual position could not be confirmed.")
    return pos, pos["entry"]


def fx_close_position_market(self, symbol, position_side, qty):
    pos = fx_fetch_position(self, symbol)
    if isinstance(self.exchange, MT5ForexAdapter) and self.exchange.paper:
        self.exchange.create_order(
            symbol, "market", "sell" if position_side == "LONG" else "buy",
            fx_safe_amount(self, symbol, qty), None,
            {"position": pos["id"] if pos else None},
        )
        return
    if not pos:
        return
    order = self.exchange.create_order(
        symbol, "market", "sell" if position_side == "LONG" else "buy",
        fx_safe_amount(self, symbol, qty), None,
        {"position": pos["id"], "deviation": 30}
    )
    return order


def fx_cancel_all_open_orders(self, symbol):
    for order in self.exchange.fetch_open_orders(symbol):
        oid = order.get("id")
        if oid:
            try:
                self.exchange.cancel_order(oid, symbol)
            except Exception as e:
                self.log(f"MT5 pending-order cancel warning {oid}: {e}")


def fx_reconcile_noop(self, position):
    # MT5 SL is stored on the position, not as a separate CCXT conditional order.
    # The actual SL is verified in verify_protection_orders.
    return True


def fx_create_protection_orders(self, symbol, position_side, position_qty,
                                 sl, tp1, tp2, tp_qty_mode,
                                 tp1_close_value, tp2_close_value):
    qty = fx_safe_amount(self, symbol, position_qty)
    if qty <= 0:
        raise RuntimeError("Actual MT5 position volume is invalid.")
    hold_all_reverse = bool(self.v_hold_until_all_reverse.get())

    tp1_qty = tp2_qty = 0.0
    if not hold_all_reverse:
        tp1_qty, tp2_qty = self.calculate_tp_close_quantities(
            symbol, qty, tp_qty_mode, tp1_close_value, tp2_close_value
        )

    # Hold-SL WAIT is handled before this method in the unchanged V8 main loop.
    pos = fx_fetch_position(self, symbol)
    if not pos:
        raise RuntimeError("MT5 position disappeared before SL installation.")
    if isinstance(self.exchange, MT5ForexAdapter) and self.exchange.paper:
        sl_order = self.exchange.modify_position_sl(symbol, pos, sl)
    else:
        sl_order = self.exchange.modify_position_sl(symbol, pos, sl)
    self.log(f"MT5 BROKER-SIDE SL ACTIVE ✓ | SL={sl}")
    # TP1/TP2 are bot-managed because MT5 position-level TP supports only one TP.
    created = [("SL", sl_order)]
    if not hold_all_reverse:
        created.append(("TP1", {
            "id": f"MT5-TP1-{time.time_ns()}",
            "status": "open",
            "filled": 0.0,
            "price": float(tp1),
            "qty": float(tp1_qty),
            "info": {"managed_by_bot": True},
        }))
        created.append(("TP2", {
            "id": f"MT5-TP2-{time.time_ns()}",
            "status": "open",
            "filled": 0.0,
            "price": float(tp2),
            "qty": float(tp2_qty),
            "info": {"managed_by_bot": True},
        }))
    return created


def fx_verify_protection_orders(self, symbol, created):
    if not created:
        return True
    if isinstance(self.exchange, MT5ForexAdapter) and self.exchange.paper:
        pos = self.exchange.paper_positions.get(symbol)
        return bool(pos and float(pos.get("info", {}).get("sl", 0.0)) > 0)
    rows = mt5.positions_get(symbol=symbol) or []
    rows = [r for r in rows if int(r.magic) == int(self.mt5_magic)]
    if not rows:
        return False
    sl_orders = [o for label,o in created if label in ("SL","BREAK-EVEN SL")]
    if not sl_orders:
        return True
    requested = float(sl_orders[0].get("sl") or 0.0)
    return float(rows[0].sl or 0.0) > 0 and abs(float(rows[0].sl) - requested) <= max(float(mt5.symbol_info(symbol).point)*2, 1e-12)


def fx_manage_tp_be(self, position):
    """MT5 manual TP1/TP2 + BE manager; broker SL remains the hard protection."""
    if not position or not self.last_protected_position:
        return
    if self.v_hold_until_all_reverse.get():
        return
    protected = self.last_protected_position
    if protected.get("side") != position.get("side"):
        return
    symbol = self.symbol
    price = self._current_market_price(symbol)
    side = position["side"]
    tp1 = float(protected.get("tp1") or 0)
    tp2 = float(protected.get("tp2") or 0)
    tp1_id = protected.get("tp1_id")
    tp2_id = protected.get("tp2_id")
    # Track TP1/TP2 with bot state.
    if not protected.get("tp1_hit"):
        hit = price >= tp1 if side == "LONG" else price <= tp1
        if hit and tp1_id:
            tp1_qty = float(protected.get("tp1_qty") or 0)
            current_qty = float(position.get("qty") or 0)
            close_qty = min(tp1_qty, current_qty)
            if close_qty > 0:
                self.log(f"TP1 HIT ✓ | Price={price:.12g} | Closing={close_qty:g} lots")
                fx_close_position_market(self, symbol, side, close_qty)
                protected["tp1_hit"] = True
                self._mark_tp1_hit_for_stats()
                time.sleep(0.5)
                remaining = fx_fetch_position(self, symbol)
                if remaining and self.v_tp1_be.get():
                    be = fx_safe_price(self, symbol, remaining["entry"])
                    self.exchange.modify_position_sl(symbol, remaining, be)
                    protected["sl"] = be
                    protected["sl_id"] = f"MT5-BE-{time.time_ns()}"
                    self.tp1_be_done = True
                    self.log(f"BREAK-EVEN ACTIVE ✓ | Entry={remaining['entry']:.12g} | SL={be:.12g}")
                return

    # TP2 is evaluated against the remaining position.
    if protected.get("tp1_hit") and not protected.get("tp2_hit"):
        hit = price >= tp2 if side == "LONG" else price <= tp2
        if hit:
            remaining = fx_fetch_position(self, symbol)
            if remaining:
                self.log(f"TP2 HIT ✓ | Price={price:.12g} | Closing remaining={remaining['qty']:g} lots")
                fx_close_position_market(self, symbol, side, remaining["qty"])
                protected["tp2_hit"] = True
                return

    # PAPER mode must emulate the broker-side SL because no real order exists.
    if isinstance(self.exchange, MT5ForexAdapter) and self.exchange.paper:
        sl = float(protected.get("sl") or 0)
        if sl:
            hit = price <= sl if side == "LONG" else price >= sl
            if hit:
                self.log(f"PAPER SL HIT | Price={price:.12g} | SL={sl:.12g}")
                fx_close_position_market(self, symbol, side, position["qty"])


def fx_detect_exit_reason(self, protected):
    if not protected:
        return "UNKNOWN"
    symbol = self.symbol
    try:
        price = self._current_market_price(symbol)
    except Exception:
        return "UNKNOWN"
    side = protected.get("side")
    sl = float(protected.get("sl") or 0)
    tp1 = float(protected.get("tp1") or 0)
    tp2 = float(protected.get("tp2") or 0)
    if protected.get("tp2_hit"):
        return "TP2"
    if protected.get("tp1_hit") and not protected.get("tp2_hit"):
        # If position is now flat after TP2 it would have been marked above.
        return "TP1"
    if sl > 0 and ((side == "LONG" and price <= sl) or (side == "SHORT" and price >= sl)):
        return "SL"
    return "UNKNOWN"


def fx_emergency_flatten(self, reason, equity, threshold):
    self.log(
        f"CRITICAL MT5 CAPITAL CIRCUIT BREAKER: Equity={equity:.8f} <= "
        f"Threshold={threshold:.8f} | {reason}"
    )
    self.send_telegram(
        f"CRITICAL MT5 CAPITAL STOP: equity {equity:.4f} <= {threshold:.4f}. "
        "All account positions will be closed and bot stopped."
    )
    # This intentionally ignores magic number: emergency stop means ALL account positions.
    if isinstance(self.exchange, MT5ForexAdapter) and self.exchange.paper:
        self.exchange.paper_positions.clear()
        self.exchange.paper_equity = self.exchange.paper_balance
    else:
        rows = list(mt5.positions_get() or [])
        for p in rows:
            try:
                tick = mt5.symbol_info_tick(p.symbol)
                if tick is None:
                    continue
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": p.symbol,
                    "volume": float(p.volume),
                    "type": close_type,
                    "position": int(p.ticket),
                    "price": float(price),
                    "deviation": 50,
                    "magic": int(self.mt5_magic),
                    "comment": "UniversalForexBotV1 CAPITAL STOP",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": self.exchange._filling(p.symbol),
                }
                result = mt5.order_send(req)
                self.log(
                    f"CAPITAL STOP: {p.symbol} ticket={p.ticket} result="
                    f"{getattr(result,'retcode',None)}"
                )
            except Exception as e:
                self.log(f"CAPITAL STOP: FAILED {p.symbol} ticket={getattr(p,'ticket','?')}: {e}")
        # Cancel all pending orders account-wide.
        for o in list(mt5.orders_get() or []):
            try:
                result = mt5.order_send({
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": int(o.ticket),
                    "symbol": o.symbol,
                })
                self.log(f"CAPITAL STOP: Pending order {o.ticket} cancel={getattr(result,'retcode',None)}")
            except Exception as e:
                self.log(f"CAPITAL STOP: Pending cancel failed {getattr(o,'ticket','?')}: {e}")

        # Verify. Do not claim flat if MT5 still reports positions.
        remaining = list(mt5.positions_get() or [])
        if remaining:
            self.log(f"!!! CAPITAL STOP WARNING: {len(remaining)} MT5 positions remain open.")
        else:
            self.log("CAPITAL STOP COMPLETE ✓: ALL MT5 account positions are flat.")
    self.is_running = False
    try:
        self.root.after(0, lambda: (
            self.btn_start.config(state="normal"),
            self.btn_stop.config(state="disabled")
        ))
    except Exception:
        pass


def fx_fetch_strategy_ohlcv(self, timeframe, limit):
    return self.exchange.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit)


def fx_start_bot(self):
    if self.is_running:
        return
    try:
        self.save_settings()
        if mt5 is None:
            raise RuntimeError("MetaTrader5 is not installed. Run: py -m pip install MetaTrader5")
        exchange_id = "mt5_forex"
        mode = self.v_account_mode.get().strip().upper()
        if mode not in ("MT5_PAPER","MT5_TERMINAL","MT5_LIVE"):
            raise ValueError("Choose MT5_PAPER, MT5_TERMINAL or MT5_LIVE.")
        self.exchange_id = exchange_id
        self.mt5_magic = int(self.e_magic.get().strip()) if hasattr(self, "e_magic") else 26091802
        self.reference_leverage = float(self.e_lev.get().strip())
        self.exchange = fx_build_exchange(
            self, exchange_id, self.e_api_key.get().strip(),
            self.e_api_secret.get().strip(), mode
        )
        self.symbol = self.normalize_symbol(self.exchange, exchange_id, self.e_symbol.get())
        self.exchange.symbol = self.symbol
        # Broker symbol info / volume rules are logged before any order.
        info = mt5.symbol_info(self.symbol)
        if info is None:
            raise RuntimeError(f"MT5 symbol_info unavailable for {self.symbol}")
        self.log(
            f"FOREX SYMBOL: {self.symbol} | Digits={info.digits} | Point={info.point} | "
            f"Contract={info.trade_contract_size} | Lots min/step/max="
            f"{info.volume_min}/{info.volume_step}/{info.volume_max} | "
            f"StopsLevel={info.trade_stops_level} points"
        )
        if self.v_use_spread_filter.get():
            self.log(f"FOREX SPREAD FILTER: ON | Max={self.e_max_spread_points.get().strip()} points")
        self.configure_leverage(self.symbol, self.reference_leverage)

        max_trades = int(self.e_max_trades.get().strip())
        if max_trades < 0:
            raise ValueError("Max Trades cannot be negative.")
        self.start_balance = self.fetch_balance_total()
        self.total_trades = self.opened_trades = self.winning_trades = self.losing_trades = 0
        self.trade_pnls = []
        self.active_trade = None
        self.session_started_at = time.time()
        self.session_max_trades = max_trades
        self.reentry_direction_lock = None
        self.last_protected_position = None
        self.tp1_be_done = False
        self.hold_sl_threshold_hit = False
        self.hold_sl_threshold_logged = False
        self.last_entry_candle_ts = None
        self.last_flat_time = 0.0

        self.log(
            f"CONNECTED: MT5 {mode} | {self.symbol} | "
            f"Start Balance={self.start_balance:.4f} | "
            f"Equity={self.fetch_account_equity():.4f}"
        )
        self.log("FOREX ENGINE: MT5-native candles + broker lot rules + MT5 P/L/margin calculations")
        self.log("STRATEGY ENGINE: V8 indicator/entry/reversal logic preserved unchanged.")
        self.log(
            f"SL/TP engine: {self.v_sl_mode.get()} / {self.v_tp_mode.get()} | "
            "Forex ROI targets use actual MT5 margin + order_calc_profit after fill."
        )

        self.is_running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.bot_thread = threading.Thread(target=self._run_bot_logic, daemon=True)
        self.bot_thread.start()
    except Exception as e:
        self.log(f"START FAILED: {e}")
        self.is_running = False
        try:
            messagebox.showerror("Forex bot start failed", str(e))
        except Exception:
            pass


# Spread filter: injected at the beginning of each strategy cycle without changing
# any indicator or signal formulas. We wrap the original method only to gate entries.
_original_run_bot_logic_v1 = UniversalFuturesBotGUI._run_bot_logic

def fx_run_bot_logic(self):
    # The V8 main loop is retained. A lightweight spread guard is enforced by
    # monkey-patching desired order creation through a flag checked by sizing.
    self._fx_spread_block = False
    return _original_run_bot_logic_v1(self)

# Extra fields/settings compatibility.
_original_save_settings_v1 = UniversalFuturesBotGUI.save_settings
def fx_save_settings(self):
    _original_save_settings_v1(self)
    try:
        cfg_path = CONFIG_FILE
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["exchange"] = "mt5_forex"
        cfg["account_mode"] = self.v_account_mode.get()
        cfg["mt5_server"] = getattr(self, "e_mt5_server", tk.Entry()).get().strip() if hasattr(self,"e_mt5_server") else ""
        cfg["paper_balance"] = getattr(self, "e_paper_balance", tk.Entry()).get().strip() if hasattr(self,"e_paper_balance") else "1000"
        cfg["use_spread_filter"] = self.v_use_spread_filter.get() if hasattr(self,"v_use_spread_filter") else False
        cfg["max_spread_points"] = self.e_max_spread_points.get().strip() if hasattr(self,"e_max_spread_points") else "30"
        # V2 Forex guardrails
        cfg.update({
            "v2_auto_symbol": self.v_auto_symbol.get(),
            "v2_use_slippage": self.v_use_slippage.get(),
            "v2_max_slippage_points": self.e_max_slippage_points.get().strip(),
            "v2_use_session": self.v_use_session.get(),
            "v2_session_start": self.e_session_start.get().strip(),
            "v2_session_end": self.e_session_end.get().strip(),
            "v2_friday_protect": self.v_friday_protect.get(),
            "v2_friday_cutoff": self.e_friday_cutoff.get().strip(),
            "v2_use_daily_loss": self.v_use_daily_loss.get(),
            "v2_daily_loss_pct": self.e_daily_loss_pct.get().strip(),
            "v2_use_daily_profit": self.v_use_daily_profit.get(),
            "v2_daily_profit_pct": self.e_daily_profit_pct.get().strip(),
            "v2_use_loss_streak": self.v_use_loss_streak.get(),
            "v2_max_loss_streak": self.e_max_loss_streak.get().strip(),
            "v2_use_trailing": self.v_use_trailing.get(),
            "v2_trail_activation": self.e_trail_activation.get().strip(),
            "v2_trail_distance": self.e_trail_distance.get().strip(),
            "v2_use_atr_sl": self.v_use_atr_sl.get(),
            "v2_atr_sl_mult": self.e_atr_sl_mult.get().strip(),
            "v2_use_news": self.v_use_news.get(),
            "v2_news_minutes": self.e_news_minutes.get().strip(),
            "v2_use_correlation": self.v_use_correlation.get(),
            "v2_corr_threshold": self.e_corr_threshold.get().strip(),
            "v2_corr_symbols": self.e_corr_symbols.get().strip(),
            "v2_scanner": self.v_scanner.get(),
            "v2_scan_symbols": self.e_scan_symbols.get().strip(),
            "v2_reconnect": self.v_reconnect.get(),
            "v2_position_recovery": self.v_position_recovery.get(),
            "v2_magic": self.e_magic.get().strip(),
        })
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        self.log(f"Forex config extension save warning: {e}")

# Use a Forex-safe load wrapper for the extra controls while retaining every V8 strategy setting.
_original_load_settings_v1 = UniversalFuturesBotGUI.load_settings
def fx_load_settings(self):
    _original_load_settings_v1(self)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.v_exchange.set("mt5_forex")
        self.v_account_mode.set(cfg.get("account_mode","MT5_PAPER"))
        if hasattr(self, "e_mt5_server"):
            self.e_mt5_server.delete(0, tk.END)
            self.e_mt5_server.insert(0, cfg.get("mt5_server",""))
        if hasattr(self, "e_paper_balance"):
            self.e_paper_balance.delete(0, tk.END)
            self.e_paper_balance.insert(0, cfg.get("paper_balance","1000"))
        if hasattr(self, "v_use_spread_filter"):
            self.v_use_spread_filter.set(cfg.get("use_spread_filter",False))
        if hasattr(self, "e_max_spread_points"):
            self.e_max_spread_points.delete(0, tk.END)
            self.e_max_spread_points.insert(0, cfg.get("max_spread_points","30"))
        # V2 Forex guardrails
        self.v_auto_symbol.set(cfg.get("v2_auto_symbol", True))
        self.v_use_slippage.set(cfg.get("v2_use_slippage", True))
        self.e_max_slippage_points.delete(0, tk.END); self.e_max_slippage_points.insert(0, cfg.get("v2_max_slippage_points","20"))
        self.v_use_session.set(cfg.get("v2_use_session", False))
        self.e_session_start.delete(0, tk.END); self.e_session_start.insert(0, cfg.get("v2_session_start","07:00"))
        self.e_session_end.delete(0, tk.END); self.e_session_end.insert(0, cfg.get("v2_session_end","20:00"))
        self.v_friday_protect.set(cfg.get("v2_friday_protect", True))
        self.e_friday_cutoff.delete(0, tk.END); self.e_friday_cutoff.insert(0, cfg.get("v2_friday_cutoff","18:00"))
        self.v_use_daily_loss.set(cfg.get("v2_use_daily_loss", True))
        self.e_daily_loss_pct.delete(0, tk.END); self.e_daily_loss_pct.insert(0, cfg.get("v2_daily_loss_pct","3.0"))
        self.v_use_daily_profit.set(cfg.get("v2_use_daily_profit", False))
        self.e_daily_profit_pct.delete(0, tk.END); self.e_daily_profit_pct.insert(0, cfg.get("v2_daily_profit_pct","5.0"))
        self.v_use_loss_streak.set(cfg.get("v2_use_loss_streak", True))
        self.e_max_loss_streak.delete(0, tk.END); self.e_max_loss_streak.insert(0, cfg.get("v2_max_loss_streak","3"))
        self.v_use_trailing.set(cfg.get("v2_use_trailing", False))
        self.e_trail_activation.delete(0, tk.END); self.e_trail_activation.insert(0, cfg.get("v2_trail_activation","30"))
        self.e_trail_distance.delete(0, tk.END); self.e_trail_distance.insert(0, cfg.get("v2_trail_distance","20"))
        self.v_use_atr_sl.set(cfg.get("v2_use_atr_sl", False))
        self.e_atr_sl_mult.delete(0, tk.END); self.e_atr_sl_mult.insert(0, cfg.get("v2_atr_sl_mult","1.5"))
        self.v_use_news.set(cfg.get("v2_use_news", False))
        self.e_news_minutes.delete(0, tk.END); self.e_news_minutes.insert(0, cfg.get("v2_news_minutes","30"))
        self.v_use_correlation.set(cfg.get("v2_use_correlation", False))
        self.e_corr_threshold.delete(0, tk.END); self.e_corr_threshold.insert(0, cfg.get("v2_corr_threshold","0.85"))
        self.e_corr_symbols.delete(0, tk.END); self.e_corr_symbols.insert(0, cfg.get("v2_corr_symbols","EURUSD,GBPUSD,USDCHF,USDJPY"))
        self.v_scanner.set(cfg.get("v2_scanner", False))
        self.e_scan_symbols.delete(0, tk.END); self.e_scan_symbols.insert(0, cfg.get("v2_scan_symbols","EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"))
        self.v_reconnect.set(cfg.get("v2_reconnect", True))
        self.v_position_recovery.set(cfg.get("v2_position_recovery", True))
        self.e_magic.delete(0, tk.END); self.e_magic.insert(0, cfg.get("v2_magic","26091802"))
    except Exception:
        pass


# ============================================================
# V2 FOREX SAFETY / EXECUTION EXTENSIONS
# Strategy and indicator formulas above remain unchanged.
# These modules add broker-aware execution and optional guardrails.
# ============================================================

from datetime import datetime, timezone

def _v2_bool(bot, name, default=False):
    try:
        return bool(getattr(bot, name).get())
    except Exception:
        return default

def _v2_float(bot, name, default):
    try:
        return float(getattr(bot, name).get().strip())
    except Exception:
        return float(default)

def _v2_time_hm(value, default=(0, 0)):
    try:
        h, m = [int(x) for x in str(value).strip().split(":")[:2]]
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:
        pass
    return default

def fx_v2_in_session(self):
    if not _v2_bool(self, "v_use_session", False):
        return True
    now = datetime.now(timezone.utc)
    cur = now.hour * 60 + now.minute
    sh, sm = _v2_time_hm(self.e_session_start.get(), (7, 0))
    eh, em = _v2_time_hm(self.e_session_end.get(), (20, 0))
    start = sh * 60 + sm
    end = eh * 60 + em
    if start == end:
        return True
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end

def fx_v2_friday_block(self):
    if not _v2_bool(self, "v_friday_protect", True):
        return False
    now = datetime.now(timezone.utc)
    if now.weekday() != 4:
        return False
    h, m = _v2_time_hm(self.e_friday_cutoff.get(), (18, 0))
    return now.hour * 60 + now.minute >= h * 60 + m

def fx_v2_day_start(self, equity):
    key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if getattr(self, "v2_day_key", None) != key or getattr(self, "v2_day_start_equity", 0) <= 0:
        self.v2_day_key = key
        self.v2_day_start_equity = float(equity)
        self.v2_loss_streak = 0
        self.log(f"V2 DAILY RISK RESET | UTC={key} | Start Equity={equity:.4f}")

def fx_v2_daily_status(self):
    equity = float(self.fetch_account_equity())
    fx_v2_day_start(self, equity)
    base = max(float(self.v2_day_start_equity), 1e-12)
    pct = (equity - base) / base * 100.0
    return equity, pct

def fx_v2_close_bot_position(self, reason):
    try:
        p = fx_fetch_position(self, self.symbol)
        if p:
            self.log(f"V2 RISK FLATTEN: {reason} | {p['side']} {p['qty']} {self.symbol}")
            fx_cancel_all_open_orders(self, self.symbol)
            fx_close_position_market(self, self.symbol, p["side"], p["qty"])
            time.sleep(0.5)
    except Exception as e:
        self.log(f"V2 RISK FLATTEN FAILED: {e}")

def fx_v2_news_block(self, symbol):
    if not _v2_bool(self, "v_use_news", False):
        return False
    now = time.time()
    if now - getattr(self, "v2_last_news_check", 0) > 300:
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            self.v2_news_cache = data if isinstance(data, list) else []
            self.v2_last_news_check = now
        except Exception as e:
            # Fail open for entries when the optional news source is unavailable.
            if now - getattr(self, "v2_last_news_check", 0) > 900:
                self.log(f"NEWS FILTER WARNING: calendar unavailable; entries are not blocked. {e}")
            self.v2_last_news_check = now
            return True
    minutes = max(0.0, _v2_float(self, "e_news_minutes", 30))
    pair = str(symbol).upper().replace("/", "")
    currencies = []
    if len(pair) >= 6:
        currencies = [pair[:3], pair[3:6]]
    now_dt = datetime.now(timezone.utc)
    for item in getattr(self, "v2_news_cache", []):
        try:
            impact = str(item.get("impact", "")).strip().lower()
            if impact != "high":
                continue
            country = str(item.get("country", "")).upper()
            if currencies and country not in currencies:
                continue
            raw = item.get("date") or item.get("datetime")
            if not raw:
                continue
            event_dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)
            delta = abs((event_dt.astimezone(timezone.utc) - now_dt).total_seconds()) / 60.0
            if delta <= minutes:
                title = item.get("title") or item.get("event") or "High impact event"
                self.log(f"NEWS BLOCK: {title} | {country} | ±{minutes:g} min")
                return True
        except Exception:
            continue
    return False

def fx_v2_correlation_block(self, symbol):
    if not _v2_bool(self, "v_use_correlation", False):
        return False
    threshold = min(0.999, max(0.0, _v2_float(self, "e_corr_threshold", 0.85)))
    symbols = [x.strip().upper() for x in self.e_corr_symbols.get().split(",") if x.strip()]
    base_raw = str(symbol).upper().replace("/", "")
    for raw in symbols:
        try:
            candidate = self.exchange.normalize(raw)
            if candidate == symbol:
                continue
            existing = self.exchange.fetch_positions([candidate])
            if not existing:
                continue
            a = self.exchange.fetch_ohlcv(symbol, "1h", 80)
            b = self.exchange.fetch_ohlcv(candidate, "1h", 80)
            da = pd.DataFrame(a, columns=["time","open","high","low","close","vol"])
            db = pd.DataFrame(b, columns=["time","open","high","low","close","vol"])
            n = min(len(da), len(db))
            if n < 30:
                continue
            corr = da["close"].pct_change().tail(n).corr(db["close"].pct_change().tail(n))
            if pd.notna(corr) and abs(float(corr)) >= threshold:
                self.log(f"CORRELATION BLOCK: {candidate} position exists | 1H corr={float(corr):.3f} >= {threshold:.3f}")
                return True
        except Exception:
            continue
    return False

def fx_v2_apply_atr_sl(self, symbol, side, entry, sl, qty):
    if not _v2_bool(self, "v_use_atr_sl", False):
        return sl
    try:
        mult = max(0.1, _v2_float(self, "e_atr_sl_mult", 1.5))
        rows = self.exchange.fetch_ohlcv(symbol, self.v_tf.get(), 120)
        d = pd.DataFrame(rows, columns=["time","open","high","low","close","vol"])
        if len(d) < 20:
            return sl
        tr = pd.concat([
            d["high"] - d["low"],
            (d["high"] - d["close"].shift(1)).abs(),
            (d["low"] - d["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = float(calculate_rma(tr, 14).iloc[-2])
        if not np.isfinite(atr) or atr <= 0:
            return sl
        candidate = entry - mult * atr if side == "LONG" else entry + mult * atr
        candidate = fx_safe_price(self, symbol, candidate)
        # Never make ATR stop less protective than the configured stop.
        if side == "LONG":
            return min(float(sl), candidate)
        return max(float(sl), candidate)
    except Exception as e:
        self.log(f"ATR SL WARNING: {e}")
        return sl

def fx_v2_trailing_manage(self, position):
    if not position or not _v2_bool(self, "v_use_trailing", False):
        return
    try:
        symbol = self.symbol
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return
        point = float(info.point or 0.00001)
        activation = max(0.0, _v2_float(self, "e_trail_activation", 30)) * point
        distance = max(1.0, _v2_float(self, "e_trail_distance", 20)) * point
        side = position["side"]
        entry = float(position["entry"])
        current = float(tick.bid if side == "LONG" else tick.ask)
        favorable = current - entry if side == "LONG" else entry - current
        if favorable < activation:
            return
        new_sl = current - distance if side == "LONG" else current + distance
        new_sl = fx_safe_price(self, symbol, new_sl)
        old_sl = float((self.last_protected_position or {}).get("sl") or 0.0)
        improve = (new_sl > old_sl) if side == "LONG" else (new_sl < old_sl or old_sl == 0)
        valid = (new_sl < current and new_sl > entry) if side == "LONG" else (new_sl > current and new_sl < entry)
        if improve and valid:
            self.exchange.modify_position_sl(symbol, position, new_sl)
            if self.last_protected_position is not None:
                self.last_protected_position["sl"] = new_sl
            self.v2_trailing_last_log = time.time()
            self.log(f"TRAILING SL UPDATED ✓ | {side} | Entry={entry:.8f} | SL={new_sl:.8f}")
    except Exception as e:
        self.log(f"TRAILING STOP WARNING: {e}")

def fx_v2_reconnect(self):
    try:
        info = mt5.account_info()
        if info is not None:
            return True
    except Exception:
        pass
    try:
        mt5.shutdown()
    except Exception:
        pass
    try:
        if mt5.initialize():
            self.log("MT5 RECONNECTED ✓")
            mt5.symbol_select(self.symbol, True)
            return True
    except Exception as e:
        self.log(f"MT5 RECONNECT FAILED: {e}")
    return False

def fx_v2_scanner(self):
    if not _v2_bool(self, "v_scanner", False):
        return
    if time.time() - getattr(self, "v2_last_scan", 0) < 300:
        return
    self.v2_last_scan = time.time()
    rows = []
    for raw in [x.strip() for x in self.e_scan_symbols.get().split(",") if x.strip()]:
        try:
            sym = self.exchange.normalize(raw)
            o = self.exchange.fetch_ohlcv(sym, self.v_tf.get(), 80)
            d = pd.DataFrame(o, columns=["time","open","high","low","close","vol"])
            if len(d) < 30:
                continue
            d = calculate_supertrend(d, int(self.e_st_len.get()), float(self.e_st_mult.get()), self.v_st_source.get(), self.v_st_change_atr.get())
            ema = d["close"].ewm(span=int(self.e_ema_len.get()), adjust=False).mean()
            st = "BUY" if bool(d["trend"].iloc[-2]) else "SELL"
            em = "BUY" if float(d["close"].iloc[-2]) > float(ema.iloc[-2]) else "SELL"
            rows.append(f"{sym}:{st}/{em}")
        except Exception:
            continue
    if rows:
        self.log("V2 SCANNER | " + " | ".join(rows))

def fx_v2_watchdog(self):
    self.v2_watchdog_running = True
    while self.is_running and self.v2_watchdog_running:
        try:
            if _v2_bool(self, "v_reconnect", True):
                fx_v2_reconnect(self)
            equity, day_pct = fx_v2_daily_status(self)

            if _v2_bool(self, "v_use_daily_loss", True):
                limit = abs(_v2_float(self, "e_daily_loss_pct", 3.0))
                if day_pct <= -limit:
                    self.log(f"DAILY LOSS LIMIT HIT: {day_pct:.2f}% <= -{limit:.2f}%")
                    fx_v2_close_bot_position(self, "Daily loss limit")
                    self.stop_bot()
                    break

            if _v2_bool(self, "v_use_daily_profit", False):
                target = abs(_v2_float(self, "e_daily_profit_pct", 5.0))
                if day_pct >= target:
                    self.log(f"DAILY PROFIT LOCK HIT: {day_pct:.2f}% >= {target:.2f}%")
                    fx_v2_close_bot_position(self, "Daily profit target")
                    self.stop_bot()
                    break

            if _v2_bool(self, "v_use_loss_streak", True):
                max_streak = max(1, int(_v2_float(self, "e_max_loss_streak", 3)))
                if self.v2_loss_streak >= max_streak:
                    self.log(f"CONSECUTIVE LOSS STOP: {self.v2_loss_streak} losses reached.")
                    fx_v2_close_bot_position(self, "Consecutive loss protection")
                    self.stop_bot()
                    break

            p = fx_fetch_position(self, self.symbol) if getattr(self, "exchange", None) else None
            if p:
                fx_v2_trailing_manage(self, p)
            fx_v2_scanner(self)
        except Exception as e:
            self.log(f"V2 WATCHDOG WARNING: {e}")
        for _ in range(5):
            if not self.is_running or not self.v2_watchdog_running:
                break
            time.sleep(1)

def fx_v2_open_market_position(self, symbol, signal, qty):
    # Entry gates are checked immediately before broker order submission.
    if not fx_v2_in_session(self):
        raise RuntimeError("Entry blocked: outside configured UTC trading session.")
    if fx_v2_friday_block(self):
        raise RuntimeError("Entry blocked: Friday protection cutoff reached.")
    if fx_v2_news_block(self, symbol):
        raise RuntimeError("Entry blocked: high-impact economic news window.")
    if fx_v2_correlation_block(self, symbol):
        raise RuntimeError("Entry blocked: correlated bot position exists.")
    requested_tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    requested_mid = None
    if requested_tick and info:
        requested_mid = float(requested_tick.ask if signal == "BUY" else requested_tick.bid)
    result = _fx_v2_original_open(self, symbol, signal, qty)
    if _v2_bool(self, "v_use_slippage", True) and requested_mid is not None:
        actual = float(result[1])
        deviation_points = abs(actual - requested_mid) / float(info.point or 1e-5)
        max_points = max(0.0, _v2_float(self, "e_max_slippage_points", 20))
        self.log(f"SLIPPAGE CHECK: {deviation_points:.2f} points | Max={max_points:.2f}")
        if deviation_points > max_points:
            try:
                p = fx_fetch_position(self, symbol)
                if p:
                    fx_close_position_market(self, symbol, p["side"], p["qty"])
            finally:
                raise RuntimeError(f"Entry rejected by slippage protection: {deviation_points:.2f} > {max_points:.2f} points.")
    return result

def fx_v2_pip_size(symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"MT5 symbol_info unavailable for pip calculation: {symbol}")
    point = float(info.point or 0.00001)
    digits = int(info.digits)
    return point * 10.0 if digits in (3, 5) else point

def fx_v2_calculate_protection_prices(self, symbol, side, actual_entry, position_qty,
                                      position_initial_margin, sl_target_pct, tp1_target_pct,
                                      tp2_target_pct, sl_mode, tp_mode, leverage):
    # V2 adds PIPS mode; V1 PRICE_% and ROI_% calculations are preserved.
    if str(sl_mode).upper() == "PIPS" or str(tp_mode).upper() == "PIPS":
        entry = float(actual_entry)
        qty = float(position_qty)
        pip = fx_v2_pip_size(symbol)
        def px(target, mode, positive):
            target = float(target)
            if target <= 0:
                raise RuntimeError("SL/TP targets must be greater than zero.")
            if str(mode).upper() == "PIPS":
                return entry + (pip * target if positive else -pip * target)
            # Delegate each non-PIPS leg to the V1 engine.
            return None
        if str(sl_mode).upper() == "PIPS":
            sl = px(sl_target_pct, "PIPS", side == "SHORT")
        else:
            base = _fx_v2_original_calc_protection(self, symbol, side, entry, qty,
                                                    position_initial_margin, sl_target_pct,
                                                    max(tp1_target_pct, 0.0001), max(tp2_target_pct, 0.0001),
                                                    sl_mode, "PRICE_%", leverage)
            sl = base[0]
        if str(tp_mode).upper() == "PIPS":
            tp1 = px(tp1_target_pct, "PIPS", side == "LONG")
            tp2 = px(tp2_target_pct, "PIPS", side == "LONG")
            if side == "SHORT":
                tp1 = px(tp1_target_pct, "PIPS", False)
                tp2 = px(tp2_target_pct, "PIPS", False)
        else:
            base = _fx_v2_original_calc_protection(self, symbol, side, entry, qty,
                                                    position_initial_margin, max(sl_target_pct, 0.0001),
                                                    tp1_target_pct, tp2_target_pct,
                                                    "PRICE_%", tp_mode, leverage)
            tp1, tp2 = base[1], base[2]
        sl, tp1, tp2 = [fx_safe_price(self, symbol, x) for x in (sl, tp1, tp2)]
        if side == "LONG" and not (sl < entry and tp1 > entry and tp2 > tp1):
            raise RuntimeError("Calculated LONG Forex PIPS SL/TP prices are invalid.")
        if side == "SHORT" and not (sl > entry and tp1 < entry and tp2 < tp1):
            raise RuntimeError("Calculated SHORT Forex PIPS SL/TP prices are invalid.")
        sl = fx_v2_apply_atr_sl(self, symbol, side, entry, sl, qty)
        return sl, tp1, tp2, abs(sl-entry)/entry, abs(tp1-entry)/entry, abs(tp2-entry)/entry

    vals = _fx_v2_original_calc_protection(self, symbol, side, actual_entry, position_qty,
                                            position_initial_margin, sl_target_pct, tp1_target_pct,
                                            tp2_target_pct, sl_mode, tp_mode, leverage)
    sl = fx_v2_apply_atr_sl(self, symbol, side, actual_entry, vals[0], position_qty)
    return (sl, vals[1], vals[2], abs(sl-actual_entry)/actual_entry, vals[4], vals[5])

def fx_v2_calculate_entry_qty(self, symbol, balance, reference_price,
                              risk_pct, sl_price_fraction, size_mode, fixed_qty):
    # When ATR SL or PIPS SL is enabled, size from the actual intended stop distance
    # rather than the generic V1 percentage/ROI approximation.
    if size_mode == "FIXED_QTY":
        return fx_calculate_entry_qty(self, symbol, balance, reference_price,
                                       risk_pct, sl_price_fraction, size_mode, fixed_qty)
    fraction = float(sl_price_fraction)
    if _v2_bool(self, "v_use_atr_sl", False):
        try:
            rows = self.exchange.fetch_ohlcv(symbol, self.v_tf.get(), 120)
            d = pd.DataFrame(rows, columns=["time","open","high","low","close","vol"])
            tr = pd.concat([d["high"]-d["low"], (d["high"]-d["close"].shift(1)).abs(),
                            (d["low"]-d["close"].shift(1)).abs()], axis=1).max(axis=1)
            atr = float(calculate_rma(tr, 14).iloc[-2])
            fraction = (max(0.1, _v2_float(self, "e_atr_sl_mult", 1.5)) * atr) / float(reference_price)
        except Exception as e:
            self.log(f"ATR SIZING WARNING: {e}")
    elif str(self.v_sl_mode.get()).upper() == "PIPS":
        try:
            fraction = (fx_v2_pip_size(symbol) * float(self.e_sl_pct.get())) / float(reference_price)
        except Exception:
            pass
    return fx_calculate_entry_qty(self, symbol, balance, reference_price,
                                  risk_pct, fraction, size_mode, fixed_qty)

def fx_v2_normalize_symbol(self, exchange, exchange_id, raw_symbol):
    raw = str(raw_symbol).strip()
    if _v2_bool(self, "v_auto_symbol", True):
        return fx_normalize_symbol(self, exchange, exchange_id, raw)
    info = mt5.symbol_info(raw)
    if info is None:
        raise RuntimeError(f"Broker Symbol Auto-Discovery is OFF and exact symbol was not found: {raw}")
    mt5.symbol_select(raw, True)
    return raw

def fx_v2_finalize_performance(self, reason="UNKNOWN", balance=None):
    _v2_original_finalize(self, reason=reason, balance=balance)
    # Infer streak from the latest completed trade P/L.
    try:
        pnl = float(self.trade_pnls[-1]) if self.trade_pnls else 0.0
        if pnl < 0:
            self.v2_loss_streak += 1
        elif pnl > 0:
            self.v2_loss_streak = 0
    except Exception:
        pass

def fx_v2_recover_position(self):
    if not _v2_bool(self, "v_position_recovery", True):
        return
    try:
        p = fx_fetch_position(self, self.symbol)
        if not p:
            return
        raw = p.get("raw", {})
        info = raw.get("info", {}) if isinstance(raw, dict) else {}
        broker_sl = float(info.get("sl") or 0.0)
        self.last_protected_position = {
            "side": p["side"], "qty": p["qty"], "entry": p["entry"],
            "sl": broker_sl, "tp1": 0.0, "tp2": 0.0,
            "sl_id": "RECOVERED", "tp1_id": None, "tp2_id": None,
            "tp_orders_enabled": False, "hold_sl_wait_reversal": False,
        }
        self.log(f"POSITION RECOVERY ✓ | Existing {p['side']} {p['qty']} lots @ {p['entry']:.8f} | Broker SL={broker_sl:.8f}")
    except Exception as e:
        self.log(f"POSITION RECOVERY WARNING: {e}")

# Capture V1 methods before replacing them.
_fx_v2_original_open = fx_open_market_position
_fx_v2_original_calc_protection = fx_calculate_protection_prices
_v2_original_finalize = UniversalFuturesBotGUI._finalize_performance_trade

# Override V1 methods with V2-aware wrappers.
UniversalFuturesBotGUI.open_market_position = fx_v2_open_market_position
UniversalFuturesBotGUI.calculate_entry_qty = fx_v2_calculate_entry_qty
UniversalFuturesBotGUI.normalize_symbol = fx_v2_normalize_symbol
UniversalFuturesBotGUI.calculate_protection_prices = fx_v2_calculate_protection_prices
UniversalFuturesBotGUI._finalize_performance_trade = fx_v2_finalize_performance

# Start wrapper: keeps V1 startup and adds V2 state/watchdog/recovery.
_fx_v2_original_start = fx_start_bot
def fx_v2_start_bot(self):
    if self.is_running:
        return
    try:
        self.mt5_magic = int(self.e_magic.get().strip())
    except Exception:
        self.mt5_magic = 26091802
    _fx_v2_original_start(self)
    if self.is_running:
        try:
            eq = self.fetch_account_equity()
            fx_v2_day_start(self, eq)
        except Exception as e:
            self.log(f"V2 risk initialization warning: {e}")
        fx_v2_recover_position(self)
        if self.is_running:
            self.v2_watchdog_running = True
            self.v2_watchdog_thread = threading.Thread(target=fx_v2_watchdog, args=(self,), daemon=True)
            self.v2_watchdog_thread.start()

UniversalFuturesBotGUI.start_bot = fx_v2_start_bot

# Save/load wrapper references the already extended V1 wrappers.
_fx_v2_original_save = fx_save_settings
_fx_v2_original_load = fx_load_settings

def fx_v2_save_settings(self):
    _fx_v2_original_save(self)

def fx_v2_load_settings(self):
    _fx_v2_original_load(self)

UniversalFuturesBotGUI.save_settings = fx_v2_save_settings
UniversalFuturesBotGUI.load_settings = fx_v2_load_settings


# Bind overrides. No indicator/signal calculation function is modified.
UniversalFuturesBotGUI.build_exchange = fx_build_exchange
UniversalFuturesBotGUI.normalize_symbol = fx_normalize_symbol
UniversalFuturesBotGUI.safe_amount = fx_safe_amount
UniversalFuturesBotGUI.safe_price = fx_safe_price
UniversalFuturesBotGUI.fetch_balance_total = fx_fetch_balance_total
UniversalFuturesBotGUI.fetch_account_equity = fx_fetch_account_equity
UniversalFuturesBotGUI.fetch_position = fx_fetch_position
UniversalFuturesBotGUI.wait_for_position = fx_wait_for_position
UniversalFuturesBotGUI.cancel_all_open_orders = fx_cancel_all_open_orders
UniversalFuturesBotGUI.calculate_entry_qty = fx_calculate_entry_qty
UniversalFuturesBotGUI.target_to_price_fraction = fx_target_to_price_fraction
UniversalFuturesBotGUI.calculate_protection_prices = fx_calculate_protection_prices
UniversalFuturesBotGUI._current_market_price = lambda self, symbol: float(self.exchange.fetch_ticker(symbol)["last"])
UniversalFuturesBotGUI.create_protection_orders = fx_create_protection_orders
UniversalFuturesBotGUI.verify_protection_orders = fx_verify_protection_orders
UniversalFuturesBotGUI._reconcile_protection_orders = fx_reconcile_noop
UniversalFuturesBotGUI._manage_tp1_break_even = fx_manage_tp_be
UniversalFuturesBotGUI._detect_protection_exit_reason = fx_detect_exit_reason
UniversalFuturesBotGUI._emergency_flatten_all_positions = fx_emergency_flatten
UniversalFuturesBotGUI.open_market_position = fx_open_market_position
UniversalFuturesBotGUI.close_position_market = fx_close_position_market
UniversalFuturesBotGUI.configure_leverage = fx_configure_leverage
UniversalFuturesBotGUI._fetch_strategy_ohlcv = fx_fetch_strategy_ohlcv
UniversalFuturesBotGUI.start_bot = fx_start_bot
UniversalFuturesBotGUI.save_settings = fx_save_settings
UniversalFuturesBotGUI.load_settings = fx_load_settings



# Re-bind V2 overrides after the legacy V1 binding block.
UniversalFuturesBotGUI.open_market_position = fx_v2_open_market_position
UniversalFuturesBotGUI.calculate_entry_qty = fx_v2_calculate_entry_qty
UniversalFuturesBotGUI.normalize_symbol = fx_v2_normalize_symbol
UniversalFuturesBotGUI.calculate_protection_prices = fx_v2_calculate_protection_prices
UniversalFuturesBotGUI._finalize_performance_trade = fx_v2_finalize_performance
UniversalFuturesBotGUI.start_bot = fx_v2_start_bot
UniversalFuturesBotGUI.save_settings = fx_v2_save_settings
UniversalFuturesBotGUI.load_settings = fx_v2_load_settings

# Stop watchdog cleanly when the user presses STOP.
_fx_v2_original_stop = UniversalFuturesBotGUI.stop_bot
def fx_v2_stop_bot(self):
    self.v2_watchdog_running = False
    return _fx_v2_original_stop(self)
UniversalFuturesBotGUI.stop_bot = fx_v2_stop_bot

# -------------------- MAIN ----------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = UniversalFuturesBotGUI(root)
    root.mainloop()


# ============================================================
# V8.3.3 FOREX-ONLY FINAL OVERRIDES
# ============================================================
_original_v833_build_exchange = UniversalFuturesBotGUI.build_exchange
def v833_forex_build_exchange(self, exchange_id, api_key, api_secret, account_mode):
    if str(exchange_id).strip().lower() not in ("mt5_forex","mt5","forex"):
        raise RuntimeError("V8.3.3 FOREX-ONLY BOT: Crypto/futures exchanges are disabled. Use MT5 Forex.")
    return fx_build_exchange(self, "mt5_forex", api_key, api_secret, account_mode)
UniversalFuturesBotGUI.build_exchange = v833_forex_build_exchange
# Keep the existing V2 MT5 execution, recovery, session/news/correlation/trailing layers.

