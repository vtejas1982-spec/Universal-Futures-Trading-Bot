# V8.2.5 Backtester Parity Specification

## Source basis
The backtester was built from the uploaded V8.2.4 live bot and the previously supplied V8 multi-strategy backtester reference.

## Live modules covered
1. Supertrend
2. EMA Filter
3. EMA Cross
4. MACD Cross
5. RSI Cross/Zone
6. Bollinger
7. Stochastic
8. VWAP
9. VWAP Delta
10. Volumatic VIDYA
11. Nadaraya-Watson Envelope
12. Liquidity Swings
13. Trendline Breakout
14. 4H MTF
15. Volume
16. ADX
17. ATR

## Signal contract
- SINGLE_SIGNAL
- ANY_NON_CONFLICTING
- SCORE
- 2_SIGNALS
- 3_SIGNALS
- 4_SIGNALS
- STRICT_ALL_FILTERS

## Execution model
- Completed-candle evaluation.
- Normal strategy entry at next candle open.
- Actual-entry-based SL/TP conversion.
- PRICE_% and ROI_% protection.
- TP1/TP2 quantity split.
- TP1 break-even.
- Hold-All-Reverse with optional threshold WAIT mode.
- Post-SL/UNKNOWN opposite-signal lock.
- No same-candle re-entry and cooldown.
- Daily drawdown and emergency capital-loss stop.

## Grid model
- DIRECT_SHOT
- LONG_GRID
- SHORT_GRID
- NEUTRAL_GRID
- Grid levels, spacing, size increase, basket TP, global SL, maximum exposure, Grid DD, trend filter, score minimum, recenter and cooldown.
- NEUTRAL_GRID direction follows Supertrend when configured, otherwise the complete enabled strategy score.

## Backtest-only assumptions
- OHLC range touch fills historical Grid limits.
- If SL and TP are both touched within one candle, SL is processed first.
- Funding, liquidation, latency, order-book depth and exchange-specific trigger quirks are not fabricated.

## Known live correction
- V8.2.5 changes the default Grid Global SL to 6.0% because 5 levels × 1.0% spacing requires a Global SL strictly greater than 5.0%.