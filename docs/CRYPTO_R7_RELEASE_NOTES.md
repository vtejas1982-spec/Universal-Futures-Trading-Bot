# Crypto R7 Release Notes — 2026-09-27

## Release

- Live engine: `UniversalFuturesBot_CRYPTO.py`
- Release marker: `V8.4.2-CRYPTO-EVIDENCE-HARDENED-R7`
- Audit marker: `V8.4.2-ENGINE-AUDIT-2026-09-27-R7`
- Config schema remains **9**: no new user-editable configuration field was introduced.
- Runtime schema is now **6**: explicit stop-request lifecycle state was added.

## Why R7 was required

The Bybit Demo validation exposed two separate production issues:

1. A profile could remain displayed as **RUNNING** after the bot had stopped or after a stale runtime checkpoint was left behind. The profile could then be difficult to stop, load, or delete.
2. Risk sizing interpreted the GUI value `0.75` as `75%` of equity instead of `0.75%`. This could produce an oversized requested quantity before the exchange rejected it.
3. The live engine did not enforce the exchange's maximum order quantity before submitting an entry. Bybit therefore had to reject an oversized order.

R7 fixes these at the lifecycle, sizing, and exchange-boundary layers without loosening the strategy.

## Fixed

### 1. Stop / RUNNING / profile lifecycle

The old shutdown path flipped `is_running` but left the GUI/profile lifecycle dependent on the worker's eventual cleanup. The profile table could therefore continue to show RUNNING, while stale runtime status could also block profile deletion.

R7 adds an explicit lifecycle:

```
RUNNING
   ↓ Stop requested
STOPPING
   ↓ worker exits + final exchange check
STOPPED                 or PAUSED_WITH_POSITION
```

Changes:

- Added `stop_requested` and `stop_started_at` runtime state.
- Stop now persists `STOPPING` immediately.
- The GUI waits asynchronously for the worker instead of blocking the Tk mainloop.
- The profile lock is not released until the worker has actually exited.
- Start is blocked while the previous worker is still shutting down.
- Worker completion refreshes the profile manager and button states.
- Same-process profile locks are now recognized while the worker is still alive/stopping.
- A stale flat RUNNING/STOPPING/CRASHED checkpoint with no saved position/Grid state and no live process is normalized to STOPPED.
- A stale lifecycle marker alone no longer prevents deletion of a flat orphaned profile.
- A saved position, active trade, Grid state, or live profile lock still blocks destructive profile operations.

This prevents the GUI from claiming a bot is running merely because an old JSON status says RUNNING.

### 2. Risk percentage sizing

R6 live sizing used:

```
risk_amount = balance × risk_pct
```

while the GUI explicitly labels the field as a percentage.

For a configured 0.75%, that incorrectly meant 75% of equity.

R7 uses:

```
risk_fraction = risk_pct / 100
risk_amount = balance × risk_fraction
quantity = risk_amount / stop_distance
```

So a configured **0.75** means **0.75%**.

The backtester already used the percentage interpretation; R7 brings the live engine into parity with it.

### 3. Exchange maximum quantity enforcement

R7 now enforces:

- CCXT unified `market.limits.amount.min`
- CCXT unified `market.limits.amount.max`
- exchange raw lot-size maximums when the unified maximum is unavailable
- amount precision after the maximum is applied

Bybit-specific raw fallbacks include `maxMktOrderQty` and `maxOrderQty`.

Runtime logging now reports:

```
EXCHANGE MAX QTY CAP | OP/USDT:USDT |
Requested=... | Max=... | Final=...
```

For risk-sized entries, the bot also reports the configured risk and the actual stop-distance risk after an exchange cap/precision reduction.

The exchange cap can only reduce the calculated quantity; it never increases it.

### 4. ATR configuration default parity

The new-profile constant already defined ATR regime gating as ON, but one load-settings fallback still used OFF when the persisted key was absent.

R7 changes that fallback to `DEFAULT_USE_ATR`, eliminating the GUI-default/load-default mismatch.

### 5. Max Open Trades semantics

This engine is intentionally a single-symbol, one-net-position coordinator.

R7 makes that contract explicit:

- `Max Open Trades = 1` is the only effective value.
- `0` no longer means "unlimited" for this engine.
- Values other than 1 are normalized to 1.
- Startup and runtime diagnostics now say "hard limit of 1 net position."

This removes a misleading configuration path where the GUI could display UNLIMITED even though the engine could only manage one net position.

### 6. Code cleanup

- Removed the duplicate `DIVERGENCE_INDICATORS` constant definition.
- Preserved the R6 cooldown and Hold-SL WAIT fixes.
- Preserved Evidence-family thresholds and directional logic.
- Preserved actual-fill SL/TP and recovery verification architecture.

## Strategy contract intentionally unchanged

R7 does **not** weaken or change:

- `ADAPTIVE_EVIDENCE`
- Evidence minimum families = **2**
- Family minimum score = **0.35**
- Adaptive Edge = **0.18**
- Trend required = **ON**
- Independent non-Trend family required = **ON**
- ATR/ADX as regime gates
- completed-candle signal evaluation
- Hold-All-Reverse semantics
- post-SL opposite-direction lock
- ATR Dynamic SL = **1.50 ATR**
- ATR TP1 = **1.20 × SL distance**
- ATR TP2 = **2.20 × SL distance**
- configured leverage
- configured risk value itself
- single-symbol one-net-position architecture

The risk calculation is corrected so the configured percentage is interpreted correctly; the user-facing 0.75% setting is not silently changed to another percentage.

## Tests

R7 adds:

- `tests/test_crypto_r7_regressions.py`

Coverage includes:

- source AST/compile contract
- R7 release markers
- duplicate-definition detection
- percentage risk-sizing semantics
- exchange maximum quantity clamp
- stop lifecycle and STOPPING state
- stale flat runtime normalization
- safe stale-profile deletion
- ATR default parity
- single-symbol Max Open Trades hard limit

Local validation performed during the R7 audit:

```
R6 regression suite: 5 passed
R7 regression suite: 8 passed
Combined: 13 passed
Python py_compile: PASS
Module import: PASS
```

The local regression suite does not claim a live exchange order lifecycle. Bybit Demo validation remains required.

## Deployment checklist

1. Stop the currently running old bot instance.
2. Update `UniversalFuturesBot_CRYPTO.py`.
3. Keep existing profiles/configuration unless intentionally changing settings.
4. Start in Bybit Demo.
5. Confirm the profile manager shows **RUNNING** only while the worker is actually alive.
6. Stop the bot and confirm it reaches **STOPPED** when the Demo account is flat.
7. Reopen the GUI and confirm a flat stopped profile does not produce a phantom recovery prompt.
8. Test one controlled entry and verify:
   - requested quantity
   - exchange maximum
   - final quantity
   - actual filled quantity
   - actual entry price
   - protection state
9. Only after Demo validation should live deployment be considered.

R7 is an execution/lifecycle/risk-boundary hardening release. It does not guarantee profitability or that every strategy signal will result in an entry.
