# V8.2.6 — Advanced Strategy Modules + Backtester Parity

## Added

### 1. Divergence for Many Indicators module
Ported the supplied **Divergence for Many Indicators v4** logic into the live strategy engine and the historical backtester.

Supported divergence sources:
- MACD
- MACD Histogram
- RSI
- Stochastic
- CCI
- Momentum
- OBV
- Volume-weighted MACD
- Chaikin Money Flow
- Money Flow Index

Settings include:
- Pivot Period
- Pivot Source: Close / High-Low
- Divergence Type: Regular / Hidden / Regular+Hidden
- Minimum number of divergences
- Maximum pivot points
- Maximum bars to check
- CCI and Momentum periods
- Fresh divergence vs persistent divergence state
- Individual source-indicator enable switches

The original chart drawing, labels and alert objects are represented as numeric strategy states. **Unconfirmed / future-looking divergence is not allowed in the trading engine.** Pivots are confirmed before they can generate a signal.

### 2. Volume-based Support & Resistance Zones module
Ported the supplied **Volume-based Support & Resistance Zones V2** fractal logic.

Supported:
- Four configurable S/R timeframes
- Chart / 15m / 30m / 1h / 4h / D / W / Disable
- Volume MA threshold
- MAJORITY / ANY / ALL timeframe vote
- CURRENT_ZONE / FRESH_BREAK entry mode

The original TradingView line/label/fill drawing objects are intentionally not reproduced as execution objects. Their numerical support/resistance zone states are used for directional strategy voting.

### 3. Strategy engine expanded
The V8 directional module contract now contains:
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
11. NWE
12. Liquidity Swings
13. Trendline Breakout
14. MTF
15. Volume
16. ADX
17. ATR
18. Divergence
19. Volume S/R

Both new modules participate in:
- SINGLE_SIGNAL
- ANY_NON_CONFLICTING
- SCORE
- 2/3/4_SIGNALS
- STRICT_ALL_FILTERS
- Grid SCORE / NEUTRAL_GRID direction logic
- Hold-All-Reverse persistent reversal checks

## Fixed / Hardened

- Configuration schema bumped from 5 to **6** because new strategy settings were added.
- Backtester module count and combination laboratory now include both new modules.
- Backtester validation covers all new settings and rejects invalid divergence/S/R configurations.
- Backtester now requests enough historical warmup for configured higher-timeframe Volume S/R analysis.
- Higher-timeframe S/R states are aligned at the **close of the higher-timeframe candle**, preventing future-data leakage.
- The previous CCXT market-loading hotfix remains included.
- The previous Grid default correction remains included: **Global Grid SL = 6.0%** with 5 levels × 1% spacing.
- Removed an old unused backtester `decide()` undefined-`df` dependency.
- Added advanced live signal logging for confirmed divergence and fresh Volume S/R events.

## Modified

- Live Strategy tab now has an Advanced Strategy Modules section.
- Live save/load configuration includes every new setting.
- Grid validation counts the new directional modules.
- Backtester JSON import/export includes the new settings.
- Combination Lab can generate combinations involving DIVERGENCE and VOL_SR.
- Persistent Hold-All-Reverse state now includes the new modules.

## Important execution-model note

The backtester remains a historical OHLC model. It does not claim to reproduce:
- exchange order-book depth
- network latency
- partial fills
- funding
- liquidation engine behavior
- exchange-specific trigger execution
- exact live higher-timeframe feed timing in every exchange condition

Those differences must be validated on demo/testnet before live deployment.

## Validation

- Live bot AST parse: PASS
- Backtester AST parse: PASS
- Backtester import with CCXT stub: PASS
- 19-module contract: PASS
- New divergence/S/R columns: PASS
- All-module synthetic voting: PASS
- Normal synthetic backtest: PASS
- NEUTRAL_GRID synthetic backtest: PASS
- Signal-engine regression: PASS