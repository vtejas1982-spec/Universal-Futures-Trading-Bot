"""
Universal Futures Bot V8.4.1 FINAL audit/regression suite.

Covers:
- syntax/compile contracts
- self-contained core indicator engine
- V8.4 Evidence-Family StrategyEngine
- legacy signal-mode parity
- GUI construction and critical option/widget coverage
- save/load round-trip for newly audited settings
- deterministic synthetic indicator chain
- Volume S/R module contract
- Grid mode/strategy constants
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
import tempfile
import types
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import py_compile


ROOT = Path(__file__).resolve().parent
if (ROOT / "UniversalFuturesBot_V8_4_1_CRYPTO_FINAL_AUDITED_FIXED.py").exists():
    LIVE = ROOT / "UniversalFuturesBot_V8_4_1_CRYPTO_FINAL_AUDITED_FIXED.py"
else:
    LIVE = ROOT / "UniversalFuturesBot_V8_4_1_EVIDENCE_FAMILY_FULL_AUDIT.py"

if (ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_BACKTESTER_EVIDENCE_V8_4_1_FINAL_AUDITED.py").exists():
    BACKTEST = ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_BACKTESTER_EVIDENCE_V8_4_1_FINAL_AUDITED.py"
else:
    BACKTEST = ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_BACKTESTER_EVIDENCE_V8_4_1_AUDITED.py"

if (ROOT / "UniversalFuturesBot_V8_RECOVERY_MULTI_BOT_AUDITED_V8_4_1_FIXED.py").exists():
    RECOVERY = ROOT / "UniversalFuturesBot_V8_RECOVERY_MULTI_BOT_AUDITED_V8_4_1_FIXED.py"
else:
    RECOVERY = ROOT / "UniversalFuturesBot_V8_RECOVERY_MULTI_BOT_AUDITED.py"

PASS = 0
FAIL = 0
SKIP = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name}" + (f" :: {detail}" if detail else ""))


def skip(name, detail):
    global SKIP
    SKIP += 1
    print(f"[SKIP] {name} :: {detail}")


def load_module(path: Path):
    # The GUI/live module only needs ccxt to exist during import. If the test
    # environment lacks it, provide a no-network compatibility stub.
    try:
        import ccxt  # noqa: F401
    except ModuleNotFoundError:
        ccxt = types.ModuleType("ccxt")

        class DummyExchange:
            def __init__(self, *args, **kwargs):
                pass

        for name in ("bybit", "binance", "gate", "bitget", "weex"):
            setattr(ccxt, name, DummyExchange)
        ccxt.NetworkError = Exception
        ccxt.ExchangeError = Exception
        sys.modules["ccxt"] = ccxt

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not create import spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def synthetic_ohlcv(rows=700):
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.35, rows))
    open_ = close + rng.normal(0.0, 0.12, rows)
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.6, rows)
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.6, rows)
    vol = rng.uniform(100.0, 2000.0, rows)
    return pd.DataFrame(
        {
            "time": np.arange(rows, dtype=np.int64) * 900_000,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "vol": vol,
        }
    )


def main():
    print("=== Universal Futures Bot V8.4.1 FINAL Audit ===")

    for path in (LIVE, BACKTEST, RECOVERY):
        check(f"Required file: {path.name}", path.exists())
        if path.exists():
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                check(f"AST parse: {path.name}", True)
                py_compile.compile(str(path), doraise=True)
                check(f"py_compile: {path.name}", True)
            except Exception as exc:
                check(f"compile: {path.name}", False, repr(exc))

    if not LIVE.exists():
        print(f"RESULT: {PASS} PASS / {FAIL} FAIL / {SKIP} SKIP")
        return 1

    live_source = LIVE.read_text(encoding="utf-8")

    # 1. The categorized live file must contain the entire core indicator engine.
    core_functions = (
        "calculate_rma",
        "calculate_supertrend",
        "calculate_adx",
        "calculate_macd",
        "calculate_rsi",
        "calculate_wma",
        "calculate_rsi_ma",
        "calculate_hma",
        "calculate_vwap_delta",
        "calculate_vidya",
        "calculate_nadaraya_watson_envelope",
    )
    for name in core_functions:
        check(f"Core indicator present: {name}", f"def {name}(" in live_source)

    # 2. Evidence-family and GUI contract.
    for item in (
        'APP_VERSION = "V8.4.1-CRYPTO-EVIDENCE-FAMILY-AUDITED"',
        'AUDIT_BUILD = "V8.4.1-ENGINE-AUDIT-2026-09-21-FINAL"',
        'DEFAULT_SIGNAL_MODE = "ADAPTIVE_EVIDENCE"',
        '"ADAPTIVE_EVIDENCE"',
        '"TREND"',
        '"MOMENTUM"',
        '"FLOW"',
        '"STRUCTURE"',
        '"REGIME"',
        "evidence_min_families",
        "evidence_family_min_score",
        "evidence_require_trend",
        "evidence_require_independent",
        "e_div_min_count",
        "div_use_all",
        "class StrategyEngine",
        "class UniversalFuturesBotGUI",
    ):
        check(f"Live contract: {item}", item in live_source)

    tree = ast.parse(live_source)
    gui_classes = [
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "UniversalFuturesBotGUI"
    ]
    check("Exactly one UniversalFuturesBotGUI class", len(gui_classes) == 1)

    # 3. StrategyEngine behavioral contract.
    try:
        mod = load_module(LIVE)
        engine = mod.StrategyEngine

        trend_only = [("ST", True, False), ("EMA", True, False)]
        b, s, *_ = engine.decide_signal(
            trend_only,
            "ADAPTIVE_EVIDENCE",
            1,
            atr_pass=True,
            adx_pass=True,
            evidence_min_families=1,
            evidence_family_min_score=0.35,
            evidence_require_trend=True,
            evidence_require_independent=True,
            adaptive_edge=0.0,
        )
        check("Evidence: Trend-only blocked by independent-family rule", not b and not s)

        trend_momentum = trend_only + [("RSI", True, False), ("STOCH", True, False)]
        b, s, *_ = engine.decide_signal(
            trend_momentum,
            "ADAPTIVE_EVIDENCE",
            1,
            atr_pass=True,
            adx_pass=True,
            evidence_min_families=2,
            evidence_family_min_score=0.35,
            evidence_require_trend=True,
            evidence_require_independent=True,
            adaptive_edge=0.0,
        )
        check("Evidence: Trend + Momentum BUY", b and not s)

        b, s, *_ = engine.decide_signal(
            trend_momentum,
            "ADAPTIVE_EVIDENCE",
            1,
            atr_pass=False,
            adx_pass=True,
            evidence_min_families=2,
            evidence_family_min_score=0.35,
            evidence_require_trend=True,
            evidence_require_independent=True,
            adaptive_edge=0.0,
        )
        check("Evidence: ATR regime gate blocks signal", not b and not s)

        b, s, *_ = engine.decide_signal(
            [("ST", True, False), ("EMA", True, False)],
            "2_SIGNALS",
            2,
        )
        check("Legacy 2_SIGNALS preserved", b and not s)

        b, s, *_ = engine.decide_signal(
            [("ST", True, False)],
            "SINGLE_SIGNAL",
            1,
        )
        check("Legacy SINGLE_SIGNAL preserved", b and not s)

        reason = engine.decision_reason(
            trend_momentum,
            "ADAPTIVE_EVIDENCE",
            1,
            atr_pass=True,
            adx_pass=True,
            evidence_min_families=2,
            evidence_family_min_score=0.35,
            evidence_require_trend=True,
            evidence_require_independent=True,
            adaptive_edge=0.0,
        )
        check("Evidence decision_reason uses family settings", reason.startswith("EVIDENCE_BUY_"))

        verifier = object.__new__(mod.UniversalFuturesBotGUI)
        verifier.protection_reconcile_interval = 10.0
        verifier.log = lambda *_args, **_kwargs: None
        verifier._order_is_still_open = lambda *_args, **_kwargs: None
        verified = verifier.verify_protection_orders("BTC/USDT", [("SL", {"id": "ambiguous"})])
        check("Protection verification fails closed on inconclusive order state", verified is False)

    except ModuleNotFoundError as exc:
        skip("StrategyEngine import/behavior", f"missing dependency: {exc.name}")
        mod = None
    except Exception as exc:
        check("StrategyEngine import/behavior", False, repr(exc))
        traceback.print_exc()
        mod = None

    # 4. Full indicator chain.
    if mod is not None:
        try:
            df = synthetic_ohlcv()
            df = mod.calculate_supertrend(df, 10, 2.0, "CLOSE", True)
            df = mod.calculate_adx(df, 14)
            df = mod.calculate_macd(df, 12, 26, 9)
            df = mod.calculate_rsi(df, 14)
            df = mod.calculate_rsi_ma(df, "EMA", 9)
            df = mod.calculate_bollinger(df, 20, 2.0)
            df = mod.calculate_stochastic(df, 14, 3, 3)
            df = mod.calculate_vwap(df, 50)
            df = mod.calculate_vwap_delta(df, False, 21, 50)
            df = mod.calculate_vidya(df, 10, 20, 2.0)
            df = mod.calculate_nadaraya_watson_envelope(df, 8, 3.0)
            df = mod.calculate_liquidity_swings(df, 14, "Wick Extremity", "Count", 0)
            df = mod.calculate_trendline_breakout(df, 14, 5, 0.0, 3)
            div_cfg = {
                "div_pivot": 5, "div_source": "Close", "div_type": "Regular",
                "div_max_pivots": 10, "div_max_bars": 100,
                "div_cci_len": 10, "div_mom_len": 10, "div_entry_mode": "FRESH",
                "div_use_macd": True, "div_use_macd_hist": True, "div_use_rsi": True,
                "div_use_stoch": True, "div_use_cci": True, "div_use_momentum": True,
                "div_use_obv": True, "div_use_vwmacd": True,
                "div_use_cmf": True, "div_use_mfi": True,
            }
            df = mod.calculate_divergence_module(df, div_cfg)
            check("Full 19-module indicator chain builds", len(df) == 700)

            sr = mod.calculate_volume_sr_module(
                [("Chart", df[["time","open","high","low","close","vol"]].copy(), True)],
                {
                    "sr_volume_ma": 6,
                    "sr_vote_mode": "MAJORITY",
                    "sr_entry_mode": "CURRENT_ZONE",
                },
            )
            check("Volume S/R module returns directional state", isinstance(sr, dict) and "bull" in sr and "bear" in sr)
        except Exception as exc:
            check("Full 19-module indicator chain", False, repr(exc))
            traceback.print_exc()

    # 5. GUI init + critical widget + config round-trip.
    if mod is not None:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            with tempfile.TemporaryDirectory(prefix="v841_audit_") as tmp:
                tmp = Path(tmp)
                mod.PROFILE_DIR = tmp / "profiles"
                mod.CONFIG_FILE = str(tmp / "config.json")
                mod.LOG_FILE = str(tmp / "trades.csv")
                mod.MASTER_DB_FILE = str(tmp / "master.db")
                mod.MASTER_CSV_FILE = str(tmp / "master.csv")

                app = mod.UniversalFuturesBotGUI(root)
                check("GUI initializes", True)
                check("GUI has missing divergence Min Div control", hasattr(app, "e_div_min_count"))
                check("GUI has Use-All divergence control", hasattr(app, "v_div_use_all"))
                check("GUI default signal mode is ADAPTIVE_EVIDENCE", app.v_signal_mode.get() == "ADAPTIVE_EVIDENCE")

                app.v_bot_id.set("AUDIT-TEMP")
                app.bot_profile_id = "AUDIT-TEMP"
                app.e_div_min_count.delete(0, tk.END)
                app.e_div_min_count.insert(0, "3")
                app.v_div_use_all.set(False)
                app.div_use_macd.set(True)
                app.div_use_rsi.set(False)
                app.e_evidence_min_families.delete(0, tk.END)
                app.e_evidence_min_families.insert(0, "2")
                app.save_settings()
                app.e_div_min_count.delete(0, tk.END)
                app.e_div_min_count.insert(0, "1")
                app.load_settings(show_resume=False)
                check("Divergence Min Div save/load round-trip", app.e_div_min_count.get() == "3")
                check("Divergence source save/load round-trip", not bool(app.div_use_rsi.get()))
                check("Evidence family setting save/load round-trip", app.e_evidence_min_families.get() == "2")

            root.destroy()
        except Exception as exc:
            # Headless CI may not have a display. A real Windows run is still
            # covered by the same GUI constructor path.
            if exc.__class__.__name__ in {"TclError", "tkinter.TclError"} or "no display" in str(exc).lower():
                skip("GUI smoke/round-trip", "headless Tk environment")
            else:
                check("GUI smoke/round-trip", False, repr(exc))
                traceback.print_exc()

    print()
    print(f"RESULT: {PASS} PASS / {FAIL} FAIL / {SKIP} SKIP")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())