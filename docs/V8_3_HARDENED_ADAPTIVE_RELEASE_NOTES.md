# V8.3.0 — Hardened Adaptive Trading Engine

## Purpose
V8.3.0 is a hardening release built from the V8.2.6 Advanced Strategy Bot. The goal is not to promise maximum profit; it is to improve the quality of entries, reduce correlated-indicator double counting, and make failure/recovery behavior more fail-closed.

## Added

### 1. ADAPTIVE_SCORE strategy mode
- Correlation-aware weighted voting across the 19 directional modules.
- Trend/structure modules receive more weight than raw candle-direction proxies.
- MTF receives the highest weight because it is a separate timeframe regime check.
- Divergence and Volume S/R receive elevated weights because they provide information different from basic moving-average trend signals.
- VOL and ATR are treated as regime gates in ADAPTIVE_SCORE instead of being counted as independent directional votes.
- Configurable Adaptive Edge and Adaptive Minimum Weight.
- Detailed decision reasons such as `ADAPTIVE_BUY_W..._EDGE...` and `ADAPTIVE_BLOCKED...`.

### 2. Adaptive Grid parity
- When `ADAPTIVE_SCORE` is selected, Grid SCORE/NEUTRAL_GRID now uses the same weighted evidence model rather than silently reverting to raw vote counts.
- Adaptive Grid thresholds are validated against weighted module capacity.

### 3. Peak-equity risk circuit
- Daily drawdown is now measured from the intraday daily peak equity, not only closed balance.
- Session peak equity is persisted for recovery/audit purposes.
- Unrealized drawdown therefore cannot hide behind an unchanged wallet balance.

### 4. Market-data stale-data guard
- Strategy data is rejected when the newest exchange candle is older than the configured timeframe's safety multiple.
- A stale-feed condition becomes a cycle error instead of allowing decisions from old market data.

### 5. Consecutive-cycle safety halt
- Three consecutive execution-cycle errors halt the bot fail-closed.
- The error is stored in runtime state for recovery diagnostics.

### 6. Safe emergency-stop scope
- New default: `BOT_SYMBOL`.
- Optional explicit `ALL_ACCOUNT` scope remains available.
- An emergency loss in one bot therefore does not silently close unrelated positions by default.

### 7. Managed-order cleanup
- Added a managed-order registry derived from active protection and Grid state.
- Normal/Grid shutdown and reversal cleanup now prefer known bot-managed order IDs instead of blindly cancelling every symbol order.

## Modified

- Config schema: **6 → 7**.
- Runtime schema: **3 → 4**.
- New profiles default to `ADAPTIVE_SCORE`; existing saved profiles keep their saved strategy mode.
- Adaptive strategy settings are persisted with normal save/load and recovery snapshots.
- Backtester default strategy mode is also `ADAPTIVE_SCORE` so research starts from the same strategy family as the hardened live bot.
- Backtester includes Adaptive Edge / Adaptive Minimum Weight controls.
- Live/backtest adaptive decision logic was regression-tested for parity.

## Safety / execution philosophy

The bot remains one-way/single-position oriented. Actual exchange position entry price and quantity remain authoritative for protection. Confirmed-candle signals, confirmed divergence pivots, and higher-timeframe close alignment are retained from V8.2.6.

## What was deliberately NOT added

- No Martingale escalation.
- No averaging-down multiplier intended to hide losses.
- No look-ahead / unconfirmed-pivot execution.
- No claim that a backtest guarantees future profit.

## Validation

`tests/test_v830_hardened.py`:

- source compilation: PASS
- V8.3 contracts: PASS
- live/backtester adaptive parity: PASS
- synthetic OHLCV backtest smoke test: PASS
- safety-contract static audit: PASS

**6/6 PASS**.

## Backtester limitations

The backtester remains an OHLC historical simulator. It cannot reproduce exchange queue position, latency, partial fills, funding, liquidation, order-book microstructure, or every exchange-specific conditional-order behavior. Results should be treated as research evidence, not a profit guarantee.