# Current Release Manifest — R6.8.7.12

## Active Crypto AI-Agent release
- Release: **V8.4.2-CRYPTO-AI-AGENT-R6.8.7.12**
- Live engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.12.py`
- Backtester: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.12_BACKTESTER.py`
- Windows build: `BUILD_CRYPTO_AI_AGENT_R6.8.7.12_EXE.bat`
- Convenience launcher: `backtest.py`
- Config schema: **33**
- Runtime schema: **24**
- Signal mode: **AI_AGENT**
- Full audit: `docs/R6.8.7.12_FULL_AUDIT_R5.md`
- Contract tests: `tests/test_crypto_ai_agent_r6_8_7_12_contract.py`

## AI-Agent contract
- Minimum families: 3
- Edge: 0.20
- Family confidence: 0.55
- Family participation: 0.35
- Trend required: ON
- Structure required: ON
- Maximum family conflicts: 1
- 2-family fallback: ON
- 2-family edge: 0.65
- 2-family confidence: 0.65
- 2-family participation: 0.40
- Adaptive ATR: ON
- Adaptive ATR quantile: 0.30
- Adaptive ATR floor: 0.10%
- AI SL: 1.95 ATR
- AI TP1: 1.35R
- AI TP2: 2.70R

## R6.8.7.12 R5 fixes
- 2F `None` runtime crash fixed.
- Divergence zero-source fatal startup fixed with fail-closed optional-module disable.
- `div_use_all` preset/profile synchronization fixed.
- Final worker runtime snapshot refresh added after startup leverage mutations.
- Backtester now has a real AI_AGENT decision path, causal adaptive ATR and leverage-tier risk caps.

## Validation
- Live engine compile: PASS
- Backtester compile: PASS
- Backtester AST parse: PASS
- AI council smoke test: PASS
- 150x risk-cap smoke test: PASS
- Synthetic OHLCV end-to-end backtest: PASS
- Bybit Demo remains required for final exchange-side validation.

## Repository cleanup
Superseded Crypto AI-Agent root copies and build scripts through R6.8.7.11 were removed from the active tree. They remain recoverable through Git history. The only currently active Crypto AI-Agent root release is R6.8.7.12.
