import ast
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "UniversalFuturesBot_CRYPTO.py"


def load_live():
    stub = types.ModuleType("ccxt")
    class DummyExchange:
        pass
    stub.Exchange = DummyExchange
    for name in ("bybit", "binance", "gate", "bitget", "weex"):
        setattr(stub, name, DummyExchange)
    for name in ("NetworkError", "RequestTimeout", "ExchangeNotAvailable", "DDoSProtection", "RateLimitExceeded"):
        setattr(stub, name, type(name, (Exception,), {}))
    sys.modules["ccxt"] = stub
    spec = importlib.util.spec_from_file_location("crypto_r7_live_test", LIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeExchange:
    def __init__(self, max_qty=100.0):
        self.max_qty = max_qty

    def market(self, symbol):
        return {
            "limits": {"amount": {"min": 0.1, "max": self.max_qty}},
            "info": {"lotSizeFilter": {"maxOrderQty": self.max_qty}},
        }

    def amount_to_precision(self, symbol, qty):
        return f"{qty:.1f}"


def make_bot(module, max_qty=100.0):
    bot = module.UniversalFuturesBotGUI.__new__(module.UniversalFuturesBotGUI)
    bot.exchange = FakeExchange(max_qty)
    bot.logs = []
    bot.log = lambda message: bot.logs.append(str(message))
    bot.bot_profile_id = "BOT-01"
    bot.is_running = False
    bot.bot_thread = None
    bot.stop_requested = False
    return bot


def test_r8_source_compiles_and_release_contract_is_unique():
    source = LIVE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            methods[node.name] = methods.get(node.name, 0) + 1
    assert not {name: n for name, n in methods.items() if n > 1}
    assert 'APP_VERSION = "V8.4.2-CRYPTO-EVIDENCE-HARDENED-R8"' in source
    assert 'AUDIT_BUILD = "V8.4.2-ENGINE-AUDIT-2026-09-27-R7"' in source
    assert "RUNTIME_SCHEMA_VERSION = 6" in source
    assert source.count("DIVERGENCE_INDICATORS = (") == 1


def test_r7_risk_percentage_is_percent_not_fraction():
    module = load_live()
    bot = make_bot(module, max_qty=1000)
    qty = bot.calculate_entry_qty(
        "OP/USDT:USDT",
        balance=1000.0,
        reference_price=100.0,
        risk_pct=0.75,
        sl_price_fraction=0.01,
        size_mode="EQUITY_RISK_%",
        fixed_qty=0.001,
    )
    # 0.75% of $1000 = $7.50; $1 stop distance => 7.5 contracts.
    assert abs(qty - 7.5) < 1e-9


def test_r7_exchange_max_quantity_is_enforced():
    module = load_live()
    bot = make_bot(module, max_qty=100.0)
    qty = bot.safe_amount("OP/USDT:USDT", 150.0)
    assert qty == 100.0
    assert any("EXCHANGE MAX QTY CAP" in line for line in bot.logs)


def test_r7_stop_lifecycle_contracts():
    source = LIVE.read_text(encoding="utf-8")
    assert "self.stop_requested = True" in source
    assert 'self._persist_runtime_state(status="STOPPING")' in source
    assert "def _poll_stop_completion(self):" in source
    assert "def _on_worker_finished(self):" in source
    assert "profile remains locked until the worker exits." in source


def test_r7_stale_flat_runtime_is_normalized():
    source = LIVE.read_text(encoding="utf-8")
    assert 'status in ("RUNNING", "STOPPING", "CRASHED")' in source
    assert "and not position" in source
    assert "and not active_trade" in source
    assert "and not has_grid_state" in source
    assert 'state["status"] = "STOPPED"' in source


def test_r7_stale_profile_can_be_deleted_but_live_state_cannot():
    source = LIVE.read_text(encoding="utf-8")
    assert "if has_saved_position or has_grid_state:" in source
    assert "if status in risky_statuses or has_saved_position or has_grid_state:" not in source


def test_r7_atr_default_matches_new_profile_default():
    source = LIVE.read_text(encoding="utf-8")
    assert '"use_atr",\n                    DEFAULT_USE_ATR' in source


def test_r7_single_symbol_max_open_trades_is_hard_one():
    source = LIVE.read_text(encoding="utf-8")
    assert source.count("if max_open_trades != 1:") >= 3
    assert "single-symbol engine has a hard limit of 1 net position" in source


def test_r8_equity_risk_percentage_is_not_double_divided():
    module = load_live()
    bot = make_bot(module, max_qty=100000)
    qty = bot.calculate_entry_qty(
        "OP/USDT:USDT",
        balance=46405.2433,
        reference_price=5.423,
        risk_pct=0.75,
        sl_price_fraction=0.01,
        size_mode="EQUITY_RISK_%",
        fixed_qty=1500,
    )
    # 0.75% of equity = 348.0393 USDT; 1% price stop on 5.423 costs
    # 0.05423 USDT per OP, so the quantity is approximately 6419.5.
    expected = (46405.2433 * 0.0075) / (5.423 * 0.01)
    assert abs(qty - expected) < 1e-6


def test_r8_fixed_qty_risk_sl_uses_account_risk_budget():
    module = load_live()
    bot = make_bot(module, max_qty=100000)
    bot.safe_price = lambda symbol, price: float(price)
    sl, tp1, tp2, sl_move, tp1_move, tp2_move = bot.calculate_protection_prices(
        "OP/USDT:USDT",
        "LONG",
        actual_entry=5.423,
        position_qty=1500.0,
        position_initial_margin=271.15,
        sl_target_pct=1.5,
        tp1_target_pct=2.0,
        tp2_target_pct=4.0,
        sl_mode="RISK_%",
        tp_mode="PRICE_%",
        leverage=30,
        account_balance=46405.2433,
        risk_pct=0.75,
        atr_value=None,
        atr_sl_multiplier=1.5,
        atr_tp1_multiplier=1.2,
        atr_tp2_multiplier=2.2,
    )
    expected_move = (46405.2433 * 0.0075) / (1500.0 * 5.423)
    assert abs(sl_move - expected_move) < 1e-12
    assert abs(sl - (5.423 * (1 - expected_move))) < 1e-12
    assert abs(tp1_move - expected_move * 1.2) < 1e-12
    assert abs(tp2_move - expected_move * 2.2) < 1e-12


def test_r8_risk_sl_is_explicitly_incompatible_with_hold_all_reverse_and_equity_sizing():
    source = LIVE.read_text(encoding="utf-8")
    assert 'SL Mode RISK_% is only valid with Sizing Mode FIXED_QTY' in source
    assert 'SL Mode RISK_% cannot be combined with Hold-All-Reverse' in source
    assert 'risk_pct = float(self.e_risk_pct.get())' in source
    assert 'risk_pct = (' not in source[source.find('size_mode = ('):source.find('max_dd = (')]


def test_r8_risk_mode_disables_atr_sizing_path():
    source = LIVE.read_text(encoding="utf-8")
    assert 'if use_atr_sl and not hold_all_reverse and sl_mode != "RISK_%":' in source
    assert 'if use_atr_sl and not hold_all_reverse and sl_mode != "RISK_%":' in source
