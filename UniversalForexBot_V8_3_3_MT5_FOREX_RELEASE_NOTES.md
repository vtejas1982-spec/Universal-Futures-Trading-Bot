# Universal Forex Bot V8.3.3 — MT5 Forex Only

## Reference
Built from the latest supplied `UniversalForexBot_V2_MT5_ALL_FEATURES_READY.py` Forex/MT5 engine, with the latest V8.3.3 crypto strategy contract used as the strategy reference.

## V8.3.3 Forex strategy

19 strategy modules are available:

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
18. Confirmed Divergence
19. Volume S/R

Adaptive Score uses the V8.3.3 weighted contract with Edge 0.18 and Minimum Weight 3.5 by default. Adaptive parameters are passed explicitly per decision.

## Forex-only execution

- MT5 is the only selectable platform.
- Crypto/futures exchange selection is blocked at runtime.
- MT5 Paper / Terminal / Live modes remain available.
- Broker symbol auto-discovery and suffix handling are retained.
- Forex spread, slippage, session, Friday, daily loss/profit, loss-streak, trailing, ATR-SL, news and correlation guardrails from the supplied Forex V2 engine are retained.
- Magic-number and position recovery support are retained.

## Strategy safety

- Completed candles are used for decisions.
- Confirmed-pivot divergence is causal and does not use future pivots.
- Liquidity and trendline modules use confirmed pivots.
- Volume S/R is causal and multi-timeframe aligned.
- NWE repainting remains OFF by default.
- Hold-All-Reverse and post-protection re-entry safeguards remain available.

## Backtest

`UniversalForexBot_V8_3_3_MT5_FOREX_BACKTESTER.py` imports the exact Forex V8.3.3 strategy implementation rather than maintaining a separate copy of the indicators. This reduces live/backtest strategy drift.

The backtester supports Forex OHLCV CSV input, Adaptive modes, risk sizing, spread/slippage, SL/TP, partial TP, break-even after TP1, session/Friday filters and drawdown-related controls.

## Validation

`test_forex_v833.py`: **6/6 PASS**

Validated:
- compile/import
- 19-module contract
- Adaptive decision parity
- full strategy-frame construction
- deterministic synthetic backtest
- Forex-only runtime guard

The deterministic synthetic test completed successfully. Synthetic results are engineering validation only and are not a forecast of live Forex performance.
