"""R6.8.7.11 focused contract checks."""

import ast
from pathlib import Path

SOURCE = Path("UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.11.py")

def load_source():
    return SOURCE.read_text(encoding="utf-8")

def test_source_parses_and_compiles():
    src = load_source()
    tree = ast.parse(src)
    compile(src, str(SOURCE), "exec")
    assert tree

def test_vwap_delta_bear_is_not_forced_when_enabled():
    src = load_source()
    bad = """                    else:
                        vwap_delta_bull = True
                    vwap_delta_bear = True
"""
    assert bad not in src

def test_ai_direct_calls_share_soft_and_2f_contract():
    tree = ast.parse(load_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "ai_agent_decision":
            names = {kw.arg for kw in node.keywords}
            for key in (
                "fallback_2f_enabled", "fallback_2f_min_edge",
                "fallback_2f_min_confidence", "fallback_2f_min_participation",
                "fallback_2f_require_structure", "fallback_2f_require_independent",
                "soft_regime", "soft_edge", "soft_min_families",
                "soft_max_regime_misses",
            ):
                assert key in names

def test_grid_quantity_uses_contract_size():
    src = load_source()
    assert "usdt_size / (price * contract_size)" in src
    assert "current_exposure" in src and "* _grid_contract_size" in src

def test_grid_liquidation_guard_exists():
    src = load_source()
    assert "Grid Global SL is too wide" in src
    assert "liq_safe_move(_grid_leverage, _grid_buffer)" in src

def test_decide_signal_uses_keyword_contract():
    tree = ast.parse(load_source())
    target = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "decide_signal")
    params = {a.arg for a in target.args.args}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "decide_signal":
            assert not node.args
            names = {kw.arg for kw in node.keywords if kw.arg}
            assert params >= names
            assert "ai_min_family_confidence" in names
            assert "ai_max_conflicting_families" in names

def test_high_leverage_diagnostic_uses_authoritative_tier():
    src = load_source()
    assert "float(leverage_tier(lev)[0])" in src
    assert "min(HIGH_LEVERAGE_MAX_RISK_PCT, leverage_tier(lev)[0]" not in src

def test_new_ai_controls_are_persisted():
    src = load_source()
    for key in (
        "ai_2f_min_edge", "ai_2f_min_family_confidence",
        "ai_2f_min_participation", "ai_2f_require_structure",
        "ai_2f_require_independent", "ai_adaptive_atr_quantile",
        "ai_adaptive_atr_floor_pct",
    ):
        assert key in src

def test_actual_fixed_qty_check_uses_actual_exchange_leverage():
    src = load_source()
    assert "actual_position_leverage or leverage" in src

def test_runtime_snapshot_numeric_reads_are_hardened():
    src = load_source()
    assert "def _safe_runtime_float" in src
    assert "def _safe_runtime_int" in src
    assert "def _safe_runtime_bool" in src
    assert "def _safe_runtime_text" in src
    assert "risk_pct = self._safe_runtime_float" in src
    assert "leverage = self._safe_runtime_int" in src

def test_cycle_error_records_traceback():
    src = load_source()
    assert "CYCLE ERROR TRACE:" in src
    assert "traceback.format_exc()" in src

def test_live_ai_trade_manager_receives_profile_2f_controls():
    src = load_source()
    marker = "fallback_2f_enabled=bool(self._runtime_gui_value"
    pos = src.rfind(marker)
    tail = src[pos:pos + 1800]
    for key in (
        "fallback_2f_min_edge",
        "fallback_2f_min_confidence",
        "fallback_2f_min_participation",
        "fallback_2f_require_structure",
        "fallback_2f_require_independent",
    ):
        assert key in tail

def test_no_duplicate_2f_preset_keys():
    src = load_source()
    assert src.count('"ai_2f_min_edge": 0.65') == 1
    assert src.count('"ai_2f_min_family_confidence": 0.65') == 1
    assert src.count('"ai_2f_min_participation": 0.40') == 1
