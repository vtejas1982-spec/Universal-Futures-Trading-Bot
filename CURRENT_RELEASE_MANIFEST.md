# Current Release Manifest — R6.8.28

## Active Crypto AI-Agent release
- Release: V8.4.2-CRYPTO-AI-AGENT-R6.8.28
- Engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28_LINUX_RSS_VPS_MEMORY_HARDENED_FULL_AUDIT.py`
- Config schema: 67
- Signal mode: AI_AGENT
- Target environment: Linux/Oracle VPS (~1 GB RAM)

## R6.8.28
- Added Linux process RSS measurement using /proc/self/status with statm fallback.
- Added low-memory scanner admission guard.
- Added fail-closed memory admission when memory measurement is unavailable.
- Added RAM/swap/RSS diagnostics.
- Retained scanner-child resource disposal and bounded queues.
- No trading strategy or hard safety gate was weakened.

## Validation status
- Python compile: PASS
- AST parse: PASS
- Windows/Bybit DEMO startup + scanner discovery: confirmed.
- Oracle VPS long-run memory validation: pending; planned VPS run is the final memory validation.

## Repository status
The obsolete root crypto engine files were removed. Historical release documentation remains under docs/.
