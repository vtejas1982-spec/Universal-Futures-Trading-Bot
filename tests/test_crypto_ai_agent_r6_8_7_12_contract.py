import importlib.util
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BT = ROOT / "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.12_BACKTESTER.py"

spec = importlib.util.spec_from_file_location("crypto_bt", BT)
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

def test_ai_agent_contract():
    votes = [
        ("EMA", True, False), ("MACD", True, False),
        ("VWAP", True, False), ("LIQ_SWING", True, False),
        ("MTF", True, False),
    ]
    result = bt.StrategyEngine.ai_agent_decision(
        votes, True, True, True, True, False
    )
    assert isinstance(result, tuple) and len(result) == 5

def test_150x_risk_cap():
    cfg = dict(bt.DEFAULTS)
    cfg.update({"leverage": 150, "risk_pct": 1.0})
    checked = bt.validate_config(cfg)
    assert float(checked["risk_pct"]) <= 0.10

def test_synthetic_end_to_end():
    n = 700
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 0.08, n))
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": np.r_[close[0], close[:-1]],
        "high": close + 0.25,
        "low": close - 0.25,
        "close": close,
        "vol": np.full(n, 1000.0),
    })
    df["time"] = df["datetime"].astype("int64") // 10**6
    cfg = dict(bt.DEFAULTS)
    cfg.update({"signal_mode": "AI_AGENT", "use_atr": True, "use_atr_sl": True, "grid_mode": "OFF"})
    prepared = bt.build_strategy_columns(df, cfg)
    result = bt.run_backtest(prepared, cfg)
    assert isinstance(result, tuple) and len(result) == 4
