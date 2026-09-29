from pathlib import Path
import ast
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py"


def _source():
    return SOURCE.read_text(encoding="utf-8")


def test_r67_parses_and_contains_expected_class_contract():
    source = _source()
    tree = ast.parse(source)
    gui = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "UniversalFuturesBotGUI"
    )
    methods = {
        node.name for node in gui.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    required = {
        "_log_protection_order_response",
        "_order_is_still_open",
        "create_bybit_trigger",
        "create_protection_orders",
        "verify_protection_orders",
    }
    assert required <= methods


def test_r67_bybit_protection_parameters_are_explicit():
    source = _source()
    for token in (
        '"triggerPrice"',
        '"triggerDirection"',
        '"triggerBy": "LastPrice"',
        '"reduceOnly": True',
        '"closeOnTrigger": True',
        '"positionIdx": 0',
    ):
        assert token in source


def test_r67_tp_split_defaults_and_fail_closed_contract():
    source = _source()
    assert 'DEFAULT_TP_QTY_MODE = "PERCENT_%"' in source
    assert "DEFAULT_TP1_CLOSE_PERCENT = 50.0" in source
    assert "DEFAULT_TP2_CLOSE_PERCENT = 50.0" in source
    assert "PROTECTION SET CREATE FAILED" in source
    assert "PROTECTION VERIFY FAILED" in source
    assert "Protection set incomplete" in source


def test_r67_ai_manager_forwards_real_regime_gates():
    source = _source()
    assert "atr_pass=bool(atr_pass)" in source
    assert "vol_pass=bool(vol_pass)" in source
    assert "adx_pass=bool(adx_pass)" in source
    assert "mtf_pass_bull=bool(mtf_pass_bull)" in source
    assert "mtf_pass_bear=bool(mtf_pass_bear)" in source


def test_r67_ai_block_diagnostics_include_dominant_and_mtf_gate():
    source = _source()
    assert 'blocks=[f"DOMINANT={dominant_side}"]' in source
    assert 'blocks.append("MTF_GATE_BUY")' in source
    assert 'blocks.append("MTF_GATE_SELL")' in source
    assert 'blocks.append("MTF_GATE_TIE")' in source


def test_r67_ai_startup_log_uses_configured_thresholds():
    source = _source()
    assert 'f"AI MinFamilies={ai_min_families}"' in source
    assert 'f"AI Edge>={ai_min_edge:.2f}"' in source
    assert 'f"AI FamilyConfidence>={ai_family_confidence:.2f}"' in source
    assert 'f"AI MaxConflicts={ai_max_conflicts}"' in source


def test_r67_tp_preflight_rejects_invalid_split_and_ordering():
    source = _source()
    assert 'TP Quantity Mode must be PERCENT_% or FIXED_QTY.' in source
    assert 'TP1/TP2 close percentages must each be greater than 0 and less than 100%.' in source
    assert 'ATR TP2 multiplier must be greater than ATR TP1 multiplier.' in source


def test_r67_runtime_schema_and_full_contract_audit_marker():
    source = _source()
    assert 'CONFIG_SCHEMA_VERSION = 23' in source
    assert 'RUNTIME_SCHEMA_VERSION = 24' in source
    assert 'R6.7-PROTECTION-ENGINE-AUDIT-FULL-CONTRACT-AUDIT' in source


def test_r67_volume_sr_uses_completed_candles_in_live_cache():
    source = _source()
    assert 'base_df.iloc[:-1].copy() if len(base_df) > 1 else base_df.iloc[0:0].copy()' in source
    assert '# Live strategy signals use completed candles only; exclude the current HTF candle.' in source


def test_r67_conditional_protection_validation_is_feature_aware():
    source = _source()
    assert 'Every enabled SL/TP target must be finite and greater than 0.' in source
    assert 'ATR SL multiplier must be greater than 0 when ATR SL is enabled.' in source
    assert 'ATR TP2 multiplier must be greater than ATR TP1 when both TP levels are enabled.' in source


def test_r67_ai_runtime_log_uses_configured_values():
    source = _source()
    assert 'f"AI MinFamilies={ai_min_families}' in source
    assert 'f"AI Edge>={ai_min_edge:.2f}' in source
    assert 'f"AI FamilyConfidence>={ai_family_confidence:.2f}' in source
    assert 'f"AI MaxConflicts={ai_max_conflicts}' in source


def test_r68_risk_notional_cap_is_present():
    source = _source()
    assert 'RISK_NOTIONAL_UTILIZATION_CAP = 0.95' in source
    assert 'RISK NOTIONAL CAP' in source
    assert 'leverage=None' in source


def test_r68_ai_block_diagnostics_include_family_confidence():
    source = _source()
    assert 'FAMILY_DETAIL=' in source
    assert "data['confidence']:.2f" in source
