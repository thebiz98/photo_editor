# Native Windows on ARM64 Photo & Print Studio — Implementation Plan

## 1. Project Overview & Objective

Transform the prototype photo editor into a **100% native Windows on ARM64 (Snapdragon)** desktop application using **PySide6 (Qt6)** and **RMBG-2.0 (BiRefNet)**.

### Core Problems Solved
1. **Security & Smart App Control Compliance**: Replaces the Gradio web stack (which was blocked due to unsigned C-extensions like `orjson`) with pure Qt6 and pre-compiled native ARM64 wheels that pass Windows Smart App Control out of the box.
2. **True Native Performance**: Eliminates web-server latency (FastAPI/Uvicorn/WebSockets) and Edge browser wrappers. All slider adjustments, canvas rendering, and compositing occur directly in-memory at 60 FPS.
3. **Studio-Grade Edge Quality**: Upgrades the cutout engine from legacy MODNet (~74% accuracy) to **RMBG-2.0** (>90% accuracy, continuous 8-bit soft alpha matting) for hair-level passport cutouts.
4. **Physical Print Accuracy**: Retains the 300-DPI A4 shelf bin-packing layout engine and integrates directly with the native Windows Print Spooler (`QPrinter` / `QPrintDialog`).

---

## 2. Technology Stack & ARM64 Environment

| Layer | Technology | Status / Details |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 on ARM64 | Snapdragon architecture |
| **Security Policy** | Smart App Control (SAC) | **Enabled** (fully compliant) |
| **Runtime** | Python 3.12 (ARM64) | Managed strictly inside `.\venv\` |
| **GUI Framework** | **PySide6 (Qt6)** | Official `win_arm64` wheels from PyPI |
| **Inference Engine** | **ONNX Runtime (ARM64)** | `onnxruntime-1.31.1` (CPU + DirectML/QNN fallback) |
| **Segmentation Model** | **RMBG-2.0 (BiRefNet)** | Pre-bundled ONNX (~180 MB); pluggable hook for MODNet |
| **Image Pipeline** | **Pillow & NumPy** | Native ARM64 vector processing & color transformations |
| **Printing System** | **QPrinter / QPrintDialog** | Native Windows print subsystem + 300 DPI PNG export |

---

## 3. Model Architecture: RMBG-2.0 vs. MODNet

```
┌────────────────────────────────────────────────────────┐
│                   SegmentationEngine                   │
│            (Modular ONNX Inference Manager)            │
└───────────┬────────────────────────────────┬───────────┘
            │                                │
            ▼ (Default)                      ▼ (Pluggable)
┌───────────────────────┐        ┌───────────────────────┐
│       RMBG-2.0        │        │        MODNet         │
│  (BiRefNet, ~180MB)   │        │     (CNN, ~25MB)      │
│  • >90% Accuracy      │        │  • ~74% Accuracy      │
│  • 8-bit Alpha Matte  │        │  • Coarse Matting     │
│  • Fine Hair Detail   │        │  • Faster on low-end  │
└───────────────────────┘        └───────────────────────┘
```

* **Why RMBG-2.0 is primary**: BiRefNet provides continuous transparency gradients (0–255), preventing the "cardboard cutout" halo effect around hair and shoulders on passport photos.
* **Adding MODNet later**: The `SegmentationEngine` class defines a generic `predict_mask(pil_image) -> Image (mode='L')` interface. Adding MODNet or any future model is simply registering its ONNX path and input normalizer in the dropdown selector.

---

## 4. UI Architecture & Features

The native interface (`main.py`) uses a high-productivity 3-pane layout built with PySide6 widgets:

```
┌────────────────────────────────────────────────────────────────────────┐
│  Local Photo & Print Studio (Native ARM64)          [-] [□] [X]        │
├──────────────┬──────────────────────────────────────────┬──────────────┤
│ 1. INGEST    │ 2. INTERACTIVE CANVAS                    │ 3. ADJUST    │
│              │                                          │              │
│ [Open File]  │  ┌────────────────────────────────────┐  │ [Light][BG]  │
│ [Paste Clp]  │  │                                    │  │ [Size]       │
│ [Drag Drop]  │  │      Preview / Live Result         │  ├──────────────┤
│              │  │                                    │  │ Brightness   │
│ Model:       │  │    ┌──────────────────────────┐    │  │ Contrast     │
│ [RMBG-2.0 ▾] │  │    │  Box (ROI) Selector      │    │  │ Saturation   │
│              │  │    │  (Drag-to-resize crop)   │    │  │ Warmth       │
│ [Extract BG] │  │    └──────────────────────────┘    │  │ Sharpness    │
│              │  │                                    │  ├──────────────┤
│ Copies: [4]  │  │                                    │  │ Mode: White  │
│ [Add to A4]  │  └────────────────────────────────────┘  │ Blur / Navy  │
│              │  [Zoom: 100%] [Fit] [Split Before/After] │ Custom Color │
├──────────────┴──────────────────────────────────────────┴──────────────┤
│ Tab 1: 📸 Photo Studio   |   Tab 2: 🖨️ A4 Print Studio                 │
└────────────────────────────────────────────────────────────────────────┘
```

### Key UI Capabilities
* **Interactive Box (ROI) Selector**: A draggable, resizable rubberband box on the canvas for framing passport photos according to standard rules (chin-to-crown ratio).
* **Zero-Latency Sliders**: Adjusting brightness, contrast, warmth, and backdrop colors recalculates in milliseconds via local NumPy array operations.
* **A4 Print Studio Tab**:
  * Visual queue gallery of photos ready to print.
  * Editable table for copy counts, physical width, and height.
  * Live 300-DPI A4 sheet preview with margins, spacing, and scissor cutting lines.
  * Direct 1-click print button launching the native **Windows Print Dialog** (`QPrintDialog`).

---

## 5. File Structure

```
photo_editor/
├── venv/                     # Windows ARM64 virtual environment (clean, isolated)
├── models/                   # Pre-bundled local ONNX neural models
│   └── rmbg2/
│       └── model.onnx        # RMBG-2.0 weights (~180 MB)
├── wsl/                      # Archived WSL prototype files
│   ├── app.py
│   ├── engine.py
│   ├── printer.py
│   ├── styles.py
│   ├── PhotoStudio.bat
│   └── PhotoStudio_Native.bat
├── main.py                   # PySide6 native desktop UI & application entry point
├── engine.py                 # Modular ONNX segmentation & Pillow/NumPy processing
├── printer.py                # 2D A4 shelf bin-packing layout & QPrinter driver
├── download_models.py        # Model download & verification script
├── install.bat               # Automated venv setup script
├── install_info.txt          # Command history & environment tracking
├── PLAN.md                   # This implementation roadmap
├── .gitignore                # Git exclusions (venv, models, dist)
└── README.md                 # Updated project documentation
```

---

## 6. Detailed Implementation Steps

### Phase 1: Virtual Environment & Dependencies
1. Run `.\venv\Scripts\python.exe -m pip install PySide6`
2. Verify that PySide6 imports cleanly without triggering Smart App Control.
3. Update `install_info.txt` to track the installation.

### Phase 2: Model Acquisition & Inference Engine (`engine.py`)
1. Create `download_models.py` to download `briaai/RMBG-2.0` ONNX model directly to `.\models\rmbg2\model.onnx`.
2. Implement `engine.py`:
   * `SegmentationEngine`: Preprocessing (1024x1024 tensor normalization), ONNX session instantiation, execution provider fallback (CPU / DirectML), and 8-bit alpha matte post-processing.
   * `LightingEngine`: High-performance Pillow / NumPy adjustments for brightness, contrast, saturation, sharpness, and warmth.
   * `BackdropEngine`: Compositing solid colors (White Studio, Passport Grey, Corporate Navy, Custom), Gaussian blur, custom background image, or transparent PNG.
   * `CropEngine`: Aspect-ratio calculations and 300-DPI physical resampling for standard sizes (Indian Passport, Indian Stamp, US Visa, Custom).

### Phase 3: A4 Print Engine (`printer.py`)
1. Re-implement the 2D shelf bin-packing layout generator for A4 sheets (210mm × 297mm @ 300 DPI = 2481 × 3507 px).
2. Add support for margins (mm), inter-photo spacing (mm), and scissor cut guides.
3. Add native Qt print function: takes the PIL A4 sheet, converts to `QImage`, and sends it to `QPrinter` via `QPrintDialog` for 1:1 hardware printer output.

### Phase 4: Desktop Interface (`main.py`)
1. Construct the PySide6 main window with standard menus, status bar, and dockable/tabbed panels.
2. Build custom canvas widget supporting zoom, pan, and a draggable/resizable cropping bounding box (ROI).
3. Connect real-time slider signals to `engine.py` background workers to keep UI responsive.
4. Build the A4 Print Studio tab with queue management, editable table, and preview rendering.

### Phase 5: Testing & Packaging (PyInstaller on ARM64)
1. Test end-to-end functionality on Windows 11 ARM64.
2. Build PyInstaller spec targeting `win_arm64`.
3. Verify that the resulting `.exe` and bundled DLLs launch smoothly under Smart App Control.
