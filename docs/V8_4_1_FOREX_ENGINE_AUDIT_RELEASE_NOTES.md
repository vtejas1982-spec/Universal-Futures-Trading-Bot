# Universal Forex Trading Bot V8.4.1 — Engine / Strategy / GUI / Safety Audit R2

Date: 2026-09-21

## Scope
Follow-up audit against the V8.2 Engine Audit contract, applied to the MT5 Forex V8.4 Evidence-Family bot and matching backtester.

## Fixes and modifications
- Fixed `SINGLE_SIGNAL`: simultaneous BUY and SELL evidence now returns `NONE` instead of accepting the first module encountered.
- Synchronized `decision_reason()` with the actual Evidence-Family decision gates, including Trend-family and independent non-Trend requirements.
- Restored/validated the complete core indicator pipeline and checked duplicate top-level indicator definitions.
- Added a startup strategy/risk/SL-TP preflight gate before MT5 connection/login/order setup. Worker-side validation remains authoritative.
- Fixed worker signal-mode validation so `ADAPTIVE_EVIDENCE`, `ADAPTIVE_SCORE`, `ANY_NON_CONFLICTING`, and all legacy supported modes are actually accepted at runtime.
- Added config schema version 8 and migration logging while preserving existing saved values.
- Kept the Forex-only MT5 execution architecture and existing V2 safety extensions: broker-side SL reconciliation, fail-closed protection handling, entry idempotency after `order_send=None`, profile lock, runtime recovery, session/Friday/news/correlation/spread/slippage controls, trailing, ATR-SL, and risk stops.
- Fixed backtester NWE parameter parity with the live engine.
- Added a public `run_backtest()` API that accepts raw OHLCV with either `time` or `datetime`.

## Validation
- AST / compile: PASS
- GUI construction under Xvfb: PASS
- Default Evidence-Family preflight: PASS
- Invalid Evidence-family preflight gate: PASS
- Config save/load round-trip with schema 8: PASS
- SINGLE_SIGNAL conflict/single-side tests: PASS
- Evidence-family Trend + Momentum: PASS
- Regime-only evidence blocked: PASS
- ATR gate failure blocked: PASS
- Full 19-module strategy frame including NWE: PASS
- Raw OHLCV backtest API: PASS
- Deterministic audit suite: **7/7 audit groups PASS**

Synthetic backtest results are engineering validation only and are not evidence of live profitability or future performance.