# V8.3 Adaptive Strategy Specification

## Core idea

V8.3 separates **directional evidence** from **market-regime gates**.

The 19 modules remain available:

1. Supertrend
2. EMA
3. EMA Cross
4. MACD
5. RSI
6. Bollinger Bands
7. Stochastic
8. VWAP
9. VWAP Delta
10. VIDYA
11. Nadaraya-Watson Envelope
12. Liquidity Swings
13. Trendline Breakout
14. 4H MTF
15. Volume
16. ADX
17. ATR
18. Divergence
19. Volume S/R

## Adaptive weighting

| Module | Weight |
|---|---:|
| ST | 1.50 |
| EMA | 1.00 |
| EMA_CROSS | 1.25 |
| MACD | 1.25 |
| RSI | 1.00 |
| BB | 0.75 |
| STOCH | 0.75 |
| VWAP | 1.25 |
| VWAP_DELTA | 1.00 |
| VIDYA | 1.25 |
| NWE | 1.00 |
| LIQ_SWING | 1.50 |
| TRENDLINE | 1.50 |
| MTF | 2.00 |
| DIVERGENCE | 1.75 |
| VOL_SR | 1.50 |
| VOL | 0.50 |
| ADX | 1.25 |
| ATR | 0.50 |

The weights are not probabilities and are not a guarantee of predictive power. Their purpose is to prevent a large number of correlated indicators from being treated as equally independent evidence.

## Entry rule

For each completed candle:

- calculate bullish and bearish module states;
- ignore modules with simultaneous bullish/bearish conflict;
- sum the configured module weights by side;
- calculate:

`edge = abs(weight_buy - weight_sell) / (weight_buy + weight_sell)`

A side can trigger only when:

- its weighted score is at least Adaptive Minimum Weight;
- it is strictly greater than the opposite weighted score;
- Edge is at least Adaptive Edge;
- ATR/Volume/ADX gates pass when enabled;
- 4H MTF direction agrees when MTF is enabled.

VOL and ATR are therefore not counted twice as both a gate and a directional candle vote in Adaptive mode.

## Risk hardening

- Daily DD uses daily peak equity.
- Session peak equity is persisted.
- Stale market data is rejected.
- Three consecutive execution-cycle failures stop the worker.
- Emergency loss scope defaults to the bot's active symbol.
- Normal cleanup prefers bot-managed order IDs.

## Why this is different from simply adding more indicators

The objective is to make the decision layer more robust to indicator correlation and market regime changes rather than increasing the raw number of signals.