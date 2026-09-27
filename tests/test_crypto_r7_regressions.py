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


def test_r7_source_compiles_and_release_contract_is_unique():
    source = LIVE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            methods[node.name] = methods.get(node.name, 0) + 1
    assert not {name: n for name, n in methods.items() if n > 1}
    assert 'APP_VERSION = "V8.4.2-CRYPTO-EVIDENCE-HARDENED-R7"' in source
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
