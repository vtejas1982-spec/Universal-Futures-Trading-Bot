# Current Release Manifest — R6.8.7.14 HOTFIX4

## Active Crypto AI-Agent release
- Release: **V8.4.2-CRYPTO-AI-AGENT-R6.8.7.14**
- Live engine: `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.14.py`
- Config schema: **35**
- Runtime schema: **24**
- Signal mode: **AI_AGENT**
- Audit build: `V8.4.2-AI-AGENT-AUDIT-2026-09-30-R6.8.7.14-AI-LEVERAGE-ADAPTIVE-FULL-AUDIT-HOTFIX4-LIQ-BOUNDARY`

## R6.8.7.14 HOTFIX4 changes
- Automatic session-only leverage recovery for qualified entries blocked solely by the minimum 1.50 ATR liquidation-safety requirement.
- Recovery chooses the highest safe integer leverage and can only lower leverage.
- GUI/saved leverage remains unchanged.
- Strict post-check prevents floating-point boundary violations.
- All downstream liquidation, cost, fixed-quantity risk, execution-quality and protection gates remain mandatory.

## Demo validation
- Bybit Demo SOON/USDT.
- Configured leverage: 25x.
- Recovered session leverage: 7x.
- AI stop: 1.626 ATR after safety adjustment.
- Actual fill: LONG 0.4536, Qty 1400.
- Protection verified: SL 0.4322, TP1 0.4795, TP2 0.5055.
- Position protection verification: PASS.

## Repository policy
This main branch keeps one active Crypto AI-Agent root engine: **R6.8.7.14**. Superseded R6.8.7.12 root source/build/backtester/test artifacts are removed from the active tree and remain recoverable through Git history.
