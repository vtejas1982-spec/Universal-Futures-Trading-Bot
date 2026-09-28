# Crypto AI-Agent R6.7 — Protection & Engine Audit Release Notes

**Release:** V8.4.2-CRYPTO-AI-AGENT-R6.7  
**Date:** 2026-09-29  
**Previous release:** R6.6

## Why R6.7 was created

During Bybit Demo validation, the GUI showed TP Engine ON, TP1 ON 50%, TP2 ON 50%, ATR TP ON and TP1 break-even ON, while the exchange showed only one Conditional order: the full-position SL.

R6.7 treats that as a protection-contract failure to diagnose and harden rather than assuming the GUI setting alone proves that TP1/TP2 were installed.

## Fixed

### 1. Bybit TP1/TP2 conditional-order path
- Uses CCXT `market` + `triggerPrice` for Bybit conditional exits.
- Explicitly sends:
  - `triggerDirection`
  - `triggerBy=LastPrice`
  - `reduceOnly=true`
  - `closeOnTrigger=true`
  - `positionIdx=0`
- Keeps SL as a 100% actual-position protection order.
- Keeps TP1 and TP2 as separate reduce-only conditional close orders.

### 2. Protection observability
Every protection order now logs:
- label (SL / TP1 / TP2)
- exchange order ID
- status
- type
- side
- quantity
- trigger price
- reduce-only state
- close-on-trigger state
- submitted parameters

The bot does not log API keys/secrets.

### 3. Protection verification
Bybit order verification now checks the conditional `StopOrder` view first, then the normal order endpoint.

A `create_order()` acknowledgement alone is not considered proof that protection is active.

### 4. Atomic protection-set behavior
The engine submits:
1. SL
2. TP1
3. TP2

If a required order creation fails:
- the known created protection orders are cancelled;
- the existing worker safety-recovery path then cancels remaining open orders and closes an unprotected position;
- the position is not intentionally left open as a partially protected R6.7 trade.

### 5. TP quantity contract
Default:
- TP1 = 50% of actual filled quantity
- TP2 = 50% of actual filled quantity

The split is calculated from the actual post-fill position quantity and exchange precision.

If only one TP is enabled, that enabled TP now closes the full remaining position instead of requiring an artificial 50+50 configuration.

### 6. AI trade-management gate propagation
The bounded AI trade manager previously re-evaluated its council with regime/MTF gates hard-coded to TRUE.

R6.7 passes the real completed-candle:
- ATR gate
- Volume gate
- ADX gate
- MTF bullish gate
- MTF bearish gate

into the AI management decision.

## Added

- R6.7 protection acknowledgement diagnostics.
- R6.7 protection contract metadata in runtime state.
- Explicit protection-target logging before order creation.
- Conditional-order verification using Bybit StopOrder filtering.
- R6.7 release metadata and schema versions.

## Modified defaults

- Config schema: **23**
- Runtime schema: **24**
- AI preset: `AI_AGENT_RECOMMENDED_R6.7`
- New-profile ATR TP multiplier control defaults to ON.
- New-profile ATR SL multiplier default aligns with the R6.7 AI-Agent preset at 1.8.
- TP quantity mode default: `PERCENT_%`
- TP1 close default: 50%
- TP2 close default: 50%

Existing saved profiles remain authoritative and are not silently rewritten.

## Strategy / engine audit

The R6.7 review also checked:
- Evidence-Family architecture
- AI_AGENT decision path
- ATR/ADX regime gates
- MTF gate propagation
- completed-candle signal inputs
- actual-fill entry/quantity protection
- TP1/TP2 quantity persistence
- SL/TP GUI controls
- callback bindings
- GUI runtime-variable references
- configuration save/load mappings
- profile/recovery/kill-switch contracts
- Grid mode isolation
- Max Open Trades single-symbol contract
- NWE non-repainting contract
- divergence/structure configuration fields

No new missing GUI callback binding was found in the audited R6.7 source. The remaining historical compatibility field `nwe_repaint` is intentionally persisted as false because the live NWE implementation is causal/non-repainting.

## Verification performed

Local R6.7 source:
- AST parse: PASS
- Python bytecode compilation: PASS
- GUI callback binding audit: PASS
- GUI runtime variable audit: PASS
- 50/50 synthetic Bybit protection smoke test: PASS
- Single-TP protection smoke test: PASS
- AI gate-forwarding smoke test: PASS
- Protection calculation smoke test: PASS

These tests are structural/execution-contract tests. They do not prove profitability and do not replace Bybit Demo/Testnet execution testing.

## Demo validation checklist

Before Live:
1. Select the intended profile and verify symbol.
2. Verify Bybit Demo/Testnet account mode.
3. Open one small test position.
4. Confirm Bybit Conditional orders show:
   - SL for 100% position
   - TP1 for 50%
   - TP2 for 50%
5. Confirm the R6.7 log contains:
   - `SL ACK`
   - `TP1 ACK`
   - `TP2 ACK`
   - `SL VERIFIED ACTIVE`
   - `TP1 VERIFIED ACTIVE`
   - `TP2 VERIFIED ACTIVE`
6. Confirm TP1 closes 50% and remaining quantity receives the break-even SL when TP1 break-even is ON.
7. Confirm TP2 closes the remaining 50%.
8. Only after this Demo validation consider Live.

## Important

R6.7 is an engineering hardening release. It does not claim maximum profit, profitability, or guaranteed execution. Futures trading remains high risk.
