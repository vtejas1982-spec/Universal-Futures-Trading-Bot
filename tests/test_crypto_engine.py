import ast, importlib.util, sys, types
from pathlib import Path
import numpy as np, pandas as pd

ROOT=Path(__file__).resolve().parents[1]
LIVE=ROOT/"UniversalFuturesBot_CRYPTO.py"
BT=ROOT/"UniversalFuturesBot_CRYPTO_BACKTESTER.py"

def load(path,name):
    try:
        spec=importlib.util.spec_from_file_location(name,str(path)); m=importlib.util.module_from_spec(spec); sys.modules[name]=m; spec.loader.exec_module(m); return m
    except ModuleNotFoundError as e:
        if e.name!="ccxt": raise
        stub=types.ModuleType("ccxt"); stub.Exchange=type("Exchange",(),{})
        for n in ("bybit","binance","gateio"): setattr(stub,n,type(n,(),{}))
        sys.modules["ccxt"]=stub
        spec=importlib.util.spec_from_file_location(name,str(path)); m=importlib.util.module_from_spec(spec); sys.modules[name]=m; spec.loader.exec_module(m); return m

def synthetic(n=1200):
    rng=np.random.default_rng(42); ret=.00015+.003*rng.normal(size=n); close=100*np.exp(np.cumsum(ret)); op=np.r_[close[0],close[:-1]]
    dt=pd.date_range("2026-01-01",periods=n,freq="15min",tz="UTC")
    return pd.DataFrame({"time":dt.astype("int64")//10**6,"datetime":dt,"open":op,"high":np.maximum(op,close)*1.001,"low":np.minimum(op,close)*.999,"close":close,"vol":rng.integers(100,2000,n)})

def main():
    s=LIVE.read_text(encoding="utf-8"); b=BT.read_text(encoding="utf-8")
    ast.parse(s); ast.parse(b); fx=load(LIVE,"crypto_r5_live"); bt=load(BT,"crypto_r5_bt")
    checks=[
        fx.APP_VERSION.endswith("R5"), fx.AUDIT_BUILD.endswith("R5"), fx.CONFIG_SCHEMA_VERSION==9,
        "evidence_min_families = int" in s, "evidence_family_min_score = float" in s,
        "Normalizing to 1." in s, "ATR SL Multiplier must be > 0 and <= 10." in s,
        "def run_backtest" in b, "atr_sl_mult" in b, "atr_tp1_mult" in b, "atr_tp2_mult" in b,
        fx.StrategyEngine.decide_signal([("A",True,False),("B",False,True)],"SINGLE_SIGNAL",1)[:2]==(False,False)
    ]
    c=bt.DEFAULTS
    checks += [c["signal_mode"]=="ADAPTIVE_EVIDENCE",c["evidence_min_families"]==2,c["evidence_family_min_score"]==.35,
               c["use_atr_sl"] is True,c["atr_sl_mult"]==1.5,c["atr_tp1_mult"]==1.2,c["atr_tp2_mult"]==2.2,c["max_open_trades"]==1]
    r=bt.run_backtest(bt.load_ohlcv(synthetic()),dict(c))
    checks += [isinstance(r,tuple) and len(r)==4]
    print(f"CRYPTO V8.4.2-R5 AUDIT: {sum(checks)}/{len(checks)} PASS")
    if not all(checks): raise SystemExit(1)

if __name__=="__main__": main()
