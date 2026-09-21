# V8.4.1 Final Full Engine Audit — 2026-09-21

## Scope

This was a full audit of the crypto live bot against the V8.2 Engine Audit requirements and the V8.4 Evidence-Family redesign, covering:

- strategy engine and 19 directional modules
- Evidence-Family logic
- GUI variables/options/callbacks
- defaults and save/load persistence
- preflight validation
- Grid engine and Grid safety
- actual-fill SL/TP protection
- TP1 break-even and protection reconciliation
- recovery/resume and managed-order ownership
- multi-bot profile isolation
- exchange/account-mode handling
- backtester parity
- regression/synthetic indicator tests

## Critical fixes found in this audit

### 1. Restored missing core indicator engine

The categorized crypto live file was syntactically valid but had accidentally lost the executable definitions for these functions:

- `calculate_rma`
- `calculate_supertrend`
- `calculate_adx`
- `calculate_macd`
- `calculate_rsi`
- `calculate_wma`
- `calculate_rsi_ma`
- `calculate_hma`
- `calculate_vwap_delta`
- `calculate_vidya`
- `calculate_nadaraya_watson_envelope`

The live bot could therefore import/compile while failing when the strategy attempted to calculate indicators.

All eleven functions were restored from the audited live/recovery implementation.

### 2. Hardened ADX

`calculate_adx()` is now self-contained and calculates its own true-range columns. It no longer depends on Supertrend having been called first.

The same hardening was applied to the strategy-parity backtester.

### 3. Fixed missing Divergence GUI control

The GUI loaded/saved `e_div_min_count` and the runtime used it, but the categorized GUI did not create the entry widget.

The `Min Div` control is now present in MOMENTUM and participates in save/load.

### 4. Fixed "Use all divergence sources"

The `Use all divergence sources` GUI option was present but not functionally synchronized.

It now:
- enables all divergence sources when turned ON
- automatically clears itself when an individual source is disabled
- persists through save/load

### 5. Fixed Evidence diagnostic parity

`decision_reason()` now receives the exact Evidence-Family settings used by the live decision:
- Minimum Families
- Family Minimum Score
- Require Trend Family
- Require Independent Non-Trend Family

This prevents the log/diagnostic reason from being generated with different defaults than the actual decision.

### 6. Fixed default signal migration

When an older configuration has no `signal_mode`, the fallback is now the current `DEFAULT_SIGNAL_MODE` (`ADAPTIVE_EVIDENCE`) rather than legacy `ADAPTIVE_SCORE`.

Existing explicitly saved modes remain authoritative.

### 7. Added account-mode preflight validation

The startup preflight now validates the selected account mode against the selected exchange before exchange construction.

Examples:
- Bybit: `BYBIT_DEMO`, `BYBIT_TESTNET`, `LIVE`
- Binance/Gate: `TESTNET`, `LIVE`
- Bitget/WEEX: `DEMO`, `LIVE`

The exchange builder already remained fail-closed and does not silently convert a mismatch into LIVE.

### 8. Protection verification now fails closed

A newly submitted SL/TP/BE order is now considered verified only when the exchange explicitly reports it as open.

An inconclusive exchange response is no longer treated as proof that protection is active.

This is especially important for:
- initial SL/TP creation
- TP1 break-even replacement
- protection recovery

## V8.4 Evidence-Family GUI

Section 3 remains organized as:

- TREND — direction / trend continuation
- MOMENTUM — reversal / acceleration
- FLOW — price / volume participation
- STRUCTURE — market geometry / location
- REGIME — ATR/ADX tradeability gates
- OPTIONAL / LEGACY — Bollinger
- DECISION ENGINE — Evidence-Family and legacy signal modes

The five-family contract remains:

- TREND: ST, EMA, EMA Cross, MACD, VIDYA, NWE
- MOMENTUM: RSI, Stochastic, Divergence
- FLOW: VWAP, VWAP Delta, Volume, Volume S/R
- STRUCTURE: Liquidity Swings, Trendline Breakout, MTF
- REGIME: ATR, ADX

REGIME is a gate and is not counted as independent directional evidence.

## V8.2 safety contract retained

The audit confirmed that the current engine still contains the previously required hardening for:

- actual filled entry price before protection calculation
- actual filled position quantity
- exchange-side SL/TP creation and verification
- TP1 break-even replacement ordering
- protection reconciliation
- fail-closed unknown/manual order handling
- exact managed-order ownership
- Grid individual order verification
- Grid cancellation verification
- Grid exposure and Grid DD controls
- NEUTRAL_GRID direction handling
- Hold-All-Reverse
- Hold-SL WAIT mode
- post-SL opposite-signal lock
- same-candle protection
- recovery identity checks
- symbol normalization
- profile locking and safe profile deletion
- worker-thread avoidance of Tkinter `stop_bot()` calls
- stale-market-data and consecutive-cycle-error safety
- emergency-stop scope
- multi-bot runtime isolation

## Validation

Final regression suite:

**54 PASS / 0 FAIL / 0 SKIP**

Covered by deterministic tests:
- AST parsing
- Python compilation
- all eleven core indicator functions
- Evidence-Family StrategyEngine
- legacy signal modes
- regime-gate behavior
- Evidence diagnostic parity
- protection fail-closed behavior
- full 19-module indicator chain
- Volume S/R module
- GUI initialization
- critical GUI controls
- configuration save/load round-trip

Import smoke:
- live crypto bot: PASS
- backtester: PASS
- recovery engine: PASS

## Important limitation

This remains a source-code and deterministic/synthetic audit. It does not prove exchange-specific live execution behavior. Demo/testnet validation should still be performed before live leveraged trading.