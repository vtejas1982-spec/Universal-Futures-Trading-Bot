@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m pip install --upgrade pyinstaller ccxt numpy pandas requests
py -3.14 -m py_compile "UniversalFuturesBot_CRYPTO.py"
py -3.14 -m PyInstaller --noconfirm --clean --onefile --windowed --name "UniversalFuturesBot_CRYPTO" --collect-all ccxt "UniversalFuturesBot_CRYPTO.py"
echo.
echo Crypto build complete: %CD%\dist\UniversalFuturesBot_CRYPTO.exe
pause
endlocal
