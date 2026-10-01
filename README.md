# Universal Futures Trading Bot — R6.8.28

## Current release

**R6.8.28 — Linux RSS + Low-RAM VPS Memory Hardened**

- Engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28_LINUX_RSS_VPS_MEMORY_HARDENED_FULL_AUDIT.py`
- Config schema: **67**
- Signal mode: **AI_AGENT**
- Scanner: two-stage live pair scanner with sequential preflight/active trade children
- Timeframe authority: selected scanner timeframe propagates through discovery and child strategy analysis
- Trading capital authority: configured strategy-capital cap propagates to scanner children and strategy sizing
- Memory target: Linux/Oracle VPS with approximately 1 GB RAM

## R6.8.28 changes

### Low-RAM / VPS hardening
- Added Linux process RSS measurement using `/proc/self/status` with `/proc/self/statm` fallback.
- Added 60-second Hub memory diagnostics for RSS, available RAM and swap usage.
- Added low-memory scanner admission guard so temporary scanner children are not created when the VPS is under memory pressure.
- Memory measurement failure is fail-closed for new scanner-child admission.
- Preserved bounded UI/log queues and scanner candidate structures.
- Preserved explicit scanner-child exchange disposal, Tk callback cancellation, Hub callback purge and garbage collection after cleanup.
- Removed duplicate memory-diagnostic scheduling.

### Trading/scanner safety retained
- No strategy, AI evidence, leverage, SL/TP, cost-gate, liquidation, execution-quality, ownership or protection rule was loosened.
- Scanner still has no direct `create_order()` path.
- Normal order execution remains delegated to the existing safety pipeline.
- Capital allocation and selected timeframe remain runtime-authoritative.

## Validation

- Python compile: PASS
- AST parse: PASS
- Scanner direct order path: 0
- `self.profile_id` stale references: 0
- Config schema: 67
- Runtime validation on Windows/Bybit DEMO: startup and scanner discovery confirmed.
- **Oracle Linux VPS long-run memory validation: pending.** The VPS test is the final validation step for RSS stability and swap behavior.

## Repository cleanup

R6.8.28 is the active crypto engine. The obsolete crypto engine files previously stored at repository root were removed so the repository no longer presents an old crypto engine as current.

Historical release notes remain under `docs/` for traceability.

> Engineering/safety hardening only. Continue Bybit Demo/Testnet validation before Live deployment.
