import ast
import re
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("UniversalFuturesBot_V8_RECOVERY_MULTI_BOT_AUDITED.py")
if not SOURCE.exists():
    SOURCE = Path(__file__).resolve().parents[1] / "UniversalFuturesBot_V8_RECOVERY_MULTI_BOT_AUDITED.py"

class V81StaticSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text, str(SOURCE))
        cls.cls = next(node for node in cls.tree.body if isinstance(node, ast.ClassDef) and node.name == "UniversalFuturesBotGUI")
        cls.methods = {node.name: node for node in cls.cls.body if isinstance(node, ast.FunctionDef)}

    def test_python_compiles(self):
        compile(self.text, str(SOURCE), "exec")

    def test_all_gui_setting_attributes_are_assigned(self):
        attrs = set(re.findall(r"self\.([ve]_[A-Za-z0-9_]+)", self.text))
        assigned = set()
        for node in ast.walk(self.cls):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for item in ast.walk(target):
                        if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == "self":
                            assigned.add(item.attr)
        self.assertEqual(sorted(a for a in attrs if a not in assigned), [])

    def test_self_method_calls_resolve(self):
        suspicious = []
        for node in ast.walk(self.cls):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                name = node.func.attr
                if name not in self.methods and not name.startswith(("v_", "e_")):
                    suspicious.append(name)
        self.assertEqual(sorted(set(suspicious)), [])

    def test_save_and_load_configuration_keys_match(self):
        save, load = self.methods["save_settings"], self.methods["load_settings"]
        save_keys = set()
        for node in ast.walk(save):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        save_keys.add(key.value)
        load_keys = set()
        for node in ast.walk(load):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and isinstance(node.func.value, ast.Name) and node.func.value.id == "cfg" and node.args and isinstance(node.args[0], ast.Constant):
                load_keys.add(node.args[0].value)
        load_keys |= {"grid_levels","grid_spacing","grid_order_size","grid_size_increase","grid_tp","grid_sl","grid_max_exposure","grid_max_dd","grid_score_min","grid_recenter_distance","grid_cooldown"}
        self.assertEqual(sorted(save_keys - load_keys), ["config_schema_version", "nwe_repaint"])
        self.assertEqual(sorted(load_keys - save_keys), [])

    def test_start_validates_credentials_before_profile_lock(self):
        start = self.methods["start_bot"]
        credential_lines = [node.lineno for node in ast.walk(start) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and isinstance(node.func.value, ast.Attribute) and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == "self" and node.func.value.attr in {"e_api_key","e_api_secret"}]
        lock_lines = [node.lineno for node in ast.walk(start) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self" and node.func.attr == "_acquire_profile_lock"]
        self.assertTrue(credential_lines); self.assertTrue(lock_lines); self.assertLess(max(credential_lines), min(lock_lines))

    def test_recovery_requires_saved_identity_and_protection(self):
        self.assertIn("does not contain a verifiable saved position identity", self.text)
        self.assertIn("live position has no saved protection state", self.text)
        self.assertIn("_reconcile_protection_orders(current_position)", self.text)

    def test_one_way_position_guard_exists(self):
        self.assertIn("MULTIPLE ACTIVE POSITIONS DETECTED", self.text)
        self.assertIn("requires one-way/single-position mode", self.text)

    def test_trendline_buffer_is_bounded(self):
        self.assertIn("trendline_buffer < 0 or trendline_buffer >= 100", self.text)

    def test_runtime_config_schema_is_versioned(self):
        self.assertIn('"config_schema_version": 3', self.text)

    def test_signal_decision_helper(self):
        method_node = next(node for node in self.cls.body if isinstance(node, ast.FunctionDef) and node.name == "_decide_signal")
        module = ast.Module(body=[method_node], type_ignores=[]); ast.fix_missing_locations(module); namespace = {}
        exec(compile(module, str(SOURCE), "exec"), namespace)
        decide = namespace["_decide_signal"]; dummy = object.__new__(type("Dummy", (), {}))
        buy, sell, bs, ss = decide(dummy, [("ST",True,False),("EMA",True,False),("RSI",False,True)], "2_SIGNALS", 2)
        self.assertTrue(buy); self.assertFalse(sell); self.assertEqual((bs,ss),(2,1))
        buy, sell, _, _ = decide(dummy, [("ST",True,False),("EMA",True,False)], "STRICT_ALL_FILTERS", 1, atr_pass=False)
        self.assertFalse(buy); self.assertFalse(sell)
        buy, sell, _, _ = decide(dummy, [("ST",True,False),("EMA",False,True)], "SINGLE_SIGNAL", 1)
        self.assertTrue(buy); self.assertFalse(sell)
        with self.assertRaises(ValueError): decide(dummy, [], "BAD_MODE", 1)

if __name__ == "__main__":
    unittest.main()
