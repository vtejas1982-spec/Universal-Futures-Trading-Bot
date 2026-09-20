# V8.2.4 — Strategy Decision + Execution Safety Audit

Date: 2026-09-20

## Added

- **ANY_NON_CONFLICTING** signal mode.
  - Any enabled directional module may provide the direction.
  - A BUY/SELL conflict is explicitly blocked.
  - Example: EMA=BULL + VWAP Delta=NEUTRAL => BUY; EMA=BULL + VWAP Delta=BEAR => no trade.
- Centralized `StrategyEngine.decision_reason()` diagnostics.
- Detailed per-module state logging such as `EMA_CROSS:BULL,VWAP_DELTA:BEAR`.
- Configuration schema version 5.

## Fixed

- `2_SIGNALS`, `3_SIGNALS` and `4_SIGNALS` now enforce their named confirmation count inside the StrategyEngine itself instead of depending only on the GUI caller to supply the correct minimum.
- Saved/unknown signal-mode values are validated against the central supported-mode contract during profile load.
- Worker-thread trade-limit shutdown no longer calls `stop_bot()`, which accesses Tkinter widgets from the worker thread.
- Worker-thread daily drawdown circuit-breaker shutdown no longer calls `stop_bot()` for the same Tkinter thread-safety reason.
- Runtime schema and config schema literals use the central schema constants where persisted.

## Modified

- Strategy decision logging now exposes the actual directional state of each enabled module and a machine-readable decision reason.
- Existing `SINGLE_SIGNAL`, `SCORE`, `STRICT_ALL_FILTERS`, Grid, recovery, profile, SL/TP and protection architecture remains intact.
- The existing `OP/USDT` → `OP/USDT:USDT` runtime symbol normalization from V8.2.3 remains in place.

## Audit results

- Python compilation: PASS.
- Duplicate GUI method audit: PASS.
- GUI variable assignment audit: PASS.
- Save/load Entry/Variable coverage: PASS; `v_nwe_repaint` is intentionally load-only because NWE is fixed non-repainting and the saved compatibility value is always `False`.
- StrategyEngine regression tests: 12/12 PASS locally.
- No `self.stop_bot()` calls remain in the worker execution path.
- Full live exchange lifecycle was not claimed by this static audit.

## Important signal behavior

With `2_SIGNALS`, these states intentionally produce no entry:

    EMA_CROSS=BULL
    VWAP_DELTA=BEAR
    BUY=1 / SELL=1
    Signal=NONE
    Reason=INSUFFICIENT_OR_CONFLICTING_B1_S1_R2

To allow either enabled module to trigger while still blocking contradictory directions, select:

    ANY_NON_CONFLICTING

This is a strategy-rule choice; it does not guarantee better trading results.

## Safety

Continue using Bybit Demo/Testnet or another controlled environment for exchange-order validation before live use.