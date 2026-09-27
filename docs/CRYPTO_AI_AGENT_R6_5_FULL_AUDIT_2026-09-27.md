# Crypto AI-Agent R6.5 — Full Engine Audit & Runtime/UI Hardening
**Date:** 2026-09-27

## Current release
- Engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5.py`
- Version: `V8.4.2-CRYPTO-AI-AGENT-R6.5`
- Config schema: 21
- Runtime schema: 22

## Fixed
### 1. Execution-log horizontal display
The GUI log was using a double-escaped newline in the affected source path, which caused long records to appear as one horizontal line. The GUI and fail-closed kill-switch log writers now use a real Python newline.

### 2. Repeated configuration saves
The 30-second GUI checkpoint previously called `save_settings()` on every cycle. Configuration is now written only after a setting has actually changed. Runtime state continues to be checkpointed independently.

### 3. Repeated completed-candle diagnostics
The same long strategy diagnostic could be written repeatedly while the same completed candle remained active. Diagnostics are now de-duplicated by completed candle, signal/state, position state and decision reason.

### 4. Bybit/private-request timestamp handling
CCXT time-difference correction and a larger `recvWindow` are now enabled in both normal exchange setup and emergency kill-switch exchange setup. Normal startup also attempts an exchange time-difference synchronization before private requests.

### 5. Current-source version clarity
Obsolete R2/R3/R4/R5 labels in the active R6.5 source comments were cleaned up so the current engine is easier to audit.

## Added
### Log controls
- **Copy Log** copies the visible GUI log to the Windows clipboard.
- **Clear Log** clears only the GUI pane; CSV/database history is preserved.
- **Auto Scroll** can be disabled for inspecting earlier messages.
- GUI log retention is bounded to 4,000 lines to avoid unbounded Tk text growth.

### Settings dirty tracking
All GUI variables and Entry widgets are tracked. Periodic checkpoints therefore avoid unnecessary configuration rewrites.

### Exchange/account-mode callback
Changing the exchange now checks the selected Account Mode and automatically moves an invalid combination to the first valid mode for that exchange rather than letting the invalid combination reach the connection stage.

### Regression test
Added:
`tests/test_crypto_ai_agent_r6_5_contract.py`

The suite checks version/mode, duplicate methods, log controls/newline handling, dirty checkpoint behavior, time synchronization, callbacks, AI safety envelopes, AI preset persistence, AI decision parameters and protection-path presence.

## Audited
- Engine structure and StrategyEngine methods.
- 19-module evidence/directional chain and AI-Agent decision parameters.
- AI preset variables and configuration persistence.
- GUI callbacks and runtime GUI key conventions.
- Risk sizing and AI dynamic risk management.
- Actual-fill SL/TP resolution and protection-order creation/reconciliation.
- Profile lifecycle, checkpointing, recovery and mandatory kill switch.
- Exchange/account-mode validation and startup path.

## Verification performed
- Python compilation: PASS.
- R6.5 contract regression suite: PASS (11/11 locally).
- AI council decision smoke tests: PASS.
- AI risk/SL/TP hard-envelope tests: PASS.
  - Risk: 0.20%–0.50%
  - SL: 1.50–2.40 ATR
  - TP1: 1.00–1.50R
  - TP2: 2.00–3.00R

## Runtime-log interpretation
The supplied 15m log repeatedly showing the 15:30 UTC completed candle while the 15:45 candle was still in progress is consistent with the engine's completed-candle rule (`closed_idx=-2`). The actual issue was repeated logging of the same state, not necessarily stale market data.

The supplied `AI_AGENT_BLOCKED` messages such as `FAMILIES_1/3`, `FAMILIES_0/3` and `EDGE_0.05<0.20` are consistent with the strict configured AI-Agent acceptance rules; they are not an exception or process failure.

## Safety boundary
The deterministic AI-Agent remains a rule-based evidence council, not an external LLM. The hard risk/SL/TP envelopes and exchange-side protection model remain in place. No API credentials, profile identity, symbol ownership or mandatory kill-switch behavior were weakened by this audit.
