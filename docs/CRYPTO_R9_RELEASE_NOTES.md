# Crypto R9 Release Notes — 2026-09-27

## Problem addressed

R8 persisted profile runtime state, but the Profile Manager could still display a historical RUNNING checkpoint when the worker process was gone. A GUI instance controlling BOT-02 also had no safe way to stop BOT-01 when BOT-01 was running in another process.

## Fixed

1. Cross-process STOP: added profile-scoped control.json and a Profile Manager STOP Selected Bot action. The target worker acknowledges the request and exits through the normal runtime-finalization path.
2. Truthful lifecycle status: a runtime checkpoint is historical data, not proof that a worker is alive. Live lock + worker state controls RUNNING/STOPPING. Stale flat sessions become STOPPED. Stale sessions with saved position/Grid inventory become RECOVERY_REQUIRED.
3. Profile status heartbeat: profile table refreshes every 3 seconds.
4. Max Open Trades: the current engine is single-symbol/one-way and supports one net live position. Values other than 1 are rejected explicitly. Max Completed Trades remains the session trade-count limit.
5. Configuration default parity: missing legacy cooldown uses DEFAULT_COOLDOWN_MIN; missing legacy divergence enable uses DEFAULT_USE_DIVERGENCE.
6. Dead configuration cleanup: removed unused RISK_COST_BUFFER because it did not participate in any live calculation.

## Preserved risk/protection contract

- EQUITY_RISK_% remains quantity sizing.
- FIXED_QTY remains literal exchange/base quantity.
- FIXED_QTY + RISK_% remains the explicit hard-SL risk-budget mode.
- ATR Dynamic protection remains enabled by default for new profiles with 1.5x ATR SL, 1.2x SL-distance TP1, and 2.2x SL-distance TP2.
- Protection continues to use actual filled entry and actual position quantity.
- Grid risk remains independent from normal-strategy risk/SL/TP.

## Validation

- Python py_compile: PASS on the R9 source.
- AST audit: 139 GUI methods; no missing self-method call candidates.
- Import/runtime self-test was not run in the analysis environment because ccxt is not installed there.
- Bybit Demo live lifecycle/order validation is still required before treating the build as production-validated.
