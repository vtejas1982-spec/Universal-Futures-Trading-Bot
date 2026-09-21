# V8.4.0 Crypto + Forex Evidence Hardened

## Crypto
- Added `UniversalFuturesBot_V8_4_0_CRYPTO_EVIDENCE_HARDENED.py`.
- Preserves the V8.3 crypto futures execution architecture and exchange support.
- Adds `ADAPTIVE_EVIDENCE` using independent evidence families.
- TREND: ST, EMA, EMA Cross, MACD, VIDYA, NWE.
- MOMENTUM: RSI, Stochastic, Divergence.
- FLOW: VWAP, VWAP Delta, Volume, Volume S/R.
- STRUCTURE: Liquidity Swings, Trendline Breakout, MTF.
- REGIME: ATR and ADX gates only.
- Default: minimum 2 independent families, family threshold 0.35, edge 0.18, Trend required, independent non-Trend family required.
- Existing legacy signal modes remain available.
- Matching crypto backtester: `UniversalFuturesBot_V8_4_0_CRYPTO_BACKTESTER_EVIDENCE.py`.

## Forex
- V8.4 MT5 Forex Evidence Hardened remains a separate Forex implementation.
- Forex keeps MT5 execution, broker-side protection, runtime checkpointing, profile locking, stale-data protection, emergency scope and other V8.3.4 hardening.

## Rule
Strategy changes are maintained in both Crypto and Forex implementations, with matching backtest/regression coverage and GitHub updates.

Backtests remain historical OHLC approximations and are not guarantees of live performance.
