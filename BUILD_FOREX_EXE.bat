@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m pip install --upgrade pyinstaller MetaTrader5 numpy pandas requests
py -3.14 -m py_compile "UniversalForexBot_MT5.py"
py -3.14 -m PyInstaller --noconfirm --clean --onefile --windowed --name "UniversalForexBot_MT5" "UniversalForexBot_MT5.py"
echo.
echo Forex/MT5 build complete: %CD%\dist\UniversalForexBot_MT5.exe
pause
endlocal
