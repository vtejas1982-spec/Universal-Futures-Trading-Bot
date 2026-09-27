# Crypto AI Agent R6.5 Release Notes

Date: 2026-09-27

## Scope

R6.5 is a full hardening audit of the R6.4 crypto AI-Agent engine. The review covered engine calls, strategy/evidence-family logic, AI risk and protection management, configuration variables and defaults, callbacks, persistence/recovery, shutdown and protection reconciliation.

## Fixed

### Thread-safe GUI boundary
Trading and safety workers now communicate GUI work through a bounded queue drained on Tk's main thread. This removes direct worker-to-Tk callbacks and direct worker reads of Tkinter variables from the execution call graph.

The queue is deliberately non-blocking. When full, cosmetic UI updates are dropped rather than stalling the trading/safety worker.

### Shutdown lifecycle
Worker completion no longer releases the profile lock while a background kill-switch cleanup is still active.

Closing an idle GUI no longer contacts the exchange. Exchange cleanup is reserved for active or stale bot runtime state.

### Protection/recovery
Actual TP1/TP2 quantities and the configured TP split are stored in the runtime protection checkpoint.

If TP2 protection disappears, reconstruction now uses the saved TP2 quantity first, then saved split metadata. A 50% fallback remains only for checkpoints from releases that predate TP split metadata.

### Diagnostics
Normal AI-Agent runtime protection is labelled AI_DYNAMIC in runtime state.

The execution diagnostic Required field now reports the AI minimum-family requirement when Signal Mode is AI_AGENT rather than the unrelated legacy minimum-score value.

## Retained AI-Agent contract

- Minimum families: 3.
- Minimum edge: 0.20.
- Minimum family confidence: 0.55.
- Maximum conflicting families: 1.
- Trend required: ON.
- Structure required: ON.
- Dynamic risk: 0.20% to 0.50%.
- ATR SL: 1.50 to 2.40 ATR.
- TP1: 1.00R to 1.50R.
- TP2: 2.00R to 3.00R.
- TP2 is kept beyond TP1.
- Position sizing uses the effective AI stop distance.
- Final protection is based on actual filled entry and actual position quantity.
- Exchange-side protection remains fail-closed and verified.

## Versioning

- Internal version: V8.4.2-CRYPTO-AI-AGENT-R6.5.
- Config schema: 21.
- Runtime schema: 22.
- AI preset: AI_AGENT_RECOMMENDED_R6.5.

## Validation

- Python AST parse: PASS.
- Python bytecode compilation: PASS.
- AI decision and decision-reason smoke tests: PASS.
- TP split calculation smoke tests: PASS.
- Worker-reachable GUI/Tk static audit: PASS.
- StrategyEngine keyword contract audit: PASS.
- Automated contract tests: 5 passed.
- Full live exchange lifecycle is not claimed by this audit.

## Demo test sequence

1. Start the R6.5 production source on Bybit Demo.
2. Confirm Signal Mode is AI_AGENT.
3. Confirm Hold-All-Reverse is OFF.
4. Confirm ATR TP is ON.
5. Apply the recommended R6.5 preset with YES.
6. Start the bot.
7. Allow it to process completed 15m candles.
8. On an accepted setup, verify the execution log contains AI TRADE MANAGER and AI EFFECTIVE RISK, followed by actual-fill protection and exchange-order verification.
9. Test TP1 -> break-even -> TP2 and recovery/reconciliation only after a normal accepted trade has been observed.
10. Test both Stop and window X shutdown and verify the GUI remains responsive.

## Stable filename

The repository keeps UniversalFuturesBot_CRYPTO_AI_AGENT_R4.py as the stable production filename; APP_VERSION identifies the internal release.
