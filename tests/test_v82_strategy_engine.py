import ast
import pathlib
import unittest

BOT = pathlib.Path(__file__).resolve().parents[1] / "UniversalFuturesBot_V8_2_MODULAR_ENGINE.py"
TREE = ast.parse(BOT.read_text(encoding="utf-8"))

def load_engine():
    node = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "StrategyEngine")
    ns = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(BOT), "exec"), ns)
    return ns["StrategyEngine"]

class StrategyEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Engine = load_engine()

    def test_score_long(self):
        self.assertEqual(self.Engine.decide_signal(
            [("ST", True, False), ("EMA", True, False), ("RSI", False, True)], "SCORE", 2),
            (True, False, 2, 1))

    def test_score_short(self):
        self.assertEqual(self.Engine.decide_signal(
            [("ST", False, True), ("EMA", False, True), ("RSI", True, False)], "SCORE", 2),
            (False, True, 1, 2))

    def test_tie_is_neutral(self):
        self.assertEqual(self.Engine.decide_signal(
            [("A", True, False), ("B", False, True)], "SCORE", 1)[:2], (False, False))

    def test_single_signal_ignores_ambiguous_vote(self):
        self.assertEqual(self.Engine.decide_signal(
            [("A", True, True), ("B", False, True)], "SINGLE_SIGNAL", 1)[:2], (False, True))

    def test_strict_all_filters(self):
        self.assertEqual(self.Engine.decide_signal(
            [("A", True, False), ("B", True, False)], "STRICT_ALL_FILTERS", 1,
            atr_pass=True, vol_pass=True, adx_pass=True, mtf_pass_bull=True)[:2], (True, False))

    def test_invalid_score_rejected(self):
        with self.assertRaises(ValueError):
            self.Engine.decide_signal([("A", True, False)], "SCORE", 0)

if __name__ == "__main__":
    unittest.main()
