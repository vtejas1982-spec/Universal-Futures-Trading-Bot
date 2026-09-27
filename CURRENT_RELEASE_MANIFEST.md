# Current Release Manifest — 2026-09-28

This main branch contains the current active production code only. Superseded root-level bot copies have been removed; their history remains available in Git history.

## Live engines
- UniversalFuturesBot_CRYPTO_V8.4.2-R9.6.py — Crypto Futures production engine
- UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5.py — Crypto AI-Agent production/Demo engine
- UniversalForexBot_MT5.py — Forex/MT5 AI-Agent R6.5 production engine

## Backtesters
- UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5_BACKTESTER.py — AI-Agent strategy/risk/SL/TP backtester
- UniversalForexBot_MT5_BACKTESTER.py — Forex/MT5 AI-Agent R6.5 strategy/risk/SL/TP backtester

## Tests
- tests/test_crypto_engine.py
- tests/test_crypto_gui.py
- tests/test_forex_engine.py
- tests/test_forex_ai_agent_r6_5_contract.py
- tests/test_crypto_ai_agent_r6_5_contract.py

## Build
- BUILD_CRYPTO_EXE.bat
- BUILD_CRYPTO_AI_AGENT_R6.5_EXE.bat
- BUILD_FOREX_EXE.bat

## Documentation
- README.md
- CHANGELOG.md
- docs/CRYPTO_AI_AGENT_R6_5_RELEASE_NOTES.md
- docs/CRYPTO_AI_AGENT_R6_5_FULL_AUDIT_2026-09-27.md
- docs/CRYPTO_AI_AGENT_R6_5_BACKTESTER_RELEASE_NOTES.md
- docs/CRYPTO_R9_6_RELEASE_NOTES.md
- docs/FOREX_R5_RELEASE_NOTES.md
- docs/FOREX_AI_AGENT_R6_5_RELEASE_NOTES.md
- docs/FOREX_AI_AGENT_R6_5_FULL_AUDIT_2026-09-28.md
- docs/CRYPTO_FX_PARITY_AUDIT_2026-09-28.md

## Current versions
- Crypto: V8.4.2-R9.6
- Crypto AI Agent: V8.4.2-CRYPTO-AI-AGENT-R6.5
- Forex/MT5: V8.4.2-FOREX-AI-AGENT-R6.5
- Crypto AI config schema: 21
- Crypto AI runtime schema: 22
- Crypto R9.6 config/runtime schema: 12
- Forex AI Agent config/runtime schema: 21 / 22

## Naming policy
Active production root files use the release-identifying filename. New experimental revisions should be kept in Git branches/tags or a dedicated development directory rather than accumulating duplicate root files.
