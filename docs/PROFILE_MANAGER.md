# Bot Profile Manager

## Purpose

The V8 Connection tab now includes a persistent Bot Profile Manager for running multiple independent configurations without rebuilding the strategy settings manually.

## Profile table

The table shows:

- Profile ID
- Exchange
- Account mode
- Pair
- Timeframe
- Leverage
- Strategy/Grid mode
- Quantity or risk mode
- Grid mode
- Runtime status
- Last update/checkpoint

Select a profile to display its detailed configuration.

## Profile details

The details panel shows market settings, strategy mode and enabled modules, Grid settings, position sizing, SL/TP settings, Telegram status, recovery/session information and all saved configuration keys. API keys, API secrets and Telegram tokens are masked.

## Copying a bot

Use **Copy Selected Profile**.

Example: BOT-01 using NEAR/USDT at 10x can be copied to BOT-02. The copy keeps the source strategy, indicators, risk, Grid, exchange and credential configuration.

The copied profile's old runtime checkpoint is reset. After the copy:

1. Change the Pair.
2. Change Quantity/Risk if required.
3. Change Leverage if required.
4. Review Grid and risk limits for the new pair.
5. Click **Save Profile**.
6. Start the new profile.

## Profile isolation

Each profile has its own bot_profiles/<PROFILE_ID>/config.json and bot_profiles/<PROFILE_ID>/runtime_state.json files. A process lock prevents two live bot processes from using the same Profile ID.

## Safety behavior

A running bot cannot silently change its Profile ID, Exchange, Account Mode or Active Symbol through a live configuration checkpoint. Stop the bot before changing those identity fields.

Loading a nonexistent profile is blocked.

## Configuration-load fix

Profile switching now clears Tk Entry widgets before loading the selected configuration. This prevents repeated loads from concatenating text fields or credentials.

## Important

Copying a profile also copies its saved API credentials because the feature is designed for creating another bot from the same exchange account configuration. Review credentials and account permissions before starting the copied bot.

Always test new profiles with demo/testnet credentials first.


## V8.1 profile safety update

- The profile directory is now the authoritative Profile ID namespace.
- If a saved config.json contains a stale or mismatched bot_id, the loader keeps the selected profile identity and logs the mismatch.
- Saved configurations now include config_schema_version=3.
- Credential validation occurs before profile-lock acquisition.
- Recovery cannot adopt an exchange position unless the checkpoint contains matching position identity and saved protection state.
