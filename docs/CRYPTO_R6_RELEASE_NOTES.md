# Crypto R6 Release Notes — 2026-09-27

## Release

- Live engine: `UniversalFuturesBot_CRYPTO.py`
- Release marker: `V8.4.2-CRYPTO-EVIDENCE-HARDENED-R6`
- Audit marker: `V8.4.2-ENGINE-AUDIT-2026-09-27-R6`
- Config schema remains **9** because R6 does not introduce a new persisted configuration field.

## Why R6 was required

An overnight live run produced valid BUY decisions but no entries. The runtime repeatedly reported a 900-second cooldown even while the bot remained flat.

The root cause was execution-state handling: `last_flat_time` was refreshed on every flat polling cycle. Because the loop runs approximately every 30 seconds, the configured 15-minute cooldown was continually restarted and could never expire.

## Fixed

### 1. Cooldown state machine

Before R6:

```
flat poll -> last_flat_time = now
30s -> last_flat_time = now
30s -> last_flat_time = now
...
cooldown never expires
```

R6:

```
verified live/active state -> flat
        |
        +--> last_flat_time = now
        |
        +--> configured cooldown starts
        |
        +--> cooldown expires normally
```

A continuously-flat bot no longer starts or restarts the cooldown.

The runtime now also logs:

```
COOLDOWN STARTED: 15 min after verified live->flat transition.
```

or the equivalent strategy-reversal message.

### 2. Hold-SL WAIT reversal gate

When Hold-All-Reverse + Hold-SL WAIT is enabled, the configured ROI threshold must be reached before a strategy reversal can close the position.

The previous live code set `reversal_allowed = False`, then immediately recalculated it from the ALL-REVERSE directional checks. That could bypass the WAIT prerequisite.

R6 makes the two conditions explicit:

1. Hold-SL threshold must be reached.
2. Then all active directional states must reverse.

### 3. Diagnostic cleanup

- Removed an unreachable duplicate `ADAPTIVE_EVIDENCE` startup log branch.
- Added explicit cooldown-start logging.

## Added

- `tests/test_crypto_r6_regressions.py`
- R6 release documentation.
- R6 checks in `tests/test_crypto_engine.py`.

Regression coverage includes:

- source/AST compilation
- R6 release markers
- cooldown transition contract
- Hold-SL WAIT ordering
- all supported StrategyEngine modes
- SINGLE_SIGNAL conflict fail-closed behavior

## Modified

- Stable production file remains `UniversalFuturesBot_CRYPTO.py`; no duplicate R6 production filename was added to the repository.
- Crypto backtester release marker is aligned to R6. Its historical signal calculations are otherwise unchanged.
- README, changelog and production manifest now identify Crypto R6 as the current Crypto production line.

## Intentionally not changed

R6 does **not** change:

- ADAPTIVE_EVIDENCE thresholds
- Evidence-family definitions
- Adaptive Edge 0.18
- Minimum Evidence Families 2
- Family Minimum Score 0.35
- Trend requirement
- Independent non-Trend requirement
- ATR/ADX regime-gate semantics
- risk percentage
- leverage
- ATR SL/TP multipliers
- exchange order/protection architecture
- single-symbol one-net-position execution model

This was deliberate: the cooldown problem was an execution-state defect, not a reason to loosen the strategy.

## Validation

The R6 source was syntax-compiled and the dedicated local regression suite passed:

```
5 passed
```

The GitHub regression test suite should be run on the repository environment as an additional verification step before live deployment.

## Deployment recommendation

1. Stop any running old Crypto bot instance.
2. Pull the updated `UniversalFuturesBot_CRYPTO.py`.
3. Keep the existing profile/config unless you intentionally want to change strategy settings.
4. Run Bybit Demo/Testnet first.
5. Watch for:
   - `SIGNAL=BUY/SELL`
   - `ENTRY BLOCKED`
   - `COOLDOWN STARTED`
   - `ENTRY ...`
   - `ACTUAL FILL`
   - `POSITION PROTECTED ✓`
6. Confirm the first entry before considering live deployment.

R6 fixes the execution-state defect; it does not guarantee that every signal will become a trade because the remaining safety gates are intentionally preserved.
