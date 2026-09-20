# V8.3.1 Adaptive Strategy Specification

## V8.3.1 execution contract

V8.3.1 retains the V8.3 Adaptive strategy but makes Adaptive thresholds explicitly per-call/per-profile.

A bot worker passes adaptive_edge and adaptive_min_weight directly to the pure StrategyEngine.

They are not stored as mutable class-level state. This prevents one running bot profile from overwriting another profile's thresholds.

## Core strategy

V8.3 separates directional evidence from market-regime gates.

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

These are engineering weights, not probabilities.

## Entry rule

For each completed candle:

- calculate bullish/bearish module states;
- ignore simultaneous bull/bear module conflicts;
- sum weights by direction;
- calculate edge = abs(weight_buy - weight_sell) / (weight_buy + weight_sell).

A side can trigger only when weighted score is at least Adaptive Minimum Weight, is strictly greater than the opposite side, Edge is at least Adaptive Edge, enabled ATR/Volume/ADX gates pass, and enabled 4H MTF direction agrees.

VOL and ATR are not double-counted as both directional evidence and regime gates in Adaptive mode.

## Risk hardening

- Daily DD uses daily peak equity.
- Session peak equity is persisted.
- Stale market data is rejected.
- Three consecutive execution-cycle failures stop the worker.
- Emergency loss scope defaults to the active bot symbol.
- Normal cleanup prefers bot-managed order IDs.

## Backtester parity

The backtester accepts the same Adaptive Edge and Minimum Weight values explicitly and uses the same decision contract.

This prevents a hidden global setting from changing historical results.
