# Universal Forex Trading Bot V8.4.0 — MT5 Forex Evidence Hardened

## Strategy architecture
V8.4.0 redesigns the strategy GUI and adaptive decision layer around five evidence families:

- TREND: Supertrend, EMA, EMA Cross, MACD, VIDYA, NWE
- MOMENTUM: RSI, Stochastic, Divergence
- FLOW: VWAP, VWAP Delta, Volume, Volume S/R
- STRUCTURE: Liquidity Swings, Trendline Breakout, MTF
- REGIME: ATR, ADX

Bollinger Bands remains available under Optional / Legacy so existing V8.3.x configurations do not lose functionality.

## Main strategy fix
The new `ADAPTIVE_EVIDENCE` mode normalizes evidence within each family instead of treating correlated trend indicators as independent votes.

- ATR and ADX are regime gates only.
- Volume is FLOW evidence.
- MTF is STRUCTURE evidence.
- ATR/ADX/MTF/Volume are not double-counted in the new adaptive evidence mode.
- Default minimum independent families: 2.
- Default family evidence threshold: 0.35.
- Default edge threshold: 0.18.
- Optional requirement for Trend family and at least one independent non-Trend family.

Legacy modes including `ADAPTIVE_SCORE`, `SCORE`, `2_SIGNALS`, `3_SIGNALS`, `4_SIGNALS`, `SINGLE_SIGNAL`, `ANY_NON_CONFLICTING`, and `STRICT_ALL_FILTERS` remain available.

## Preserved features
All existing V8.3.4 strategy calculations, indicator parameters, entry modes, SL/TP modes, risk controls, emergency scope, peak-equity drawdown protection, news/session/spread/slippage controls, profile locking, runtime recovery/checkpointing, broker-side protection reconciliation, trailing, TP1/BE, correlation controls, scanner, reconnect and Telegram controls are retained.

## Backtester parity
The matching V8.4 backtester imports the exact V8.4 strategy engine and supports the same family-aware decision contract.

Backtesting remains an OHLC approximation and is not an exact MT5 tick/execution simulator.

## Validation
Regression test suite: **7/7 PASS**.

Additional GUI smoke test under Xvfb: **GUI_INIT_OK** with default `ADAPTIVE_EVIDENCE` mode.

## Files
- `UniversalForexBot_V8_4_0_MT5_FOREX_EVIDENCE_HARDENED.py`
- `UniversalForexBot_V8_4_0_MT5_FOREX_BACKTESTER_EVIDENCE.py`
- `test_forex_v840_evidence.py`