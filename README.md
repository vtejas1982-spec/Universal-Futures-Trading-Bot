# Universal Futures & Forex Trading Bot

**Current production release: V8.4.2-R5**

This repository is intentionally kept clean: the main branch contains the **current production engines**, not a pile of old V8.x copies. Historical snapshots belong in Git history/tags/releases.

## Current production files

| Area | Live engine | Backtester |
|---|---|---|
| Crypto / Futures | `UniversalFuturesBot_CRYPTO.py` | `UniversalFuturesBot_CRYPTO_BACKTESTER.py` |
| Forex / MT5 | `UniversalForexBot_MT5.py` | `UniversalForexBot_MT5_BACKTESTER.py` |

### Tests

- `tests/test_crypto_engine.py`
- `tests/test_crypto_gui.py`
- `tests/test_forex_engine.py`

### Build scripts

- `BUILD_CRYPTO_EXE.bat`
- `BUILD_FOREX_EXE.bat`

## V8.4.2-R5 contract

### Strategy

- Signal mode: `ADAPTIVE_EVIDENCE`
- Minimum evidence families: **2**
- Family minimum score: **0.35**
- Trend family required: **ON**
- Independent non-Trend family required: **ON**
- Adaptive Edge: **0.18**
- Adaptive Minimum Weight: **3.50**
- Evidence families:
  - TREND
  - MOMENTUM
  - FLOW
  - STRUCTURE
- ATR and ADX are **regime gates**, not independent directional evidence families.
- `DIRECT_SHOT`, `LONG_GRID`, `SHORT_GRID`, and `NEUTRAL_GRID` remain supported by the Crypto engine.

## Dynamic protection

R5 uses the following ATR relationship when ATR Dynamic protection is enabled:

```
Completed-candle ATR
        ↓
SL = 1.50 × ATR
        ↓
TP1 = 1.20 × actual SL distance
TP2 = 2.20 × actual SL distance
```

The live engine calculates protection from the **actual filled entry price** and actual position quantity.

Runtime diagnostics report:

```
Entry Price
ATR
SL Price %
SL ROI %
TP1 Price %
TP1 ROI %
TP2 Price %
TP2 ROI %
```

## Max Open Trades

The current execution coordinator is a **single-symbol net-position engine**.

Therefore:

```
Max Open Trades > 1
        ↓
normalized safely
        ↓
1 net position per bot/symbol
```

This does **not** claim support for two independent same-symbol positions.

## Crypto backtester

`UniversalFuturesBot_CRYPTO_BACKTESTER.py` is the R5 research simulator.

It supports the strategy-side contract including:

- completed-candle signals
- next-candle-open entry simulation
- Evidence-family decisions
- MTF
- divergence
- Volume/S/R
- ATR Dynamic SL/TP
- risk sizing
- cooldown
- drawdown
- loss streak
- post-SL opposite lock
- TP1 partial close
- TP1 break-even
- Grid modes
- conservative same-bar ambiguity handling

Backtesting is not a substitute for exchange demo validation.

## Forex / MT5

`UniversalForexBot_MT5.py` is the self-contained R5 MT5 production engine.

It includes:

- MT5 execution
- broker lot/price rules
- MT5-native account handling
- Evidence-family strategy
- ATR Dynamic protection
- post-SL lock
- recovery/checkpoint behavior
- spread/session/news/correlation protections inherited from the audited MT5 engine

The Forex backtester loads the clean production Forex engine rather than a historical V8.4.0 source file.

## Configuration

Current configuration schema:

```
CONFIG_SCHEMA_VERSION = 9
```

Existing saved profiles remain authoritative. Missing R5 fields are populated with safe defaults.

Important persisted R5 fields include:

- `max_open_trades`
- `use_atr_sl`
- `atr_sl_mult`
- `atr_tp1_mult`
- `atr_tp2_mult`
- Evidence-family settings

## Running

### Crypto

```
py -3.14 UniversalFuturesBot_CRYPTO.py
```

### Crypto backtester

```
py -3.14 UniversalFuturesBot_CRYPTO_BACKTESTER.py
```

### Forex / MT5

```
py -3.14 UniversalForexBot_MT5.py
```

### Forex backtester

```
py -3.14 UniversalForexBot_MT5_BACKTESTER.py
```

Install dependencies from `requirements.txt` first.

## Safety

- Use exchange demo/testnet or MT5 paper/demo first.
- Do not treat backtest results as a guarantee of live execution.
- Verify actual fills, protection orders, broker/exchange trigger behavior, partial fills, reconnects and recovery before live deployment.
- Never commit API keys, passwords or tokens.

## Release documentation

- [Crypto R5 release notes](docs/CRYPTO_R5_RELEASE_NOTES.md)
- [Forex R5 release notes](docs/FOREX_R5_RELEASE_NOTES.md)
- [Changelog](CHANGELOG.md)

## User manuals

The repository now includes three **complete, self-contained V8.4.2-R5 manuals**. Each manual contains the full Crypto + Forex/MT5 + Backtester reference; the edition title only identifies its primary focus.

- [Complete Crypto Edition](docs/USER_MANUAL_V8_4_2_R5_CRYPTO.md)
- [Complete Forex / MT5 Edition](docs/USER_MANUAL_V8_4_2_R5_FOREX_MT5.md)
- [Complete Backtester Edition](docs/USER_MANUAL_V8_4_2_R5_BACKTESTER.md)

The manuals document every R5 indicator family, indicator purpose, major options, signal modes, Evidence-family logic, risk/protection controls, Grid modes, live execution concepts, Forex news/session/correlation controls, and backtesting rules.

## Versioning policy

The production root uses stable filenames. Do **not** create files such as:

```
*_V8_4_2_R6.py
*_FINAL2.py
*_AUDITED_R3.py
*_HARDENED_R4.py
```

For a new release:

1. Update the current production source.
2. Update the internal `APP_VERSION` / `AUDIT_BUILD`.
3. Update tests.
4. Update `CHANGELOG.md`.
5. Tag the release in Git.

That keeps the working tree understandable while Git history and releases retain previous versions.
