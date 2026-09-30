# Current Release Manifest — R6.8.7.12

## Crypto AI Agent
- Release: V8.4.2-CRYPTO-AI-AGENT-R6.8.7.12
- Live engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.12.py`
- Backtester: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.12_BACKTESTER.py`
- Build: `BUILD_CRYPTO_AI_AGENT_R6.8.7.12_EXE.bat`
- Config schema: 33
- Runtime schema: 24
- Signal mode: AI_AGENT
- Audit: `docs/R6.8.7.12_FULL_AUDIT_R5.md`
- Contract tests: `tests/test_crypto_ai_agent_r6_8_7_12_contract.py`

## Release contract
- AI Min Families: 3
- AI Edge: 0.20
- AI Family Confidence: 0.55
- AI Family Participation: 0.35
- Trend Required: ON
- Structure Required: ON
- Max Conflicting Families: 1
- 2F fallback: ON, Edge 0.65, Confidence 0.65, Participation 0.40
- Adaptive ATR: ON, quantile 0.30, floor 0.10%
- AI protection defaults: SL 1.95 ATR, TP1 1.35R, TP2 2.70R

## Validation
- Live engine compile: PASS
- Backtester compile: PASS
- AST parse: PASS
- AI council smoke test: PASS
- 150x risk cap smoke test: PASS
- Synthetic OHLCV end-to-end backtest: PASS
- Bybit Demo validation remains required before live use.

---

# Current Release Manifest — R6.8.7.2

## Crypto AI Agent
- Release: V8.4.2-CRYPTO-AI-AGENT-R6.8.7.2
- Live engine: UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.2.py
- Backtester: UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.2_BACKTESTER.py
- Config schema: 27
- AI preset: AI_AGENT_RECOMMENDED_R6.8.7.2
- Primary fixes: AI trailing-stop activation; post-fill execution-quality guard; fail-closed bad-fill recovery.
- Contract tests: tests/test_crypto_ai_agent_r6_8_7_2_contract.py
- Audit: docs/R6.8.7.2_FULL_AUDIT.md
- Changelog: docs/R6.8.7.2_CHANGELOG.md

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
- Audit marker: `V8.4.2-AI-AGENT-AUDIT-2026-09-29-R6.7-PROTECTION-ENGINE-AUDIT-FULL-CONTRACT-AUDIT`.
- R6.7 AI diagnostics explicitly report dominant side and directional MTF blockers; TP preflight validates quantity mode, percentage split and ATR TP ordering.


---

# Current Release Manifest — 2026-09-28

This main branch contains the current active production code only. Superseded root-level bot copies have been removed; their history remains available in Git history.

## Live engines
- UniversalFuturesBot_CRYPTO_V8.4.2-R9.6.py — Crypto Futures production engine
- UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py — Crypto AI-Agent production/Demo engine
- UniversalForexBot_MT5.py — Forex/MT5 AI-Agent R6.6 production engine

## Backtesters
- UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6_BACKTESTER.py — AI-Agent strategy/risk/SL/TP backtester (R6.7 live engine contract remains backward-compatible)
- UniversalForexBot_MT5_BACKTESTER.py — Forex/MT5 AI-Agent R6.6 strategy/risk/SL/TP backtester

## Tests
- tests/test_crypto_engine.py
- tests/test_crypto_gui.py
- tests/test_forex_engine.py
- tests/test_forex_ai_agent_r6_5_contract.py
- tests/test_crypto_ai_agent_r6_5_contract.py
- tests/test_crypto_ai_agent_r6_7_protection_contract.py

## Build
- BUILD_CRYPTO_EXE.bat
- BUILD_CRYPTO_AI_AGENT_R6.5_EXE.bat
- BUILD_CRYPTO_AI_AGENT_R6.7_EXE.bat
- BUILD_FOREX_EXE.bat

## Documentation
- README.md
- CHANGELOG.md
- docs/CRYPTO_AI_AGENT_R6_5_RELEASE_NOTES.md
- docs/CRYPTO_AI_AGENT_R6_7_RELEASE_NOTES.md
- docs/CRYPTO_AI_AGENT_R6_7_FULL_CONTRACT_AUDIT_2026-09-29.md
- docs/USER_MANUAL_V8_4_2_R6_7_CRYPTO.md
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
- Crypto AI Agent: V8.4.2-CRYPTO-AI-AGENT-R6.7
- Forex/MT5: V8.4.2-FOREX-AI-AGENT-R6.6
- Crypto AI config schema: 23
- Crypto AI runtime schema: 24
- Crypto R9.6 config/runtime schema: 12
- Forex AI Agent config/runtime schema: 22 / 22

## Naming policy
Active production root files use the release-identifying filename. New experimental revisions should be kept in Git branches/tags or a dedicated development directory rather than accumulating duplicate root files.


## R6.7 Final Audit Update — 2026-09-29

- Engine: UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py
- Version: V8.4.2-CRYPTO-AI-AGENT-R6.7
- Config schema: 23
- Runtime schema: 24
- Audit marker: V8.4.2-AI-AGENT-AUDIT-2026-09-29-R6.7-PROTECTION-ENGINE-AUDIT-FULL-CONTRACT-AUDIT

### Final audit scope
Strategy and evidence-family decision logic; completed-candle consistency including Volume/SR; AI-Agent risk/SL/TP management; position sizing and risk controls; SL/TP overlap/priority and TP quantity accounting; GUI callbacks/settings/defaults; save/load/migration; protection verification/reconciliation; kill-switch and recovery lifecycle.

### Final audit result
No unresolved missing GUI callback, undefined runtime protection setting, or broken AI gate was found in the audited engine. One live-strategy timing inconsistency was fixed: Volume/SR now uses confirmed candles only.

Exchange-side Bybit Demo validation remains mandatory before Live.


## R6.8 Release — 2026-09-29

- Engine: UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.py
- Build script: BUILD_CRYPTO_AI_AGENT_R6.8_EXE.bat
- Tests: tests/test_crypto_ai_agent_r6_8_contract.py
- Config schema remains 23; no new persistent GUI field was introduced.
- Runtime schema remains 24; no new checkpoint field was introduced.

### R6.8 audit
Strategy/evidence-family logic, AI-Agent confidence/edge/family/trend/structure/MTF gates, risk sizing, fixed quantity fail-closed behavior, SL/TP ownership, TP quantity accounting, GUI callbacks/defaults/save-load and the R6.7 completed-candle Volume/SR correction were checked.

Source-level checks pass. Bybit Demo order behavior remains the final operational validation before Live.
