@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m pip install --upgrade pyinstaller ccxt numpy pandas requests
py -3.14 -m py_compile "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py"
py -3.14 -m PyInstaller --noconfirm --clean --onefile --windowed --name "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7" --collect-all ccxt "UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.py"
echo.
echo Crypto AI-Agent R6.7 build complete: %CD%\dist\UniversalFuturesBot_CRYPTO_AI_AGENT_R6.7.exe
pause
endlocal
