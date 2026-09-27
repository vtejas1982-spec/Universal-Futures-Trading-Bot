# Cross-engine parity audit — 2026-09-28

## Scope

Compared:

- `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.5.py`
- `UniversalForexBot_MT5.py`
- `UniversalForexBot_MT5_BACKTESTER.py`

## Strategy parity checks

The Forex `StrategyEngine` AST is identical to the Crypto R6.5 `StrategyEngine`.

The following shared indicator/strategy calculation functions are identical:

- RMA
- Supertrend
- ADX
- MACD
- RSI
- WMA / RSI MA / HMA
- VWAP Delta
- Volumatic VIDYA
- Nadaraya-Watson Envelope
- Bollinger
- Stochastic
- VWAP
- Liquidity Swings
- Trendline Breakout
- Divergence module
- Volume/SR base-series calculation

The shared `AI_AGENT_PRESET` is value-identical across the two engines (134 keys).

## Execution boundary

Crypto remains CCXT/futures-native. Forex remains MT5-native. The Forex source does not enable Crypto exchange execution simply because the strategy contract is shared.

## AI risk/protection boundary

Both engines expose the same hard AI envelopes:

- Risk: 0.20%–0.50%
- SL: 1.50–2.40 ATR
- TP1: 1.00–1.50R
- TP2: 2.00–3.00R

Forex converts those targets into MT5 broker price levels using its existing MT5-safe price/lot/protection functions.

## Reversal parity

Forex now supports both:

- `ALL_ACTIVE`
- `MIN_FAMILIES`

for the existing Hold-All-Reverse behavior. The default AI preset leaves Hold-All-Reverse OFF.

## Configuration / GUI

- AI_AGENT added to Forex signal modes.
- Six AI-Agent controls added and persisted.
- Explicit YES/NO preset confirmation added.
- Max Open Trades exposed and normalized to 1 for the current single-position MT5 contract.
- Existing Forex guardrails retained.
- Copy/Clear/Auto Scroll log controls retained.

## Backtesting

The Forex backtester now uses the live Forex strategy module implementations instead of duplicating simplified indicator formulas, and it calls the live StrategyEngine for AI-Agent decisions.
