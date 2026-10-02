"""Forex V7.1.3 MT5 audit contract tests.
Dependency-light: no live MetaTrader 5 terminal is required.
"""
import ast
import math
import random
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "UniversalForexBot_MT5.py"

def load_strategy_engine():
    src = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(src, str(SOURCE))
    ns = {"np": np, "math": math}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                ns[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception:
                pass
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "StrategyEngine")
    module = ast.Module(body=[cls], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SOURCE), "exec"), ns)
    return ns["StrategyEngine"], src

def test_source_parses_and_compiles():
    src = SOURCE.read_text(encoding="utf-8")
    ast.parse(src, str(SOURCE))
    compile(src, str(SOURCE), "exec")
    assert 'APP_VERSION = "V8.4.2-FOREX-AI-AGENT-V7.1.3-FX-MT5"' in src
    assert "CONFIG_SCHEMA_VERSION = 71" in src
    assert "RUNTIME_SCHEMA_VERSION = 71" in src

def test_forex_mt5_runtime_contract():
    _, src = load_strategy_engine()
    assert "UniversalFuturesBotGUI.build_exchange = v833_forex_build_exchange" in src
    assert 'raise RuntimeError("V8.3.3 FOREX-ONLY BOT: Crypto/futures exchanges are disabled. Use MT5 Forex.")' in src
    for token in ("mt5.symbol_info", "mt5.symbol_info_tick", "mt5.positions_get", "mt5.order_send"):
        assert token in src

def _decision(SE, modules):
    return SE.ai_agent_decision(
        modules, atr_pass=True, vol_pass=True, adx_pass=True,
        mtf_pass_bull=True, mtf_pass_bear=True,
        min_families=3, min_edge=.2, min_family_confidence=.55,
        require_trend=True, require_structure=True,
        max_conflicting_families=1, min_family_participation=.25,
        fallback_2f_enabled=True, fallback_2f_min_edge=.55,
        fallback_2f_min_confidence=.55, fallback_2f_min_participation=.30,
        fallback_2f_require_structure=True, fallback_2f_require_independent=True,
    )

def test_council_2f_fallback_rejects_opposing_qualified_family():
    SE, _ = load_strategy_engine()
    result = SE.ai_agent_decision(
        [("ST", True, False), ("EMA", True, False), ("RSI", False, True)],
        atr_pass=True, vol_pass=True, adx_pass=True,
        mtf_pass_bull=True, mtf_pass_bear=True,
        min_families=3, min_edge=.99, min_family_confidence=0.0,
        require_trend=False, require_structure=False,
        max_conflicting_families=10, min_family_participation=0.0,
        fallback_2f_enabled=True, fallback_2f_min_edge=.1,
        fallback_2f_min_confidence=0.0, fallback_2f_min_participation=0.0,
        fallback_2f_require_structure=False, fallback_2f_require_independent=False,
    )
    assert result["fallback_2f_buy"] is False
    assert result["side"] == "NONE"

def test_council_never_returns_both_directions():
    SE, _ = load_strategy_engine()
    families = tuple(SE.EVIDENCE_FAMILIES.values())
    indicators = [x for group in families for x in group] + ["ADX", "ATR"]
    random.seed(713)
    for _ in range(30000):
        modules = []
        for name in indicators:
            r = random.random()
            modules.append((name, r < .45, .45 <= r < .90))
        result = _decision(SE, modules)
        assert not (result["buy_ok"] and result["sell_ok"])
        if result.get("split_council"):
            assert result["side"] == "NONE"

def test_ambiguous_candle_is_explicitly_blocked():
    src = SOURCE.read_text(encoding="utf-8")
    assert "AMBIGUOUS_CANDLE" in src
    assert "buy_signal = sell_signal = False" in src

def test_mt5_lot_rounding_and_small_lot_tp_contracts_are_present():
    src = SOURCE.read_text(encoding="utf-8")
    assert "math.floor(q / step + 1e-9) * step" in src
    assert "FOREX SMALL-LOT NOTICE" in src
    assert "the whole position closes at TP1 (TP2 not used)" in src

def test_break_even_verifies_and_retries_without_dropping_original_sl():
    src = SOURCE.read_text(encoding="utf-8")
    assert "for _be_try in range(2)" in src
    assert "BREAK-EVEN NOT VERIFIED: original broker SL remains active" in src

def test_startup_risk_contract():
    src = SOURCE.read_text(encoding="utf-8")
    assert "must be farther than TP1" in src
    assert "RISK CONFLICT: Risk Per Trade" in src
    assert 'emergency_capital_pct": "10.0"' in src
    assert 'self.e_emergency_capital_pct.insert(0, "10.0")' in src

if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in tests:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(tests)}/{len(tests)} PASS")
