# WSL Web Stack Installation & Setup Guide 🐧🌐

This document covers how to set up, configure, and run the alternative/legacy web-based Photo Studio using the **Windows Subsystem for Linux (WSL)** with Ubuntu.

> [!NOTE]
> The primary, recommended application for Windows 11 ARM64 is the **Native PySide6 Desktop Application** located in the root repository. Refer to the main [README.md](file:///c:/custom_apps/photo_editor/README.md) for full instructions on running and bundling the native desktop app.

---

## 🎯 Why WSL for the Web Stack?

On Windows 11 ARM64, running Gradio / FastAPI / Uvicorn natively on Windows can trigger **Windows Smart App Control (SAC)** blocks due to unsigned C-extensions (such as `orjson` and compiled async event loops). Running the web stack inside an isolated Linux container via WSL bypasses these restrictions completely while keeping the GUI accessible on Windows via Microsoft Edge or Google Chrome.

---

## 🛠️ Step 1: Install WSL & Ubuntu on Windows 11

1. Open **PowerShell** as **Administrator**:
   - Press `Win + X` and select **Terminal (Admin)** or **PowerShell (Admin)**.

2. Install WSL with Ubuntu:
   ```powershell
   wsl --install -d Ubuntu
   ```

3. Restart your computer if prompted by Windows.

4. After rebooting, open **Ubuntu** from the Windows Start menu to finish the initial setup. Set your default UNIX username and password when prompted.

5. Update the package database:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

---

## 🐍 Step 2: Install Python & Virtual Environment Tools in WSL

Inside the Ubuntu terminal, install Python 3, pip, and venv tooling:

```bash
sudo apt install -y python3 python3-pip python3-venv git
```

Verify Python installation:
```bash
python3 --version
```
*(Python 3.10 or 3.12 will be installed depending on your Ubuntu release).*

---

## 📁 Step 3: Choose Workspace Location & Create Virtual Environment

You have two setup options:

### Option A: Direct Windows Mount (Recommended for instant file syncing)
Access the files directly from the Windows partition without copying:
```bash
cd /mnt/c/custom_apps/photo_editor/wsl
python3 -m venv venv
source venv/bin/activate
```

### Option B: Copied to Linux Home (`~/photo_editor`)
If you prefer faster Linux filesystem performance:
```bash
mkdir -p ~/photo_editor
cp -r /mnt/c/custom_apps/photo_editor/wsl/* ~/photo_editor/
cd ~/photo_editor
python3 -m venv venv
source venv/bin/activate
```

---

## 📦 Step 4: Install Dependencies

With the virtual environment active (`(venv)` shown in your prompt), install the required packages:

```bash
pip install --upgrade pip
pip install gradio numpy pillow onnxruntime huggingface_hub
```

Optionally, if you wish to use the native borderless webview launcher on Windows:
```bash
pip install pywebview
```

---

## 🚀 Step 5: Launching from Windows

You do **not** need to open an Ubuntu terminal every time you use the app. Two Windows batch scripts are provided in `wsl/`:

### 1. Standard App Mode Launcher (`PhotoStudio.bat`)
Double-click [PhotoStudio.bat](file:///c:/custom_apps/photo_editor/wsl/PhotoStudio.bat) directly in Windows File Explorer:
- Automatically starts the Gradio server inside Ubuntu WSL in the background.
- Waits 3 seconds for port `7860` to spin up.
- Launches **Microsoft Edge in clean `--app` mode** (`http://127.0.0.1:7860`), providing a distraction-free window without URL bars or browser tabs.
- When you close the Edge window, the script automatically terminates the background WSL session (`wsl --terminate Ubuntu`) to free system RAM and NPU/CPU resources.

### 2. Native Window Launcher (`PhotoStudio_Native.bat`)
Double-click [PhotoStudio_Native.bat](file:///c:/custom_apps/photo_editor/wsl/PhotoStudio_Native.bat):
- Uses `pywebview` on Windows to wrap the WSL Gradio server into a standalone Windows window.
- Shuts down WSL when the window is closed.

---

## 🔍 Troubleshooting WSL

- **Gradio server port already in use**:
  Terminate any lingering WSL instances from Windows PowerShell:
  ```powershell
  wsl --terminate Ubuntu
  ```
- **File path conversions**:
  Windows paths (`C:\custom_apps\photo_editor\wsl`) map to `/mnt/c/custom_apps/photo_editor/wsl` in WSL. You can convert any path dynamically in WSL using `wslpath "C:\path\to\file"`.
