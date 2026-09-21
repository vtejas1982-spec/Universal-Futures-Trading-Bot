import ast
import pathlib
import py_compile

ROOT = pathlib.Path(__file__).resolve().parents[1]

FILES = [
    ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_EVIDENCE_HARDENED.py",
    ROOT / "UniversalFuturesBot_V8_RECOVERY_MULTI_BOT_AUDITED.py",
    ROOT / "UniversalFuturesBot_V8_4_0_CRYPTO_BACKTESTER_EVIDENCE.py",
]

def test_all_crypto_sources_compile():
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        py_compile.compile(str(path), doraise=True)

def test_live_engine_has_single_gui_definition():
    source = FILES[0].read_text(encoding="utf-8")
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "UniversalFuturesBotGUI"]
    assert len(classes) == 1

def test_live_engine_has_no_duplicate_top_level_functions():
    source = FILES[0].read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert len(names) == len(set(names))

def test_live_evidence_settings_are_persisted():
    source = FILES[0].read_text(encoding="utf-8")
    for key in ("evidence_min_families", "evidence_family_min_score", "evidence_require_trend", "evidence_require_independent"):
        assert key in source
