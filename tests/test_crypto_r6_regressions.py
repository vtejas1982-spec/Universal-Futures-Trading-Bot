import ast
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "UniversalFuturesBot_CRYPTO.py"

def load_live():
    stub = types.ModuleType("ccxt")
    class DummyExchange:
        pass
    stub.Exchange = DummyExchange
    for name in ("bybit", "binance", "gate", "bitget", "weex"):
        setattr(stub, name, DummyExchange)
    sys.modules["ccxt"] = stub
    spec = importlib.util.spec_from_file_location("crypto_r6_live_test", LIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_r6_source_and_release_contract():
    source = LIVE.read_text(encoding="utf-8")
    ast.parse(source)
    assert 'APP_VERSION = "V8.4.2-CRYPTO-EVIDENCE-HARDENED-R6"' in source
    assert 'AUDIT_BUILD = "V8.4.2-ENGINE-AUDIT-2026-09-27-R6"' in source
    assert source.count('elif signal_mode == "ADAPTIVE_EVIDENCE":') == 1

def test_cooldown_only_starts_after_real_live_to_flat_transition():
    source = LIVE.read_text(encoding="utf-8")
    assert "had_live_state = (" in source
    assert "if had_live_state:" in source
    assert "COOLDOWN STARTED:" in source
    assert "not reset the cooldown on every 30-second poll." in source

def test_hold_sl_wait_cannot_be_overwritten_by_reversal_gate():
    source = LIVE.read_text(encoding="utf-8")
    marker = "if self.hold_sl_wait_reversal and not self.hold_sl_threshold_hit:"
    start = source.index(marker)
    end = source.index("if (", start)
    block = source[start:end]
    assert "reversal_allowed = False" in block
    assert "opposite_checks" in block
    assert block.index("reversal_allowed = False") < block.index("opposite_checks")

def test_all_strategy_modes_still_execute():
    m = load_live()
    modules = [
        ("ST", True, False),
        ("EMA", True, False),
        ("VWAP", True, False),
        ("RSI", False, False),
        ("MACD", False, True),
    ]
    kwargs = dict(
        directional_modules=modules,
        min_score=1,
        atr_pass=True,
        vol_pass=True,
        adx_pass=True,
        mtf_pass_bull=True,
        mtf_pass_bear=True,
        adaptive_edge=0.18,
        adaptive_min_weight=3.5,
        evidence_min_families=2,
        evidence_family_min_score=0.35,
        evidence_require_trend=True,
        evidence_require_independent=True,
    )
    for mode in m.SUPPORTED_SIGNAL_MODES:
        buy, sell, *_ = m.StrategyEngine.decide_signal(signal_mode=mode, **kwargs)
        assert isinstance(buy, bool) and isinstance(sell, bool)

def test_single_signal_conflict_fails_closed():
    m = load_live()
    result = m.StrategyEngine.decide_signal(
        [("A", True, False), ("B", False, True)],
        "SINGLE_SIGNAL",
        1,
    )
    assert result[:2] == (False, False)
