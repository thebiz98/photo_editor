@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo Setting up Windows ARM64 Virtual Environment
echo ===================================================

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment with system ARM64 Python...
    python -m venv venv
)

echo.
echo Upgrading pip, setuptools, and wheel...
venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

echo.
echo Installing native ARM64 core libraries...
venv\Scripts\python.exe -m pip install numpy pillow onnxruntime huggingface_hub PySide6

echo.
echo ===================================================
echo Environment setup complete!
echo ===================================================
pause
