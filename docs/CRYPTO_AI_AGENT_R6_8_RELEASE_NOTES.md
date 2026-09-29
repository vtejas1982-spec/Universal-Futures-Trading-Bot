# Crypto AI-Agent R6.8 — Fixed Engine Release Notes

Date: 2026-09-29
Release: V8.4.2-CRYPTO-AI-AGENT-R6.8

## Purpose

R6.8 is the deterministic Crypto AI-Agent engine with evidence-family decisioning, bounded AI trade management, actual-fill protection, exchange-order reconciliation, and fail-closed lifecycle controls.

This hotfix synchronizes the engine with the completed 2026-09-29 audit findings. It is an engineering/Demo hardening release, not a profitability guarantee.

## Fixed

### 1. Python execution safety
- Removed the remaining same-quote nested f-string syntax hazards in protection diagnostics.
- Replaced unsafe TP1/TP2 success formatting when a target is disabled and therefore represented by None.

### 2. AI risk management
- The configured Risk Per Trade is now a hard ceiling for AI dynamic management.
- AI conviction and volatility logic may scale the configured risk downward, but cannot increase a low user-configured risk setting.

### 3. SL-resolution and sizing parity
- Entry sizing now follows the exact normal protection priority: ATR -> normal ROI -> fallback ROI.
- The resolved SL is checked against the conservative liquidation-distance envelope in the protection resolver.
- Startup preflight blocks unsafe ROI/Hold-SL thresholds.
- Pre-entry sizing blocks an unsafe resolved SL before the exchange order is created.

### 4. TP protection
- Percentage TP1/TP2 lot-size feasibility is checked before market entry.
- Disabled TP levels are displayed as OFF instead of being formatted as numeric values.
- TP1 reconciliation now recognizes a likely TP1 fill from the actual live quantity reduction, avoiding repeated false missing-TP1 warnings.

### 5. Strategy/reversal logging
- Normal strategy reversals and Grid direction changes use explicit operational reasons instead of the emergency-close label.

### 6. Worker/UI thread safety
- Worker-thread dashboard updates, runtime checkpoint callbacks and worker-finished callbacks use the GUI UI queue instead of calling Tk directly.

## Retained contracts

- AI-Agent evidence families remain independent of the REGIME gate family.
- ATR/ADX remain regime gates rather than independent directional voters.
- Completed-candle execution semantics remain in force.
- Actual filled entry and actual position quantity remain authoritative for protection.
- Exchange-side SL remains mandatory for normal protection paths.
- Hold-SL WAIT remains an explicit exception where the user intentionally chooses bot-managed reversal monitoring.
- Notional utilization remains conservatively capped at 95% for equity-risk sizing.

## Configuration

Persistent configuration compatibility remains:
- Config schema: 23
- Runtime schema: 24
- AI preset: AI_AGENT_RECOMMENDED_R6.8
- Default TP quantity mode: PERCENT_%
- Default TP split: 50% / 50%
- Default timeframe: 15m
- Default leverage preset: 5x
- Default max open trades: 1
- Default risk per trade: 0.35%

Existing saved profiles remain authoritative; selecting or applying the R6.8 preset is explicit.

## Validation

Completed locally:
- Python bytecode compilation: PASS.
- Worker-thread GUI static audit: PASS.
- Hotfix contract static checks: PASS.
- Strategy mode smoke tests across supported signal modes: PASS.
- Indicator smoke tests for the core R6.8 modules: PASS.
- Synthetic AI-Agent decision tests for bullish, conflicting and no-evidence cases: PASS.

Exchange behavior must still be validated on the intended Demo/Testnet account before Live trading.
