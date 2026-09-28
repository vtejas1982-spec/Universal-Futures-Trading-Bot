# CRYPTO FUTURES — V8.4.2-AI-AGENT-R6.7 USER MANUAL

**Release:** R6.7  
**Date:** 2026-09-29  
**Live engine:** `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py`

This R6.7 manual update focuses on the protection/execution contract and the full engine audit. Strategy modules and unchanged GUI controls retain the R6.6 definitions unless listed here.

## 1. R6.7 release contract

| Item | R6.7 |
|---|---|
| Crypto live engine | `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py` |
| Config schema | 23 |
| Runtime schema | 24 |
| AI preset | `AI_AGENT_RECOMMENDED_R6.7` |
| Signal mode | AI_AGENT |
| Default timeframe | 15m |
| Default leverage | 5x |
| Max Open Trades | 1 net position |
| TP quantity mode | PERCENT_% |
| TP1 close | 50% |
| TP2 close | 50% |
| TP1 break-even | ON |
| ATR TP multipliers | ON for new profiles |
| ATR SL multiplier | 1.8x for new profiles |

Existing saved profiles remain authoritative.

## 2. TP1 / TP2 contract

R6.7 uses the **actual filled position quantity**, not the requested entry quantity, for protection.

For the default 50/50 configuration:

- Position = 5,000 units
- TP1 = 2,500 units
- TP2 = 2,500 units
- SL = 5,000 units

Exchange precision is applied before orders are submitted.

### Single-TP mode

If only TP1 or only TP2 is enabled, that enabled target closes the full remaining position. The disabled target's close percentage is not used to manufacture a split.

## 3. Bybit protection orders

For Bybit, R6.7 creates independent conditional market exits.

### SL

- Close side is opposite the position.
- SL quantity = 100% of actual position.
- `triggerDirection`: 2 for LONG SL, 1 for SHORT SL.
- `triggerBy`: LastPrice.
- `reduceOnly`: true.
- `closeOnTrigger`: true.
- `positionIdx`: 0.

### TP1 / TP2

- Close side is opposite the position.
- TP quantity follows the configured split.
- `triggerDirection`: 1 for LONG TP, 2 for SHORT TP.
- `triggerBy`: LastPrice.
- `reduceOnly`: true.
- `closeOnTrigger`: true.
- `positionIdx`: 0.

The GUI setting being ON is not considered proof of protection. The exchange order must be acknowledged and then verified.

## 4. What you must see on Bybit Demo

Immediately after a new test position is opened, open **Open Orders → Conditional**.

For normal TP1/TP2 operation you should see:

1. **SL** — close the full position.
2. **TP1** — close 50%.
3. **TP2** — close 50%.

All should be **Untriggered** until their trigger conditions occur.

If only SL is present while TP1/TP2 are enabled, treat the trade as a protection failure and stop the bot. R6.7 is designed to log the exchange acknowledgement/rejection so the exact failure can be diagnosed.

## 5. R6.7 protection log

A successful order path should contain messages similar to:

```
PROTECTION TARGETS ...
SL SUBMIT ...
SL ACK ...
TP1 SUBMIT ...
TP1 ACK ...
TP2 SUBMIT ...
TP2 ACK ...
SL VERIFIED ACTIVE ...
TP1 VERIFIED ACTIVE ...
TP2 VERIFIED ACTIVE ...
PROTECTION VERIFY PASSED ...
```

The ACK line reports order metadata only. API keys and secrets are never included.

## 6. Protection failure behavior

R6.7 creates the protection set in this order:

```
ACTUAL FILL
   ↓
ACTUAL ENTRY + ACTUAL QTY
   ↓
SL
   ↓
TP1
   ↓
TP2
   ↓
VERIFY EACH ORDER
   ↓
POSITION PROTECTED
```

If creation fails part-way through:

- known created protection orders are cancelled;
- the existing safety recovery path cancels remaining bot-symbol orders;
- the unprotected position is closed rather than intentionally continuing without the requested protection set.

## 7. AI-Agent strategy contract

R6.7 keeps the deterministic Evidence-Family AI-Agent architecture.

Families:

- TREND
- MOMENTUM
- FLOW
- STRUCTURE

Regime gates:

- ATR
- ADX

MTF is part of STRUCTURE and is also used as a directional gate.

The AI-Agent is a deterministic rule engine; it is not an external LLM.

### R6.7 AI manager fix

The bounded AI trade manager now receives the actual completed-candle gate state:

- ATR pass/fail
- Volume pass/fail
- ADX pass/fail
- MTF bullish pass/fail
- MTF bearish pass/fail

It no longer re-runs the management decision with all of those gates forced to TRUE.

## 8. Default protection profile

For the R6.7 AI-Agent recommended profile:

- Risk: 0.35% equity
- ATR SL: 1.8x
- ATR TP1: 1.2x SL distance
- ATR TP2: 2.2x SL distance
- TP1: 50%
- TP2: 50%
- TP1 break-even: ON
- Hold-All-Reverse: OFF
- Hold-SL WAIT: OFF
- Grid: OFF
- Max Open Trades: 1

These settings are configuration defaults, not profitability claims.

## 9. Full settings/configuration audit

R6.7 rechecked:

- GUI strategy controls
- Risk controls
- SL/TP controls
- Grid controls
- AI-Agent controls
- Evidence-family settings
- divergence settings
- liquidity settings
- trendline settings
- MTF settings
- profile loading/saving
- configuration migration
- callback bindings
- runtime GUI-variable access
- actual-fill sizing
- protection order ownership
- protection recovery
- kill switch
- worker lifecycle
- single-symbol max-open-position contract

No missing GUI callback binding was found in the audited source.

## 10. Demo validation procedure

Before Live:

1. Use **Bybit Demo/Testnet**.
2. Select the intended bot profile.
3. Verify the symbol shown in the GUI matches the intended Bybit contract.
4. Verify leverage and Max Open Trades.
5. Verify:
   - TP Engine ON
   - TP1 ON
   - TP2 ON
   - TP1 Close 50
   - TP2 Close 50
   - TP1 Break-even ON
6. Start the bot.
7. Wait for one real test entry.
8. Confirm Bybit shows three Conditional orders.
9. Confirm the log shows all three ACKs and all three VERIFIED ACTIVE messages.
10. Let TP1 trigger in Demo and confirm approximately 50% of the actual position closes.
11. Confirm the remaining SL moves to actual entry when TP1 break-even is ON.
12. Confirm TP2 closes the remaining position.

## 11. Important safety note

R6.7 is an engineering hardening release. AST/compile/smoke tests validate code structure and protection contracts; they do not establish profitability, slippage behavior, funding costs, liquidation behavior, or guaranteed live execution.

Use Demo/Testnet validation before Live.

## 12. Related files

- `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py`
- `BUILD_CRYPTO_AI_AGENT_R6.7_EXE.bat`
- `docs/CRYPTO_AI_AGENT_R6_7_RELEASE_NOTES.md`
- `CHANGELOG.md`
- `CURRENT_RELEASE_MANIFEST.md`


## R6.7 Full-Contract Audit Hotfix — 2026-09-29

The R6.7 engine was re-audited after Demo execution.

### AI-Agent diagnostics

When an entry is rejected, the log now identifies:
- dominant side: BUY / SELL / TIE
- family count and edge
- Trend/Structure requirements
- ATR / Volume / ADX gates
- directional MTF gate, for example MTF_GATE_SELL

Do not interpret the generic Minimum Score field as the AI-Agent entry threshold. In AI_AGENT mode the effective controls are Minimum Families, Edge, Family Confidence, Max Conflicts, Trend requirement and Structure requirement.

### TP configuration validation

Before any new exchange-side position is opened, R6.7 validates:
- TP Quantity Mode = PERCENT_% or FIXED_QTY.
- Two-TP percentage mode uses positive percentages below 100% and totals exactly 100%.
- Fixed TP quantities are positive.
- When ATR TP is enabled with both TP levels active, TP2 ATR multiplier must be greater than TP1.

### Demo verification

For a two-target position, confirm Bybit Conditional orders contain:
1. one full-position SL;
2. one TP1 close order for the configured first split;
3. one TP2 close order for the configured second split.

The R6.7 log should show SUBMIT, ACK and VERIFIED ACTIVE for each required protection order. If any required order is rejected or disappears while the position remains open, the protection reconciliation path reports it and attempts restoration; an inconclusive protection-state check pauses new entries rather than guessing.



## Final audit notes — 2026-09-29

### Volume/SR signal timing
Volume/SR is now explicitly completed-candle only in the live worker. The newest chart/HTF candle is excluded before Volume/SR state calculation, keeping VOL_SR consistent with the other entry modules.

### Protection settings
- If a protection feature is OFF, its unused numeric target is not treated as an active validation requirement.
- ATR SL multiplier is validated when ATR SL is enabled.
- ATR TP1/TP2 multipliers are validated when their corresponding TP levels are enabled.
- With both ATR TP levels ON, TP2 must be farther from entry than TP1.
- The normal protection resolver still owns exactly one SL basis at a time: Hold-SL/WAIT, then ATR, then ROI, then Fallback.
- TP uses ATR multipliers only when ATR TP is enabled; otherwise it uses the configured ROI targets.
- The exchange-side SL protects the full live position; TP1/TP2 are separate reduce-only exits whose quantities account for the actual filled position.
