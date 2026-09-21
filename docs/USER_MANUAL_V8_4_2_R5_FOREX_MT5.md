# FOREX / MT5 EDITION — V8.4.2-R5

Primary focus: Forex/MT5 live engine. This file is nevertheless a complete reference for Forex, Crypto and both backtesters.

# Universal Futures & Forex Trading Bot V8.4.2-R5 — Complete User Manual

**Scope:** This manual is self-contained. Each edition contains the complete Crypto Futures, Forex/MT5, strategy, indicator, risk, Grid, protection, and backtesting reference. The edition heading only identifies the primary use case.

## 1. Production files and version contract

| Area | Current production file |
|---|---|
| Crypto live | `UniversalFuturesBot_CRYPTO.py` |
| Crypto backtester | `UniversalFuturesBot_CRYPTO_BACKTESTER.py` |
| Forex / MT5 live | `UniversalForexBot_MT5.py` |
| Forex / MT5 backtester | `UniversalForexBot_MT5_BACKTESTER.py` |

The production root uses stable filenames; old FINAL/AUDITED/HARDENED copies belong in Git history/tags/releases.

**Repository note:** README/CHANGELOG/release notes describe Forex as V8.4.2-R5, while the current Forex live source header still carries an older V8.4.1/R2 APP_VERSION/AUDIT_BUILD. This is a version-label inconsistency and is documented rather than silently hidden.

## 2. R5 architecture — how a signal is built

R5 is an **Evidence-Family** architecture.

Directional families:
- **TREND:** Supertrend, EMA, EMA Cross, MACD, VIDYA, NWE.
- **MOMENTUM:** RSI, Stochastic, Divergence.
- **FLOW:** VWAP, VWAP Delta, Volume, Volume S/R.
- **STRUCTURE:** Liquidity Swings, Trendline Breakout, MTF.

Regime gates:
- **ATR**
- **ADX**

ATR/ADX can block unsuitable market conditions but are not independent directional families in ADAPTIVE_EVIDENCE.

### Default R5 Evidence contract

| Setting | Value |
|---|---:|
| Signal Mode | ADAPTIVE_EVIDENCE |
| Minimum Families | 2 |
| Family Minimum Score | 0.35 |
| Require Trend Family | ON |
| Require Independent non-Trend Family | ON |
| Adaptive Edge | 0.18 |
| Adaptive Minimum Weight | 3.50 |

This prevents false confirmation such as EMA + MACD + Supertrend being counted as three independent families; all three are TREND.

## 3. Signal modes and their meanings

### SINGLE_SIGNAL
A single unambiguous direction can qualify. If bullish and bearish evidence coexist, R5 fails closed and returns no trade.

### ANY_NON_CONFLICTING
BUY requires at least one BUY indication and no SELL indication. SELL is the reverse. Any conflict blocks the signal.

### SCORE
Counts directional confirmations. The chosen side must reach the configured minimum score and exceed the opposite side.

### 2_SIGNALS / 3_SIGNALS / 4_SIGNALS
Require respectively 2, 3 or 4 directional confirmations, with the chosen side exceeding the opposite side.

### ADAPTIVE_SCORE
Uses weighted modules rather than equal votes. Current weights:
- ST 1.50
- EMA 1.00
- EMA_CROSS 1.25
- MACD 1.25
- RSI 1.00
- BB 0.75
- STOCH 0.75
- VWAP 1.25
- VWAP_DELTA 1.00
- VIDYA 1.25
- NWE 1.00
- LIQ_SWING 1.50
- TRENDLINE 1.50
- MTF 2.00
- DIVERGENCE 1.75
- VOL_SR 1.50
- VOL 0.50
- ADX 1.25
- ATR 0.50

The weighted side must meet minimum weighted support, dominate the opposite side, meet Adaptive Edge, and pass the configured regime/MTF gates.

### ADAPTIVE_EVIDENCE
Primary R5 mode. It evaluates family-level bullish/bearish evidence. A side normally needs the minimum number of families, family score, Trend-family requirement, independent non-Trend family requirement, adaptive edge, and ATR/ADX gates.

### STRICT_ALL_FILTERS
Every enabled directional module must agree with the selected side. ATR, volume, ADX and MTF gates also have to pass. This can generate very few trades.

## 4. Indicators — complete reference

### TREND

#### Supertrend (ST)
Purpose: ATR-based trend state.
Options: length, multiplier, source, ATR-change behavior, entry mode.
R5 starting values: length 10, multiplier 3.0, CURRENT_TREND.
CURRENT_TREND means the current trend state supplies direction. Fresh-cross modes require a new transition rather than an already-established state.

#### EMA
Purpose: slower directional trend filter.
R5: length 50.
Price above EMA = bullish module state; below = bearish.

#### EMA Cross
Purpose: faster trend relationship.
R5: fast 9, slow 21.
Fast above slow = bullish; fast below slow = bearish.
Still TREND family, not an independent family.

#### MACD
R5: 12 / 26 / 9.
Compares MACD and signal line for directional evidence.
TREND family.

#### VIDYA
Adaptive moving-average module. The implementation also calculates ATR-derived bands, trend state, cross-up/down and accumulated up/down volume/delta.
Options: length, momentum length, band distance/multiplier, entry mode.
R5 starting recommendation: OFF, because the core Trend family already has substantial evidence.

#### NWE — Nadaraya-Watson Envelope
Causal/end-point envelope implementation.
Options: bandwidth, multiplier, lookback, MAE length, entry mode and repaint protection.
Uses completed/past data for trading signals; future-looking/repainting data is not allowed.
R5 starting recommendation: OFF.

### MOMENTUM

#### RSI
R5: length 14, OB 70, OS 30.
The R5 profile uses RSI as continuation/current-trend momentum evidence rather than automatically buying oversold or selling overbought.
Where MA comparison is enabled, RSI can be compared with its configured MA.
OB/OS describe extremes; they do not automatically create a trade.

#### Stochastic
R5: K 14, smoothing 3, D 3.
K > D = bullish momentum; K < D = bearish momentum.

### Bollinger Bands (BB) — optional module

The R5 code retains Bollinger Bands as an optional weighted strategy module. It is **not** one of the four named R5 Evidence families, so enabling BB does not create an additional independent Evidence family in ADAPTIVE_EVIDENCE.

Current backtester defaults:
- Use BB = OFF
- Length = 20
- Standard deviation = 2.0


Meaning: the middle band is the moving-average reference; upper/lower bands are volatility envelopes. A BB directional condition can contribute when enabled, but its contribution is subject to the selected signal mode.


For ADAPTIVE_SCORE, BB has weight 0.75. For ADAPTIVE_EVIDENCE, do not count BB as a fifth independent family.


### RSI comparison options

The current backtester profile contains:
- RSI length = 14
- Overbought = 70
- Oversold = 30
- RSI logic = CROSS_MA
- RSI MA type = EMA
- RSI MA length = 9


CROSS_MA means the strategy compares RSI with its configured RSI moving average rather than treating 70/30 alone as a trade trigger. The OB/OS values remain contextual momentum thresholds.


### NWE option details

The backtester profile includes:
- Bandwidth = 8.0
- Multiplier = 3.0
- Lookback = 500
- MAE length = 499
- Entry mode = FRESH_CROSS


FRESH_CROSS is intended to react to a newly occurring envelope crossing rather than repeatedly treating an already-established state as a new event. The implementation is causal/end-point and does not use future values for trading decisions.


### Divergence source-option meanings

The ten supported divergence source series have distinct roles:
- MACD: trend/momentum oscillator relationship.
- MACD Histogram: distance between MACD and signal line.
- RSI: momentum strength.
- Stochastic: short-term momentum.
- CCI: deviation of typical price from its moving average.
- Momentum: price change over the configured momentum length.
- OBV: cumulative volume signed by price direction.
- VWMACD: volume-weighted MACD-style relationship.
- CMF: money-flow pressure relative to the candle range.
- MFI: volume-weighted momentum/flow oscillator.


The Use All Divergence Sources option enables the configured divergence source set together. Individual source switches are also persisted by the engine where available.


### Liquidity/Trendline event-option meanings

FRESH_BREAK = only a newly detected break is treated as the event.
CURRENT_ZONE = the current price/zone state can provide the directional state.
CURRENT_TREND = the existing current directional state can provide evidence.
COUNT filter = uses the configured count-based swing/filter interpretation.
Wick Extremity = uses wick extremes as the swing/liquidity reference area.
Retest = number of subsequent candles considered for the configured trendline retest behavior.


### MTF anti-lookahead rule

The higher-timeframe candle must be available before its information is merged into the lower-timeframe decision. In the 4H-on-15m configuration, the bot does not intentionally use an unfinished future 4H candle as if it were already closed.

#### Divergence
A causal/confirmed momentum module. Supported source series:
MACD, MACD Histogram, RSI, Stochastic, CCI, Momentum, OBV, Volume-weighted MACD, CMF, MFI.
Options include pivot length, maximum pivots, maximum bars, divergence type, source, all-source switch, CCI length, momentum length, VW-MACD fast/slow, CMF length and MFI length.
Confirmed pivots are used. Future-looking “don't wait for confirmation” signals are not permitted.
Regular bullish divergence: price makes a weaker/lower low while the oscillator makes a stronger/higher low. Regular bearish is the inverse. Hidden divergence is continuation-style divergence where selected.

### FLOW

#### VWAP
Price/flow reference.
R5 length 50.
Above VWAP = bullish flow evidence; below = bearish.

#### VWAP Delta
VWAP-derived flow/delta state.
Options: smoothing, smoothing length, baseline, logic.
R5: smoothing ON, length 21, baseline 50, CURRENT_TREND.
It belongs to FLOW.

#### Volume
R5 volume MA commonly 20.
Volume can act as a flow/quality condition. The evidence architecture avoids pretending raw volume is an independent directional family by itself.
When used directionally, candle close > open is bullish and close < open bearish.

#### Volume S/R (VOL_SR)
Converts volume-confirmed support/resistance/fractal concepts into numerical strategy states.
Options: volume MA, vote mode, entry mode and zone/history parameters.
R5 profile: MA 20, MAJORITY vote, CURRENT_ZONE entry.
It is strategy state, not only a chart drawing.

### STRUCTURE

#### Liquidity Swings
Finds meaningful swing/liquidity areas and directional breaks.
Options: length, area, filter, filter value, entry mode.
R5: length 14, Wick Extremity, Count.
Wick Extremity emphasizes swing extremes represented by wicks.

#### Trendline Breakout
Detects breaks of swing-derived trendlines.
Options: length, minimum distance, buffer, retest candles, entry mode.
R5: length 14, minimum distance 5, buffer 0, retest 3, FRESH_BREAK.
FRESH_BREAK means a newly occurring break rather than an already-established position above/below the line.

#### MTF
Higher-timeframe structural alignment.
R5 profile: chart 15m, higher timeframe 4H.
The strategy builds a higher-TF EMA200 context:
higher-TF close > EMA200 = bullish; below = bearish.
Availability is aligned so an incomplete future higher-TF candle is not used.

### REGIME

#### ATR gate
ATR measures volatility. Gate uses ATR/price*100.
Recommended starting threshold:
- Crypto 0.30%
- Forex 0.20%
ATR is a regime gate, not a directional family in ADAPTIVE_EVIDENCE.

#### ADX gate
Measures trend strength, not direction.
R5:
- Crypto length 14, threshold 21
- Forex length 14, threshold 20
If ADX is below the configured threshold, the strategy can block a trend-dependent signal.

## 5. Entry / execution modes

### DIRECT_SHOT
One normal strategy position when all signal, risk and protection conditions pass. Recommended first production mode.

### LONG_GRID
Long-side grid operation.

### SHORT_GRID
Short-side grid operation.

### NEUTRAL_GRID
Grid operation without forcing a single initial direction, subject to configured evidence/trend/exposure controls.

### OFF
Grid disabled.

Current Crypto engine/backtester supports all five: OFF, DIRECT_SHOT, LONG_GRID, SHORT_GRID, NEUTRAL_GRID.

## 6. Grid options

The Crypto R5 backtester includes:
- Grid levels: maximum planned/additional levels.
- Grid spacing: distance between levels.
- Grid order size: base order size.
- Grid size increase: optional increase for later levels.
- Grid TP: basket/group profit target.
- Grid SL: global basket protection.
- Grid max exposure: total exposure ceiling.
- Grid max DD: grid drawdown ceiling.
- Grid score minimum: minimum strategy/evidence quality.
- Grid trend filter: alignment requirement.
- Grid recenter: move grid reference when configured.
- Grid recenter distance: distance triggering recentering.
- Grid cooldown: minimum time between grid cycles/actions.

Starting production recommendation: validate DIRECT_SHOT first and keep Grid OFF until behavior is understood.

## 7. Risk management

Risk is intended to be derived from account equity and stop distance rather than simply increasing leverage.

Conceptually:
**position size ≈ allowed monetary risk / stop distance**

Crypto starting profile:
- risk 0.75% preferred; source range 0.5–1.0%
- max DD 5%
- daily loss 3%
- emergency capital loss 30%
- max consecutive losses 3

Forex starting profile:
- risk 0.50% preferred; source range 0.5–0.75%
- max DD 5%
- daily loss 2%
- max loss streak 3
- emergency scope BOT_ONLY

## 8. Candle, cooldown and lock rules

Completed Candle: R5 signals are intended to use completed candles.

Same Candle Re-entry: recommended OFF.

Cooldown: blocks a new action until configured time has elapsed.

Post-SL opposite lock: after a stop loss, the bot can require an opposite-direction signal before another entry. This is a behavioral safety rule, not a prediction.

Hold-All-Reverse / reverse controls:
- exit-on-opposite behavior
- hold until all reverse
- wait-for-reversal behavior
are distinct settings. An opposite indicator does not automatically close a position unless the selected execution logic says so.

## 9. SL / TP protection

R5 ATR Dynamic contract:
**SL = 1.50 × completed-candle ATR**
**TP1 = 1.20 × actual SL distance**
**TP2 = 2.20 × actual SL distance**

Live Crypto protection uses the actual filled entry and actual position quantity.

Typical split:
- TP1 50%
- TP2 50%
- TP1 break-even ON

The engines also support PRICE_% and ROI_% modes.

### PRICE_%
Percentage is price movement from actual entry.

### ROI_%
Percentage is target position ROI and is converted into a price trigger using leverage. ROI % is therefore not the same as price %.

## 10. Live Crypto engine

Supported exchanges in the current Crypto source:
- Bybit
- Binance
- Gate.io
- Bitget
- WEEX

Protection architecture:
1. obtain actual filled position entry
2. calculate protection from actual average entry
3. fetch actual quantity
4. use exchange-specific trigger parameters
5. verify created protection
6. if protection cannot be installed, attempt to avoid leaving the position unprotected
7. maintain runtime/checkpoint order ownership/recovery controls

Current coordinator is single-symbol net-position:
**Max Open Trades above 1 is normalized to 1 net position per bot/symbol.**
This does not mean two independent same-symbol positions are supported.

## 11. Crypto recommended starting profile

| Setting | Start |
|---|---|
| Timeframe | 15m |
| Higher TF | 4H |
| Entry | DIRECT_SHOT |
| Signal | ADAPTIVE_EVIDENCE |
| Min families | 2 |
| Family score | 0.35 |
| Trend required | ON |
| Independent family required | ON |
| Adaptive Edge | 0.18 |
| Adaptive minimum weight | 3.50 |
| Supertrend | 10 / 3.0 / CURRENT_TREND |
| EMA | 50 |
| EMA Cross | 9 / 21 |
| MACD | 12 / 26 / 9 |
| VIDYA | OFF initially |
| NWE | OFF initially |
| RSI | 14 / 70 / 30 |
| Stochastic | 14 / 3 / 3 |
| Divergence | ON, confirmed/causal, all sources |
| VWAP | 50 |
| VWAP Delta | 21, baseline 50, CURRENT_TREND |
| Volume | MA 20 |
| Volume S/R | MA 20, MAJORITY, CURRENT_ZONE |
| Liquidity | 14, Wick Extremity, Count |
| Trendline | 14, min distance 5, buffer 0, retest 3, FRESH_BREAK |
| MTF | 4H |
| ATR gate | 0.30% |
| ADX | 14 / 21 |
| Risk | 0.75% preferred |
| Max DD | 5% |
| Daily loss | 3% |
| Loss streak | 3 |
| ATR SL | 1.5x |
| TP1 / TP2 | 1.2R / 2.2R |
| Grid | OFF initially |

## 12. Live Forex / MT5 engine

The Forex engine is MT5-native and includes:
- broker lot/price rules
- MT5 account handling
- Evidence-family strategy
- ATR Dynamic protection
- post-SL lock
- checkpoint/recovery
- spread controls
- session controls
- Friday controls
- news controls
- correlation controls

It is not simply the Crypto engine with different symbols.

### Forex news
Recommended ON for USD/EUR/GBP/JPY.
Window: 30 minutes before and 30 minutes after.
Fail-closed rule: **news data unavailable -> BLOCK NEW ENTRY.**

### Forex session
Recommended ON: 07:00–20:00.
Friday protection ON: cutoff 18:00.
Verify time basis against the MT5 environment/broker.

### Forex pairs for initial testing
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF.
Avoid stacking several highly correlated USD positions.

## 13. Forex recommended starting profile

| Setting | Start |
|---|---|
| Timeframe | 15m |
| Higher TF | 4H |
| Entry | DIRECT_SHOT |
| Signal | ADAPTIVE_EVIDENCE |
| Min families | 2 |
| Family score | 0.35 |
| Trend required | ON |
| Independent family required | ON |
| Adaptive Edge | 0.18 |
| Supertrend | 10 / 3.0 / CURRENT_TREND |
| EMA | 50 |
| EMA Cross | 9 / 21 |
| MACD | 12 / 26 / 9 |
| VIDYA | OFF |
| NWE | OFF |
| RSI | 14 / 70 / 30 |
| Stochastic | 14 / 3 / 3 |
| Divergence | ON, confirmed, all sources |
| VWAP | 50 |
| VWAP Delta | 21 / baseline 50 |
| Volume | MA 20 |
| Volume S/R | MA 20, MAJORITY, CURRENT_ZONE |
| Liquidity | 14, Wick Extremity, Count |
| Trendline | 14, distance 5, buffer 0, retest 3, FRESH_BREAK |
| MTF | 4H |
| ATR gate | 0.20% |
| ADX | 14 / 20 |
| Risk | 0.50% preferred |
| Max DD | 5% |
| Daily loss | 2% |
| Loss streak | 3 |
| News | ON |
| Session | ON |
| Friday | ON |
| Grid | OFF initially |

### Forex TP documentation distinction
The supplied profile recommends TP1 = 1.3R and TP2 = 2.2R. The GitHub R5 protection contract documents TP1 = 1.20 × actual SL distance and TP2 = 2.20 × actual SL distance. These should not be treated as the same configuration statement. Verify the actual GUI/profile values before trading.

## 14. Backtester — what it does

Crypto:
`UniversalFuturesBot_CRYPTO_BACKTESTER.py`

Forex:
`UniversalForexBot_MT5_BACKTESTER.py`

The backtesters are strategy simulators. They preserve strategy-side behavior including completed-candle signals, next-candle-open entries, evidence decisions, MTF, divergence, Volume/S/R, risk sizing, cooldown, drawdown, loss controls, ATR Dynamic SL/TP, TP1 partial close, break-even and supported Grid logic.

Crypto backtester capabilities recorded in the repository include:
- raw OHLCV/DataFrame/CSV input
- Binance/Bybit public OHLCV
- CSV/XLSX export when available
- parameter sweep
- walk-forward
- combination testing
- multi-symbol sequential runs
- Grid modes and Grid controls

### Historical execution rule
Signals use completed candles; normal entries are simulated at the next candle open.

### Same-bar ambiguity
If one candle touches both SL and TP, the Crypto R5 backtester uses conservative **SL-first** handling.

### Backtest limitations
Historical candles cannot prove:
- exchange/broker order acceptance
- funding
- liquidation
- exact spread
- latency
- partial fills
- precision/trigger behavior
- websocket failures/reconnects
- live checkpoint/reconciliation behavior

Do not treat a backtest as proof of live profitability.

## 15. Backtest workflow

1. Verify symbol, timeframe, dates and OHLCV quality.
2. Start from the R5 profile before optimization.
3. Check trade count and signal reasons.
4. Review drawdown, loss streak, stop frequency, TP1/TP2 behavior and exposure, not only net return.
5. Use walk-forward or separate validation periods.
6. Test demo/paper with the exact production engine.
7. Only then consider live deployment.

## 16. Configuration persistence

Current configuration schema:
**CONFIG_SCHEMA_VERSION = 9**

Important persisted R5 fields include:
- max_open_trades
- use_atr_sl
- atr_sl_mult
- atr_tp1_mult
- atr_tp2_mult
- evidence-family settings

Existing saved profiles remain authoritative; missing R5 fields are populated with safe defaults.

## 17. Runtime diagnostics

Important diagnostics can include:
Signal, Closed Candle, EMA filter/cross, Supertrend, Signal Mode, evidence votes, family scores, MACD, RSI, BB, Stochastic, VWAP, VWAP Delta, Volume, Volume S/R, Liquidity, Trendline, MTF, ATR, ADX, Entry Price, ATR, SL Price %, SL ROI %, TP1 Price %, TP1 ROI %, TP2 Price %, TP2 ROI %.

Use diagnostics to understand why a trade was allowed or blocked.

## 18. Common NO-TRADE reasons

- no enabled directional modules
- bullish/bearish conflict
- minimum family count not reached
- Trend family requirement not met
- independent family requirement not met
- adaptive edge not met
- ATR gate failed
- ADX gate failed
- MTF disagrees
- cooldown active
- same-candle protection
- daily loss protection
- max drawdown protection
- loss-streak protection
- post-SL opposite lock
- Forex news window
- Forex session/Friday protection
- correlation protection
- Grid exposure/level limit

## 19. Commands

Install:
```powershell
py -3.14 -m pip install -r requirements.txt
```

Crypto live:
```powershell
py -3.14 UniversalFuturesBot_CRYPTO.py
```

Crypto backtest:
```powershell
py -3.14 UniversalFuturesBot_CRYPTO_BACKTESTER.py
```

Forex live:
```powershell
py -3.14 UniversalForexBot_MT5.py
```

Forex backtest:
```powershell
py -3.14 UniversalForexBot_MT5_BACKTESTER.py
```

## 20. Safety checklist

Before live trading:
- use demo/testnet/paper first
- verify symbol/timeframe/leverage
- verify risk and protection
- verify saved profile
- verify Max Open Trades is understood as one net position per symbol
- verify actual SL/TP after a fill
- verify API/broker permissions
- verify news/session controls for Forex
- monitor logs/recovery behavior
- never commit API keys/passwords/tokens

## 21. R5 validation recorded by the repository

Crypto R5 documentation reports:
- 27/27 engine checks PASS
- GUI smoke PASS
- synthetic raw-OHLCV backtest PASS
- SINGLE_SIGNAL conflict fail-closed PASS

Forex R5 documentation reports:
- 26/26 local audit checks PASS
- GUI smoke PASS
- configuration round-trip PASS
- synthetic raw-OHLCV backtest PASS
- Evidence-family contract PASS

These are repository-reported validation results, not guarantees of live trading performance.

## 22. R5 mental model

```
OHLCV / MT5 DATA
      ↓
INDICATORS
      ↓
TREND + MOMENTUM + FLOW + STRUCTURE
      ↓
EVIDENCE-FAMILY ENGINE
      ↓
ATR / ADX REGIME GATES + MTF
      ↓
RISK / COOLDOWN / DD / LOSS / NEWS / SESSION CONTROLS
      ↓
DIRECT_SHOT or GRID
      ↓
ACTUAL FILL
      ↓
ATR / PRICE / ROI PROTECTION
      ↓
TP1 → optional break-even → TP2
      ↓
LOG / CHECKPOINT / RECOVERY
```

**Core R5 principle:** require better evidence from different families instead of simply counting more correlated indicators.


## APPENDIX — SUPPLIED UPDATED MANUAL: RECOMMENDED CRYPTO + FOREX PROFILES

The supplied V8.4.2-R5 updated manual contains the following recommended settings. They are recommendations, not profitability guarantees.

### Crypto Futures — recommended profile

| Setting | Value |
|---|---|
| Timeframe | 15m |
| Higher timeframe | 4H |
| Entry / Grid | DIRECT_SHOT; Grid OFF initially |
| Signal Mode | ADAPTIVE_EVIDENCE |
| Minimum Families / Family Score | 2 / 0.35 |
| Trend / Independent family required | YES / YES |
| Adaptive Edge / Minimum Weight | 0.18 / 3.50 |
| Max Open Trades | 1 net position per bot/symbol |
| Cooldown | 15 min |
| Completed Candle / Same-candle re-entry | ON / OFF |
| Leverage | 3x–5x |
| Margin | ISOLATED where supported |
| Risk / trade | 0.75% preferred; source range 0.5%–1.0% |
| Max DD | 5% |
| Emergency capital loss | 30% |
| Loss streak | ON; max 3 |
| Daily loss | ON; 3% |
| Supertrend | ON; 10; 3.0; CURRENT_TREND |
| EMA / EMA Cross | ON; 50 / ON; 9/21 |
| MACD | ON; 12/26/9 |
| VIDYA / NWE | OFF initially / OFF initially |
| RSI | ON; 14; OB 70; OS 30; continuation/current-trend style |
| Stochastic | ON; K14; Smooth3; D3 |
| Divergence | ON; confirmed/causal; all sources ON |
| VWAP | ON; 50 |
| VWAP Delta | ON; Smooth; 21; baseline 50; CURRENT_TREND |
| Volume / Volume S/R | ON; MA20 / ON; MA20; MAJORITY; CURRENT_ZONE |
| Liquidity Swings | ON; 14; Wick Extremity; Count |
| Trendline Breakout | ON; 14; min distance 5; buffer 0; retest 3; FRESH_BREAK |
| MTF | ON; 15m + 4H |
| ATR gate | Recommended ON; minimum 0.30% |
| ADX | ON; 14; threshold 21 |
| ATR Dynamic SL | ON; 1.50 × completed-candle ATR |
| TP1 / TP2 | 1.20 × actual SL distance / 2.20 × actual SL distance |
| TP1 / TP2 close | 50% / 50% |
| TP1 break-even | ON |

### Forex / MT5 — recommended profile

| Setting | Value |
|---|---|
| Timeframe / Higher timeframe | 15m / 4H |
| Entry | DIRECT_SHOT |
| Signal Mode | ADAPTIVE_EVIDENCE |
| Minimum Families / Family Score | 2 / 0.35 |
| Trend / Independent family required | YES / YES |
| Adaptive Edge | 0.18 |
| Risk / trade | 0.50% preferred |
| Max DD / Daily loss | 5% / 2% |
| Max loss streak | 3 |
| Emergency scope | BOT_ONLY |
| News filter | ON; 30 min before + 30 min after |
| News unavailable | BLOCK NEW ENTRY |
| Session | ON; 07:00–20:00 |
| Friday protection | ON; cutoff 18:00 |
| Grid | OFF initially |
| Supertrend | ON; 10/3.0; CURRENT_TREND |
| EMA / EMA Cross | ON; 50 / ON; 9/21 |
| MACD | ON; 12/26/9 |
| VIDYA / NWE | OFF / OFF; repaint protection retained |
| RSI / Stochastic | ON; 14/70/30 / ON; 14/3/3 |
| Divergence | ON; confirmed; all sources ON |
| VWAP | ON; 50 |
| VWAP Delta | ON; Smooth; 21; baseline 50; CURRENT_TREND |
| Volume / Volume S/R | ON; MA20 / ON; MA20; MAJORITY; CURRENT_ZONE |
| Liquidity Swings | ON; 14; Wick Extremity; Count |
| Trendline Breakout | ON; 14; min distance 5; buffer 0; retest 3; FRESH_BREAK |
| MTF | ON; 15m + 4H |
| ATR gate | Recommended 0.20% minimum |
| ADX | ON; 14; threshold 20 |
| ATR Dynamic SL | ON; 1.50 × completed-candle ATR |
| TP1 / TP2 | **1.30R / 2.20R in the supplied recommendation** |
| TP1 / TP2 close | 50% / 50% |
| TP1 break-even | ON |

### Forex pairs listed in the supplied manual

EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF. The supplied manual also says to avoid opening several highly correlated USD positions simultaneously; the audited Forex engine includes correlation controls.

### Important Forex TP1 distinction

The supplied updated manual records **TP1 = 1.30R** as the recommended Forex profile value. Separately, the GitHub R5 engine/release contract documents **TP1 = 1.20 × actual SL distance** and TP2 = 2.20 × actual SL distance. These are intentionally documented as two different values/semantics rather than silently changing one to match the other. Verify the actual GUI/profile value before live trading.

### Quick-start values from the supplied manual

| Parameter | Crypto | Forex |
|---|---|---|
| TF | 15m | 15m |
| MTF | 4H | 4H |
| Entry | DIRECT_SHOT | DIRECT_SHOT |
| Signal | ADAPTIVE_EVIDENCE | ADAPTIVE_EVIDENCE |
| Families / Family score | 2 / 0.35 | 2 / 0.35 |
| Trend / Independent | YES / YES | YES / YES |
| Adaptive Edge | 0.18 | 0.18 |
| ST / EMA / Cross / MACD | 10/3; 50; 9/21; 12/26/9 | 10/3; 50; 9/21; 12/26/9 |
| RSI / Stoch | 14/70/30; 14/3/3 | 14/70/30; 14/3/3 |
| Divergence | ON, causal | ON, causal |
| VWAP / Delta | ON / ON | ON / ON |
| Volume / S/R | ON / ON | ON / ON |
| Liquidity / Trendline | ON / ON | ON / ON |
| ATR gate | 0.30% recommended | 0.20% recommended |
| ADX | 21 | 20 |
| Risk / trade | 0.75% preferred | 0.50% preferred |
| Max DD | 5% | 5% |
| Daily loss | 3% | 2% |
| Loss streak | 3 | 3 |
| ATR SL | 1.5× | 1.5× |
| TP1 / TP2 | 1.2R / 2.2R recommended | 1.3R / 2.2R recommended |
| Grid | OFF initially | OFF |
| News / session | N/A | ON / ON |
