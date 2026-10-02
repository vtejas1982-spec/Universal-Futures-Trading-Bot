# Universal Futures Trading Bot — V7.1 Crypto User Manual

## 1. Release overview
V7.1 is the V8.4.2 Crypto AI-Agent engine line with multi-bot Hub operation, asynchronous Windows scanner preflight, resource governance, global capital authority, hardened TP1/TP2/true-BE protection, scanner ephemeral-profile lifecycle management, and completed Trade History.

**Config schema:** 68  
**Runtime schema:** 25

> Use Bybit Demo/Testnet for validation before any live deployment. This manual documents engine behavior; it does not establish profitability.

## 2. Normal launch
The default launch mode is the **Multi-Bot Hub**. The Hub can host multiple normal `BOT-*` profiles and scanner children.

Use the explicit single-bot/legacy launch mode only when editing or testing a standalone profile.

## 3. Profiles
Normal profiles use names such as:
- `BOT-01`
- `BOT-02`
- `BOT-03`

Scanner children use transient names such as:
- `SCANNER-BOT-01-CT_USDT_USDT-000855`

Scanner children are runtime workers, not permanent user profiles.

## 4. Scanner lifecycle
The live scanner performs discovery and preflight analysis. The scanner itself is not the normal exchange order path.

Flow:

```text
Universe
  -> ticker/liquidity filter
  -> OHLCV cohort
  -> ranked shortlist
  -> external preflight worker
  -> AI/evidence + strategy gates
  -> qualified child
  -> normal child trade engine
  -> exchange order/protection lifecycle
```

Windows heavyweight preflight startup is offloaded to an external worker so the parent Tk GUI remains responsive.

### Temporary profile cleanup
Rejected preflight workers are marked `PREFLIGHT_WORKER` and are eligible for safe deletion after the worker is stopped and no active/recovery state exists.

Startup reconciliation also checks abandoned preflight-worker directories.

Active trade/recovery profiles are protected and are not blindly deleted.

## 5. Resource governance
Windows uses a Hub-level resource governor for:
- available RAM
- current process RSS telemetry
- active engine count
- scanner preflight concurrency

Linux/Oracle VPS protection retains:
- 180 MB available-RAM admission floor
- 240 MB recovery threshold after a low-memory latch
- 780 MB process RSS ceiling
- fail-closed behavior when required telemetry is unavailable

A resource block is not a strategy rejection. The scanner retries when admission becomes available.

## 6. Global capital authority
The Hub supports:
- `OFF / ACCOUNT`
- `GLOBAL_SHARED`
- `INDIVIDUAL`

When enabled, scanner children inherit their parent BOT allocation.

`GLOBAL_SHARED` limits the combined strategy allocation across the selected Hub profiles. `INDIVIDUAL` assigns separate allocations to each normal BOT profile.

Existing per-profile Trading Capital remains the fallback when Hub global authority is OFF.

## 7. AI Agent / evidence configuration
The AI Agent remains the decision authority. Saved profile values remain authoritative unless the user explicitly applies a preset.

The engine records AI configuration provenance and can report saved-profile drift from the recommended preset.

Do not lower AI evidence gates merely to force more trades. A candidate can be rejected because it lacks the required evidence families, participation, trend, structure, edge, or other configured gates.

## 8. Execution-quality gates
The Adaptive/other execution profiles enforce configured limits for:
- spread
- slippage
- order-book depth
- candle/price drift

These gates operate before exchange mutation.

## 9. Leverage and quantity
AUTO leverage is bounded by the exchange market maximum and the engine's leverage/liquidation safety rules. Manual leverage remains subject to exchange and safety validation.

Quantity is resolved through the configured sizing/capital/risk authority and then validated against exchange precision and safety boundaries.

## 10. Protection: SL / TP1 / TP2 / true BE
The hardened protection contract is:

```text
ENTRY
  |
  +--> SL
  |
  +--> TP1 (reduce-only)
  |
  +--> TP2 (reduce-only)
         |
         +--> after verified TP1 fill:
                 refresh actual exchange position
                 create TRUE BE at actual filled entry
                 verify BE
                 cancel old SL
                 preserve TP2
```

TP1/TP2 quantities and ordering are validated before entry.

TP1 fill is confirmed from exchange execution state, not merely from a price touch.

The BE price is the actual exchange-filled entry price.

The original SL order ID and BE order ID are tracked separately in Trade History.

## 11. Trade History tab
The Hub contains a **TRADE HISTORY** tab.

It displays **completed trades only**.

### Filters
- select a normal BOT profile
- select `ALL PROFILES`

Scanner trades are attributed to their parent BOT while the full scanner engine ID remains visible.

### Recorded fields
The history includes:
- result
- BOT profile
- scanner engine ID
- symbol
- side
- entry time
- exit time
- entry price
- exit price
- entry quantity
- exit quantity
- P&L
- exit reason
- leverage
- duration
- trade ID
- entry order ID
- original SL order ID
- TP1 order ID
- TP2 order ID
- BE order ID
- final exit order ID
- TP1 fill quantity/price/time
- TP2 fill quantity/price/time

### Copying a trade
Select a row and press **COPY SELECTED**, or double-click the row.

This is intended to make exchange-side reconciliation easy without searching thousands of scanner logs.

## 12. Master trade database
The authoritative trade history is stored in the master SQLite trade table.

V7.1 adds the order/fill identity fields without replacing existing trade records. Existing databases are upgraded additively.

The master CSV export remains available for spreadsheet analysis.

## 13. Diagnosing scanner rejection
Typical outcomes:

- `AI_OR_STRATEGY_SIGNAL_BLOCKED` — strategy/evidence gate rejected the candidate.
- `SCANNER_PREFLIGHT_CAPACITY` — resource governor/concurrency limit temporarily blocked another worker.
- `SCANNER_CHILD_START_BLOCKED` — safety state such as an existing position prevented startup.
- `SCANNER_CHILD_START_EXCEPTION` — worker startup/exchange/API exception.
- `SCANNER_PREFLIGHT_TIMEOUT` — preflight exceeded the watchdog limit.

These are different failure classes and should not be treated as the same problem.

## 14. Recommended validation procedure
1. Run V7.1 on Bybit Demo/Testnet.
2. Start one BOT first.
3. Confirm scanner candidates are being evaluated.
4. Confirm rejected scanner directories are purged.
5. Confirm the Trade History tab remains empty until a trade completes.
6. After a completed trade, verify entry/SL/TP1/TP2/BE/exit order IDs against the exchange.
7. Then test BOT-01/BOT-02/BOT-03 together.
8. Test `GLOBAL_SHARED` and `INDIVIDUAL` capital authority separately.
9. Only after these checks consider longer unattended operation.

## 15. Important limitation
The complete V7.1 production source is maintained as the locally audited artifact until it is synchronized through a normal large-file-safe Git path. GitHub documentation must not be treated as proof that the production source blob has been synchronized.