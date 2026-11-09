@echo off
setlocal

:: ─────────────────────────────────────────────────────
:: Local Photo & Print Studio — Native Window Launcher
:: ─────────────────────────────────────────────────────
:: Runs the Gradio server in WSL and opens it in a
:: pywebview native window on Windows (no browser chrome).
::
:: Requires: pip install pywebview  (Windows Python)
:: ─────────────────────────────────────────────────────

:: 1. Start the Gradio server inside WSL (headless)
start "" wsl -d Ubuntu bash -c "cd ~/photo_editor && source venv/bin/activate && python3 -c \"import app; app.app.launch(server_name='0.0.0.0', server_port=7860, inbrowser=False)\""

:: 2. Wait for the server to be reachable
echo Starting Photo Studio server...
:wait
timeout /t 1 /nobreak >nul
powershell -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:7860' -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 goto wait
echo Server ready.

:: 3. Open native window (blocks until window is closed)
python -c "import webview; webview.create_window('Local Photo & Print Studio', 'http://127.0.0.1:7860', width=1380, height=820, min_size=(1024, 600)); webview.start()"

:: 4. Clean up WSL when the window closes
wsl --terminate Ubuntu >nul 2>&1
endlocal
exit
