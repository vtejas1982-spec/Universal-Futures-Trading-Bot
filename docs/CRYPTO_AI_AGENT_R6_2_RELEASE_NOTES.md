# Crypto AI Agent R6.2 Release Notes

Date: 2026-09-27

## Purpose

R6.1 repaired the SL configuration-variable migration. The next Bybit Demo run exposed a second integration defect in the direct AI decision-diagnostics path. R6.2 repairs that API contract and makes the NEW-profile AI-Agent defaults internally consistent.

## 1. Reported failure

The worker failed three consecutive cycles with:

`StrategyEngine.decision_reason() got an unexpected keyword argument 'ai_family_confidence'. Did you mean 'ai_min_family_confidence'?`

The fail-closed safety path then stopped the worker and verified the bot-owned symbol was flat with no open orders.

## 2. Root cause

The StrategyEngine method signature uses:

- `ai_min_family_confidence`
- `ai_max_conflicting_families`

The worker called it using the shorter GUI field names:

- `ai_family_confidence`
- `ai_max_conflicts`

The GUI names remain valid at the configuration layer. The fix maps them to the canonical StrategyEngine API names at the direct call boundary.

## 3. Fixed

### 3.1 decision_reason() call contract

Changed:

`ai_family_confidence=ai_family_confidence`

to:

`ai_min_family_confidence=ai_family_confidence`

Changed:

`ai_max_conflicts=ai_max_conflicts`

to:

`ai_max_conflicting_families=ai_max_conflicts`

The wrapper path was already mapping to the correct canonical names.

### 3.2 AI TP configuration visibility

The recommended AI-Agent preset now sets the GUI/configuration value:

`simple_atr_tp_enabled = True`

This matches the R6.x runtime behavior where accepted AI-Agent trades use the effective ATR-TP branch for AI-selected R-multiple targets.

### 3.3 NEW-profile Hold-All-Reverse default

The NEW-profile default is now OFF.

Reason: the R6.x AI dynamic manager condition intentionally excludes Hold-All-Reverse mode. Hold-All-Reverse is a separate reversal/hold behavior that uses hard SL and disables normal TP.

This avoids a fresh AI-Agent profile starting in a state where the AI manager is disabled.

### 3.4 Explicit diagnostics

Two new diagnostics are present:

- AI_AGENT CONFIG NOTICE when AI_AGENT is active without the confirmed recommended preset.
- AI TRADE MANAGER BLOCKED when HOLD-ALL-REVERSE is ON.

The bot does not silently overwrite a user's saved settings in either case.

## 4. AI-Agent behavior retained

For an accepted AI-Agent trade with dynamic management active:

- Risk remains bounded at 0.20%–0.50%.
- ATR SL remains bounded at 1.50–2.40 ATR.
- TP1 remains bounded at 1.00–1.50R.
- TP2 remains bounded at 2.00–3.00R.
- TP2 is kept beyond TP1.
- Risk sizing uses the resolved AI stop distance.
- Final SL/TP is resolved from actual filled entry and actual position quantity.
- Exchange-side protection remains verified.

The AI manager is deterministic rule logic over completed-candle evidence. It is not an external LLM.

## 5. Validation

- Python AST/syntax parse: PASS.
- Direct StrategyEngine keyword audit: PASS.
- `decision_reason()` AI_AGENT smoke test: PASS.
- No unexpected keyword arguments remain in the audited StrategyEngine calls.
- Full exchange lifecycle is not claimed in this pass.

## 6. Test this release

Start with Bybit Demo/Testnet.

Expected initial configuration for the NEW AI-Agent profile:

`Signal Mode = AI_AGENT`

`Hold-All-Reverse = OFF`

`ATR TP = ON`

Then select AI_AGENT and confirm YES when the preset confirmation appears.

For the first accepted trade, the execution log should contain:

- `AI TRADE MANAGER:`
- `AI EFFECTIVE RISK:`
- `PROTECTION RESOLVED:`
- `TP RESOLVED:`
- `PROTECTION CALCULATED FROM ACTUAL ENTRY:`

The failed run did not reach entry; after this hotfix, the next demo run is the required validation of the complete live execution path.

## 7. Stable filename

The repository continues to use the stable production filename:

`UniversalFuturesBot_CRYPTO_AI_AGENT_R4.py`

The internal release is identified by `APP_VERSION = V8.4.2-CRYPTO-AI-AGENT-R6.2`.
