# V8.2.6 Advanced Strategy Modules Specification

## Source basis

This update uses the user-supplied:
- Divergence for Many Indicators v4 (MPL 2.0, © LonesomeTheBlue).
- Volume-based Support & Resistance Zones V2.

The live V8.2.5 bot and V8.2.5 strategy-parity backtester were extended together so the same new settings and directional-module contract are available in both.

## New directional modules

### DIVERGENCE

The numerical strategy port supports:
- MACD
- MACD Histogram
- RSI
- Stochastic
- CCI
- Momentum
- OBV
- VWMACD
- Chaikin Money Flow
- Money Flow Index

Settings:
- Pivot Period: 1-50
- Source: Close / High-Low
- Divergence Type: Regular / Hidden / Regular+Hidden
- Minimum Divergence Count
- Maximum Pivot Points
- Maximum Bars to Check
- CCI period
- Momentum period
- Fresh / Current-State entry mode
- Individual source enable switches

Safety:
- Trading signals use confirmed pivots only.
- The source's "Don't Wait for Confirmation" mode is not used for execution.
- Chart-only lines, labels and alerts become numerical strategy states.

### VOL_SR

Numerical strategy port of the supplied Volume-based Support & Resistance Zones V2.

Settings:
- Four timeframes
- Volume MA threshold
- MAJORITY / ANY / ALL timeframe vote
- CURRENT_ZONE / FRESH_BREAK entry mode

The source's volume-confirmed five-bar fractal structure is used to create numerical resistance/support levels and zones. Chart line/fill/label objects are not execution objects.

## Strategy contract

The V8 contract now has 19 directional modules:

1. ST
2. EMA
3. EMA_CROSS
4. MACD
5. RSI
6. BB
7. STOCH
8. VWAP
9. VWAP_DELTA
10. VIDYA
11. NWE
12. LIQ_SWING
13. TRENDLINE
14. MTF
15. VOL
16. ADX
17. ATR
18. DIVERGENCE
19. VOL_SR

Both new modules feed:
- SINGLE_SIGNAL
- ANY_NON_CONFLICTING
- SCORE
- 2_SIGNALS
- 3_SIGNALS
- 4_SIGNALS
- STRICT_ALL_FILTERS
- Grid SCORE / NEUTRAL_GRID direction
- Hold-All-Reverse persistent reversal state

## Backtester parity

The backtester:
- builds the same divergence numerical states;
- builds multi-timeframe Volume S/R states;
- aligns higher-timeframe S/R availability to the higher-timeframe candle close;
- requests additional historical warmup for configured higher-timeframe S/R;
- exposes all new settings through GUI and JSON;
- includes the modules in the combination laboratory.

## V8.2.6 fixes

- Config schema: 5 -> 6.
- Added live save/load coverage for all new fields.
- Added Grid module-count coverage for the new modules.
- Fixed an unused compatibility helper that referenced an undefined df.
- Added advanced live event diagnostics.
- Retained the V8.2.5 CCXT market-loading hotfix and Grid default correction.

## Validation

Local V8.2.6 validation:
- Live bot AST parse: PASS
- Backtester AST parse/import: PASS
- 19-module contract: PASS
- Divergence/S/R indicator columns: PASS
- All-module synthetic voting: PASS
- Normal synthetic backtest: PASS
- NEUTRAL_GRID synthetic backtest: PASS
- Regression suite: 7/7 PASS

## Historical-model limitations

The backtester does not claim to reproduce exact exchange fills, latency, order-book depth, funding, liquidation, partial fills or exchange-specific conditional-order trigger semantics. Demo/testnet validation remains required before live deployment.
