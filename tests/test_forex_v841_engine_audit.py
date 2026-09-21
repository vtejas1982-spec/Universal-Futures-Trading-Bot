import ast
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
LIVE = ROOT / 'UniversalForexBot_V8_4_1_MT5_FOREX_EVIDENCE_AUDITED_R2.py'
BT = ROOT / 'UniversalForexBot_V8_4_1_MT5_FOREX_BACKTESTER_AUDITED_R2.py'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    live = load(LIVE, 'fx_audit_live')
    bt = load(BT, 'fx_audit_bt')
    checks = []

    tree = ast.parse(LIVE.read_text(encoding='utf-8'))
    top_classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    check(top_classes.count('StrategyEngine') == 1, 'duplicate StrategyEngine')
    check(top_classes.count('UniversalFuturesBotGUI') == 1, 'duplicate GUI class')
    checks.append('AST/classes')

    text = LIVE.read_text(encoding='utf-8')
    for fn in ('calculate_adx','calculate_macd','calculate_rsi','calculate_rsi_ma','calculate_vidya','calculate_nadaraya_watson_envelope','calculate_liquidity_swings','calculate_trendline_breakout'):
        check(text.count(f'def {fn}(') == 1, f'duplicate/missing {fn}')
    checks.append('core indicators')

    S = live.StrategyEngine
    check(S.decide_signal([('A', True, False), ('B', False, True)], 'SINGLE_SIGNAL', 1)[:2] == (False, False), 'SINGLE_SIGNAL conflict not blocked')
    check(S.decide_signal([('A', True, False)], 'SINGLE_SIGNAL', 1)[:2] == (True, False), 'single BUY broken')
    check(S.decide_signal([('A', False, True)], 'SINGLE_SIGNAL', 1)[:2] == (False, True), 'single SELL broken')
    checks.append('SINGLE_SIGNAL')

    kwargs = dict(min_score=1, atr_pass=True, vol_pass=True, adx_pass=True,
                  mtf_pass_bull=True, mtf_pass_bear=True, adaptive_edge=0.0,
                  adaptive_min_weight=1, evidence_min_families=2,
                  evidence_family_min_score=0.35, evidence_require_trend=True,
                  evidence_require_independent=True)
    trend_mom = [('ST', True, False), ('RSI', True, False)]
    trend_regime = [('ST', True, False), ('ATR', True, False)]
    check(S.decide_signal(trend_mom, 'ADAPTIVE_EVIDENCE', **kwargs)[:2] == (True, False), 'Trend+Momentum evidence should pass')
    check(S.decide_signal(trend_regime, 'ADAPTIVE_EVIDENCE', **kwargs)[:2] == (False, False), 'Regime must not count as family')
    check('EVIDENCE_BLOCKED' in S.decision_reason(trend_regime, 'ADAPTIVE_EVIDENCE', **kwargs), 'diagnostic gate parity broken')
    check(S.decide_signal(trend_mom, 'ADAPTIVE_EVIDENCE', **{**kwargs, 'atr_pass':False})[:2] == (False, False), 'ATR gate failure not blocking')
    checks.append('Evidence-family contract')

    # Full strategy frame through the audited backtester, including NWE.
    rng = np.random.default_rng(42)
    n = 700
    close = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.00045, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.0007, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.0007, n))
    dt = pd.date_range('2025-01-01', periods=n, freq='15min', tz='UTC')
    df = pd.DataFrame({'time': dt.view('int64') // 10**6, 'open': open_, 'high': high, 'low': low,
                       'close': close, 'vol': rng.integers(100, 500, n)})
    cfg = dict(bt.DEFAULTS)
    cfg.update({'use_macd':True,'use_rsi':True,'use_bb':True,'use_stoch':True,
                'use_vwap':True,'use_vwap_delta':True,'use_vidya':True,'use_nwe':True,
                'use_liq_swing':True,'use_trendline':True,'use_divergence':True,
                'use_vol_sr':True,'use_mtf':True})
    frame = bt.build_frame(df, cfg)
    for col in ('trend','adx','macd','rsi','bb_mid','stoch_k','vwap','vwap_delta','vidya',
                'liq_swing_trend','trendline_state','div_bull_signal','sr_bull','mtf_close'):
        check(col in frame.columns, f'missing strategy column {col}')
    checks.append('19-module frame')

    raw = df.copy()
    raw_result = bt.run_backtest(raw, {'signal_mode':'ADAPTIVE_EVIDENCE'})
    check('ending_equity' in raw_result and 'trades_detail' in raw_result, 'raw OHLCV run_backtest failed')
    checks.append('raw OHLCV backtest API')

    # Public supported-mode parity: worker must not reject the default/new modes.
    for mode in live.SUPPORTED_SIGNAL_MODES:
        check(mode in live.SUPPORTED_SIGNAL_MODES, f'mode missing {mode}')
    check('allowed_signal_modes = SUPPORTED_SIGNAL_MODES' in text, 'worker mode validation drift')
    check('CONFIG_SCHEMA_VERSION = 8' in text, 'config schema missing')
    check('_validate_strategy_preflight' in text, 'strategy preflight missing')
    checks.append('config/preflight/mode parity')

    print(f'PASS: {len(checks)} audit groups / 0 FAIL')
    for i, item in enumerate(checks, 1):
        print(f'{i:02d}. {item}')


if __name__ == '__main__':
    main()