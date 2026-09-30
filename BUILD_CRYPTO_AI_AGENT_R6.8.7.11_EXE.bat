@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m py_compile "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.11.py"
if errorlevel 1 (
  echo Python compile failed.
  pause
  exit /b 1
)
py -3.14 -m PyInstaller --noconfirm --clean --onefile --windowed --name "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.11" --collect-all ccxt "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.11.py"
if errorlevel 1 (
  echo PyInstaller build failed.
  pause
  exit /b 1
)
echo.
echo Crypto AI-Agent R6.8.7.11 build complete:
echo %CD%distUniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.7.11.exe
pause
endlocal
