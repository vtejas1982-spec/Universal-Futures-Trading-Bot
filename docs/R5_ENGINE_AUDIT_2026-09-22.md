# V8.4.2-R5 Engine Audit — 2026-09-22

## Scope

This audit covers the current production Crypto live engine, Forex/MT5 live engine, and Crypto R5 backtester, with the repository tests used as regression checks.

## Fixed

### Crypto live
- Added explicit ADX Period configuration (default 14) instead of keeping the ADX period implicit in the calculation.
- ADX period is now saved/loaded with the profile and validated before startup.
- Improved ADAPTIVE_EVIDENCE diagnostics. A blocked signal now identifies the dominant side, family-count failure, edge failure, missing Trend family, missing independent non-Trend family, ATR gate failure, or ADX gate failure.
- Runtime logs now show the completed-candle ADX value and ADXGate=PASS/FAIL.
- New-profile defaults were aligned to the supplied conservative Crypto recommendation: ATR regime gate ON, Grid OFF, risk per trade 0.75%, cooldown 15 minutes.
- Existing saved profiles are not silently overwritten.

### Crypto backtester
- Fixed a Grid fill-loop defect in _grid_fill_orders() that could repeatedly re-process the same fill because the fill list was mutated while it was being iterated.
- Implemented the configured Grid cooldown after Grid DD/TP/SL/max-exposure exits.
- Added max_loss_streak enforcement.
- Daily drawdown now evaluates marked equity, including adverse unrealized PnL, instead of only closed equity.
- signal_for_bar() now passes the configured Evidence-family thresholds/requirements explicitly instead of relying on engine defaults.
- Added the same detailed Evidence blocker diagnostics used by the live engine.
- Added explicit adx_len configuration (14).
- Safer research defaults: ATR gate ON, Grid OFF, 0.75% risk, 15-minute cooldown.

### Forex / MT5 live
- Added explicit ADX Period configuration and profile persistence.
- Added the same detailed ADAPTIVE_EVIDENCE blocker diagnostics and ADX runtime visibility.
- Updated the R5 new-profile recommendation: risk 0.50%, ATR regime gate ON, ATR Dynamic protection ON, news filter ON with ±30 minutes, session filter ON at 07:00–20:00 UTC, daily loss limit 2%, correlation protection ON at 0.85, Friday cutoff 18:00 UTC.
- Forex ATR protection defaults: SL 1.50x, TP1 1.30x actual SL distance, TP2 2.20x actual SL distance.
- Existing saved configurations remain authoritative.

## Important semantics clarification

EVIDENCE_BLOCKED_BF3_SF1_EDGE0.25 means:
- BF3 = 3 qualifying bullish Evidence families.
- SF1 = 1 qualifying bearish Evidence family.

SF is not "strong families"; it is the bearish-family count.

The new diagnostic suffix can show the exact hard blocker, for example:
SIDE=BUY | BLOCK=ADX_GATE | ATR=PASS | ADX=FAIL

This is specifically intended to make "no trade for hours" debugging actionable without weakening the Evidence thresholds.

## Protection contracts

### Crypto R5
- ATR SL = 1.50x completed-candle ATR
- TP1 = 1.20x actual SL distance
- TP2 = 2.20x actual SL distance

### Forex R5
- ATR SL = 1.50x completed-candle ATR
- TP1 = 1.30x actual SL distance
- TP2 = 2.20x actual SL distance

The Forex 1.30R TP1 is a Forex-specific profile recommendation; Crypto remains 1.20R.

## What was deliberately not changed

- The Evidence-family threshold was not weakened merely to increase trade frequency.
- TREND and independent-family requirements remain intact.
- ATR/ADX remain regime gates in ADAPTIVE_EVIDENCE.
- The single-symbol execution coordinator still manages one net position per bot/symbol.
- Exchange/MT5 live-only order semantics are not fabricated inside the historical simulator.

## Regression checks

Run the repository tests after every production source change:
- Crypto engine syntax/import + synthetic backtest
- Crypto GUI smoke
- Forex engine syntax/import + synthetic backtest
- SINGLE_SIGNAL conflict fail-closed behavior
- Evidence-family decision behavior
- R5 configuration fields/defaults

## Operational recommendation

Run the updated bot on demo/testnet first and inspect DecisionReason, Evidence-family counts, ATR gate and ADX gate in the execution log. This makes the next overnight test easier to diagnose.
