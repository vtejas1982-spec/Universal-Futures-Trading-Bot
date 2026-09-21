# V8.4.2-R5 Crypto Release Notes

## Fixed
- R5 is based directly on the V8.4.2-R3 hardened live engine.
- Max Open Trades values above 1 no longer abort startup; they normalize to 1 because the current single-symbol coordinator manages one net position.
- Added safety upper bounds for ATR Dynamic SL/TP multipliers.
- Preserved explicit Evidence-family runtime propagation, including evidence_min_families and evidence_family_min_score.
- Removed the pandas FutureWarning in Volume/S-R aggregation.

## Added
- Strategy-parity backtester for the R5 live engine.
- Raw OHLCV/DataFrame/CSV backtesting.
- Completed-candle ATR Dynamic SL/TP: 1.50 ATR SL, TP1 1.20x actual SL distance, TP2 2.20x actual SL distance.
- Evidence-family decision contract.
- Completed 4H MTF alignment, causal divergence, Volume/S-R and existing grid simulation.
- Next-candle-open entry model and conservative same-bar SL-first ambiguity rule.
- Risk sizing, fees, cooldown, daily loss, drawdown, loss-streak and post-SL lock simulation.
- Deterministic engine audit and GUI smoke tests.

## Modified
- Version/build markers moved to V8.4.2-R5.
- Backtester defaults synchronized to ADAPTIVE_EVIDENCE / 2 families / .35 family score / Trend + independent family / Edge .18 / ATR Dynamic 1.50 / 1.20 / 2.20.
- ATR remains a regime gate and is not counted as a directional evidence family.

## Validation
- 27/27 deterministic local engine checks PASS.
- GUI smoke PASS.
- Synthetic raw-OHLCV backtest PASS.

## Limitation
Historical backtesting cannot prove exchange order acceptance, trigger semantics, partial fills, network recovery or broker-side reconciliation. Demo validation remains required.
