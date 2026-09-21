"""
Universal Futures Bot V8.4.1 FINAL-R2 audit/regression suite.

Covers:
- syntax/compile contracts for live/backtester/recovery
- self-contained live core indicator engine
- V8.4 Evidence-Family StrategyEngine
- legacy signal-mode parity and conflict handling
- GUI construction/critical option coverage
- configuration save/load round-trip
- deterministic 19-module indicator chain
- Volume S/R module contract
- direct backtester execution from raw OHLCV without a prebuilt datetime/indicator frame
- duplicate top-level strategy-function guard
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
import traceback
import types
from pathlib import Path

import numpy as np
import pandas as pd
import py_compile


ROOT = Path(__file__).resolve().parent
if ROOT.name == "tests":
    ROOT = ROOT.parent

LIVE = ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_EVIDENCE_HARDENED.py"
BACKTEST = ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_BACKTESTER_EVIDENCE.py"
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


def install_ccxt_stub():
    if "ccxt" in sys.modules:
        return
    try:
        import ccxt  # noqa: F401
        return
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


def load_module(path: Path):
    install_ccxt_stub()
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
    print("=== Universal Futures Bot V8.4.1 FINAL-R2 Audit ===")

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
    live_tree = ast.parse(live_source)

    # Live top-level duplicate guard.
    for name in (
        "calculate_liquidity_swings",
        "calculate_trendline_breakout",
        "UniversalFuturesBotGUI",
        "StrategyEngine",
    ):
        count = sum(
            isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name
            for n in live_tree.body
        )
        check(f"Live single definition: {name}", count == 1, f"count={count}")

    # Backtester duplicate guard.
    if BACKTEST.exists():
        bt_tree = ast.parse(BACKTEST.read_text(encoding="utf-8"))
        for name in ("calculate_liquidity_swings", "calculate_trendline_breakout"):
            count = sum(
                isinstance(n, ast.FunctionDef) and n.name == name
                for n in bt_tree.body
            )
            check(f"Backtester single definition: {name}", count == 1, f"count={count}")

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

    for item in (
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

    try:
        live = load_module(LIVE)
        engine = live.StrategyEngine

        trend_only = [("ST", True, False), ("EMA", True, False)]
        common = dict(
            atr_pass=True,
            adx_pass=True,
            evidence_min_families=2,
            evidence_family_min_score=0.35,
            evidence_require_trend=True,
            evidence_require_independent=True,
            adaptive_edge=0.0,
        )

        b, s, *_ = engine.decide_signal(trend_only, "ADAPTIVE_EVIDENCE", 1, **common)
        check("Evidence: Trend-only blocked", not b and not s)

        trend_momentum = trend_only + [("RSI", True, False), ("STOCH", True, False)]
        b, s, *_ = engine.decide_signal(trend_momentum, "ADAPTIVE_EVIDENCE", 1, **common)
        check("Evidence: Trend + Momentum BUY", b and not s)

        b, s, *_ = engine.decide_signal(
            trend_momentum, "ADAPTIVE_EVIDENCE", 1, **{**common, "atr_pass": False}
        )
        check("Evidence: ATR gate blocks", not b and not s)

        regime_only = trend_only + [("ATR", True, False), ("ADX", True, False)]
        b, s, *_ = engine.decide_signal(regime_only, "ADAPTIVE_EVIDENCE", 1, **common)
        check("Evidence: Regime does not count as family", not b and not s)

        b, s, *_ = engine.decide_signal(
            [("ST", True, False), ("EMA", False, True)], "SINGLE_SIGNAL", 1
        )
        check("SINGLE_SIGNAL conflict blocks", not b and not s)

        b, s, *_ = engine.decide_signal(
            [("ST", True, False)], "SINGLE_SIGNAL", 1
        )
        check("SINGLE_SIGNAL single BUY", b and not s)

        b, s, *_ = engine.decide_signal(
            [("ST", True, False), ("EMA", True, False)], "2_SIGNALS", 2
        )
        check("Legacy 2_SIGNALS preserved", b and not s)

        reason = engine.decision_reason(
            trend_only, "ADAPTIVE_EVIDENCE", 1, **common
        )
        check("Evidence diagnostic parity", reason.startswith("EVIDENCE_BLOCKED_"))

        # Protection verification should fail closed when exchange state is inconclusive.
        verifier = object.__new__(live.UniversalFuturesBotGUI)
        verifier.protection_reconcile_interval = 10.0
        verifier.log = lambda *_a, **_k: None
        verifier._order_is_still_open = lambda *_a, **_k: None
        try:
            result = verifier.verify_protection_orders(
                "BTC/USDT", [("SL", {"id": "ambiguous"})]
            )
            check("Protection verification fails closed", result is False)
        except Exception as exc:
            check("Protection verification fail-closed path", False, repr(exc))

        # Deterministic full indicator chain.
        df = synthetic_ohlcv()
        df = live.calculate_supertrend(df, 10, 2.0, "CLOSE", True)
        df = live.calculate_adx(df, 14)
        df = live.calculate_macd(df, 12, 26, 9)
        df = live.calculate_rsi(df, 14)
        df = live.calculate_rsi_ma(df, "EMA", 9)
        df = live.calculate_bollinger(df, 20, 2.0)
        df = live.calculate_stochastic(df, 14, 3, 3)
        df = live.calculate_vwap(df, 50)
        df = live.calculate_vwap_delta(df, False, 21, 50)
        df = live.calculate_vidya(df, 10, 20, 2.0)
        df = live.calculate_nadaraya_watson_envelope(df, 8, 3.0)
        df = live.calculate_liquidity_swings(df, 14, "Wick Extremity", "Count", 0)
        df = live.calculate_trendline_breakout(df, 14, 5, 0.0, 3)
        div_cfg = {
            "div_pivot": 5,
            "div_source": "Close",
            "div_type": "Regular",
            "div_max_pivots": 10,
            "div_max_bars": 100,
            "div_cci_len": 10,
            "div_mom_len": 10,
            "div_entry_mode": "FRESH",
            "div_use_macd": True,
            "div_use_macd_hist": True,
            "div_use_rsi": True,
            "div_use_stoch": True,
            "div_use_cci": True,
            "div_use_momentum": True,
            "div_use_obv": True,
            "div_use_vwmacd": True,
            "div_use_cmf": True,
            "div_use_mfi": True,
        }
        df = live.calculate_divergence_module(df, div_cfg)
        sr = live.calculate_volume_sr_module(
            [("Chart", df[["time", "open", "high", "low", "close", "vol"]], True)],
            {"sr_volume_ma": 6, "sr_vote_mode": "MAJORITY", "sr_entry_mode": "CURRENT_ZONE"},
        )
        check("Full 19-module indicator chain", len(df) == 700)
        check("Volume S/R state", isinstance(sr, dict) and "bull" in sr and "bear" in sr)

        # GUI smoke is skipped only when there is no display.
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            with tempfile.TemporaryDirectory(prefix="v841_r2_") as tmp:
                tmp = Path(tmp)
                live.APP_DIR = tmp
                live.PROFILE_DIR = tmp / "profiles"
                live.CONFIG_FILE = str(tmp / "config.json")
                live.LOG_FILE = str(tmp / "trades.csv")
                live.MASTER_DB_FILE = str(tmp / "master.db")
                live.MASTER_CSV_FILE = str(tmp / "master.csv")

                app = live.UniversalFuturesBotGUI(root)
                check("GUI initializes", True)
                check("GUI Min Div exists", hasattr(app, "e_div_min_count"))
                check("GUI Use-All divergence exists", hasattr(app, "v_div_use_all"))
                check(
                    "GUI default ADAPTIVE_EVIDENCE",
                    app.v_signal_mode.get() == "ADAPTIVE_EVIDENCE",
                )

                app.bot_profile_id = "AUDIT-R2"
                app.v_bot_id.set("AUDIT-R2")
                app.e_div_min_count.delete(0, tk.END)
                app.e_div_min_count.insert(0, "3")
                app.e_evidence_min_families.delete(0, tk.END)
                app.e_evidence_min_families.insert(0, "3")
                app.save_settings()
                app.e_div_min_count.delete(0, tk.END)
                app.e_div_min_count.insert(0, "1")
                app.load_settings(show_resume=False)
                check("GUI save/load Min Div", app.e_div_min_count.get() == "3")
                check(
                    "GUI save/load Evidence Families",
                    app.e_evidence_min_families.get() == "3",
                )
                check("Startup preflight defaults", app._validate_v83_preflight() is True)

            root.destroy()
        except Exception as exc:
            if "no display" in str(exc).lower() or exc.__class__.__name__ == "TclError":
                skip("GUI smoke/round-trip", "headless environment")
            else:
                check("GUI smoke/round-trip", False, repr(exc))
                traceback.print_exc()

    except ModuleNotFoundError as exc:
        skip("Live import/behavior", f"missing dependency: {exc.name}")
    except Exception as exc:
        check("Live import/behavior", False, repr(exc))
        traceback.print_exc()

    # Backtester direct API regression.
    if BACKTEST.exists():
        try:
            bt = load_module(BACKTEST)
            cfg = dict(bt.DEFAULTS)
            raw = synthetic_ohlcv(900)
            result = bt.run_backtest(raw, cfg)
            check("Backtester accepts raw OHLCV with only time", isinstance(result, tuple) and len(result) >= 2)
        except Exception as exc:
            check("Backtester raw-OHLCV regression", False, repr(exc))
            traceback.print_exc()

    print()
    print(f"RESULT: {PASS} PASS / {FAIL} FAIL / {SKIP} SKIP")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())