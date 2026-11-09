@echo off
cd /d "%~dp0"
setlocal EnableDelayedExpansion

echo ========================================================
echo   Setting up Local Photo & Print Studio Environment
echo ========================================================

:: 1. Check if Python is installed on the host Windows machine
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH.
    echo Please install Python 3.10+ from python.org or the Microsoft Store.
    pause
    exit /b 1
)

:: 2. Create the virtual environment if missing
if not exist "venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment already exists.
)

:: 3. Upgrade pip
echo [2/4] Upgrading pip...
.\venv\Scripts\python.exe -m pip install --upgrade pip

:: 4. Install full application dependencies
echo [3/4] Installing application dependencies...
.\venv\Scripts\python.exe -m pip install numpy pillow onnxruntime PySide6-Essentials huggingface_hub
if %errorlevel% neq 0 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)

:: 5. Download and bundle local models if missing
echo [4/4] Verifying and downloading local models...
.\venv\Scripts\python.exe download_models.py
if %errorlevel% neq 0 (
    echo [ERROR] Model setup failed.
    pause
    exit /b 1
)

:: 6. Smart App Control & Import Smoke Test
echo Verifying components...
.\venv\Scripts\python.exe -c "import numpy, PIL, onnxruntime; from PySide6 import QtWidgets, QtGui, QtCore, QtPrintSupport; print('Environment and SAC verification passed!')"

echo ========================================================
echo   Installation Complete! You can now run PhotoStudio.bat
echo ========================================================
pause
