# Crypto AI-Agent R6.7 — Full Contract Audit

**Release:** V8.4.2-CRYPTO-AI-AGENT-R6.7  
**Audit date:** 2026-09-29  
**Config schema:** 23  
**Runtime schema:** 24  
**Audit marker:** V8.4.2-AI-AGENT-AUDIT-2026-09-29-R6.7-PROTECTION-ENGINE-AUDIT-FULL-CONTRACT-AUDIT

## Audit objective

Review the complete R6.7 Crypto engine after the Bybit Demo observation that the GUI showed TP1/TP2 enabled while the exchange displayed only the SL conditional order.

The review covers the complete path from configuration -> strategy evidence -> AI-Agent decision -> sizing -> actual fill -> SL/TP calculation -> exchange order creation -> verification -> reconciliation -> exit handling -> persistence/recovery.

## Fixed

### AI-Agent decision diagnostics
- Blocked decisions now identify the dominant side.
- Directional MTF failures are explicitly logged as MTF_GATE_BUY, MTF_GATE_SELL or MTF_GATE_TIE.
- Startup AI-Agent threshold logging now displays the actual configured values.
- Generic Minimum Score is explicitly described as validation-only when AI_AGENT is selected.

### Protection engine
- SL uses the actual filled entry and actual live position quantity.
- TP1 and TP2 are independent reduce-only conditional exits.
- Default split is 50% / 50%.
- TP2 is calculated from the remaining quantity after TP1 precision rounding in percentage mode.
- A single enabled TP closes the full remaining position.
- Protection creation is ordered SL -> TP1 -> TP2.
- Known protection orders are rolled back when the protection set cannot be completed.
- Exchange acknowledgements are logged without credentials.
- Bybit conditional StopOrder state is checked during verification.
- Missing protection is reconciled while the position remains open.
- TP1 break-even replacement verifies the new SL before retiring the old SL.

### Preflight validation
- TP quantity mode is validated.
- Two-TP percentage splits must be positive, below 100% individually and total exactly 100%.
- Fixed TP quantities must be positive.
- ATR TP2 multiplier must be greater than ATR TP1 when both targets are enabled.
- Existing AI-Agent, risk, SL and strategy validation remains fail-closed.

## Added

- Full-contract audit marker.
- Expanded R6.7 regression tests for AI diagnostics and TP validation.
- Detailed release/audit documentation.
- Explicit runtime protection contract metadata.
- More precise protection failure/recovery observability.

## Modified

### Strategy / AI
- AI-Agent continues to require its configured family, edge, confidence, conflict, Trend and Structure gates.
- ATR, Volume, ADX and directional MTF gates are propagated into AI trade-management instead of being assumed true.
- Completed-candle execution semantics remain intact.
- Evidence Families remain separated so ATR/ADX act as regime gates rather than fake directional votes.

### Configuration
- Existing saved profiles remain authoritative.
- New R6.7 fields use release defaults during migration.
- GUI runtime snapshots remain the worker's thread-safe configuration source.
- TP split and ATR protection settings are persisted.
- Compatibility fields such as NWE repaint remain persisted but the live calculation stays causal/non-repainting.

### Lifecycle / safety
- Single-symbol / one-way position contract remains explicit: Max Open Trades must be 1.
- New sessions do not silently adopt unknown existing positions or orders.
- Kill-switch and stop cleanup remain fail-closed.
- Protection verification errors pause new entries instead of guessing.

## GUI / callback audit

Checked:
- Strategy setting variables
- Risk/protection variables
- AI-Agent variables
- Grid variables
- Profile controls
- Save/load callbacks
- Exchange/account callbacks
- Signal-mode callbacks
- Risk-mode callbacks
- Runtime snapshot references

No missing direct GUI callback method was found in the audited R6.7 source.

## Configuration audit

Checked:
- Save mappings
- Load mappings
- Migration defaults
- AI-Agent preset fields
- TP1/TP2 settings
- ATR SL/TP settings
- Risk sizing compatibility
- Profile identity protection
- Runtime checkpoint metadata

## Known design constraints

1. The engine intentionally manages one symbol and one net position per profile.
2. Bybit protection currently uses positionIdx=0 because the engine's contract is one-way/single-position mode.
3. Hold-All-Reverse / Hold-SL WAIT is an explicit alternative management mode and can intentionally suppress exchange-side TP/SL behavior according to its configured contract.
4. R6.7 is an engineering hardening release, not a profitability guarantee.

## Validation

- AST parse: PASS
- Python bytecode compilation: PASS
- Module import: PASS
- GUI callback audit: PASS
- GUI runtime-variable audit: PASS
- Configuration save/load contract audit: PASS
- TP 50/50 quantity smoke test: PASS
- Invalid TP split rejection: PASS
- AI MTF gate smoke test: PASS
- Protection contract static checks: PASS

## Demo validation still required

Before Live, open a small Bybit Demo/Testnet position and verify:
- one SL conditional order for the full live position;
- TP1 for the first configured split;
- TP2 for the second configured split;
- ACK and VERIFIED ACTIVE log entries for every required order;
- TP1 actually reduces the position by the configured amount;
- break-even SL replaces the original SL after TP1 when enabled;
- TP2 closes the remaining position.

