# Crypto AI Agent R6.3 Release Notes

Date: 2026-09-27

## Problem

A BOT-01 profile saved with configuration schema 18 repeatedly produced the CONFIG MIGRATION schema 18 -> 19 message. The message was informational, not a trading error. The root cause was that the loader detected an old schema but did not persist the upgraded schema number after a successful load.

## Fixed

### 1. Migration persistence

After the entire GUI configuration is loaded successfully, R6.3 now writes config_schema_version = 20 back to the same profile configuration. The next load therefore sees the current schema and does not announce the same migration again.

### 2. Existing values remain authoritative

Migration does not reset the user's saved strategy, risk, protection, symbol, exchange, or account values. Missing fields continue to use current release defaults during GUI loading.

### 3. ATR-SL backward compatibility

When a migrated profile contains only the legacy use_atr_sl field, R6.3 populates the canonical simple_atr_sl_enabled value from it. When the canonical field exists, the legacy alias is synchronized to the canonical value.

### 4. Cleaner logging

The historical R3 sizing message is replaced by one concise compatibility message.

## Versioning

Internal source: V8.4.2-CRYPTO-AI-AGENT-R6.3
Config schema: 20
Runtime schema: 20
Audit marker: V8.4.2-AI-AGENT-AUDIT-2026-09-27-R6.3-MIGRATION-PERSISTENCE-HOTFIX

## Validation

- Local Python compilation: PASS.
- Static migration-persistence audit: PASS.
- Existing-value preservation: retained.
- Full live exchange lifecycle: not claimed by this patch.

## Expected behavior

On the first load of an older profile, one migration notice may appear, followed by CONFIG MIGRATION COMPLETE showing the upgrade persisted to config.json. Subsequent loads should show only Configuration loaded unless a newer schema is introduced.

## Test

1. Start the R6.3 source.
2. Load BOT-01.
3. If the profile is still schema 18, expect one migration-complete message.
4. Load BOT-01 again or restart the application.
5. The repeated schema-18 migration notice should no longer appear.
6. Confirm saved trading settings remain unchanged.

## Stable filename

The repository continues to use UniversalFuturesBot_CRYPTO_AI_AGENT_R4.py. The release is identified by APP_VERSION.
