@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m pip install --upgrade pyinstaller ccxt numpy pandas requests
py -3.14 -m py_compile "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6.py"
py -3.14 -m PyInstaller --noconfirm --clean --onefile --windowed --name "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6" --collect-all ccxt "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6.py"
echo.
echo Crypto AI-Agent build complete: %CD%\dist\UniversalFuturesBot_CRYPTO_AI_AGENT_R6.6.exe
pause
endlocal
