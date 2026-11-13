# Native Windows ARM64 Photo Studio & Print Engine 📸🖨️

A 100% offline, native Windows 11 desktop application designed for portrait matting, official document/ID card photo retouching, physical size calibration, and automated 1:1 hardware A4 print layout.

Built specifically for **Windows 11 on ARM64 (Qualcomm Snapdragon X)** with zero web stack, zero browser overhead, full compliance with **Windows Smart App Control (SAC)**, and bundled local ONNX neural models.

---

## 🎯 Purpose & Key Innovations

Preparing official passport, visa, and ID photos or fixing scanned document photos typically requires multiple disconnected tools. **Native Photo Studio** brings the entire pipeline into a single, high-performance desktop application:

1. **Zero Web Stack / Zero Server**: Pure native Qt6 GUI (`PySide6-Essentials`) — no Gradio, no FastAPI, no Uvicorn, and no browser chrome.
2. **100% Offline Runtime & Bundled Weights**: Pre-bundled local ONNX weights (`RMBG-1.4` and `MODNet`). Runs completely disconnected with zero network calls.
3. **Streamlined Retouch Scope & Isolated Per-Photo Workspaces**:
   - **Whole Image (Default)**: Lighting, color grading, and AI background removal apply to the full photo by default.
   - **Edit inside box**: Toggle `Edit inside box` inside the right-pane **Lighting & Color Grading** panel to confine lighting and AI backdrop changes to a sub-region (like a portrait on a scanned ID), then click `✔️ Commit` to bake edits permanently and reset all retouch sliders cleanly.
   - **Crop to Box (Extract Standalone Photo)**: Extract the sub-region and scale directly to standard physical dimensions at 300 DPI.
   - **Per-Photo Workspace Isolation**: Each loaded photo maintains its own independent sliders, AI backdrop settings, crop presets/units, and perspective pins when switching between images.
4. **Morphological Edge Refinement**: Replaces manual brushwork with instant morphological erosion (`Edge Choke` 0–5 px) to eliminate background halos around hair and shoulders, plus Gaussian blur (`Edge Feather` 0.0–5.0 px) for smooth edge transitions.
5. **In-Memory Alpha Caching**: Raw alpha mattes are cached in memory so moving lighting sliders, color grading, backdrop colors, or edge refinement sliders never triggers redundant ONNX inference.
6. **A4 2D Shelf Bin-Packing Engine**: Automatically tiles arbitrary photo dimensions and copy counts onto standard A4 paper (`2480 x 3508` @ 300 DPI) with customizable margins, inter-photo gaps, and scissor cut lines.
7. **True 1:1 Hardware Printing**: Directly drives physical printers via `QPrinter` with a 0 mm margin layout, preventing Windows printer drivers from auto-shrinking 35×45 mm photos.
8. **Deterministic Rescaling & AI Super-Resolution**: Built-in CPU Lanczos downscaling/upscaling (10% to 400%) with smart unsharp edge sharpening and 4096 px memory ceilings, plus 100% offline neural 2x super-resolution (`RealESRGAN-x2plus`) via ONNX Runtime to restore low-res images before printing. Zero UI freezes via background `QThread` workers.
9. **4-Point Perspective Straightening & ID Extractor**: Cleanly digitizes and straightens slanted, perspective-distorted photos of ID cards, driver's licenses, and documents. Users drag 4 circular corner pins (with an amber **`TOP`** edge hint for Width orientation) onto the card corners and extract either at native unconstrained pixel resolution or fitted directly to specified physical (`mm`/`in` @ 300 DPI) or pixel (`px`) dimensions via **Apply Size**, with full Undo/Redo integration.

---

## 🏗️ Architecture & Pipeline

```
 ┌────────────────────────────────────────────────────────┐
 │  Workspace Ingest (Add Photos, Drag & Drop, Ctrl+V)    │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │  Interactive Canvas (Pan, Zoom, 8-Point ROI Handles)   │
 └──────────────────────────┬─────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
 ┌──────────────────────┐       ┌──────────────────────┐
 │ ROI Mode: Patch ID   │       │ ROI Mode: Crop /     │
 │ (Edit inside box,    │       │ Whole Image          │
 │  paste back into doc)│       │ (Extract standalone) │
 └──────────┬───────────┘       └──────────┬───────────┘
            │                              │
            └───────────────┬──────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │  Deterministic Lighting & Color Grading                │
 │  (Brightness, Contrast, Saturation, Sharpness, Warmth) │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │  AI Matting & In-Memory Alpha Cache (engine.py)        │
 │  (RMBG-1.4: 1024x1024  |  MODNet: 512x512)            │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │  Morphological Edge Refinement & Backdrop Compositing  │
 │  (MinFilter Choke, Gaussian Feather, Solid/Blur BG)   │
 └──────────────────────────┬─────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
 ┌──────────────────────┐       ┌──────────────────────┐
 │ Single Photo Export  │       │ Send to A4 Queue     │
 │ (PNG / JPEG @ 300DPI)│       │ (Tab 2: Print Studio)│
 └──────────────────────┘       └──────────┬───────────┘
                                           │
                                           ▼
                                ┌──────────────────────┐
                                │ A4 2D Shelf Packing  │
                                │ (printer.py)         │
                                └──────────┬───────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
         ┌─────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
         │ 1:1 Hardware Print  │ │ 300-DPI A4 PNG     │ │ 300-DPI A4 PDF     │
         │ (QPrinter 0mm Marg) │ │ (2480 x 3508 px)   │ │ (High-Res Master)  │
         └─────────────────────┘ └────────────────────┘ └────────────────────┘
```

---

## 📂 Repository Structure

```text
photo_editor/
├── venv/                       # Verified Windows 11 ARM64 virtual environment
├── models/                     # Bundled offline ONNX model weights
│   ├── rmbg14/model.onnx       # RMBG-1.4 high-precision segmentation (~176 MB)
│   ├── modnet/model.onnx       # MODNet portrait specialist (~25.8 MB)
│   └── superres/model.onnx     # Real-ESRGAN 2x neural super-resolution (~64 MB)
├── install.bat                 # One-click dependency setup & SAC verification
├── download_models.py          # Offline model bundler (skips if present on disk)
├── engine.py                   # ONNX inference, ROI patch engine, edge choke & lighting
├── transforms.py               # Pure geometric transforms, homography solver, & perspective warp
├── rescaler.py                 # CPU Lanczos scaling, smart unsharp, & Real-ESRGAN 2x engine
├── canvas_items.py             # Reusable interactive handles, ROI rect box, & 4-corner perspective quad
├── canvas.py                   # Viewport, zoom, pan, overlay coordination, keyboard nudging
├── ui/                         # Modular PySide6 UI system
│   ├── theme/                  # Design tokens, section configs, dark theme, & dynamic QSS builder
│   ├── primitives/             # Reusable wheel-safe inputs, variant buttons, labels, & sliders
│   └── panels/                 # Extracted Photo Studio panels (workspace, crop, toolbar, AI, lighting, rescale)
├── styles.py                   # Compatibility facade re-exporting compiled dark theme QSS
├── workspace.py                # Isolated per-photo workspace state & undo history model
├── printer.py                  # A4 2D shelf bin-packing & 1:1 QPrinter hardware engine
├── print_studio.py             # Tab 2: A4 Print Studio controller
├── main.py                     # Native PySide6 GUI desktop application
├── tests/                      # Headless PySide6 UI modularity & workflow tests
├── PhotoStudio.bat             # Zero-console Windows launcher (pythonw.exe)
├── PLAN.md                     # Technical architecture & specification document
├── README.md                   # This documentation
└── wsl/                        # Legacy / Alternative WSL Web Stack (Gradio)
    ├── README.md               # WSL installation and setup guide
    ├── app.py                  # Gradio web application
    ├── PhotoStudio.bat         # WSL + Edge app launcher
    └── PhotoStudio_Native.bat  # WSL + pywebview launcher
```

---

## ⚡ Quick Start

### 1. Clone & One-Click Installation
Anyone cloning this repository can set up the complete environment in one step. Open Command Prompt in the cloned directory and run `install.bat`:

```bat
install.bat
```

The script automatically:
- Checks if Python 3.10+ is installed on the host machine.
- Creates the local virtual environment (`venv`) if it doesn't already exist.
- Upgrades `pip` and installs dependencies (`numpy`, `pillow`, `onnxruntime`, `PySide6-Essentials`, `huggingface_hub`).
- Downloads and bundles local ONNX neural models into `./models/` for 100% offline runtime.
- Runs a Smart App Control & import verification smoke test.

### 2. Launch the Desktop Application
Double-click `PhotoStudio.bat` or run from your terminal:

```bat
.\venv\Scripts\python.exe main.py
```

---

## 📦 Native Executable Bundling (`.exe`)

You can compile the native Python application into a standalone Windows executable (`.exe`) that runs without exposing terminal windows or requiring manual Python invocation.

### Method 1: Build Standalone Executable with PyInstaller

1. Activate your virtual environment and install `pyinstaller`:
   ```bat
   .\venv\Scripts\python.exe -m pip install pyinstaller
   ```

2. Compile the application into a distribution folder:
   ```bat
   .\venv\Scripts\pyinstaller --noconsole --name "PhotoStudio" ^
       --add-data "models;models" ^
       --collect-all PySide6 ^
       --collect-all onnxruntime ^
       main.py
   ```

   > [!TIP]
   > On Windows 11 ARM64 with Smart App Control enabled, `--onedir` mode (the default shown above) is strongly recommended over `--onefile`. It enables instant startup without unpacking temporary files and allows Windows to cleanly verify digital signatures on runtime DLLs.

3. The generated executable will be located in:
   ```text
   dist\PhotoStudio\PhotoStudio.exe
   ```

### Method 2: Zero-Console Launcher (`PhotoStudio.bat`)

If you want an instant zero-overhead launcher without re-bundling files, double-click [PhotoStudio.bat](file:///c:/custom_apps/photo_editor/PhotoStudio.bat). It uses Windows `pythonw.exe` to run [main.py](file:///c:/custom_apps/photo_editor/main.py) natively with zero console windows.

---

## 📐 Dual-Mode Crop & Perspective Straightening

The **Crop & Straighten** panel provides two dedicated workflows in a single unified interface:

### 1. `✂️ Crop` (Physical Sizing)
- **Use Case:** Framing portraits or cropping photos to exact physical passport, visa, or ID dimensions.
- **Features:** 8 interactive resize handles, aspect ratio locking, physical print presets (Passport $35 \times 45\text{ mm}$, Visa $2 \times 2\text{ in}$, ID Card $85.6 \times 54\text{ mm}$), shared `mm`/`in`/`px` dimensions, and keyboard arrow nudging (hold `Shift` for $10\text{ px}$ nudge).

### 2. `📐 Straighten` (4-Corner ID & Document Extractor)
- **Use Case:** Digitizing skewed or slanted snapshots of ID cards, licenses, certificates, and business cards taken at an angle.
- **Workflow:**
  1. Toggle to `📐 Straighten` in the **Crop & Straighten** panel.
  2. Drag the 4 circular corner pins onto the 4 corners of the card on the canvas. Align the highlighted amber **`TOP`** edge (`TL → TR`) with the top (`Width`) edge of the card (click `🔄 Reset` anytime to re-center pins).
  3. *(Optional)* To reverse 3D foreshortening and fit the card directly into exact dimensions (such as $85.6 \times 54.0\text{ mm}$), enter **Width** and **Height** (in `mm`, `in`, or `px`) and check **Apply Size**. Leave **Apply Size** unchecked to extract at unconstrained natural pixel resolution.
  4. Click `🪄 Extract` to compute the projective homography matrix and rectify the card into a flat, straight rectangular photo.
  5. The extracted photo replaces the active image with full `Ctrl+Z` Undo and Revert support.

---

## 📐 Physical Document Presets (300 DPI)

| Preset Name | Physical Size (mm) | Pixel Dimensions (300 DPI) | Common Use |
| :--- | :---: | :---: | :--- |
| **Standard Passport** | 35.0 × 45.0 mm | 413 × 531 px | UK, EU, Schengen, Australian Passport |
| **Indian Passport / US Visa** | 50.8 × 50.8 mm (2×2") | 600 × 600 px | Indian Passport, US Visa, OCI |
| **PAN / Official ID Portrait** | 25.0 × 35.0 mm | 295 × 413 px | Indian PAN Card, Government ID |
| **Indian Stamp Size** | 20.0 × 25.0 mm | 236 × 295 px | Application forms, Admit cards |
| **Standard ID Card Full** | 85.6 × 54.0 mm | 1011 × 638 px | ISO/IEC 7810 ID-1 (Aadhaar, Driving License) |
| **Custom Size (mm)** | User-defined | User-defined | Any custom physical millimeter dimension |

---

## 🐧 Legacy / Alternative: WSL Web Stack

Prior to the native Qt6 desktop app, an experimental web version was developed using Gradio and FastAPI. 

Running the web stack directly on Windows 11 ARM64 can trigger Smart App Control blocks due to unsigned C-extensions (like `orjson`). To run the web stack inside an isolated Linux environment using Windows Subsystem for Linux (WSL), refer to the dedicated guide:

👉 **[WSL Web Stack Setup & Installation Guide](file:///c:/custom_apps/photo_editor/wsl/README.md)**

The WSL guide details:
- How to install WSL and Ubuntu on Windows 11.
- Setting up Python virtual environments inside WSL.
- Installing Gradio web dependencies.
- Running the web studio seamlessly from Windows via [wsl/PhotoStudio.bat](file:///c:/custom_apps/photo_editor/wsl/PhotoStudio.bat) in borderless Microsoft Edge App Mode.

---

## 📄 License & Attribution

- **MODNet**: Portrait Matting via [Xenova/modnet](https://huggingface.co/Xenova/modnet).
- **RMBG-1.4**: High-accuracy salient background removal by [BRIA AI](https://bria.ai).
- **Qt6**: Built with `PySide6-Essentials` (The Qt Company).
- **ONNX Runtime**: Machine learning inference engine by Microsoft.
