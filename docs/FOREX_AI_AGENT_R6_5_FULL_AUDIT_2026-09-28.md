# Forex MT5 AI-Agent R6.5 — Full Audit — 2026-09-28

## Scope
The MT5 Forex engine is aligned with Crypto AI-Agent R6.5 for strategy, evidence families, AI council thresholds, bounded risk management, SL/TP management, GUI configuration and lifecycle handling. MT5 execution remains Forex-native.

## Added
- AI-Agent R6.5 recommended preset and confirmation workflow.
- AI council controls: 3 families, 0.20 edge, 0.55 family confidence, Trend ON, Structure ON, max 1 conflict.
- Bounded AI risk: 0.20%–0.50%.
- Bounded AI SL: 1.50–2.40 ATR.
- Bounded AI TP1: 1.00–1.50R.
- Bounded AI TP2: 2.00–3.00R.
- AI-aware Forex lot sizing that preserves the AI-selected stop distance.
- Liquidity Swing FRESH_BREAK/CURRENT_TREND control.
- Divergence minimum-count and FRESH/CURRENT_STATE control.
- Visible Grid Mode parity control; Forex MT5 remains OFF-only for grid execution.
- Forex R6.5 historical backtester with CSV/MT5 data, risk sizing, TP1/BE and capital guards.
- Regression tests for StrategyEngine parity and runtime bindings.

## Fixed
- Static ATR lot-sizing logic could overwrite an AI-selected ATR stop; AI stop distance is now authoritative.
- Configuration migration no longer silently applies the full AI preset to existing profiles. Missing fields are added while saved values remain authoritative.
- MT5 GUI close operations are moved off the Tk main thread so network/runtime cleanup does not freeze the window.
- GUI log growth is bounded.

## Modified
- Forex config/runtime schema aligned to 21/22.
- Forex AI-Agent indicator defaults follow the R6.5 recommended profile: 15m, 5x reference leverage, one open trade, 15m cooldown, no same-candle re-entry, evidence-family strategy and R6.5 protection.
- Liquidity and divergence entry semantics are now explicitly configurable and persisted.
- 4H MTF backtesting uses close-availability alignment to avoid future leakage.

## Intentionally Forex-native
- MetaTrader 5 terminal/account modes, broker symbol discovery and order API.
- Forex lot sizing through tick size/tick value.
- Existing MT5 broker-side SL and Forex TP management.
- Grid execution is not copied from crypto futures; the GUI control is OFF-only.

## Validation
- Local Python compilation passed.
- StrategyEngine parity was checked between Forex R6.5 and Crypto R6.5.
- A deterministic synthetic Forex backtest pipeline completed with return code 0.
- No live broker trade was executed during this audit.
