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
import subprocess
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


APP_VERSION = "V8.4.2-CRYPTO-EVIDENCE-HARDENED-R9.3"
APP_TITLE = "Universal Futures Trading Bot V8.4.2-R9.3 - Crypto Production Engine"
AUDIT_BUILD = "V8.4.2-ENGINE-AUDIT-2026-09-27-R9.3-STOP-FIX-FIXED-QTY"
# V8.3.3 safety hardening: persist retired managed-order IDs across flat exits and clean only exact checkpoint-proven stale bot orders.\n
# Keep the config and trade log beside the executable when packaged with PyInstaller.
# When running the .py directly, keep them beside the script.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_FILE = str(APP_DIR / "config_universal_fixed.json")
LOG_FILE = str(APP_DIR / "universal_trade_logs_fixed.csv")
PROFILE_DIR = APP_DIR / "bot_profiles"
MASTER_DB_FILE = str(APP_DIR / "universal_bot_master.db")
MASTER_CSV_FILE = str(APP_DIR / "universal_bot_master_log.csv")

# R9 lifecycle hardening: cross-process profile STOP control, truthful stale-runtime status,
# profile heartbeat, and explicit single-symbol max-open-position contract.
# V8.2 configuration/runtime contracts.
CONFIG_SCHEMA_VERSION = 10  # R8 adds Fixed-Qty Risk Guard configuration.
RUNTIME_SCHEMA_VERSION = 9  # R9.3 hardens stop completion + Fixed-Qty independence.
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

# V8.4 Evidence-Family contract. Core indicator functions are retained in this live file so the strategy is self-contained.
# REGIME is deliberately a gate family, not a directional voting family:
# ATR/ADX must pass, but never count as independent directional confirmation.
EVIDENCE_FAMILIES = {
    "TREND": ("ST", "EMA", "EMA_CROSS", "MACD", "VIDYA", "NWE"),
    "MOMENTUM": ("RSI", "STOCH", "DIVERGENCE"),
    "FLOW": ("VWAP", "VWAP_DELTA", "VOL", "VOL_SR"),
    "STRUCTURE": ("LIQ_SWING", "TRENDLINE", "MTF"),
    "REGIME": ("ATR", "ADX"),
}
EVIDENCE_FAMILY_ORDER = ("TREND", "MOMENTUM", "FLOW", "STRUCTURE")
EVIDENCE_DEFAULT_MIN_FAMILIES = 2
EVIDENCE_DEFAULT_FAMILY_MIN_SCORE = 0.35
EVIDENCE_DEFAULT_REQUIRE_TREND = True
EVIDENCE_DEFAULT_REQUIRE_INDEPENDENT = True

# V8.3.2 requested default trading profile.
# These are GUI defaults for a NEW/unsaved profile; an existing saved profile
# remains authoritative and is not silently overwritten.
DEFAULT_SIGNAL_MODE = "ADAPTIVE_EVIDENCE"
DEFAULT_ADAPTIVE_EDGE = "0.18"
DEFAULT_ADAPTIVE_MIN_WEIGHT = "3.5"
DEFAULT_USE_MTF = True
DEFAULT_USE_ADX = True
DEFAULT_USE_VOLUME = True
DEFAULT_USE_ATR = True
DEFAULT_GRID_MODE = "OFF"
DEFAULT_MAX_OPEN_TRADES = 1
DEFAULT_ATR_SL_ENABLED = True
DEFAULT_ATR_SL_MULTIPLIER = 1.5
DEFAULT_ATR_TP1_MULTIPLIER = 1.2
DEFAULT_ATR_TP2_MULTIPLIER = 2.2
DEFAULT_RISK_MODE = "EQUITY_RISK_%"
DEFAULT_RISK_PER_TRADE = "0.75"
DEFAULT_POST_SL_OPPOSITE_LOCK = True
DEFAULT_NO_SAME_CANDLE = True
DEFAULT_COOLDOWN_MIN = "15"
DEFAULT_USE_DIVERGENCE = True
DEFAULT_DIV_USE_ALL = True
MAX_CONSECUTIVE_CYCLE_ERRORS = 3
MAX_CONSECUTIVE_TRANSIENT_CYCLE_ERRORS = 10
MAX_STOP_WAIT_SECONDS = 20.0
# R9.3 FAIL-CLOSED KILL SWITCH + STOP COMPLETION:
# Any bot stop, worker crash, fatal execution halt, or stale heartbeat must
# flatten the bot-owned symbol and cancel its open orders.  This is mandatory
# for this production build; it is intentionally not a user-disableable flag.
KILL_SWITCH_REQUIRED = True
KILL_SWITCH_HEARTBEAT_SECONDS = 3.0
KILL_SWITCH_STALE_SECONDS = 45.0
KILL_SWITCH_RETRY_SECONDS = 1.0
KILL_SWITCH_MAX_ATTEMPTS = 4
PROFILE_CONTROL_SCHEMA_VERSION = 1
PROFILE_STATUS_HEARTBEAT_MS = 3000
REMOTE_STOP_STALE_SECONDS = 300.0
ACCOUNT_READ_RETRIES = 3
ACCOUNT_READ_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
MAX_DATA_STALENESS_MULTIPLIER = 2.5
DEFAULT_ADX_LEN = 14
PROFILE_OPERATION_SCHEMA_VERSION = 2  # V8.2.2 explicit current-vs-selected profile controls
# V8.3.0 advanced strategy defaults
DIVERGENCE_INDICATORS = (
    "MACD", "MACD_HIST", "RSI", "STOCH", "CCI",
    "MOMENTUM", "OBV", "VWMACD", "CMF", "MFI",
)

# V8.2.3: normalize GUI symbols before live checkpoint identity checks.


def _kill_switch_profile_paths(profile_id):
    """Return profile paths without constructing the Tk GUI."""
    raw = str(profile_id or "BOT-01").strip().upper()
    raw = re.sub(r"[^A-Z0-9._-]+", "_", raw).strip("._-")[:64] or "BOT-01"
    folder = PROFILE_DIR / raw
    return raw, folder, folder / "config.json", folder / "runtime_state.json", folder / "kill_switch_heartbeat.json", folder / "kill_switch.log"


def _kill_switch_log(path, message):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\\n")
    except Exception:
        pass


def _kill_switch_read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _kill_switch_exchange(exchange_id, api_key, api_secret, account_mode):
    supported = {
        "bybit": "swap", "binance": "future", "gate": "swap",
        "bitget": "swap", "weex": "swap",
    }
    allowed_modes = {
        "bybit": {"BYBIT_DEMO", "BYBIT_TESTNET", "LIVE"},
        "binance": {"TESTNET", "LIVE"},
        "gate": {"TESTNET", "LIVE"},
        "bitget": {"DEMO", "LIVE"},
        "weex": {"DEMO", "LIVE"},
    }
    exchange_id = str(exchange_id or "").strip().lower()
    account_mode = str(account_mode or "").strip().upper()
    if exchange_id not in supported or account_mode not in allowed_modes.get(exchange_id, set()):
        raise RuntimeError(f"Kill switch: unsupported exchange/account mode: {exchange_id}/{account_mode}")
    exchange = getattr(ccxt, exchange_id)({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": supported[exchange_id]},
    })
    if exchange_id == "bybit":
        if account_mode == "BYBIT_DEMO":
            if not hasattr(exchange, "enable_demo_trading"):
                raise RuntimeError("Installed CCXT does not support Bybit Demo Trading.")
            exchange.enable_demo_trading(True)
        elif account_mode == "BYBIT_TESTNET":
            exchange.set_sandbox_mode(True)
    elif exchange_id == "binance" and account_mode == "TESTNET":
        exchange.set_sandbox_mode(True)
    elif exchange_id == "gate" and account_mode == "TESTNET":
        exchange.set_sandbox_mode(True)
    elif exchange_id == "bitget" and account_mode == "DEMO":
        if hasattr(exchange, "enable_demo_trading"):
            exchange.enable_demo_trading(True)
        else:
            exchange.set_sandbox_mode(True)
    elif exchange_id == "weex" and account_mode == "DEMO":
        exchange.set_sandbox_mode(True)
    exchange.load_markets()
    return exchange


def _kill_switch_flatten_profile(profile_id, reason="KILL SWITCH"):
    """Emergency flatten one bot profile's configured symbol and cancel orders."""
    profile, folder, config_path, runtime_path, heartbeat_path, log_path = _kill_switch_profile_paths(profile_id)
    cfg = _kill_switch_read_json(config_path)
    if not cfg and profile == "BOT-01":
        cfg = _kill_switch_read_json(CONFIG_FILE)
    runtime = _kill_switch_read_json(runtime_path)
    if not cfg:
        raise RuntimeError(f"Kill switch: no configuration found for {profile}.")
    exchange_id = str(runtime.get("exchange") or cfg.get("exchange") or "").lower()
    account_mode = str(runtime.get("account_mode") or cfg.get("account_mode") or "").upper()
    symbol = str(runtime.get("symbol") or cfg.get("symbol") or "").strip().upper()
    api_key = str(cfg.get("api_key") or "").strip()
    api_secret = str(cfg.get("api_secret") or "").strip()
    if not exchange_id or not symbol or not api_key or not api_secret:
        raise RuntimeError(f"Kill switch: incomplete exchange identity for {profile}.")
    exchange = _kill_switch_exchange(exchange_id, api_key, api_secret, account_mode)
    if symbol not in exchange.markets:
        compact = symbol.replace("/", "").replace(":", "")
        candidates = [
            sym for sym, market in exchange.markets.items()
            if sym.replace("/", "").replace(":", "").upper() == compact
            and (market.get("swap") or market.get("future") or market.get("contract"))
        ]
        if candidates:
            symbol = candidates[0]
        else:
            raise RuntimeError(f"Kill switch: symbol not found on {exchange_id}: {symbol}")

    _kill_switch_log(log_path, f"ARMED | Profile={profile} | Symbol={symbol} | Reason={reason}")
    last_error = None
    for attempt in range(1, KILL_SWITCH_MAX_ATTEMPTS + 1):
        try:
            # Cancel every open order on the bot-owned symbol. This deliberately
            # removes stale entry/TP/SL/grid orders so a stopped bot cannot leave
            # an order behind that can create a new position later.
            try:
                if hasattr(exchange, "cancel_all_orders"):
                    exchange.cancel_all_orders(symbol)
            except Exception as e:
                _kill_switch_log(log_path, f"Cancel-all warning | Attempt={attempt} | {e}")
            try:
                orders = exchange.fetch_open_orders(symbol)
                for order in orders:
                    oid = order.get("id")
                    if oid:
                        try:
                            exchange.cancel_order(oid, symbol)
                        except Exception as e:
                            _kill_switch_log(log_path, f"Cancel warning | ID={oid} | {e}")
            except Exception as e:
                raise RuntimeError(f"Open-order verification failed: {e}") from e

            positions = exchange.fetch_positions([symbol])
            live = []
            for pos in positions or []:
                side = str(pos.get("side") or "").upper()
                try:
                    qty = abs(float(pos.get("contracts") or 0))
                except Exception:
                    qty = 0.0
                if qty > 0 and side in ("LONG", "SHORT"):
                    live.append((side, qty, pos))

            for side, qty, pos in live:
                market = exchange.market(symbol)
                try:
                    qty = float(exchange.amount_to_precision(symbol, qty))
                except Exception:
                    pass
                if qty <= 0:
                    continue
                close_side = "sell" if side == "LONG" else "buy"
                params = {"reduceOnly": True}
                if exchange_id == "bybit":
                    params["positionIdx"] = 0
                exchange.create_order(symbol, "market", close_side, qty, None, params)
                _kill_switch_log(log_path, f"CLOSE SENT | Attempt={attempt} | Side={side} | Qty={qty:g} | Symbol={symbol}")

            time.sleep(0.75)
            remaining_positions = exchange.fetch_positions([symbol])
            remaining = []
            for pos in remaining_positions or []:
                side = str(pos.get("side") or "").upper()
                try:
                    qty = abs(float(pos.get("contracts") or 0))
                except Exception:
                    qty = 0.0
                if qty > 0 and side in ("LONG", "SHORT"):
                    remaining.append((side, qty))
            remaining_orders = exchange.fetch_open_orders(symbol)
            if not remaining and not remaining_orders:
                _kill_switch_log(log_path, f"SUCCESS | Profile={profile} | Symbol={symbol} | FLAT + NO OPEN ORDERS")
                return True
            last_error = RuntimeError(
                f"Kill switch verification still sees {len(remaining)} position(s) and {len(remaining_orders)} open order(s)."
            )
        except Exception as e:
            last_error = e
            _kill_switch_log(log_path, f"ATTEMPT FAILED | Attempt={attempt}/{KILL_SWITCH_MAX_ATTEMPTS} | {e}")
        if attempt < KILL_SWITCH_MAX_ATTEMPTS:
            time.sleep(KILL_SWITCH_RETRY_SECONDS)
    raise RuntimeError(str(last_error or "Kill switch failed."))


def _run_kill_switch_watchdog(profile_id, parent_pid):
    """Independent fail-closed watchdog for hard process crashes/forced exits."""
    profile, folder, config_path, runtime_path, heartbeat_path, log_path = _kill_switch_profile_paths(profile_id)
    _kill_switch_log(log_path, f"WATCHDOG STARTED | Profile={profile} | ParentPID={parent_pid}")
    while True:
        runtime = _kill_switch_read_json(runtime_path)
        heartbeat = _kill_switch_read_json(heartbeat_path)
        status = str(runtime.get("status") or "").upper()
        runtime_pid = int(runtime.get("worker_pid") or 0)
        hb_pid = int(heartbeat.get("parent_pid") or 0)
        hb_ts = str(heartbeat.get("heartbeat_utc") or "")
        try:
            hb_time = datetime.fromisoformat(hb_ts.replace("Z", "+00:00")).timestamp() if hb_ts else 0.0
        except Exception:
            hb_time = 0.0
        age = time.time() - hb_time if hb_time else 10**9

        # A newer bot process has taken ownership of this profile; the old
        # watchdog must never flatten the new session.
        if runtime_pid and runtime_pid != int(parent_pid):
            _kill_switch_log(log_path, f"WATCHDOG EXIT | Ownership moved to PID={runtime_pid}")
            return
        if hb_pid and hb_pid != int(parent_pid):
            _kill_switch_log(log_path, f"WATCHDOG EXIT | Heartbeat ownership moved to PID={hb_pid}")
            return
        if status in ("STOPPED", "CONFIGURED"):
            _kill_switch_log(log_path, f"WATCHDOG EXIT | Clean status={status}")
            return
        if status == "STOPPING":
            # Give the worker a short grace period to perform its own kill switch.
            time.sleep(3)
            runtime2 = _kill_switch_read_json(runtime_path)
            if str(runtime2.get("status") or "").upper() == "STOPPED":
                _kill_switch_log(log_path, "WATCHDOG EXIT | Worker completed clean stop")
                return

        parent_alive = False
        try:
            if os.name == "nt":
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(parent_pid))
                if handle:
                    parent_alive = True
                    ctypes.windll.kernel32.CloseHandle(handle)
            else:
                os.kill(int(parent_pid), 0)
                parent_alive = True
        except Exception:
            parent_alive = False

        if (not parent_alive) or age > KILL_SWITCH_STALE_SECONDS:
            reason = "parent process exited" if not parent_alive else f"heartbeat stale for {age:.1f}s"
            _kill_switch_log(log_path, f"WATCHDOG TRIGGERED | {reason}")
            try:
                _kill_switch_flatten_profile(profile, f"WATCHDOG: {reason}")
            except Exception as e:
                _kill_switch_log(log_path, f"WATCHDOG FLATTEN FAILED | {e}")
                time.sleep(KILL_SWITCH_RETRY_SECONDS)
                continue
            try:
                state = _kill_switch_read_json(runtime_path)
                state["status"] = "STOPPED"
                state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
                state["last_error"] = f"KILL SWITCH: {reason}"
                with open(runtime_path, "w", encoding="utf-8") as fh:
                    json.dump(state, fh, indent=4, ensure_ascii=True)
            except Exception as e:
                _kill_switch_log(log_path, f"Runtime state update warning | {e}")
            _kill_switch_log(log_path, "WATCHDOG COMPLETE | Profile flattened and disarmed")
            return
        time.sleep(2)


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
    length = int(length)
    if length <= 0:
        raise ValueError("ADX period must be greater than 0.")

    # Keep ADX self-contained.  The live loop normally calls Supertrend first,
    # which leaves tr0/tr1/tr2 on the frame, but callers/tests/backtester helpers
    # must not depend on that incidental ordering.
    prev_close = df["close"].shift(1)
    df["tr0"] = (df["high"] - df["low"]).abs()
    df["tr1"] = (df["high"] - prev_close).abs()
    df["tr2"] = (df["low"] - prev_close).abs()

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