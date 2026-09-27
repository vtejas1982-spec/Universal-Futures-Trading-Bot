# Crypto AI Agent R6.5 Backtester

Date: 2026-09-27

## Current file

UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5_BACKTESTER.py

## Purpose

This is the dedicated historical simulator for the current Crypto AI-Agent R6.5 engine. It was separated from the older generic R8 crypto backtester so the active repository no longer presents an older simulator as the current AI backtest.

## Strategy contract

The backtester includes the current R6.5 AI-Agent decision parameters:

- Minimum families: 3
- Minimum edge: 0.20
- Minimum family confidence: 0.55
- Maximum conflicting families: 1
- Trend required: ON
- Structure required: ON

## AI management

For accepted AI-Agent setups it simulates the bounded deterministic manager:

- Risk: 0.20% to 0.50%
- Stop: 1.50 to 2.40 ATR
- TP1: 1.00R to 1.50R
- TP2: 2.00R to 3.00R
- TP1 partial close followed by break-even on the remaining position.

The manager is rule-based; no external LLM is used.

## Simulation assumptions

- Signal is calculated from a completed candle.
- Entry is simulated at the following candle open.
- Conservative intrabar ambiguity: if SL and TP are both touched in one candle, SL is considered first.
- Fees and slippage are modeled inputs.
- Exchange-specific fills, funding, latency, order-book depth and trigger semantics cannot be perfectly reproduced.

## Root cleanup

The previous generic UniversalFuturesBot_CRYPTO_BACKTESTER.py was removed from the active root because it represented an older R8-era strategy contract. The R6.5 AI backtester is now the named AI backtest entry point.

## Test

Use Bybit or Binance public OHLCV data and run the backtester from PowerShell:

py ".\UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5_BACKTESTER.py" --exchange bybit --symbol BTC/USDT:USDT --timeframe 15m --start 2026-01-01 --end 2026-09-01 --capital 1000

Keep the R6.5 live engine in the same folder because the backtester imports its StrategyEngine and indicator functions.

## Important

Backtest outputs are historical research results. They do not establish future profitability or prove that the live exchange lifecycle will behave identically.


## Backtest parity note

The standalone R6.5 backtester intentionally does not fabricate a per-candle Volume S/R state from the live multi-timeframe chart module. Its default AI-Agent vote set uses the other Trend, Momentum, Flow and Structure inputs plus the live R6.5 StrategyEngine. This avoids claiming false indicator parity. The live production engine can still use Volume S/R when enabled.

For the closest production comparison, run the backtester on the same symbol/timeframe/date range and compare accepted signal timestamps and AI risk/SL/TP values with the live Demo logs.
