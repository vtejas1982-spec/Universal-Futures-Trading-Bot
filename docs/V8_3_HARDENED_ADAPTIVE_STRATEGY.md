# V8.3.3 Adaptive Strategy Specification

V8.3.3 retains the V8.3 Adaptive strategy contract and hardens the execution/configuration boundary.

## Adaptive execution contract

- 19 strategy modules remain available.
- Adaptive Edge and Adaptive Minimum Weight are explicit per-call/per-profile inputs.
- No mutable StrategyEngine Adaptive class state is allowed.
- Completed candles remain the execution basis.
- Existing divergence confirmation and higher-timeframe S/R close alignment remain unchanged.

## Safety and recovery additions

- Exact bot-created protection/Grid order IDs are retained after a position becomes flat.
- A NEW session may automatically clean only IDs proven by the previous checkpoint to belong to this bot.
- Unknown/manual orders block startup.
- A strict Bybit open-order snapshot that reaches the 50-order page limit is treated as potentially incomplete.
- Requested new-profile defaults are centralized and persisted through normal profile save/load.

## Adaptive defaults

| Setting | Default |
|---|---:|
| Signal Mode | ADAPTIVE_SCORE |
| Adaptive Edge | 0.18 |
| Adaptive Min Weight | 3.5 |
| 4H MTF | ON |
| ADX | ON |
| Volume | ON |
| ATR | OFF |
| Grid | OFF |
| Risk Mode | EQUITY_RISK_% |
| Risk Per Trade | 1.0% |
| Post-SL Opposite Lock | ON |
| No Same Candle | ON |

Existing saved profile configuration remains authoritative.

## Important

These are engineering defaults and safety contracts, not a profitability guarantee.


## Backtester parity

V8.3.3 keeps the historical backtester aligned with the live strategy contract. The backtester mirrors the live StrategyEngine Adaptive decision/diagnostic methods, explicit per-profile Adaptive Edge / Minimum Weight parameters, causal Volume S/R handling, and the V8.3.3 completed-candle execution model.

Runtime-only exchange protections such as managed-order checkpoint ownership, strict open-order pagination safety and startup inventory preflight are intentionally not simulated as historical price signals.

Regression coverage: tests/test_v833_backtester_parity.py — 8/8 PASS.
