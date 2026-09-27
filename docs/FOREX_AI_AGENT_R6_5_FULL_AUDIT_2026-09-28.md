# Forex MT5 AI-Agent R6.5 — Full Audit

Date: 2026-09-28

## Scope

This audit ports the Crypto AI-Agent R6.5 decision/risk/protection contract to the MT5 Forex engine while keeping broker execution, symbol handling, lot sizing and MT5 account modes Forex-native.

## Added

- AI-Agent R6.5 parity in the Forex GUI, configuration and runtime contract.
- AI-Agent preset: AI_AGENT_RECOMMENDED_R6.5.
- AI council controls: minimum families, edge, family confidence, maximum conflicts, trend requirement and structure requirement.
- Bounded AI risk management: 0.20%-0.50% risk per trade.
- Bounded AI ATR stop: 1.50-2.40 ATR.
- Bounded AI TP1: 1.00-1.50R.
- Bounded AI TP2: 2.00-3.00R.
- AI-aware lot sizing that preserves the dynamically selected stop distance.
- Liquidity Swing entry mode: FRESH_BREAK/CURRENT_TREND.
- Divergence minimum-count and FRESH/CURRENT_STATE entry controls.
- Forex GUI Grid Mode control; MT5 Forex keeps grid execution OFF-only.
- R6.5 Forex backtester with CSV and optional MT5 history input.
- Spread, slippage, commission and Forex tick-value/tick-size inputs in the backtester.
- TP1 partial exit and break-even simulation.
- Post-SL opposite-signal lock and capital drawdown guardrails.
- Regression tests covering compile, StrategyEngine parity, GUI contract and runtime bindings.

## Fixed

- AI risk/SL sizing mismatch: static Forex ATR sizing can no longer overwrite an AI-selected stop distance.
- Configuration migration no longer silently applies the entire AI preset to existing profiles. Existing saved values remain authoritative; only missing fields are initialized.
- GUI shutdown no longer performs blocking MT5 position/runtime operations directly on the Tk main thread.
- Execution log is bounded to prevent unbounded GUI text growth.

## Modified

- Forex config/runtime schema aligned to 21/22.
- Forex R6.5 AI-Agent strategy module parameters now mirror the Crypto R6.5 recommended profile.
- MTF backtest alignment is based on completed 4H candles to avoid look-ahead.
- Liquidity and divergence semantics are configurable and shared between entry and reversal logic.

## Intentionally Forex-native

- MetaTrader 5 terminal/account modes remain unchanged.
- Broker symbol discovery and MT5 position/order APIs remain Forex-specific.
- Forex lot sizing uses tick-size/tick-value instead of crypto contract sizing.
- MT5 does not expose the crypto exchange grid execution path; Grid Mode is therefore OFF-only.
- Forex protection continues using the MT5-native broker SL plus existing TP management rather than copying exchange-specific Bybit trigger parameters.

## Validation

Local static/regression validation passed for the patched engine and the R6.5 StrategyEngine contract. A deterministic synthetic-data backtest pipeline also completed successfully; zero trades in synthetic data is not a performance claim.

No live broker trade was executed as part of this audit.
