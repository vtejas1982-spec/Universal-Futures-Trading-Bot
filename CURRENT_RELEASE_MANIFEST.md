# Current Release Manifest — Forex MT5 V7.1.3

## Active release
- Release: **V7.1.3**
- Engine: `UniversalForexBot_MT5.py`
- Audited artifact: `UniversalForexBot_MT5_V7_1_3_AUDITED.py`
- Low-memory reference: `UniversalForexBot_MT5_V7.1.2_LOW_MEMORY.py`
- Config schema: **71**
- Runtime schema: **71**
- Default signal mode: **AI_AGENT**
- Platform: **MetaTrader 5 / Forex**

## Safety and engine scope
- MT5-native market data, position, order and volume semantics.
- Forex-only runtime guard rejects Crypto/futures exchange selection.
- V7.1 evidence-family council and guarded 2F fallback.
- BUY/SELL council split fails closed.
- Completed-candle ambiguous BUY+SELL signal fails closed.
- Broker-side SL verification retained.
- TP1/TP2 bot management retained for MT5.
- Minimum-lot TP split handled safely.
- Break-even verification retries once and retains the original SL on failure.
- Global capital authority, scanner lifecycle and resource-governor controls retained.
- Persistent kill-switch latch retained.

## Validation
- AST parse: PASS
- Python compile: PASS
- Randomized council regression: PASS
- 2F fallback opposing-family regression: PASS
- MT5 lot/protection contract: PASS
- Live MT5 terminal/broker validation: **PENDING**

## Repository source status
The GitHub production source is now synchronized to the V7.1.3 Forex release. Historical release notes remain for reference only.
