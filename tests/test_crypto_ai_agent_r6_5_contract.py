import ast
from pathlib import Path
import re

SOURCE = Path(__file__).resolve().parents[1] / "UniversalFuturesBot_CRYPTO_AI_AGENT_R4.py"

def source():
    return SOURCE.read_text(encoding="utf-8")

def gui_methods(tree):
    cls = next(c for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and c.name == "UniversalFuturesBotGUI")
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}

def worker_reachable_methods(methods):
    calls = {name:set() for name in methods}
    for name,node in methods.items():
        for x in ast.walk(node):
            if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and isinstance(x.func.value,ast.Name) and x.func.value.id=="self":
                calls[name].add(x.func.attr)
    out=set(); stack=["_run_bot_logic"]
    while stack:
        name=stack.pop()
        if name in out: continue
        out.add(name); stack.extend(calls.get(name,()))
    return out

def test_version_and_runtime_schema():
    s=source()
    assert 'APP_VERSION = "V8.4.2-CRYPTO-AI-AGENT-R6.5"' in s
    assert "RUNTIME_SCHEMA_VERSION = 22" in s

def test_strategy_engine_keyword_contract():
    tree=ast.parse(source())
    sigs={}
    for n in ast.walk(tree):
        if isinstance(n,ast.FunctionDef) and n.name in {"ai_agent_decision","decide_signal","decision_reason"}:
            sigs[n.name]={a.arg for a in n.args.posonlyargs+n.args.args+n.args.kwonlyargs}
    for n in ast.walk(tree):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=="StrategyEngine" and n.func.attr in sigs:
            bad=[k.arg for k in n.keywords if k.arg and k.arg not in sigs[n.func.attr]]
            assert not bad,(n.lineno,n.func.attr,bad)

def test_worker_has_no_direct_tk_access():
    tree=ast.parse(source())
    methods=gui_methods(tree)
    reachable=worker_reachable_methods(methods)
    bad_gui=[]; bad_after=[]
    for name in reachable:
        node=methods.get(name)
        if not node: continue
        for x in ast.walk(node):
            if isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name) and x.value.id=="self" and re.match(r"^[ve]_",x.attr):
                bad_gui.append((name,x.lineno,x.attr))
            if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=="after" and isinstance(x.func.value,ast.Attribute) and isinstance(x.func.value.value,ast.Name) and x.func.value.value.id=="self" and x.func.value.attr=="root":
                bad_after.append((name,x.lineno))
    assert not bad_gui,bad_gui
    assert [x for x in bad_after if x[0]!="log"]==[]

def test_tp_split_metadata_present():
    s=source()
    for key in ('"tp1_qty":','"tp2_qty":','"tp_qty_mode":','"tp1_close_value":','"tp2_close_value":'):
        assert key in s

def test_migration_persistence_present():
    s=source()
    assert 'migrated_cfg["config_schema_version"] = CONFIG_SCHEMA_VERSION' in s
    assert "CONFIG MIGRATION COMPLETE:" in s
