# Universal Futures Trading Bot V8.2 — Modular Engine

## What changed

V8.2 is the next engineering layer on top of the V8.1 Recovery + Multi-Bot build.

### Added
- StrategyEngine: GUI/exchange-independent signal decision contract.
- Central V8.2 engine constants for supported exchanges, signal modes and Grid modes.
- Preflight validation before profile-lock acquisition or exchange-side mutations.
- CCXT exchange client timeout of 20 seconds.
- Runtime state schema version 3.
- Configuration schema version 4.
- Dedicated V8.2 static, strategy, recovery and opt-in exchange-demo test files.

### Fixed / hardened
- Strategy voting now treats a module that simultaneously reports bull and bear as ambiguous in SINGLE_SIGNAL instead of allowing the first branch to win.
- Invalid minimum signal score is rejected before execution.
- Invalid signal mode is rejected before exchange initialization.
- Non-positive leverage is rejected before exchange configuration.
- Grid validation remains the gate before leverage/order activity.
- Existing fail-closed Grid protection and recovery behavior is preserved.

### Preserved
- 17 directional modules.
- Completed-candle evaluation.
- DIRECT_SHOT / SCORE and signal compatibility modes.
- LONG_GRID / SHORT_GRID / NEUTRAL_GRID.
- Actual-fill-based normal SL/TP protection.
- Recovery, profile manager, profile lock and master ledger.
- Bybit, Binance, Gate.io, Bitget and WEEX support.

## Validation

Local V8.2 regression suite: 22 tests passed, 1 exchange-demo gate skipped.

The exchange-demo test is intentionally opt-in. Static/unit tests do not prove real exchange order lifecycle behavior.

## Demo/testnet plan

1. Run V8.2 with one bot profile.
2. Use exchange demo/testnet credentials.
3. Test market entry and actual filled entry detection.
4. Verify SL/TP creation and exchange-side status.
5. Test TP1 to break-even.
6. Test SL/TP disappearance and reconciliation.
7. Test restart to Resume / Start New.
8. Test Grid duplicate-order synchronization.
9. Test Grid stop, max exposure and max drawdown.
10. Test NEUTRAL_GRID direction reversal.
11. Only after successful demo validation consider live deployment.

V8.2 remains a software engineering/testing release, not a guarantee of trading performance or safety on every exchange/account mode.
