@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m pip install --upgrade pyinstaller ccxt numpy pandas requests
py -3.14 -m py_compile "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28_LINUX_RSS_VPS_MEMORY_HARDENED_FULL_AUDIT.py"
py -3.14 -m PyInstaller --noconfirm --clean --onefile --windowed --name "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28" --collect-all ccxt "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28_LINUX_RSS_VPS_MEMORY_HARDENED_FULL_AUDIT.py"
echo.
echo Crypto build complete: %CD%\dist\UniversalFuturesBot_CRYPTO_AI_AGENT_R6.8.28.exe
pause
endlocal
