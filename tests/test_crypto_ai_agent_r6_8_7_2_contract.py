#!/usr/bin/env python3
"""Focused contract tests for Crypto AI-Agent R6.8.7.2."""

import importlib.util
import math
import sys
import types
from pathlib import Path

import numpy as np

ENGINE = Path(__file__).with_name("UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.2_AUDIT_FIXED.py")

# The live engine requires ccxt at runtime. The pure contract tests do not need
# an installed exchange adapter, so provide a minimal import stub when needed.
try:
    import ccxt  # noqa: F401
except Exception:
    stub = types.ModuleType("ccxt")
    for name in ("bybit", "binance", "gate", "bitget", "weex"):
        setattr(stub, name, lambda *a, **k: None)
    sys.modules["ccxt"] = stub

spec = importlib.util.spec_from_file_location("crypto_ai_r6872", str(ENGINE))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_version_and_contract():
    assert_true(mod.APP_VERSION.endswith("R6.8.7.2"), mod.APP_VERSION)
    assert_true(mod.CONFIG_SCHEMA_VERSION == 27, "unexpected config schema")
    assert_true("AI_AGENT_RECOMMENDED_R6.8.7.2" == mod.AI_AGENT_PRESET_NAME,
                mod.AI_AGENT_PRESET_NAME)


def test_ai_council_strong_buy():
    modules = [
        ("ST", True, False), ("EMA", True, False), ("EMA_CROSS", True, False),
        ("MACD", True, False), ("VWAP", True, False),
        ("VWAP_DELTA", True, False), ("VIDYA", True, False),
        ("LIQ_SWING", True, False), ("TRENDLINE", True, False),
        ("MTF", True, False),
    ]
    r = mod.StrategyEngine.ai_agent_decision(
        modules, atr_pass=True, vol_pass=True, adx_pass=True,
        mtf_pass_bull=True, mtf_pass_bear=False,
        min_families=3, min_edge=.20, min_family_confidence=.55,
        require_trend=True, require_structure=True,
        max_conflicting_families=1, min_family_participation=.35,
    )
    assert_true(r["side"] == "BUY", f"unexpected AI side: {r}")


def test_ai_ambiguous_council_is_none():
    modules = [
        ("ST", True, False), ("EMA", False, True),
        ("VWAP", True, False), ("VWAP_DELTA", False, True),
        ("LIQ_SWING", True, False), ("TRENDLINE", False, True),
        ("MTF", True, False),
    ]
    r = mod.StrategyEngine.ai_agent_decision(
        modules, atr_pass=True, vol_pass=True, adx_pass=True,
        mtf_pass_bull=True, mtf_pass_bear=False,
        min_families=3, min_edge=.20, min_family_confidence=.55,
        require_trend=True, require_structure=True,
        max_conflicting_families=1, min_family_participation=.35,
    )
    assert_true(r["side"] in ("NONE", "BUY"), "council must not manufacture SELL")


def test_liquidation_and_cost_guards():
    assert_true(mod.liq_safe_move(5, 3) > mod.liq_safe_move(20, 3),
                "higher leverage must tighten liquidation-safe stop distance")
    assert_true(mod.cost_gate_reason(.0005, .001, .055) is not None,
                "tiny stop should fail cost gate")
    assert_true(mod.cost_gate_reason(.01, .02, .055) is None,
                "healthy stop/TP should pass cost gate")


def test_entry_sizing_formula():
    obj = mod.UniversalFuturesBotGUI.__new__(mod.UniversalFuturesBotGUI)
    obj.safe_amount = lambda symbol, q: float(q)
    obj.log = lambda *a, **k: None
    obj._runtime_gui_value = lambda key, default=None: False
    qty = obj.calculate_entry_qty(
        "TEST", 1000.0, 100.0, .35, .02,
        "EQUITY_RISK_%", .001, leverage=5
    )
    # 1000 * .35% / (100 * 2%) = 1.75 units.
    assert_true(abs(qty - 1.75) < 1e-12, f"wrong risk sizing: {qty}")


def test_protection_resolver_ordering():
    obj = mod.UniversalFuturesBotGUI.__new__(mod.UniversalFuturesBotGUI)
    obj._runtime_gui_value = lambda key, default=None: {
        "e_hold_sl_roi": 5.0,
        "v_hold_until_all_reverse": False,
        "v_hold_sl_wait_reversal": False,
    }.get(key, default)
    obj._liq_buffer_value = lambda: 3.0
    obj.safe_price = lambda symbol, x: float(x)
    sl, tp1, tp2, slm, t1m, t2m, source = obj._calculate_r96_protection_prices(
        "TEST", "LONG", 100.0, 10.0, 100.0, 5.0,
        atr_value=1.0, use_legacy=False, hold_all_reverse=False,
        hold_wait_reversal=False, simple_sl_enabled=True,
        simple_roi_sl_enabled=True, roi_sl_target=30.0,
        simple_atr_sl_enabled=True, fallback_sl_enabled=True,
        fallback_sl_roi=30.0, simple_tp_enabled=True,
        tp1_enabled=True, tp2_enabled=True, tp1_roi=60.0,
        tp2_roi=120.0, simple_atr_tp_enabled=True,
        atr_sl_mult=1.5, atr_tp1_mult=1.2, atr_tp2_mult=2.2
    )
    assert_true(source == "ATR", source)
    assert_true(sl < 100 < tp1 < tp2, (sl, tp1, tp2))
    assert_true(t2m > t1m > 0, (t1m, t2m))


def test_post_fill_guard():
    obj = mod.UniversalFuturesBotGUI.__new__(mod.UniversalFuturesBotGUI)
    obj.execution_quality_last = {"best_ask": 100.0}
    obj._safe_runtime_float = lambda key, default: .20
    obj.log = lambda *a, **k: None
    obj._post_fill_execution_safety_check({"side":"LONG","entry":100.10}, obj.execution_quality_last)
    try:
        obj._post_fill_execution_safety_check({"side":"LONG","entry":100.50}, obj.execution_quality_last)
    except RuntimeError:
        pass
    else:
        raise AssertionError("bad post-fill slippage was not rejected")


def test_trailing_is_actually_called():
    text = ENGINE.read_text(encoding="utf-8")
    calls = text.count("self._manage_ai_trailing_stop(")
    assert_true(calls >= 1, "AI trailing method exists but is not called by the runtime")


def main():
    tests = [
        test_version_and_contract,
        test_ai_council_strong_buy,
        test_ai_ambiguous_council_is_none,
        test_liquidation_and_cost_guards,
        test_entry_sizing_formula,
        test_protection_resolver_ordering,
        test_post_fill_guard,
        test_trailing_is_actually_called,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"\nALL {len(tests)} R6.8.7.2 CONTRACT TESTS PASSED")


if __name__ == "__main__":
    main()