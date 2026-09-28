## 2026-09-29 — Crypto AI-Agent R6.7 Full-Contract Audit Hotfix

### Fixed
- Added explicit dominant-side and directional MTF gate diagnostics to AI-Agent blocked decisions.
- Replaced hard-coded AI-Agent startup threshold display with the actual configured values.
- Added TP quantity-mode preflight validation.
- Added TP1/TP2 percentage range validation and retained the exact 100% split requirement.
- Added fixed-quantity TP positivity validation.
- Added ATR TP1/TP2 ordering validation before exchange mutation.

### Added
- Full-contract R6.7 audit marker: V8.4.2-AI-AGENT-AUDIT-2026-09-29-R6.7-PROTECTION-ENGINE-AUDIT-FULL-CONTRACT-AUDIT.
- Expanded R6.7 protection/AI contract regression tests.

### Retained
- Actual-fill SL/TP protection.
- 50%/50% TP1/TP2 default split.
- Bybit conditional StopOrder-aware verification.
- Protection rollback and reconciliation.
- Actual ATR/Volume/ADX/MTF gate propagation into AI trade management.
- Profile/configuration migration compatibility and fail-closed lifecycle safety.

### Validation
- AST parse: PASS.
- Python bytecode compilation: PASS.
- Module import: PASS.
- TP 50/50 and invalid-split smoke tests: PASS.
- AI MTF gate smoke test: PASS.
- GUI callback/runtime/config contract audit: PASS.

## V8.4.2-CRYPTO-AI-AGENT-R6.7 — Protection engine + full runtime audit — 2026-09-29

### Fixed
- Hardened Bybit conditional SL/TP submission with explicit `triggerDirection`, `triggerBy=LastPrice`, `reduceOnly`, `closeOnTrigger` and `positionIdx=0`.
- Fixed the protection verification path so Bybit conditional StopOrders are checked explicitly instead of relying only on a generic order endpoint.
- Added atomic protection-set rollback when SL/TP creation is incomplete.
- Preserved the actual-fill TP1/TP2 split contract: default 50% / 50%.
- Single-TP mode now closes the full remaining position and no longer requires an artificial 50+50 split.
- Passed real ATR/Volume/ADX/MTF regime state into the bounded AI trade manager instead of hard-coded TRUE gates.

### Added
- Protection ACK diagnostics with order ID, status, type, side, quantity, trigger and reduce-only/close-on-trigger state.
- Explicit protection target diagnostics before exchange submission.
- R6.7 protection contract metadata in runtime state.
- Release-specific audit notes and Demo validation checklist.

### Modified
- Config schema 22 -> 23.
- Runtime schema 23 -> 24.
- AI preset `AI_AGENT_RECOMMENDED_R6.6` -> `AI_AGENT_RECOMMENDED_R6.7`.
- New-profile ATR TP default ON.
- New-profile ATR SL default 1.8x.
- Default TP quantity mode remains `PERCENT_%`, with TP1 50% and TP2 50%.

### Audit / validation
- AST parse: PASS.
- Python bytecode compilation: PASS.
- GUI callback binding: PASS.
- GUI runtime-variable contract: PASS.
- Save/load active configuration audit: PASS.
- Synthetic 50/50 protection smoke test: PASS.
- Single-TP smoke test: PASS.
- AI gate-forwarding smoke test: PASS.

See `docs/CRYPTO_AI_AGENT_R6_7_RELEASE_NOTES.md`.

# V8.4.2 Forex/MT5 AI Agent R6.6 metadata alignment — 2026-09-28

## Modified
- Forex/MT5 live engine release marker advanced from R6.5-HOTFIX1 to R6.6.
- Forex/MT5 backtester release marker advanced to R6.6.
- Forex R6.6 manual now matches the current configuration contract.
- No new Forex Grid execution was introduced; MT5 remains single-position and Grid is OFF-only.

---

# V8.4.2 Crypto AI-Agent R6.6 — parser-integrity and release-contract repair — 2026-09-28

## Fixed
- Fixed the startup SyntaxError in the R6.5 Crypto AI-Agent source at the Nadaraya-Watson Envelope function.
- Fixed additional malformed statement concatenations discovered by full AST parsing: profile sanitization, Supertrend GUI setup, grid-state initialization, RSI validation and VWAP Delta state assignment.
- The downloaded R6.5 file was treated as a corrupted release artifact rather than applying only the first visible parser fix.

## Modified
- Crypto AI-Agent version: R6.5 -> R6.6.
- AI preset: AI_AGENT_RECOMMENDED_R6.5 -> AI_AGENT_RECOMMENDED_R6.6.
- Crypto config schema: 21 -> 22.
- Crypto runtime schema: 22 -> 23.
- Added dedicated R6.6 live engine and R6.6 backtester files.
- Added dedicated Crypto and Forex R6.6 user manuals.

## Validation
- Local AST parse: PASS.
- Local Python bytecode compilation: PASS.
- Manual source audit of the reported R6.5 parser failures: PASS.
- Demo/Testnet/live exchange lifecycle is not claimed by syntax validation.

See docs/USER_MANUAL_V8_4_2_R6_6_CRYPTO.md and docs/USER_MANUAL_V8_4_2_R6_6_FOREX_MT5.md.

---

# V8.4.2 Forex AI Agent R6.5-HOTFIX1 — 2026-09-28

## Fixed
- Fixed the R6.5 startup exception: `UniversalFuturesBotGUI` no longer reaches `v_grid_mode` before the variable exists.
- Added the missing R6.5 GUI/configuration contract fields: Liquidity Entry, Divergence Entry, Divergence Minimum Count, AI TP1 R and AI TP2 R.
- Corrected the AI preset emergency scope from unsupported `BOT_SYMBOL` to MT5-supported `BOT_ONLY`.
- Added S/R timeframe mappings to the AI preset callback.
- Added AI TP1/TP2 persistence and validation; TP2 must remain above TP1.
- Configuration schema advanced from 21 to 22. Runtime schema remains 22.

## Modified
- Forex Grid remains OFF-only; no grid execution path was introduced.
- The R6.5 hotfix controls are initialized before configuration loading, preventing loader-order failures.
- Forex backtester release marker updated to R6.5-HOTFIX1 while retaining the live engine as its strategy source of truth.
- Expanded Forex R6.5 contract tests to cover GUI runtime variables and preset mappings.

## Validation
- AST parse: PASS.
- Bytecode compilation: PASS.
- Module import: PASS.
- GUI runtime-variable declaration audit: PASS.
- Callback binding audit: PASS.
- AI council decision smoke test: PASS.
- AI bounded risk/SL/TP manager smoke test: PASS.
- Preset mapping audit: PASS.
- Full live MT5 execution lifecycle was not claimed by this source-level hotfix audit.

---

# V8.4.2 Crypto repository cleanup + AI-Agent R6.5 current release — 2026-09-27

## Current production files
- `UniversalFuturesBot_CRYPTO_V8.4.2-R9.6.py`
- `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5.py`
- `UniversalForexBot_MT5.py`

## Current backtest/build files
- `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5_BACKTESTER.py`
- `UniversalForexBot_MT5_BACKTESTER.py`
- `BUILD_CRYPTO_EXE.bat`
- `BUILD_CRYPTO_AI_AGENT_R6.5_EXE.bat`
- `BUILD_FOREX_EXE.bat`

## R6.5 Full engine audit + UI/runtime hardening

### Fixed
- GUI execution-log newline defect fixed; long messages now wrap vertically.
- Periodic configuration writes now occur only when settings are dirty.
- Repeated identical completed-candle strategy diagnostics are suppressed.
- CCXT exchange time-difference correction and receive-window hardening added.
- Active R6.5 source comments cleaned of obsolete release labels.

### Added
- Copy Log, Clear Log and Auto Scroll controls.
- Bounded GUI log retention.
- Settings dirty tracking.
- Exchange/account-mode callback validation.
- R6.5 regression contract tests and a full audit report.

### Verified
- Python compilation passed.
- 11/11 R6.5 contract tests passed locally.
- AI decision and AI risk/SL/TP hard-envelope smoke tests passed.

See `docs/CRYPTO_AI_AGENT_R6_5_FULL_AUDIT_2026-09-27.md`.

## Forex/MT5 AI-Agent R6.5 — full parity + backtester + lifecycle hardening — 2026-09-28

### Added
- Crypto AI-Agent R6.5 strategy/evidence-family parity in the MT5 Forex engine.
- AI-Agent recommended preset with explicit YES/NO confirmation.
- AI council controls: 3 minimum families, 0.20 edge, 0.55 family confidence, Trend ON, Structure ON, max 1 conflict.
- Bounded AI management: 0.20%-0.50% risk, 1.50-2.40 ATR SL, 1.00-1.50R TP1 and 2.00-3.00R TP2.
- AI-aware Forex lot sizing using the dynamically selected stop distance.
- Liquidity Swing entry mode and Divergence minimum-count/entry-mode controls.
- Forex Grid Mode parity control; non-OFF grid execution is rejected because the MT5 engine remains single-position Forex-native.
- New Forex AI-Agent R6.5 backtester with CSV/MT5 data input and trade/equity/summary outputs.
- Regression test covering compile, StrategyEngine parity, GUI contract and runtime binding integrity.

### Fixed
- Static Forex ATR lot sizing could overwrite an AI-selected stop distance; AI stop distance is now authoritative.
- Configuration migration no longer silently replaces existing saved profiles with the recommended preset.
- MT5 window-close network/runtime operations are moved away from the Tk UI thread.
- GUI log retention is bounded.

### Modified
- Forex config schema 21 and runtime schema 22.
- AI strategy parameters and protection concepts are aligned to Crypto AI-Agent R6.5 while MT5 execution, broker symbol/lot rules and account modes remain unchanged.

## Repository cleanup
- Removed superseded duplicate Crypto root engines (generic, R9 production, and R9.6 unified-protection copies).
- Removed superseded Crypto AI Agent R2/R3/R4 root copies.
- Removed old V8.2/V8.3 development bot/backtester duplicates from the root.
- Removed the old generic R8 Crypto backtester from the root after introducing the dedicated R6.5 AI-Agent backtester.
- Removed an obsolete root-level V8.4 evidence release-note file.
- Historical code remains recoverable from Git history.

## AI-Agent current release
- Version: `V8.4.2-CRYPTO-AI-AGENT-R6.5`
- AI recommended preset: `AI_AGENT_RECOMMENDED_R6.5`
- Config schema: 21
- Runtime schema: 22

The older R5/R4/R3/R2 entries below are historical changelog entries and do not indicate active files in the main branch.

---

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

## V8.4.2-CRYPTO-AI-AGENT-R4 — Full engine audit + configuration hardening — 2026-09-27

### Fixed
- R3 config-load sizing variable ordering retained and audited.
- AI_AGENT added to the GUI Signal Mode selector.
- AI council settings are now persisted and explicitly propagated through GUI -> worker -> StrategyEngine.
- Corrected the AI decision-reason parameter mismatch found during audit.

### Added
- Per-profile AI Min Families, Edge, Family Confidence, Max Conflicts, Require Trend and Require Structure controls.
- Startup AI council diagnostics.

### Audited
- Indicator/evidence-family engine, strategy modes, configuration/defaults/callbacks, recovery, sizing, protection, Grid, profiles and kill-switch lifecycle.

### Validation
- In-memory compile: PASS.
- AST and GUI callback/self-call audits: PASS.
- Undefined-global-name audit: no unresolved globals detected.
- Deterministic AI-Agent decision smoke tests: PASS.

See docs/CRYPTO_AI_AGENT_R4_RELEASE_NOTES.md.

---

## V8.4.2-R9.6 — Unified ROI protection + configurable reversal hold — 2026-09-27

### Fixed
- Fixed Qty remains literal exchange/base quantity and never enters the Equity-Risk sizing formula.
- Risk sizing, simple SL, fallback SL, ATR SL, TP and reversal-hold modules now have explicit ownership boundaries.
- Only one resolved SL basis can be installed for a normal position.
- Legacy R9.3 protection is isolated behind an explicit compatibility switch.
- Hold-SL WAIT no longer hard-codes ALL_ACTIVE; it follows the selected reversal rule.

### Added
- Independent ON/OFF controls for normal risk/protection modules.
- Simple ROI SL/TP protection.
- Hold Position Until Reverse, ALL_ACTIVE and MIN_FAMILIES.
- Minimum Reverse Families and Hold-SL threshold/WAIT controls.
- R9.6 release documentation.

### Validation
- Python compile: PASS.
- AST/GUI self-call audit: PASS.
- R9.3 protection calculator parity: PASS.
- Simple ROI and reversal-family smoke tests: PASS.
- Live Bybit Demo lifecycle remains required.

See docs/CRYPTO_R9_6_RELEASE_NOTES.md.

---

## V8.4.2-R9.3 — Stop completion + Fixed-Qty execution hardening — 2026-09-27

### Fixed
- Manual STOP no longer blocks the GUI while kill-switch exchange cleanup runs.
- STOP polling continues until the worker exits; the profile lock is retained while the worker is alive.
- A verified kill-switch result is reused by worker finalization instead of submitting duplicate flatten operations.
- FIXED_QTY is literal exchange/base quantity and is passed directly to the market entry order after precision/minimum normalization.
- Fixed Qty no longer changes SL Mode automatically.
- PRICE_%, ROI_%, ATR Dynamic and explicit RISK_% SL behavior remain independently validated.

### Audited
- Strategy/evidence-family engine.
- Settings/defaults and callbacks.
- Configuration save/load and profile isolation.
- Recovery/resume and live exchange snapshot.
- Entry sizing and order submission.
- SL/TP calculation and protection verification.
- Kill switch, watchdog and worker lifecycle.

### Validation
- Python compile: PASS.
- GUI AST/self-call audit: PASS.
- Fixed-Qty branch audit: PASS.
- Live Bybit Demo lifecycle: still required.

See docs/CRYPTO_R9_3_RELEASE_NOTES.md.

---

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

---

# Crypto R9 Release Notes — 2026-09-27

## Problem addressed

R8 persisted profile runtime state, but the Profile Manager could still display a historical RUNNING checkpoint when the worker process was gone. A GUI instance controlling BOT-02 also had no safe way to stop BOT-01 when BOT-01 was running in another process.

## Fixed

1. Cross-process STOP: added profile-scoped control.json and a Profile Manager STOP Selected Bot action. The target worker acknowledges the request and exits through the normal runtime-finalization path.
2. Truthful lifecycle status: a runtime checkpoint is historical data, not proof that a worker is alive. Live lock + worker state controls RUNNING/STOPPING. Stale flat sessions become STOPPED. Stale sessions with saved position/Grid inventory become RECOVERY_REQUIRED.
3. Profile status heartbeat: profile table refreshes every 3 seconds.
4. Max Open Trades: the current engine is single-symbol/one-way and supports one net live position. Values other than 1 are rejected explicitly. Max Completed Trades remains the session trade-count limit.
5. Configuration default parity: missing legacy cooldown uses DEFAULT_COOLDOWN_MIN; missing legacy divergence enable uses DEFAULT_USE_DIVERGENCE.
6. Dead configuration cleanup: removed unused RISK_COST_BUFFER because it did not participate in any live calculation.

## Preserved risk/protection contract

- EQUITY_RISK_% remains quantity sizing.
- FIXED_QTY remains literal exchange/base quantity.
- FIXED_QTY + RISK_% remains the explicit hard-SL risk-budget mode.
- ATR Dynamic protection remains enabled by default for new profiles with 1.5x ATR SL, 1.2x SL-distance TP1, and 2.2x SL-distance TP2.
- Protection continues to use actual filled entry and actual position quantity.
- Grid risk remains independent from normal-strategy risk/SL/TP.

## Validation

- Python py_compile: PASS on the R9 source.
- AST audit: 139 GUI methods; no missing self-method call candidates.
- Import/runtime self-test was not run in the analysis environment because ccxt is not installed there.
- Bybit Demo live lifecycle/order validation is still required before treating the build as production-validated.
---

## V8.4.2-R8 — 2026-09-27 Crypto Fixed-Qty Risk Protection

### Fixed
- **Critical percentage conversion:** the R7 live worker divided Risk Per Trade (%) by 100 before passing it to the sizing engine, while the sizing engine already treated the value as a percentage. R8 removes that double conversion. A GUI value of **0.75** now consistently means **0.75%**.
- Fixed-quantity entries remain literal exchange quantities; selecting FIXED_QTY no longer causes the risk-sizing engine to replace the requested quantity.
- **Risk-based hard SL:** added explicit RISK_% SL mode. With FIXED_QTY, Risk Per Trade (%) becomes the account-risk budget and the hard SL is calculated from the actual filled quantity and actual entry price.
- RISK_% protection uses the actual filled position, so the final SL is recalculated after the exchange confirms the fill.
- ATR sizing/protection is not silently mixed with RISK_% SL mode.
- Fixed a worker-thread Tkinter access hazard: runtime strategy/settings reads now come from a GUI-thread snapshot instead of calling Tk variables directly from the trading worker.
- RISK_% TP1/TP2 remain governed by the existing ATR-derived distance relationship used by the R8 contract; the new mode changes the hard-SL basis only.
- RISK_% is fail-closed unless Sizing Mode is FIXED_QTY; it is also incompatible with Hold-All-Reverse because Hold-All-Reverse intentionally owns the hard-stop semantics.
- Added a GUI callback: switching to FIXED_QTY automatically selects RISK_% SL when Hold-All-Reverse is OFF; switching back to EQUITY_RISK_% returns the SL selector to PRICE_%.

### Added
- SL Mode option: RISK_%.
- Config schema 10 and runtime schema 7.
- Worker-safe GUI configuration snapshot and persisted sizing/protection-basis metadata.
- Runtime diagnostics for fixed-quantity risk SL, including a conservative leverage-envelope warning when the required stop distance is wide.
- R8 regression suite: tests/test_crypto_r8_regressions.py.
- Clear separation between EQUITY_RISK_% quantity sizing and FIXED_QTY + RISK_% stop-risk budgeting.

### Preserved
- ADAPTIVE_EVIDENCE strategy logic and thresholds.
- R6 cooldown and Hold-SL WAIT fixes.
- R7 lifecycle, stale RUNNING normalization, exchange max-quantity enforcement and profile locking.
- Actual-fill protection/recovery architecture.
- Grid risk remains independent from normal-strategy sizing/protection.

### Risk note
A fixed quantity plus a percentage-of-equity risk target can mathematically require a much wider price stop than an ATR stop. At high leverage, the liquidation price may be reached before such a stop. R8 therefore treats the percentage as a calculated risk target, not a guarantee against liquidation; exchange margin and liquidation rules remain authoritative.

---
## V8.4.2-R7 — 2026-09-27 Crypto Lifecycle + Risk-Boundary Hardening

### Fixed
- **Critical risk-sizing bug:** live `0.75` Risk Per Trade was being interpreted as 75% of equity. R7 correctly interprets the GUI percentage as `risk_pct / 100`.
- **Critical exchange-size boundary:** live entries are now clamped to CCXT/exchange maximum amount and precision before order submission.
- **Critical profile lifecycle bug:** Stop now has an explicit STOPPING phase and waits for the worker to exit before the profile lock is released.
- Same-process profile ownership is now recognized while the worker is running/stopping.
- Flat stale RUNNING/STOPPING/CRASHED runtime checkpoints without saved position/Grid state are normalized to STOPPED.
- Stale lifecycle status alone no longer blocks deletion of an otherwise flat orphaned profile.
- Missing `use_atr` configuration now falls back to `DEFAULT_USE_ATR`, matching the new-profile default.
- Max Open Trades is explicitly normalized to the single-symbol engine hard limit of 1; 0 is no longer presented as unlimited.
- Removed duplicate `DIVERGENCE_INDICATORS` definition.

### Added
- Runtime schema 6 with explicit stop-request state.
- Non-blocking stop-completion polling and worker-finished GUI callback.
- Exchange quantity-cap diagnostics and actual-risk-after-cap diagnostics.
- `tests/test_crypto_r7_regressions.py`.
- `docs/CRYPTO_R7_RELEASE_NOTES.md`.

### Modified
- Crypto live marker: `V8.4.2-CRYPTO-EVIDENCE-HARDENED-R7`.
- Crypto audit marker: `V8.4.2-ENGINE-AUDIT-2026-09-27-R7`.
- Crypto backtester marker/parity version aligned to R7; its risk percentage formula was already percentage-correct.
- README and production manifest updated to Crypto R7.

### Preserved
- ADAPTIVE_EVIDENCE thresholds and Evidence-family definitions.
- Completed-candle strategy logic.
- ATR/ADX regime-gate semantics.
- Hold-All-Reverse and post-SL opposite lock.
- Actual-fill SL/TP protection architecture.
- Recovery identity checks and one-net-position-per-profile execution model.

### Validation
- R6 regression suite: **5 passed**
- R7 regression suite: **8 passed**
- Combined local regression tests: **13 passed**
- Python `py_compile`: PASS
- Module import: PASS
- Live exchange order lifecycle is not claimed by the local unit tests; Bybit Demo validation remains required.

---

## V8.4.2-R6 — 2026-09-27 Crypto Execution Hardening

### Fixed
- **Critical live cooldown defect:** a flat bot was refreshing `last_flat_time` during every 30-second polling cycle. With a 15-minute cooldown this prevented the cooldown from ever expiring and could block valid entries indefinitely.
- Cooldown now starts only when the engine observes a real live-position/active-trade state transition to flat.
- **Hold-SL WAIT reversal defect:** the WAIT prerequisite was being set to false and then overwritten by the later ALL-REVERSE calculation. R6 preserves the WAIT gate until the configured Hold-SL ROI threshold has actually been reached.
- Removed an unreachable duplicate ADAPTIVE_EVIDENCE startup log branch.

### Added
- Explicit `COOLDOWN STARTED` runtime diagnostics.
- Dedicated `tests/test_crypto_r6_regressions.py` coverage for cooldown, Hold-SL WAIT, all signal modes and SINGLE_SIGNAL conflict behavior.
- R6 release documentation.

### Modified
- Crypto live production marker: `V8.4.2-CRYPTO-EVIDENCE-HARDENED-R6`.
- Engine audit marker: `V8.4.2-ENGINE-AUDIT-2026-09-27-R6`.
- Crypto backtester release marker aligned to R6; historical signal logic remains unchanged.

### Strategy safety
- No Evidence-family threshold was weakened.
- No new directional indicator was added to force trades.
- Existing saved profiles remain authoritative.
- Demo/testnet validation remains required before live deployment.

---

## V8.4.2-R5 — 2026-09-22 Managed-Order Cleanup Hotfix

### Fixed
- A closed SL/TP could still leave retired order IDs in the managed-order cleanup set.
- Bybit retCode 110001 ("order not exists or too late to cancel") was previously treated as a cancellation failure.
- The same inactive IDs could therefore be retried every 30 seconds until the 3-cycle safety halt.
- Terminal managed orders are now recognized as inactive and removed from tracking.
- Genuine unresolved open/protection orders still fail closed.

## V8.4.2-R5 — 2026-09-22 API Resilience Hotfix

### Fixed
- BOT-01 could halt after three consecutive transient Bybit Demo wallet-balance failures. Account reads now use bounded retry/backoff.
- Transient network/time-out/rate-limit/exchange-unavailable errors have a separate recovery budget of 10 execution cycles.
- Non-transient execution errors retain the 3-cycle fail-closed safety limit.
- The main execution cycle reuses one successful wallet-balance response for balance and equity calculations.
- Final position inspection is best-effort so a failed cleanup read does not hide the original runtime error.

### Safety
- No new entry is attempted when a verified account snapshot is unavailable.
- Persistent exchange/API failure still causes a fail-closed stop.
- No stale balance is used for new risk sizing.

## V8.4.2-R5 — Engine Audit Follow-up — 2026-09-22

### Fixed
- Crypto R5 backtester Grid fill processing no longer mutates the fill queue while iterating, removing a repeated-fill/infinite-loop defect.
- Crypto backtester Grid cooldown is now actually enforced after Grid risk/exit resets.
- Crypto backtester daily drawdown now includes adverse marked-to-market PnL.
- Crypto backtester now enforces the configured maximum loss streak.
- ADAPTIVE_EVIDENCE blocked-signal diagnostics now identify the actual gate/family/edge blocker instead of only reporting BF/SF counts.
- Runtime logs now expose the completed-candle ADX value and ADX gate result.

### Added
- Explicit ADX Period setting (default 14) in Crypto and Forex R5 GUI/configuration.
- ADX Period persistence and validation.
- R5 Engine Audit document: docs/R5_ENGINE_AUDIT_2026-09-22.md.

### Modified
- New Crypto profiles: ATR gate ON, Grid OFF, 0.75% risk, 15-minute cooldown.
- New Forex profiles: 0.50% risk, ATR gate ON, ATR Dynamic protection ON, news/session/correlation guardrails ON, 2% daily loss, and Forex TP1 = 1.30R.
- Crypto protection remains 1.50 / 1.20 / 2.20 ATR/SL-distance; Forex uses 1.50 / 1.30 / 2.20.

### Diagnostic clarification
- In EVIDENCE_BLOCKED_BF3_SF1_EDGE0.25, BF3 is the bullish-family count and SF1 is the bearish-family count. SF does not mean "strong families".

### Safety
- Evidence thresholds were not weakened to manufacture more trades.
- Existing saved profiles remain authoritative; these are new-profile defaults.
- Demo/testnet validation remains required.

## V8.4.2-R5 — Repository Cleanup / Production Layout — 2026-09-21

### Changed
- Established four production source files with stable names:
  - `the superseded generic Crypto engine`
  - `the superseded generic Crypto backtester`
  - `UniversalForexBot_MT5.py`
  - `UniversalForexBot_MT5_BACKTESTER.py`
- Removed superseded versioned production copies from the main working tree where present.
- Made the Forex R5 production engine self-contained so it no longer depends on a historical V8.4.0 source file.
- Updated the Forex R5 backtester to load the clean production Forex engine.
- Added clean production test entry points under `tests/`.
- README now identifies the four current production files as the only files to run.
- Historical releases should be recovered from Git history/tags/releases, not from duplicate source files in the production root.

### Important
- This cleanup changes filenames, not the intended R5 trading contract.
- The current single-symbol execution coordinator still manages one net position per bot/symbol.
- Demo validation remains required before live trading.

---

## V8.4.2-R5 — Crypto Evidence Hardened + Backtester — 2026-09-21

### Fixed
- Max Open Trades values above 1 no longer abort startup; they normalize to 1 net position for the current single-symbol coordinator.
- Added ATR Dynamic SL/TP multiplier safety bounds.
- Preserved completed-candle ATR and actual-filled-entry protection calculations.
- Preserved explicit Evidence-family parameters in the live execution path.
- Removed the pandas FutureWarning in Volume/S-R boolean aggregation.

### Added
- Crypto V8.4.2-R5 hardened live engine.
- Crypto V8.4.2-R5 strategy-parity backtester.
- Raw OHLCV/DataFrame/CSV backtesting.
- Completed 4H MTF alignment, causal divergence and Volume/S-R.
- ATR Dynamic SL 1.50x ATR, TP1 1.20x actual SL distance, TP2 2.20x actual SL distance.
- R5 deterministic engine audit and GUI smoke tests.
- R5 release documentation.

### Modified
- Build marker: V8.4.2-ENGINE-AUDIT-2026-09-21-R5.
- Backtester defaults synchronized to ADAPTIVE_EVIDENCE, 2 evidence families, family score 0.35, Trend required, independent non-Trend family required and Adaptive Edge 0.18.
- ATR is a regime gate in ADAPTIVE_EVIDENCE and is not counted as an independent directional family.
- Historical execution remains completed-candle signal -> next-candle-open entry with conservative SL-first same-bar ambiguity.

### Validation
- 27/27 Crypto R5 engine checks PASS.
- GUI smoke PASS.
- Synthetic raw-OHLCV backtest PASS.
- SINGLE_SIGNAL conflict fail-closed PASS.

### Safety
- The execution engine remains one-net-position-per-bot/symbol. R5 does not claim two independent same-symbol positions.
- Historical backtests do not prove exchange order acceptance, conditional-trigger behavior, partial fills or recovery; demo validation remains required.

---

## V8.4.2-R5 — Forex / MT5 Evidence Hardened — 2026-09-21

### Fixed
- Added fail-safe Max Open Trades handling; values above 1 normalize to 1 net position per bot/symbol.
- Fixed the Forex GUI cooldown-row placement.
- Added ATR Dynamic SL/TP parity with the Crypto R5 protection contract.
- ATR Dynamic protection uses the latest completed candle and actual filled entry/position quantity.
- Fixed the Forex backtester protection-mode parity gap for ATR / PRICE_% / ROI_% target handling.
- Added post-SL opposite-direction lock coverage to the strategy-parity backtester.

### Added
- Persistent max_open_trades, atr_sl_mult, atr_tp1_mult and atr_tp2_mult configuration fields.
- Config schema 9 migration compatibility.
- R5 Protection / Execution GUI controls.
- Canonical Forex R5 live wrapper: UniversalForexBot_V8_4_2_MT5_FOREX_EVIDENCE_HARDENED_R5.py.
- Forex R5 strategy-parity backtester.
- Forex R5 audit tests and release documentation.

### Modified
- New-profile defaults are aligned with the R5 Evidence-family strategy contract: ADAPTIVE_EVIDENCE, 2 evidence families, family minimum score 0.35, Trend required, independent non-Trend family required, Adaptive Edge 0.18, synchronized trend/momentum/flow/structure defaults.
- ATR defaults are SL 1.50×, TP1 1.20× SL distance and TP2 2.20× SL distance.
- Existing saved configurations remain authoritative; missing R5 fields use safe defaults.

### Validation
- **26/26 local Forex R5 audit checks PASS**
- GUI smoke: PASS.
- Config save/load round-trip: PASS.
- Synthetic raw-OHLCV backtest: PASS.
- SINGLE_SIGNAL conflict fail-closed: PASS.
- Evidence-family decision contract: PASS.

### Safety
- The current single-symbol execution coordinator still manages one net position per bot profile. This release does not claim two independent MT5 positions from one profile.
- Demo/paper broker validation remains required before live deployment.

---

## V8.4.1 FOREX-R2 — MT5 Forex Full Engine Audit — 2026-09-21

### Fixed
- Fixed SINGLE_SIGNAL conflict semantics to fail closed on simultaneous bullish/bearish evidence.
- Fixed Evidence-Family diagnostic parity with Trend-family and independent-family gates.
- Added startup strategy/risk/SL/TP preflight before MT5 broker setup.
- Fixed runtime signal-mode validation to accept the complete supported mode set, including ADAPTIVE_EVIDENCE.
- Added config schema 8 and migration logging.
- Fixed Forex backtester NWE argument parity with the live implementation.
- Added raw-OHLCV run_backtest() API coverage.

### Preserved safety/execution architecture
- MT5-native Forex execution and broker lot rules.
- Broker-side SL reconciliation and fail-closed protection handling.
- order_send=None entry reconciliation to avoid blind duplicate retries.
- Runtime checkpoint/recovery and single-instance profile lock.
- Spread/slippage/session/Friday/news/correlation/trailing/ATR-SL/risk protections.

### Validation
- **7/7 audit groups PASS**
- GUI construction/default preflight: PASS.
- Config save/load round-trip: PASS.
- Full 19-module strategy frame including NWE: PASS.
- Raw OHLCV backtest: PASS.

---

## V8.4.1-R2 — Full Follow-up Engine Audit — 2026-09-21

### Fixed
- Restored the V8.4.1 live source as the complete self-contained crypto engine and retained the categorized Evidence-Family GUI.
- Fixed legacy `SINGLE_SIGNAL` ambiguity: if both bullish and bearish directional evidence exists, the engine now returns no trade.
- Fixed `decision_reason()` so Evidence-Family Trend/Independent requirements match the actual decision engine.
- Fixed the `Use all divergence sources` checkbox so it actually enables/disables all divergence sources and persists correctly.
- Added comprehensive startup strategy/risk/SL/TP validation before exchange-side leverage/order setup.
- Added legacy-config migration logging while preserving explicitly saved user settings.
- Preserved the current crypto GUI default with Confirmed Divergence enabled.

### Backtester
- Fixed direct `run_backtest()` calls with raw OHLCV data that contains `time` but no `datetime`.
- Fixed direct `run_backtest()` calls that did not pre-build strategy indicator columns.
- Removed duplicate top-level Liquidity Swings and Trendline Breakout implementations.
- Synchronized backtester Evidence-Family diagnostics and SINGLE_SIGNAL behavior with live.

### Tests
- Reworked the regression suite to resolve repository-root paths correctly when run from `tests/`.
- Added raw-OHLCV backtester regression coverage.
- Added Evidence-family conflict/gate coverage.

### Validation
- **60 PASS / 0 FAIL / 0 SKIP**
- Live, backtester and recovery AST/compile: PASS.
- Full 19-module indicator chain: PASS.
- GUI initialization and save/load: PASS.
- StrategyEngine behavior and diagnostics: PASS.
- Raw-OHLCV backtest execution: PASS.

---

## V8.4.1 — FINAL Full Engine Audit — 2026-09-21

### Fixed
- Restored 11 missing core live indicator function definitions that had been lost during the categorized GUI merge.
- Hardened ADX so direct indicator callers do not depend on Supertrend-generated true-range columns.
- Added the missing Divergence Min Div GUI control and save/load coverage.
- Made Use All Divergence Sources functional and persistent.
- Passed all Evidence-Family controls explicitly into decision diagnostics.
- Corrected missing signal-mode fallback to the current ADAPTIVE_EVIDENCE default.
- Added exchange/account-mode preflight validation.
- Made SL/TP/BE protection verification fail closed on inconclusive exchange order-state responses.

### Added / Modified
- Final categorized V8.4 Evidence-Family Section 3.
- Final 19-module indicator-chain regression coverage.
- GUI construction and configuration round-trip tests.
- Protection fail-closed regression test.
- Final full audit release notes.

### Retained from V8.2/V8.3
- Actual-fill SL/TP calculation and verification.
- TP1 break-even protection replacement.
- Recovery/resume identity checks.
- Exact managed-order ownership and orphan-order safety.
- Grid order verification/cancellation safety.
- Hold-All-Reverse and Hold-SL WAIT.
- Post-SL opposite-signal lock and same-candle protection.
- Profile locking, profile deletion safety and multi-bot isolation.
- Stale-data and consecutive-cycle-error safety.
- Emergency-stop scope.

### Validation
- **54 PASS / 0 FAIL / 0 SKIP**
- Live, backtester and recovery AST/compile checks: PASS.
- Full deterministic 19-module indicator chain: PASS.
- Evidence-Family and legacy signal modes: PASS.
- GUI init and save/load round-trip: PASS.
- Protection verification fail-closed test: PASS.

---

## V8.4.1 — Engine Audit and Source Hardening — 2026-09-21

### Fixed
- Repaired syntax/indentation corruption in the crypto live engine, recovery engine and backtester.
- Removed the duplicate live `UniversalFuturesBotGUI` definition and duplicate top-level Liquidity Swings / Trendline implementations.
- Added persistence for Adaptive Evidence settings.
- Hardened backtester MTF input handling for `datetime` or millisecond `time` data.
- Aligned backtester default signal mode with the live engine: `ADAPTIVE_EVIDENCE`.

### Validation
- Three crypto sources: AST parse and Python compilation PASS.
- Import smoke tests PASS.
- 19-module indicator smoke tests PASS.
- All signal modes and Grid modes PASS in deterministic synthetic tests.
- Added `tests/test_v841_engine_audit.py`.

---

## V8.3.3 — Full Engine / Strategy / Configuration Audit — 2026-09-20

### Fixed
- Fixed the V8.3.2 orphan-order ownership gap: exact SL/TP/Grid order IDs are now retained in runtime recovery state after the live position becomes flat.
- Fixed strict Bybit open-order safety so a full 50-order page cannot be mistaken for a complete inventory snapshot.
- Added startup preflight validation for sizing mode, risk %, fixed quantity, daily drawdown, emergency loss, emergency scope and cooldown.

### Added
- Runtime schema version 5.
- Persistent `retired_managed_order_ids`.
- Centralized requested new-profile defaults.
- Full-audit regression test file `tests/test_v833_full_audit.py`.
- V8.3.3 release notes.

### Modified
- New-profile defaults are Adaptive Conservative defaults; existing saved profiles remain authoritative.
- Grid shutdown/direction cleanup retains exact managed IDs for future orphan cleanup.
- Unknown/manual orders remain fail-closed and are never auto-adopted.

### Validation
- Source compilation/import: PASS.
- Adaptive isolation: PASS.
- Retired-order checkpoint extraction: PASS.
- Strict open-order page guard: PASS.
- Runtime checkpoint serialization: PASS.

- Added V8.3.3 strategy-parity backtester updates: explicit Adaptive per-profile parameters, synchronized causal Volume S/R logic, and pandas nullable-Boolean aggregation compatibility.
- Added backtester parity regression coverage: 8/8 tests passed, including a deterministic synthetic full-module run.

---

## V8.3.1 — Adaptive Startup + Multi-Bot Isolation Fix — 2026-09-20

### Fixed

- Fixed a real V8.3.0 startup failure in ADAPTIVE_SCORE: start_bot() referenced adaptive_edge before that worker-local variable existed.
- Adaptive Edge and Adaptive Minimum Weight are now read and validated in the startup callback before Adaptive logging.
- Removed mutable StrategyEngine.adaptive_edge and StrategyEngine.adaptive_min_weight class state.
- Live Adaptive thresholds are passed explicitly to the decision engine and decision diagnostics.
- Backtester Adaptive thresholds are passed explicitly instead of relying on global cfg_adaptive_edge / cfg_adaptive_min_weight values.

### Hardened

- Multiple bot profiles running concurrently can no longer overwrite each other's Adaptive thresholds through shared StrategyEngine class state.
- Live and backtester decision contracts now use the same explicit Adaptive parameter interface.

### Validation

- Live source compilation: PASS.
- Backtester source compilation: PASS.
- Live/backtester Adaptive decision parity: PASS.
- Startup NameError regression: PASS.
- Per-profile Adaptive isolation: PASS.
- Regression suite: **6/6 PASS**.

---

## V8.3.0 — Hardened Adaptive Engine — 2026-09-20

### Added
- Added `ADAPTIVE_SCORE`, a correlation-aware weighted voting mode across the 19-module V8 strategy family.
- Added Adaptive Edge and Adaptive Minimum Weight configuration.
- VOL and ATR are regime gates in Adaptive mode rather than independent candle-direction votes.
- Added daily peak-equity drawdown protection and persisted session/daily peak state.
- Added stale-market-data detection and a three-consecutive-cycle-error fail-closed halt.
- Added emergency-stop scope with safe `BOT_SYMBOL` default and explicit `ALL_ACCOUNT` option.
- Added managed-order cleanup for normal/Grid shutdown and strategy reversal paths.
- Added Adaptive Grid parity: Grid SCORE/NEUTRAL_GRID now uses the same weighted evidence model when ADAPTIVE_SCORE is active.
- Added V8.3 hardened strategy-parity backtester and 5/5 regression tests.

### Fixed / Hardened
- Configuration schema bumped from 6 to 7.
- Runtime checkpoint schema bumped from 3 to 4.
- Daily drawdown no longer relies only on closed wallet balance; unrealized equity drawdown is included through the daily peak-equity reference.
- Emergency circuit breaker no longer defaults to closing unrelated account positions.
- Normal cleanup/reversal paths prefer known bot-managed order IDs instead of broad symbol-wide cancellation.
- Existing confirmed-candle, confirmed-divergence and higher-timeframe look-ahead protections remain in place.

### Modified
- New profiles default to `ADAPTIVE_SCORE`; existing saved profiles retain their saved strategy mode.
- Backtester defaults to the same Adaptive strategy family and exposes Adaptive Edge / Minimum Weight.
- Grid score validation now understands weighted Adaptive capacity.
- Release documentation now records the exact strategy/risk hardening contract.

### Validation
- Live bot compilation: PASS.
- Backtester compilation: PASS.
- Live/backtester Adaptive decision parity: PASS.
- Synthetic backtest smoke test: PASS.
- Safety-contract static audit: PASS.
- Regression suite: **6/6 PASS**.

### Important
V8.3.0 does not claim a guaranteed maximum-profit configuration. The new strategy is designed to improve signal quality and robustness; historical backtests remain OHLC approximations and demo/testnet validation is required before live deployment.

---
## V8.2.6 — Advanced Strategy Modules + Backtester Parity — 2026-09-20

### Added
- Added **DIVERGENCE** as a new directional module using confirmed/causal pivots from the supplied Divergence for Many Indicators v4 source.
- Added MACD, MACD Histogram, RSI, Stochastic, CCI, Momentum, OBV, VWMACD, CMF and MFI divergence sources.
- Added **VOL_SR** as a new directional module using the supplied Volume-based Support & Resistance Zones V2 volume-confirmed fractal/S/R logic.
- Added four configurable Volume S/R timeframes, volume threshold, timeframe voting and entry mode controls.
- Added both modules to the live strategy contract, Grid SCORE/NEUTRAL_GRID direction logic, Hold-All-Reverse persistent states and the strategy-parity backtester.
- Added V8.2.6 regression tests covering source parsing, 19-module contract, new settings, new indicator columns, module voting, normal/Grid simulation and signal-engine behavior.

### Fixed / Hardened
- Configuration schema bumped from version 5 to **6** for the new settings.
- Higher-timeframe S/R backtest states are aligned to the higher-timeframe candle close instead of the candle open, preventing future-data leakage during lower-timeframe bars.
- Backtester history is extended when higher-timeframe S/R is enabled so configured D/W S/R has meaningful historical context.
- The backtester compatibility decide() helper no longer references an undefined df.
- Advanced live events now have explicit diagnostic logging.
- Existing V8.2.5 CCXT market-loading and Grid-default fixes remain included.

### Modified
- Strategy module count increased from 17 to **19**.
- Live GUI Strategy tab now exposes Divergence and Volume S/R controls.
- Save/load configuration, Grid module counting, combination lab and backtester JSON configuration include the new settings.
- Chart-only TradingView drawing objects are converted to numerical strategy states rather than being treated as executable orders.

### Validation
- Live bot AST parse: PASS.
- Backtester AST parse/import: PASS.
- 19-module contract: PASS.
- New divergence/S/R columns: PASS.
- All-module synthetic voting: PASS.
- Normal and NEUTRAL_GRID synthetic backtests: PASS.
- Regression suite: **7/7 PASS**.

### Important
The backtester remains a historical OHLC model and cannot reproduce every exchange-specific fill, latency, order-book, funding, liquidation or conditional-order behavior. Demo/testnet validation remains required before live deployment.

---

## V8.2.5 — Strategy-Parity Backtester + Grid Default Audit — 2026-09-20

### Added
- Added the V8.2.5 strategy-parity backtester package locally with all 17 live directional modules, live signal modes, normal SL/TP/risk behavior, Hold-All-Reverse, post-SL lock, Grid modes, sweep, walk-forward, combination lab, caching and exports.
- Added V8 bot-config JSON import/export to the backtester.
- Added regression coverage for all 17 modules and the V8.2.4 signal contract.

### Fixed
- Fixed the live Grid default: Global Grid SL changed from 5.0% to 6.0%. The previous 5.0% value was invalid with 5 levels × 1.0% spacing because the validator requires SL to be greater than the total grid depth.
- Backtester EMA Filter now has its own EMA period instead of incorrectly reusing the EMA Cross slow period.
- Backtester indicator calculations are conditional in the same places as the live bot.
- Backtester now includes the live Liquidity Swings and Trendline modules that were absent from the older reference backtester.
- Backtester signal decisions use the centralized V8.2.4 StrategyEngine rather than the old ALL/MAJORITY-only rule.

### Modified
- Added exact live-style protection conversion, TP1/TP2 split handling, break-even, reversal-hold checks and Grid basket protection simulation.
- Added conservative same-candle SL/TP ambiguity handling: SL first.
- Added monthly statistics to Excel output.

### Validation
- Live V8.2.5 source compilation: PASS.
- Backtester compilation: PASS.
- Indicator source parity check: all 16 indicator functions match the uploaded V8.2.4 bot implementations.
- Backtester regression suite: 6/6 PASS.
- Synthetic normal and Grid simulations: PASS.

---
## V8.2.4 — Strategy Decision + Execution Safety Audit — 2026-09-20

### Added
- Added `ANY_NON_CONFLICTING` signal mode: one or more enabled directional modules may trigger when all active votes point to one side; contradictory BUY/SELL votes are blocked.
- Added `StrategyEngine.decision_reason()` and per-module state diagnostics.
- Bumped configuration schema to version 5.

### Fixed
- `2_SIGNALS`, `3_SIGNALS` and `4_SIGNALS` now enforce 2/3/4 confirmations in the central StrategyEngine, preventing caller/default drift.
- Unknown saved signal modes are rejected safely during load and fall back to `SINGLE_SIGNAL`.
- Removed worker-thread calls to `stop_bot()` from max-drawdown and trade-limit shutdown paths because `stop_bot()` accesses Tkinter widgets.
- Persisted config/runtime schema values use the central schema constants.

### Modified
- Execution logs now report directional states, effective required confirmations and a deterministic decision reason.
- Existing Grid, recovery, profile deletion, SL/TP and exchange protection behavior remains preserved.
- V8.2.3 symbol/checkpoint normalization remains included.

### Validation
- Python compilation: PASS.
- GUI attribute/callback audit: PASS.
- Save/load coverage audit: PASS.
- V8.2.4 regression suite: 12/12 PASS locally.
- Full live exchange order lifecycle: not claimed by this audit.

### User-visible signal behavior
- With `2_SIGNALS`, EMA_CROSS=BULL + VWAP_DELTA=BEAR produces no trade because the score is B1/S1 and two same-direction confirmations are required.
- `ANY_NON_CONFLICTING` is available when the intended rule is that any enabled module may trigger, while contradictory directions must remain blocked.

---
## V8.2.2 — Profile Manager Selection/Identity Fix — 2026-09-20

### Fixed
- Fixed the profile-manager state mismatch where the tree could visibly select BOT-02 while the top Connection-section Load Profile action still used the Bot Profile ID field containing BOT-01.
- The top Connection controls are now explicitly ID-driven: **Load Profile ID** and **Delete Profile ID** operate on the Profile ID field.
- The Profile Manager controls remain selection-driven: **Load Selected** and **Delete Selected** operate on the selected tree row.
- After deleting the current profile, the GUI synchronizes the Profile ID field with the first remaining saved profile instead of leaving a deleted ID such as BOT-01 active.
- Profile deletion safety, recovery-state blocking, profile locking and master trade/session history preservation remain unchanged.

### Validation
- V8.2.2 source compilation: PASS.
- Profile-control consistency static checks: PASS.

## V8.2.1 — Profile Delete + Safety Hardening — 2026-09-20

### Added
- Delete Profile button in the Connection/Profile controls.
- Delete Selected button in the Saved Bot Profiles manager.
- Confirmation before destructive profile deletion.
- Profile-operation safety contract (PROFILE_OPERATION_SCHEMA_VERSION = 1).

### Fixed / Hardened
- Profile deletion is blocked while the current GUI bot is running.
- Profile deletion is blocked when another bot process owns the profile lock.
- Recovery checkpoints with RUNNING, CRASHED, STOPPING or PAUSED_WITH_POSITION status cannot be deleted.
- Saved protected positions, active trades, active Grid state, filled Grid levels and Grid protection order IDs block deletion.
- Legacy BOT-01 root configuration is removed together with BOT-01 only after safety checks.
- Master SQLite trade/session history is preserved.
- After deleting the selected active profile, the GUI returns to BOT-01 as a clean identity.

### Audit
- Existing StrategyEngine, strategy modules, settings/defaults, save/load/copy callbacks and Grid/recovery execution paths were retained.
- V8.2.1 Python AST parse and compilation passed.
- Dedicated profile-delete static regression checks passed.

## V8.2 Modular Engine + Safety Hardening — 2026-09-20

### Added

- New V8.2 Modular StrategyEngine for GUI/exchange-independent final signal voting.
- Centralized V8.2 contracts for supported exchanges, signal modes and Grid modes.
- Configuration schema version 4 and runtime checkpoint schema version 3.
- Cross-module startup preflight validation before profile-lock acquisition or exchange-side mutations.
- 20-second CCXT client timeout.
- V8.2 static, strategy, recovery and opt-in exchange-demo regression tests.
- V8.2 release notes and demo/testnet validation plan.

### Fixed / Hardened

- SINGLE_SIGNAL no longer lets an ambiguous module reporting both bull and bear win merely because its bull branch appears first; ambiguous votes are ignored.
- Invalid minimum signal score is rejected.
- Invalid signal mode is rejected before exchange initialization.
- Non-positive leverage is rejected before exchange configuration.
- Existing Grid validation remains a mandatory pre-order gate.
- Existing recovery and Grid fail-closed protection behavior is preserved.

### Validation

- Local V8.2 regression suite: 22 tests passed, 1 exchange-demo gate skipped.
- Full real exchange lifecycle is not claimed by this release; demo/testnet execution remains required.

# Changelog


# V8.4.2 Crypto AI Agent R6.5 — 2026-09-27

## Fixed
- Routed worker-to-GUI updates through a thread-safe callback queue.
- Removed direct worker-thread reads of Tkinter Entry/Variable objects from execution-reachable methods.
- Routed dashboard/checkpoint/worker-finish UI updates through the GUI bridge.
- Made emergency-stop UI updates thread-safe.
- Kept the profile lock held until background kill-switch cleanup is finished and verification is complete.
- Made idle GUI close avoid exchange cleanup when no active bot runtime exists.
- Changed runtime protection basis to AI_DYNAMIC for normal AI-Agent sessions.
- Persisted TP1/TP2 quantities and split metadata in recovery state.
- Repaired TP2 protection reconstruction to preserve the configured TP split rather than assuming 50/50.
- Corrected the AI Required diagnostic to use the AI minimum-family setting.

## Added
- Runtime schema: 21 -> 22.
- GUI callback queue and non-blocking worker-to-GUI bridge.
- Automated R6.5 contract tests.

## Retained
- Deterministic AI evidence-family engine.
- Bounded AI risk/ATR-SL/ATR-TP manager.
- Actual-fill protection and fail-closed exchange verification.
- Mandatory kill switch and watchdog lifecycle.

## Validation
- AST parse: PASS.
- Bytecode compilation: PASS.
- AI decision/decision-reason smoke tests: PASS.
- TP split smoke tests: PASS.
- Worker Tk-thread safety audit: PASS.
- StrategyEngine keyword audit: PASS.
- Full live exchange lifecycle not claimed in this patch.



# V8.4.2 Crypto AI Agent R6.4 — 2026-09-27

## Fixed
- Fixed the Windows GUI "Not Responding" condition during window close.
- Removed the synchronous GUI-thread call to the exchange kill switch from on_close().
- GUI shutdown now starts the background stop-cleanup worker and returns control to Tkinter immediately.
- _poll_stop_completion() now waits for the execution worker, stop-cleanup worker, and kill-switch activity without blocking the GUI.
- The window is destroyed only after the mandatory kill switch verifies FLAT + NO OPEN ORDERS.
- When cleanup verification fails, the GUI remains open and reports that safe close is blocked rather than silently destroying the window.

## Modified
- Added _close_requested lifecycle state.
- Configuration/runtime schema: 20 -> 21.
- Internal version: V8.4.2-CRYPTO-AI-AGENT-R6.4.
- Audit marker: V8.4.2-AI-AGENT-AUDIT-2026-09-27-R6.4-GUI-SHUTDOWN-NONBLOCKING-HOTFIX.

## Retained
- Mandatory fail-closed kill switch.
- Background exchange flatten/cancel/verification.
- Watchdog heartbeat protection.
- Actual-fill SL/TP protection.
- AI-Agent risk/ATR-SL/ATR-TP management.
- Persisted configuration migration.

## Validation
- Python AST parse: PASS.
- Python bytecode compilation: PASS.
- Static shutdown audit: PASS; on_close() contains no direct GUI-thread _activate_kill_switch() call.
- Static lifecycle audit: PASS; GUI close schedules background cleanup and polls completion.
- Full live exchange lifecycle was not claimed by this patch.


# V8.4.2 Crypto AI Agent R6.3 — 2026-09-27

## Fixed
- Fixed repeated CONFIG MIGRATION schema 18 -> 19 messages.
- Configuration migration now persists the new schema marker after the full GUI configuration load completes successfully.
- Existing user values remain authoritative; migration does not replace saved trading settings.
- Legacy use_atr_sl remains synchronized with canonical simple_atr_sl_enabled during migration.

## Modified
- Configuration schema: 19 -> 20.
- Runtime schema: 19 -> 20.
- Replaced the old R3-specific migration log with a clearer sizing-compatibility migration message.
- Internal version: V8.4.2-CRYPTO-AI-AGENT-R6.3.
- Audit marker: V8.4.2-AI-AGENT-AUDIT-2026-09-27-R6.3-MIGRATION-PERSISTENCE-HOTFIX.

## Validation
- Python compilation of the repaired local source: PASS.
- Migration persistence logic: static audit PASS.
- Existing-values-authoritative behavior retained.
- No live exchange lifecycle claim in this patch.


# V8.4.2 Crypto AI Agent R6.2 — 2026-09-27

## Fixed
- Repaired the direct `StrategyEngine.decision_reason()` call that passed `ai_family_confidence` instead of `ai_min_family_confidence`.
- Repaired the direct call that passed `ai_max_conflicts` instead of `ai_max_conflicting_families`.
- This removes the cycle error observed in Bybit Demo and prevents the three-cycle fail-closed halt caused by the bad keyword contract.

## Added / Modified
- AI-Agent recommended preset now shows ATR-TP ON in the GUI/configuration, matching the runtime AI TP-management path.
- NEW-profile Hold-All-Reverse default changed from ON to OFF because the R6.x dynamic AI manager intentionally does not run while Hold-All-Reverse is active.
- When AI_AGENT is active but the recommended preset was not explicitly confirmed, the worker logs a notice and continues using the current saved GUI settings without silently overwriting them.
- When HOLD-ALL-REVERSE blocks the AI manager, the worker logs the reason explicitly.
- Configuration schema: 18 -> 19.
- Runtime schema: 18 -> 19.

## Retained
- Deterministic AI evidence-family decision engine.
- AI bounded risk, ATR-SL and R-multiple TP management.
- Actual-fill-based final protection resolution and exchange-side verification.
- Fail-closed kill-switch behavior.

## Validation
- Python AST/syntax parse: PASS.
- Direct StrategyEngine call keyword audit: PASS; no unexpected keyword arguments remain for decision_reason, decide_signal or ai_agent_decision.
- decision_reason AI_AGENT smoke test: PASS.
- Full live/demo exchange lifecycle was not claimed; continue with Bybit Demo/Testnet validation.


# V8.4.2 Crypto AI Agent R6.1 — 2026-09-27

## Fixed
- Repaired the R6 startup/configuration failure: 'UniversalFuturesBotGUI' no longer references the nonexistent 'v_use_atr_sl' attribute.
- Changed the saved canonical ATR-SL value to 'simple_atr_sl_enabled', while retaining 'use_atr_sl' as a backward-compatible JSON alias.
- Changed the legacy ATR-SL runtime path to use the canonical 'v_simple_atr_sl_enabled' variable.
- Repaired old-profile migration so 'use_atr_sl' can populate the canonical ATR-SL control when needed.
- Repaired ATR-TP migration so 'simple_atr_tp_enabled' is independent of ATR-SL.
- Updated profile-summary diagnostics to use the canonical ATR-SL key.
- Added a GUI/protection configuration-contract audit before settings are saved.

## Added / Modified
- Configuration schema: 17 -> 18.
- Runtime schema: 17 -> 18.
- Internal release marker: 'V8.4.2-CRYPTO-AI-AGENT-R6.1'.
- AI preset marker: 'AI_AGENT_RECOMMENDED_R6.1'.
- Audit marker: 'V8.4.2-AI-AGENT-AUDIT-2026-09-27-R6.1-CONFIG-PROTECTION-HOTFIX'.

## Retained R6 AI risk/protection behavior
- AI risk is dynamically bounded between 0.20% and 0.50% per accepted trade.
- AI ATR stop width is bounded between 1.50 and 2.40 ATR.
- AI TP1 is bounded to 1.00–1.50R and TP2 to 2.00–3.00R, with TP2 forced beyond TP1.
- Position sizing uses the AI-selected stop distance.
- Final protection uses actual filled entry/quantity and exchange-side protection verification.

## Validation
- Python compilation: PASS on the uploaded R6 source after applying the R6.1 patch.
- Static GUI attribute audit: PASS; no executable 'v_use_atr_sl' reference remains.
- AI trade-manager smoke test: PASS.
- Actual-fill protection resolver smoke test: PASS.
- Full live/demo exchange lifecycle: not claimed in this audit.


## V8.1 Engine + Strategy Safety Audit — 2026-09-20

### Fixed

- Validated API credentials before profile-lock acquisition.
- Recovery now requires verifiable saved position identity before adopting a live position.
- Recovery blocks an open position when saved protection state is missing.
- Recovery immediately reconciles normal-position protection.
- Multiple active positions for one symbol are treated as an unsafe multi-position/hedge state.
- Bybit normal entry and normal emergency close explicitly use positionIdx=0.
- Trendline breakout buffer is bounded to less than 100%.
- Generic CCXT trigger creation checks explicit triggerPrice/reduceOnly capability results when available.
- Profile-folder identity is authoritative when config.json contains a stale/mismatched bot_id.

### Modified

- Extracted signal voting into pure _decide_signal() logic without changing the existing signal modes.
- Added configuration schema version 3.

### Added

- 10 automated V8.1 static/regression checks in tests/test_v81_static_audit.py.

### Validation

- Python compile: PASS.
- Static GUI/configuration/callback audit: PASS.
- V8.1 regression checks: 10/10 PASS.
- Full exchange lifecycle remains untested live/demo in this pass.

## V8.2.3
- Fixed a live-checkpoint bug where equivalent symbol forms such as `OP/USDT` and `OP/USDT:USDT` were treated as different symbols.
- Live strategy/risk settings can now be checkpointed without the false `Symbol cannot be changed while the bot is running` warning.
- Real exchange/symbol/account/profile identity changes while running remain blocked.


## 2026-09-22 — Crypto R5-HOTFIX2

### Fixed
- Corrected accidental line-merge corruption in the superseded generic Crypto engine that caused Python SyntaxError around the Volume/SR series builder (_volume_sr_series).
- Repaired the divergence GUI callback definition where the function header and first statement had been merged onto one line.
- Repaired the VWAP Delta settings validation where two statements had been merged onto one line.
- Repaired the liquidity-entry else branch where statements had been merged onto one line.

### Verified
- Full Python source compilation completed successfully after the repairs.
- Strategy/evidence-family architecture, ADAPTIVE_EVIDENCE gating, ATR/ADX regime gates, risk defaults, cooldown, grid settings, callbacks, and configuration schema were preserved rather than weakened.
- Version marker: V8.4.2-CRYPTO-EVIDENCE-HARDENED-R5-HOTFIX2.
- Audit marker: V8.4.2-ENGINE-AUDIT-2026-09-22-R5-HOTFIX2.

### Existing resilience fixes retained
- Bybit transient wallet-balance retry/backoff and recovery handling.
- Managed-order terminal-state handling for Bybit 110001 so already-inactive orders do not repeatedly halt the bot.


## 2026-09-29 — Crypto AI-Agent R6.7 final strategy/risk/protection audit

### Fixed
- Volume/SR live-state inconsistency: the live Volume/SR cache now excludes the newest in-progress candle for chart and HTF data.
- Protection validation now evaluates only enabled SL/TP targets.
- ATR TP validation requires TP2 to be greater than TP1 when both are enabled.
- ATR SL/TP multiplier validation is feature-aware and fail-closed.

### Verified / retained
- AI-Agent configured thresholds and MTF gate diagnostics.
- Evidence-family decision gates and regime filters.
- Equity-risk sizing and fixed-quantity separation.
- One full-position exchange-side SL plus independent TP1/TP2 reduce-only conditional exits.
- TP quantity contract and actual-position quantity reconciliation.
- TP1 break-even replacement with replacement-first safety.
- Protection ACK/verification/reconciliation and rollback.
- GUI callbacks, settings variables, defaults, profile save/load and schema migration.
- Kill-switch, watchdog and fail-closed stop/recovery behavior.

### Validation
AST parse: PASS. Bytecode compile: PASS. Module import: PASS. GUI callback audit: PASS. AI decision/gate smoke tests: PASS. TP split smoke tests: PASS. Completed-candle Volume/SR smoke test: PASS.

### Demo verification still required
Confirm one full-position SL, TP1 and TP2 are visible as active Bybit conditional orders; confirm TP1 closes only its configured quantity and moves the remaining SL to break-even when enabled; confirm TP2 closes the remaining position.
