"""
main.py - Native Windows 11 ARM64 Photo Studio & A4 Print Studio.
Pure PySide6 desktop application with 100% offline ONNX inference and 1:1 hardware printing.
"""

import sys
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from PySide6.QtCore import (
    Qt, QRectF, QPointF, Signal, Slot, QMarginsF, QSize, QMimeData, QThread
)
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QBrush, QColor, QKeySequence,
    QShortcut, QAction, QIcon, QCursor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QGroupBox, QLabel, QSlider, QComboBox,
    QCheckBox, QPushButton, QRadioButton, QButtonGroup, QSpinBox,
    QDoubleSpinBox, QFileDialog, QColorDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
    QGraphicsItem, QFrame, QStatusBar, QSizePolicy, QAbstractItemView,
    QScrollArea, QGridLayout, QLayout
)
from PIL import Image

import engine
import printer
import rescaler
from styles import DARK_THEME_QSS


PRESET_MAP = {
    "Freeform / Original": None,
    "Standard Passport (35 x 45 mm)": (35.0, 45.0),
    "Indian Passport / US Visa (2 x 2 in)": (50.8, 50.8),
    "PAN / ID Portrait (25 x 35 mm)": (25.0, 35.0),
    "Indian Stamp Size (20 x 25 mm)": (20.0, 25.0),
    "Standard ID Card (85.6 x 54 mm)": (85.6, 54.0),
    "Custom Size": None,
}


from canvas import InteractiveCanvas, pil_to_pixmap
from print_studio import PrintStudioTab


class NoWheelSlider(QSlider):
    """QSlider that ignores mouse wheel events to prevent accidental value changes and allow parent scroll areas to scroll smoothly."""
    def wheelEvent(self, event):
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """QSpinBox that ignores mouse wheel events to prevent accidental value changes."""
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that ignores mouse wheel events to prevent accidental dimension changes."""
    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events when closed to prevent accidental preset/unit switching while scrolling."""
    def wheelEvent(self, event):
        event.ignore()


class SuperResWorker(QThread):
    """Background worker for non-blocking neural super-resolution inference."""
    finished = Signal(object)  # Emits enhanced PIL.Image
    error = Signal(str)

    def __init__(self, img: Image.Image):
        super().__init__()
        self.img = img

    def run(self):
        try:
            enhanced = rescaler.GLOBAL_SUPERRES_ENGINE.enhance_2x(self.img)
            self.finished.emit(enhanced)
        except Exception as e:
            self.error.emit(str(e))


class PhotoStudioApp(QMainWindow):
    """Main window with dual Photo Studio and A4 Print Studio tabs."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Native Windows ARM64 Photo Studio & Print Engine")
        self.resize(1340, 880)
        self.setMinimumSize(1000, 700)

        # In-memory photo workspace
        # List of items: {"id": int, "name": str, "orig": PIL.Image, "baked": PIL.Image, "processed": PIL.Image, "roi": tuple, "params": dict}
        self.workspace_photos: List[Dict[str, Any]] = []
        self.current_photo_idx: int = -1
        self._block_signals: bool = False
        self._custom_bg_color: Tuple[int, int, int] = (255, 255, 255)
        self._current_unit: str = "mm"
        self._dim_w_mm: float = 35.0
        self._dim_h_mm: float = 45.0

        # Print queue: List of {"image": PIL.Image, "width_mm": float, "height_mm": float, "copies": int, "label": str}

        self._setup_ui()
        self._setup_shortcuts()
        self._apply_dark_style()
        self.statusBar().showMessage("Ready - 100% Offline Native Windows ARM64 Studio")

    def _setup_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 1: Photo Studio
        self.tab_studio = QWidget()
        self._build_studio_tab(self.tab_studio)
        self.tabs.addTab(self.tab_studio, "📸 Photo Studio")

        # Tab 2: A4 Print Studio
        self.tab_printer = PrintStudioTab(status_bar_callback=self.statusBar().showMessage)
        self.tabs.addTab(self.tab_printer, "🖨️ A4 Print Studio")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _build_studio_tab(self, parent_widget: QWidget):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # 1. Left Panel (Workspace & ROI Mode) - Compact width, NO horizontal scroll
        left_panel = QWidget()
        left_panel.setMinimumWidth(240)
        left_panel.setMaximumWidth(300)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(5)

        # Photo list group
        grp_workspace = QGroupBox("📁 Photo Workspace")
        grp_workspace_layout = QVBoxLayout(grp_workspace)
        grp_workspace_layout.setSpacing(5)

        btn_row_1 = QHBoxLayout()
        btn_row_1.setSpacing(4)
        self.btn_add_photos = QPushButton("📂 Add")
        self.btn_add_photos.setToolTip("Open photo(s) from disk")
        self.btn_add_photos.clicked.connect(self._on_open_files)
        self.btn_paste = QPushButton("📋 Paste")
        self.btn_paste.setToolTip("Paste image from clipboard (Ctrl+V)")
        self.btn_paste.clicked.connect(self._on_paste_clipboard)
        btn_row_1.addWidget(self.btn_add_photos)
        btn_row_1.addWidget(self.btn_paste)
        grp_workspace_layout.addLayout(btn_row_1)

        self.list_photos = QListWidget()
        self.list_photos.setIconSize(QSize(40, 40))
        self.list_photos.setMinimumHeight(110)
        self.list_photos.setMaximumHeight(150)
        self.list_photos.currentRowChanged.connect(self._on_photo_selected)
        grp_workspace_layout.addWidget(self.list_photos)

        self.btn_remove_photo = QPushButton("🗑️ Remove Selected")
        self.btn_remove_photo.clicked.connect(self._on_remove_photo)
        grp_workspace_layout.addWidget(self.btn_remove_photo)
        left_layout.addWidget(grp_workspace)

        # Retouch Scope (Lighting & Local Patching)
        grp_roi_mode = QGroupBox("🎯 Retouch Scope")
        grp_roi_layout = QVBoxLayout(grp_roi_mode)
        grp_roi_layout.setSpacing(3)
        self.bg_roi_mode = QButtonGroup(self)

        self.radio_mode_whole = QRadioButton("Whole Image")
        self.radio_mode_patch = QRadioButton("Edit Inside Box (Patch)")
        self.radio_mode_whole.setChecked(True)

        self.bg_roi_mode.addButton(self.radio_mode_whole, 0)
        self.bg_roi_mode.addButton(self.radio_mode_patch, 1)
        self.bg_roi_mode.idClicked.connect(self._on_roi_mode_changed)

        grp_roi_layout.addWidget(self.radio_mode_whole)
        grp_roi_layout.addWidget(self.radio_mode_patch)

        self.btn_bake_edit = QPushButton("✔️ Bake Edits to Base")
        self.btn_bake_edit.setToolTip("Permanently commits current patch or lighting into image base")
        self.btn_bake_edit.clicked.connect(self._on_bake_edit)
        grp_roi_layout.addWidget(self.btn_bake_edit)
        left_layout.addWidget(grp_roi_mode)

        # Crop & Physical Preset Sizes
        grp_preset = QGroupBox("📏 Crop && Physical Sizing")
        grp_preset_layout = QVBoxLayout(grp_preset)
        grp_preset_layout.setSpacing(5)

        self.combo_presets = NoWheelComboBox()
        for preset_name in PRESET_MAP.keys():
            self.combo_presets.addItem(preset_name)
        self.combo_presets.currentTextChanged.connect(self._on_preset_changed)
        grp_preset_layout.addWidget(self.combo_presets)

        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel("Unit:"))
        self.combo_unit = NoWheelComboBox()
        self.combo_unit.addItems(["mm", "in", "px"])
        self.combo_unit.currentTextChanged.connect(self._on_unit_changed)
        unit_row.addWidget(self.combo_unit)
        grp_preset_layout.addLayout(unit_row)

        dim_grid = QGridLayout()
        dim_grid.setContentsMargins(0, 2, 0, 0)
        dim_grid.setSpacing(5)

        lbl_w = QLabel("Width:")
        self.spin_custom_w = NoWheelDoubleSpinBox()
        self.spin_custom_w.setRange(5.0, 1000.0)
        self.spin_custom_w.setValue(35.0)
        self.spin_custom_w.setSingleStep(1.0)
        self.spin_custom_w.setDecimals(1)
        self.spin_custom_w.setSuffix(" mm")
        self.spin_custom_w.valueChanged.connect(self._on_spinbox_dimension_changed)

        lbl_h = QLabel("Height:")
        self.spin_custom_h = NoWheelDoubleSpinBox()
        self.spin_custom_h.setRange(5.0, 1000.0)
        self.spin_custom_h.setValue(45.0)
        self.spin_custom_h.setSingleStep(1.0)
        self.spin_custom_h.setDecimals(1)
        self.spin_custom_h.setSuffix(" mm")
        self.spin_custom_h.valueChanged.connect(self._on_spinbox_dimension_changed)

        dim_grid.addWidget(lbl_w, 0, 0)
        dim_grid.addWidget(self.spin_custom_w, 0, 1)
        dim_grid.addWidget(lbl_h, 1, 0)
        dim_grid.addWidget(self.spin_custom_h, 1, 1)
        grp_preset_layout.addLayout(dim_grid)

        self.btn_apply_crop = QPushButton("✂️ Apply Crop / Dimensions")
        self.btn_apply_crop.setObjectName("btn_apply_crop")
        self.btn_apply_crop.clicked.connect(self._on_apply_crop)
        grp_preset_layout.addWidget(self.btn_apply_crop)

        left_layout.addWidget(grp_preset)
        left_layout.addStretch()

        splitter.addWidget(left_panel)

        # 2. Center Panel (Interactive Canvas + Top Toolbar)
        center_panel = QWidget()
        center_panel.setMinimumWidth(380)
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(6)

        # Top Toolbar - clean, non-clipped labels with full tooltips
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_zoom_in = QPushButton("🔍+")
        self.btn_zoom_in.setToolTip("Zoom In (Mouse Wheel Up)")
        self.btn_zoom_in.clicked.connect(lambda: self.canvas.zoom(1.2))

        self.btn_zoom_out = QPushButton("🔍-")
        self.btn_zoom_out.setToolTip("Zoom Out (Mouse Wheel Down)")
        self.btn_zoom_out.clicked.connect(lambda: self.canvas.zoom(1 / 1.2))

        self.btn_fit = QPushButton("📐 Fit")
        self.btn_fit.setToolTip("Fit Image to Window")
        self.btn_fit.clicked.connect(lambda: self.canvas.fit_image())

        self.btn_rotate = QPushButton("🔄 Rotate")
        self.btn_rotate.setToolTip("Rotate 90° Clockwise")
        self.btn_rotate.clicked.connect(self._on_rotate_90)

        self.btn_reset_roi = QPushButton("⬜ Reset")
        self.btn_reset_roi.setToolTip("Reset / Clear Selection Box")
        self.btn_reset_roi.clicked.connect(self._on_reset_roi)

        self.btn_undo = QPushButton("↩️ Undo")
        self.btn_undo.setToolTip("Undo Last Action / Crop (Ctrl+Z)")
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_undo.setEnabled(False)

        self.btn_revert = QPushButton("⏮️ Revert")
        self.btn_revert.setToolTip("Revert Photo to Pristine Original State")
        self.btn_revert.clicked.connect(self._on_revert_to_original)

        self.btn_compare = QPushButton("👁️ Compare")
        self.btn_compare.setToolTip("Hold to Compare Original (Unedited) Photo")
        self.btn_compare.pressed.connect(self._on_compare_pressed)
        self.btn_compare.released.connect(self._on_compare_released)

        self.btn_send_queue = QPushButton("➕ Print")
        self.btn_send_queue.setObjectName("btn_send_queue")
        self.btn_send_queue.setToolTip("Add Current Photo to A4 Print Queue")
        self.btn_send_queue.clicked.connect(self._on_send_to_print_queue)

        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.btn_fit)
        toolbar.addWidget(self.btn_rotate)
        toolbar.addWidget(self.btn_reset_roi)
        toolbar.addWidget(self.btn_undo)
        toolbar.addWidget(self.btn_revert)
        toolbar.addWidget(self.btn_compare)
        toolbar.addWidget(self.btn_send_queue)
        toolbar.addStretch()
        center_layout.addLayout(toolbar)

        # Canvas
        self.canvas = InteractiveCanvas()
        self.canvas.roiChanged.connect(self._on_canvas_roi_changed)
        self.canvas.filesDropped.connect(self._load_image_paths)
        center_layout.addWidget(self.canvas)

        splitter.addWidget(center_panel)

        # 3. Right Panel (AI Segmentation, Lighting & Resolution)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setMinimumWidth(260)
        right_scroll.setMaximumWidth(450)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 10, 8)
        right_layout.setSpacing(5)

        # AI Background Group
        grp_ai = QGroupBox("🤖 AI Background Removal")
        grp_ai_layout = QVBoxLayout(grp_ai)
        grp_ai_layout.setSpacing(4)

        self.chk_remove_bg = QCheckBox("Enable AI Background Removal")
        self.chk_remove_bg.setChecked(False)
        self.chk_remove_bg.toggled.connect(self._on_ai_toggled)
        grp_ai_layout.addWidget(self.chk_remove_bg)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self.combo_ai_model = NoWheelComboBox()
        self.combo_ai_model.addItems(["RMBG-1.4 (High Precision)", "MODNet (Fast Portrait)"])
        self.combo_ai_model.currentTextChanged.connect(lambda _: self._trigger_render())
        model_row.addWidget(self.combo_ai_model)
        grp_ai_layout.addLayout(model_row)

        backdrop_row = QHBoxLayout()
        backdrop_row.addWidget(QLabel("Backdrop:"))
        self.combo_backdrop = NoWheelComboBox()
        self.combo_backdrop.addItems([
            "Studio White", "Passport Grey", "Standard Blue",
            "Corporate Navy", "Soft Blur", "Custom Solid Color..."
        ])
        self.combo_backdrop.currentTextChanged.connect(self._on_backdrop_changed)
        backdrop_row.addWidget(self.combo_backdrop)
        grp_ai_layout.addLayout(backdrop_row)

        self.btn_pick_color = QPushButton("🎨 Pick Custom Color")
        self.btn_pick_color.setObjectName("btn_pick_color")
        self.btn_pick_color.setEnabled(False)
        self.btn_pick_color.clicked.connect(self._on_pick_custom_color)
        grp_ai_layout.addWidget(self.btn_pick_color)

        # Edge refinement - full sliders with reduced panel length
        lbl_choke_row = QHBoxLayout()
        lbl_choke_row.addWidget(QLabel("Edge Choke (Halo Cut):"))
        lbl_choke_row.addStretch()
        self.lbl_choke_val = QLabel("0 px")
        lbl_choke_row.addWidget(self.lbl_choke_val)
        grp_ai_layout.addLayout(lbl_choke_row)

        self.slider_choke = NoWheelSlider(Qt.Horizontal)
        self.slider_choke.setRange(0, 5)
        self.slider_choke.setValue(0)
        self.slider_choke.valueChanged.connect(self._on_choke_changed)
        grp_ai_layout.addWidget(self.slider_choke)

        lbl_feather_row = QHBoxLayout()
        lbl_feather_row.addWidget(QLabel("Edge Feather (Softness):"))
        lbl_feather_row.addStretch()
        self.lbl_feather_val = QLabel("0.0 px")
        lbl_feather_row.addWidget(self.lbl_feather_val)
        grp_ai_layout.addLayout(lbl_feather_row)

        self.slider_feather = NoWheelSlider(Qt.Horizontal)
        self.slider_feather.setRange(0, 50)
        self.slider_feather.setValue(0)
        self.slider_feather.valueChanged.connect(self._on_feather_changed)
        grp_ai_layout.addWidget(self.slider_feather)

        right_layout.addWidget(grp_ai)

        # Lighting & Color Adjustments Group - full sliders with reduced panel length
        grp_lighting = QGroupBox("☀️ Lighting && Color Grading")
        grp_lighting_layout = QVBoxLayout(grp_lighting)
        grp_lighting_layout.setSpacing(3)

        # Helper to create slider rows (title + value header, slider beneath)
        def create_slider(name: str, min_v: int, max_v: int, def_v: int, suffix: str = "%"):
            header = QHBoxLayout()
            lbl_title = QLabel(name)
            lbl_val = QLabel(f"{def_v}{suffix}")
            header.addWidget(lbl_title)
            header.addStretch()
            header.addWidget(lbl_val)
            slider = NoWheelSlider(Qt.Horizontal)
            slider.setRange(min_v, max_v)
            slider.setValue(def_v)
            slider.valueChanged.connect(lambda v: lbl_val.setText(f"{v}{suffix}"))
            slider.valueChanged.connect(lambda _: self._trigger_render())
            grp_lighting_layout.addLayout(header)
            grp_lighting_layout.addWidget(slider)
            return slider, lbl_val

        self.slider_bright, self.lbl_bright = create_slider("Brightness", 50, 150, 100)
        self.slider_contrast, self.lbl_contrast = create_slider("Contrast", 50, 150, 100)
        self.slider_sat, self.lbl_sat = create_slider("Saturation", 0, 200, 100)
        self.slider_sharp, self.lbl_sharp = create_slider("Sharpness", 0, 300, 100)
        self.slider_warmth, self.lbl_warmth = create_slider("Warmth", -30, 30, 0, "")

        self.btn_reset_lighting = QPushButton("🔄 Reset Lighting")
        self.btn_reset_lighting.clicked.connect(self._on_reset_lighting)
        grp_lighting_layout.addWidget(self.btn_reset_lighting)

        right_layout.addWidget(grp_lighting)

        # -------------------------------------------------------------------------
        # Resolution & Scaling Group (rescaler.py integration)
        # -------------------------------------------------------------------------
        grp_rescale = QGroupBox("📐 Resolution && Scaling")
        grp_rescale_layout = QVBoxLayout(grp_rescale)
        grp_rescale_layout.setSpacing(5)

        # Current Resolution Display
        self.lbl_current_res = QLabel("Current: None")
        self.lbl_current_res.setStyleSheet("color: #a1a1aa; font-weight: normal;")
        grp_rescale_layout.addWidget(self.lbl_current_res)

        # Scale Percentage SpinBox
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Scale:"))
        self.spin_rescale_pct = NoWheelSpinBox()
        self.spin_rescale_pct.setRange(rescaler.MIN_SCALE_PCT, rescaler.MAX_SCALE_PCT)
        self.spin_rescale_pct.setValue(100)
        self.spin_rescale_pct.setSingleStep(10)
        self.spin_rescale_pct.setSuffix(" %")
        self.spin_rescale_pct.valueChanged.connect(self._on_rescale_pct_changed)
        scale_row.addWidget(self.spin_rescale_pct)
        grp_rescale_layout.addLayout(scale_row)

        # Target Resolution Live Preview Label
        self.lbl_target_res = QLabel("Result: 100% (Original)")
        self.lbl_target_res.setStyleSheet("color: #38bdf8; font-size: 11px;")
        grp_rescale_layout.addWidget(self.lbl_target_res)

        # Apply Scale Button
        self.btn_apply_scale = QPushButton("⚡ Apply Scale")
        self.btn_apply_scale.setObjectName("btn_apply_scale")
        self.btn_apply_scale.setToolTip("Apply compute-based Lanczos rescaling to current image")
        self.btn_apply_scale.clicked.connect(self._on_apply_rescale)
        grp_rescale_layout.addWidget(self.btn_apply_scale)

        # AI Enhance Container
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("color: #3f3f46; margin: 4px 0;")
        grp_rescale_layout.addWidget(sep)

        self.btn_ai_enhance = QPushButton("✨ AI Enhance (2x)")
        self.btn_ai_enhance.setObjectName("btn_ai_enhance")
        self.btn_ai_enhance.setToolTip("Reconstruct sharp details and textures using offline AI (for blurry/small photos)")
        self.btn_ai_enhance.clicked.connect(self._on_ai_enhance_clicked)
        grp_rescale_layout.addWidget(self.btn_ai_enhance)

        right_layout.addWidget(grp_rescale)

        # Bottom Actions
        self.btn_save_photo = QPushButton("💾 Save Single Photo (PNG/JPG)")
        self.btn_save_photo.clicked.connect(self._on_save_single_photo)
        right_layout.addWidget(self.btn_save_photo)

        right_layout.addStretch()
        right_scroll.setWidget(right_panel)
        splitter.addWidget(right_scroll)

        # Configure splitter behavior: fixed side panes, center expands
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([250, 815, 275])


    def _setup_shortcuts(self):
        # Global Ctrl+V clipboard paste shortcut
        paste_shortcut = QShortcut(QKeySequence.Paste, self)
        paste_shortcut.activated.connect(self._on_paste_clipboard)

        # Global Ctrl+Z undo shortcut
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self._on_undo)

    def _apply_dark_style(self):
        self.setStyleSheet(DARK_THEME_QSS)

    # -------------------------------------------------------------------------
    # Workspace & Photo Management
    # -------------------------------------------------------------------------

    def _on_open_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Open Image(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All Files (*.*)"
        )
        if files:
            self._load_image_paths(files)

    def _load_image_paths(self, paths: List[str]):
        new_indices = []
        for p in paths:
            try:
                img = Image.open(p).convert("RGB")
                filename = Path(p).name
                idx = self._add_photo_to_workspace(img, filename)
                new_indices.append(idx)
            except Exception as e:
                QMessageBox.warning(self, "Load Error", f"Could not load image:\n{p}\n\nError: {e}")

        if new_indices:
            self.list_photos.setCurrentRow(new_indices[-1])

    def _on_paste_clipboard(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        # Check for image data directly
        if clipboard.image() and not clipboard.image().isNull():
            qimg = clipboard.image()
            buffer = qimg.convertToFormat(QImage.Format_RGB888)
            ptr = buffer.constBits()
            img = Image.frombuffer("RGB", (qimg.width(), qimg.height()), ptr, "raw", "RGB", 0, 1)
            idx = self._add_photo_to_workspace(img, f"Pasted_Photo_{len(self.workspace_photos) + 1}")
            self.list_photos.setCurrentRow(idx)
            self.statusBar().showMessage("Pasted image from clipboard", 3000)
            return

        # Check for file URLs in clipboard
        if mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls() if u.toLocalFile()]
            if paths:
                self._load_image_paths(paths)

    def _add_photo_to_workspace(self, img: Image.Image, name: str) -> int:
        idx = len(self.workspace_photos)
        item_data = {
            "id": idx,
            "name": name,
            "orig_initial": img.copy(),
            "orig": img.copy(),
            "baked": img.copy(),
            "processed": img.copy(),
            "roi": None,
            "target_w_mm": None,
            "target_h_mm": None,
            "params": self._get_current_params(),
            "history": []
        }
        self.workspace_photos.append(item_data)

        # Create thumbnail for list
        thumb = img.copy()
        thumb.thumbnail((48, 48), Image.BILINEAR)
        pix = pil_to_pixmap(thumb)

        list_item = QListWidgetItem(QIcon(pix), name)
        self.list_photos.addItem(list_item)
        return idx

    def _on_remove_photo(self):
        row = self.list_photos.currentRow()
        if 0 <= row < len(self.workspace_photos):
            self.workspace_photos.pop(row)
            self.list_photos.takeItem(row)
            if self.workspace_photos:
                new_row = min(row, len(self.workspace_photos) - 1)
                self.list_photos.setCurrentRow(new_row)
            else:
                self.current_photo_idx = -1
                self.canvas.set_pixmap(QPixmap())
                self._update_rescale_ui()

    def _on_photo_selected(self, row: int):
        if row < 0 or row >= len(self.workspace_photos):
            self.current_photo_idx = -1
            self._update_rescale_ui()
            return

        self.current_photo_idx = row
        item = self.workspace_photos[row]

        # Load parameters
        self._block_signals = True
        try:
            self.canvas.set_pixmap(pil_to_pixmap(item["baked"]), keep_roi=False)
            if item["roi"]:
                self.canvas.set_roi_box(item["roi"])
            else:
                self.canvas.set_roi_box(None)
            self.spin_rescale_pct.setValue(100)
        finally:
            self._block_signals = False

        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(len(item.get("history", [])) > 0)

    def _push_undo_snapshot(self, item: Dict[str, Any], desc: str):
        """Pushes a deep snapshot of the current photo state into its undo history stack."""
        snapshot = {
            "baked": item["baked"].copy(),
            "orig": item["orig"].copy(),
            "roi": item.get("roi"),
            "target_w_mm": item.get("target_w_mm"),
            "target_h_mm": item.get("target_h_mm"),
            "dim_w_mm": self._dim_w_mm,
            "dim_h_mm": self._dim_h_mm,
            "current_unit": self._current_unit,
            "preset": self.combo_presets.currentText(),
            "desc": desc,
        }
        item.setdefault("history", []).append(snapshot)
        if len(item["history"]) > 25:
            item["history"].pop(0)
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(True)

    def _on_undo(self):
        """Reverts the last crop, rotation, or bake operation for the current photo."""
        if self.current_photo_idx < 0:
            return
        item = self.workspace_photos[self.current_photo_idx]
        history = item.get("history", [])
        if not history:
            self.statusBar().showMessage("Nothing to undo for this photo.", 3000)
            if hasattr(self, "btn_undo"):
                self.btn_undo.setEnabled(False)
            return

        snapshot = history.pop()
        item["baked"] = snapshot["baked"]
        item["orig"] = snapshot["orig"]
        item["roi"] = snapshot["roi"]
        item["target_w_mm"] = snapshot["target_w_mm"]
        item["target_h_mm"] = snapshot["target_h_mm"]
        self._dim_w_mm = snapshot["dim_w_mm"]
        self._dim_h_mm = snapshot["dim_h_mm"]

        self._block_signals = True
        try:
            if snapshot.get("current_unit"):
                self._current_unit = snapshot["current_unit"]
                self.combo_unit.setCurrentText(self._current_unit)
            unit_w = self._convert_mm_to_unit(self._dim_w_mm, self._current_unit)
            unit_h = self._convert_mm_to_unit(self._dim_h_mm, self._current_unit)
            self.spin_custom_w.setValue(unit_w)
            self.spin_custom_h.setValue(unit_h)
            if snapshot.get("preset"):
                self.combo_presets.setCurrentText(snapshot["preset"])
            if item["roi"]:
                self.canvas.set_roi_box(item["roi"])
                self.btn_apply_crop.setEnabled(True)
            else:
                self.canvas.set_roi_box(None)
                self.btn_apply_crop.setEnabled(False)
        finally:
            self._block_signals = False

        # Refresh thumbnail in workspace list
        thumb = item["baked"].copy()
        thumb.thumbnail((40, 40), Image.BILINEAR)
        list_item = self.list_photos.item(self.current_photo_idx)
        if list_item:
            list_item.setIcon(QIcon(pil_to_pixmap(thumb)))

        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self.statusBar().showMessage(f"↩️ Undid: {snapshot['desc']}", 4000)
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(len(history) > 0)

    def _on_revert_to_original(self):
        """Restores the current photo back to its pristine, unedited initial state."""
        if self.current_photo_idx < 0:
            return
        item = self.workspace_photos[self.current_photo_idx]
        orig_init = item.get("orig_initial")
        if orig_init is None:
            orig_init = item["orig"]

        # Push to undo history first so revert itself can be undone
        self._push_undo_snapshot(item, "Revert to Original")

        item["baked"] = orig_init.copy()
        item["orig"] = orig_init.copy()
        item["roi"] = None
        item["target_w_mm"] = None
        item["target_h_mm"] = None

        self._block_signals = True
        try:
            self.canvas.set_roi_box(None)
            self.btn_apply_crop.setEnabled(False)
            self.combo_presets.setCurrentText("Freeform / Original")
        finally:
            self._block_signals = False

        thumb = item["baked"].copy()
        thumb.thumbnail((40, 40), Image.BILINEAR)
        list_item = self.list_photos.item(self.current_photo_idx)
        if list_item:
            list_item.setIcon(QIcon(pil_to_pixmap(thumb)))

        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self.statusBar().showMessage("⏮️ Reverted photo to initial unedited state.", 5000)

    def _on_bake_edit(self):
        if self.current_photo_idx < 0:
            return
        item = self.workspace_photos[self.current_photo_idx]
        if item.get("processed"):
            self._push_undo_snapshot(item, "Bake Edits")
            item["baked"] = item["processed"].copy()
            item["roi"] = None
            self.canvas.set_pixmap(pil_to_pixmap(item["baked"]), keep_roi=False)
            self._on_reset_lighting()
            self._on_reset_roi()
            self._update_rescale_ui()
            self.statusBar().showMessage("Current edits baked successfully into base image", 4000)

    # -------------------------------------------------------------------------
    # Resolution & Scaling Handlers (rescaler.py)
    # -------------------------------------------------------------------------

    def _on_rescale_pct_changed(self, pct: int):
        """Calculates live target pixel readout and validates against safety ceiling."""
        if self.current_photo_idx < 0 or self.current_photo_idx >= len(self.workspace_photos):
            self.lbl_target_res.setText("Result: No photo selected")
            return
        item = self.workspace_photos[self.current_photo_idx]
        orig_w, orig_h = item["baked"].size
        target_w, target_h = rescaler.calculate_target_dimensions(orig_w, orig_h, pct)

        if not rescaler.is_within_safe_limits(target_w, target_h):
            self.lbl_target_res.setText(f"Result: {target_w}x{target_h} px (⚠️ Exceeds {rescaler.MAX_SAFE_IMAGE_DIM}px Cap!)")
            self.lbl_target_res.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 11px;")
            self.btn_apply_scale.setEnabled(False)
        else:
            self.lbl_target_res.setText(f"Result: {target_w} x {target_h} px")
            self.lbl_target_res.setStyleSheet("color: #38bdf8; font-size: 11px;")
            self.btn_apply_scale.setEnabled(True)

    def _update_rescale_ui(self):
        """Refreshes the resolution readout and target calculation for active photo."""
        if self.current_photo_idx >= 0 and self.current_photo_idx < len(self.workspace_photos):
            item = self.workspace_photos[self.current_photo_idx]
            w, h = item["baked"].size
            self.lbl_current_res.setText(f"Current: {w} x {h} px")
            self._on_rescale_pct_changed(self.spin_rescale_pct.value())
            self.btn_apply_scale.setEnabled(True)

            if not rescaler.GLOBAL_SUPERRES_ENGINE.is_available():
                self.btn_ai_enhance.setEnabled(False)
                self.btn_ai_enhance.setToolTip("Super-resolution model not downloaded (check models/superres)")
            elif max(w, h) > rescaler.MAX_AI_INPUT_DIM:
                self.btn_ai_enhance.setEnabled(False)
                self.btn_ai_enhance.setToolTip(f"Image is already high resolution (>{rescaler.MAX_AI_INPUT_DIM}px)")
            else:
                self.btn_ai_enhance.setEnabled(True)
                self.btn_ai_enhance.setToolTip("Reconstruct sharp details using 2x neural super-resolution")
        else:
            self.lbl_current_res.setText("Current: None")
            self.lbl_target_res.setText("Result: None")
            self._block_signals = True
            try:
                self.spin_rescale_pct.setValue(100)
            finally:
                self._block_signals = False
            self.btn_apply_scale.setEnabled(False)
            if hasattr(self, "btn_ai_enhance"):
                self.btn_ai_enhance.setEnabled(False)

    def _on_apply_rescale(self):
        """Executes compute-based rescaling and registers snapshot to undo history."""
        if self.current_photo_idx < 0 or self.current_photo_idx >= len(self.workspace_photos):
            return
        pct = self.spin_rescale_pct.value()
        if pct == 100:
            self.statusBar().showMessage("Scale is 100% (no changes applied).", 3000)
            return

        item = self.workspace_photos[self.current_photo_idx]

        try:
            # 1. Push undo snapshot FIRST so this operation is reversible via Ctrl+Z
            self._push_undo_snapshot(item, f"Scale to {pct}%")

            # 2. Rescale image using rescaler module
            scaled_img, (new_w, new_h) = rescaler.rescale_image(item["baked"], pct)

            # 3. Update working image & clear stale ROI
            item["baked"] = scaled_img
            item["orig"] = scaled_img
            item["roi"] = None

            # 4. Refresh workspace list thumbnail
            thumb = scaled_img.copy()
            thumb.thumbnail((48, 48), Image.BILINEAR)
            list_item = self.list_photos.item(self.current_photo_idx)
            if list_item:
                list_item.setIcon(QIcon(pil_to_pixmap(thumb)))

            # 5. Reset scale spinner back to 100% baseline for the new resolution
            self._block_signals = True
            try:
                self.spin_rescale_pct.setValue(100)
            finally:
                self._block_signals = False

            # 6. Re-render canvas & update readouts
            self.canvas.set_pixmap(pil_to_pixmap(scaled_img), keep_roi=False)
            self._trigger_render()
            self.canvas.fit_image()
            self._update_rescale_ui()

            # 7. Enable undo button and show confirmation
            if hasattr(self, "btn_undo"):
                self.btn_undo.setEnabled(True)
            self.statusBar().showMessage(f"⚡ Rescaled to {pct}% ({new_w} x {new_h} px). Undo with Ctrl+Z.", 5000)

        except ValueError as e:
            QMessageBox.warning(self, "Scale Limit Exceeded", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Rescaling Error", f"Failed to rescale image:\n{e}")

    def _on_ai_enhance_clicked(self):
        """Launches non-blocking AI super-resolution in background thread."""
        if self.current_photo_idx < 0 or self.current_photo_idx >= len(self.workspace_photos):
            return
        item = self.workspace_photos[self.current_photo_idx]

        w, h = item["baked"].size
        if max(w, h) > rescaler.MAX_AI_INPUT_DIM:
            QMessageBox.information(
                self, "Resolution Sufficient",
                f"Image is already {w}x{h} px. AI enhancement is designed for photos under {rescaler.MAX_AI_INPUT_DIM}px."
            )
            return

        # Lock UI controls during inference
        self.btn_ai_enhance.setEnabled(False)
        self.btn_apply_scale.setEnabled(False)
        self.statusBar().showMessage("🤖 Running AI Super-Resolution (2x)... Please wait.")

        # Start non-blocking QThread
        self._ai_worker = SuperResWorker(item["baked"].copy())
        self._ai_worker.finished.connect(self._on_ai_enhance_finished)
        self._ai_worker.error.connect(self._on_ai_enhance_error)
        self._ai_worker.start()

    def _on_ai_enhance_finished(self, enhanced_img: Image.Image):
        """Callback when AI enhance completes successfully."""
        if self.current_photo_idx < 0 or self.current_photo_idx >= len(self.workspace_photos):
            return
        item = self.workspace_photos[self.current_photo_idx]

        # Push undo snapshot FIRST
        self._push_undo_snapshot(item, "AI Super-Resolution (2x)")

        # Update working photo
        item["baked"] = enhanced_img
        item["orig"] = enhanced_img
        item["roi"] = None

        # Refresh thumbnail
        thumb = enhanced_img.copy()
        thumb.thumbnail((48, 48), Image.BILINEAR)
        list_item = self.list_photos.item(self.current_photo_idx)
        if list_item:
            list_item.setIcon(QIcon(pil_to_pixmap(thumb)))

        # Re-render canvas
        self.canvas.set_pixmap(pil_to_pixmap(enhanced_img), keep_roi=False)
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()

        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(True)

        w, h = enhanced_img.size
        self.statusBar().showMessage(f"✨ AI Super-Resolution complete! New size: {w} x {h} px. Undo with Ctrl+Z.", 5000)

    def _on_ai_enhance_error(self, err_msg: str):
        """Callback if AI inference fails."""
        self._update_rescale_ui()
        self.statusBar().showMessage("AI enhancement failed.", 4000)
        QMessageBox.warning(self, "AI Enhance Failed", f"Could not enhance image:\n{err_msg}")

    # -------------------------------------------------------------------------
    # Canvas Actions & ROI
    # -------------------------------------------------------------------------

    def _on_canvas_roi_changed(self, box: Tuple[int, int, int, int]):
        if self.current_photo_idx >= 0:
            self.workspace_photos[self.current_photo_idx]["roi"] = box
        self._trigger_render()

    def _on_reset_roi(self):
        self.canvas.set_roi_box(None)
        if self.current_photo_idx >= 0:
            self.workspace_photos[self.current_photo_idx]["roi"] = None
        self._trigger_render()

    def _on_rotate_90(self):
        if self.current_photo_idx < 0:
            return
        item = self.workspace_photos[self.current_photo_idx]
        self._push_undo_snapshot(item, "Rotate 90°")
        item["baked"] = item["baked"].rotate(-90, expand=True)
        item["roi"] = None
        self.canvas.set_pixmap(pil_to_pixmap(item["baked"]), keep_roi=False)
        self._trigger_render()
        self.canvas.fit_image()
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(len(item.get("history", [])) > 0)

    def _on_compare_pressed(self):
        if self.current_photo_idx >= 0:
            orig = self.workspace_photos[self.current_photo_idx]["orig"]
            self.canvas.set_pixmap(pil_to_pixmap(orig), keep_roi=False)

    def _on_compare_released(self):
        if self.current_photo_idx >= 0:
            proc = self.workspace_photos[self.current_photo_idx].get("processed")
            if proc:
                self.canvas.set_pixmap(pil_to_pixmap(proc), keep_roi=True)

    # -------------------------------------------------------------------------
    # Settings, Presets, Units & Dimension Handlers
    # -------------------------------------------------------------------------

    def _get_current_dimensions_in_mm(self) -> Tuple[float, float]:
        """Returns the current width and height in millimeters."""
        return (self._dim_w_mm, self._dim_h_mm)

    def _convert_mm_to_unit(self, val_mm: float, target_unit: str) -> float:
        """Converts millimeters to target unit (mm, in, or px)."""
        if target_unit == "in":
            return round(val_mm / 25.4, 2)
        elif target_unit == "px":
            return float(round(val_mm * engine.PX_PER_MM))
        else:
            return round(val_mm, 1)

    def _convert_unit_to_mm(self, val: float, source_unit: str) -> float:
        """Converts value from source unit to millimeters."""
        if source_unit == "in":
            return val * 25.4
        elif source_unit == "px":
            return val / engine.PX_PER_MM
        else:
            return val

    def _on_unit_changed(self, new_unit: str):
        if new_unit == self._current_unit:
            return

        new_w = self._convert_mm_to_unit(self._dim_w_mm, new_unit)
        new_h = self._convert_mm_to_unit(self._dim_h_mm, new_unit)

        self._block_signals = True
        try:
            if new_unit == "in":
                self.spin_custom_w.setDecimals(2)
                self.spin_custom_h.setDecimals(2)
                self.spin_custom_w.setSingleStep(0.1)
                self.spin_custom_h.setSingleStep(0.1)
                self.spin_custom_w.setRange(0.2, 50.0)
                self.spin_custom_h.setRange(0.2, 50.0)
                self.spin_custom_w.setSuffix(" in")
                self.spin_custom_h.setSuffix(" in")
            elif new_unit == "px":
                self.spin_custom_w.setDecimals(0)
                self.spin_custom_h.setDecimals(0)
                self.spin_custom_w.setSingleStep(10.0)
                self.spin_custom_h.setSingleStep(10.0)
                self.spin_custom_w.setRange(20.0, 10000.0)
                self.spin_custom_h.setRange(20.0, 10000.0)
                self.spin_custom_w.setSuffix(" px")
                self.spin_custom_h.setSuffix(" px")
            else:  # "mm"
                self.spin_custom_w.setDecimals(1)
                self.spin_custom_h.setDecimals(1)
                self.spin_custom_w.setSingleStep(1.0)
                self.spin_custom_h.setSingleStep(1.0)
                self.spin_custom_w.setRange(5.0, 1000.0)
                self.spin_custom_h.setRange(5.0, 1000.0)
                self.spin_custom_w.setSuffix(" mm")
                self.spin_custom_h.setSuffix(" mm")

            self.spin_custom_w.setValue(new_w)
            self.spin_custom_h.setValue(new_h)
            self._current_unit = new_unit
        finally:
            self._block_signals = False

    def _on_preset_changed(self, text: str):
        if self._block_signals:
            return

        dims_mm = PRESET_MAP.get(text)
        if dims_mm is not None:
            w_mm, h_mm = dims_mm
            self._dim_w_mm = w_mm
            self._dim_h_mm = h_mm
            unit_w = self._convert_mm_to_unit(w_mm, self._current_unit)
            unit_h = self._convert_mm_to_unit(h_mm, self._current_unit)

            self._block_signals = True
            try:
                self.spin_custom_w.setValue(unit_w)
                self.spin_custom_h.setValue(unit_h)
            finally:
                self._block_signals = False

            self.btn_apply_crop.setEnabled(True)
            aspect = w_mm / h_mm if h_mm > 0 else 1.0
            self.canvas.set_aspect_ratio(aspect)
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=aspect)
            self.statusBar().showMessage(
                f"Preset loaded: {text} ({w_mm:.1f} x {h_mm:.1f} mm). Frame with box, then click Apply Crop.",
                5000
            )
        elif text == "Freeform / Original":
            self.canvas.set_aspect_ratio(None)
            self.btn_apply_crop.setEnabled(self.canvas.get_roi_box() is not None)
            self.statusBar().showMessage("Freeform: Drag any box freely or leave full image.", 3000)
        elif text == "Custom Size":
            self.btn_apply_crop.setEnabled(True)
            w_mm, h_mm = self._get_current_dimensions_in_mm()
            aspect = w_mm / h_mm if h_mm > 0 else 1.0
            self.canvas.set_aspect_ratio(aspect)
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=aspect)

    def _on_spinbox_dimension_changed(self):
        if self._block_signals:
            return

        w_val = self.spin_custom_w.value()
        h_val = self.spin_custom_h.value()
        self._dim_w_mm = self._convert_unit_to_mm(w_val, self._current_unit)
        self._dim_h_mm = self._convert_unit_to_mm(h_val, self._current_unit)

        if self.combo_presets.currentText() != "Custom Size":
            self._block_signals = True
            try:
                self.combo_presets.setCurrentText("Custom Size")
            finally:
                self._block_signals = False

        self.btn_apply_crop.setEnabled(True)

        if self._dim_w_mm > 0 and self._dim_h_mm > 0:
            aspect = self._dim_w_mm / self._dim_h_mm
            self.canvas.set_aspect_ratio(aspect)
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=aspect)

    def _on_roi_mode_changed(self, mode_id: int):
        if self._block_signals:
            return

        if mode_id == 0:  # Whole Image
            self.canvas.set_roi_box(None)
            self._trigger_render()
        elif mode_id == 1:  # Patch ID
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=None)
            self._trigger_render()

    def _on_apply_crop(self):
        if self.current_photo_idx < 0:
            QMessageBox.information(self, "No Photo", "Please add or select a photo first.")
            return

        item = self.workspace_photos[self.current_photo_idx]
        roi_box = self.canvas.get_roi_box()
        if not roi_box:
            w, h = item["baked"].size
            roi_box = (0, 0, w, h)

        w_mm, h_mm = self._get_current_dimensions_in_mm()
        preset = self.combo_presets.currentText()

        target_px = None
        if preset != "Freeform / Original" and w_mm > 0 and h_mm > 0:
            target_w_px = int(round(w_mm * engine.PX_PER_MM))
            target_h_px = int(round(h_mm * engine.PX_PER_MM))
            target_px = (target_w_px, target_h_px)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            desc = f"Crop to {w_mm:.1f}x{h_mm:.1f} mm" if target_px else "Crop to Selection"
            self._push_undo_snapshot(item, desc)
            item["baked"] = engine.crop_and_resize(item["baked"], roi_box, target_px)
            item["orig"] = engine.crop_and_resize(item["orig"], roi_box, target_px)
            item["target_w_mm"] = w_mm if preset != "Freeform / Original" else None
            item["target_h_mm"] = h_mm if preset != "Freeform / Original" else None
            item["roi"] = None

            thumb = item["baked"].copy()
            thumb.thumbnail((40, 40), Image.BILINEAR)
            list_item = self.list_photos.item(self.current_photo_idx)
            if list_item:
                list_item.setIcon(QIcon(pil_to_pixmap(thumb)))

            self._block_signals = True
            try:
                self.canvas.set_roi_box(None)
            finally:
                self._block_signals = False

            self._trigger_render()
            self.canvas.fit_image()

            dim_text = f" ({w_mm:.1f} x {h_mm:.1f} mm)" if target_px else ""
            self.statusBar().showMessage(
                f"✂️ Cropped photo to {item['baked'].width} x {item['baked'].height} px{dim_text} with zero distortion",
                5000
            )
        except Exception as e:
            QMessageBox.critical(self, "Crop Error", f"Failed to crop image:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _on_ai_toggled(self, checked: bool):
        self.combo_ai_model.setEnabled(checked)
        self.combo_backdrop.setEnabled(checked)
        self.slider_choke.setEnabled(checked)
        self.slider_feather.setEnabled(checked)
        self._trigger_render()

    def _on_backdrop_changed(self, text: str):
        is_custom = "Custom" in text
        self.btn_pick_color.setEnabled(is_custom)
        self._trigger_render()

    def _on_pick_custom_color(self):
        qcolor = QColorDialog.getColor(QColor(*self._custom_bg_color), self, "Select Backdrop Color")
        if qcolor.isValid():
            self._custom_bg_color = (qcolor.red(), qcolor.green(), qcolor.blue())
            self._trigger_render()

    def _on_choke_changed(self, val: int):
        self.lbl_choke_val.setText(f"{val} px")
        self._trigger_render()

    def _on_feather_changed(self, val: int):
        feather_px = val / 10.0
        self.lbl_feather_val.setText(f"{feather_px:.1f} px")
        self._trigger_render()

    def _on_reset_lighting(self):
        self._block_signals = True
        try:
            self.slider_bright.setValue(100)
            self.slider_contrast.setValue(100)
            self.slider_sat.setValue(100)
            self.slider_sharp.setValue(100)
            self.slider_warmth.setValue(0)
            self.lbl_bright.setText("100%")
            self.lbl_contrast.setText("100%")
            self.lbl_sat.setText("100%")
            self.lbl_sharp.setText("100%")
            self.lbl_warmth.setText("0")
        finally:
            self._block_signals = False
        self._trigger_render()

    def _get_current_params(self) -> Dict[str, Any]:
        w_mm, h_mm = self._get_current_dimensions_in_mm()
        return {
            "remove_bg": self.chk_remove_bg.isChecked(),
            "ai_model": "RMBG-1.4" if "RMBG" in self.combo_ai_model.currentText() else "MODNet",
            "backdrop": self.combo_backdrop.currentText(),
            "custom_color": self._custom_bg_color,
            "choke_px": self.slider_choke.value(),
            "feather_px": self.slider_feather.value() / 10.0,
            "brightness": self.slider_bright.value() / 100.0,
            "contrast": self.slider_contrast.value() / 100.0,
            "saturation": self.slider_sat.value() / 100.0,
            "sharpness": self.slider_sharp.value() / 100.0,
            "warmth": self.slider_warmth.value(),
            "preset_name": self.combo_presets.currentText(),
            "custom_w_mm": w_mm,
            "custom_h_mm": h_mm,
        }

    # -------------------------------------------------------------------------
    # Core Synchronous Rendering Pipeline
    # -------------------------------------------------------------------------

    def _trigger_render(self):
        if self._block_signals or self.current_photo_idx < 0:
            return

        item = self.workspace_photos[self.current_photo_idx]
        base_img = item["baked"]
        params = self._get_current_params()
        roi_box = self.canvas.get_roi_box()

        mode_id = self.bg_roi_mode.checkedId()
        mode_str = "patch" if mode_id == 1 else "whole"

        # Synchronous execution with wait cursor
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = engine.process_image_pipeline(
                full_img=base_img,
                roi_box=roi_box,
                roi_mode=mode_str,
                params=params,
                seg_engine=engine.GLOBAL_SEGMENTATION_ENGINE
            )
            item["processed"] = result
            item["params"] = params
            item["roi"] = roi_box

            # Update preview canvas
            self.canvas.set_pixmap(pil_to_pixmap(result), keep_roi=True)
        except Exception as e:
            self.statusBar().showMessage(f"Processing Error: {e}", 5000)
        finally:
            QApplication.restoreOverrideCursor()

    # -------------------------------------------------------------------------
    # Save & Queue Actions
    # -------------------------------------------------------------------------

    def _on_save_single_photo(self):
        if self.current_photo_idx < 0:
            return
        item = self.workspace_photos[self.current_photo_idx]
        proc = item.get("processed")
        if not proc:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Processed Photo", "photo_studio_export.png",
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*.*)"
        )
        if filepath:
            try:
                proc.save(filepath, dpi=(engine.DPI, engine.DPI))
                self.statusBar().showMessage(f"Saved: {filepath}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed saving image:\n{e}")

    def _on_send_to_print_queue(self):
        if self.current_photo_idx < 0:
            QMessageBox.information(self, "No Photo", "Please select a photo to send to print queue.")
            return
        item = self.workspace_photos[self.current_photo_idx]
        proc = item.get("processed")
        if not proc:
            proc = item["baked"]

        if item.get("target_w_mm") and item.get("target_h_mm"):
            w_mm = item["target_w_mm"]
            h_mm = item["target_h_mm"]
        else:
            preset = self.combo_presets.currentText()
            dims_mm = PRESET_MAP.get(preset)
            if dims_mm is not None:
                w_mm, h_mm = dims_mm
            else:
                w_mm, h_mm = self._get_current_dimensions_in_mm()
                if preset == "Freeform / Original":
                    w_mm = round(proc.width / engine.PX_PER_MM, 1)
                    h_mm = round(proc.height / engine.PX_PER_MM, 1)

        self.tab_printer.add_photo(proc, w_mm, h_mm, copies=4, label=item["name"])
        self.statusBar().showMessage(f"Added to A4 Queue: {item['name']} ({w_mm:.1f} x {h_mm:.1f} mm)", 4000)

    # -------------------------------------------------------------------------
    # A4 Print Studio Handlers
    # -------------------------------------------------------------------------

    def _on_tab_changed(self, idx: int):
        if idx == 1:
            self.tab_printer.refresh_preview()



def main():
    # Enable high DPI scaling on Windows
    app = QApplication(sys.argv)
    app.setApplicationName("PhotoStudioNative")

    window = PhotoStudioApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
