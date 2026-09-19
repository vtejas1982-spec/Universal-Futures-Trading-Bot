import json
import os
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk

import ccxt
import numpy as np
import pandas as pd
import requests
import sys
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


APP_TITLE = "Universal Futures Trading Bot V8 - Multi-Exchange (No KuCoin)"

# Keep the config and trade log beside the executable when packaged with PyInstaller.
# When running the .py directly, keep them beside the script.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_FILE = str(APP_DIR / "config_universal_fixed.json")
LOG_FILE = str(APP_DIR / "universal_trade_logs_fixed.csv")


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
# Liquidity Swings © LuxAlgo — CC BY-NC-SA 4.0.
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


# -------------------- GUI BOT -------------------------------

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
        self.daily_start_balance = 0.0
        self.daily_start_date = None
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
        # After a stop-loss / break-even stop exit, optionally require the        # strategy to produce a valid opposite signal before allowing a
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
        """Build the V8 interface.

        This method intentionally reorganizes presentation only.  All existing
        widget names, StringVar/BooleanVar objects, defaults, callbacks and
        configuration fields are preserved so the trading logic and saved
        settings remain compatible.
        """
        title = tk.Label(
            self.root,
            text="Universal Futures Trading Bot V8 - Multi-Exchange Futures",
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

        tk.Label(
            f_api,
            text=(
                "Bybit: BYBIT_DEMO / BYBIT_TESTNET | "
                "Binance/Gate: TESTNET where supported | "
                "Bitget/WEEX: DEMO"
            ),
            fg="#555555",
        ).grid(
            row=4,
            column=0,
            columnspan=5,
            sticky="w",
        )

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
        ttk.OptionMenu(
            f_strat, self.v_nwe_entry_mode, "FRESH_CROSS",
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
        self.v_signal_mode = tk.StringVar(value="SINGLE_SIGNAL")
        tk.Label(f_strat, text="Signal Mode:").grid(row=31, column=0, sticky="w")
        ttk.OptionMenu(
            f_strat,
            self.v_signal_mode,
            "SINGLE_SIGNAL",
            "SINGLE_SIGNAL",
            "2_SIGNALS",
            "3_SIGNALS",
            "4_SIGNALS",
            "SCORE",
            "STRICT_ALL_FILTERS",
        ).grid(row=31, column=1, padx=5, sticky="w")

        tk.Label(f_strat, text="Score (SCORE mode):").grid(row=31, column=2, sticky="e")
        self.e_min_score = tk.Entry(f_strat, width=5)
        self.e_min_score.insert(0, "4")
        self.e_min_score.grid(row=31, column=3, padx=2)

        self.v_hold_until_all_reverse = tk.BooleanVar(value=True)
        tk.Checkbutton(
            f_strat,
            text="Hold Position Until ALL Active Signals Reverse",
            variable=self.v_hold_until_all_reverse,
        ).grid(row=32, column=0, columnspan=4, sticky="w")

        tk.Label(
            f_strat,
            text="ON: open trade waits until every enabled directional module shows the opposite direction. OFF: normal reversal.",
            fg="#444444",
        ).grid(row=33, column=0, columnspan=8, sticky="w")

        tk.Label(
            f_strat,
            text=(
                "SINGLE_SIGNAL = any ONE enabled signal can trade; "
                "2/3/4_SIGNALS = required directional votes; SCORE = custom minimum votes; "
                "STRICT_ALL_FILTERS = original strict mode."
            ),
            fg="#444444",
        ).grid(row=34, column=0, columnspan=8, sticky="w", pady=3)

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

        # 4. Grid Trading Engine
        f_grid = tk.LabelFrame(self.tab_grid, text=" 4. Grid Trading Engine ")
        f_grid.pack(fill="x", padx=10, pady=5)

        tk.Label(f_grid, text="Grid Mode:").grid(row=0, column=0, sticky="w")
        self.v_grid_mode = tk.StringVar(value="OFF")
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
        self.e_grid_sl = tk.Entry(f_grid, width=7); self.e_grid_sl.insert(0, "5.0"); self.e_grid_sl.grid(row=2, column=1, padx=5, sticky="w")
        tk.Label(f_grid, text="Max Exposure USDT:").grid(row=2, column=2, sticky="e")
        self.e_grid_max_exposure = tk.Entry(f_grid, width=9); self.e_grid_max_exposure.insert(0, "100"); self.e_grid_max_exposure.grid(row=2, column=3, padx=3)        tk.Label(f_grid, text="Max Grid DD %:").grid(row=2, column=4, sticky="e")
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
            "hold_until_all_reverse": self.v_hold_until_all_reverse.get(),

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

            self.v_grid_mode.set(cfg.get("grid_mode", "OFF"))
            for widget, key, default in ((self.e_grid_levels, "grid_levels", "5"), (self.e_grid_spacing, "grid_spacing", "1.0"), (self.e_grid_order_size, "grid_order_size", "10"), (self.e_grid_size_increase, "grid_size_increase", "0"), (self.e_grid_tp, "grid_tp", "1.0"), (self.e_grid_sl, "grid_sl", "5.0"), (self.e_grid_max_exposure, "grid_max_exposure", "100"), (self.e_grid_max_dd, "grid_max_dd", "3.0"), (self.e_grid_score_min, "grid_score_min", "1"), (self.e_grid_recenter, "grid_recenter_distance", "3.0"), (self.e_grid_cooldown, "grid_cooldown", "30")):
                widget.delete(0, tk.END); widget.insert(0, cfg.get(key, default))
            self.v_grid_trend_filter.set(cfg.get("grid_trend_filter", "OFF"))
            self.v_grid_recenter.set(cfg.get("grid_recenter", False))

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

            legacy_mode_map = {                "ALL_FILTERS": "STRICT_ALL_FILTERS",
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
            self.root.after(0, lambda: self._set_bot_button_states(running=False))
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
            # Bybit V5 returns only 20 open orders by default and allows up to
            # 50 per page. Grid uses at most 50 entry levels, so explicitly
            # request the maximum page size.  Relying on the exchange default
            # can make a 50-level Grid look partially missing and cause the
            # engine to recreate orders that are still open.
            if self.exchange_id == "bybit":
                return self.exchange.fetch_open_orders(
                    symbol,
                    limit=50,
                )
            return self.exchange.fetch_open_orders(
                symbol,
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
    ):        params = {
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
        oid = str(order_id or "")
        if not oid:
            return False
        try:
            order = self.exchange.fetch_order(oid, symbol)
            status = str(order.get("status") or "").lower()
            return status in ("open", "new", "partially_filled", "pending")
        except Exception:
            # If the exchange cannot confirm cancellation, keep the ID pending.
            return True

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
        grid_score_min = int(self.e_grid_score_min.get())
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
            if grid_score_min > enabled_strategy_count:
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
                if grid_score_min > enabled_strategy_count:
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
        score_min = int(cfg["score_min"])
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
            oid = meta.get("id")
            if oid:
                try:
                    self.exchange.cancel_order(oid, symbol)
                except Exception as e:
                    self.log(f"GRID FILTER CANCEL WARNING: {e} | ID={oid}")
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
                order = self.exchange.fetch_order(oid, symbol)
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
                    "retaining local order state."                )

    def _grid_manage_protection(self, symbol, cfg, position):
        """Synchronize Grid basket TP/SL without leaving a half-protected position."""
        if not position or float(position.get("qty") or 0) <= 0:
            for oid in (self.grid_state.get("tp_order_id"), self.grid_state.get("sl_order_id")):
                if oid:
                    try:
                        self.exchange.cancel_order(oid, symbol)
                    except Exception:
                        pass
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
            try:
                open_orders = self.fetch_open_orders_safe(symbol)
                open_ids = {str(o.get("id")) for o in open_orders if o.get("id")}
            except Exception as e:
                # A temporary exchange read failure is not evidence that
                # protection disappeared; retain the known-good local state.
                self.log(f"GRID PROTECTION VERIFY NOTICE: {e}")
                return

            if existing_tp_id in open_ids and existing_sl_id in open_ids:
                return

            missing = []
            if existing_tp_id not in open_ids:
                missing.append("TP")
            if existing_sl_id not in open_ids:
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
            open_orders = self.fetch_open_orders_safe(symbol)
            open_ids = {str(o.get("id")) for o in open_orders if o.get("id")}
            if str(new_sl.get("id") or "") not in open_ids or str(new_tp.get("id") or "") not in open_ids:
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

    def _grid_stop(self, symbol, reason, cooldown_seconds=0):
        """Stop Grid safely: close inventory before removing its protection."""
        self.log(f"GRID STOP: {reason}")
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
            self._grid_cancel_managed_orders(symbol)
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

        score_min = int(cfg["score_min"])
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
        # basket TP/SL protection.
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

            # Validate all Grid controls before modifying exchange leverage.
            # This keeps startup transactional: bad Grid settings fail locally
            # without changing the account's leverage first.
            self._grid_validate_settings()

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
            self.daily_start_balance = self.start_balance
            self.daily_start_date = datetime.now().date()

            self.total_trades = 0
            self.opened_trades = 0
            self.winning_trades = 0
            self.losing_trades = 0
            self.trade_pnls = []
            self.active_trade = None
            self.session_started_at = time.time()
            self.session_max_trades = max_trades

            grid_cfg = self._grid_initialize(self.symbol, self.start_balance, self.fetch_account_equity())
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

            messagebox.showerror(
                "Bot start failed",
                str(e),
            )

    def stop_bot(self):
        # Flip the run flag first so the worker cannot begin another execution
        # cycle while Grid shutdown is cleaning up exchange orders/positions.
        self.is_running = False
        try:
            grid_mode = self.v_grid_mode.get().strip().upper()
            if self.symbol and grid_mode in ("LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID"):
                if self.grid_state.get("active"):
                    self._grid_stop(self.symbol, "Manual bot stop", cooldown_seconds=0)
                else:
                    # Retry any locally tracked Grid orders even if the engine
                    # was already marked inactive after a previous cleanup.
                    self._grid_cancel_managed_orders(self.symbol)
                self.log("GRID ENGINE STOPPED safely.")
        except Exception as e:
            self.log(f"GRID stop cleanup warning: {e}")

        self.log(
            "Stopping execution thread..."
        )

        self._set_bot_button_states(running=False)

    def on_close(self):
        if self.is_running:
            if not messagebox.askyesno(
                "Stop bot?",
                "Bot is running. Stop it and close?",
            ):
                return

        # Stop Grid safely before GUI exit; do not remove protection from a
        # position unless the position has first been confirmed flat.
        self.is_running = False
        try:
            grid_mode = self.v_grid_mode.get().strip().upper()
            if self.symbol and grid_mode in ("LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID"):
                if self.grid_state.get("active"):
                    self._grid_stop(self.symbol, "GUI shutdown", cooldown_seconds=0)
                else:
                    self._grid_cancel_managed_orders(self.symbol)
                self.log("GRID ENGINE SHUTDOWN completed safely.")
        except Exception as e:
            self.log(f"GRID shutdown cleanup warning: {e}")

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
        timeframe candle. It does not guarantee that a signal/trade will        occur on every candle.
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
            if trendline_buffer < 0:
                raise ValueError("Trendline Breakout Buffer cannot be negative.")
            if trendline_retest_candles <= 0:
                raise ValueError("Trendline Retest Candles must be greater than 0.")
            if trendline_entry_mode not in ("FRESH_BREAK", "CURRENT_TREND", "BREAK_RETEST"):
                raise ValueError("Trendline Entry must be FRESH_BREAK, CURRENT_TREND, or BREAK_RETEST.")

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

                    # Reset the daily drawdown reference at local midnight.
                    # Emergency Capital Loss Stop remains session-based.
                    today = datetime.now().date()
                    if self.daily_start_date != today:
                        self.daily_start_date = today
                        self.daily_start_balance = curr_balance
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
                        (
                            self.daily_start_balance
                            - curr_balance
                        )
                        / self.daily_start_balance
                        if self.daily_start_balance > 0
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
                        limit=600 if (use_nwe or use_liq_swings or use_trendline) else 250,
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
                            breakout_buffer_pct=trendline_buffer,
                            retest_candles=trendline_retest_candles,
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

                    # Volume is a strength/participation measure rather than
                    # a direction by itself. If volume is above its MA, its
                    # vote follows the completed candle direction.
                    if use_vol and vol_pass:
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
                    if use_atr and atr_pass:
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

                    grid_buy_score = sum(
                        1 for _, bull, _ in grid_directional_modules if bull
                    )
                    grid_sell_score = sum(
                        1 for _, _, bear in grid_directional_modules if bear
                    )
                    grid_score_count = len(grid_directional_modules)

                    # SINGLE_SIGNAL is a pure single-signal mode:
                    # ONE enabled signal is enough. No second indicator,
                    # Volume, ADX, ATR, MTF, or agreement check is required.
                    # If any enabled module produces BUY, BUY is allowed; if
                    # any enabled module produces SELL, SELL is allowed.
                    # When both directions appear simultaneously, the first
                    # directional vote in the enabled-module order wins,
                    # making the result deterministic without requiring a
                    # second confirmation.
                    if signal_mode == "SINGLE_SIGNAL":
                        single_signal = "NONE"
                        for name, bull, bear in directional_modules:
                            if bull:
                                single_signal = "BUY"
                                break
                            if bear:
                                single_signal = "SELL"
                                break

                        buy_signal = single_signal == "BUY"
                        sell_signal = single_signal == "SELL"

                    elif signal_mode in (
                        "SCORE",
                        "2_SIGNALS",
                        "3_SIGNALS",
                        "4_SIGNALS",
                    ):
                        # Every enabled module that passes its own condition
                        # contributes one vote. Volume/ADX/ATR are no longer
                        # added a second time as hard confirmations in these
                        # voting modes.
                        #
                        # If fewer modules pass than the requested vote count,
                        # no trade is made.
                        buy_signal = (
                            directional_count > 0
                            and buy_score >= min_score
                            and buy_score > sell_score
                        )

                        sell_signal = (
                            directional_count > 0
                            and sell_score >= min_score
                            and sell_score > buy_score
                        )

                    else:
                        # STRICT_ALL_FILTERS: every enabled directional module
                        # must explicitly vote in the same direction, plus all
                        # enabled confirmation filters must pass. This prevents
                        # disabled modules (whose neutral values are True) from
                        # creating a false BUY/SELL when no directional module is enabled.
                        strict_buy_votes = bool(directional_modules) and all(
                            bool(bull) and not bool(bear)
                            for _, bull, bear in directional_modules
                        )
                        strict_sell_votes = bool(directional_modules) and all(
                            bool(bear) and not bool(bull)
                            for _, bull, bear in directional_modules
                        )
                        buy_signal = strict_buy_votes and atr_pass and vol_pass and adx_pass and mtf_pass_bull
                        sell_signal = strict_sell_votes and atr_pass and vol_pass and adx_pass and mtf_pass_bear

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
                    if use_vol and vol_pass:
                        hold_directional_modules.append(("VOL", candle_bull, candle_bear))
                    if use_adx and adx_pass:
                        hold_directional_modules.append(("ADX", adx_bull, adx_bear))
                    if use_atr and atr_pass:
                        hold_directional_modules.append(("ATR", candle_bull, candle_bear))

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
                                new_position.get(                                    "initial_margin",
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
                    lambda: self._set_bot_button_states(running=False),
                )
            except Exception:
                pass

            self.log(
                "Bot execution thread halted."
            )


# -------------------- MAIN ----------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = UniversalFuturesBotGUI(root)
    root.mainloop()