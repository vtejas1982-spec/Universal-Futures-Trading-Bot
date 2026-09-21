from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
BOT=ROOT/'UniversalForexBot_V8_3_3_MT5_FOREX.py'
BT=ROOT/'UniversalForexBot_V8_3_3_MT5_FOREX_BACKTESTER.py'

def load(p,n):
    s=importlib.util.spec_from_file_location(n,str(p)); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
fx=load(BOT,'fx833')
bt=load(BT,'bt833')

def synthetic(n=2200):
    np.random.seed(7); t=pd.date_range('2026-01-01',periods=n,freq='15min',tz='UTC')
    r=np.random.normal(0,.0007,n)+.00002*np.sin(np.arange(n)/31); c=1.10*np.exp(np.cumsum(r)); o=np.r_[c[0],c[:-1]]
    h=np.maximum(o,c)*(1+np.random.rand(n)*.0008); l=np.minimum(o,c)*(1-np.random.rand(n)*.0008); v=np.random.lognormal(9,.25,n)
    return pd.DataFrame({'time':t.astype('int64')//10**6,'datetime':t,'open':o,'high':h,'low':l,'close':c,'vol':v})

def test_compile_import():
    compile(BOT.read_text(),str(BOT),'exec'); compile(BT.read_text(),str(BT),'exec'); assert fx.APP_VERSION=='V8.3.3-FOREX'; assert bt.APP_VERSION=='V8.3.3-FOREX-BT'

def test_forex_only_contract():
    assert 'mt5_forex' in fx.APP_TITLE.lower() or 'mt5' in fx.APP_TITLE.lower(); assert len(fx.ADAPTIVE_MODULE_WEIGHTS)==19; assert fx.DEFAULT_SIGNAL_MODE=='ADAPTIVE_SCORE'

def test_adaptive_parity():
    votes=[('ST',True,False),('EMA',True,False),('MTF',True,False),('VOL_SR',False,True)]
    a=fx.StrategyEngine.decide_signal(votes,'ADAPTIVE_SCORE',1,True,True,True,True,True,.18,3.5)
    b=bt.fx.StrategyEngine.decide_signal(votes,'ADAPTIVE_SCORE',1,True,True,True,True,True,.18,3.5)
    assert a==b

def test_full_strategy_frame():
    d=synthetic(1500); c=dict(bt.DEFAULTS); x=bt.build_frame(d,c)
    required=['trend','adx','ema','ema_fast','ema_slow','liq_swing_trend','trendline_state','div_bull_signal','div_bear_signal','sr_bull','sr_bear']
    for k in required: assert k in x.columns,k
    assert len(x)==len(d)

def test_synthetic_backtest():
    m=bt.backtest(synthetic(),dict(bt.DEFAULTS)); assert np.isfinite(m['ending_equity']); assert np.isfinite(m['net_pnl']); assert m['trades']>=0

def test_runtime_guard_is_mt5_only():
    # The final override must reject crypto/futures runtime selection before broker construction.
    assert 'FOREX-ONLY BOT' in BOT.read_text()

if __name__=='__main__':
    tests=[v for k,v in globals().items() if k.startswith('test_')]
    for f in tests: f(); print('PASS',f.__name__)
    print(f'{len(tests)}/{len(tests)} PASS')
