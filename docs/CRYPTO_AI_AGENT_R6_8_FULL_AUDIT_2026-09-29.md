# Crypto AI-Agent R6.8 Full Audit

## Scope
Strategy engine, evidence families, AI-Agent council, settings/defaults, callbacks, configuration persistence, sizing, SL/TP resolution, TP quantities, emergency risk, kill-switch, exchange protection and completed-candle consistency.

## Findings

### Risk-sized notional capacity
A very tight resolved stop could mathematically create notional above Balance x Leverage. R6.8 applies a 95% utilization ceiling for equity-risk sizing. Fixed quantity mode fails closed instead of silently changing requested size.

### AI diagnostic visibility
The AI engine already used family confidence internally, but blocked logs did not expose each family's confidence. R6.8 adds FAMILY_DETAIL diagnostics. This is observability only and does not alter entry eligibility.

### Previously fixed and rechecked
Volume/SR completed-candle behavior; disabled protection validation; ATR TP2 ordering; single-owner SL resolution; actual-position TP accounting; Bybit conditional protection; GUI callbacks/configuration; AI MTF/ATR/Volume/ADX gates.

## Validation
AST parse PASS. py_compile PASS. Static contract audit PASS. Dedicated R6.8 tests added.

The local validation container did not have ccxt, so module import could not be executed there. This is an environment dependency issue, not a syntax failure.

## Demo validation
Before Live, verify SL, TP1 and TP2 are active on a small Bybit Demo position; verify TP1 BE replacement and TP2 final close; verify oversized risk sizing logs RISK NOTIONAL CAP.
