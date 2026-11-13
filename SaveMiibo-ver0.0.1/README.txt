SaveMiibo
=========

A small desktop companion for the Amiibo Bridge Android app.

Files
-----
SaveMiibo.py       Desktop GUI
amiibo_bridge.py   Phone connection and API helper
requirements.txt   Python dependencies
build_windows.bat  Builds SaveMiibo.exe on Windows

Run on Fedora/Linux
-------------------
Install the required packages:
  sudo dnf install python3-tkinter python3-pillow-tk
  python3 -m pip install --user 'qrcode[pil]'

Then, from this folder, run:
  python3 SaveMiibo.py

Build the Windows EXE
---------------------
Install Python on Windows, open Command Prompt in this folder, and run:
  build_windows.bat

The EXE will be created in:
  dist\SaveMiibo.exe

Pairing and safety
------------------
The PC and Android phone must be on the same Wi-Fi network. Pair the phone
using the QR button in SaveMiibo. The pairing listener uses TCP port 8766;
the phone app uses TCP port 8765.

Restore and wipe are intended only for compatible writable NTAG215 tags.
Do NOT use these operations on genuine Amiibo figures. Keep backups of
original data.

The Windows EXE is built by running the included script on Windows; it is
not included in this source ZIP.
