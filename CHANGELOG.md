# Changelog

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
