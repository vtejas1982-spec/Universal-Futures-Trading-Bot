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



## V8 Recovery + Multi-Bot Build — 2026-09-20

### Added

- Crash/restart recovery with an explicit **Resume last saved stage / Start New Bot** prompt.
- Per-profile runtime checkpoints.
- Per-profile configuration and runtime-state directories.
- Bot Profile ID support for running multiple independent bot instances.
- Profile lock to prevent duplicate instances of the same bot profile.
- Exchange-side reconciliation before resuming a saved session.
- Recovery of normal-trade state, protection state, re-entry state and Grid state.
- Shared SQLite master database: `universal_bot_master.db`.
- Excel-compatible master CSV: `universal_bot_master_log.csv`.
- Configuration hash/session metadata in the master ledger.
- Recovery audit documentation.
- Contributor and issue infrastructure retained and expanded.

### Fixed

- Protection reconciliation branch that referenced an undefined `open_ids` variable.
- Recovery no longer assumes that local state alone proves an exchange position/order belongs to the bot.
- Protection verification now treats uncertain exchange states conservatively.

### Preserved

- 17 directional strategy modules.
- Completed-candle/no-lookahead evaluation.
- DIRECT_SHOT / SCORE.
- LONG_GRID / SHORT_GRID / NEUTRAL_GRID.
- NEUTRAL_GRID automatic direction handling.
- Grid TP/SL and exposure/drawdown controls.
- Existing Grid duplicate-order synchronization fix.
- Telegram/dashboard/CSV logging.
- Existing exchange support: Bybit, Binance, Gate.io, Bitget and WEEX.

### Important limitations

- The release has not been fully live-tested against every supported exchange.
- Exchange-specific account mode, order mode, permissions and recovery behavior still require demo/testnet validation.
- Normal-trade PnL remains based on the existing account-balance-delta accounting model. When multiple bots share one exchange account, deposits, withdrawals, fees or another bot's activity can affect that balance delta.
- The master ledger should therefore be treated as an operational/session ledger rather than an exchange-certified per-fill realized-PnL statement.

## V8 Profile Manager + Configuration Audit — 2026-09-20

### Added

- Saved Bot Profile Manager in the Connection tab.
- Profile table showing pair, timeframe, leverage, mode, quantity/risk, Grid state, runtime status and last update.
- Full selected-profile details viewer with secrets masked.
- Copy Selected Profile workflow for cloning a complete configuration to another Bot Profile ID.
- Copied profiles start with a reset runtime checkpoint so the new bot does not inherit the source bot recovery session.

### Fixed

- Repeated profile loads no longer concatenate values in Tk Entry widgets.
- Loading a nonexistent profile is now blocked instead of leaving the previous profile settings active.
- A running bot cannot silently change Profile ID, exchange, account mode or active symbol through configuration checkpoints.
- Profile locking now occurs after API credential validation, avoiding a lock leak on missing-credential startup failure.

### Audited

- 115 GUI setting attributes reviewed; all are assigned before use.
- Current GUI callbacks resolve to existing methods.
- 117 saved configuration keys reviewed, including dynamically loaded Grid settings.
- Strategy, Grid, recovery, protection and persistence paths rechecked.

### Limitation

- Python syntax/static checks passed; full exchange lifecycle testing remains a separate demo/testnet task.
