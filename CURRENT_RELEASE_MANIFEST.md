# Current Release Manifest — V7.1

## Active Crypto AI-Agent release
- Release: **V7.1**
- Engine: `UniversalFuturesBot_V7.1_SCANNER_EPHEMERAL_TRADE_HISTORY.py`
- Build: `V7.1-AI-AGENT-SCANNER-EPHEMERAL-LIFECYCLE-PROFILE-TRADE-HISTORY-ORDER-ID-AUDIT-FULL-AUDIT`
- Config schema: **68**
- Runtime schema: **25**
- Signal mode: **AI_AGENT**
- Local source SHA-256: `ffc25d3138d9515361efd66dba59b2064e80f168aaaa830828ae41ef17d123f6`

## V7.1 release scope
- Scanner `PREFLIGHT_WORKER` directories are safely purged after terminal rejection/failure when no active/recovery state exists.
- Startup reconciliation handles abandoned scanner preflight directories.
- Hub `TRADE HISTORY` shows completed trades only and supports parent-BOT filtering.
- Trade History records entry/SL/TP1/TP2/BE/final exit order IDs and TP1/TP2 fills.
- Actual protection IDs are synchronized after exchange verification.
- Original SL and BE order IDs remain separate.

## Safety retained
- AI/evidence gates unchanged.
- Saved profile remains authoritative.
- TP1/TP2/true-BE contract retained.
- Windows resource governor and async preflight retained.
- Linux 180/240/780 MB memory contract retained.
- Global capital authority retained.

## Validation status
- AST parse: PASS
- Python compile: PASS
- Compileall: PASS
- Embedded V7.1 and R6.x safety audits: PASS
- SQLite history smoke test: PASS
- Target Windows runtime validation: **PENDING**

## Source synchronization status
The repository metadata and manuals are synchronized to V7.1. The complete ~1.29 MB production Python source remains pending normal large-file-safe Git synchronization; a truncated source blob is intentionally not committed as the production engine.