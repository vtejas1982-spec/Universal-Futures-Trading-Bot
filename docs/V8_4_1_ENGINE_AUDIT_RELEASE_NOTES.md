# V8.4.1-R2 Follow-up Engine Audit — 2026-09-21

This document records the second full pass over the crypto live bot, strategy engine, GUI/configuration system, Grid/backtester path and the V8.2 safety requirements.

## Findings and fixes

### Live strategy engine
- The complete core indicator function set is present in the final live source: RMA, Supertrend, ADX, MACD, RSI, WMA, RSI-MA, HMA, VWAP Delta, VIDYA and Nadaraya-Watson Envelope.
- `SINGLE_SIGNAL` now fails closed when both bullish and bearish directional modules are active.
- `ADAPTIVE_EVIDENCE` diagnostics now apply the same Minimum Families, Family Minimum Score, Require Trend Family and Require Independent Non-Trend Family controls as the actual decision.
- REGIME remains a gate only; ATR/ADX are not counted as independent directional families.

### GUI / configuration
- Section 3 remains organized into TREND, MOMENTUM, FLOW, STRUCTURE, REGIME, OPTIONAL/LEGACY and DECISION ENGINE.
- Divergence `Min Div` exists and is persisted.
- `Use all divergence sources` now has an explicit user-action callback and persists through configuration.
- Startup strategy/risk/SL/TP validation now runs before leverage/order setup.
- Legacy configuration loading reports schema migration while preserving explicitly saved values.

### Backtester
- `run_backtest()` now accepts raw OHLCV with millisecond `time` and creates `datetime` automatically.
- `run_backtest()` now builds the strategy indicator frame when callers provide raw OHLCV instead of a prebuilt frame.
- Duplicate top-level Liquidity Swings and Trendline Breakout definitions were removed.
- Backtester SINGLE_SIGNAL and Evidence diagnostic behavior now matches the live engine.

## V8.2 safety requirements rechecked

- actual filled entry/quantity before protection calculation
- fail-closed SL/TP/BE verification
- managed-order ownership and orphan-order protection
- Grid order verification/cancellation
- Grid exposure and drawdown controls
- Hold-All-Reverse and Hold-SL WAIT
- post-SL opposite-signal lock
- same-candle protection
- symbol normalization
- profile locking and multi-bot isolation
- stale-data and consecutive-cycle-error safety
- emergency-stop scope

## Validation

**60 PASS / 0 FAIL / 0 SKIP**

The deterministic suite covers:
- live/backtester/recovery AST and compile
- duplicate-definition guards
- core indicator presence
- Evidence-Family strategy behavior
- SINGLE_SIGNAL conflict behavior
- regime-gate behavior
- Evidence diagnostic parity
- protection fail-closed behavior
- full 19-module indicator chain
- Volume S/R state
- GUI construction and critical controls
- configuration save/load
- startup preflight
- direct raw-OHLCV backtest execution

This remains a source-code and deterministic/synthetic audit. Exchange-specific live execution, fees, funding, latency, trigger semantics and liquidation behavior still require demo/testnet validation.
