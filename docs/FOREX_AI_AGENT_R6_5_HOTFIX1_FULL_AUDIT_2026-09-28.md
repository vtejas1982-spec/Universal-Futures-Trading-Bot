# Forex AI-Agent R6.5-HOTFIX1 — Full Audit — 2026-09-28

## Scope

This audit covers the Forex/MT5 AI-Agent R6.5 production engine, its configuration contract, GUI variables, callbacks, AI-Agent decision path, bounded risk/protection manager, and the dedicated backtester.

## Release

- Engine: `UniversalForexBot_MT5.py`
- Version: `V8.4.2-FOREX-AI-AGENT-R6.5-HOTFIX1`
- Configuration schema: **22**
- Runtime schema: **22**
- Backtester: `UniversalForexBot_MT5_BACKTESTER.py`
- Backtester marker: `V8.4.2-FOREX-AI-AGENT-R6.5-HOTFIX1-BT`

## Root cause found

The reported startup exception was:

`AttributeError: 'UniversalFuturesBotGUI' object has no attribute 'v_grid_mode'`

R6.5 configuration loading was executed during the parent GUI constructor, while the R6.5 wrapper expected several new controls to already exist.

The audit found the same loader-order defect for additional R6.5 controls:

- `v_grid_mode`
- `v_liq_entry_mode`
- `v_div_entry_mode`
- `e_div_min_count`
- `e_atr_tp1_mult`
- `e_atr_tp2_mult`

## Fixed

### GUI / initialization
All R6.5 runtime controls are initialized before the parent constructor calls `load_settings()`.

The hotfix also exposes the missing controls in a dedicated Forex/MT5 R6.5 control strip:

- Liquidity Entry
- Divergence Entry
- Minimum Divergence Count
- AI TP1 R
- AI TP2 R
- Grid status explicitly shown as OFF-only

### Configuration
- Configuration schema: **21 -> 22**
- Existing saved values remain authoritative.
- Missing R6.5 fields receive deterministic defaults.
- AI TP1/TP2 values are persisted.
- S/R timeframe preset fields are applied by the AI preset callback.
- Unsupported `BOT_SYMBOL` emergency scope was corrected to `BOT_ONLY`.

### Strategy / AI-Agent
The R6.5 decision contract remains:

- Minimum families: **3**
- Minimum edge: **0.20**
- Family confidence: **0.55**
- Require Trend: **ON**
- Require Structure: **ON**
- Maximum conflicting families: **1**

The bounded management envelope remains:

- Risk: **0.20%–0.50%**
- SL: **1.50–2.40 ATR**
- TP1: **1.00–1.50R**
- TP2: **2.00–3.00R**

TP2 is explicitly validated to remain above TP1.

### Grid
Forex grid execution is not enabled by this release. The Forex contract remains **Grid OFF-only**.

## Backtester

The dedicated backtester remains source-of-truth linked to:

`LIVE_FILE = ROOT / "UniversalForexBot_MT5.py"`

It retains:

- completed-candle signal decisions
- the same Evidence-Family AI-Agent council
- 3-family / 0.20-edge / 0.55-confidence contract
- bounded AI risk and ATR/R protection
- MT5-style lot sizing
- spread/slippage simulation
- TP1 partial and break-even handling
- post-SL opposite-direction lock
- drawdown and emergency-capital guards
- one simulated open trade
- OFF-only Forex Grid contract

The backtester is a research simulator; it does not reproduce every broker-specific MT5 execution condition.

## Validation performed

- Python AST parse: **PASS**
- Python bytecode compilation: **PASS**
- Module import: **PASS**
- GUI variable declaration audit: **PASS**
- Callback binding audit: **PASS**
- AI council smoke test: **PASS**
- AI bounded risk/SL/TP manager smoke test: **PASS**
- AI preset coverage audit: **PASS — 119 active preset fields mapped**
- No unresolved `v_grid_mode`, `v_liq_entry_mode`, `v_div_entry_mode`, `e_div_min_count`, `e_atr_tp1_mult` or `e_atr_tp2_mult` GUI contract references remain in the verified local hotfix source.

## Not claimed

This is a source/configuration/backtester audit. It does **not** establish profitability or a complete live MT5 broker execution lifecycle. Demo/paper validation should still be performed before live deployment.
