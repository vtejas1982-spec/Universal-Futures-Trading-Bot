# V8.4.1 Engine Audit — 2026-09-21

## Scope

This audit covered the V8.4.0 crypto live engine, the recovery/multi-bot engine, and the crypto strategy-parity backtester.

## Fixed

### Live V8.4.1
- Fixed multiple syntax/indentation corruptions in HMA, NWE, metrics, Neutral Grid state handling, estimated-window logic, and the reversal path.
- Removed the obsolete duplicate `UniversalFuturesBotGUI` class definition.
- Removed duplicate top-level Liquidity Swings and Trendline Breakout implementations.
- Added persistence for `evidence_min_families`, `evidence_family_min_score`, `evidence_require_trend`, and `evidence_require_independent`.
- Bumped the audited build identifier to V8.4.1.

### Recovery / Multi-Bot
- Fixed the unexpected-indentation corruption in the live-position parser around entry/leverage/margin extraction.
- Bumped the audited recovery build identifier to V8.4.1.

### Backtester
- Fixed NWE and metrics syntax corruption.
- Changed the default signal mode from `ADAPTIVE_SCORE` to `ADAPTIVE_EVIDENCE` to match the current live engine default.
- Hardened the 4H MTF filter so it accepts either `datetime` or millisecond `time` input.
- Bumped the audited backtester build identifier to V8.4.1.

## Validation
- All three files: AST parse PASS.
- All three files: `py_compile` PASS.
- Live, recovery and backtester import smoke tests PASS with the exchange connector stubbed.
- Synthetic backtester build and execution PASS.
- Backtester input without `datetime` PASS after MTF hardening.
- All 19 strategy modules: indicator-build smoke tests PASS.
- All supported signal modes: PASS.
- All supported Grid modes: PASS.
- StrategyEngine direct decision smoke tests: PASS.
- Live file now contains one `UniversalFuturesBotGUI` definition and no duplicate top-level strategy-module definitions.

## Important limitation

This is a source-code and deterministic synthetic-test audit. It is not proof of safe live trading. Exchange-specific order behavior, trigger semantics, permissions, latency, fills, funding, liquidation and account-mode behavior still require demo/testnet validation before live use.
