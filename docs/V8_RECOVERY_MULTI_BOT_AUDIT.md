# V8 Recovery + Multi-Bot Audit

## Scope

This audit covers the uploaded 9,738-line V8 recovery/multi-bot source and the changes published with this build.

## Checked

- Strategy-engine structure
- 17 directional modules
- GUI settings variables
- Configuration save/load paths
- Start/stop callbacks
- Runtime persistence
- Recovery prompt
- Recovery configuration restore
- Normal-position state
- Grid state serialization
- Protection reconciliation
- Profile isolation
- Profile locking
- SQLite master database
- Master CSV export
- Existing Grid order synchronization safeguards

## Fix identified during audit

The previous protection reconciliation implementation contained an undefined `open_ids` reference in a branch that could be reached during reconciliation. The recovery build removes that undefined-variable dependency and uses the specific order-verification path.

## Recovery design

A profile runtime checkpoint stores:

- session ID
- exchange
- account mode
- symbol
- timeframe
- strategy mode
- enabled strategy-module summary
- configuration hash
- session statistics
- daily drawdown reference
- normal active-trade/protection state
- TP1/BE state
- re-entry lock state
- Grid center
- Grid entry order IDs
- Grid filled levels
- Grid TP/SL IDs
- Grid state
- configuration snapshot without API/Telegram secrets

On startup, the bot asks before attempting recovery. Resume restores state and then verifies exchange-side inventory/orders. Start New creates a new session and does not silently adopt an existing position/order.

## Multi-bot design

Each Bot Profile ID has isolated:

- configuration
- runtime checkpoint
- process/profile lock

All profiles share a master SQLite ledger and Excel-compatible CSV export.

## Testing

Static validation completed:

- Python syntax compilation
- configuration coverage review
- callback review
- persistence serialization checks
- profile-path checks
- profile-lock checks
- SQLite ledger checks
- CSV export checks
- recovery-state checks

## Not live-tested

No full live/demo order lifecycle was executed against every supported exchange during this audit. Users should test recovery with demo/testnet credentials and a single profile before using live funds.

## PnL limitation

Normal-trade PnL follows the existing account-balance-delta accounting model. Multiple bots sharing one account can therefore influence the observed balance delta. Exact per-fill exchange PnL remains a future enhancement.

## Runtime files

The bot creates local runtime data that is intentionally excluded from Git:

```text
bot_profiles/
universal_bot_master.db
universal_bot_master_log.csv
```


## Profile Manager audit update — 2026-09-20

### Added

- Saved profile table with Pair, Timeframe, Leverage, Mode, Qty/Risk, Grid, Status and Last Update.
- Full selected-profile detail view with API/Telegram secrets masked.
- Copy Profile workflow that duplicates strategy/risk/Grid/exchange configuration and resets the target runtime checkpoint.
- Safe profile switching and profile refresh after save/copy.

### Configuration bugs fixed

1. Repeated profile loads previously inserted new text into existing Tk Entry widgets without clearing them. The loader now clears all `e_*` Entry widgets before inserting the selected profile.
2. Loading an unknown Profile ID could leave the previous profile settings on screen. The loader now blocks nonexistent profiles.
3. A running bot could save a changed Profile ID, exchange, account mode or symbol while the execution worker still owned the old runtime identity. Live checkpoints now reject those identity changes.
4. Profile locking previously occurred before API credential validation. A missing-credential early return could therefore leave a lock. Lock acquisition now occurs after credential validation.

### Configuration coverage audit

- 115 GUI setting attributes are assigned before use.
- 117 settings are written by `save_settings()`.
- Grid fields are loaded through the shared dynamic Grid-setting loop.
- `nwe_repaint` is intentionally forced to `False` because the current NWE engine is non-repainting.
- `e_bot_id` is the Entry presentation for `v_bot_id` and is not a second configuration key.

### Strategy audit

The current build retains the 17-module completed-candle strategy engine and the shared Grid SCORE directional-module path. No strategy module was removed by the Profile Manager work.

### Validation

Python syntax compilation and static GUI/configuration/callback review passed. No full live exchange lifecycle was performed during this audit.
