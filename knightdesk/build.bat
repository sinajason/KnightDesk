@echo off
cd /d "%~dp0"
py -m pip install --upgrade pip
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --collect-data tzdata --collect-submodules winrt --collect-data winrt --onefile --noconsole --name KnightDesk app.py
echo.
echo Done. Your app: dist\KnightDesk.exe
pause
