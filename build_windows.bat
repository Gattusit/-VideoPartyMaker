@echo off
setlocal
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name VideoPartyMaker --add-data "src;src" main.py
echo.
echo EXE creato in dist\VideoPartyMaker.exe
pause
