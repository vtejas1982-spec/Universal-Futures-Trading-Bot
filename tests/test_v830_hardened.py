import importlib.util
import sys
import types
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BOT = ROOT / 'V8_3_HARDENED_ADAPTIVE_BOT.py'
BT = ROOT / 'V8_3_HARDENED_ADAPTIVE_BACKTESTER.py'

cc = types.ModuleType('ccxt')
cc.__getattr__ = lambda name: type(name, (), {})
sys.modules['ccxt'] = cc

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_compile():
    import py_compile
    py_compile.compile(str(BOT), doraise=True)
    py_compile.compile(str(BT), doraise=True)

def test_contracts():
    bot = load(BOT, 'v830_bot_contract')
    bt = load(BT, 'v830_bt_contract')
    assert bot.CONFIG_SCHEMA_VERSION == 7
    assert bot.RUNTIME_SCHEMA_VERSION == 4
    assert 'ADAPTIVE_SCORE' in bot.SUPPORTED_SIGNAL_MODES
    assert 'ADAPTIVE_SCORE' in bt.SUPPORTED_SIGNAL_MODES
    assert len(bt.MODULES) == 19
    assert bot.StrategyEngine.adaptive_edge == bot.ADAPTIVE_DEFAULT_EDGE

def test_adaptive_parity():
    bot = load(BOT, 'v830_bot_adaptive')
    bt = load(BT, 'v830_bt_adaptive')
    bot.StrategyEngine.adaptive_edge = 0.18
    bot.StrategyEngine.adaptive_min_weight = 3.5
    bt.cfg_adaptive_edge = 0.18
    bt.cfg_adaptive_min_weight = 3.5
    votes = [
        ('ST', True, False), ('EMA', True, False), ('MTF', True, False),
        ('MACD', True, False), ('RSI', False, True), ('VOL_SR', True, False),
    ]
    a = bot.StrategyEngine.decide_signal(votes, 'ADAPTIVE_SCORE', 1, True, True, True, True, False)
    b = bt.StrategyEngine.decide_signal(votes, 'ADAPTIVE_SCORE', 1, True, True, True, True, False)
    assert a == b
    assert a[0] and not a[1]

def test_backtest_smoke():
    bt = load(BT, 'v830_bt_smoke')
    n = 700
    rng = np.random.default_rng(830)
    close = 100 * np.exp(np.cumsum(0.0002 + rng.normal(0, 0.004, n)))
    open_ = np.r_[100.0, close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, .003, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, .003, n))
    vol = rng.lognormal(10, .25, n)
    df = pd.DataFrame({'time': np.arange(n)*900000, 'open': open_, 'high': high, 'low': low, 'close': close, 'vol': vol})
    df['datetime'] = pd.to_datetime(df.time, unit='ms', utc=True)
    cfg = bt.validate_config(dict(bt.DEFAULTS, use_mtf=False, signal_mode='ADAPTIVE_SCORE',
                                  adaptive_edge=.18, adaptive_min_weight=3.5,
                                  grid_mode='OFF', max_trades=0, warmup=250))
    x = bt.build_strategy_columns(df, cfg)
    trades, metrics, equity, events = bt.run_backtest(x, cfg)
    assert len(x) == n
    assert isinstance(metrics, dict)
    assert 'net_pnl' in metrics and 'max_drawdown' in metrics

def test_safety_contracts_static():
    s = BOT.read_text(encoding='utf-8')
    assert 'BOT_SYMBOL' in s
    assert 'ALL_ACCOUNT' in s
    assert 'MAX_CONSECUTIVE_CYCLE_ERRORS = 3' in s
    assert 'STALE_MARKET_DATA' in s
    assert 'daily_peak_equity' in s
    assert '_cancel_known_managed_orders' in s

if __name__ == '__main__':
    tests = [test_compile, test_contracts, test_adaptive_parity, test_backtest_smoke, test_safety_contracts_static]
    for t in tests:
        t(); print('PASS', t.__name__)
    print('5/5 PASS')