# V8.3.1 — Adaptive Startup + Multi-Bot Isolation Fix

## Incident fixed

The first V8.3.0 live start with ADAPTIVE_SCORE could fail after exchange connection with:

START FAILED: name 'adaptive_edge' is not defined

### Root cause

start_bot() logged the Adaptive thresholds before the worker thread _run_bot_logic() had created its local adaptive_edge and adaptive_min_weight variables.

The GUI fields and saved configuration were present, but the startup callback referenced worker-local variables too early.

## Fixed

### 1. Startup NameError
start_bot() now reads and validates Adaptive Edge and Adaptive Minimum Weight before Adaptive startup logging.

### 2. Per-profile Adaptive isolation
The first V8.3 implementation stored Adaptive thresholds on mutable StrategyEngine class attributes. That can create cross-profile races when multiple bot workers run in the same process.

V8.3.1 removes that shared mutable state. Adaptive thresholds are passed explicitly into:

- StrategyEngine.decide_signal()
- StrategyEngine.decision_reason()
- GUI _decide_signal()

Each bot/profile therefore uses its own thresholds.

### 3. Backtester parity
The backtester no longer relies on global cfg_adaptive_edge / cfg_adaptive_min_weight values. It accepts the same explicit Adaptive parameters as the live decision engine.

## Validation

- Live source compilation: PASS.
- Backtester source compilation: PASS.
- Live/backtester Adaptive decision parity: PASS.
- Adaptive parameter isolation test: PASS.
- Startup ordering / NameError regression test: PASS.
- Mutable shared StrategyEngine state check: PASS.
- Regression suite: 6/6 PASS.

## Existing V8.3 hardening retained

- 19 directional modules.
- ADAPTIVE_SCORE weighting.
- Daily peak-equity drawdown.
- Stale-data protection.
- Consecutive-cycle fail-closed halt.
- BOT_SYMBOL emergency-stop default.
- Managed-order cleanup.
- Confirmed divergence.
- Higher-timeframe S/R close alignment.
- Actual-fill-based SL/TP.
- Grid protection and recovery.

## Important

V8.3.1 is a correctness/hardening patch. It does not claim higher future profitability. The primary objective is to ensure the strategy selected in the GUI is the strategy actually executed, independently for every running bot profile.

## Backtester limitations

The backtester remains an OHLC historical simulator. It cannot reproduce exchange queue position, latency, partial fills, funding, liquidation, order-book microstructure, or every exchange-specific conditional-order behavior.
