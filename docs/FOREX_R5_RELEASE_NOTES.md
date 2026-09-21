# Forex / MT5 V8.4.2-R5 Release Notes

## Production files
- `UniversalForexBot_MT5.py`
- `UniversalForexBot_MT5_BACKTESTER.py`

## Fixed / modified
- Forex R5 is now self-contained and no longer imports the historical V8.4.0 engine file.
- Max Open Trades above 1 normalize safely to 1 net position per bot/symbol.
- ATR Dynamic SL/TP uses completed-candle ATR and actual filled entry/position quantity.
- ATR GUI controls and configuration persistence are part of the R5 production engine.
- Backtester points directly to the clean production Forex engine.
- Existing saved profiles remain authoritative; missing R5 settings use safe defaults.

## Strategy contract
- ADAPTIVE_EVIDENCE.
- Minimum families = 2.
- Family score = 0.35.
- Trend required.
- Independent non-Trend family required.
- Adaptive Edge = 0.18.
- Adaptive minimum weight = 3.50.
- ATR/ADX remain regime gates, not directional families.

## Protection contract
- SL = 1.50 × completed-candle ATR.
- TP1 = 1.20 × actual SL distance.
- TP2 = 2.20 × actual SL distance.
- Runtime logs report actual entry, ATR, Price %, and ROI %.

## Limitation
MT5 broker behavior, fills, stop-distance rules, terminal connectivity and account mode must be validated in MT5 demo/paper before live use.
