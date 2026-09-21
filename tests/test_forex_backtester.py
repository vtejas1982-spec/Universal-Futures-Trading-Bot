import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
BT=ROOT/"UniversalForexBot_MT5_BACKTESTER.py"
sp=importlib.util.spec_from_file_location("fx_bt",str(BT)); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)

rng=np.random.default_rng(7)
n=700
r=.00005+.0008*rng.normal(size=n)
close=1.10*np.exp(np.cumsum(r))
open_=np.r_[close[0],close[:-1]]
high=np.maximum(open_,close)*(1+np.abs(rng.normal(0,.0005,n)))
low=np.minimum(open_,close)*(1-np.abs(rng.normal(0,.0005,n)))
dt=pd.date_range("2026-01-01",periods=n,freq="15min",tz="UTC")
df=pd.DataFrame({"time":dt.astype("int64")//10**6,"datetime":dt,"open":open_,"high":high,"low":low,"close":close,"vol":rng.uniform(100,1000,n)})

res=m.run_backtest(df,{"max_trades":5})
assert res["max_open_trades"]==1
assert res["starting_equity"]==m.DEFAULTS["capital"]
assert np.isfinite(res["ending_equity"])
print("FOREX R5 BACKTEST SMOKE: PASS",res)
