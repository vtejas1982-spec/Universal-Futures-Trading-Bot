import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "V8_3_HARDENED_ADAPTIVE_BOT.py"

cc = types.ModuleType("ccxt")
cc.__getattr__ = lambda name: type(name, (), {})
sys.modules["ccxt"] = cc

def load_bot():
    spec = importlib.util.spec_from_file_location("v833_audit_bot", BOT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_compile_and_import():
    import py_compile
    py_compile.compile(str(BOT), doraise=True)
    bot = load_bot()
    assert bot.APP_VERSION == "V8.3.3"
    assert bot.RUNTIME_SCHEMA_VERSION == 5

def test_adaptive_isolation():
    bot = load_bot()
    assert len(bot.ADAPTIVE_MODULE_WEIGHTS) == 19
    assert not hasattr(bot.StrategyEngine, "adaptive_edge")
    assert not hasattr(bot.StrategyEngine, "adaptive_min_weight")
    low = bot.StrategyEngine.decide_signal(
        [("ST", True, False)], "ADAPTIVE_SCORE", 1,
        adaptive_edge=0.18, adaptive_min_weight=1.0
    )
    high = bot.StrategyEngine.decide_signal(
        [("ST", True, False)], "ADAPTIVE_SCORE", 1,
        adaptive_edge=0.18, adaptive_min_weight=2.0
    )
    assert low[0] and not low[1]
    assert not high[0] and not high[1]

def test_retired_order_ids():
    bot = load_bot()
    state = {
        "position_state": {
            "last_protected_position": None,
            "retired_managed_order_ids": ["SL-OLD", "TP-OLD"],
        },
        "grid_state": {
            "entry_orders": {"0": {"id": "GRID-OLD"}},
            "tp_order_id": "GRID-TP",
            "sl_order_id": "GRID-SL",
        },
    }
    ids = bot.UniversalFuturesBotGUI._checkpoint_managed_order_ids(state)
    assert ids == {"SL-OLD", "TP-OLD", "GRID-OLD", "GRID-TP", "GRID-SL"}

def test_strict_order_page_guard():
    bot = load_bot()
    obj = bot.UniversalFuturesBotGUI.__new__(bot.UniversalFuturesBotGUI)
    class Exchange:
        def fetch_open_orders(self, symbol, limit=None):
            return [{"id": str(i)} for i in range(limit or 50)]
    obj.exchange_id = "bybit"
    obj.exchange = Exchange()
    obj.log = lambda *_a, **_k: None
    try:
        obj.fetch_open_orders_safe("OP/USDT:USDT", strict=True)
    except RuntimeError as exc:
        assert "page limit" in str(exc).lower()
    else:
        raise AssertionError("strict full-page snapshot was accepted")

def test_runtime_serialization():
    bot = load_bot()
    obj = bot.UniversalFuturesBotGUI.__new__(bot.UniversalFuturesBotGUI)
    obj.retired_managed_order_ids = {"A", "B"}
    obj.active_trade = None
    obj.last_protected_position = None
    obj.tp1_be_done = False
    obj.hold_sl_wait_reversal = False
    obj.hold_sl_threshold_hit = False
    obj.hold_sl_threshold_logged = False
    obj.reentry_direction_lock = None
    obj.reentry_lock_reason = ""
    obj.last_entry_candle_ts = None
    obj.last_flat_time = 0.0
    obj.grid_state = {"active": False, "mode": "OFF", "entry_orders": {},
                      "filled_levels": set(), "tp_order_id": None, "sl_order_id": None}
    obj.session_id = "S"; obj.bot_profile_id = "BOT-01"; obj.exchange_id = "bybit"
    obj.runtime_account_mode = "BYBIT_DEMO"; obj.symbol = "OP/USDT:USDT"
    obj.runtime_timeframe = "15m"; obj.runtime_strategy_mode = "ADAPTIVE_SCORE"
    obj.runtime_strategy_modules = "ST"; obj.runtime_config_hash = "x"
    obj.runtime_resumed = False; obj.session_started_at = 0; obj.session_max_trades = 10
    obj.start_balance = obj.daily_start_balance = obj.daily_peak_equity = obj.session_peak_equity = 100
    obj.consecutive_cycle_errors = obj.last_market_data_ts = 0
    obj.daily_start_date = None
    obj.total_trades = obj.opened_trades = obj.winning_trades = obj.losing_trades = 0
    obj.trade_pnls = []; obj.net_pnl = 0; obj.runtime_last_error = ""
    obj._serializable_protected_position = lambda: None
    obj._serializable_grid_state = lambda: {}
    obj._config_snapshot_for_recovery = lambda: {}
    payload = obj._runtime_state_payload()
    assert payload["position_state"]["retired_managed_order_ids"] == ["A", "B"]

if __name__ == "__main__":
    tests = [test_compile_and_import, test_adaptive_isolation, test_retired_order_ids,
             test_strict_order_page_guard, test_runtime_serialization]
    for fn in tests:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(tests)}/{len(tests)} PASS")
