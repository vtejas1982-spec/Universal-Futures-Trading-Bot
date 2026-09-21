# Universal Forex Bot V8.3.4 — MT5 Forex Hardened

## Purpose

V8.3.4 is a reliability/safety hardening release built on the V8.3.3 MT5 Forex bot. It does not claim or target guaranteed profitability. The focus is reducing execution, recovery, protection, and operational failure modes.

## Major hardening changes

- **Broker-side SL reconciliation:** live MT5 positions are checked periodically for the expected hard stop. A missing/mismatched SL is repaired; if repair cannot be verified, the position is closed fail-closed.
- **Order-send idempotency:** when `mt5.order_send()` returns `None` for an entry, the bot reconciles bot-owned positions before treating the request as failed. This avoids blind duplicate-entry retries.
- **Broker stop/freeze validation:** SL modification checks MT5 stop/freeze distance before submission.
- **Peak-equity drawdown:** max drawdown is measured from the session peak equity rather than only from starting balance.
- **Equity-based sizing:** risk-per-trade sizing uses current equity at the entry decision.
- **Emergency-stop scope:** defaults to `BOT_ONLY`; `ALL_ACCOUNT` is an explicit option for users who intentionally want account-wide flattening.
- **News filter fail-closed:** when the news safety filter is enabled but its calendar source is unavailable, new entries are blocked instead of silently allowed.
- **Runtime checkpoint:** active position/protection state is periodically persisted and restored when a matching symbol/magic position exists after restart.
- **Single-instance profile lock:** prevents two copies of the same bot profile from trading simultaneously.
- **Stale-market-data guard:** stale MT5 candle data blocks the strategy cycle.
- **Thread coordination:** watchdog protection management uses the runtime lock to reduce concurrent state mutations.
- **Final Forex-only override ordering fixed:** the executable `__main__` block is now after the final MT5/Forex bindings.

## Backtester parity

The matching V8.3.4 backtester was updated to model the new risk controls:

- peak-equity max drawdown stop
- emergency capital stop
- consecutive-loss stop
- equity-based risk sizing
- same completed-candle strategy contract

It remains a historical OHLC approximation and is not an exact MT5 execution simulator.

## Validation

`test_forex_v834_hardened.py`: **7/7 PASS**

Synthetic engineering backtest completed successfully. Synthetic results are not evidence of live profitability or future performance.
