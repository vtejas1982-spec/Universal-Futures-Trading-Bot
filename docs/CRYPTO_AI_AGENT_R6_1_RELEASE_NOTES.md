# Crypto AI Agent R6.1 Release Notes

Date: 2026-09-27

## Purpose

R6 introduced deterministic AI-Agent risk, SL and TP management. A live startup test then exposed a configuration-variable mismatch: the GUI created 'v_simple_atr_sl_enabled', while save/load and legacy-protection code still referenced the obsolete 'v_use_atr_sl'.

R6.1 is a focused configuration/protection hardening release. It keeps the R6 trading logic and fixes the configuration contract around it.

## 1. Fixed

### 1.1 Startup failure

Observed error:

'AttributeError: UniversalFuturesBotGUI object has no attribute v_use_atr_sl'

The failing save path attempted to read 'self.v_use_atr_sl.get()'.

Root cause: the unified protection GUI uses 'self.v_simple_atr_sl_enabled', but older save/load and legacy-protection paths still expected 'self.v_use_atr_sl'.

### 1.2 Save configuration

The canonical saved field is 'simple_atr_sl_enabled'.

The older JSON field 'use_atr_sl' is still written as a compatibility alias, using the same canonical GUI value. This prevents existing profile files from becoming incompatible.

### 1.3 Load configuration

R6.1 loads:
1. 'simple_atr_sl_enabled' when present.
2. Otherwise 'use_atr_sl' from older profiles.
3. Otherwise the current default.

No 'v_use_atr_sl' Tk variable is created or required.

### 1.4 ATR-TP migration

The previous fallback incorrectly used the ATR-SL setting as the fallback source for ATR-TP. R6.1 keeps 'simple_atr_tp_enabled' independent and uses its own default when the field is absent.

### 1.5 Legacy ATR-SL path

When the explicitly selected legacy protection engine needs the ATR-SL switch, it now reads the canonical 'v_simple_atr_sl_enabled' instead of the obsolete variable.

### 1.6 Profile diagnostics

Profile summaries now read the canonical ATR-SL key first and fall back to the old JSON alias.

### 1.7 Configuration contract audit

Before 'save_settings()' builds the configuration dictionary, R6.1 verifies the required SL/TP GUI attributes exist. If a future refactor removes one, the bot reports a clear configuration-contract error instead of failing later with a raw Tkinter AttributeError.

## 2. R6 AI-Agent risk/protection retained

R6.1 does not remove the R6 AI manager.

For accepted AI-Agent trades, the deterministic manager can adapt:
- Risk: 0.20%–0.50% hard envelope.
- ATR SL: 1.50–2.40 ATR hard envelope.
- TP1: 1.00–1.50R.
- TP2: 2.00–3.00R.
- TP2 is forced beyond TP1.
- Wider stops reduce entry quantity when equity-risk sizing is active.
- Final protection is resolved from the actual filled entry and actual position quantity.

The AI manager is deterministic rule logic based on completed-candle evidence. It is not an external LLM and does not guarantee profitability.

## 3. Configuration/schema

- Config schema: 17 -> 18.
- Runtime schema: 17 -> 18.
- Internal version: 'V8.4.2-CRYPTO-AI-AGENT-R6.1'.
- AI preset: 'AI_AGENT_RECOMMENDED_R6.1'.

Existing credentials, exchange, account mode, symbol and profile identity are not changed by the AI preset.

## 4. Validation performed

- Python compilation of the uploaded R6 source after the R6.1 patch: PASS.
- Static GUI-attribute audit: PASS.
- No executable reference to 'v_use_atr_sl' remains.
- AI trade-manager smoke test: PASS.
- Actual-fill protection resolver smoke test: PASS.
- Preset mapping audit: all 134 preset keys map to GUI entry/variable controls.
- Save/load audit: all directly saved configuration keys have corresponding load paths; grouped dynamic fields were also reviewed.
- Full exchange lifecycle was not claimed in this audit. Continue testing on Bybit Demo/Testnet before any live deployment.

## 5. Recommended test sequence

1. Start the R6.1 file.
2. Select profile BOT-01.
3. Select 'AI_AGENT'.
4. Click YES on the recommended-settings confirmation.
5. Confirm:
   - Timeframe = 15m
   - Leverage = 5x
   - Max Open Trades = 1
   - Risk-Based Sizing = ON
   - Risk Per Trade = 0.35%
   - ATR SL = ON
   - ATR SL multiplier baseline = 1.8x
   - TP1/TP2 = ON
6. Save Config.
7. Start on Bybit Demo/Testnet.
8. For an accepted trade, verify the execution log contains:
   - 'AI TRADE MANAGER:'
   - 'AI EFFECTIVE RISK:'
   - 'PROTECTION CALCULATED FROM ACTUAL ENTRY:'
   - 'PROTECTION RESOLVED:'
   - 'TP RESOLVED:'
9. Verify the exchange shows the expected bot-owned protection orders.
10. Do not move to live until entry, fill, SL, TP, partial TP, reversal, reconnect and stop/kill-switch behavior have all been observed in demo/testnet.

## 6. Stable filename policy

The repository keeps the stable production filename:

'UniversalFuturesBot_CRYPTO_AI_AGENT_R4.py'

The internal APP_VERSION identifies the R6.1 release. Historical releases remain in Git history rather than creating additional root-level copies.
