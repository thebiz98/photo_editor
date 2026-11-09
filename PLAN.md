# System Instructions & Technical Specification: Native Windows on ARM Photo & Print Studio

You are building a native Windows 11 ARM64 desktop application in Python using `PySide6-Essentials`, `Pillow`, `NumPy`, and `ONNXRuntime`.

## CRITICAL RULES FOR IMPLEMENTATION
1. **Zero Web Stack / Zero WSL:** Do NOT use Gradio, FastAPI, Uvicorn, web servers, browsers, or WSL. This is a 100% native Windows GUI application built with `PySide6` (Qt6).
2. **Synchronous Execution:** Do NOT use complex multi-threading (`QThread`) for inference. `RMBG-1.4` and `MODNet` run in `<0.5s` on Snapdragon X. Run inference synchronously on the main thread using `QApplication.setOverrideCursor(Qt.WaitCursor)` during the brief ONNX execution and restore it immediately inside a `try...finally` block.
3. **100% Offline Runtime & Bundled Models:** Assume `./models/rmbg14/model.onnx` and `./models/modnet/model.onnx` are bundled locally on disk for offline execution. In `download_models.py`, check if each local `.onnx` file already exists and is `>10 MB`; only download if missing. The main application (`main.py`, `engine.py`) must NEVER make network requests.
4. **No Manual Brush:** Do NOT implement a freehand painting brush. Edge cleanup is handled entirely by fast morphological `Edge Choke` (erosion) and `Edge Feather` (blur) sliders on the alpha matte.
5. **Deliverables:** Implement the application strictly following the specification below, outputting complete, self-contained, production-ready code for every file (`install.bat`, `download_models.py`, `engine.py`, `printer.py`, `main.py`, `PhotoStudio.bat`) with zero placeholders or omitted functions.

---

## 1. Environment & Directory Structure

### 1.1 Existing Verified Virtual Environment (`.\venv`)
- **OS & Architecture:** Windows 11 on ARM64 (Snapdragon X) with Windows Smart App Control (SAC) enabled.
- **Pre-installed & Verified in `.\venv`:** `numpy`, `pillow`, `onnxruntime`.

### 1.2 Target Directory Tree
```text
photo_editor/
├── venv/                      # Native Windows ARM64 Python Virtual Environment
├── models/
│   ├── rmbg14/
│   │   └── model.onnx         # briaai/RMBG-1.4 ONNX (~170 MB, input: 1024x1024)
│   └── modnet/
│       └── model.onnx         # MODNet Portrait Matting (~25 MB, input: 512x512)
├── install.bat                # Dependency installer & Smart App Control smoke test
├── download_models.py         # One-time local model downloader (skips if present)
├── engine.py                  # ONNX inference, ROI sub-region processor, edge filters, lighting
├── printer.py                 # 2D shelf bin-packing & QPrinter 1:1 hardware print engine
├── main.py                    # PySide6 GUI application (Photo Studio + A4 Print Studio tabs)
└── PhotoStudio.bat            # Zero-console desktop launcher using pythonw.exe
```

---

## 2. File-by-File Technical Specifications

### File 1: `install.bat`
Automates installing `PySide6-Essentials` (slim Qt6 binaries containing `QtCore`, `QtGui`, `QtWidgets`, `QtPrintSupport` without bloated WebEngine/3D DLLs) and `huggingface_hub`, runs a Smart App Control import verification, and triggers the one-time model check:
```bat
@echo off
cd /d "%~dp0"
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install PySide6-Essentials huggingface_hub
.\venv\Scripts\python.exe -c "from PySide6 import QtWidgets, QtGui, QtCore, QtPrintSupport; print('SAC Verification Passed!')"
.\venv\Scripts\python.exe download_models.py
.\venv\Scripts\python.exe -m pip freeze > install_info.txt
pause
```

---

### File 2: `download_models.py`
One-time setup script to populate `./models/` if the weights are not already bundled:
1. Create directories `./models/rmbg14` and `./models/modnet` if they do not exist.
2. Check if `./models/rmbg14/model.onnx` exists and `os.path.getsize(...) > 10_000_000`. If not, use `huggingface_hub.hf_hub_download(repo_id="briaai/RMBG-1.4", filename="onnx/model.onnx")` and copy/move the file to `./models/rmbg14/model.onnx`.
3. Check if `./models/modnet/model.onnx` exists and `os.path.getsize(...) > 10_000_000`. If not, use `huggingface_hub.hf_hub_download(repo_id="Xenova/modnet", filename="onnx/model.onnx")` (with fallback to `gradio/modnet` if needed) and save to `./models/modnet/model.onnx`.
4. Print clear progress and completion status.

---

### File 3: `engine.py` (Core Image, ROI Patching & Segmentation Engine)

#### 3.1 Physical Size & DPI Constants
- Base print resolution: `DPI = 300`, `PX_PER_MM = 300 / 25.4` (`11.8110236`).
- `PRESET_SIZES` dictionary mapping name to `(width_mm, height_mm, width_px, height_px)`:
  - `"Freeform / Original"`: `(None, None, None, None)`
  - `"Standard Passport (35 x 45 mm)"`: `(35.0, 45.0, 413, 531)`
  - `"Indian Passport / US Visa (2 x 2 in / 51 x 51 mm)"`: `(50.8, 50.8, 600, 600)`
  - `"PAN / Official ID Portrait (25 x 35 mm)"`: `(25.0, 35.0, 295, 413)`
  - `"Indian Stamp Size (20 x 25 mm)"`: `(20.0, 25.0, 236, 295)`
  - `"Standard ID Card Full (85.6 x 54.0 mm)"`: `(85.6, 54.0, 1011, 638)`
  - `"Custom Size (mm)"`: User-specified `(custom_w_mm, custom_h_mm)` converted via `round(mm * PX_PER_MM)`.

#### 3.2 `SegmentationEngine` Class
- Lazy-loads `onnxruntime.InferenceSession` for `"RMBG-1.4"` (`./models/rmbg14/model.onnx`) and `"MODNet"` (`./models/modnet/model.onnx`) using `providers=["CPUExecutionProvider"]`.
- **In-Memory Alpha Caching:** Store `(image_hash, model_name) -> raw_alpha_pil_image` so moving sliders (brightness, contrast, edge choke, edge feather, backdrop color) NEVER re-runs ONNX inference. Inference only executes when the input image/crop region changes or the user switches AI models.
- **RMBG-1.4 Inference Pipeline:**
  1. Convert input `PIL.Image` to `"RGB"`, record `(orig_w, orig_h)`, resize to `(1024, 1024)` via `Image.BILINEAR`.
  2. Convert to `float32` NumPy array scaled `[0.0, 1.0]`.
  3. Normalize: `tensor = (img_np - 0.5) / 1.0`.
  4. Transpose `(H, W, C)` -> `(1, 3, 1024, 1024)` (`np.ascontiguousarray`).
  5. Run `session.run(None, {input_name: tensor})[0][0][0]`.
  6. Post-process: `matte = (pred - pred.min()) / (pred.max() - pred.min() + 1e-8)`, convert to `(matte * 255).clip(0, 255).astype(np.uint8)`, convert to `PIL.Image` mode `"L"`, resize to `(orig_w, orig_h)` using `Image.LANCZOS`.
- **MODNet Inference Pipeline:**
  1. Convert input `PIL.Image` to `"RGB"`, record `(orig_w, orig_h)`, resize to `(512, 512)` via `Image.BILINEAR`.
  2. Convert to `float32` scaled `[0.0, 1.0]`, normalize via `(img_np - 0.5) / 0.5` (range `[-1.0, 1.0]`).
  3. Transpose to `(1, 3, 512, 512)`, run inference, extract 2D matte `[0][0]`, scale `[0.0, 1.0]` to `0..255` `uint8`, resize to `(orig_w, orig_h)` using `Image.LANCZOS`.

#### 3.3 Morphological Edge Refinement (`refine_alpha(alpha_img, choke_px, feather_px)`)
Replaces manual brushing in `<5 ms`:
1. **Choke / Erosion (`choke_px`: `int` `0` to `5`):**
   - If `choke_px > 0`, apply `alpha_img = alpha_img.filter(ImageFilter.MinFilter(size=choke_px * 2 + 1))`. This eliminates 1–5 px of background halo/bleed around hair and shoulders.
2. **Feather / Blur (`feather_px`: `float` `0.0` to `5.0`):**
   - If `feather_px > 0`, apply `alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=feather_px))`.

#### 3.4 Deterministic Lighting & Color Pipeline (`apply_lighting(pil_img, params)`)
Applies adjustments in order to an RGB `PIL.Image`:
- `brightness` (`0.5` to `1.5`, default `1.0`): `ImageEnhance.Brightness(img).enhance(brightness)`
- `contrast` (`0.5` to `1.5`, default `1.0`): `ImageEnhance.Contrast(img).enhance(contrast)`
- `saturation` (`0.0` to `2.0`, default `1.0`): `ImageEnhance.Color(img).enhance(saturation)`
- `sharpness` (`0.0` to `3.0`, default `1.0`): `ImageEnhance.Sharpness(img).enhance(sharpness)`
- `warmth` (`-30` to `+30`, default `0`): Convert to `int16` NumPy array; add `warmth` to Red channel `arr[:, :, 0]`, subtract `warmth` from Blue channel `arr[:, :, 2]`; `np.clip(arr, 0, 255).astype(np.uint8)`.

#### 3.5 Backdrop Compositing (`composite_backdrop(fg_rgb, orig_rgb, refined_alpha, backdrop_mode, custom_color_rgb)`)
- If `remove_bg` is `False`: return `fg_rgb` directly.
- If `remove_bg` is `True`:
  - Determine background `bg_img` of same `(W, H)`:
    - `"Studio White"`: Solid `(255, 255, 255)`
    - `"Passport Grey"`: Solid `(230, 230, 230)`
    - `"Standard Blue"`: Solid `(0, 82, 180)`
    - `"Corporate Navy"`: Solid `(27, 54, 93)`
    - `"Soft Blur"`: `orig_rgb.filter(ImageFilter.GaussianBlur(radius=15))`
    - `"Custom Color"`: Solid `custom_color_rgb`
  - Composite via `Image.composite(fg_rgb, bg_img, refined_alpha)`.

#### 3.6 Dual-Mode ROI Box Processing (`process_image_pipeline(full_img, roi_box, roi_mode, params)`)
`roi_box` is `(x1, y1, x2, y2)` in image pixel coordinates (clamped to image bounds):
1. **Mode 0: `"Whole Image"`**
   - Process the entire `full_img` through `apply_lighting` and optional `SegmentationEngine` + `refine_alpha` + `composite_backdrop`.
   - If a target preset size is selected, resize/crop to target `(width_px, height_px)` using `ImageOps.fit(result, (width_px, height_px), method=Image.LANCZOS)`.
2. **Mode 1: `"Edit Inside Box Only (Patch Document/ID)"`**
   - Designed for selecting a sub-region (like the portrait photo on a scanned ID card), fixing its lighting/background, and keeping it embedded inside the full document.
   - Crop `sub_patch = full_img.crop((x1, y1, x2, y2))`.
   - Run `apply_lighting` and (if `remove_bg=True`) segmentation + edge refinement + backdrop compositing **exclusively on `sub_patch`**.
   - Paste `sub_patch` back onto a copy of `full_img` at `(x1, y1)` and return the full modified document.
3. **Mode 2: `"Crop to Box (Extract Standalone Photo)"`**
   - Crop `cropped = full_img.crop((x1, y1, x2, y2))`.
   - Run `apply_lighting` and optional segmentation + edge refinement + backdrop compositing on `cropped`.
   - If a target physical preset size is active, resize `cropped` to `(width_px, height_px)` via `Image.LANCZOS`.

---

### File 4: `printer.py` (A4 2D Shelf Bin-Packing & 1:1 Hardware Print Engine)

#### 4.1 A4 Constants & Bin-Packing (`generate_a4_sheet(queue_items, margin_mm=10.0, gap_mm=2.0, draw_cut_lines=True)`)
- **A4 @ 300 DPI Canvas:** `A4_W = 2480`, `A4_H = 3508` pixels, white RGB `(255, 255, 255)`.
- Convert `margin_px = round(margin_mm * PX_PER_MM)` and `gap_px = round(gap_mm * PX_PER_MM)`.
- Each entry in `queue_items` contains: `{"image": pil_img, "width_mm": w_mm, "height_mm": h_mm, "copies": int_copies, "label": str}`.
- For each copy of each item:
  - Target pixel size: `w_px = round(w_mm * PX_PER_MM)`, `h_px = round(h_mm * PX_PER_MM)`.
  - Resize `pil_img` to `(w_px, h_px)` using `Image.LANCZOS`.
  - **2D Shelf Packing:**
    - Start at `cursor_x = margin_px`, `cursor_y = margin_px`, `shelf_height = 0`.
    - If `cursor_x + w_px > A4_W - margin_px`: move to next row (`cursor_x = margin_px`, `cursor_y += shelf_height + gap_px`, `shelf_height = 0`).
    - If `cursor_y + h_px > A4_H - margin_px`: stop placing and increment `overflow_count`.
    - Paste resized item at `(cursor_x, cursor_y)`.
    - If `draw_cut_lines` is `True`: use `ImageDraw.Draw(canvas).rectangle([cursor_x, cursor_y, cursor_x + w_px - 1, cursor_y + h_px - 1], outline=(200, 200, 200), width=1)` so white-background passport photos have clean scissor cut guides on white paper.
    - Advance `cursor_x += w_px + gap_px`, `shelf_height = max(shelf_height, h_px)`.
- Return `(canvas_pil, placed_count, overflow_count)`.

#### 4.2 True 1:1 Physical Hardware Printing (`print_a4_hardware(parent_widget, a4_pil_image)`)
Prevents Windows printer drivers from adding extra margins and shrinking `35x45mm` passport photos:
```python
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtGui import QPainter, QPageSize, QPageLayout, QImage
from PySide6.QtCore import QMarginsF

def pil_to_qimage(pil_img):
    rgb = pil_img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)
    return qimg.copy()

def print_a4_hardware(parent_widget, a4_pil_image):
    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageOrientation(QPageLayout.Portrait)
    printer.setFullPage(True)
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)

    dialog = QPrintDialog(printer, parent_widget)
    if dialog.exec() == QPrintDialog.Accepted:
        qimg = pil_to_qimage(a4_pil_image)
        painter = QPainter(printer)
        target_rect = painter.viewport()
        painter.drawImage(target_rect, qimg, qimg.rect())
        painter.end()
        return True
    return False
```
- Also implement `export_a4_png(a4_pil_image, filepath)` (`a4_pil_image.save(filepath, "PNG", dpi=(300, 300))`) and `export_a4_pdf(a4_pil_image, filepath)` (`a4_pil_image.save(filepath, "PDF", resolution=300.0)`).

---

### File 5: `main.py` (Native PySide6 Desktop GUI)

#### 5.1 Custom `InteractiveCanvas(QGraphicsView)` Widget
- Displays the active `QPixmap` inside a `QGraphicsScene`.
- **Interactive Rubber-Band / Handle ROI Box:**
  - Allows the user to left-click and drag to draw or resize a visible cyan/yellow dashed selection rectangle `(x1, y1, x2, y2)` over any region of the image (e.g., around the portrait inside an ID card or around a person's head/shoulders).
  - If `"Crop to Box"` mode is active and a fixed-aspect preset (like `35x45mm`) is selected, optionally constrain or snap the box aspect ratio to match the preset.
  - Emits `roiChanged` signal on mouse release so the preview updates automatically.
- **Navigation & Drag-and-Drop:**
  - Mouse wheel zooms smoothly (`scale(1.15, 1.15)` / `scale(1/1.15, 1/1.15)`).
  - Middle-mouse button (or `Space + Left Drag`) pans the view.
  - Accepts file Drag-and-Drop (`dragEnterEvent`, `dropEvent`) for `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`.

#### 5.2 Global Shortcuts
- `Ctrl + V`: Reads image from `QApplication.clipboard().image()` or file URLs from `mimeData()`, converts to `PIL.Image`, adds to workspace, and selects it immediately.

#### 5.3 Main Window Dual-Tab Layout (`QTabWidget`)

##### Tab 1: `📸 Photo Studio` (3-Column Splitter Layout)
1. **Left Panel (Workspace & Region Mode, ~270px width):**
   - Buttons: `📂 Add Photo(s)`, `📋 Paste Clipboard (Ctrl+V)`, `🗑️ Remove Selected`.
   - `QListWidget` displaying loaded photos with small thumbnails.
   - **Box Selection Mode (`QButtonGroup` / Radio Buttons):**
     - `Whole Image (Ignore Box)`
     - `Edit Inside Box Only (Patch ID / Document)`
     - `Crop to Box (Extract Standalone Photo)`
   - Button: `✔️ Bake / Commit Current Edit to Image` (Applies the current box/lighting edit permanently into the base workspace image so the user can subsequently draw a new box on another area or crop the whole card).
   - **Physical Output Size Preset (`QComboBox`):**
     - Lists all `PRESET_SIZES` plus two `QDoubleSpinBox` inputs (`Width mm`, `Height mm`) that enable when `"Custom Size (mm)"` is selected.
2. **Center Panel (Interactive Canvas + Top Toolbar):**
   - Toolbar buttons: `🔍+ Zoom In`, `🔍- Zoom Out`, `📐 Fit to Window`, `🔄 Rotate 90° CW`, `⬜ Reset Selection Box`, `👁️ Hold to Compare Original`.
   - `InteractiveCanvas` widget.
3. **Right Panel (AI Segmentation, Edge Refinement & Lighting, ~310px width):**
   - **AI Background GroupBox:**
     - `QCheckBox`: `Enable AI Background Removal` (Default: `False` so document/ID edits are instant unless segmentation is toggled on).
     - `QComboBox`: `AI Model` -> `["RMBG-1.4 (High Precision)", "MODNet (Fast Portrait)"]`.
     - `QComboBox`: `Backdrop` -> `["Studio White", "Passport Grey", "Standard Blue", "Corporate Navy", "Soft Blur", "Custom Solid Color..."]`.
     - Button: `Pick Custom Color` (opens `QColorDialog`).
     - **Morphological Edge Refinement Sliders:**
       - `Edge Choke / Halo Removal (0 to 5 px)` (`QSlider` + value label)
       - `Edge Feather / Smooth (0.0 to 5.0 px)` (`QSlider` + value label)
   - **Lighting & Color GroupBox:**
     - Sliders with live value labels and a `Reset Lighting` button:
       - `Brightness` (`50%` to `150%`, default `100%`)
       - `Contrast` (`50%` to `150%`, default `100%`)
       - `Saturation` (`0%` to `200%`, default `100%`)
       - `Sharpness` (`0%` to `300%`, default `100%`)
       - `Warmth` (`-30` to `+30`, default `0`)
   - **Bottom Action Buttons:**
     - `💾 Save Single Photo (PNG/JPG)`
     - `➕ Send to A4 Print Queue` (Sends processed image along with its physical millimeter dimensions to Tab 2 and shows confirmation in status bar).

##### Tab 2: `🖨️ A4 Print Studio` (2-Column Layout)
1. **Left Panel (Print Queue & Layout Controls, ~360px width):**
   - `QTableWidget` with columns: `[Preview | Size (mm) | Copies (QSpinBox 1-50) | Remove]`.
   - Changing any copy count spinbox immediately regenerates the live A4 preview.
   - Button: `🗑️ Clear Entire Queue`.
   - **Page Layout Settings GroupBox:**
     - `Page Margin (mm)`: `QDoubleSpinBox` (`0.0` to `30.0`, default `10.0 mm`).
     - `Gap Between Photos (mm)`: `QDoubleSpinBox` (`0.0` to `20.0`, default `2.0 mm`).
     - `QCheckBox`: `Draw Light-Grey Scissor Cut Lines` (default `Checked`).
   - Status Label showing `"Placed: X photos | Overflow: Y photos"`.
2. **Right Panel (Live A4 Preview & Hardware Export):**
   - Zoomable/fitted preview of the `2480 x 3508` A4 sheet rendered with a clean drop-shadow border.
   - **Primary Output Bar:**
     - `🖨️ Print Directly (1:1 Hardware A4)` -> calls `print_a4_hardware`
     - `💾 Save 300-DPI A4 PNG` -> calls `export_a4_png`
     - `📄 Save 300-DPI A4 PDF` -> calls `export_a4_pdf`

---

### File 6: `PhotoStudio.bat` (Zero-Console Desktop Launcher)
Launches the GUI using `pythonw.exe` so no command prompt window ever appears:
```bat
@echo off
cd /d "%~dp0"
start "" ".\venv\Scripts\pythonw.exe" main.py
```