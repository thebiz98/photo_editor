@echo off
setlocal
cd /d "%~dp0"

:: ─────────────────────────────────────────────────────────────────────────────
:: Photo Studio - WSL Launcher
:: Starts Gradio in Ubuntu WSL and launches Microsoft Edge in App Mode
:: ─────────────────────────────────────────────────────────────────────────────

:: 1. Start the Python app inside WSL
:: Checks local Linux home first (~/photo_editor), then the Windows mount path
start "" wsl -d Ubuntu bash -c "if [ -d ~/photo_editor/venv ]; then cd ~/photo_editor; elif [ -d /mnt/c/custom_apps/photo_editor/wsl/venv ]; then cd /mnt/c/custom_apps/photo_editor/wsl; else cd $(wslpath '%~dp0'); fi; source venv/bin/activate && python3 app.py"

:: 2. Wait 3 seconds for the Gradio server to spin up on port 7860
timeout /t 3 /nobreak >nul

:: 3. Launch Microsoft Edge in clean App Mode
start "" "msedge.exe" --app="http://127.0.0.1:7860" --window-size=1380,820

:: 4. Monitor the Edge window and shut down WSL when closed
:loop
tasklist /fi "imagename eq msedge.exe" 2>nul | find /i "msedge.exe" >nul
if errorlevel 1 goto cleanup
timeout /t 3 /nobreak >nul
goto loop

:cleanup
wsl --terminate Ubuntu >nul 2>&1
endlocal
exit
