# V8.4.2-FOREX-AI-AGENT-R6.5 — Forex/MT5 AI-Agent parity release

Date: 2026-09-28

## Purpose

`UniversalForexBot_MT5.py` is now the Forex/MT5 implementation of the Crypto AI-Agent R6.5 strategy contract while keeping execution broker-native to MetaTrader 5.

The strategy contract is synchronized with `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5.py`: the same Evidence Families, same `StrategyEngine`, same AI-Agent controls, same recommended preset values, and the same bounded AI risk/SL/TP envelopes.

## Added

- AI_AGENT signal mode for Forex/MT5.
- AI-Agent confirmation dialog:
  - YES = apply `AI_AGENT_RECOMMENDED_R6.5`.
  - NO = keep current settings and leave AI_AGENT selected.
- Six AI council controls:
  - AI Min Families
  - AI Min Edge
  - AI Family Confidence
  - AI Max Conflicts
  - AI Require Trend
  - AI Require Structure
- Max Open Trades control normalized to the MT5 single-position contract of 1.
- AI dynamic trade-management contract:
  - Risk: 0.20%–0.50% per accepted trade.
  - SL: 1.50–2.40 ATR.
  - TP1: 1.00–1.50R.
  - TP2: 2.00–3.00R.
- AI effective-risk logging after an accepted signal.
- Forex backtester rebuilt around the R6.5 strategy/risk/protection contract.
- Backtester support for spread/slippage assumptions, session filter, Friday protection, daily profit/loss controls, loss-streak guard and post-SL opposite lock.
- Backtester metrics including net P/L, return, win rate, profit factor, average R and maximum drawdown.
- Regression test for Forex/AI-Agent parity.
- Log controls retained/enhanced: Copy Log, Clear Log and Auto Scroll.

## Fixed / Modified

- Replaced the Forex `StrategyEngine` with the same R6.5 AI-aware implementation used by Crypto.
- Synchronized all shared core indicator calculations with the Crypto R6.5 engine, including ADX and Volume/SR base-series logic.
- Added the missing AI runtime arguments to signal and diagnostic paths.
- Added deterministic AI manager reuse for Forex risk/SL/TP calculation.
- AI protection uses the completed-candle ATR and the actual MT5 fill/position values through the existing MT5 protection adapter.
- Implemented `MIN_FAMILIES` reversal evaluation for the existing Hold-All-Reverse option; `ALL_ACTIVE` remains available.
- Configuration migration advances Forex to schema 16 and preserves MT5 credentials, broker mode and symbol identity.
- The shared AI preset is byte-for-value equivalent to the Crypto R6.5 preset; Forex-only execution controls remain outside the strategy contract.
- Removed duplicate global Bollinger/Stochastic/VWAP function definitions from the local Forex source.

## Intentionally Forex-native

The following are not copied from Crypto and remain MT5-specific:

- MT5/PAPER/TERMINAL/LIVE connection modes.
- Broker symbol/suffix discovery.
- MT5 lot size, volume step, min/max volume and price precision.
- MT5 `order_calc_profit` / margin-based sizing and P/L.
- MT5 market order placement and position discovery.
- MT5 SL/TP modification, reconciliation, trailing and recovery.
- Existing Forex session, spread, slippage, news and correlation guardrails.

## Backtester model notes

- Signals are evaluated on completed candles.
- Entry is modeled at the next bar open.
- Same-bar SL precedence is conservative when both SL and TP extremes are touched.
- TP1 realizes the configured partial quantity and can move the remaining stop to entry.
- Remaining open positions are force-closed at the final test close and marked `FORCED_CLOSE_END`.
- P/L formula is `price distance × lots × contract size`, which is directly suitable for USD-quoted pairs such as EURUSD. Cross-currency pairs need quote-currency conversion for exact account-currency reporting.
- Economic-calendar/news execution effects are not reconstructed from historical feeds by this backtester.

## Validation

- Python compilation: PASS.
- StrategyEngine AST parity against Crypto R6.5: PASS.
- Shared AI preset value parity: PASS (134/134 values equal).
- AI council decision smoke test: PASS.
- AI risk/SL/TP hard-envelope test: PASS.
- Forex backtester smoke test: PASS.
- GUI initialization under Xvfb: PASS.
- AI preset confirmation/save/load GUI contract: PASS.
- Duplicate StrategyEngine/global strategy methods audit: PASS.
