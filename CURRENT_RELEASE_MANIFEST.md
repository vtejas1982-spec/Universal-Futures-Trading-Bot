## R6.7 Crypto AI-Agent manifest update — 2026-09-29

- Crypto live engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py`
- Crypto AI-Agent release: `V8.4.2-CRYPTO-AI-AGENT-R6.7`
- Crypto config schema: **23**
- Crypto runtime schema: **24**
- AI preset: `AI_AGENT_RECOMMENDED_R6.7`
- Protection contract: actual-fill SL 100% + independent TP1/TP2 reduce-only conditional exits.
- Default TP split: **50% / 50%**.
- Bybit protection parameters: `triggerPrice`, `triggerDirection`, `triggerBy=LastPrice`, `reduceOnly=true`, `closeOnTrigger=true`, `positionIdx=0`.
- Protection verification: Bybit StopOrder-aware.
- AI manager: actual ATR/Volume/ADX/MTF gate state propagated.
- Local validation: AST, bytecode compile, GUI callback/variable audits and synthetic protection smoke tests PASS.
- Demo/Testnet validation is still required before Live.

---

# Current Release Manifest — 2026-09-28

This main branch contains the current active production code only. Superseded root-level bot copies have been removed; their history remains available in Git history.

## Live engines
- UniversalFuturesBot_CRYPTO_V8.4.2-R9.6.py — Crypto Futures production engine
- UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6.py — Crypto AI-Agent production/Demo engine
- UniversalForexBot_MT5.py — Forex/MT5 AI-Agent R6.6 production engine

## Backtesters
- UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6_BACKTESTER.py — AI-Agent strategy/risk/SL/TP backtester
- UniversalForexBot_MT5_BACKTESTER.py — Forex/MT5 AI-Agent R6.6 strategy/risk/SL/TP backtester

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
- docs/FOREX_AI_AGENT_R6_5_HOTFIX1_FULL_AUDIT_2026-09-28.md
- docs/CRYPTO_FX_PARITY_AUDIT_2026-09-28.md

## Current versions
- Crypto: V8.4.2-R9.6
- Crypto AI Agent: V8.4.2-CRYPTO-AI-AGENT-R6.6
- Forex/MT5: V8.4.2-FOREX-AI-AGENT-R6.6
- Crypto AI config schema: 22
- Crypto AI runtime schema: 23
- Crypto R9.6 config/runtime schema: 12
- Forex AI Agent config/runtime schema: 22 / 22

## Naming policy
Active production root files use the release-identifying filename. New experimental revisions should be kept in Git branches/tags or a dedicated development directory rather than accumulating duplicate root files.
