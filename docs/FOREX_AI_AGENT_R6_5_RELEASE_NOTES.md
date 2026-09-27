# Forex MT5 AI-Agent R6.5 — Release Notes — 2026-09-28

The current Forex production engine is **UniversalForexBot_MT5.py** and the matching historical simulator is **UniversalForexBot_MT5_BACKTESTER.py**.

### Strategy
The five StrategyEngine contract methods are kept in parity with Crypto AI-Agent R6.5:
- family mapping
- evidence-family summary
- AI-Agent council
- centralized signal decision
- decision diagnostics

### AI-Agent preset
- 15m
- 5x reference leverage
- maximum 1 open position
- 15 minute cooldown
- no same-candle re-entry
- 3 evidence families
- 0.20 minimum edge
- 0.55 family confidence
- Trend required
- Structure required
- maximum 1 conflict

### AI risk/protection
- risk 0.20%–0.50%
- SL 1.50–2.40 ATR
- TP1 1.00–1.50R
- TP2 2.00–3.00R
- TP1 partial exit and break-even handling

### Forex-specific
MT5 execution, account modes, symbol resolution and lot/risk conversion remain Forex-native. The AI manager changes the risk/protection decision but not the broker API model. Grid is intentionally OFF-only.

### Backtester
The backtester imports the live Forex engine and calls its StrategyEngine and AI management methods rather than maintaining a separate strategy algorithm. It supports CSV or MT5 history and outputs trade/equity/summary files.

Backtest results are research simulations and are not guarantees of live profitability or execution equivalence.
