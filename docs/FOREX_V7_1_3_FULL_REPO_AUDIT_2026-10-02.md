# Forex MT5 V7.1.3 — Full Repository Audit
Date: 2026-10-02

## Scope
Audited the GitHub repository `vtejas1982-spec/Universal-Futures-Trading-Bot` and the supplied Forex sources:
- `UniversalForexBot_MT5_V7_1_3_AUDITED.py`
- `UniversalForexBot_MT5_V7.1.2_LOW_MEMORY(1).py`

The Forex production source remains MT5/Forex-native. Crypto/futures execution code is not used as the runtime broker layer.

## Release synchronization
- Canonical production file: `UniversalForexBot_MT5.py`
- V7.1.3 audited artifact: `UniversalForexBot_MT5_V7_1_3_AUDITED.py`
- V7.1.2 low-memory reference: `UniversalForexBot_MT5_V7.1.2_LOW_MEMORY.py`
- Config schema: 71
- Runtime schema: 71
- V7.1.3 local SHA-256: `b113440cc1e75d15ee167f0938d2e0c0b9be061341c21a6cd2576c298bb42baf`

## Source-level validation
- AST parse: PASS
- Python `py_compile`: PASS
- V7.1.2 AST parse: PASS
- V7.1.2 `py_compile`: PASS
- No duplicate top-level assignment names detected.
- StrategyEngine, UniversalFuturesBotGUI, MT5ForexAdapter and MultiBotHub are present.
- Forex-only exchange override is present and rejects non-MT5 exchange IDs.
- MT5-native symbol/tick/position/order APIs are present.

## AI council / signal safety
Verified in V7.1.3:
- 2-family fallback refuses to fire when an opposing qualified family is present.
- BUY+SELL council split is represented by `split_council` and forces no trade.
- Ambiguous BUY+SELL signal is explicitly blocked with `AMBIGUOUS_CANDLE`.
- A 30,000-case randomized council run produced 0 simultaneous BUY/SELL outcomes.
- A 30,000-case randomized fallback check produced 0 opposing-qualified-family fallback violations.

## Execution / protection
Verified:
- MT5 broker-side SL is installed on the actual position.
- TP1/TP2 are bot-managed for Forex/MT5; the broker-side SL remains the hard protection.
- Minimum-lot TP split failure is handled before leaving the position unprotected; a minimum-size position is configured to close as a whole at TP1.
- Break-even modification retries once and verifies the broker SL. If verification fails, the original broker SL remains active.
- MT5 lot sizing uses broker volume_min/volume_max/volume_step and step-safe rounding.
- Startup validation checks SL/TP ordering and risk-vs-drawdown/emergency thresholds.

## Low-memory / lifecycle
The V7.1.2 low-memory source retains the lazy-profile/resource-guard architecture. The V7.1.3 source also retains:
- Windows available-RAM/RSS resource guard
- active-engine limits
- scanner preflight limits
- kill-switch latch
- profile and capital-authority state
- Hub callback budget controls.

## Repository hygiene findings
The repository previously contained historical regression tests that referenced retired source files that are not present in the repository. Those obsolete Forex tests were removed from the active test suite and replaced by `tests/test_forex_v713_audit.py`.

Historical Crypto/V8 documents remain as history/reference material; they are not treated as the current Forex production source.

## Runtime limitation
A live MetaTrader 5 terminal/broker session was not available in this audit environment. Therefore:
- no live order was sent;
- broker-specific execution/filling behavior was not claimed as live-verified;
- paper/stub/static tests do not substitute for Demo validation.

## Final status
**Source synchronization: PASS**
**Static audit: PASS**
**Council regression contract: PASS**
**MT5 execution safety contract: PASS**
**Live MT5 terminal validation: PENDING**

Do not treat this report as proof of profitability or live-broker correctness. Demo validation remains required before live deployment.
