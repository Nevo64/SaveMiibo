@echo off
setlocal
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean --onefile --windowed --name SaveMiibo --collect-all qrcode --collect-all PIL SaveMiibo.py
echo.
echo Build complete. EXE: dist\SaveMiibo.exe
pause
