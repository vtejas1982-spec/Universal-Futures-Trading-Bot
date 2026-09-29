# Crypto AI-Agent R6.8 Release Notes

Date: 2026-09-29
Release: V8.4.2-CRYPTO-AI-AGENT-R6.8

## Fixes

### Risk-sized notional overflow
An extremely tight stop can mathematically produce notional above practical Balance x Leverage capacity. R6.8 adds a conservative 95% utilization cap.

EQUITY_RISK_%: quantity is safely reduced to the cap.
FIXED_QTY: quantity is never silently changed; an oversized request is rejected.

### AI decision observability
Blocked AI-Agent decisions now include each active evidence family's direction and confidence. This improves diagnosis without changing entry rules.

## Retained protection contract
One full-position SL; independent reduce-only TP1/TP2; actual fill/position quantity; TP reconciliation; TP1 break-even replacement; exchange ACK/verification; rollback; completed-candle Volume/SR; feature-aware protection validation.

## Settings/configuration
No new persistent GUI field was required. Config schema 23 and runtime schema 24 remain compatible.

## Strategy behavior
R6.8 does not weaken minimum families, edge, family confidence, trend, structure, conflict, MTF, ATR, Volume or ADX gates.

## Validation
AST parse PASS; py_compile PASS; static audit PASS; dedicated R6.8 tests added. Bare-container import was unavailable because ccxt is not installed. Bybit Demo remains required for exchange behavior.
