"""V8.2.4 static/regression tests for the audited Universal Futures Bot."""
from pathlib import Path
import ast
import re
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "UniversalFuturesBot_V8_2_4_AUDITED_STRATEGY_ENGINE.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)

def strategy_engine_class():
    for node in TREE.body:
        if isinstance(node, ast.ClassDef) and node.name == "StrategyEngine":
            module = ast.Module(body=[node], type_ignores=[])
            namespace = {}
            exec(compile(module, str(SOURCE), "exec"), namespace)
            return namespace["StrategyEngine"]
    raise AssertionError("StrategyEngine class not found")

class V824AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = strategy_engine_class()

    def test_source_compiles(self):
        compile(TEXT, str(SOURCE), "exec")

    def test_supported_signal_contract_contains_new_mode(self):
        self.assertIn("ANY_NON_CONFLICTING", TEXT)
        self.assertIn("CONFIG_SCHEMA_VERSION = 5", TEXT)

    def test_two_signals_require_two_same_direction_votes(self):
        self.assertEqual(self.engine.decide_signal(
            [("EMA_CROSS", True, False), ("VWAP_DELTA", True, False)],
            "2_SIGNALS", 2), (True, False, 2, 0))

    def test_two_signals_block_conflict(self):
        self.assertEqual(self.engine.decide_signal(
            [("EMA_CROSS", True, False), ("VWAP_DELTA", False, True)],
            "2_SIGNALS", 2), (False, False, 1, 1))

    def test_any_non_conflicting_allows_one_direction(self):
        self.assertEqual(self.engine.decide_signal(
            [("EMA_CROSS", True, False)],
            "ANY_NON_CONFLICTING", 1), (True, False, 1, 0))

    def test_any_non_conflicting_blocks_opposite_votes(self):
        self.assertEqual(self.engine.decide_signal(
            [("EMA_CROSS", True, False), ("VWAP_DELTA", False, True)],
            "ANY_NON_CONFLICTING", 1), (False, False, 1, 1))

    def test_three_signals_cannot_trade_with_only_two_votes(self):
        self.assertEqual(self.engine.decide_signal(
            [("A", True, False), ("B", True, False)],
            "3_SIGNALS", 3), (False, False, 2, 0))

    def test_decision_reason_exposes_conflict(self):
        reason = self.engine.decision_reason(
            [("EMA_CROSS", True, False), ("VWAP_DELTA", False, True)],
            "2_SIGNALS", 2)
        self.assertIn("CONFLICTING", reason)

    def test_gui_attributes_have_no_missing_self_references(self):
        assigned, loaded = set(), set()
        for node in ast.walk(TREE):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
                (assigned if isinstance(node.ctx, ast.Store) else loaded).add(node.attr)
        self.assertEqual([
            n for n in loaded if n.startswith(("v_", "e_", "lbl_")) and n not in assigned
        ], [])

    def test_no_worker_stop_bot_call_remains(self):
        self.assertNotIn("self.stop_bot()", TEXT)

    def test_save_load_entry_variable_coverage(self):
        funcs = {node.name: node for node in ast.walk(TREE) if isinstance(node, ast.FunctionDef)}
        save = ast.get_source_segment(TEXT, funcs["save_settings"])
        load = ast.get_source_segment(TEXT, funcs["load_settings"])
        save_attrs = set(re.findall(r"self\.((?:e_|v_)\w+)", save))
        load_attrs = set(re.findall(r"self\.((?:e_|v_)\w+)", load))
        self.assertEqual(save_attrs - load_attrs, set())
        self.assertEqual(load_attrs - save_attrs, {"v_nwe_repaint"})

    def test_strategy_engine_has_no_duplicate_methods(self):
        for cls in [n for n in TREE.body if isinstance(n, ast.ClassDef)]:
            names = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
            self.assertEqual({x for x in names if names.count(x) > 1}, set(), cls.name)

if __name__ == "__main__":
    unittest.main(verbosity=2)
