# Crypto AI Agent R6.4 Release Notes

Date: 2026-09-27

## Problem

A Windows run showed the application title changing to Not Responding after the user closed the bot window.

The source had two shutdown designs: the Stop button already scheduled exchange cleanup on a background thread, while the window-close callback called the exchange kill switch directly from the Tkinter callback thread.

## Root Cause

The old on_close() path performed _activate_kill_switch( GUI SHUTDOWN ) directly inside the Tkinter event handler. The kill switch performs exchange operations including market loading, open-order cancellation, position reads, close orders, sleeps/retries, and final verification. Those operations must not run on the Tk event loop.

## Fixed

### 1. Non-blocking window close

on_close() now asks for confirmation when necessary, saves local configuration, marks the close request, stops the worker flag, marks runtime status STOPPING, starts the background cleanup worker, schedules GUI polling, and returns immediately to Tkinter. No exchange API call is made directly by the close callback.

### 2. Safe final close

_poll_stop_completion() now monitors the execution worker, stop-cleanup worker, and kill-switch in-progress state. The GUI remains responsive while those operations run. The window is destroyed only after the kill switch has verified FLAT + NO OPEN ORDERS.

### 3. Failed cleanup behavior

If the cleanup worker finishes without verified flat state, the GUI is deliberately not destroyed. It logs and displays that safe close is blocked so shutdown can be retried.

### 4. Stop-wait behavior

Stop-wait diagnostics now account for background cleanup as well as the main execution worker.

## Versioning

Internal source: V8.4.2-CRYPTO-AI-AGENT-R6.4
Config schema: 21
Runtime schema: 21
Audit marker: V8.4.2-AI-AGENT-AUDIT-2026-09-27-R6.4-GUI-SHUTDOWN-NONBLOCKING-HOTFIX

## Validation

- Python AST parse: PASS.
- Python bytecode compilation: PASS.
- Static shutdown audit: PASS.
- on_close() has no direct GUI-thread kill-switch call.
- on_close() schedules background cleanup and GUI polling.
- _poll_stop_completion() waits for worker/cleanup completion before destruction.
- Full live exchange lifecycle was not claimed by this patch.

## Test

Start R6.4 on Bybit Demo and close the application with the window X.

Expected: the GUI remains responsive, exchange cleanup runs in the background, and the window closes only after FLAT + NO OPEN ORDERS verification. If cleanup cannot be verified, the GUI remains open and reports that safe close is blocked.

## Stable filename

The repository continues to use UniversalFuturesBot_CRYPTO_AI_AGENT_R4.py. The release is identified by APP_VERSION.
