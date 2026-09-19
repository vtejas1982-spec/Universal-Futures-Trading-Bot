# Universal Futures Trading Bot V8

A Python/Tkinter multi-exchange cryptocurrency futures trading bot for development, testing, research and educational use.

> **Important:** This project is not financial advice and does not guarantee profits. Cryptocurrency futures and leverage can cause rapid losses. Start with demo/testnet environments and understand your exchange's order, account-mode and liquidation rules.

## 🚀 V8 at a glance

**Current build**

`UniversalFuturesBot_V8_NEUTRAL_GRID_AUTO_DIRECTION_ALL_STRATEGIES_FINAL_AUDITED_GRID_DUPLICATE_FIXED.py`

The current V8 build combines configurable directional strategies with advanced Grid execution, including the audited Grid duplicate-order synchronization fix.

### Highlights

- Multi-exchange futures execution through CCXT
- Completed-candle strategy evaluation
- **17 configurable directional modules**
- DIRECT_SHOT and SCORE strategy execution
- LONG_GRID / SHORT_GRID / NEUTRAL_GRID
- NEUTRAL_GRID automatic direction changes
- Grid basket TP and global Grid SL
- Grid exposure and drawdown controls
- Global daily drawdown and emergency capital-loss protection
- Individual Grid order-status verification
- Telegram alerts
- Dashboard and CSV trade logging

## 🖥️ V8 GUI Preview

The screenshots below show the actual V8 desktop interface, including connection, market, strategy/indicator, Grid, risk/SL-TP, and alerts/dashboard configuration.

![Universal Futures Trading Bot V8 GUI](docs/screenshots/V8_GUI_Screenshots_Overview.jpg)

## 📖 User Manual

**[Read the Universal Futures Bot V8 User Manual (PDF)](docs/UniversalFuturesBot_V8_User_Manual.pdf)**

The manual covers architecture, connection/API setup, market settings, all 17 directional indicators and parameters, signal modes, Grid modes, NEUTRAL_GRID automatic direction, Grid TP/SL, exposure and drawdown controls, normal strategy risk settings, alerts, dashboard, logging, testing and troubleshooting.

## 🧠 17 directional modules

The V8 Section 3 strategy engine can use:

1. Supertrend
2. EMA
3. EMA Cross
4. MACD
5. RSI
6. Bollinger Bands
7. Stochastic
8. VWAP
9. VWAP Delta
10. Volumatic VIDYA
11. NWE
12. Liquidity Swings
13. Trendline Breakout
14. Multi-Timeframe
15. Volume
16. ADX
17. ATR

The Grid SCORE logic uses the same enabled Section 3 directional modules and their configured parameters.

## 📊 Strategy modes

### DIRECT_SHOT

Direct strategy execution using the configured signal engine.

### SCORE

Combines directional module votes into a bullish/bearish score and requires the configured minimum score.

### Grid modes

- **LONG_GRID** — buy-side Grid
- **SHORT_GRID** — sell-side Grid
- **NEUTRAL_GRID** — automatic direction based on the configured direction source

## 🔄 NEUTRAL_GRID automatic direction

NEUTRAL_GRID can automatically change Grid direction:

- **SUPERTREND** — follows the current Supertrend direction.
- **SCORE** — uses the complete enabled Section 3 directional-module score.
- **OFF** — uses the complete Section 3 score logic in the supplied V8 build.

When direction changes, the Grid engine cancels old pending entries, handles existing Grid inventory, verifies the position state before switching sides, resets the Grid center and places the new side.

LONG_GRID and SHORT_GRID remain explicitly directional and are not automatically switched by this mechanism.

## 🛠️ Grid duplicate-order fix

One of the important V8 engineering fixes addresses a Grid synchronization problem.

The engine does not rely only on an incomplete open-order snapshot to decide whether a tracked Grid order still exists. It:

1. Retrieves Bybit open orders with an explicit page size.
2. Tracks locally managed order IDs.
3. Checks missing tracked IDs individually with order-status queries.
4. Retains orders when their status is still open or ambiguous.
5. Removes or marks orders according to their verified exchange status.
6. Verifies managed cancellations individually.

This is intended to prevent repeated recreation of Grid levels when an exchange response does not contain every open order.

## 🏗️ Architecture

The project is organized around a desktop GUI and a multi-exchange execution engine.

High-level flow:

```text
Tkinter GUI
    │
    ├── Market / Strategy Configuration
    ├── Indicator Parameters
    ├── Risk & Grid Configuration
    └── Monitoring / Dashboard
            │
            ▼
     Strategy Engine
            │
            ├── Directional Modules
            ├── SCORE / DIRECT_SHOT
            └── Grid Engine
                    │
                    ▼
                 CCXT
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
      Bybit      Binance      Other supported exchanges
```

The current design supports Bybit, Binance, Gate.io, Bitget and WEEX. KuCoin is not included in this V8 build.

## ⚡ Quick start

### 1. Clone the repository

```bash
git clone https://github.com/vtejas1982-spec/Universal-Futures-Trading-Bot.git
cd Universal-Futures-Trading-Bot
```

### 2. Install dependencies

Python 3.13/3.14 is recommended for the current Windows development environment.

```powershell
py -m pip install -r requirements.txt
```

### 3. Configure credentials locally

Never commit exchange API keys, API secrets, Telegram tokens, passwords or private configuration files.

Keep credentials outside Git. See:

- [SECURITY.md](SECURITY.md)
- [.gitignore](.gitignore)

### 4. Run the bot

```powershell
py UniversalFuturesBot_V8_NEUTRAL_GRID_AUTO_DIRECTION_ALL_STRATEGIES_FINAL_AUDITED_GRID_DUPLICATE_FIXED.py
```

### 5. Test safely first

Use demo/testnet credentials before live trading. Verify exchange account mode, position mode, leverage, symbol rules, order types and permissions before using real funds.

## 🔬 Development and testing

The current published V8 Grid duplicate-order synchronization fix was syntax-checked before publication.

Exchange-side behavior should still be tested in a controlled environment because exchange APIs, account modes, order modes, permissions and exchange-side limits can vary.

Useful areas for future testing include:

- Exchange integration tests
- Grid order lifecycle tests
- Protection-order reconciliation tests
- Backtesting
- Strategy performance reporting
- Configuration import/export

## 🗺️ Roadmap

### V8 — current

- [x] 17 directional modules
- [x] DIRECT_SHOT / SCORE execution
- [x] LONG_GRID / SHORT_GRID / NEUTRAL_GRID
- [x] NEUTRAL_GRID automatic direction
- [x] Grid TP / global Grid SL
- [x] Grid exposure and drawdown controls
- [x] Grid duplicate-order synchronization fix
- [x] User manual
- [x] Security guidance

### Future work

- [ ] Expanded automated exchange integration tests
- [ ] Dedicated Grid-engine unit-test suite
- [ ] Backtesting engine
- [ ] Strategy performance reports
- [ ] Configuration profiles/import-export
- [ ] Additional documentation and examples
- [ ] More contributor-friendly modularization

## 🤝 Contributing

Contributions, bug reports, documentation improvements and testing feedback are welcome.

Before opening an issue:

1. Confirm the problem on the latest `main` version.
2. Include the exchange, symbol, mode and relevant configuration.
3. Remove API keys, secrets, Telegram tokens and other private information from logs.
4. Include reproducible steps where possible.

For code contributions, keep changes focused and explain the behavior being changed.

## 🔐 Security

**Never commit secrets.**

Do not publish:

- Exchange API keys
- Exchange API secrets
- Telegram bot tokens
- Passwords
- Private configuration files
- Personal account information

See [SECURITY.md](SECURITY.md) for the project's security guidance.

## 📁 Repository structure

```text
Universal-Futures-Trading-Bot/
├── UniversalFuturesBot_V8_NEUTRAL_GRID_AUTO_DIRECTION_ALL_STRATEGIES_FINAL_AUDITED_GRID_DUPLICATE_FIXED.py
├── README.md
├── requirements.txt
├── LICENSE
├── SECURITY.md
└── docs/
    ├── UniversalFuturesBot_V8_User_Manual.pdf
    └── screenshots/
        └── V8_GUI_Screenshots_Overview.jpg
```

## 📜 License

MIT. See [LICENSE](LICENSE).
