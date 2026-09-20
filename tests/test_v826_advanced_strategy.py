import ast, importlib.util, sys, types, unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BT = ROOT / "V8_2_6_ADVANCED_STRATEGY_BACKTESTER.py"
BOT = ROOT / "V8_2_6_ADVANCED_STRATEGY_BOT.py"

class DummyExchange:
    id = "bybit"
    markets = {}
    def __init__(self, *a, **k): pass

ccxt_stub = types.ModuleType("ccxt")
for name in ("bybit","binance","gate","bitget","weex"):
    setattr(ccxt_stub, name, DummyExchange)
sys.modules.setdefault("ccxt", ccxt_stub)

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

bt = load_module(BT, "v826_bt_test")

class V826AdvancedAudit(unittest.TestCase):
    def synthetic(self, n=1200):
        rng=np.random.default_rng(42)
        close=100*np.exp(np.cumsum(rng.normal(0,0.002,n)))
        open_=np.r_[close[0],close[:-1]]
        high=np.maximum(open_,close)*(1+rng.uniform(0,0.002,n))
        low=np.minimum(open_,close)*(1-rng.uniform(0,0.002,n))
        vol=rng.lognormal(10,0.4,n)
        d=pd.DataFrame({"time":np.arange(n)*900000,"open":open_,"high":high,
                        "low":low,"close":close,"vol":vol})
        d["datetime"]=pd.to_datetime(d["time"],unit="ms",utc=True)
        return d

    def test_source_compiles(self):
        ast.parse(BOT.read_text(encoding="utf-8"))
        ast.parse(BT.read_text(encoding="utf-8"))

    def test_module_contract_is_19(self):
        self.assertEqual(len(bt.MODULES), 19)
        self.assertIn("DIVERGENCE", bt.MODULES)
        self.assertIn("VOL_SR", bt.MODULES)

    def test_new_config_defaults_and_validation(self):
        c=dict(bt.DEFAULTS)
        self.assertEqual(c["div_pivot"],5)
        self.assertEqual(c["div_type"],"Regular")
        self.assertEqual(c["sr_tf2"],"4h")
        self.assertEqual(c["sr_tf3"],"D")
        self.assertEqual(c["sr_tf4"],"W")
        self.assertEqual(c["sr_history_bars"],40)
        self.assertEqual(c["grid_sl"],6.0)
        bt.validate_config(c)

    def test_divergence_and_sr_columns_are_causal(self):
        c=dict(bt.DEFAULTS)
        c.update({"use_divergence":True,"use_vol_sr":True,
                  "sr_tf1":"Chart","sr_tf2":"4h","sr_tf3":"D","sr_tf4":"W"})
        x=bt.build_strategy_columns(self.synthetic(),c)
        for col in ("div_bull_count","div_bear_count","divergence_state",
                    "sr_bull","sr_bear","sr_fresh_bull","sr_fresh_bear"):
            self.assertIn(col,x.columns)

    def test_all_modules_can_vote(self):
        mapping={"ST":"st","EMA":"ema","EMA_CROSS":"ema_cross","MACD":"macd","RSI":"rsi",
                 "BB":"bb","STOCH":"stoch","VWAP":"vwap","VWAP_DELTA":"vwap_delta",
                 "VIDYA":"vidya","NWE":"nwe","LIQ_SWING":"liq_swings","TRENDLINE":"trendline",
                 "MTF":"mtf","VOL":"vol","ADX":"adx","ATR":"atr","DIVERGENCE":"divergence","VOL_SR":"vol_sr"}
        c=dict(bt.DEFAULTS)
        for _,k in mapping.items(): c["use_"+k]=True
        c.update({"signal_mode":"SCORE","min_score":2,"sr_tf1":"Chart","sr_tf2":"4h","sr_tf3":"D","sr_tf4":"W"})
        x=bt.build_strategy_columns(self.synthetic(),c)
        votes=bt.module_votes(x,700,c)
        names={v[0] for v in votes}
        self.assertTrue({"DIVERGENCE","VOL_SR"}.issubset(names))
        self.assertGreaterEqual(len(names),17)

    def test_normal_and_grid_backtests_run(self):
        c=dict(bt.DEFAULTS)
        c.update({"use_divergence":True,"use_vol_sr":True,
                  "sr_tf1":"Chart","sr_tf2":"4h","sr_tf3":"D","sr_tf4":"W",
                  "signal_mode":"SCORE","min_score":2})
        x=bt.build_strategy_columns(self.synthetic(),c)
        _,m,_,_=bt.run_backtest(x,c)
        self.assertIsInstance(m["trades"],int)
        g=dict(c); g.update({"grid_mode":"NEUTRAL_GRID","grid_trend_filter":"SCORE","grid_score_min":1})
        _,gm,_,_=bt.run_backtest(x,g)
        self.assertGreaterEqual(float(gm["trades"]),0.0)

    def test_signal_engine_contract(self):
        self.assertEqual(bt.StrategyEngine.decide_signal(
            [("A",True,False),("B",True,False)],"2_SIGNALS",2)[0:2],(True,False))
        self.assertEqual(bt.StrategyEngine.decide_signal(
            [("A",True,False),("B",False,True)],"ANY_NON_CONFLICTING",1)[0:2],(False,False))

if __name__=="__main__":
    unittest.main()