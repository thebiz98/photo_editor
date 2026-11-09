
@echo off
setlocal

:: 1. Start the Python app inside WSL (using python3)
start "" wsl -d Ubuntu bash -c "cd ~/photo_editor && source venv/bin/activate && python3 app.py"

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
