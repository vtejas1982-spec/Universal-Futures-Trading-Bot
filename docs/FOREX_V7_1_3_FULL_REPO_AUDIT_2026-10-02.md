# Forex MT5 V7.1.3 — Full GitHub Repository Audit
Date: 2026-10-02

## Repository
- Repository: `vtejas1982-spec/Universal-Futures-Trading-Bot`
- Default branch: `main`
- Connected GitHub account has admin/maintain/push access.
- This is the only repository exposed by the connected GitHub account that matches the current project. No separate older Forex repository is visible.

## Sources audited
- `UniversalForexBot_MT5.py` — canonical Forex production filename.
- `UniversalForexBot_MT5_V7_1_3_AUDITED.py` — supplied V7.1.3 artifact.
- `UniversalForexBot_MT5_V7.1.2_LOW_MEMORY.py` — low-memory reference.
- `UniversalForexBot_MT5_BACKTESTER.py`
- `tests/test_forex_v713_audit.py`
- Forex documentation under `docs/`.

## Supplied-file SHA-256
- V7.1.3 audited: `b113440cc1e75d15ee167f0938d2e0c0b9be061341c21a6cd2576c298bb42baf`
- V7.1.2 low-memory: `da94960caf0e2eccdb280816efd5236a61254f5ad5f608ebcd4cd9d1afdf76c9`

## Static validation
- V7.1.3 AST parse: PASS
- V7.1.3 py_compile: PASS
- V7.1.2 AST parse: PASS
- V7.1.2 py_compile: PASS
- StrategyEngine extraction/smoke: PASS
- Randomized council regression: 30,000 cases, 0 simultaneous BUY+SELL results.
- Opposing-qualified-family 2F fallback regression: PASS; fallback refused to fire against an opposing qualified family.

## Safety contracts verified
- BUY+SELL ambiguity is explicitly blocked with `AMBIGUOUS_CANDLE`.
- AI council exposes `split_council` and blocks split outcomes.
- MT5-native `symbol_info`, `symbol_info_tick`, `positions_get`, and `order_send` paths are present.
- Broker volume min/max/step handling and step-safe rounding are present.
- Minimum-size TP split has a whole-position-at-TP1 path.
- Break-even modifies and verifies broker SL and retries once; original SL is retained if verification fails.
- Startup risk validation checks TP ordering and risk against daily-drawdown/emergency thresholds.
- Low-memory resource guard, active-engine limits, scanner preflight limits, kill-switch latch, profile state, and capital-authority state are present.

## Repository hygiene finding
The shipped Forex source still contains a legacy CCXT/futures implementation block. The active Forex path is overridden later by MT5-native bindings and explicitly rejects non-MT5 exchange selection, so this finding is about dead-code hygiene and maintenance rather than evidence that the active Forex runtime currently uses CCXT.

Residual examples include:
- compatibility import of `ccxt`;
- legacy futures exchange builder/symbol lookup;
- legacy BYBIT/BINANCE account-mode branches;
- legacy `self.exchange.fetch_ticker(...)` market-price path.

This should be removed in a dedicated cleanup release after regression testing, not blindly deleted during a version synchronization.

## Repository synchronization
- The canonical production filename is already V7.1.3-compatible in the repository.
- The V7.1.3 audited artifact is already present.
- The V7.1.2 low-memory reference is already present.
- The Forex V7.1.3 contract test was hardened to run 30,000 randomized council cases and explicitly verify split-council no-trade behavior.
- The audit document is synchronized with these findings.

## Runtime limitation
No live MetaTrader 5 terminal/broker session is available in this audit environment. No live order/fill/slippage/filling-mode behavior is claimed as verified. Demo validation remains required before live deployment.

## Old-repository request
The active repository must not be deleted: it contains the current Crypto and Forex project history and is the only matching repository visible to the connected account. A separate old repository could not be identified safely, so no destructive repository deletion was performed.

## Final status
- Source integrity: PASS
- Council safety contract: PASS
- MT5 contract presence: PASS
- Low-memory architecture presence: PASS
- Test contract: UPDATED
- Repository hygiene: ACTION REQUIRED — remove dead CCXT/futures block in a controlled cleanup release
- Live MT5 validation: PENDING
