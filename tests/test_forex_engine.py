import ast
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
LIVE=ROOT/"UniversalForexBot_MT5.py"
BT=ROOT/"UniversalForexBot_MT5_BACKTESTER.py"

def load(p,n):
    sp=importlib.util.spec_from_file_location(n,str(p)); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m

def data(n=700):
    rng=np.random.default_rng(42); r=.0001+.001*rng.normal(size=n)
    close=1.1*np.exp(np.cumsum(r)); op=np.r_[close[0],close[:-1]]
    dt=pd.date_range("2026-01-01",periods=n,freq="15min",tz="UTC")
    return pd.DataFrame({"time":dt.astype("int64")//10**6,"datetime":dt,"open":op,
        "high":np.maximum(op,close)*1.0008,"low":np.minimum(op,close)*.9992,
        "close":close,"vol":rng.integers(100,1000,n)})

def run():
    fx=load(LIVE,"fx"); bt=load(BT,"bt")
    src=LIVE.read_text()
    checks=[
      fx.APP_VERSION=="V8.4.2-FOREX-EVIDENCE-HARDENED-R5",
      fx.CONFIG_SCHEMA_VERSION==9,
      "ADAPTIVE_EVIDENCE" in fx.SUPPORTED_SIGNAL_MODES,
      "max_open_trades" in src and "atr_tp1_mult" in src and "atr_tp2_mult" in src,
      "ATR DYNAMIC" in src and "completed-candle ATR" in src,
      fx.StrategyEngine.decide_signal([("EMA",True,False),("VWAP",False,True)],"SINGLE_SIGNAL",1)[:2]==(False,False),
      "UniversalForexBot_MT5.py" in BT.read_text(),
      bt.DEFAULTS["max_open_trades"]==1,
      bt.DEFAULTS["atr_tp1_mult"]==1.2 and bt.DEFAULTS["atr_tp2_mult"]==2.2,
      isinstance(bt.run_backtest(data(),{"max_trades":3}),dict)
    ]
    print(f"FOREX V8.4.2-R5 AUDIT: {sum(checks)}/{len(checks)} PASS")
    if not all(checks): raise SystemExit(1)

if __name__=="__main__": run()
