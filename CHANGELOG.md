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
