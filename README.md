# Local Photo & Print Studio 📸🖨️

A local, AI-powered photo editing and print preparation studio designed specifically for identity photos, visa/passport portraits, and multi-copy photo sheet printing.

The studio combines deep-learning background matting with deterministic image enhancements and a 2D shelf-packing layout engine that outputs print-ready, high-resolution (300 DPI) A4 sheets with physical dimension accuracy.

---

## 🎯 Purpose & Capabilities

Preparing official identification, visa, and passport photos usually requires multiple fragmented tools: background removers, photo editors, dimension croppers, and layout software to tile multiple copies onto photo paper. 

**Local Photo & Print Studio** provides an integrated, offline-capable pipeline that handles the entire workflow:
1. **Capture / Ingest**: Upload any portrait or capture directly via webcam.
2. **AI Background Extraction**: Extract clean subject cutouts with hair-level detail using local neural networks.
3. **Backdrop Replacement & Lighting**: Apply official backgrounds (White, Passport Grey, Corporate Navy, blur, or custom backdrops) and tune lighting independently on the subject or the whole frame.
4. **Standard Physical Sizing**: Crop to exact physical standards (Indian Passport/ID, Indian Stamp, US Visa, custom dimensions) at true 300 DPI.
5. **A4 Auto-Grid Packing**: Arrange arbitrary quantities of different photo sizes onto standard A4 paper with customizable margins, photo spacing, and cut guides.
6. **1:1 Physical Printing**: Print directly from the browser with zero margin scaling or export as a 300 DPI PNG.

---

## 🏗️ Architecture & Pipeline

The application is structured into modular layers separating the UI, neural inference, deterministic image processing, and print layout algorithms.

```
 ┌──────────────────────┐
 │  Input Photo         │  (Upload or Webcam)
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐      ┌───────────────────────────────┐
 │  AI Segmentation     │ ───► │ ONNX Runtime                  │
 │  (engine.py)         │      │ (MODNet / RMBG-1.4)           │
 └──────────┬───────────┘      └───────────────────────────────┘
            │ Alpha Mask
            ▼
 ┌──────────────────────┐
 │  Mask Refinement     │  (Threshold, Edge Feathering,
 └──────────┬───────────┘   Manual Brush Touch-up)
            │
            ▼
 ┌──────────────────────┐
 │  Lighting & Color    │  (Brightness, Contrast, Saturation,
 │  (Pillow / NumPy)    │   Sharpness, Dual-Channel Warmth)
 └──────────┬───────────┘  [Scope: Subject-Only or Whole-Image]
            │
            ▼
 ┌──────────────────────┐
 │  Compositing & Crop  │  (Backdrop synthesis, Aspect Crop,
 └──────────┬───────────┘   Physical DPI Resize)
            │
            ▼
 ┌──────────────────────┐
 │  A4 Shelf Packing    │  (printer.py: Shelf bin-packing,
 │  & Print Studio      │   Margins, Gaps, Scissor Guides)
 └──────────┬───────────┘
            │
      ┌─────┴──────────────────┐
      ▼                        ▼
┌──────────────┐       ┌─────────────────┐
│ Browser 1:1  │       │ 300 DPI PNG     │
│ Print Dialog │       │ Master Export   │
└──────────────┘       └─────────────────┘
```

### Module Breakdown

| Module | Responsibility |
| :--- | :--- |
| **[`app.py`](app.py)** | **UI & Orchestration**: Main entry point built with Gradio Blocks. Manages session states (`orig_state`, `mask_state`, `print_queue_state`), interactive controls, event routing, and tabbed workflow. |
| **[`engine.py`](engine.py)** | **Inference & Image Processing**: Handles ONNX model sessions, tensor preprocessing/postprocessing, alpha matting, lighting adjustments, manual mask brush editing, and dimension-accurate cropping. |
| **[`printer.py`](printer.py)** | **A4 Layout Engine**: Implements a 2D shelf bin-packing algorithm that places arbitrary photo tiles onto an A4 canvas (210mm × 297mm) at 300 DPI, enforcing margins, inter-photo gaps, and cutting guides. |
| **[`styles.py`](styles.py)** | **Layout & Print Styling**: Custom CSS defining the edge-to-edge 3-pane responsive studio workspace, independent sidebar scrolling, and zero-margin JavaScript print utility (`@page { size: A4 portrait; margin: 0; }`). |

---

## 🤖 AI Models & Hardware Acceleration

Background extraction is powered by local ONNX neural network models loaded via `huggingface_hub` and executed through `onnxruntime`:

### 1. MODNet (`Xenova/modnet`)
- **Specialty**: Portrait matting and human subject extraction.
- **Characteristics**: Excellent edge transparency around fine hair strands and complex silhouettes.
- **Preprocessing**: Dynamically calculates dimension multiples of 32 centered around a 512px reference constraint to preserve natural aspect ratios during inference.

### 2. RMBG-1.4 (`briaai/RMBG-1.4`)
- **Specialty**: Generalist salient object and subject segmentation.
- **Characteristics**: High boundary sharpness and contrast separation across diverse foreground subjects.
- **Preprocessing**: Standardized 1024×1024 tensor normalization.

### Hardware Execution Providers
`engine.py` dynamically queries available ONNX Runtime execution providers to maximize performance:
- `QNNExecutionProvider`: Qualcomm Snapdragon NPU acceleration.
- `DmlExecutionProvider`: DirectML acceleration for DirectX 12 compatible GPUs.
- `CPUExecutionProvider`: Universal CPU fallback.

---

## 🛠️ Key Features

### 1. Photo Editor Workspace (Tab 1)
- **Interactive Light & Color**:
  - Independent adjustments: Brightness, Contrast, Saturation, Sharpness, and Warmth.
  - Selective scoping: Adjust the **Whole Image** or isolate adjustments to **Subject Only** using the alpha mask.
- **Backdrop Modes**:
  - Original (No Cutout)
  - White Studio (`#FFFFFF`) — standard passport specification
  - Passport Grey (`#E5E7EB`)
  - Corporate Navy (`#1E293B`)
  - Custom Solid Color via color picker
  - Gaussian Background Blur (adjustable 5–50px radius)
  - Custom Backdrop Image
  - Transparent PNG export
  - Raw Mask Debug View
- **Mask Refinement & Manual Brush**:
  - Auto-mask tightness/threshold slider.
  - Gaussian edge feathering (0.0 to 5.0).
  - Built-in brush editor: paint black to erase background artifacts or paint white to restore clipped foreground features.
- **Preset Document Dimensions**:
  - **Indian Passport / ID**: 1.5" × 2.0" (3.5 × 4.5 cm)
  - **Indian Stamp Size**: 0.8" × 1.0"
  - **US Visa**: 2.0" × 2.0" (51 × 51 mm)
  - **Standard Ratios**: 1:1 Square, 3:4 Passport, 4:5 Portrait
  - **Custom Size**: User-defined width and height in inches.

### 2. A4 Print Studio (Tab 2)
- **Multi-Photo Queue**: Add edited photos with designated copy counts into a unified print queue.
- **Live Editable Dataframe**: Directly edit width, height, or copy counts in a spreadsheet-style table with instant layout recalculation.
- **Shelf Bin-Packing**: Automatically wraps photos row by row, keeping track of sheet bounds and reporting overflow warnings if counts exceed a single sheet.
- **Print Formatting Controls**:
  - Page margin adjustment (0 to 20 mm).
  - Photo gap spacing (0 to 15 mm).
  - Toggleable dashed cutting borders (`#9CA3AF`).
- **Precision Output**:
  - Direct 1:1 browser print popup formatted for borderless A4 portrait output.
  - High-res 300 DPI PNG download (2481 × 3507 pixels).

---

## 💻 Tech Stack

- **Framework**: [Gradio](https://github.com/gradio-app/gradio) (Responsive web UI, image canvas, state management)
- **AI / ML Runtime**: [ONNX Runtime](https://onnxruntime.ai/) (`onnxruntime`)
- **Model Distribution**: [Hugging Face Hub](https://huggingface.co/docs/huggingface_hub) (`huggingface_hub`)
- **Image Processing**: [Pillow](https://python-pillow.org/) (`PIL.Image`, `PIL.ImageEnhance`, `PIL.ImageFilter`, `PIL.ImageDraw`)
- **Numerical Computing**: [NumPy](https://numpy.org/) (Tensor normalization, channel shifting, alpha compositing)

---

## 📋 Repository Structure

```
photo_editor/
├── app.py              # Main Gradio application, state wiring & event handlers
├── engine.py           # ONNX model inference, color balance & mask processing
├── printer.py          # A4 shelf bin-packing layout engine (300 DPI)
├── styles.py           # Studio layout CSS & 1:1 JavaScript print handler
├── .gitignore          # Git exclusion rules
└── README.md           # Project documentation
```
