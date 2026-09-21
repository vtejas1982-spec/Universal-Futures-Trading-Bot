from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent.parent
BOT = ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_EVIDENCE_HARDENED.py"
BT = ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_BACKTESTER_EVIDENCE.py"

def load(p, n):
    s = importlib.util.spec_from_file_location(n, str(p))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m

def test_versions():
    fx = load(BOT, "crypto840")
    bt = load(BT, "bt840")
    assert fx.APP_VERSION == "V8.4.0-CRYPTO-EVIDENCE-HARDENED"
    assert bt.APP_VERSION == "V8.4.0-CRYPTO-EVIDENCE-BT"

def test_evidence_families():
    fx = load(BOT, "crypto840")
    E = fx.StrategyEngine.EVIDENCE_FAMILIES
    assert E["TREND"] == ("ST","EMA","EMA_CROSS","MACD","VIDYA","NWE")
    assert E["MOMENTUM"] == ("RSI","STOCH","DIVERGENCE")
    assert E["FLOW"] == ("VWAP","VWAP_DELTA","VOL","VOL_SR")
    assert E["STRUCTURE"] == ("LIQ_SWING","TRENDLINE","MTF")
    assert "ATR" not in sum(E.values(), ())
    assert "ADX" not in sum(E.values(), ())

def test_regime_not_double_counted():
    fx = load(BOT, "crypto840")
    votes = [("ST",True,False),("EMA",True,False),("MTF",True,False),
             ("VOL",True,False),("ADX",True,False),("ATR",True,False)]
    buy, sell, *_ = fx.StrategyEngine.decide_signal(
        votes,"ADAPTIVE_EVIDENCE",1,True,True,True,True,True,
        .18,3.5,2,.35,True,True)
    assert buy and not sell

def test_trend_only_blocked():
    fx = load(BOT, "crypto840")
    votes = [("ST",True,False),("EMA",True,False),("ADX",True,False),("ATR",True,False)]
    buy, sell, *_ = fx.StrategyEngine.decide_signal(
        votes,"ADAPTIVE_EVIDENCE",1,True,True,True,True,True,
        .18,3.5,2,.35,True,True)
    assert not buy and not sell

if __name__ == "__main__":
    tests = [v for k,v in globals().items() if k.startswith("test_")]
    for fn in tests:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(tests)}/{len(tests)} PASS")
