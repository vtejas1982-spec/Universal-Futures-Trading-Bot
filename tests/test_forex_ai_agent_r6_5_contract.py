from __future__ import annotations

import ast
import importlib.util
import math
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOREX = HERE / "UniversalForexBot_MT5.py"
CRYPTO = HERE / "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5(2).py"
BACKTESTER = HERE / "UniversalForexBot_MT5_BACKTESTER.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def class_node(source: str, name: str):
    tree = ast.parse(source)
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name), tree


class ForexR65ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx_source = FOREX.read_text(encoding="utf-8")
        cls.cr_source = CRYPTO.read_text(encoding="utf-8")
        cls.fx = load_module(FOREX, "fx_r65_test")
        cls.bt = load_module(BACKTESTER, "fx_r65_bt_test")

    def test_compile_import_version(self):
        self.assertEqual(self.fx.APP_VERSION, "V8.4.2-FOREX-AI-AGENT-R6.5")
        self.assertIn("AI_AGENT", self.fx.SUPPORTED_SIGNAL_MODES)
        self.assertEqual(self.bt.APP_VERSION, "V8.4.2-FOREX-AI-AGENT-BACKTESTER-R6.5")

    def test_strategy_engine_is_crypto_r65_parity(self):
        fx_node, _ = class_node(self.fx_source, "StrategyEngine")
        cr_node, _ = class_node(self.cr_source, "StrategyEngine")
        self.assertEqual(ast.unparse(fx_node), ast.unparse(cr_node))

    def test_ai_preset_is_strategy_parity(self):
        fx_tree = ast.parse(self.fx_source)
        cr_tree = ast.parse(self.cr_source)
        fx_preset = next(n.value for n in fx_tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "AI_AGENT_PRESET" for t in n.targets))
        cr_preset = next(n.value for n in cr_tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "AI_AGENT_PRESET" for t in n.targets))
        # The Forex preset is intentionally identical to Crypto R6.5: Forex-specific
        # behavior belongs to the MT5 execution adapter, not the strategy contract.
        self.assertEqual(ast.literal_eval(fx_preset), ast.literal_eval(cr_preset))
        self.assertEqual(self.fx.AI_AGENT_PRESET_NAME, "AI_AGENT_RECOMMENDED_R6.5")

    def test_ai_hard_envelopes(self):
        checks = {
            "AI_AGENT_MIN_RISK_PCT": (0.20, 0.50),
            "AI_AGENT_MAX_RISK_PCT": (0.20, 0.50),
            "AI_AGENT_MIN_ATR_SL_MULT": (1.50, 2.40),
            "AI_AGENT_MAX_ATR_SL_MULT": (1.50, 2.40),
            "AI_AGENT_MIN_TP1_R_MULT": (1.00, 1.50),
            "AI_AGENT_MAX_TP1_R_MULT": (1.00, 1.50),
            "AI_AGENT_MIN_TP2_R_MULT": (2.00, 3.00),
            "AI_AGENT_MAX_TP2_R_MULT": (2.00, 3.00),
        }
        for name, (low, high) in checks.items():
            value = float(getattr(self.fx, name))
            self.assertGreaterEqual(value, low)
            self.assertLessEqual(value, high)

    def test_ai_decision_smoke(self):
        strong = [
            ("ST", True, False), ("EMA", True, False), ("EMA_CROSS", True, False),
            ("MACD", True, False), ("RSI", True, False), ("VWAP", True, False),
            ("LIQ_SWING", True, False), ("TRENDLINE", True, False), ("MTF", True, False),
        ]
        result = self.fx.StrategyEngine.ai_agent_decision(
            strong,
            min_families=3, min_edge=.20, min_family_confidence=.55,
            require_trend=True, require_structure=True, max_conflicting_families=1,
        )
        self.assertEqual(result["side"], "BUY")
        self.assertGreaterEqual(len(result["bull_families"]), 3)

    def test_ai_manager_hard_bounds(self):
        class Dummy: pass
        votes = [
            ("ST", True, False), ("EMA", True, False), ("EMA_CROSS", True, False),
            ("MACD", True, False), ("RSI", True, False), ("VWAP", True, False),
            ("LIQ_SWING", True, False), ("TRENDLINE", True, False), ("MTF", True, False),
        ]
        d = Dummy()
        for atr in (.0005, .001, .002, .006):
            r = self.fx.UniversalFuturesBotGUI._ai_agent_trade_management(
                d, votes, "LONG", atr, 1.10, .35, 1.8, 1.2, 2.2,
                3, .20, .55, True, True, 1,
            )
            self.assertTrue(.20 <= r["risk_pct"] <= .50)
            self.assertTrue(1.50 <= r["atr_sl_mult"] <= 2.40)
            self.assertTrue(1.00 <= r["tp1_r"] <= 1.50)
            self.assertTrue(2.00 <= r["tp2_r"] <= 3.00)
            self.assertGreater(r["tp2_r"], r["tp1_r"])

    def test_gui_contract_strings(self):
        for marker in (
            "Copy Log", "Clear Log", "Auto Scroll", 'wrap="word"',
            "e_ai_min_families", "e_ai_min_edge", "e_ai_family_confidence",
            "e_ai_max_conflicts", "v_ai_require_trend", "v_ai_require_structure",
            "e_max_open_trades", "AI_AGENT_RECOMMENDED_R6.5",
        ):
            self.assertIn(marker, self.fx_source)

    def test_protection_and_native_mt5_contracts(self):
        for marker in (
            "MT5ForexAdapter", "fx_calculate_entry_qty", "fx_v2_calculate_entry_qty",
            "fx_v2_calculate_protection_prices", "fx_v2_open_market_position",
            "fx_reconcile_protection_mt5", "r65_prot", "AI EFFECTIVE RISK",
            "ACTUAL ENTRY PRICE", "ACTUAL POSITION QTY",
        ):
            self.assertIn(marker, self.fx_source)

    def test_backtester_has_required_contract(self):
        text = BACKTESTER.read_text(encoding="utf-8")
        for marker in (
            "build_frame", "module_votes", "signal_at", "run_backtest",
            "AI_AGENT_MIN_RISK_PCT", "AI_AGENT_MAX_RISK_PCT",
            "FORCED_CLOSE_END", "profit_factor", "max_drawdown_pct",
        ):
            self.assertIn(marker, text)

    def test_backtest_smoke(self):
        import numpy as np
        import pandas as pd
        n = 900
        t = np.arange(n)
        dt = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
        close = 1.10 + 0.018*np.sin(t/23.0) + 0.00002*t
        open_ = close - 0.0004*np.cos(t/5.0)
        high = np.maximum(open_, close) + 0.0014 + 0.0002*np.sin(t/11.0)
        low = np.minimum(open_, close) - 0.0014 - 0.0002*np.cos(t/13.0)
        vol = 1000 + 1300*(1 + np.sin(t/17.0))
        df = pd.DataFrame({"datetime": dt, "open": open_, "high": high, "low": low, "close": close, "vol": vol})
        cfg = {
            "capital": 10000.0,
            "ai_min_families": 1,
            "ai_min_edge": .01,
            "ai_family_confidence": .20,
            "ai_require_trend": False,
            "ai_require_structure": False,
            "ai_max_conflicts": 1,
            "use_mtf": False,
            "use_vol": False,
            "use_adx": False,
            "max_loss_streak": 10,
        }
        result = self.bt.run_backtest(df, cfg)
        m = result["metrics"]
        for key in ("starting_equity", "ending_equity", "net_pnl", "trades", "max_drawdown_pct", "profit_factor"):
            self.assertIn(key, m)
        self.assertGreaterEqual(m["trades"], 0)
        self.assertTrue(math.isfinite(float(m["net_pnl"])))


if __name__ == "__main__":
    unittest.main(verbosity=2)