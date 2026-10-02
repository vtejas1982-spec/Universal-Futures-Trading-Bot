# Universal Futures Trading Bot — V7.1

## Current release

**V7.1 — Scanner Ephemeral Lifecycle + Profile Trade History + Order-ID Telemetry**

- Engine: `UniversalFuturesBot_V7.1_SCANNER_EPHEMERAL_TRADE_HISTORY.py`
- Config schema: **68**
- Runtime schema: **25**
- Signal mode: **AI_AGENT**
- Multi-Bot Hub with asynchronous Windows scanner preflight
- Global capital authority (`OFF/ACCOUNT`, `GLOBAL_SHARED`, `INDIVIDUAL`)
- Hardened TP1/TP2/true-BE protection contract
- Scanner temporary-profile cleanup and startup reconciliation
- Completed Trade History tab with exchange order IDs and TP1/TP2 fill details

## V7.1 fixed / added / modified

### Fixed
- Prevented rejected scanner preflight profiles from accumulating indefinitely.
- Added safe startup reconciliation for abandoned `PREFLIGHT_WORKER` directories.
- Repaired trade-history protection telemetry so actual SL/TP1/TP2 order IDs are persisted after protection verification.
- Preserved the original SL order ID separately from the BE order ID.

### Added
- Hub `TRADE HISTORY` tab showing completed trades only.
- BOT profile filter and `ALL PROFILES` view.
- Full scanner engine ID alongside parent BOT attribution.
- Entry, SL, TP1, TP2, BE and final exit order IDs.
- TP1/TP2 fill quantity, price and time.
- `COPY SELECTED` trade-history action.
- Ephemeral scanner purge/deferred-purge diagnostics.

### Modified
- Master SQLite trade schema is upgraded additively; existing history is preserved.
- TP2 recreation updates the trade-history TP2 order ID.
- No AI, strategy, leverage, risk, cost, liquidation, execution-quality or protection gate was loosened.

## Validation

- AST parse: PASS
- Python compile: PASS
- Compileall: PASS
- MultiBotHub: 77 methods, 0 duplicates
- UniversalFuturesBotGUI: 250 methods, 0 duplicates
- Embedded V7.1 + prior safety audits: PASS
- SQLite trade-history smoke test: PASS

## Source synchronization
The validated V7.1 production source is approximately 1.29 MB. The connected GitHub file-write path cannot safely serialize that complete source blob in this session without truncation, so the repository does **not** falsely claim that the large production source has been replaced.

The authoritative local source SHA-256 is:
`ffc25d3138d9515361efd66dba59b2064e80f168aaaa830828ae41ef17d123f6`

See `docs/V7.1_SOURCE_SYNC.md` for synchronization instructions.

## User guide
- `docs/USER_MANUAL_V8_4_2_V7_1_CRYPTO.md`
- `docs/V7.1_RELEASE_NOTES.md`
- `docs/V7.1_FULL_AUDIT_REPORT.md`

> Engineering/safety hardening only. Continue Bybit Demo/Testnet validation before Live deployment.