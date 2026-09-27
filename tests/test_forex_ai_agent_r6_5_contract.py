"""Forex MT5 AI-Agent R6.5 contract regression tests."""
import ast
import py_compile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOREX=ROOT/"UniversalForexBot_MT5.py"
CRYPTO=ROOT/"UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5.py"
BACKTESTER=ROOT/"UniversalForexBot_MT5_BACKTESTER.py"

def tree(p):
    return ast.parse(p.read_text(encoding="utf-8"))

def cls(t,name):
    return next(x for x in t.body if isinstance(x,ast.ClassDef) and x.name==name)

def meth(c,name):
    return next(x for x in c.body if isinstance(x,ast.FunctionDef) and x.name==name)

def test_compile():
    for p in (FOREX,CRYPTO,BACKTESTER):
        py_compile.compile(str(p),cfile=f"/tmp/{p.stem}_r65.pyc",doraise=True)

def test_strategy_engine_parity():
    fx=cls(tree(FOREX),"StrategyEngine")
    cr=cls(tree(CRYPTO),"StrategyEngine")
    for name in ("_family_name","evidence_summary","ai_agent_decision","decide_signal","decision_reason"):
        assert ast.dump(meth(fx,name),include_attributes=False)==ast.dump(meth(cr,name),include_attributes=False), name

def test_forex_r65_contract():
    s=FOREX.read_text(encoding="utf-8")
    required=(
      'APP_VERSION = "V8.4.2-FOREX-AI-AGENT-R6.5"',
      'AI_AGENT_PRESET_NAME = "AI_AGENT_RECOMMENDED_R6.5"',
      "AI_AGENT_DYNAMIC_MANAGEMENT_ENABLED = True",
      "AI_AGENT_MIN_RISK_PCT = 0.20","AI_AGENT_MAX_RISK_PCT = 0.50",
      "AI_AGENT_MIN_ATR_SL_MULT = 1.50","AI_AGENT_MAX_ATR_SL_MULT = 2.40",
      "AI_AGENT_MIN_TP1_R_MULT = 1.00","AI_AGENT_MAX_TP1_R_MULT = 1.50",
      "AI_AGENT_MIN_TP2_R_MULT = 2.00","AI_AGENT_MAX_TP2_R_MULT = 3.00",
      "command=self._on_signal_mode_selected",
      "self.v_grid_mode","self.v_liq_entry_mode","self.e_div_min_count","self.v_div_entry_mode",
      "Dynamic AI SL preserved","ForexGuiCloseWorker")
    for marker in required: assert marker in s, marker

def test_runtime_bindings():
    t=tree(FOREX)
    defined={x.name for x in t.body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
    missing=[]
    for n in ast.walk(t):
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Attribute) and isinstance(n.targets[0].value,ast.Name) and n.targets[0].value.id=="UniversalFuturesBotGUI" and isinstance(n.value,ast.Name):
            if n.value.id not in defined: missing.append(n.value.id)
    assert not missing, missing

def test_backtester_uses_live_engine():
    s=BACKTESTER.read_text(encoding="utf-8")
    for marker in ("LIVE_FILE = ROOT / \"UniversalForexBot_MT5.py\"","LIVE.UniversalFuturesBotGUI._ai_agent_trade_management","LIVE.StrategyEngine.decide_signal"):
        assert marker in s, marker

if __name__=="__main__":
    for f in (test_compile,test_strategy_engine_parity,test_forex_r65_contract,test_runtime_bindings,test_backtester_uses_live_engine):
        f()
        print(f.__name__+": PASS")
    print("ALL FOREX R6.5 CONTRACT TESTS: PASS")
