# CRYPTO FUTURES — V8.4.2-AI-AGENT-R6.8.28 USER MANUAL

**Release:** R6.8.28  
**Date:** 2026-10-01  
**Current engine:** `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28_LINUX_RSS_VPS_MEMORY_HARDENED_FULL_AUDIT.py`  
**Config schema:** 67  
**Signal mode:** AI_AGENT

> This is the current R6.8.28 operating guide. The detailed indicator/protection reference from the previous R6.7 manual is preserved below under **Historical / inherited reference**. Where an older section names an older release or filename, the R6.8.28 release contract in Sections 1–12 takes precedence.

---

## 1. R6.8.28 release contract

R6.8.28 is the low-RAM Linux/VPS hardening release for the two-stage live scanner.

| Area | R6.8.28 behavior |
|---|---|
| Crypto engine | `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28_LINUX_RSS_VPS_MEMORY_HARDENED_FULL_AUDIT.py` |
| Config schema | 67 |
| Signal mode | AI_AGENT |
| Scanner | Two-stage discovery → preflight → promotion → normal trade child |
| Scanner children | Sequential; temporary preflight children are not retained |
| Scanner direct orders | **0** |
| Timeframe | Selected scanner timeframe is authoritative for OHLCV/ATR/momentum discovery and child strategy analysis |
| Ticker liquidity | 24h ticker liquidity remains timeframe-independent |
| Leverage | AUTO or MANUAL; AUTO is bounded by exchange maximum and the safety envelope |
| Quantity | AUTO or FIXED; existing risk/quantity guards remain authoritative |
| Trading capital | Optional hard strategy-capital allocation; child preflight/promotion inherits the allocation |
| Memory | Linux RSS diagnostics + low-memory scanner admission guard |
| Target deployment | Low-RAM Linux/Oracle VPS |
| Live status | Windows/Bybit Demo startup + scanner discovery validated; long-run Oracle VPS memory validation remains pending |

R6.8.28 does **not** claim profitability or guarantee live execution.

---

## 2. What changed in R6.8.28

### Linux/VPS memory hardening

R6.8.28 adds:

- Linux process RSS measurement using `/proc/self/status`.
- `/proc/self/statm` fallback for RSS measurement.
- RAM and swap diagnostics.
- RSS delta tracking.
- A low-memory admission guard before creating temporary scanner children.
- Fail-closed scanner-child admission if required memory telemetry cannot be obtained.
- A single authoritative 60-second Hub memory diagnostic.
- Explicit scanner-child exchange disposal.
- Tk callback cancellation during child disposal.
- Hub callback purge for retired children.
- Garbage collection after scanner-child cleanup.
- Bounded scanner/UI structures.

### Important

The memory guard does **not** change the AI signal or lower safety thresholds. It simply prevents another temporary scanner child from being created when the VPS is under the configured memory-safety condition.

---

## 3. Live Pair Scanner — how it works

The scanner is deliberately **not** a second order engine.

### Stage A — discovery

The scanner:

1. Gets the eligible active linear USDT perpetual/swap universe.
2. Applies the fast liquidity/market-data filter.
3. Builds the selected OHLCV cohort using the configured scanner timeframe.
4. Calculates the fast ranking inputs.
5. Produces a bounded shortlist.
6. Queues candidates sequentially.

Example runtime structure:

```
ELIGIBLE UNIVERSE
      ↓
FAST TICKER / LIQUIDITY FILTER
      ↓
SELECTED-TIMEFRAME OHLCV COHORT
      ↓
FAST RANKING
      ↓
SHORTLIST
      ↓
SEQUENTIAL PREFLIGHT
```

### Stage B — normal strategy preflight

For one candidate at a time:

```
SHORTLIST CANDIDATE
      ↓
TEMPORARY CHILD
      ↓
NORMAL STRATEGY / AI PIPELINE
      ↓
SIGNAL
      ↓
LEVERAGE / LIQUIDATION SAFETY
      ↓
COST GATE
      ↓
RISK / QUANTITY
      ↓
EXECUTION QUALITY
      ↓
PROMOTE ONLY IF QUALIFIED
```

**No exchange order is allowed during preflight.**

If the candidate fails strategy/safety requirements, the temporary child is cleaned up and the scanner proceeds to the next candidate.

If it qualifies, the child is promoted into the normal trading path.

### Scanner safety contract

The scanner parent:

- has no exchange symbol position;
- does not directly call `create_order()`;
- does not bypass normal protection;
- does not bypass the normal kill switch;
- does not bypass symbol ownership;
- does not bypass one-way position verification;
- does not bypass leverage validation;
- does not bypass risk sizing;
- does not bypass execution-quality checks.

---

## 4. Scanner timeframe authority

The selected scanner timeframe is authoritative.

For example, if the GUI scanner timeframe is **5m**:

- scanner OHLCV discovery uses 5m;
- scanner ATR/momentum discovery uses 5m;
- preflight strategy analysis uses 5m;
- promoted child strategy analysis uses 5m.

The 24-hour ticker volume/liquidity filter is not a candle-timeframe measurement and therefore remains timeframe-independent.

Runtime confirmation uses a message equivalent to:

```
SCANNER TIMEFRAME AUTHORITY: 5m
All scanner OHLCV/ATR/momentum discovery and child strategy analysis
use the selected timeframe
```

---

## 5. Trading Capital Authority

R6.8.28 supports a strategy-capital allocation boundary separate from the exchange wallet balance.

Example:

- Exchange balance = **100 USDT**
- Trading Capital Limit = **60 USDT**
- Effective Strategy Capital = **60 USDT**

When enabled, the strategy uses the effective allocation for:

- risk sizing;
- fixed-quantity risk validation;
- notional/utilization calculations;
- grid sizing;
- scanner child sizing;
- capital-pool calculations where applicable.

The exchange's actual wallet balance remains available for **margin/liquidation safety checks**.

### Runtime authority

The scanner parent propagates the same allocation to temporary preflight and promoted children.

A correct runtime log should show:

```
SCANNER CAPITAL AUTHORITY:
Enabled=True
ConfiguredCap=60.0000 USDT
EffectiveStrategyCapital=60.0000 USDT
```

and the child should show:

```
TRADING CAPITAL AUTHORITY:
AccountBalance=...
ConfiguredCap=60.0000 USDT
EffectiveStrategyCapital=60.0000 USDT
```

If the allocation is disabled, effective strategy capital equals the available account balance.

---

## 6. AUTO leverage

AUTO leverage does **not** simply select the exchange maximum.

The scanner considers:

- exchange market maximum leverage;
- ATR/stop distance;
- liquidation safety buffer;
- the existing leverage safety envelope;
- the selected symbol's market characteristics.

Therefore different pairs can receive different AUTO leverage values.

Example concept:

```
Exchange max = 75x
AUTO result   = 14x
```

The exchange maximum is a ceiling, not a target.

For MANUAL leverage, the selected leverage remains authoritative. Unsafe conditions are rejected rather than silently lowering the user's requested leverage.

---

## 7. AI-Agent / Evidence-Family strategy

R6.8.28 retains the deterministic AI-Agent architecture.

Directional evidence families:

- **TREND**
- **MOMENTUM**
- **FLOW**
- **STRUCTURE**

Regime/quality gates include:

- ATR
- ADX
- completed-candle requirements
- MTF where enabled
- configured participation/confidence/edge requirements.

The AI-Agent is a deterministic rule engine. It is not an external LLM.

### Important scanner behavior

The scanner ranking score is **not** the final trade signal.

A high scanner score can still be rejected by the full AI strategy.

The scanner therefore follows:

```
FAST RANKING ≠ TRADE APPROVAL
```

The full normal strategy remains authoritative.

---

## 8. Execution-quality profiles

The selected execution profile controls the existing market-quality gates.

### ADAPTIVE

Runtime examples:

- Spread ≤ 0.35%
- Slippage ≤ 0.20%
- Depth ≥ 1x
- Candle drift ≤ 0.75%

### STRICT

Runtime examples:

- Spread ≤ 0.25%
- Slippage ≤ 0.20%
- Depth ≥ 2x
- Candle drift ≤ 0.75%

The execution profile does not replace the AI strategy. It only determines the execution-quality limits applied after the strategy qualifies.

---

## 9. Memory diagnostics on a Linux VPS

R6.8.28 is specifically hardened for a low-RAM Linux deployment.

The Hub periodically reports memory information such as:

```
HUB MEMORY DIAGNOSTIC:
RSS=... MB
AvailableRAM=... MB
Swap=... MB
RSSDelta60s=...
Engines=...
UIQ=...
```

### What to monitor during the VPS test

For the planned long-run test, record:

1. RSS over time.
2. `RSSDelta60s`.
3. Available RAM.
4. Swap usage and whether it keeps increasing.
5. Temporary scanner child count.
6. UI queue size.
7. Low-memory guard events.
8. Whether scanner cycles continue after repeated candidate rejection.
9. Whether retired child engines disappear after cleanup.
10. Whether the process remains responsive.

### Interpretation

A single RSS increase is not by itself proof of a leak. The important measurement is whether RSS continues to grow without returning/stabilizing after scanner children are cleaned up.

The Oracle VPS long-run test is therefore the final validation for this release's memory objective.

---

## 10. Scanner operating modes

### SCAN_ONLY

Use when validating:

- universe discovery;
- liquidity filtering;
- timeframe propagation;
- ranking;
- candidate selection;
- memory behavior.

No AUTO_TRADE order path should be used.

### AUTO_TRADE

The scanner may promote a qualified candidate into the normal trading engine.

Before an actual order, the normal engine must still pass:

```
AI / SIGNAL
→ DIRECTION
→ LEVERAGE
→ LIQUIDATION BUFFER
→ COST GATE
→ RISK / QTY
→ EXECUTION QUALITY
→ ORDER
→ ACTUAL FILL
→ PROTECTION
```

---

## 11. Shutdown and scanner-child lifecycle

R6.8.28 retains the hardened scanner shutdown sequence.

A temporary child is not considered safely finished merely because its Python worker returned.

The cleanup contract verifies:

- worker termination;
- stop-cleanup state;
- kill-switch completion;
- flat exchange state where applicable;
- no residual open orders;
- exchange transport disposal;
- pending UI callback cleanup;
- Hub callback purge;
- object release and garbage collection.

The scanner then proceeds to the next candidate.

---

## 12. Protection contract

The existing actual-fill protection contract remains authoritative.

After a real entry:

1. Obtain actual filled entry price.
2. Obtain actual position quantity.
3. Calculate/resolve SL and TP.
4. Submit required protection orders.
5. Verify exchange acknowledgement.
6. Verify active protection.
7. Continue only when the position is protected.

The GUI setting being ON is not proof that the exchange-side protection exists.

Protection failure remains fail-closed.

---

## 13. Capital and position limits are different

Do not confuse:

**Trading Capital Limit**

with:

**Max Open Positions**

and:

**Risk Per Trade**

They control different things.

Example:

- Account balance: 100 USDT
- Strategy capital: 60 USDT
- Max positions: 3
- Risk per trade: 0.35%

The 60 USDT is the strategy capital boundary; Max Positions limits simultaneous positions; Risk Per Trade controls the risk calculation inside the strategy.

---

## 14. Recommended R6.8.28 VPS validation procedure

Before Live:

### Phase 1 — startup

Confirm:

- Linux VPS starts successfully.
- Correct Python environment.
- Correct exchange credentials.
- Bybit Demo/Testnet mode.
- Correct profile.
- Correct timeframe.
- Correct trading capital.

### Phase 2 — scanner

Confirm:

- scanner starts;
- eligible universe count appears;
- fast filter appears;
- OHLCV cohort appears;
- shortlist appears;
- only sequential temporary preflight children are created;
- rejected children are cleaned up.

### Phase 3 — memory

Run for several hours.

Record:

```
Time
RSS
Available RAM
Swap
RSSDelta60s
Engines
UIQ
Low-memory events
Scanner cycle
```

### Phase 4 — trade

Only after scanner/memory behavior is understood:

- allow AUTO_TRADE on Demo;
- wait for a genuine qualified candidate;
- verify the normal entry pipeline;
- verify actual-fill protection;
- verify position quantity;
- verify SL/TP;
- verify shutdown/recovery.

### Phase 5 — Live

Do not treat static compilation, scanner discovery, or a short VPS run as proof of live safety.

---

## 15. Repository / release status

The GitHub repository documentation identifies R6.8.28 as the current release.

The obsolete root crypto engines were removed.

Historical release notes remain under `docs/`.

**Important repository audit finding:** the repository currently does **not** contain the complete R6.8.28 Python source file at the expected root path. Therefore GitHub should not yet be treated as a complete source backup of the R6.8.28 engine.

The local validated source remains:

`UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28_LINUX_RSS_VPS_MEMORY_HARDENED_FULL_AUDIT.py`

This should be synchronized to the repository before relying on GitHub as the canonical source.

---

## 16. Current validation status

| Check | Status |
|---|---|
| AST parse | PASS |
| Python compile | PASS |
| Scanner direct order path | 0 |
| Stale `self.profile_id` references | 0 |
| Config schema | 67 |
| Windows / Bybit Demo startup | PASS |
| Scanner discovery | PASS |
| Timeframe authority | PASS |
| Capital authority propagation | PASS |
| Transient preflight persistence avoidance | PASS |
| Linux long-run RSS validation | **PENDING** |
| Complete R6.8.28 source in GitHub | **PENDING** |

---

## 17. Historical / inherited indicator and protection reference

The detailed R6.7 strategy reference remains applicable to unchanged strategy components, including:

- TREND / MOMENTUM / FLOW / STRUCTURE families;
- Supertrend;
- EMA / EMA Cross;
- MACD;
- RSI;
- Stochastic;
- VWAP / VWAP Delta;
- Volume / Volume S/R;
- Liquidity Swings;
- Trendline Breakout;
- MTF;
- Divergence;
- ATR / ADX;
- actual-fill SL/TP;
- TP1/TP2 protection;
- break-even;
- Grid controls;
- backtesting limitations.

For R6.8.28, the new scanner/timeframe/capital/memory sections above take precedence over older release-specific filenames and schema numbers.

---

## 18. Safety checklist

Before any Live deployment:

- use Bybit Demo/Testnet first;
- verify the selected timeframe;
- verify AUTO/MANUAL leverage mode;
- verify Max Open Positions;
- verify Trading Capital Limit;
- verify Risk Per Trade;
- verify execution-quality profile;
- verify AI-Agent requirements;
- verify actual exchange-side SL/TP after a fill;
- verify the kill switch;
- verify scanner shutdown;
- verify Linux VPS RSS and swap behavior;
- never commit API keys, passwords or tokens.

**R6.8.28 is an engineering hardening release, not a profitability guarantee. Futures trading can result in substantial loss.**

---

# Historical / inherited reference

# CRYPTO FUTURES — V8.4.2-AI-AGENT-R6.7 USER MANUAL

**Release:** R6.7  
**Date:** 2026-09-29  
**Live engine:** `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py`

This R6.7 manual update focuses on the protection/execution contract and the full engine audit. Strategy modules and unchanged GUI controls retain the R6.6 definitions unless listed here.

## 1. R6.7 release contract

| Item | R6.7 |
|---|---|
| Crypto live engine | `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py` |
| Config schema | 23 |
| Runtime schema | 24 |
| AI preset | `AI_AGENT_RECOMMENDED_R6.7` |
| Signal mode | AI_AGENT |
| Default timeframe | 15m |
| Default leverage | 5x |
| Max Open Trades | 1 net position |
| TP quantity mode | PERCENT_% |
| TP1 close | 50% |
| TP2 close | 50% |
| TP1 break-even | ON |
| ATR TP multipliers | ON for new profiles |
| ATR SL multiplier | 1.8x for new profiles |

Existing saved profiles remain authoritative.

## 2. TP1 / TP2 contract

R6.7 uses the **actual filled position quantity**, not the requested entry quantity, for protection.

For the default 50/50 configuration:

- Position = 5,000 units
- TP1 = 2,500 units
- TP2 = 2,500 units
- SL = 5,000 units

Exchange precision is applied before orders are submitted.

### Single-TP mode

If only TP1 or only TP2 is enabled, that enabled target closes the full remaining position. The disabled target's close percentage is not used to manufacture a split.

## 3. Bybit protection orders

For Bybit, R6.7 creates independent conditional market exits.

### SL

- Close side is opposite the position.
- SL quantity = 100% of actual position.
- `triggerDirection`: 2 for LONG SL, 1 for SHORT SL.
- `triggerBy`: LastPrice.
- `reduceOnly`: true.
- `closeOnTrigger`: true.
- `positionIdx`: 0.

### TP1 / TP2

- Close side is opposite the position.
- TP quantity follows the configured split.
- `triggerDirection`: 1 for LONG TP, 2 for SHORT TP.
- `triggerBy`: LastPrice.
- `reduceOnly`: true.
- `closeOnTrigger`: true.
- `positionIdx`: 0.

The GUI setting being ON is not considered proof of protection. The exchange order must be acknowledged and then verified.

## 4. What you must see on Bybit Demo

Immediately after a new test position is opened, open **Open Orders → Conditional**.

For normal TP1/TP2 operation you should see:

1. **SL** — close the full position.
2. **TP1** — close 50%.
3. **TP2** — close 50%.

All should be **Untriggered** until their trigger conditions occur.

If only SL is present while TP1/TP2 are enabled, treat the trade as a protection failure and stop the bot. R6.7 is designed to log the exchange acknowledgement/rejection so the exact failure can be diagnosed.

## 5. R6.7 protection log

A successful order path should contain messages similar to:

```
PROTECTION TARGETS ...
SL SUBMIT ...
SL ACK ...
TP1 SUBMIT ...
TP1 ACK ...
TP2 SUBMIT ...
TP2 ACK ...
SL VERIFIED ACTIVE ...
TP1 VERIFIED ACTIVE ...
TP2 VERIFIED ACTIVE ...
PROTECTION VERIFY PASSED ...
```

The ACK line reports order metadata only. API keys and secrets are never included.

## 6. Protection failure behavior

R6.7 creates the protection set in this order:

```
ACTUAL FILL
   ↓
ACTUAL ENTRY + ACTUAL QTY
   ↓
SL
   ↓
TP1
   ↓
TP2
   ↓
VERIFY EACH ORDER
   ↓
POSITION PROTECTED
```

If creation fails part-way through:

- known created protection orders are cancelled;
- the existing safety recovery path cancels remaining bot-symbol orders;
- the unprotected position is closed rather than intentionally continuing without the requested protection set.

## 7. AI-Agent strategy contract

R6.7 keeps the deterministic Evidence-Family AI-Agent architecture.

Families:

- TREND
- MOMENTUM
- FLOW
- STRUCTURE

Regime gates:

- ATR
- ADX

MTF is part of STRUCTURE and is also used as a directional gate.

The AI-Agent is a deterministic rule engine; it is not an external LLM.

### R6.7 AI manager fix

The bounded AI trade manager now receives the actual completed-candle gate state:

- ATR pass/fail
- Volume pass/fail
- ADX pass/fail
- MTF bullish pass/fail
- MTF bearish pass/fail

It no longer re-runs the management decision with all of those gates forced to TRUE.

## 8. Default protection profile

For the R6.7 AI-Agent recommended profile:

- Risk: 0.35% equity
- ATR SL: 1.8x
- ATR TP1: 1.2x SL distance
- ATR TP2: 2.2x SL distance
- TP1: 50%
- TP2: 50%
- TP1 break-even: ON
- Hold-All-Reverse: OFF
- Hold-SL WAIT: OFF
- Grid: OFF
- Max Open Trades: 1

These settings are configuration defaults, not profitability claims.

## 9. Full settings/configuration audit

R6.7 rechecked:

- GUI strategy controls
- Risk controls
- SL/TP controls
- Grid controls
- AI-Agent controls
- Evidence-family settings
- divergence settings
- liquidity settings
- trendline settings
- MTF settings
- profile loading/saving
- configuration migration
- callback bindings
- runtime GUI-variable access
- actual-fill sizing
- protection order ownership
- protection recovery
- kill switch
- worker lifecycle
- single-symbol max-open-position contract

No missing GUI callback binding was found in the audited source.

## 10. Demo validation procedure

Before Live:

1. Use **Bybit Demo/Testnet**.
2. Select the intended bot profile.
3. Verify the symbol shown in the GUI matches the intended Bybit contract.
4. Verify leverage and Max Open Trades.
5. Verify:
   - TP Engine ON
   - TP1 ON
   - TP2 ON
   - TP1 Close 50
   - TP2 Close 50
   - TP1 Break-even ON
6. Start the bot.
7. Wait for one real test entry.
8. Confirm Bybit shows three Conditional orders.
9. Confirm the log shows all three ACKs and all three VERIFIED ACTIVE messages.
10. Let TP1 trigger in Demo and confirm approximately 50% of the actual position closes.
11. Confirm the remaining SL moves to actual entry when TP1 break-even is ON.
12. Confirm TP2 closes the remaining position.

## 11. Important safety note

R6.7 is an engineering hardening release. AST/compile/smoke tests validate code structure and protection contracts; they do not establish profitability, slippage behavior, funding costs, liquidation behavior, or guaranteed live execution.

Use Demo/Testnet validation before Live.

## 12. Related files

- `UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py`
- `BUILD_CRYPTO_AI_AGENT_R6.7_EXE.bat`
- `docs/CRYPTO_AI_AGENT_R6_7_RELEASE_NOTES.md`
- `CHANGELOG.md`
- `CURRENT_RELEASE_MANIFEST.md`


## R6.7 Full-Contract Audit Hotfix — 2026-09-29

The R6.7 engine was re-audited after Demo execution.

### AI-Agent diagnostics

When an entry is rejected, the log now identifies:
- dominant side: BUY / SELL / TIE
- family count and edge
- Trend/Structure requirements
- ATR / Volume / ADX gates
- directional MTF gate, for example MTF_GATE_SELL

Do not interpret the generic Minimum Score field as the AI-Agent entry threshold. In AI_AGENT mode the effective controls are Minimum Families, Edge, Family Confidence, Max Conflicts, Trend requirement and Structure requirement.

### TP configuration validation

Before any new exchange-side position is opened, R6.7 validates:
- TP Quantity Mode = PERCENT_% or FIXED_QTY.
- Two-TP percentage mode uses positive percentages below 100% and totals exactly 100%.
- Fixed TP quantities are positive.
- When ATR TP is enabled with both TP levels active, TP2 ATR multiplier must be greater than TP1.

### Demo verification

For a two-target position, confirm Bybit Conditional orders contain:
1. one full-position SL;
2. one TP1 close order for the configured first split;
3. one TP2 close order for the configured second split.

The R6.7 log should show SUBMIT, ACK and VERIFIED ACTIVE for each required protection order. If any required order is rejected or disappears while the position remains open, the protection reconciliation path reports it and attempts restoration; an inconclusive protection-state check pauses new entries rather than guessing.



## Final audit notes — 2026-09-29

### Volume/SR signal timing
Volume/SR is now explicitly completed-candle only in the live worker. The newest chart/HTF candle is excluded before Volume/SR state calculation, keeping VOL_SR consistent with the other entry modules.

### Protection settings
- If a protection feature is OFF, its unused numeric target is not treated as an active validation requirement.
- ATR SL multiplier is validated when ATR SL is enabled.
- ATR TP1/TP2 multipliers are validated when their corresponding TP levels are enabled.
- With both ATR TP levels ON, TP2 must be farther from entry than TP1.
- The normal protection resolver still owns exactly one SL basis at a time: Hold-SL/WAIT, then ATR, then ROI, then Fallback.
- TP uses ATR multipliers only when ATR TP is enabled; otherwise it uses the configured ROI targets.
- The exchange-side SL protects the full live position; TP1/TP2 are separate reduce-only exits whose quantities account for the actual filled position.


## R6.8 notes — 2026-09-29

- Equity-risk sizing has a conservative 95% Balance x Leverage notional guard.
- Fixed quantity mode fails closed if the requested quantity exceeds that capacity; it is not silently resized.
- AI-Agent blocked diagnostics now show per-family direction and confidence in FAMILY_DETAIL.
- No AI entry threshold was relaxed.
- Existing R6.7 completed-candle Volume/SR, SL/TP protection, TP split and break-even contracts remain active.


