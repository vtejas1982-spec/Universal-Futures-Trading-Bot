# V8.4.2-CRYPTO-AI-AGENT-R5 Release Notes

Date: 2026-09-27

## Purpose

R5 adds a confirmation-controlled AI-Agent recommended configuration preset to the audited R4 engine. The preset is deterministic and rule-based; it is not an LLM and does not guarantee profitability.

## User workflow

When **Decision Engine → Signal Mode → AI_AGENT** is selected:

1. The bot asks:
   - **YES** — Apply Recommended AI Agent Settings
   - **NO** — Continue With Current Settings
2. YES applies the R5 preset.
3. NO leaves all current settings unchanged while AI_AGENT remains enabled.
4. The selection is not silently applied during profile loading.

## Six AI-Agent controls

These remain independently editable:

| Control | R5 recommended value |
|---|---:|
| AI Min Families | 3 |
| AI Min Edge | 0.20 |
| AI Family Confidence | 0.55 |
| AI Max Conflicts | 1 |
| AI Require Trend | ON |
| AI Require Structure | ON |

## R5 recommended operating profile

- Timeframe: 15m
- Leverage: 5x
- Max open trades: 1
- No same-candle re-entry: ON
- Cooldown: 15 minutes
- Post-SL opposite lock: ON
- Risk-based sizing: ON
- Risk per trade: 0.35%
- Daily drawdown stop: 5%
- Emergency capital stop: 10%, BOT_SYMBOL scope
- Grid: OFF
- Core trend/momentum/flow/structure evidence enabled
- MTF, ADX, ATR and volume regime gates enabled
- Confirmed divergence enabled
- Legacy protection: OFF
- Simple ROI protection: SL 30%, TP1 60%, TP2 120%
- ATR SL: ON, 1.8x
- Fallback SL: ON, 30% ROI
- TP1 break-even: ON
- Hold-All-Reverse: OFF by default so normal TP protection remains active

The indicator periods and entry semantics are reset to the audited R4 GUI defaults so the preset is reproducible.

## Fixed

### Effective AI diagnostics

R4's AI-Agent decision-reason path could display the compile-time defaults even when a profile supplied different AI-Agent thresholds. R5 now reports the effective runtime values used for the decision.

### Configuration metadata

Config/runtime schema is now 16. Profiles persist:

- ai_agent_preset_name
- ai_agent_preset_applied

Existing profiles remain authoritative until the user explicitly selects AI_AGENT and confirms the preset.

## Modified

- Decision Engine Signal Mode OptionMenu now has a user-selection callback.
- AI-Agent preset application is centralized in one method rather than scattered across callbacks.
- Worker runtime snapshot is refreshed after preset application.
- API credentials, exchange/account mode, symbol and profile identity are deliberately excluded from the preset.

## Audit scope

Rechecked:

- AI-Agent six-control GUI path
- defaults and preset values
- OptionMenu callback
- configuration save/load
- schema migration
- runtime GUI snapshot
- StrategyEngine AI-Agent parameter propagation
- AI-Agent decision diagnostics
- risk sizing
- protection configuration
- reversal controls
- Grid isolation
- compile/AST path

## Validation

- Python `py_compile`: PASS
- Python AST parse: PASS
- Deterministic AI-Agent smoke test: PASS
- Live exchange profitability/order lifecycle: NOT established by source testing and still requires Bybit Demo validation.

## Important

The preset is designed as a disciplined profit-seeking configuration, not as a claim of maximum profit. Market conditions, fees, slippage, funding, execution quality and regime changes can materially affect results.
