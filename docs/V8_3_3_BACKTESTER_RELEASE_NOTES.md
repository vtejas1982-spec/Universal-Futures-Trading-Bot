# V8.3.3 Strategy-Parity Backtester Release Notes

## Purpose

V8.3.3 keeps the historical backtester synchronized with the live V8.3.3 strategy/indicator contract.

Standing project rule:

> Whenever the live trading bot strategy/indicator/configuration behavior is changed, the matching backtester must be updated and regression-tested before the Python release is treated as complete.

## Changes

### 1. Exact Adaptive decision parity
The backtester now mirrors the live V8.3.3 StrategyEngine.decide_signal() and decision_reason() implementations.

Adaptive parameters are passed explicitly per configuration:
- Adaptive Edge: 0.18
- Adaptive Minimum Weight: 3.5 default
- Minimum score remains part of the effective threshold

No hidden mutable cfg_adaptive_* state is used by the backtester decision path.

### 2. Live Volume S/R parity

The V8.3.3 causal Volume S/R changes are synchronized into the backtester, including the completed-source-candle handling used by the live engine.

### 3. Pandas compatibility

The four Volume S/R boolean aggregation paths now use nullable Boolean dtype before fillna(False).sum().

This removes the pandas future-downcasting warning observed during a full-module synthetic backtest while preserving the boolean aggregation result.

### 4. Runtime-only safety boundary

V8.3.3 live protections such as retired managed-order ID persistence, strict open-order snapshot completeness, startup inventory ownership checks and live exchange preflight are runtime/exchange-state protections. They are documented in the backtester but are not invented as historical price signals.

## Validation

tests/test_v833_backtester_parity.py covers compile/import, 30+ shared top-level indicator/helper AST parity checks, exact StrategyEngine AST parity, Adaptive per-call parameter effectiveness, backtester profile parameter propagation, Volume S/R parity, deterministic synthetic full-module backtest and default-contract validation.

Result: **8/8 PASS**

The deterministic synthetic run completed with Divergence and Volume S/R enabled and produced finite equity/PnL metrics without pandas warnings.

## Historical-model boundary

The backtester remains a historical approximation. Normal entries use completed-candle signals and next-candle-open execution. Exchange-specific fills, latency, funding, liquidation, queue position, precision and conditional-order semantics are not perfectly reproducible from OHLCV data.

No profitability or future-performance claim is made.
