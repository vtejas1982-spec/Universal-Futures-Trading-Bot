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
