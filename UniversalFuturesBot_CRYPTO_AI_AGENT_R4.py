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


APP_VERSION = "V8.4.2-CRYPTO-AI-AGENT-R4"
APP_TITLE = "Universal Futures Trading Bot V8.4.2-AI-AGENT-R4 - Crypto Production Engine"
AUDIT_BUILD = "V8.4.2-AI-AGENT-AUDIT-2026-09-27-R4-FULL-ENGINE-AUDIT"
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
CONFIG_SCHEMA_VERSION = 15  # R4 adds explicit AI-Agent council settings and GUI persistence.
RUNTIME_SCHEMA_VERSION = 15  # R4 runtime schema parity with AI-Agent settings.
OPEN_ORDER_PAGE_LIMIT = 50
SUPPORTED_GRID_MODES = ("OFF", "DIRECT_SHOT", "LONG_GRID", "SHORT_GRID", "NEUTRAL_GRID")
SUPPORTED_SIGNAL_MODES = ("SINGLE_SIGNAL", "ANY_NON_CONFLICTING", "SCORE", "2_SIGNALS", "3_SIGNALS", "4_SIGNALS", "ADAPTIVE_SCORE", "ADAPTIVE_EVIDENCE", "AI_AGENT", "STRICT_ALL_FILTERS")
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

# ---------------------------------------------------------------------------
# AI AGENT R2 — deterministic market-intelligence council.
# Inspired by the attached research-desk guide: specialists -> leads ->
# adversarial review -> chief decision. This is NOT an LLM; it uses only
# verified completed-candle/module evidence and explicit rules.
AI_AGENT_MIN_FAMILIES = 3
AI_AGENT_MIN_EDGE = 0.20
AI_AGENT_MIN_FAMILY_CONFIDENCE = 0.55
AI_AGENT_REQUIRE_TREND = True
AI_AGENT_REQUIRE_STRUCTURE = True
AI_AGENT_MAX_CONFLICTING_FAMILIES = 1
AI_AGENT_RISK_PER_TRADE = "0.35"
AI_AGENT_ATR_SL_MULT = 1.8
AI_AGENT_FALLBACK_SL_ROI = 30.0
AI_AGENT_TP1_ROI = 60.0
AI_AGENT_TP2_ROI = 120.0
AI_AGENT_HOLD_ENABLED = True
AI_AGENT_HOLD_RULE = "MIN_FAMILIES"
AI_AGENT_HOLD_MIN_FAMILIES = 2

# R9.5/R9.6 reversal-hold contract. Directional modules are grouped so
# correlated indicators do not masquerade as independent reversal votes.
REVERSAL_EXIT_MODES = ("ALL_ACTIVE", "MIN_FAMILIES")
DEFAULT_REVERSAL_EXIT_MODE = AI_AGENT_HOLD_RULE
DEFAULT_MIN_REVERSE_FAMILIES = AI_AGENT_HOLD_MIN_FAMILIES
REVERSAL_FAMILY_MAP = {
    "ST": "TREND", "EMA": "TREND", "EMA_CROSS": "TREND",
    "MACD": "TREND", "VIDYA": "TREND", "NWE": "TREND",
    "RSI": "MOMENTUM", "STOCH": "MOMENTUM", "DIVERGENCE": "MOMENTUM",
    "VWAP": "FLOW", "VWAP_DELTA": "FLOW", "VOL": "FLOW", "VOL_SR": "FLOW",
    "LIQ_SWING": "STRUCTURE", "TRENDLINE": "STRUCTURE", "MTF": "STRUCTURE",
    "BB": "LEGACY_BB",
}

# V8.3.2 requested default trading profile.
# These are GUI defaults for a NEW/unsaved profile; an existing saved profile
# remains authoritative and is not silently overwritten.
DEFAULT_SIGNAL_MODE = "AI_AGENT"
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
DEFAULT_RISK_PER_TRADE = AI_AGENT_RISK_PER_TRADE
DEFAULT_POST_SL_OPPOSITE_LOCK = True
DEFAULT_NO_SAME_CANDLE = True
DEFAULT_COOLDOWN_MIN = "15"
DEFAULT_USE_DIVERGENCE = True
DEFAULT_DIV_USE_ALL = True

# R9.6 unified normal protection defaults. Simple mode uses ROI for the user-facing
# SL/TP contract; legacy R9.3 modes remain available behind an explicit switch.
DEFAULT_SIMPLE_SL_ROI = 30.0
DEFAULT_SIMPLE_FALLBACK_SL_ROI = 30.0
DEFAULT_SIMPLE_TP1_ROI = 60.0
DEFAULT_SIMPLE_TP2_ROI = 120.0
DEFAULT_SIMPLE_ROI_SL_ENABLED = True
DEFAULT_SIMPLE_FALLBACK_SL_ENABLED = True
DEFAULT_SIMPLE_ATR_SL_ENABLED = True
DEFAULT_SIMPLE_TP_ENABLED = True
DEFAULT_SIMPLE_TP1_ENABLED = True
DEFAULT_SIMPLE_TP2_ENABLED = True
DEFAULT_SIMPLE_ATR_TP_ENABLED = False
DEFAULT_LEGACY_PROTECTION_ENABLED = False
DEFAULT_SIMPLE_TP1_BE_ENABLED = True
DEFAULT_SIMPLE_HOLD_ENABLED = AI_AGENT_HOLD_ENABLED
DEFAULT_SIMPLE_HOLD_WAIT = False
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
    cmfv = cmfm * x["vol"]    x["div_cmf"] = (
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
    bv=z[bcols].fillna(False).sum(axis=1) if bcols else pd.Series(0,index=z.index)
    sv=z[scols].fillna(False).sum(axis=1) if scols else pd.Series(0,index=z.index)
    fb=z[fbcols].fillna(False).sum(axis=1) if fbcols else pd.Series(0,index=z.index)
    fs=z[fscols].fillna(False).sum(axis=1) if fscols else pd.Series(0,index=z.index)
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
    """V8.4 Evidence-Family strategy decision engine.

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

    @classmethod
    def ai_agent_decision(
        cls, directional_modules, atr_pass=True, vol_pass=True, adx_pass=True,
        mtf_pass_bull=True, mtf_pass_bear=True,
        min_families=AI_AGENT_MIN_FAMILIES, min_edge=AI_AGENT_MIN_EDGE,
        min_family_confidence=AI_AGENT_MIN_FAMILY_CONFIDENCE,
        require_trend=AI_AGENT_REQUIRE_TREND, require_structure=AI_AGENT_REQUIRE_STRUCTURE,
        max_conflicting_families=AI_AGENT_MAX_CONFLICTING_FAMILIES,
    ):
        """Deterministic market-intelligence council used by AI_AGENT mode."""
        modules = list(directional_modules or [])
        families = {}
        for family in cls.EVIDENCE_FAMILY_ORDER:
            members = [m for m in modules if cls._family_name(m[0]) == family]
            total = sum(float(ADAPTIVE_MODULE_WEIGHTS.get(m[0], 1.0)) for m in members)
            bull = sum(float(ADAPTIVE_MODULE_WEIGHTS.get(m[0], 1.0)) for m in members if bool(m[1]) and not bool(m[2]))
            bear = sum(float(ADAPTIVE_MODULE_WEIGHTS.get(m[0], 1.0)) for m in members if bool(m[2]) and not bool(m[1]))
            dominant = "BUY" if bull > bear and bull > 0 else "SELL" if bear > bull and bear > 0 else "NONE"
            confidence = max(bull, bear) / total if total else 0.0
            conflict = bool(bull and bear and confidence < 0.70)
            families[family] = {"bull":bull,"bear":bear,"total":total,"dominant":dominant,"confidence":confidence,"conflict":conflict}
        bull_fams=[f for f,v in families.items() if v["dominant"]=="BUY" and v["confidence"]>=float(min_family_confidence)]
        bear_fams=[f for f,v in families.items() if v["dominant"]=="SELL" and v["confidence"]>=float(min_family_confidence)]
        conflicts=[f for f,v in families.items() if v["conflict"]]
        bull_total=sum(v["bull"] for v in families.values())
        bear_total=sum(v["bear"] for v in families.values())
        total=bull_total+bear_total
        edge=abs(bull_total-bear_total)/total if total else 0.0
        common=bool(edge>=float(min_edge) and len(conflicts)<=int(max_conflicting_families))
        buy_ok=bool(common and len(bull_fams)>=int(min_families) and (not require_trend or "TREND" in bull_fams) and (not require_structure or "STRUCTURE" in bull_fams) and atr_pass and vol_pass and adx_pass and mtf_pass_bull)
        sell_ok=bool(common and len(bear_fams)>=int(min_families) and (not require_trend or "TREND" in bear_fams) and (not require_structure or "STRUCTURE" in bear_fams) and atr_pass and vol_pass and adx_pass and mtf_pass_bear)
        side="BUY" if buy_ok and not sell_ok else "SELL" if sell_ok and not buy_ok else "NONE"
        return {"buy_ok":buy_ok,"sell_ok":sell_ok,"side":side,"bull_families":bull_fams,"bear_families":bear_fams,"conflicting_families":conflicts,"edge":edge,"bull_total":bull_total,"bear_total":bear_total,"families":families,"regime_buy":bool(atr_pass and vol_pass and adx_pass and mtf_pass_bull),"regime_sell":bool(atr_pass and vol_pass and adx_pass and mtf_pass_bear)}

    @staticmethod
    def decide_signal(directional_modules, signal_mode, min_score,
                      atr_pass=True, vol_pass=True, adx_pass=True,
                      mtf_pass_bull=True, mtf_pass_bear=True,
                      adaptive_edge=None, adaptive_min_weight=None, evidence_min_families=None, evidence_family_min_score=None, evidence_require_trend=True, evidence_require_independent=True,
                      ai_min_families=None, ai_min_edge=None, ai_min_family_confidence=None,
                      ai_require_trend=None, ai_require_structure=None, ai_max_conflicting_families=None):
        signal_mode = str(signal_mode).strip().upper()
        min_score = int(min_score)
        if min_score < 1:
            raise ValueError("Minimum signal score must be at least 1.")
        modules = list(directional_modules or [])
        buy_score = sum(1 for _, bull, _ in modules if bool(bull))
        sell_score = sum(1 for _, _, bear in modules if bool(bear))
        count = len(modules)

        if signal_mode == "SINGLE_SIGNAL":
            # V8.2 contract: an ambiguous candle with both bullish and bearish
            # directional evidence must never become a trade merely because the
            # first module in the list happened to be bullish/bearish.
            has_bull = any(bool(bull) and not bool(bear) for _, bull, bear in modules)
            has_bear = any(bool(bear) and not bool(bull) for _, bull, bear in modules)
            if has_bull and not has_bear:
                return True, False, buy_score, sell_score
            if has_bear and not has_bull:
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

        if signal_mode == "AI_AGENT":
            result = StrategyEngine.ai_agent_decision(
                modules,
                atr_pass=atr_pass,
                vol_pass=vol_pass,
                adx_pass=adx_pass,
                mtf_pass_bull=mtf_pass_bull,
                mtf_pass_bear=mtf_pass_bear,
                min_families=AI_AGENT_MIN_FAMILIES if ai_min_families is None else int(ai_min_families),
                min_edge=AI_AGENT_MIN_EDGE if ai_min_edge is None else float(ai_min_edge),
                min_family_confidence=AI_AGENT_MIN_FAMILY_CONFIDENCE if ai_min_family_confidence is None else float(ai_min_family_confidence),
                require_trend=AI_AGENT_REQUIRE_TREND if ai_require_trend is None else bool(ai_require_trend),
                require_structure=AI_AGENT_REQUIRE_STRUCTURE if ai_require_structure is None else bool(ai_require_structure),
                max_conflicting_families=AI_AGENT_MAX_CONFLICTING_FAMILIES if ai_max_conflicting_families is None else int(ai_max_conflicting_families),
            )
            return result["buy_ok"], result["sell_ok"], result["bull_total"], result["bear_total"]

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
                        adaptive_edge=None, adaptive_min_weight=None, evidence_min_families=None, evidence_family_min_score=None, evidence_require_trend=True, evidence_require_independent=True,
                        ai_min_families=None, ai_min_edge=None, ai_min_family_confidence=None,
                        ai_require_trend=None, ai_require_structure=None, ai_max_conflicting_families=None):
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
            has_bull = any(bool(bull) and not bool(bear) for _, bull, bear in modules)
            has_bear = any(bool(bear) and not bool(bull) for _, bull, bear in modules)
            if has_bull and not has_bear:
                return "SINGLE_SIGNAL_MATCH_BUY"
            if has_bear and not has_bull:
                return "SINGLE_SIGNAL_MATCH_SELL"
            if has_bull and has_bear:
                return f"SINGLE_SIGNAL_CONFLICT_B{buy}_S{sell}"
            return "NO_UNAMBIGUOUS_SIGNAL"
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
        if mode == "AI_AGENT":
            result = StrategyEngine.ai_agent_decision(
                modules,
                atr_pass=atr_pass,
                vol_pass=vol_pass,
                adx_pass=adx_pass,
                mtf_pass_bull=mtf_pass_bull,
                mtf_pass_bear=mtf_pass_bear,
                min_families=AI_AGENT_MIN_FAMILIES if ai_min_families is None else int(ai_min_families),
                min_edge=AI_AGENT_MIN_EDGE if ai_min_edge is None else float(ai_min_edge),
                min_family_confidence=AI_AGENT_MIN_FAMILY_CONFIDENCE if ai_min_family_confidence is None else float(ai_min_family_confidence),
                require_trend=AI_AGENT_REQUIRE_TREND if ai_require_trend is None else bool(ai_require_trend),
                require_structure=AI_AGENT_REQUIRE_STRUCTURE if ai_require_structure is None else bool(ai_require_structure),
                max_conflicting_families=AI_AGENT_MAX_CONFLICTING_FAMILIES if ai_max_conflicting_families is None else int(ai_max_conflicting_families),
            )
            bulls = "+".join(result["bull_families"]) if result["bull_families"] else "NONE"
            bears = "+".join(result["bear_families"]) if result["bear_families"] else "NONE"
            conflicts = "+".join(result["conflicting_families"]) if result["conflicting_families"] else "NONE"
            if result["side"] in ("BUY","SELL"):
                return (f"AI_AGENT_CHIEF_{result['side']} | BullFamilies={bulls} | BearFamilies={bears} | "
                        f"Edge={result['edge']:.2f} | Conflicts={conflicts} | "
                        f"Regime={'PASS' if (result['regime_buy'] or result['regime_sell']) else 'FAIL'}")
            blocks=[]
            fams=result["bull_families"] if result["bull_total"]>=result["bear_total"] else result["bear_families"]
            if len(fams)<AI_AGENT_MIN_FAMILIES: blocks.append(f"FAMILIES_{len(fams)}/{AI_AGENT_MIN_FAMILIES}")
            if result["edge"]<AI_AGENT_MIN_EDGE: blocks.append(f"EDGE_{result['edge']:.2f}<{AI_AGENT_MIN_EDGE:.2f}")
            if len(result["conflicting_families"])>AI_AGENT_MAX_CONFLICTING_FAMILIES: blocks.append("CONFLICT_REVIEW")
            if AI_AGENT_REQUIRE_TREND and "TREND" not in fams: blocks.append("TREND_REQUIRED")
            if AI_AGENT_REQUIRE_STRUCTURE and "STRUCTURE" not in fams: blocks.append("STRUCTURE_REQUIRED")
            if not atr_pass: blocks.append("ATR_GATE")
            if not vol_pass: blocks.append("VOLUME_GATE")
            if not adx_pass: blocks.append("ADX_GATE")
            return "AI_AGENT_BLOCKED | "+",".join(blocks or ["CONFLICT_OR_NEUTRAL"])

        if mode == "ADAPTIVE_EVIDENCE":
            families, bull_families, bear_families, required = StrategyEngine.evidence_summary(
                modules, evidence_min_families, evidence_family_min_score
            )
            bt = sum(v["bull_ratio"] for v in families.values())
            st = sum(v["bear_ratio"] for v in families.values())
            total = bt + st
            edge = abs(bt - st) / total if total else 0.0
            threshold = float(ADAPTIVE_DEFAULT_EDGE if adaptive_edge is None else adaptive_edge)
            trend_required = bool(evidence_require_trend)
            independent_required = bool(evidence_require_independent)

            bull_ok = (
                len(bull_families) >= required
                and bt > st
                and edge >= threshold
                and bool(atr_pass)
                and bool(adx_pass)
            )
            bear_ok = (
                len(bear_families) >= required
                and st > bt
                and edge >= threshold
                and bool(atr_pass)
                and bool(adx_pass)
            )

            if trend_required:
                bull_ok = bull_ok and "TREND" in bull_families
                bear_ok = bear_ok and "TREND" in bear_families
            if independent_required:
                bull_ok = bull_ok and any(
                    f in bull_families for f in ("MOMENTUM", "FLOW", "STRUCTURE")
                )
                bear_ok = bear_ok and any(
                    f in bear_families for f in ("MOMENTUM", "FLOW", "STRUCTURE")
                )

            if bull_ok:
                return "EVIDENCE_BUY_" + "+".join(bull_families) + f"_EDGE{edge:.2f}"
            if bear_ok:
                return "EVIDENCE_SELL_" + "+".join(bear_families) + f"_EDGE{edge:.2f}"
            dominant = "BUY" if bt > st else "SELL" if st > bt else "NONE"
            active = bull_families if dominant == "BUY" else bear_families if dominant == "SELL" else []
            blockers = []
            if len(active) < required: blockers.append(f"FAMILIES_{len(active)}/{required}")
            if edge < threshold: blockers.append(f"EDGE_{edge:.2f}<{threshold:.2f}")
            if trend_required and dominant != "NONE" and "TREND" not in active: blockers.append("TREND_REQUIRED")
            if independent_required and dominant != "NONE" and not any(f in active for f in ("MOMENTUM","FLOW","STRUCTURE")): blockers.append("INDEPENDENT_REQUIRED")
            if not atr_pass: blockers.append("ATR_GATE")
            if not adx_pass: blockers.append("ADX_GATE")
            return (f"EVIDENCE_BLOCKED_BF{len(bull_families)}_SF{len(bear_families)}_EDGE{edge:.2f}"
                    f"|SIDE={dominant}|BLOCK={','.join(blockers) if blockers else 'CONFLICT_OR_NEUTRAL'}"
                    f"|ATR={'PASS' if atr_pass else 'FAIL'}|ADX={'PASS' if adx_pass else 'FAIL'}")
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
        if p2[0] == p1[0]:            return np.nan
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
        self.worker_pid = None
        self.worker_started_at = 0.0
        self.stop_requested = False
        self.stop_started_at = 0.0
        self._stop_completion_scheduled = False
        # Tkinter variables are not thread-safe. R8 snapshots GUI configuration
        # on the GUI thread; the trading worker reads this immutable/current
        # snapshot instead of calling Tk widgets from the worker thread.
        self._runtime_gui_lock = threading.RLock()
        self._runtime_gui_values = {}

        # R3 FIX: load_settings() runs immediately after _build_ui(), and the
        # configuration loader uses v_size_mode for backward-compatible sizing
        # migration.  Keep this variable present for the entire GUI lifetime;
        # it is synchronized with Risk-Based Sizing and never drives a separate
        # calculation by itself.
        self.v_size_mode = tk.StringVar(value=DEFAULT_RISK_MODE)

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
        self.runtime_sizing_mode = ""
        self.runtime_protection_basis = ""
        self.runtime_config_hash = ""
        self.runtime_resumed = False
        self.profile_lock_fd = None
        self.worker_pid = None
        self.worker_started_at = 0.0
        self._profile_status_refresh_job = None
        self.kill_switch_watchdog = None
        self.kill_switch_watchdog_started = False
        self.last_kill_switch_heartbeat = 0.0
        self._kill_switch_lock = threading.RLock()
        self.kill_switch_completed = False
        self.kill_switch_in_progress = False
        self.stop_cleanup_thread = None

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
        # Order IDs from completed/externally-closed bot positions are retained in
        # the recovery checkpoint until the next flat-session startup proves they
        # are stale. This prevents orphan SL/TP orders from becoming "unknown" after
        # last_protected_position is cleared.
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
        self._refresh_runtime_gui_snapshot()
        self._refresh_profile_list(select_profile=self.bot_profile_id)
        self._schedule_profile_status_heartbeat()

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

    def _get_profile_control_path(self, profile_id=None):
        profile, folder, _, _ = self._profile_paths(profile_id)
        return str(folder / "control.json")

    def _write_profile_control(self, profile_id, action, reason=""):
        profile = self._sanitize_profile_id(profile_id)
        payload = {
            "schema_version": PROFILE_CONTROL_SCHEMA_VERSION,
            "profile": profile,
            "action": str(action).upper(),
            "request_id": str(uuid.uuid4()),
            "requested_at_utc": datetime.now(timezone.utc).isoformat(),
            "requested_by_pid": os.getpid(),
            "reason": str(reason or "").strip(),
        }
        self._write_json_atomic(self._get_profile_control_path(profile), payload)
        return payload

    def _read_profile_control(self, profile_id=None):
        payload = self._read_json_file(self._get_profile_control_path(profile_id))
        return payload if isinstance(payload, dict) else None

    def _clear_profile_control(self, profile_id=None, expected_request_id=None):
        path = Path(self._get_profile_control_path(profile_id))
        if not path.exists():
            return
        if expected_request_id:
            payload = self._read_json_file(str(path)) or {}
            if str(payload.get("request_id") or "") != str(expected_request_id):
                return
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _schedule_profile_status_heartbeat(self):
        try:
            self._profile_status_refresh_job = self.root.after(
                PROFILE_STATUS_HEARTBEAT_MS, self._profile_status_heartbeat
            )
        except Exception:
            self._profile_status_refresh_job = None

    def _profile_status_heartbeat(self):
        try:
            if getattr(self, "profile_tree", None) is not None:
                selected = self._selected_profile_id()
                self._refresh_profile_list(select_profile=selected)
        except Exception:
            pass
        finally:
            self._schedule_profile_status_heartbeat()

    def _kill_switch_heartbeat_path(self, profile_id=None):
        profile = self._sanitize_profile_id(profile_id)
        return str(PROFILE_DIR / profile / "kill_switch_heartbeat.json")

    def _write_kill_switch_heartbeat(self, status="RUNNING"):
        if not KILL_SWITCH_REQUIRED:
            return
        now = time.time()
        if status == "RUNNING" and now - self.last_kill_switch_heartbeat < KILL_SWITCH_HEARTBEAT_SECONDS:
            return
        payload = {
            "schema_version": 1,
            "profile": self._sanitize_profile_id(),
            "parent_pid": os.getpid(),
            "heartbeat_utc": datetime.now(timezone.utc).isoformat(),
            "status": str(status).upper(),
            "symbol": self.symbol,
            "exchange": self.exchange_id,
            "session_id": self.session_id,
        }
        try:
            self._write_json_atomic(self._kill_switch_heartbeat_path(), payload)
            self.last_kill_switch_heartbeat = now
        except Exception as e:
            self.log(f"KILL SWITCH HEARTBEAT WARNING: {e}")

    def _start_kill_switch_watchdog(self):
        if not KILL_SWITCH_REQUIRED or self.kill_switch_watchdog_started:
            return
        profile = self._sanitize_profile_id()
        try:
            args = [sys.executable]
            if getattr(sys, "frozen", False):
                args += ["--kill-switch-watchdog", profile, str(os.getpid())]
            else:
                args += [str(Path(__file__).resolve()), "--kill-switch-watchdog", profile, str(os.getpid())]
            kwargs = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "close_fds": True,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            self.kill_switch_watchdog = subprocess.Popen(args, **kwargs)
            self.kill_switch_watchdog_started = True
            self.log(
                f"KILL SWITCH WATCHDOG: ARMED | PID={self.kill_switch_watchdog.pid} | "
                f"Heartbeat={KILL_SWITCH_HEARTBEAT_SECONDS:g}s | Stale trigger={KILL_SWITCH_STALE_SECONDS:g}s"
            )
        except Exception as e:
            self.kill_switch_watchdog = None
            self.kill_switch_watchdog_started = False
            # This is a mandatory safety mechanism. Do not allow live trading
            # if the independent crash watchdog could not be armed.
            raise RuntimeError(f"KILL SWITCH WATCHDOG could not be armed: {e}") from e

    def _disarm_kill_switch_watchdog(self):
        # The watchdog normally exits itself after seeing STOPPED. Do not kill
        # a watchdog blindly while a position could still exist.
        self._write_kill_switch_heartbeat(status="STOPPING")

    def _activate_kill_switch(self, reason="BOT STOP"):
        """Flatten the configured bot symbol exactly once per session and verify flat."""
        if not KILL_SWITCH_REQUIRED:
            return True
        with self._kill_switch_lock:
            if self.kill_switch_completed:
                self.log("KILL SWITCH: already completed for this session; no duplicate flatten required.")
                return True
            if self.kill_switch_in_progress:
                # RLock prevents concurrent execution in this process; this branch is
                # retained as a defensive guard for future callers.
                return False
            self.kill_switch_in_progress = True
            self.log(f"KILL SWITCH: ARMED ACTION | Reason={reason}")
            try:
                ok = _kill_switch_flatten_profile(self._sanitize_profile_id(), reason)
                if not ok:
                    raise RuntimeError("Kill switch returned without a verified FLAT + NO OPEN ORDERS state.")
                self.kill_switch_completed = True
                self.log(
                    f"KILL SWITCH COMPLETE | Profile={self._sanitize_profile_id()} | "
                    f"Symbol={self.symbol or 'UNKNOWN'} | FLAT + NO OPEN ORDERS"
                )
                self._write_kill_switch_heartbeat(status="STOPPING")
                return True
            except Exception as e:
                self.log(f"KILL SWITCH CRITICAL FAILURE: {e}")
                self.runtime_last_error = f"KILL SWITCH FAILURE: {e}"
                self._write_kill_switch_heartbeat(status="STOPPING")
                return False
            finally:
                self.kill_switch_in_progress = False

    def _start_stop_cleanup_worker(self, reason="MANUAL BOT STOP"):
        """Run exchange flattening off the Tk thread so STOP never freezes the GUI."""
        existing = self.stop_cleanup_thread
        if existing is not None and existing.is_alive():
            return
        def _cleanup():
            ok = self._activate_kill_switch(reason)
            if ok:
                self.log("STOP CLEANUP: exchange position/orders flattened and verified.")
            else:
                self.log("STOP CLEANUP: kill switch did not verify a flat exchange state; retry/watchdog remains active.")
        self.stop_cleanup_thread = threading.Thread(target=_cleanup, name="KillSwitchStopCleanup", daemon=True)
        self.stop_cleanup_thread.start()

    def _log_exchange_resume_snapshot(self, current_position, current_orders):
        """Log the live exchange snapshot before a resumed session continues."""
        exchange_time = None
        try:
            if hasattr(self.exchange, "fetch_time"):
                exchange_time = self.exchange.fetch_time()
        except Exception:
            exchange_time = None
        try:
            balance = self.fetch_balance_total()
        except Exception:
            balance = None
        p = current_position or {}
        side = str(p.get("side") or "FLAT").upper()
        try:
            qty = abs(float(p.get("qty") or 0.0))
        except Exception:
            qty = 0.0
        try:
            entry = float(p.get("entry") or 0.0)
        except Exception:
            entry = 0.0
        raw = p.get("raw") if isinstance(p.get("raw"), dict) else {}
        mark = (
            p.get("mark") or p.get("markPrice")
            or raw.get("markPrice") or raw.get("mark_price")
        )
        try:
            mark = float(mark) if mark is not None else 0.0
        except Exception:
            mark = 0.0
        upl = p.get("unrealizedPnl")
        try:
            upl = float(upl) if upl is not None else float(
                raw.get("unrealisedPnl") or raw.get("unrealizedPnl") or 0.0
            )
        except Exception:
            upl = 0.0
        lev = p.get("leverage") or raw.get("leverage")
        strategy = self.runtime_strategy_mode or self.v_signal_mode.get().strip().upper()
        profile = self._sanitize_profile_id()
        exch_dt = "UNKNOWN"
        if exchange_time:
            try:
                exch_dt = datetime.fromtimestamp(float(exchange_time) / 1000.0, timezone.utc).isoformat()
            except Exception:
                exch_dt = str(exchange_time)
        saved_stats = (self.resume_candidate or {}).get("stats") or {}
        self.log(
            f"RECOVERY EXCHANGE SNAPSHOT | ExchangeTime={exch_dt} | Profile={profile} | "
            f"Exchange={self.exchange_id or 'UNKNOWN'} | Account={self.runtime_account_mode or self.v_account_mode.get()} | "
            f"Symbol={self.symbol} | Timeframe={self.runtime_timeframe or self.v_tf.get()} | Strategy={strategy} | "
            f"Position={side} Qty={qty:g} Entry={entry:g} Mark={mark:g} UPNL={upl:.8f} | "
            f"Leverage={lev or self.e_lev.get().strip()} | OpenOrders={len(current_orders)} | "
            f"Balance={balance if balance is not None else 'UNKNOWN'} | "
            f"SavedNetPnL={float(saved_stats.get('net_pnl') or 0.0):.8f} | "
            f"SavedTrades={int(saved_stats.get('total_trades') or 0)} | "
            f"SavedWins={int(saved_stats.get('winning_trades') or 0)} | "
            f"SavedLosses={int(saved_stats.get('losing_trades') or 0)}"
        )
        if current_position:
            self.log(
                f"RECOVERY LIVE POSITION | {side} {self.symbol} | Qty={qty:g} | Entry={entry:g} | "
                f"Mark={mark:g} | Unrealized PnL={upl:.8f} | Leverage={lev or 'exchange/default'}"
            )
        else:
            self.log(f"RECOVERY LIVE POSITION | FLAT | {self.symbol} | No exchange position is running.")

    def _request_selected_profile_stop(self):
        """Stop the selected profile, including a bot running in another GUI process."""
        profile = self._selected_profile_id()
        if not profile:
            return
        current = self._sanitize_profile_id(getattr(self, "bot_profile_id", ""))
        same_process_worker = (
            profile == current
            and getattr(self, "bot_thread", None) is not None
            and self.bot_thread.is_alive()
        )
        if same_process_worker:
            self.stop_bot()
            return

        if not self._profile_lock_is_active(profile):
            messagebox.showinfo("Profile not running", f"Profile {profile} is not currently running.")
            return
        if not messagebox.askyesno(
            "Stop selected bot?",
            f"Send a safe stop request to {profile}?\n\n"
            "The running process will finish its current exchange operation, "
            "preserve protection for an open normal-strategy position, and write "
            "a final runtime checkpoint before stopping.",
        ):
            return
        try:
            request = self._write_profile_control(profile, "STOP", "Remote stop requested from Profile Manager")
            self.log(
                f"REMOTE STOP REQUESTED | Profile={profile} | Request={request['request_id']}"
            )
            self._refresh_profile_list(select_profile=profile)
        except Exception as e:
            messagebox.showerror("Remote stop failed", str(e))

    def _consume_remote_stop_request(self):
        """Consume a STOP control request for this worker without touching Tk widgets."""
        profile = self._sanitize_profile_id(getattr(self, "bot_profile_id", "BOT-01"))
        request = self._read_profile_control(profile)
        if not isinstance(request, dict) or str(request.get("action") or "").upper() != "STOP":
            return False
        request_id = str(request.get("request_id") or "")
        self.stop_requested = True
        self.stop_started_at = time.time()
        self.log(
            f"REMOTE STOP ACKNOWLEDGED | Profile={profile} | Request={request_id or 'UNKNOWN'} | "
            f"Reason={request.get('reason') or 'remote stop'}"
        )
        self._clear_profile_control(profile, expected_request_id=request_id or None)
        try:
            if self.grid_state.get("active"):
                self._grid_stop(self.symbol, "Remote bot stop", cooldown_seconds=0)
        except Exception as grid_stop_error:
            # Do not pretend a Grid stop was clean. Keep the worker in its
            # normal finalization path so protection remains until exchange
            # state can be verified.
            self.log(f"REMOTE GRID STOP WARNING: {grid_stop_error}")
        return True

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
            "sizing_mode": self.runtime_sizing_mode,
            "protection_basis": self.runtime_protection_basis,
            "config_hash": self.runtime_config_hash,
            "resumed": bool(self.runtime_resumed),
            "stop_requested": bool(self.stop_requested),
            "stop_started_at": self.stop_started_at or None,
            "worker_pid": self.worker_pid,
            "worker_started_at": self.worker_started_at or None,
            "session_started_at": self.session_started_at,
            "session_max_trades": self.session_max_trades,
            "start_balance": self.start_balance,
            "daily_start_balance": self.daily_start_balance,
            "daily_peak_equity": self.daily_peak_equity,
            "session_peak_equity": self.session_peak_equity,
            "consecutive_cycle_errors": self.consecutive_cycle_errors,
            "last_market_data_ts": self.last_market_data_ts,
            "daily_start_date": (
                self.daily_start_date.isoformat()                if hasattr(self.daily_start_date, "isoformat")
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
            position_state = state.get("position_state") or {}
            position = position_state.get("last_protected_position")
            active_trade = position_state.get("active_trade")
            grid = state.get("grid_state") or {}
            has_grid_state = bool(
                grid.get("active")
                or grid.get("filled_levels")
                or grid.get("entry_orders")
                or grid.get("tp_order_id")
                or grid.get("sl_order_id")
            )
            if (
                status in ("RUNNING", "STOPPING", "CRASHED")
                and not position
                and not active_trade
                and not has_grid_state
                and not self._profile_lock_is_active(bot_id)
            ):
                # A stale lifecycle marker with no saved trading state and no
                # live process is safe to normalize to STOPPED.  The next
                # start still performs its normal exchange inventory/order
                # preflight; this only prevents a phantom recovery prompt.
                state["status"] = "STOPPED"
                state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
                state["last_error"] = ""
                try:
                    self._write_json_atomic(self._get_runtime_state_path(), state)
                except Exception:
                    pass
                self.log(
                    f"RECOVERY CHECK: stale {status} checkpoint had no saved "
                    "position/Grid state and no live process; normalized to STOPPED."
                )
                self._refresh_profile_list(select_profile=bot_id)
                return
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
        # A successful resume starts a new live worker lifecycle. A checkpoint
        # saying STOPPING must never re-arm the stop flag inside the new worker.
        self.stop_requested = False
        self.stop_started_at = 0.0
        self.session_id = state.get("session_id") or str(uuid.uuid4())
        self.runtime_account_mode = str(state.get("account_mode") or self.v_account_mode.get())
        self.runtime_timeframe = str(state.get("timeframe") or self.v_tf.get()).lower()
        self.runtime_strategy_mode = str(
            state.get("strategy_mode") or self.v_signal_mode.get()
        )
        self.runtime_strategy_modules = str(state.get("strategy_modules") or "")
        self.runtime_sizing_mode = str(state.get("sizing_mode") or self._runtime_gui_value("v_size_mode", DEFAULT_RISK_MODE))
        self.runtime_protection_basis = str(state.get("protection_basis") or "CONFIGURED_SL_OR_ATR")
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
                if saved_date else datetime.now().date()
            )
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
        saved_exchange = str(state.get("exchange") or "").lower()        saved_symbol = str(state.get("symbol") or "").upper()
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
        self._log_exchange_resume_snapshot(current_position, current_orders)
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
                self.retired_managed_order_ids = set()
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
            current_profile = self._sanitize_profile_id(getattr(self, "bot_profile_id", "BOT-01"))
            worker_alive = bool(
                getattr(self, "bot_thread", None)
                and self.bot_thread.is_alive()
            )
            if profile == current_profile and (
                bool(getattr(self, "is_running", False))
                or worker_alive
                or bool(getattr(self, "stop_requested", False))
            ):
                return True
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
            ("use_divergence", "Divergence"),
            ("use_vol_sr", "Volume S/R"),
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
        position_state = runtime.get("position_state") or {}
        saved_position = position_state.get("last_protected_position")
        active_trade = position_state.get("active_trade")
        grid_state = runtime.get("grid_state") or {}
        has_saved_position = bool(saved_position) or bool(active_trade)
        has_grid_state = bool(
            grid_state.get("active")
            or grid_state.get("filled_levels")
            or grid_state.get("entry_orders")
            or grid_state.get("tp_order_id")
            or grid_state.get("sl_order_id")
        )
        lock_active = self._profile_lock_is_active(profile)
        same_profile_worker_alive = bool(
            profile == self._sanitize_profile_id(getattr(self, "bot_profile_id", "BOT-01"))
            and getattr(self, "bot_thread", None)
            and self.bot_thread.is_alive()
        )
        control = self._read_profile_control(profile) or {}
        control_pending = str(control.get("action") or "").upper() == "STOP"
        if lock_active or same_profile_worker_alive:
            status = "STOPPING" if (control_pending or bool(getattr(self, "stop_requested", False))) else "RUNNING"
        elif status in {"RUNNING", "CRASHED", "STOPPING", "PAUSED_WITH_POSITION"}:
            # A runtime checkpoint is historical state, not proof that a worker
            # is alive.  Never display RUNNING after the process/lock is gone.
            # If saved inventory exists, make the required manual recovery action
            # explicit; otherwise the profile is simply stopped.
            status = "RECOVERY_REQUIRED" if (has_saved_position or has_grid_state) else "STOPPED"
            if control_pending:
                try:
                    control_ts = datetime.fromisoformat(str(control.get("requested_at_utc")).replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - control_ts).total_seconds() > REMOTE_STOP_STALE_SECONDS:
                        self._clear_profile_control(profile, expected_request_id=control.get("request_id"))
                except Exception:
                    pass
        grid_mode = str(cfg.get("grid_mode") or "OFF").upper()
        signal_mode = str(cfg.get("signal_mode") or "SINGLE_SIGNAL").upper()
        strategy_mode = grid_mode if grid_mode not in ("OFF", "DIRECT_SHOT") else signal_mode
        size_mode = str(cfg.get("size_mode") or "EQUITY_RISK_%")
        qty_display = (
            f"Risk {cfg.get('risk_pct', '1.0')}%"
            if size_mode == "EQUITY_RISK_%"
            else (
                f"Fixed {cfg.get('fixed_qty', '0.001')}"

            )
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
            f"Max Trades     : {cfg.get('max_trades', '')} completed",
            f"Max Open Pos   : {cfg.get('max_open_trades', DEFAULT_MAX_OPEN_TRADES)} (single-symbol hard cap)",
            f"Cooldown        : {cfg.get('cooldown_min', '')} min",
            f"No Same Candle : {cfg.get('no_same_candle', '')}",
            "",
            "STRATEGY",
            f"Signal Mode    : {cfg.get('signal_mode', '')}",
            f"Minimum Score  : {cfg.get('min_score', '')}",
            f"Evidence Families: min={cfg.get('evidence_min_families', 2)} | score={cfg.get('evidence_family_min_score', 0.35)} | trend={cfg.get('evidence_require_trend', True)} | independent={cfg.get('evidence_require_independent', True)}",
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
            f"ATR Dynamic SL : {cfg.get('use_atr_sl', DEFAULT_ATR_SL_ENABLED)} | SL={cfg.get('atr_sl_mult', DEFAULT_ATR_SL_MULTIPLIER)}x | TP1={cfg.get('atr_tp1_mult', DEFAULT_ATR_TP1_MULTIPLIER)}x | TP2={cfg.get('atr_tp2_mult', DEFAULT_ATR_TP2_MULTIPLIER)}x",
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

        # A stale RUNNING/CRASHED marker by itself is not proof of an active
        # bot.  The profile lock, saved position, active trade, or Grid state
        # are the actual safety blockers.  This allows a flat orphaned profile
        # to be deleted after a crash/restart without manually editing JSON.
        if has_saved_position or has_grid_state:
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
            "Trade/session history in the master database will NOT be deleted.\n\n"            "This action cannot be undone.",
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
                        status,                        end_balance,
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
        if not self._runtime_gui_value("v_tele_enable", False):
            return

        token = str(self._runtime_gui_value("e_tele_token", "") or "").strip()
        chat_id = str(self._runtime_gui_value("e_tele_chat", "") or "").strip()

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
            text="STOP Selected Bot",
            command=self._request_selected_profile_stop,
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

        tk.Label(f_market, text="Max Completed Trades:").grid(row=1, column=0, sticky="w")
        self.e_max_trades = tk.Entry(f_market, width=8)
        self.e_max_trades.insert(0, "10")
        self.e_max_trades.grid(row=1, column=1, padx=5, sticky="w")

        tk.Label(f_market, text="Max Open Trades (per bot/symbol, current engine = 1):").grid(row=1, column=2, sticky="e")
        self.e_max_open_trades = tk.Entry(f_market, width=7)
        self.e_max_open_trades.insert(0, str(DEFAULT_MAX_OPEN_TRADES))
        self.e_max_open_trades.grid(row=1, column=3, padx=5, sticky="w")

        tk.Label(f_market, text="Current engine limit: 1 net position").grid(row=1, column=4, sticky="w")
        tk.Label(f_market, text="Estimated Window:").grid(row=2, column=0, sticky="w")
        self.lbl_est_time = tk.Label(f_market, text="10 min", font=("Arial", 9, "bold"))
        self.lbl_est_time.grid(row=2, column=1, columnspan=2, padx=5, sticky="w")
        self.v_no_same_candle = tk.BooleanVar(value=DEFAULT_NO_SAME_CANDLE)
        tk.Checkbutton(f_market, text="Safety: No Re-Entry Same Candle", variable=self.v_no_same_candle).grid(row=3, column=0, columnspan=3, sticky="w")
        tk.Label(f_market, text="Prevents instant re-entry after SL/TP/reversal.", fg="#444444").grid(row=3, column=3, columnspan=3, sticky="w")
        tk.Label(f_market, text="Cooldown (min):").grid(row=4, column=0, sticky="w")
        self.e_cooldown_min = tk.Entry(f_market, width=6)
        self.e_cooldown_min.insert(0, DEFAULT_COOLDOWN_MIN)
        self.e_cooldown_min.grid(row=4, column=1, padx=5, sticky="w")
        tk.Label(f_market, text="0 = OFF", fg="#444444").grid(row=4, column=2, sticky="w")
        self.v_require_opposite_after_exit = tk.BooleanVar(value=DEFAULT_POST_SL_OPPOSITE_LOCK)
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

        # 3. Strategy — V8.4 Evidence-Family GUI
        # The crypto GUI now mirrors the V8.4 Evidence-Family organization:
        # TREND / MOMENTUM / FLOW / STRUCTURE / REGIME / OPTIONAL-LEGACY /
        # DECISION ENGINE.  The underlying variable names are kept compatible
        # with the existing crypto save/load, runtime and strategy code.
        f_strat = tk.LabelFrame(
            self.tab_strategy,
            text=" 3. Strategy Engine — V8.4 Evidence Families ",
        )
        f_strat.pack(fill="x", padx=10, pady=5)

        def _family(title):
            fr = tk.LabelFrame(f_strat, text=f" {title} ", padx=6, pady=4)
            fr.pack(fill="x", padx=6, pady=4)
            return fr

        def _entry(parent, label, var_name, default, row, col, width=6):
            tk.Label(parent, text=label).grid(
                row=row, column=col, sticky="e", padx=2, pady=2
            )
            ent = tk.Entry(parent, width=width)
            ent.insert(0, str(default))
            ent.grid(row=row, column=col + 1, sticky="w", padx=2, pady=2)
            setattr(self, var_name, ent)
            return ent

        def _check(parent, text, var_name, default, row, col=0, colspan=1):
            var = tk.BooleanVar(value=default)
            setattr(self, var_name, var)
            tk.Checkbutton(
                parent,
                text=text,
                variable=var,
            ).grid(
                row=row,
                column=col,
                columnspan=colspan,
                sticky="w",
                padx=2,
                pady=2,
            )
            return var

        def _option(parent, label, var_name, default, values, row, col, colspan=1):
            tk.Label(parent, text=label).grid(
                row=row, column=col, sticky="e", padx=2, pady=2
            )
            var = tk.StringVar(value=default)
            setattr(self, var_name, var)
            ttk.OptionMenu(
                parent,
                var,
                default,
                *values,
            ).grid(
                row=row,
                column=col + 1,
                columnspan=colspan,
                sticky="w",
                padx=2,
                pady=2,
            )
            return var

        # ---------------- TREND ----------------
        fr = _family("TREND — direction / trend continuation")

        _check(fr, "Supertrend", "v_use_st", True, 0, 0)
        _entry(fr, "ATR Period", "e_st_len", "10", 0, 2)
        _entry(fr, "ATR Mult", "e_st_mult", "2.0", 0, 4)
        _option(fr, "Source", "v_st_source", "CLOSE", ("CLOSE", "HL2"), 0, 6)

        _option(
            fr, "Entry", "v_st_entry_mode", "FRESH_FLIP",
            ("FRESH_FLIP", "CURRENT_TREND"), 1, 0, 2
        )
        _check(
            fr,
            "Change ATR Method (ON=RMA / OFF=SMA)",
            "v_st_change_atr",
            True,
            1,
            4,
            4,
        )

        _check(fr, "EMA", "v_use_ema", True, 2, 0)
        _entry(fr, "Period", "e_ema_len", "200", 2, 2)

        _check(fr, "EMA Cross", "v_use_ema_cross", False, 3, 0)
        _entry(fr, "Fast", "e_ema_fast", "9", 3, 2)
        _entry(fr, "Slow", "e_ema_slow", "20", 3, 4)
        _option(
            fr, "Entry", "v_ema_cross_entry_mode", "FRESH_CROSS",
            ("FRESH_CROSS", "CURRENT_TREND"), 3, 6
        )

        _check(fr, "MACD", "v_use_macd", False, 4, 0)
        _entry(fr, "Fast", "e_macd_fast", "12", 4, 2, 5)
        _entry(fr, "Slow", "e_macd_slow", "26", 4, 4, 5)
        _entry(fr, "Signal", "e_macd_signal", "9", 4, 6, 5)

        _check(fr, "VIDYA", "v_use_vidya", False, 5, 0)
        _entry(fr, "Length", "e_vidya_len", "10", 5, 2)
        _entry(fr, "Momentum", "e_vidya_momentum", "20", 5, 4)
        _entry(fr, "Band", "e_vidya_band", "2", 5, 6)
        _option(
            fr, "Entry", "v_vidya_entry_mode", "CURRENT_TREND",
            ("CURRENT_TREND", "FRESH_FLIP"), 6, 0, 2
        )

        _check(fr, "NWE", "v_use_nwe", False, 7, 0)
        _entry(fr, "Bandwidth", "e_nwe_bandwidth", "8", 7, 2)
        _entry(fr, "Mult", "e_nwe_mult", "3", 7, 4)
        _option(
            fr, "Entry", "v_nwe_entry_mode", "FRESH_CROSS",
            ("FRESH_CROSS", "CURRENT_TREND"), 7, 6
        )

        _check(fr, "NWE Repainting", "v_nwe_repaint", False, 8, 0, 2)
        tk.Label(
            fr,
            text=(
                "Trading calculation remains causal/completed-candle; "
                "repaint option is retained for compatibility."
            ),
            fg="#555555",
        ).grid(row=8, column=2, columnspan=7, sticky="w")

        # ---------------- MOMENTUM ----------------
        fr = _family("MOMENTUM — reversal / acceleration")

        _check(fr, "RSI", "v_use_rsi", False, 0, 0)
        _entry(fr, "Period", "e_rsi_len", "14", 0, 2)
        _entry(fr, "OB", "e_rsi_ob", "80", 0, 4)
        _entry(fr, "OS", "e_rsi_os", "20", 0, 6)

        _option(
            fr, "Logic", "v_rsi_logic", "REVERSAL_ZONE",
            ("REVERSAL_ZONE", "CROSS_MA", "EITHER"), 1, 0, 2
        )
        _option(
            fr, "MA Type", "v_rsi_ma_type", "EMA",
            ("SMA", "EMA", "WMA"), 1, 4
        )
        _entry(fr, "MA Period", "e_rsi_ma_len", "9", 1, 6)

        _check(fr, "Stochastic", "v_use_stoch", False, 2, 0)
        _entry(fr, "K", "e_stoch_k", "14", 2, 2, 5)
        _entry(fr, "Smooth", "e_stoch_smooth", "3", 2, 4, 5)
        _entry(fr, "D", "e_stoch_d", "3", 2, 6, 5)

        _check(fr, "Confirmed Divergence", "v_use_divergence", DEFAULT_USE_DIVERGENCE, 3, 0, 2)
        _entry(fr, "Pivot", "e_div_pivot", "5", 3, 2, 5)
        _entry(fr, "Min Div", "e_div_min_count", "1", 3, 4, 5)
        _entry(fr, "Max Pivots", "e_div_max_pivots", "10", 3, 6, 5)
        _entry(fr, "Max Bars", "e_div_max_bars", "100", 5, 4, 5)

        _option(
            fr, "Type", "v_div_type", "Regular",
            ("Regular", "Hidden", "Regular/Hidden"), 4, 0, 2
        )
        _option(
            fr, "Source", "v_div_source", "Close",
            ("Close", "High/Low"), 4, 4
        )
        _entry(fr, "CCI Len", "e_div_cci_len", "10", 5, 0, 5)
        _entry(fr, "Momentum Len", "e_div_mom_len", "10", 5, 2, 5)

        # The crypto implementation exposes these source toggles as individual
        # BooleanVars. Keep them inside MOMENTUM, matching the Forex V8.4 GUI.
        div_names = [
            ("div_use_macd", "MACD"),
            ("div_use_macd_hist", "Hist"),
            ("div_use_rsi", "RSI"),
            ("div_use_stoch", "Stoch"),
            ("div_use_cci", "CCI"),
            ("div_use_momentum", "MOM"),
            ("div_use_obv", "OBV"),
            ("div_use_vwmacd", "VWMACD"),
            ("div_use_cmf", "CMF"),
            ("div_use_mfi", "MFI"),
        ]
        self.v_div_use_all = tk.BooleanVar(value=DEFAULT_DIV_USE_ALL)

        def _toggle_divergence_all():
            enabled = bool(self.v_div_use_all.get())
            for key, _label in div_names:
                getattr(self, key).set(enabled)

        tk.Checkbutton(
            fr,
            text="Use all divergence sources",
            variable=self.v_div_use_all,
            command=_toggle_divergence_all,
        ).grid(row=4, column=6, columnspan=2, sticky="w", padx=2, pady=2)

        def _sync_divergence_all():
            self.v_div_use_all.set(
                all(bool(getattr(self, key).get()) for key, _label in div_names)
            )

        for j, (key, label) in enumerate(div_names):
            var = tk.BooleanVar(value=True)
            setattr(self, key, var)
            tk.Checkbutton(
                fr,
                text=label,
                variable=var,
                command=_sync_divergence_all,
            ).grid(
                row=6 + j // 5,
                column=(j % 5) * 2,
                sticky="w",
                padx=2,
                pady=1,
            )

        _option(
            fr, "Divergence Entry", "v_div_entry_mode", "FRESH",
            ("FRESH", "CURRENT_STATE"), 8, 0, 2
        )
        tk.Label(
            fr,
            text="Confirmed pivots only; no look-ahead.",
            fg="#555555",
        ).grid(row=8, column=4, columnspan=4, sticky="w")

        # ---------------- FLOW ----------------
        fr = _family("FLOW — price / volume participation")

        _check(fr, "VWAP", "v_use_vwap", False, 0, 0)
        _entry(fr, "Period", "e_vwap_len", "50", 0, 2)

        _check(fr, "VWAP Delta", "v_use_vwap_delta", False, 1, 0)
        _check(fr, "HMA Smoothing", "v_vwap_delta_smooth", False, 1, 2)
        _entry(fr, "Smooth Len", "e_vwap_delta_smooth_len", "21", 1, 4)
        _entry(fr, "Baseline", "e_vwap_delta_baseline", "50", 1, 6)

        _option(
            fr, "Logic", "v_vwap_delta_logic", "CURRENT_TREND",
            ("CURRENT_TREND", "CROSS_BASELINE"), 2, 0, 2
        )

        _check(fr, "Volume", "v_use_vol", DEFAULT_USE_VOLUME, 3, 0)
        _entry(fr, "Volume MA", "e_vol_len", "20", 3, 2)

        _check(fr, "Volume S/R", "v_use_vol_sr", False, 4, 0)
        _entry(fr, "Vol MA", "e_sr_volume_ma", "6", 4, 2)
        _option(
            fr, "Vote", "v_sr_vote_mode", "MAJORITY",
            ("MAJORITY", "ALL", "ANY"), 4, 4
        )
        _option(
            fr, "Entry", "v_sr_entry_mode", "CURRENT_ZONE",
            ("CURRENT_ZONE", "FRESH_BREAK"), 4, 6
        )

        for idx, (attr, label, default) in enumerate([
            ("sr_tf1", "TF1", "Chart"),
            ("sr_tf2", "TF2", "4h"),
            ("sr_tf3", "TF3", "D"),
            ("sr_tf4", "TF4", "W"),
        ]):
            tk.Label(fr, text=label).grid(
                row=5, column=idx * 2, sticky="e", padx=2, pady=2
            )
            var = tk.StringVar(value=default)
            setattr(self, "v_" + attr, var)
            ttk.OptionMenu(
                fr,
                var,
                default,
                "Chart", "4h", "D", "W", "1h", "15m", "30m", "Disable",
            ).grid(
                row=5, column=idx * 2 + 1, sticky="w", padx=2, pady=2
            )

        tk.Label(
            fr,
            text=(
                "Volume S/R uses volume-confirmed fractal zones; chart-only "
                "drawing objects are represented as numerical states for trading/backtesting."
            ),
            fg="#555555",
        ).grid(row=6, column=0, columnspan=8, sticky="w", pady=2)

        # ---------------- STRUCTURE ----------------
        fr = _family("STRUCTURE — market geometry / location")

        _check(fr, "Liquidity Swings", "v_use_liq_swings", False, 0, 0)
        _entry(fr, "Pivot", "e_liq_length", "14", 0, 2)
        _option(
            fr, "Swing Area", "v_liq_area", "Wick Extremity",
            ("Wick Extremity", "Full Range"), 0, 4
        )
        _option(
            fr, "Filter", "v_liq_filter", "Count",
            ("Count", "Volume"), 0, 6
        )
        _entry(fr, "Filter Value", "e_liq_filter_value", "0", 1, 0)

        _option(
            fr, "Entry", "v_liq_entry_mode", "FRESH_BREAK",
            ("FRESH_BREAK", "CURRENT_TREND"), 1, 4
        )

        _check(fr, "Trendline Breakout", "v_use_trendline", False, 2, 0)
        _entry(fr, "Pivot", "e_trendline_length", "14", 2, 2)
        _entry(fr, "Min Dist", "e_trendline_min_distance", "5", 2, 4)
        _option(
            fr, "Mode", "v_trendline_entry_mode", "FRESH_BREAK",
            ("FRESH_BREAK", "CURRENT_TREND", "BREAK_RETEST"), 2, 6
        )

        _entry(fr, "Breakout Buffer %", "e_trendline_buffer", "0", 3, 0)
        _entry(fr, "Retest Candles", "e_trendline_retest", "3", 3, 2)

        _check(fr, "Multi-TF (4h Confluence)", "v_use_mtf", DEFAULT_USE_MTF, 4, 0, 3)
        tk.Label(
            fr,
            text="4H EMA200 confluence",
            fg="#555555",
        ).grid(row=4, column=4, columnspan=4, sticky="w")

        tk.Label(
            fr,
            text=(
                "BUY = completed candle closes above descending resistance | "
                "SELL = completed candle closes below ascending support"
            ),
            fg="#444444",
        ).grid(row=5, column=0, columnspan=8, sticky="w", pady=1)

        # ---------------- REGIME ----------------
        fr = _family(
            "REGIME — tradeability gates; never counted as duplicate directional votes"
        )

        _check(fr, "ATR", "v_use_atr", DEFAULT_USE_ATR, 0, 0)
        _entry(fr, "Minimum ATR %", "e_atr_min_pct", "0.30", 0, 2)

        _check(fr, "ADX", "v_use_adx", DEFAULT_USE_ADX, 0, 4)
        _entry(fr, "ADX Threshold", "e_adx_thresh", "20", 0, 6)
        _entry(fr, "ADX Period", "e_adx_len", str(DEFAULT_ADX_LEN), 1, 4)