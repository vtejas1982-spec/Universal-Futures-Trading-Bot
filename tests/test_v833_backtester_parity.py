"""V8.3.3 live/backtester strategy-parity regression tests."""
from pathlib import Path
import ast
import importlib.util
import sys
import types
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "V8_3_HARDENED_ADAPTIVE_BOT.py"
BT = ROOT / "V8_3_HARDENED_ADAPTIVE_BACKTESTER.py"

# Backtester tests do not require a live CCXT installation.
sys.modules.setdefault("ccxt", types.SimpleNamespace())

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

live = load(BOT, "live_v833")
bt = load(BT, "bt_v833")

def top_level_functions(src):
    tree = ast.parse(src)
    return {n.name:n for n in tree.body if isinstance(n, ast.FunctionDef)}

def class_source(src, name):
    tree = ast.parse(src)
    lines = src.splitlines(True)
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == name:
            return "".join(lines[n.lineno-1:n.end_lineno])
    raise AssertionError(name)

def test_compile_and_versions():
    compile(BOT.read_text(encoding="utf-8"), str(BOT), "exec")
    compile(BT.read_text(encoding="utf-8"), str(BT), "exec")
    assert live.APP_VERSION == "V8.3.3"
    assert bt.APP_VERSION == "V8.3.3-BT-PARITY"
    assert bt.LIVE_STRATEGY_PARITY_VERSION == "V8.3.3"

def test_indicator_function_ast_parity():
    lsrc = BOT.read_text(encoding="utf-8")
    bsrc = BT.read_text(encoding="utf-8")
    lf = top_level_functions(lsrc)
    bf = top_level_functions(bsrc)
    common = sorted(set(lf) & set(bf))
    assert len(common) >= 30
    for name in common:
        assert ast.dump(lf[name], include_attributes=False) == ast.dump(bf[name], include_attributes=False), name

def test_strategy_engine_exact_parity():
    lsrc = BOT.read_text(encoding="utf-8")
    bsrc = BT.read_text(encoding="utf-8")
    assert ast.dump(ast.parse(class_source(lsrc, "StrategyEngine")), include_attributes=False) == ast.dump(ast.parse(class_source(bsrc, "StrategyEngine")), include_attributes=False)

def test_adaptive_parameters_are_effective_per_call():
    votes = [("ST", True, False), ("EMA", True, False), ("VOL", True, False)]
    passed = bt.StrategyEngine.decide_signal(votes, "ADAPTIVE_SCORE", 1, True, True, True, True, True, 0.18, 2.5)
    blocked = bt.StrategyEngine.decide_signal(votes, "ADAPTIVE_SCORE", 1, True, True, True, True, True, 0.18, 3.5)
    assert passed[0] and not passed[1]
    assert not blocked[0] and not blocked[1]

def test_backtester_decide_uses_profile_parameters():
    cfg = dict(bt.DEFAULTS, signal_mode="ADAPTIVE_SCORE", adaptive_edge=0.18, adaptive_min_weight=3.5)
    votes = [("ST", True, False), ("EMA", True, False), ("VOL", True, False)]
    out = bt.decide(votes, cfg)
    assert out[0] is False and out[1] is False

def test_volume_sr_function_parity():
    lsrc = BOT.read_text(encoding="utf-8")
    bsrc = BT.read_text(encoding="utf-8")
    for name in ("_volume_sr_single_tf", "_volume_sr_base_series"):
        lf = top_level_functions(lsrc)[name]
        bf = top_level_functions(bsrc)[name]
        assert ast.dump(lf, include_attributes=False) == ast.dump(bf, include_attributes=False), name

def test_deterministic_synthetic_full_module_backtest():
    np.random.seed(42)
    n = 2200
    times = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    ret = np.random.normal(0, 0.0012, n) + 0.00015*np.sin(np.arange(n)/35)
    close = 100*np.exp(np.cumsum(ret))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close)*(1+np.random.uniform(0,0.0015,n))
    low = np.minimum(open_, close)*(1-np.random.uniform(0,0.0015,n))
    vol = np.random.lognormal(10, 0.35, n)
    df = pd.DataFrame({
        "time": (times.view("int64")//10**6).astype(np.int64),
        "datetime": times,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "vol": vol,
    })
    cfg = bt.validate_config(dict(bt.DEFAULTS, symbols="TEST/USDT", capital=1000.0, warmup=250,
                                  use_divergence=True, use_vol_sr=True, max_trades=1000))
    built = bt.build_strategy_columns(df, cfg)
    trades, metrics, equity, events = bt.run_backtest(built, cfg)
    assert len(built) == n
    assert np.isfinite(float(metrics["ending_equity"]))
    assert np.isfinite(float(metrics["net_pnl"]))
    assert len(equity) > 0

def test_default_contract():
    assert bt.DEFAULTS["signal_mode"] == "ADAPTIVE_SCORE"
    assert float(bt.DEFAULTS["adaptive_edge"]) == 0.18
    assert float(bt.DEFAULTS["adaptive_min_weight"]) == 3.5
    assert bt.DEFAULTS["use_mtf"] is True
    assert bt.DEFAULTS["use_adx"] is True
    assert bt.DEFAULTS["use_vol"] is True
    assert bt.DEFAULTS["use_atr"] is False
    assert bt.DEFAULTS["grid_mode"] == "OFF"
    assert bt.DEFAULTS["size_mode"] == "EQUITY_RISK_%"

if __name__ == "__main__":
    tests = [v for k,v in globals().items() if k.startswith("test_")]
    for fn in tests:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(tests)}/{len(tests)} PASS")
