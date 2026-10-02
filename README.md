# Universal Trading Bot — Forex MT5 V7.1.3

## Current production release

**Universal Forex Trading Bot V7.1.3 — MT5 / Forex**

- Canonical engine: `UniversalForexBot_MT5.py`
- Audited release artifact: `UniversalForexBot_MT5_V7_1_3_AUDITED.py`
- Low-memory reference: `UniversalForexBot_MT5_V7.1.2_LOW_MEMORY.py`
- Config schema: **71**
- Runtime schema: **71**
- Signal mode default: **AI_AGENT**
- MT5-native execution, sizing, protection and position reconciliation
- V7.1 evidence-family AI council and guarded 2-family fallback
- Scanner/preflight lifecycle controls
- Global capital authority and expiring reservations
- SQLite trade history and profile system
- Windows RAM/RSS resource governor
- Persistent kill-switch latch

## V7.1.3 audit fixes

- Fixed undefined ADX runtime state used by Hold-All-Reverse paths.
- Fixed 2-family AI fallback so an opposing qualified family blocks fallback.
- Added explicit council split handling when both BUY and SELL qualify.
- Added `AMBIGUOUS_CANDLE` fail-closed handling.
- Corrected MT5 volume-step rounding/minimum-lot handling.
- Added safe minimum-lot TP1 whole-position behavior.
- Added broker-side break-even verification with one retry and fail-safe retention of the original SL.
- Added startup risk/protection ordering checks.
- Unified emergency-stop default to 10%.
- Preserved lazy-profile/resource-governor memory controls.

## Validation

See `docs/FOREX_V7_1_3_FULL_REPO_AUDIT_2026-10-02.md`.

- AST parse: PASS
- Python compile: PASS
- Randomized AI council contract: PASS
- 2F opposing-family regression: PASS
- Ambiguous-candle contract: PASS
- MT5 lot/protection contract: PASS
- Live MetaTrader 5 terminal validation: **PENDING**

## Important MT5 behavior

The Forex engine keeps the broker-side SL as the hard protection. TP1/TP2 are bot-managed because the MT5 position model does not provide the same two independent exchange-trigger orders used by the Crypto engine. If the bot process is stopped, broker-side SL remains available but bot-managed TP logic cannot run.

## Historical material

Older Crypto/V8 release notes and audit documents remain in `docs/` as historical engineering records. They are not the current Forex production source.

Engineering/safety hardening only. Validate on an MT5 Demo account with the target broker before Live deployment.
