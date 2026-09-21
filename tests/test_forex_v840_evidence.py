from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
BOT=ROOT/"UniversalForexBot_V8_4_0_MT5_FOREX_EVIDENCE_HARDENED.py"
BT=ROOT/"UniversalForexBot_V8_4_0_MT5_FOREX_BACKTESTER_EVIDENCE.py"

def load(p,n):
    s=importlib.util.spec_from_file_location(n,str(p)); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
fx=load(BOT,"fx840")
bt=load(BT,"bt840")

def synthetic(n=2200):
    np.random.seed(7); t=pd.date_range("2026-01-01",periods=n,freq="15min",tz="UTC")
    r=np.random.normal(0,.0007,n)+.00002*np.sin(np.arange(n)/31); c=1.10*np.exp(np.cumsum(r)); o=np.r_[c[0],c[:-1]]
    h=np.maximum(o,c)*(1+np.random.rand(n)*.0008); l=np.minimum(o,c)*(1-np.random.rand(n)*.0008); v=np.random.lognormal(9,.25,n)
    return pd.DataFrame({"time":t.astype("int64")//10**6,"datetime":t,"open":o,"high":h,"low":l,"close":c,"vol":v})

def test_compile_import():
    compile(BOT.read_text(),str(BOT),"exec"); compile(BT.read_text(),str(BT),"exec")
    assert fx.APP_VERSION=="V8.4.0-FOREX-EVIDENCE-HARDENED"
    assert bt.APP_VERSION=="V8.4.0-FOREX-EVIDENCE-BT"

def test_family_contract():
    assert fx.StrategyEngine.EVIDENCE_FAMILIES["TREND"]==("ST","EMA","EMA_CROSS","MACD","VIDYA","NWE")
    assert fx.StrategyEngine.EVIDENCE_FAMILIES["MOMENTUM"]==("RSI","STOCH","DIVERGENCE")
    assert fx.StrategyEngine.EVIDENCE_FAMILIES["FLOW"]==("VWAP","VWAP_DELTA","VOL","VOL_SR")
    assert fx.StrategyEngine.EVIDENCE_FAMILIES["STRUCTURE"]==("LIQ_SWING","TRENDLINE","MTF")
    assert "ATR" not in sum(fx.StrategyEngine.EVIDENCE_FAMILIES.values(),())
    assert "ADX" not in sum(fx.StrategyEngine.EVIDENCE_FAMILIES.values(),())
    assert fx.DEFAULT_SIGNAL_MODE=="ADAPTIVE_EVIDENCE"

def test_no_regime_double_count():
    votes=[("ST",True,False),("EMA",True,False),("MTF",True,False),("ADX",True,False),("ATR",True,False),("VOL",True,False)]
    b,s,_,_=fx.StrategyEngine.decide_signal(votes,"ADAPTIVE_EVIDENCE",1,True,True,True,True,True,.18,3.5,2,.35,True,True)
    assert b is True and s is False
    # Remove FLOW/STRUCTURE evidence: Trend alone must not pass with the default two-family gate.
    votes2=[("ST",True,False),("EMA",True,False),("ADX",True,False),("ATR",True,False)]
    b2,s2,_,_=fx.StrategyEngine.decide_signal(votes2,"ADAPTIVE_EVIDENCE",1,True,True,True,True,True,.18,3.5,2,.35,True,True)
    assert b2 is False and s2 is False

def test_legacy_adaptive_parity():
    votes=[("ST",True,False),("EMA",True,False),("MTF",True,False),("VOL_SR",False,True)]
    a=fx.StrategyEngine.decide_signal(votes,"ADAPTIVE_SCORE",1,True,True,True,True,True,.18,3.5)
    b=bt.fx.StrategyEngine.decide_signal(votes,"ADAPTIVE_SCORE",1,True,True,True,True,True,.18,3.5)
    assert a==b

def test_full_strategy_frame():
    d=synthetic(1500); c=dict(bt.DEFAULTS); x=bt.build_frame(d,c)
    required=["trend","adx","ema","ema_fast","ema_slow","liq_swing_trend","trendline_state","div_bull_signal","div_bear_signal","sr_bull","sr_bear"]
    for k in required: assert k in x.columns,k
    assert len(x)==len(d)

def test_backtest():
    m=bt.backtest(synthetic(),dict(bt.DEFAULTS)); assert np.isfinite(m["ending_equity"]); assert np.isfinite(m["net_pnl"]); assert m["trades"]>=0

def test_hardening_contract():
    src=BOT.read_text(encoding="utf8")
    for needle in ["fx_reconcile_protection_mt5","fx_acquire_profile_lock","fx_persist_runtime_state","STALE MT5 MARKET DATA","with self.v2_guard_lock","NEWS FILTER FAIL-CLOSED"]: assert needle in src
    assert "fx_reconcile_noop" not in src
    assert src.rfind("UniversalFuturesBotGUI.build_exchange = v833_forex_build_exchange") < src.rfind('if __name__ == "__main__":')

if __name__=="__main__":
    tests=[v for k,v in globals().items() if k.startswith("test_")]
    for f in tests: f(); print("PASS",f.__name__)
    print(f"{len(tests)}/{len(tests)} PASS")