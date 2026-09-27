# Crypto R9.1 Release Notes — 2026-09-27

## Observed Demo issue

After selecting NO / Start New Bot for BOT-01 recovery, the Profile Manager could still display BOT-01 as RUNNING because the previous runtime checkpoint was not updated by the negative recovery decision. R9.1 persists that decision immediately.

## Fixed

1. Recovery NO -> STOPPED
   - The selected profile runtime state is immediately written with status=STOPPED.
   - recovery_decision=START_NEW and a timestamp are recorded.
   - The previous position/order snapshot is retained for audit; it is not silently adopted.

2. Stale lock identity
   - Linux /proc/<pid> state is checked where available.
   - Zombie/reused-PID locks are treated as stale.
   - Stale locks are removed before the profile is reported as active.

3. Individual STOP buttons
   - Profile Manager creates a dedicated STOP BOT-01, STOP BOT-02, etc. button for every saved profile.
   - Each button targets its named profile directly, so selecting a different row cannot accidentally stop the wrong bot.
   - If the profile is not actually running, the stale runtime marker is normalized to STOPPED when no saved inventory exists, or RECOVERY_REQUIRED when saved position/Grid state exists.

4. Fixed Qty semantics
   - Removed automatic Fixed Qty -> RISK_% SL-mode switching.
   - FIXED_QTY remains literal exchange/base quantity.
   - EQUITY_RISK_% remains calculated sizing.
   - Existing saved SL mode is preserved when loading a profile.
   - Exchange precision/minimum normalization remains the only automatic adjustment to a Fixed Qty order quantity.

## Validation

- Python py_compile: PASS.
- AST GUI audit: PASS; 139 GUI methods and no missing self.* method references.
- Live Bybit Demo order execution still needs confirmation with a deliberately small Fixed Qty test.
