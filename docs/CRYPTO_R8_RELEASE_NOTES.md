# Crypto R8 Release Notes — 2026-09-27

## Release

- Live engine: `UniversalFuturesBot_CRYPTO.py`
- Release marker: `V8.4.2-CRYPTO-EVIDENCE-HARDENED-R8`
- Audit marker: `V8.4.2-ENGINE-AUDIT-2026-09-27-R8`
- Config schema is **10**: R8 formalizes the FIXED_QTY + RISK_% protection contract.
- Runtime schema is now **7**: explicit stop-request lifecycle state plus sizing/protection-basis metadata.

## Why R8 was required

R8 also hardens the GUI/worker boundary: Tkinter setting values are snapshotted on the GUI thread and read from that snapshot by the trading worker.

The Bybit Demo validation exposed two separate production issues:

1. A profile could remain displayed as **RUNNING** after the bot had stopped or after a stale runtime checkpoint was left behind. The profile could then be difficult to stop, load, or delete.
2. Risk sizing interpreted the GUI value `0.75` as `75%` of equity instead of `0.75%`. This could produce an oversized requested quantity before the exchange rejected it.
3. The live engine did not enforce the exchange's maximum order quantity before submitting an entry. Bybit therefore had to reject an oversized order.

R8 fixes these at the lifecycle, sizing, and exchange-boundary layers without loosening the strategy. RISK_% also emits a conservative leverage-envelope warning when the required price stop is wide; actual liquidation remains exchange/margin dependent.

## Fixed

### 1. Stop / RUNNING / profile lifecycle

The old shutdown path flipped `is_running` but left the GUI/profile lifecycle dependent on the worker's eventual cleanup. The profile table could therefore continue to show RUNNING, while stale runtime status could also block profile deletion.

R8 adds an explicit lifecycle:

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

R8 uses:

```
risk_fraction = risk_pct / 100
risk_amount = balance × risk_fraction
quantity = risk_amount / stop_distance
```

So a configured **0.75** means **0.75%**.

The backtester already used the percentage interpretation; R8 also adds the FIXED_QTY + RISK_% stop model so historical tests can represent the same risk-SL contract.

### 3. Exchange maximum quantity enforcement

R8 now enforces:

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

R8 changes that fallback to `DEFAULT_USE_ATR`, eliminating the GUI-default/load-default mismatch.

### 5. Max Open Trades semantics

This engine is intentionally a single-symbol, one-net-position coordinator.

R8 makes that contract explicit:

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

R8 does **not** weaken or change:

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

R8 adds:

- `tests/test_crypto_r8_regressions.py`

Coverage includes:

- source AST/compile contract
- R8 release markers
- duplicate-definition detection
- percentage risk-sizing semantics
- exchange maximum quantity clamp
- stop lifecycle and STOPPING state
- stale flat runtime normalization
- safe stale-profile deletion
- ATR default parity
- single-symbol Max Open Trades hard limit

Local validation performed during the R8 audit:

```
R6 regression suite: 5 passed
R8 regression suite: 8 passed
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

R8 is an execution/lifecycle/risk-boundary hardening release. It does not guarantee profitability or that every strategy signal will result in an entry.


## R8-specific change

R8 adds explicit FIXED_QTY + RISK_% hard-stop semantics and fixes the live Risk Per Trade percentage double-conversion discovered during Bybit Demo validation. A 0.75 GUI value is now passed as 0.75 percentage points to the sizing engine, and RISK_% protection converts it to 0.0075 internally exactly once.


## GUI callback behavior

Switching Sizing Mode to FIXED_QTY automatically selects SL Mode RISK_% when Hold-All-Reverse is OFF. Switching back to EQUITY_RISK_% returns the SL selector to PRICE_%. If Hold-All-Reverse remains ON, the GUI keeps that mode intact and logs that Risk Per Trade (%) cannot own the hard SL until Hold-All-Reverse is disabled.
