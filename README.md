## Current Crypto AI-Agent R6.7 release — 2026-09-29

The current deterministic Crypto AI-Agent maintenance release is **V8.4.2-CRYPTO-AI-AGENT-R6.7**.

- Live engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py`
- Previous R6.6 source remains in Git history and is not overwritten.
- Crypto config/runtime schema: **23 / 24**
- AI preset: `AI_AGENT_RECOMMENDED_R6.7`
- R6.7 is a protection/execution hardening release. It specifically addresses the observed case where the GUI showed TP1/TP2 enabled but Bybit displayed only the SL conditional order.
- TP1/TP2 retain the intended **50% / 50%** actual-position split by default, with TP1 break-even support.
- Bybit conditional exits now submit with explicit `triggerDirection`, `triggerBy=LastPrice`, `reduceOnly=true`, `closeOnTrigger=true` and one-way `positionIdx=0`.
- Protection acknowledgements now log exchange-returned order ID/status/type/quantity/trigger/reduce-only fields without logging API secrets.
- Protection verification now checks Bybit's conditional **StopOrder** view before falling back to generic order lookup.
- A protection-set failure rolls back known created orders and the existing safety recovery remains responsible for cancelling/flattening any exchange residue.
- AI trade-management now receives the actual ATR/Volume/ADX/MTF gate state instead of hard-coding those gates to `True`.
- Single-TP configurations no longer require a meaningless 50+50 split; the enabled TP closes the full remaining position.
- New-profile defaults align ATR TP with the recommended AI-Agent protection path; saved profiles remain authoritative.

### R6.7 audit status

- Local AST parse: PASS.
- Local Python bytecode compilation: PASS.
- GUI callback binding audit: PASS.
- GUI runtime variable contract audit: PASS.
- Save/load configuration coverage audit: PASS for active persisted fields; `nwe_repaint` remains an intentional compatibility key because R6.6/R6.7 NWE execution is always non-repainting.
- 50/50 Bybit protection smoke test: PASS (synthetic exchange).
- Single-TP protection smoke test: PASS.
- AI gate-forwarding smoke test: PASS.
- This audit does **not** establish profitability or live-exchange safety; validate the exact R6.7 file on Bybit Demo/Testnet before Live.

See `docs/CRYPTO_AI_AGENT_R6_7_RELEASE_NOTES.md` and `docs/USER_MANUAL_V8_4_2_R6_7_CRYPTO.md`.


## Historical Crypto AI-Agent R6.6 release — 2026-09-28

The current deterministic Crypto AI-Agent release is **V8.4.2-CRYPTO-AI-AGENT-R6.6**.

- Historical live engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6.py`
- Historical backtester: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6_BACKTESTER.py`
- Historical Crypto config/runtime schema: **22 / 23**
- Historical AI preset: `AI_AGENT_RECOMMENDED_R6.6`
- R6.6 specifically repairs multiple parser-level defects found in the downloadable R6.5 artifact and is validated locally with AST parsing and Python bytecode compilation.
- Forex/MT5 documentation is synchronized in `docs/USER_MANUAL_V8_4_2_R6_6_FOREX_MT5.md`.

R6.6 remains a deterministic rule-based AI-Agent council, not an external LLM. Syntax validation does not establish profitability or live-exchange execution.

# Universal Futures & Forex Trading Bot

**Current production release: V8.4.2-R9.6**  
**Crypto AI Agent engine: V8.4.2-CRYPTO-AI-AGENT-R6.7**  
**Forex/MT5 AI Agent engine: V8.4.2-FOREX-AI-AGENT-R6.6**

This repository is intentionally kept clean: the main branch contains the **current production engines**, not a pile of old V8.x copies. Historical snapshots belong in Git history/tags/releases.

## Current production files

| Area | Live engine | Backtester |
|---|---|---|
| Crypto / Futures | `UniversalFuturesBot_CRYPTO_V8.4.2-R9.6.py` | — |
| Crypto AI Agent | `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py` | `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6_BACKTESTER.py` |
| Forex / MT5 | `UniversalForexBot_MT5.py` | `UniversalForexBot_MT5_BACKTESTER.py` |

### Tests

- `tests/test_crypto_engine.py`
- `tests/test_crypto_gui.py`
- `tests/test_forex_engine.py`
- `tests/test_forex_ai_agent_r6_5_contract.py`

### Build scripts

- `BUILD_CRYPTO_EXE.bat`
- `BUILD_CRYPTO_AI_AGENT_R6.5_EXE.bat`
- `BUILD_FOREX_EXE.bat`


## V8.4.2-CRYPTO-AI-AGENT-R6.5 — Full engine audit + UI/runtime hardening — 2026-09-27

### Fixed
- Fixed the execution-log newline defect that caused long messages to render as one horizontal line.
- Prevented unchanged profile configuration from being saved again every 30 seconds.
- De-duplicated repeated full strategy diagnostics for the same completed candle/state.
- Added CCXT time-difference correction and a larger private-request receive window to normal and emergency exchange builders.
- Removed obsolete R2/R3/R4/R5 labels from the active R6.5 source comments.

### Added
- **Copy Log**, **Clear Log** and **Auto Scroll** controls.
- 4,000-line GUI log retention.
- Settings dirty tracking for checkpoint persistence.
- Exchange/account-mode validation callback.
- R6.5 contract regression test.
- Full R6.5 audit report.

### Audited
- Engine/StrategyEngine structure and callbacks.
- AI-Agent evidence-family decision path.
- AI risk/SL/TP manager and hard envelopes.
- Configuration variables, preset fields and save/load coverage.
- Profile lifecycle, recovery, protection-order reconciliation and kill-switch paths.

### Verification
- Python compilation: PASS.
- R6.5 contract regression suite: PASS (11/11 locally).
- AI council decision smoke tests: PASS.
- AI risk/SL/TP hard-envelope tests: PASS.

See `docs/CRYPTO_AI_AGENT_R6_5_FULL_AUDIT_2026-09-27.md`.

## V8.4.2-FOREX-AI-AGENT-R6.5-HOTFIX1 — Runtime contract repair + configuration parity — 2026-09-28

### Fixed
- Fixed the startup crash caused by R6.5 loading `v_grid_mode` before that GUI variable existed.
- Added the missing R6.5 runtime controls for Liquidity Entry, Divergence Entry, Divergence Minimum Count, AI TP1 R and AI TP2 R.
- Fixed the AI preset emergency scope default from the invalid `BOT_SYMBOL` value to the supported MT5 value `BOT_ONLY`.
- Added S/R timeframe fields to the AI preset-application callback so the saved preset is fully reproducible.
- Added deterministic validation that AI TP2 R is greater than AI TP1 R.
- Bumped Forex configuration schema 21 -> 22; runtime schema remains 22.

### Modified
- Forex Grid remains explicitly **OFF-only**; no Forex grid execution path is enabled.
- Forex R6.5 hotfix controls are visible in the GUI and persisted through the R6.5 save/load path.
- The dedicated Forex backtester now identifies itself as the R6.5-HOTFIX1 backtester while continuing to use `UniversalForexBot_MT5.py` as the strategy source of truth.

### Validation
- Uploaded local R6.5-HOTFIX1 source: AST parse and bytecode compile PASS.
- GUI attribute contract audit: PASS; no missing `e_*` / `v_*` runtime controls.
- Callback binding audit: PASS.
- AI council + bounded risk/SL/TP smoke test: PASS.
- Preset coverage audit: PASS; all 119 active preset fields are mapped.
- GitHub Forex contract tests expanded for the missing GUI controls, schema and preset mappings.

## V8.4.2-FOREX-AI-AGENT-R6.5 — Crypto R6.5 strategy parity + MT5-native execution — 2026-09-28

### Added
- AI_AGENT signal mode to the Forex/MT5 engine.
- The same six AI-Agent council controls used by Crypto R6.5: AI Min Families, AI Min Edge, AI Family Confidence, AI Max Conflicts, AI Require Trend, AI Require Structure.
- YES/NO AI-Agent preset confirmation. YES applies AI_AGENT_RECOMMENDED_R6.5; NO keeps current settings while AI_AGENT stays enabled.
- Bounded AI trade management with the same R6.5 hard envelopes: Risk 0.20%–0.50%; SL 1.50–2.40 ATR; TP1 1.00–1.50R; TP2 2.00–3.00R.
- Dedicated Forex/MT5 R6.5 backtester with completed-candle entries, risk-based sizing, ATR SL/TP, TP1 break-even, drawdown/loss guards and performance metrics.
- Forex AI-Agent parity regression suite.

### Fixed
- Forex StrategyEngine was upgraded to the same AI-aware R6.5 implementation as Crypto.
- Core strategy calculation parity was synchronized, including ADX and Volume/SR logic.
- Missing AI runtime arguments are now propagated into signal and decision-reason paths.
- Existing MT5 protection remains the execution authority: actual fill/lot quantity and broker precision are used for final SL/TP.
- AI lot sizing now preserves the AI-selected dynamic ATR stop instead of overwriting it with the static GUI ATR multiplier.
- Existing Hold-All-Reverse now supports both ALL_ACTIVE and MIN_FAMILIES.
- Forex configuration/runtime schema advanced to 21/22 with AI-Agent and parity fields persisted.
- Max Open Trades is explicitly constrained to the current MT5 single-position contract of 1.
- Liquidity Swing entry mode and Divergence minimum-count/entry-mode controls are now explicit and persisted.
- Grid Mode is visible for parity but is OFF-only in the MT5 Forex runtime.

### Preserved
- MT5 PAPER / TERMINAL / LIVE modes.
- Broker symbol/suffix discovery, MT5 lot rules, order_calc_profit, margin/P/L and broker-native protection/recovery.
- Existing Forex spread, slippage, session, Friday, news, correlation and trailing guardrails.

### Verification
- UniversalForexBot_MT5.py compiles and imports successfully.
- Forex StrategyEngine AST matches Crypto R6.5.
- All shared core indicator/strategy functions audited for parity.
- AI preset values match Crypto R6.5 exactly (134/134).
- AI decision and AI risk/SL/TP hard-envelope tests pass.
- Forex backtester smoke test passes.
- Forex R6.5 regression contract suite covers compile, StrategyEngine parity, GUI contract and runtime binding checks.

See `docs/FOREX_AI_AGENT_R6_5_RELEASE_NOTES.md` and `docs/FOREX_AI_AGENT_R6_5_FULL_AUDIT_2026-09-28.md`.

## Current repository cleanup — 2026-09-27

The active root is now consolidated to one current Crypto R9.6 engine, one current Crypto AI-Agent R6.5 engine, one Forex/MT5 engine, and their current backtest/build files. Superseded duplicate bot files were removed from the main branch; historical versions remain in Git history.

### Current active files

- `UniversalFuturesBot_CRYPTO_V8.4.2-R9.6.py`
- `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5.py`
- `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5_BACKTESTER.py`
- `UniversalForexBot_MT5.py`
- `UniversalForexBot_MT5_BACKTESTER.py`

The changelog below is historical by design; old release numbers in it do not represent active root files.

`UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5_BACKTESTER.py` is the dedicated R6.5 AI-Agent simulator. It uses completed-candle signals, AI-family thresholds and bounded AI risk/SL/TP management; its historical results are not a guarantee of live performance.

## V8.4.2-CRYPTO-AI-AGENT-R5 — Confirmed AI-Agent recommended preset + decision-diagnostic hardening — 2026-09-27

### Added
- Selecting **AI_AGENT** in Decision Engine now asks for confirmation before changing strategy settings.
- **YES — Apply Recommended AI Agent Settings** applies the complete deterministic R5 preset.
- **NO — Continue With Current Settings** keeps the user's existing settings unchanged while AI_AGENT remains enabled.
- The six AI-Agent council controls remain individually editable and persisted per profile:
  - AI Min Families
  - AI Min Edge
  - AI Family Confidence
  - AI Max Conflicts
  - AI Require Trend
  - AI Require Structure
- The preset also normalizes execution, evidence modules, risk sizing, protection, reversal behavior and audited indicator parameters.
- Profile metadata records whether the recommended preset was applied.

### Fixed
- AI-Agent blocked-reason diagnostics now use the **effective profile values** instead of hard-coded global thresholds.
- Configuration/runtime schema advanced to 16 for preset metadata.
- AI-Agent preset application refreshes the worker snapshot after all changes.

### Safety
- The preset does not change API credentials, exchange/account mode, symbol or bot profile identity.
- It uses 15m, 5x leverage, one net position, 0.35% equity risk, completed-candle safety, 15-minute cooldown, and exchange-side protection.
- The preset is a configuration recommendation, **not a guarantee of maximum profit or profitability**.

### Validation
- Python compile: PASS.
- AST parse: PASS.
- Deterministic AI-Agent smoke test: PASS.
- GitHub production source updated.

See `docs/CRYPTO_AI_AGENT_R5_RELEASE_NOTES.md`.

---

## V8.4.2-CRYPTO-AI-AGENT-R4 — Full engine audit + AI Agent configuration hardening — 2026-09-27

### Fixed
- Fixed the R3 configuration-load defect by retaining `v_size_mode` initialization before `load_settings()`.
- Added `AI_AGENT` to the actual GUI Signal Mode menu; the engine contract and loader already accepted it.
- AI-Agent council thresholds are now per-profile, persisted, validated, snapshotted on the GUI thread, propagated to the worker, and passed explicitly into decision and reason paths.
- Corrected an AI decision-reason parameter mismatch found during audit.
- Unknown AI council settings fail validation before exchange execution.

### Added
- AI Min Families, AI Min Edge, AI Family Confidence, AI Max Conflicts, AI Require Trend, and AI Require Structure.
- Startup logging of the exact AI council configuration used.

### Audit
- StrategyEngine, 19-module indicator/evidence chain, settings/defaults, callbacks, configuration save/load/migration, recovery, risk/sizing, SL/TP, Grid isolation, profile lifecycle and kill-switch paths rechecked.
- In-memory compile, AST, GUI self-call/callback audit, undefined-global audit and deterministic AI-agent smoke tests passed.

### Important
AI Agent R4 remains a deterministic rule engine; it does not call an external LLM. Live Bybit Demo execution and profitability are not established by the source audit.

See docs/CRYPTO_AI_AGENT_R4_RELEASE_NOTES.md.

## V8.4.2-R9.6 — Unified ROI protection + configurable reversal hold — 2026-09-27

R9.6 restores the full R9.3 protection capability behind an explicit compatibility path, adds a simpler ROI-based protection model, and integrates the R9.5 reversal-hold engine.

### Fixed
- Fixed Qty and Equity Risk entry sizing remain completely independent.
- Simple protection resolves one and only one SL basis.
- Simple protection resolves one TP model; TP1/TP2 toggles cannot leak into legacy mode.
- Hold-All-Reverse and Hold-SL WAIT are isolated from the normal TP engine.
- Actual-fill entry/position quantity remains authoritative for protection.
- Mandatory kill switch/watchdog remains retained.

### Added
- Independent ON/OFF controls for risk sizing, ROI SL, ATR SL, fallback SL, TP engine, TP1, TP2, ATR TP multipliers and TP1 break-even.
- Hold Position Until Reverse.
- Reverse Exit Rule: ALL_ACTIVE or MIN_FAMILIES.
- Minimum Reverse Families 1–4.
- Hold-SL threshold and optional WAIT-after-threshold behavior.
- R9.3 legacy protection compatibility switch.

### Audit
- R9.3 protection calculator parity retained.
- Simple ROI conversion uses ROI divided by configured leverage.
- Strategy/evidence-family, defaults, callbacks, configuration migration, entry sizing, SL/TP, recovery and kill-switch paths rechecked.
- Python compile and GUI AST/self-call audit passed.

See docs/CRYPTO_R9_6_RELEASE_NOTES.md.

## V8.4.2-R9.3 — Stop completion + Fixed-Qty execution hardening — 2026-09-27

R9.3 is a corrective production release following the R9.2 kill-switch implementation and Demo GUI testing.

### Fixed
- **STOPPING -> STOPPED:** manual STOP no longer blocks the Tk GUI during exchange flattening. Cleanup runs in a dedicated stop thread and the GUI keeps polling until the worker actually exits.
- **Stop completion is explicit:** after the worker exits, the Profile Manager is refreshed and the execution log reports whether the exchange was verified FLAT with no open orders.
- **Kill-switch idempotency:** manual stop, worker finalization and shutdown paths do not intentionally duplicate a verified flatten operation.
- **Fixed Qty entry sizing:** FIXED_QTY is literal exchange/base quantity. For example, Fixed Qty=1500 requests 1500 units, subject only to exchange precision/minimum normalization. It is not recalculated from balance or Risk Per Trade.
- **SL independence:** selecting FIXED_QTY no longer changes SL Mode. Fixed Qty can use the selected PRICE_%, ROI_%, ATR Dynamic or explicit RISK_% protection contract subject to validation.

### Audit
- Rechecked strategy engine, indicator/evidence-family logic, settings/defaults, callbacks, configuration load/save, recovery, entry sizing, SL/TP calculation, order submission, profile lifecycle and kill-switch paths.
- Fixed-Qty static branch contains no equity-risk quantity formula.
- Resume still performs a live exchange snapshot before recovery continuation.
- Python compilation and GUI self-call audit passed.

### Demo validation
Live Bybit Demo order/position lifecycle testing is still required. See docs/CRYPTO_R9_3_RELEASE_NOTES.md.

## V8.4.2-R9.1 — Profile lifecycle + recovery decision + fixed-quantity hardening — 2026-09-27

R9.1 is a corrective maintenance release based on the R9 Demo test. It addresses three concrete behaviors observed during profile testing.

### Fixed
- **NO on Recovery is now persisted:** choosing **NO / Start New Bot** immediately writes the selected profile runtime state as STOPPED with a START_NEW recovery decision. A previous RUNNING checkpoint can no longer remain visible simply because recovery was declined.
- **Stale profile locks:** profile lock checks now reject Linux zombie/reused-PID cases where possible and remove stale locks. A dead worker must not keep a profile looking RUNNING.
- **Individual profile STOP controls:** every saved profile receives its own STOP <PROFILE> button in Profile Manager, in addition to STOP Selected Bot.
- **Fixed Qty is preserved:** selecting FIXED_QTY no longer automatically changes SL mode to RISK_%. Fixed Qty remains literal exchange/base quantity; SL mode is an independent control. Existing saved Fixed Qty values are preserved during configuration loading.
- **Sizing diagnostics:** Profile Details shows sizing mode, Fixed Qty and Risk % together.

### Important contract
- FIXED_QTY = literal requested exchange/base quantity, rounded only to the exchange's allowed precision/minimum by safe_amount().
- EQUITY_RISK_% = quantity calculated from account risk and stop distance.
- RISK_% SL mode remains available only for FIXED_QTY and remains incompatible with Hold-All-Reverse, as enforced by validation.
- ATR Dynamic SL/TP does not silently convert Fixed Qty into risk sizing.

### Validation
- R9.1 source compiled successfully with Python py_compile.
- AST audit of the GUI class: 139 methods; no missing self.* method references.
- Live Bybit Demo validation remains required for order/position behavior.

See docs/CRYPTO_R9_1_RELEASE_NOTES.md.

## V8.4.2-R9 — Crypto profile lifecycle + recovery-control hardening — 2026-09-27

R9 fixes the profile-control problem where one GUI could show a saved profile as RUNNING even though its worker process was no longer owned by that GUI, and where a running profile in another GUI process could not be safely stopped from the Profile Manager.

### Fixed

- Cross-process profile stop: Profile Manager now has STOP Selected Bot. It sends a profile-scoped stop request that the running worker acknowledges and finalizes through its normal checkpoint path.
- Truthful profile status: a historical RUNNING/STOPPING/CRASHED checkpoint without a live profile lock is no longer displayed as a live RUNNING bot. Profiles with saved inventory are shown as RECOVERY_REQUIRED; flat stale profiles are shown as STOPPED.
- Live status refresh: the profile table refreshes automatically every 3 seconds.
- Max Open Trades contract: the GUI now explicitly rejects values other than 1 for the current single-symbol/one-way execution engine instead of silently normalizing them. Max Completed Trades remains the session trade-count limit.
- Default parity: missing saved cooldown_min and use_divergence values now use the declared R9/new-profile defaults.
- Unused risk constant: removed the unused RISK_COST_BUFFER variable rather than implying that it affected live risk calculations.

### Added

- Profile-scoped control.json stop requests with request IDs and stale-request cleanup.
- Runtime worker PID/start metadata.
- Recovery-aware status RECOVERY_REQUIRED.
- Profile-manager stop control for bots running in another process.
- ATR Dynamic SL/TP values in the selected-profile details panel.

### Preserved

- ADAPTIVE_EVIDENCE thresholds and Evidence-family logic.
- Completed-candle strategy calculations.
- Actual-fill SL/TP calculation and protection verification.
- Fixed-Qty + RISK_% hard-SL contract.
- Post-SL opposite lock, Hold-All-Reverse, Grid fail-closed behavior, managed-order ownership, and restart identity checks.

See docs/CRYPTO_R9_RELEASE_NOTES.md for the complete fix/add/modify list.

## V8.4.2-R8 — Crypto lifecycle + risk-boundary hardening — 2026-09-27

R8 is a production safety release following Bybit Demo validation. It fixes profile lifecycle state, corrects percentage risk sizing, adds explicit FIXED_QTY + RISK_% hard-SL semantics, enforces exchange maximum order quantity, and removes direct Tkinter setting reads from the trading worker.

### Fixed

- **Stop/profile lifecycle:** RUNNING → STOPPING → STOPPED/PAUSED_WITH_POSITION is now explicit. The GUI waits for the worker to terminate before releasing the profile lock.
- **Phantom/stale RUNNING state:** a flat profile with no live process and no saved position/Grid state is normalized to STOPPED.
- **Profile deletion:** stale lifecycle status alone no longer blocks deletion; live locks, saved positions, active trades and Grid state still block destructive operations.
- **Risk sizing:** `0.75` now means **0.75% of equity**, not 75%.
- **FIXED_QTY + RISK_% SL:** selecting FIXED_QTY can automatically select RISK_% SL; the configured Risk Per Trade becomes the account-risk budget and the stop is calculated from the actual filled quantity and entry.
- **RISK_% safety:** RISK_% is rejected with Equity-Risk sizing or Hold-All-Reverse, preventing ambiguous stop ownership.
- **Exchange quantity cap:** final order quantity is clamped to CCXT/exchange maximum amount and precision before entry.
- **ATR default parity:** missing `use_atr` configuration now uses the same ON default as a new profile.
- **Max Open Trades:** this single-symbol engine now explicitly normalizes any value other than 1 to its hard limit of one net position.
- Removed a duplicate `DIVERGENCE_INDICATORS` definition.

### Added

- Runtime schema 7 with explicit stop-request state plus sizing/protection-basis metadata.
- GUI-setting snapshot layer for worker-thread safety.
- R8 regression suite: `tests/test_crypto_r8_regressions.py`.
- Exchange-cap and actual-risk diagnostics.
- R8 release documentation.

### Preserved

R8 does not loosen the ADAPTIVE_EVIDENCE contract, Evidence-family thresholds, completed-candle signal logic, ATR/ADX regime gates, Hold-All-Reverse, post-SL lock, ATR 1.50 / 1.20 / 2.20 protection, or recovery identity checks. Fixed-quantity RISK_% SL is an explicit protection mode; it does not change the entry quantity.

See `docs/CRYPTO_R8_RELEASE_NOTES.md` for the complete fix/add/modify list.

## V8.4.2-R6 — Crypto execution hardening — 2026-09-27

R6 is a focused live-execution reliability release. It does **not** loosen the ADAPTIVE_EVIDENCE strategy thresholds or manufacture additional signals.

### Fixed

- **Critical cooldown bug:** a continuously-flat bot no longer refreshes `last_flat_time` every polling cycle. The configured cooldown now starts only after a verified live-position → flat transition, so a 15-minute cooldown can actually expire.
- **Hold-SL WAIT gate:** when `Hold-SL WAIT` is enabled, strategy reversal is blocked until the configured ROI threshold is reached. The later ALL-REVERSE check can no longer overwrite that prerequisite.
- Removed an unreachable duplicate `ADAPTIVE_EVIDENCE` startup logging branch.
- Added explicit `COOLDOWN STARTED` diagnostics for verified live-to-flat transitions and strategy reversals.

### Preserved

- ADAPTIVE_EVIDENCE: 2 families, family score 0.35, Trend required, Independent Non-Trend required, Edge 0.18.
- ATR/ADX remain regime gates rather than directional evidence families.
- Actual-fill SL/TP calculation, protection verification, recovery identity checks, managed-order ownership and fail-closed safety behavior.
- Single-symbol execution remains one net position per bot/profile.

### Validation

- Crypto live source compiles successfully.
- R6 StrategyEngine regression coverage passes all supported signal modes.
- SINGLE_SIGNAL conflict remains fail-closed.
- New R6 cooldown and Hold-SL WAIT regression tests are included under `tests/test_crypto_r6_regressions.py`.

See `docs/CRYPTO_R6_RELEASE_NOTES.md` for the exact fix/add/modify list.

## V8.4.2-R5 contract

### Strategy

- Signal mode: `ADAPTIVE_EVIDENCE`
- Minimum evidence families: **2**
- Family minimum score: **0.35**
- Trend family required: **ON**
- Independent non-Trend family required: **ON**
- Adaptive Edge: **0.18**
- Adaptive Minimum Weight: **3.50**
- Evidence families:
  - TREND
  - MOMENTUM
  - FLOW
  - STRUCTURE
- ATR and ADX are **regime gates**, not independent directional evidence families.
- `DIRECT_SHOT`, `LONG_GRID`, `SHORT_GRID`, and `NEUTRAL_GRID` remain supported by the Crypto engine.

## Dynamic protection

R5 uses the following ATR relationship when ATR Dynamic protection is enabled:

```
Completed-candle ATR
        ↓
SL = 1.50 × ATR
        ↓
TP1 = 1.20 × actual SL distance
TP2 = 2.20 × actual SL distance
```

The live engine calculates protection from the **actual filled entry price** and actual position quantity.

Runtime diagnostics report:

```
Entry Price
ATR
SL Price %
SL ROI %
TP1 Price %
TP1 ROI %
TP2 Price %
TP2 ROI %
```

## Max Open Trades

The current execution coordinator is a **single-symbol net-position engine**. `0` is not treated as unlimited; the effective hard limit is 1.

Therefore:

```
Max Open Trades != 1
        ↓
rejected at validation
        ↓
1 net position per bot/symbol
```

This does **not** claim support for two independent same-symbol positions.

## Crypto backtester

`UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5_BACKTESTER.py` is the R5 research simulator.

It supports the strategy-side contract including:

- completed-candle signals
- next-candle-open entry simulation
- Evidence-family decisions
- MTF
- divergence
- Volume/S/R
- ATR Dynamic SL/TP
- risk sizing
- cooldown
- drawdown
- loss streak
- post-SL opposite lock
- TP1 partial close
- TP1 break-even
- Grid modes
- conservative same-bar ambiguity handling

Backtesting is not a substitute for exchange demo validation.

## Forex / MT5

`UniversalForexBot_MT5.py` is the self-contained R5 MT5 production engine.

It includes:

- MT5 execution
- broker lot/price rules
- MT5-native account handling
- Evidence-family strategy
- ATR Dynamic protection
- post-SL lock
- recovery/checkpoint behavior
- spread/session/news/correlation protections inherited from the audited MT5 engine

The Forex backtester loads the clean production Forex engine rather than a historical V8.4.0 source file.

## Configuration

Current configuration schema:

```
CONFIG_SCHEMA_VERSION = 9
```

Existing saved profiles remain authoritative. Missing R5 fields are populated with safe defaults.

Important persisted R5 fields include:

- `max_open_trades`
- `use_atr_sl`
- `atr_sl_mult`
- `atr_tp1_mult`
- `atr_tp2_mult`
- Evidence-family settings

## Running

### Crypto

```
py -3.14 current Crypto R9.6 engine
```

### Crypto backtester

```
py -3.14 current dedicated Crypto AI-Agent R6.5 backtester
```

### Forex / MT5

```
py -3.14 UniversalForexBot_MT5.py
```

### Forex backtester

```
py -3.14 UniversalForexBot_MT5_BACKTESTER.py
```

Install dependencies from `requirements.txt` first.

## Safety

- Use exchange demo/testnet or MT5 paper/demo first.
- Do not treat backtest results as a guarantee of live execution.
- Verify actual fills, protection orders, broker/exchange trigger behavior, partial fills, reconnects and recovery before live deployment.
- Never commit API keys, passwords or tokens.


## 2026-09-22 Engine Audit Update

The latest R5 audit added explicit ADX Period configuration, detailed Evidence blocker diagnostics, safer new-profile defaults, and a Grid fill-loop fix in the Crypto backtester. The Crypto backtester also enforces Grid cooldown, loss-streak protection and marked-equity daily drawdown.

For Forex new profiles, the R5 recommendation now uses 0.50% risk, ATR regime gating, news/session/correlation guardrails, 2% daily loss, and the 1.50 / 1.30 / 2.20 ATR protection contract.

See docs/R5_ENGINE_AUDIT_2026-09-22.md for the complete fix/add/modify list.


## 2026-09-27 — Crypto AI Agent R6.1 configuration/protection hotfix

The Crypto AI-Agent engine was audited after a startup failure exposed a stale GUI-variable reference in the SL configuration path. R6.1 keeps the R6 deterministic AI risk/SL/TP manager and repairs the configuration contract around it.

### Fixed
- Removed executable references to the obsolete 'v_use_atr_sl' GUI variable.
- Canonicalized ATR-SL configuration on 'v_simple_atr_sl_enabled'.
- Preserved the old 'use_atr_sl' JSON key as a backward-compatible alias so existing profiles can still load.
- Fixed legacy-protection ATR-SL runtime lookup to use the canonical GUI variable.
- Fixed ATR-TP migration so its own 'simple_atr_tp_enabled' setting is never derived from the ATR-SL toggle.
- Updated profile summaries to read the canonical ATR-SL setting.
- Added a protection GUI/configuration contract check before settings are persisted, producing a clear configuration error instead of an opaque AttributeError.

### Retained from R6
- Deterministic AI-Agent evidence-family decision engine.
- Bounded per-trade AI risk adjustment (0.20%–0.50%).
- Bounded AI ATR-SL adjustment (1.50–2.40 ATR).
- AI TP1/TP2 management using bounded R-multiples.
- Risk sizing uses the AI-selected stop distance before entry.
- Final SL/TP resolution is recalculated from the actual filled entry and actual position quantity.
- Exchange-side protection verification/fail-closed behavior remains intact.

### Validation
- Uploaded R6 source plus the R6.1 hotfix was compiled successfully with Python.
- Static GUI attribute audit found no remaining executable references to the missing 'v_use_atr_sl' variable.
- AI trade-manager smoke test passed.
- Actual-fill protection resolver smoke test passed with valid LONG SL/TP ordering.
- Full live exchange lifecycle was **not** claimed by this audit; continue using Bybit Demo/Testnet before live deployment.

See [Crypto AI Agent R6.1 release notes](docs/CRYPTO_AI_AGENT_R6_1_RELEASE_NOTES.md).

## 2026-09-27 — Crypto AI Agent R6.2 decision-flow hotfix

A demo run exposed a second AI-Agent integration mismatch after the R6.1 configuration hotfix: the direct `StrategyEngine.decision_reason()` call used GUI-oriented names (`ai_family_confidence`, `ai_max_conflicts`) while the StrategyEngine API expects `ai_min_family_confidence` and `ai_max_conflicting_families`.

R6.2 fixes that call contract and improves AI-Agent startup/test behavior:
- Fixed the two incorrect decision-reason keyword arguments.
- Made the AI recommended preset explicitly show ATR-TP as ON, matching the runtime AI TP-management path.
- Changed NEW-profile Hold-All-Reverse default to OFF so it does not suppress AI dynamic risk/ATR-SL/ATR-TP management.
- Added a runtime notice when AI_AGENT is active without the confirmed recommended preset; current saved GUI settings remain unchanged.
- Added a runtime diagnostic when HOLD-ALL-REVERSE is ON and therefore intentionally blocks the AI dynamic trade manager.
- Configuration schema: 18 -> 19; runtime schema: 18 -> 19.

The AI manager remains deterministic and bounded; these changes do not create a profitability guarantee.

See [Crypto AI Agent R6.2 release notes](docs/CRYPTO_AI_AGENT_R6_2_RELEASE_NOTES.md).

## 2026-09-27 — Crypto AI Agent R6.3 migration-persistence hotfix

R6.3 fixes repeated configuration migration messages. A profile saved under schema 18 could repeatedly report schema 18 -> 19 because the loader only announced the migration and did not persist the upgraded schema marker.

R6.3 now:
- Persists the current config_schema_version only after a complete configuration load succeeds.
- Keeps existing saved configuration values authoritative.
- Re-synchronizes the legacy use_atr_sl alias from canonical simple_atr_sl_enabled during migration.
- Replaces the verbose legacy R3 migration message with a single sizing-compatibility message.
- Prevents the same schema-upgrade notice from repeating on the next profile load.
- Internal source version: V8.4.2-CRYPTO-AI-AGENT-R6.3.
- Configuration/runtime schema: 20.

See docs/CRYPTO_AI_AGENT_R6_3_RELEASE_NOTES.md.

## 2026-09-27 — Crypto AI Agent R6.4 non-blocking GUI shutdown hotfix

A Windows test exposed a GUI freeze ("Not Responding") during window close. The shutdown callback was performing the mandatory Bybit/CCXT kill-switch exchange operations directly on the Tkinter main thread.

R6.4 changes shutdown to a non-blocking fail-closed lifecycle:
- The window-close callback no longer performs exchange API calls directly.
- Exchange flatten/cancel/verification runs in the existing background cleanup worker.
- The GUI polls worker and cleanup state without blocking the Tk event loop.
- The window is destroyed only after FLAT + NO OPEN ORDERS is verified.
- If exchange cleanup cannot be verified, the window remains open and reports that safe close is blocked so cleanup can be retried.
- Stop-wait diagnostics now account for both the execution worker and cleanup worker.
- Internal source version: V8.4.2-CRYPTO-AI-AGENT-R6.4.
- Configuration/runtime schema: 21.

See docs/CRYPTO_AI_AGENT_R6_4_RELEASE_NOTES.md.

## 2026-09-27 — Crypto AI Agent R6.5 full engine/configuration audit

R6.5 is a deeper hardening pass after the R6.1-R6.4 production/Demo fixes. The audit covered the AI decision engine, evidence-family strategy path, risk/SL/TP management, configuration variables/defaults, persistence/recovery, callbacks, worker/thread boundaries, shutdown lifecycle and protection reconciliation.

### Fixed
- Added a worker-to-GUI callback queue so trading/safety workers no longer call Tkinter callbacks directly.
- Removed worker-thread reads of Tkinter Entry/Variable objects from reachable execution paths; the worker uses the existing immutable runtime GUI snapshot instead.
- Moved execution-loop dashboard/checkpoint/finish UI updates through the GUI bridge.
- Made emergency-stop button updates thread-safe.
- Prevented worker completion from releasing the profile lock while background kill-switch cleanup is still active.
- Made idle window close local-only when there is no active/stale bot runtime, avoiding an unnecessary exchange call.
- Changed the runtime protection-basis label to AI_DYNAMIC for accepted AI-Agent sessions instead of the generic SIMPLE_ROI label.
- Persisted actual TP1/TP2 quantities and TP split metadata in recovery state.
- Fixed TP2 protection reconstruction so it preserves the configured TP split; the old 50% calculation is now only a last-resort compatibility fallback for very old checkpoints.
- Fixed the AI execution diagnostic so Required reports the AI minimum-family requirement instead of the legacy minimum-score field.

### Added
- R6.5 runtime schema 22 for the expanded protection/recovery checkpoint metadata.
- UI queue back-pressure behavior: cosmetic UI updates are dropped rather than blocking trading/safety workers.
- Automated contract test coverage for StrategyEngine keyword compatibility, worker Tk-thread safety, TP split persistence and migration persistence.

### Retained
- AI-Agent minimum Families=3, Edge>=0.20, Family Confidence>=0.55, Max Conflicts<=1, Trend/Structure requirements.
- Bounded AI risk 0.20%-0.50%.
- Bounded AI ATR SL 1.50-2.40 ATR.
- Bounded AI TP1 1.00-1.50R and TP2 2.00-3.00R.
- Actual-fill entry/quantity protection resolution.
- Mandatory fail-closed kill switch and exchange-side protection verification.
- Non-repainting/confirmed-candle strategy behavior.

### Validation
- Python AST parse and bytecode compilation: PASS.
- AI-Agent decision and decision-reason smoke tests: PASS.
- TP split calculation smoke tests: PASS.
- Worker-reachable GUI/Tk audit: PASS; no direct Tk variable access remains in the execution call graph, and Tk root callbacks are routed through the GUI bridge.
- StrategyEngine keyword audit: PASS.
- Full live exchange lifecycle is not claimed by this static/functional audit; continue using Bybit Demo/Testnet before live deployment.

See [Crypto AI Agent R6.5 release notes](docs/CRYPTO_AI_AGENT_R6_5_RELEASE_NOTES.md).

## Release documentation

- [Crypto R5 release notes](docs/CRYPTO_R5_RELEASE_NOTES.md)
- [Forex R5 release notes](docs/FOREX_R5_RELEASE_NOTES.md)
- [2026-09-22 Engine Audit](docs/R5_ENGINE_AUDIT_2026-09-22.md)
- [Changelog](CHANGELOG.md)

## User manuals

The repository now includes three **complete, self-contained V8.4.2-R5 manuals**. Each manual contains the full Crypto + Forex/MT5 + Backtester reference; the edition title only identifies its primary focus.

- [Complete Crypto Edition](docs/USER_MANUAL_V8_4_2_R5_CRYPTO.md)
- [Complete Forex / MT5 Edition](docs/USER_MANUAL_V8_4_2_R5_FOREX_MT5.md)
- [Complete Backtester Edition](docs/USER_MANUAL_V8_4_2_R5_BACKTESTER.md)

The manuals document every R5 indicator family, indicator purpose, major options, signal modes, Evidence-family logic, risk/protection controls, Grid modes, live execution concepts, Forex news/session/correlation controls, and backtesting rules.

## Versioning policy

The production root uses stable filenames. Do **not** create files such as:

```
*_V8_4_2_R6.py
*_FINAL2.py
*_AUDITED_R3.py
*_HARDENED_R4.py
```

For a new release:

1. Update the current production source.
2. Update the internal `APP_VERSION` / `AUDIT_BUILD`.
3. Update tests.
4. Update `CHANGELOG.md`.
5. Tag the release in Git.

That keeps the working tree understandable while Git history and releases retain previous versions.


### 2026-09-22 API resilience hotfix

The live Crypto engine now treats transient exchange/API connectivity failures separately from strategy/runtime faults. Account balance reads use bounded retry/backoff, one successful wallet snapshot is reused for balance/equity, and persistent transient failures still halt the bot fail-closed after a larger recovery window.

This specifically addresses the BOT-01 Bybit Demo `/v5/account/wallet-balance` failure pattern seen during the overnight run.

See `docs/R5_ENGINE_AUDIT_2026-09-22.md` for the complete change history.


### 2026-09-22 managed-order cleanup hotfix

After the overnight SL event, Bybit returned terminal order state 110001 (order not exists or too late to cancel) for retired TP/SL IDs. The engine now treats that state as inactive, removes stale managed IDs, and avoids repeating the same cancellation every 30 seconds. Genuine unresolved managed-order cancellation failures remain fail-closed.


## Latest Crypto R8
See `docs/CRYPTO_R8_RELEASE_NOTES.md` and `CHANGELOG.md` for the 2026-09-27 lifecycle, risk-sizing and exchange-quantity hardening. The stable production filename remains `current Crypto R9.6 engine`.
