@echo off
setlocal
cd /d "%~dp0"
echo Building Universal Futures Bot Crypto AI Agent R6.8.7.2...
py -m PyInstaller --noconfirm --clean --onefile --windowed --name UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.2 UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.2.py
if errorlevel 1 (
  echo BUILD FAILED.
  exit /b 1
)
echo BUILD COMPLETE.
echo Output: dist\UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.2.exe
endlocal
