import ast
import py_compile
import re
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "UniversalFuturesBot_V8_2_MODULAR_ENGINE.py"

class V82StaticSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text, str(SOURCE))
        cls.cls = next(n for n in cls.tree.body if isinstance(n, ast.ClassDef) and n.name == "UniversalFuturesBotGUI")

    def test_python_compiles(self):
        py_compile.compile(str(SOURCE), doraise=True)

    def test_gui_setting_attributes_are_assigned(self):
        attrs = set(re.findall(r"self\.([ve]_[A-Za-z0-9_]+)", self.text))
        assigned = set()
        for n in ast.walk(self.cls):
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    for x in ast.walk(t):
                        if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "self":
                            assigned.add(x.attr)
        self.assertEqual(sorted(a for a in attrs if a not in assigned), [])

    def test_self_method_calls_resolve(self):
        methods = {n.name for n in self.cls.body if isinstance(n, ast.FunctionDef)}
        calls = {n.func.attr for n in ast.walk(self.cls)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"}
        self.assertEqual(sorted(calls - methods), [])

    def test_preflight_before_profile_lock(self):
        start = next(n for n in self.cls.body if isinstance(n, ast.FunctionDef) and n.name == "start_bot")
        calls = [(n.lineno, n.func.attr) for n in ast.walk(start)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"]
        pre = min(line for line,name in calls if name == "_validate_v82_preflight")
        lock = min(line for line,name in calls if name == "_acquire_profile_lock")
        self.assertLess(pre, lock)

    def test_version_schema_timeout(self):
        self.assertIn('APP_VERSION = "V8.2"', self.text)
        self.assertIn('"config_schema_version": 4', self.text)
        self.assertIn('"schema_version": 3', self.text)
        self.assertIn('"timeout": 20000', self.text)

    def test_completed_candle_contract(self):
        self.assertIn("closed_idx = -2", self.text)

    def test_grid_fail_closed(self):
        self.assertIn("GRID PROTECTION ERROR", self.text)
        self.assertIn("Failing closed and stopping Grid", self.text)

    def test_recovery_safety_contract(self):
        for token in ("_verify_resume_exchange_state", "_persist_runtime_state",
                      "Unprotected position", "MULTIPLE ACTIVE POSITIONS DETECTED"):
            self.assertIn(token, self.text)

if __name__ == "__main__":
    unittest.main()
