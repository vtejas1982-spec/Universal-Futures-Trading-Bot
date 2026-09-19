# Universal Futures Trading Bot V8

Multi-exchange cryptocurrency futures trading bot with a Tkinter desktop GUI.

## Current V8 build

**UniversalFuturesBot_V8_NEUTRAL_GRID_AUTO_DIRECTION_ALL_STRATEGIES_FINAL_AUDITED_GRID_DUPLICATE_FIXED.py**

This build includes the audited Grid duplicate-order synchronization fix.

### Main capabilities

- Multi-exchange futures execution through CCXT
- Completed-candle strategy evaluation
- Supertrend, EMA, EMA Cross, MACD, RSI, Bollinger Bands, Stochastic
- VWAP, VWAP Delta, Volumatic VIDYA, NWE
- Liquidity Swings, Trendline Breakout, Multi-Timeframe confirmation
- Volume, ADX and ATR directional modules
- DIRECT_SHOT / SCORE strategy execution
- LONG_GRID / SHORT_GRID / NEUTRAL_GRID
- NEUTRAL_GRID automatic direction changes
- Grid basket TP and global Grid SL
- Grid exposure and drawdown controls
- Global daily drawdown and emergency capital-loss protection
- Grid order synchronization and individual order-status verification
- Telegram alerts, dashboard and CSV trade logging

## Grid duplicate-order fix

The V8 Grid engine verifies tracked order IDs individually instead of trusting an incomplete open-order snapshot. Bybit open-order retrieval uses an explicit page size, and Grid cancellation/protection checks verify individual order status. This is intended to prevent repeated recreation of Grid levels when an exchange response does not contain every open order.

## NEUTRAL_GRID

- **SUPERTREND**: follows the current Supertrend direction.
- **SCORE**: uses the complete enabled Section 3 directional-module score.
- **OFF**: uses the complete Section 3 score logic in the supplied V8 build.

When direction changes, the engine cancels old pending Grid entries, handles existing Grid inventory, verifies flat state before an opposite direction, resets the Grid center, and places the new side.

## Risk notice

This is trading software for development, testing, research and educational use. It is **not financial advice and does not guarantee profits**. Cryptocurrency futures and leverage can cause rapid losses. Use demo/testnet accounts first and understand exchange-specific order, account-mode and liquidation risks.

## Credentials

Never commit exchange API keys, API secrets, Telegram tokens, passwords, or private configuration files.

Keep local credential/config files outside Git. See `SECURITY.md` and `.gitignore`.

## Supported exchanges in this V8 design

Bybit, Binance, Gate.io, Bitget and WEEX. KuCoin is not included in this V8 build.

## Development

Python 3.13/3.14 is recommended for the current Windows development environment.

Install dependencies:

    py -m pip install -r requirements.txt

Run:

    py UniversalFuturesBot_V8_NEUTRAL_GRID_AUTO_DIRECTION_ALL_STRATEGIES_FINAL_AUDITED_GRID_DUPLICATE_FIXED.py

Use demo/testnet credentials before live trading.

## Status

The supplied V8 Grid duplicate-order synchronization fix was syntax-checked before publication. Exchange-side execution should still be tested in a controlled environment because exchange APIs, account modes, order modes and permissions can vary.

## License

MIT. See LICENSE.
