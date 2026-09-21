# Crypto V8.4.2-R5 Release Notes

## Production files
- `UniversalFuturesBot_CRYPTO.py`
- `UniversalFuturesBot_CRYPTO_BACKTESTER.py`

## Fixed
- Max Open Trades values above 1 normalize safely to 1 net position for the current single-symbol coordinator.
- ATR Dynamic protection has safety bounds.
- Evidence-family execution parameters remain explicit through the worker/strategy path.
- Removed the pandas FutureWarning in the Volume/S/R aggregation path.
- Corrected the backtester release metadata so it is explicitly R5 rather than carrying stale V8.3.3/V8.3.1 branding.

## Added
- R5 strategy-parity backtester.
- Raw OHLCV/DataFrame/CSV research input.
- Evidence-family configuration.
- Completed-candle MTF.
- Causal divergence and Volume/S/R.
- ATR Dynamic SL/TP contract.
- Risk, cooldown, drawdown, loss-streak and post-SL lock simulation.
- Conservative same-bar SL-first ambiguity handling.

## Protection contract
- SL = 1.50 × completed-candle ATR.
- TP1 = 1.20 × actual SL distance.
- TP2 = 2.20 × actual SL distance.
- Live protection uses actual filled entry and actual position quantity.

## Validation
- Engine audit: 27/27 PASS.
- GUI smoke: PASS.
- Synthetic raw-OHLCV backtest: PASS.

## Limitation
Backtesting cannot prove exchange order acceptance, partial fills, trigger semantics, latency, websocket failures or live reconciliation.
