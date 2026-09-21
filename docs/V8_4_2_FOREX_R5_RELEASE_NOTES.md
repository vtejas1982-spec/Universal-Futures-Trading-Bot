# V8.4.2-R5 Forex / MT5 Release Notes

## Fixed
- Added fail-safe Max Open Trades control; values above 1 are normalized to 1 because the current single-symbol coordinator manages one net position per bot profile.
- Fixed the Forex GUI cooldown widget row collision.
- Added ATR Dynamic SL/TP parity with the Crypto R5 contract.
- ATR uses the latest completed candle.
- ATR SL = 1.50 × ATR.
- TP1 = 1.20 × the actual ATR-derived SL distance.
- TP2 = 2.20 × the actual ATR-derived SL distance.
- Protection prices are based on the actual filled entry.
- ATR configuration is persisted through config schema 9.
- Static ROI-to-price settings remain available as fallback settings.
- New-profile Evidence-family defaults are aligned with the R5 strategy contract.
- Backtester R5 uses the canonical R5 live wrapper and records deterministic raw-OHLCV results.

## Added
- max_open_trades
- atr_sl_mult
- atr_tp1_mult
- atr_tp2_mult
- R5 Protection / Execution GUI section
- Forex R5 strategy-parity backtester
- Forex R5 audit test suite

## Validation
- 26/26 deterministic audit checks PASS.
- GUI smoke test PASS.
- Config save/load round-trip PASS.
- Synthetic raw-OHLCV backtest PASS.
- SINGLE_SIGNAL conflict fail-closed PASS.
- Evidence-family decision contract PASS.

## Safety
The current execution coordinator remains one-net-position-per-bot/symbol. This release does not claim two independent MT5 positions from one profile.

Demo/paper validation is still required for broker-side order lifecycle, actual fills, stop levels, partial TP behavior and recovery.
