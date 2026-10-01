# Current Release Manifest — R6.8.32

## Active Crypto AI-Agent release
- Release: V8.4.2-CRYPTO-AI-AGENT-R6.8.32
- Engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.32_ORACLE_VPS_MEMORY_FAILCLOSED_HYSTERESIS_FULL_AUDIT.py`
- Config schema: 67
- Signal mode: AI_AGENT
- Target environment: Linux/Oracle VPS (~1 GB RAM)

## R6.8.32
- Hardened Linux/Oracle VPS scanner-child memory admission.
- Linux memory telemetry reads `/proc/meminfo`; process RSS reads `/proc/self/status` with `statm` fallback.
- Linux admission is fail-closed if required memory telemetry is unavailable.
- Added real low-memory hysteresis: admission blocks below 180 MB available RAM and, after a low-memory latch, does not resume until available RAM reaches 240 MB.
- Retained Linux process-RSS ceiling at 780 MB.
- Windows keeps available-RAM admission; RSS remains diagnostic-only.
- Scanner preflight remains sequential and temporary; rejected/flat children are disposed before the next candidate.
- No strategy, risk, cost, liquidation, execution-quality, protection, ownership, or kill-switch gate was loosened.

## Validation status
- Python AST parse: PASS.
- Python compile / py_compile: PASS.
- Static memory-helper/class-ownership audit: PASS.
- Linux fail-closed/hysteresis source audit: PASS.
- Scanner dispatch/preflight call-chain audit: PASS.
- Oracle VPS live smoke test: PASS for memory telemetry, child admission, preflight startup, and cleanup.
- Oracle long-run memory validation: PENDING; a 30–60 minute run is still required to establish sustained memory behavior.
- Local production source SHA-256: `a843dcdec83ac271b361eaec16dddda37d5ca0852ad285fa30f311c8a7ea51d9`.

## Repository source synchronization
The complete R6.8.32 production Python source was validated locally. The connected GitHub file-write endpoint cannot safely serialize the ~1.17 MB production source replacement in this session, so this repository update synchronizes the release manifest, changelog, and audit report without falsely claiming that the large source blob was replaced. The local source remains the authoritative R6.8.32 artifact until the source file is committed through a normal Git client or equivalent large-file-safe path.
