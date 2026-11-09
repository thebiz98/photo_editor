@echo off
cd /d "%~dp0"
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install PySide6-Essentials huggingface_hub
.\venv\Scripts\python.exe -c "from PySide6 import QtWidgets, QtGui, QtCore, QtPrintSupport; print('SAC Verification Passed!')"
.\venv\Scripts\python.exe download_models.py
.\venv\Scripts\python.exe -m pip freeze > install_info.txt
pause
