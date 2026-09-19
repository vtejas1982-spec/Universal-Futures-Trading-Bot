# Contributing to Universal Futures Trading Bot

Thank you for helping improve the project.

## What contributions are useful?

- Exchange integration testing
- Grid-engine testing
- Strategy/backtesting work
- Bug fixes
- Documentation
- GUI improvements
- Performance improvements
- Reproducible bug reports

## Before opening an issue

Please test against the latest `main` branch where practical.

Include:
- Exchange and market type
- Symbol
- Strategy/Grid mode
- Relevant non-secret settings
- Python version
- Reproduction steps
- Relevant log output

**Never include API keys, API secrets, Telegram tokens, passwords or private account information.**

## Pull requests

Keep changes focused and explain:
1. What changed
2. Why it changed
3. How it was tested
4. Any exchange-specific limitations

For trading/execution changes, prefer demo/testnet validation before describing behavior as exchange-tested.

## Development setup

```powershell
py -m pip install -r requirements.txt
py UniversalFuturesBot_V8_NEUTRAL_GRID_AUTO_DIRECTION_ALL_STRATEGIES_FINAL_AUDITED_GRID_DUPLICATE_FIXED.py
```

The project is intended for development, research, testing and educational use. Contributions should not claim guaranteed trading performance.
