# V8.3.3 — Full Engine / Strategy / Configuration Audit

## Root cause found

The V8.3.2 orphan-order patch was directionally correct but incomplete.

When a normal position disappeared, the runtime cleared `last_protected_position`. If an exchange-side SL/TP survived a forced close, the next NEW session could no longer prove that the order had been created by this bot.

## Fixed

### 1. Persistent retired managed-order IDs
- Added `retired_managed_order_ids` to the runtime checkpoint.
- Exact SL/TP/Grid order IDs are recorded before live position/Grid state is cleared.
- A later NEW session can clean only those exact IDs.
- Unknown/manual orders still block startup.

### 2. Strict Bybit open-order snapshot protection
- Strict safety reads now reject a full 50-order page as potentially truncated.
- The bot will not assume that a first-page snapshot is the complete symbol inventory.

### 3. Startup risk validation
Startup preflight now validates:
- Sizing Mode
- Risk Per Trade
- Fixed Qty
- Max Daily Drawdown
- Emergency Capital Loss Stop
- Emergency Scope
- Cooldown

### 4. Default consistency
The requested new-profile defaults are centralized:
- ADAPTIVE_SCORE
- Adaptive Edge 0.18
- Adaptive Min Weight 3.5
- MTF ON
- ADX ON
- Volume ON
- ATR OFF
- Grid OFF
- EQUITY_RISK_%
- Risk 1.0%
- Post-SL opposite lock ON
- No same candle ON
- Adaptive Score minimum vote field defaults to 1

Existing saved profiles remain authoritative.

## Retained safety rule

Automatic orphan cleanup is based on exact persisted order IDs only. The bot never adopts a manual order because it happens to be reduce-only or has a similar side/type/trigger.

## Validation

- Source compilation/import: PASS.
- Adaptive decision isolation: PASS.
- Retired managed-order checkpoint extraction: PASS.
- Runtime checkpoint serialization: PASS.
- Strict full-page open-order guard: PASS.
- Configuration contract markers: PASS.

This is an engineering correctness audit, not a profitability claim. Demo/testnet validation remains required before live capital.
