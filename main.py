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
import transforms
from styles import DARK_THEME_QSS
from workspace import PhotoWorkspace, RetouchState, CropState


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

        # In-memory isolated per-photo workspaces
        self.workspace_photos: List[PhotoWorkspace] = []
        self.current_photo_idx: int = -1
        self._next_photo_id: int = 0
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

        # Crop & Straighten Group
        grp_preset = QGroupBox("📏 Crop && Straighten")
        grp_preset_layout = QVBoxLayout(grp_preset)
        grp_preset_layout.setSpacing(6)

        # Mode Selector Buttons (short labels so neither clips at 240px panel width)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(4)
        self.btn_mode_box_crop = QPushButton("✂️ Crop")
        self.btn_mode_box_crop.setCheckable(True)
        self.btn_mode_box_crop.setChecked(True)
        self.btn_mode_box_crop.setProperty("class", "crop-mode-btn")
        self.btn_mode_box_crop.setToolTip("Standard rectangular crop with physical presets and aspect locking")

        self.btn_mode_perspective = QPushButton("📐 Straighten")
        self.btn_mode_perspective.setCheckable(True)
        self.btn_mode_perspective.setProperty("class", "crop-mode-btn")
        self.btn_mode_perspective.setToolTip("Drag the 4 corner pins onto your ID/document corners (amber TOP edge = Width)")

        self.bg_crop_mode = QButtonGroup(self)
        self.bg_crop_mode.setExclusive(True)
        self.bg_crop_mode.addButton(self.btn_mode_box_crop, 0)
        self.bg_crop_mode.addButton(self.btn_mode_perspective, 1)
        self.bg_crop_mode.idClicked.connect(self._on_crop_mode_toggled)

        mode_row.addWidget(self.btn_mode_box_crop)
        mode_row.addWidget(self.btn_mode_perspective)
        grp_preset_layout.addLayout(mode_row)

        # Crop-only Presets container (hidden in Straighten mode)
        self.container_presets = QWidget()
        presets_layout = QVBoxLayout(self.container_presets)
        presets_layout.setContentsMargins(0, 0, 0, 0)
        presets_layout.setSpacing(4)

        self.combo_presets = NoWheelComboBox()
        for preset_name in PRESET_MAP.keys():
            self.combo_presets.addItem(preset_name)
        self.combo_presets.currentTextChanged.connect(self._on_preset_changed)
        presets_layout.addWidget(self.combo_presets)
        grp_preset_layout.addWidget(self.container_presets)

        # Shared Unit / Width / Height controls reused by both Crop and Straighten modes
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

        # Mode 1 Actions: Standard Crop
        self.container_box_crop = QWidget()
        box_crop_layout = QVBoxLayout(self.container_box_crop)
        box_crop_layout.setContentsMargins(0, 2, 0, 0)
        box_crop_layout.setSpacing(5)

        self.btn_apply_crop = QPushButton("✂️ Apply Crop / Dimensions")
        self.btn_apply_crop.setObjectName("btn_apply_crop")
        self.btn_apply_crop.clicked.connect(self._on_apply_crop)
        box_crop_layout.addWidget(self.btn_apply_crop)

        grp_preset_layout.addWidget(self.container_box_crop)

        # Mode 2 Actions: Straighten / Perspective Extraction
        self.container_perspective = QWidget()
        persp_layout = QVBoxLayout(self.container_perspective)
        persp_layout.setContentsMargins(0, 2, 0, 0)
        persp_layout.setSpacing(6)

        self.chk_apply_size = QCheckBox("Apply Size")
        self.chk_apply_size.setChecked(False)
        self.chk_apply_size.setToolTip(
            "When checked, fits the extracted selection to Width × Height above (300 DPI for mm/in). "
            "When unchecked, extracts at natural pixel resolution."
        )
        persp_layout.addWidget(self.chk_apply_size)

        persp_btn_row = QHBoxLayout()
        persp_btn_row.setSpacing(6)

        self.btn_reset_pins = QPushButton("🔄 Reset")
        self.btn_reset_pins.setToolTip("Re-centers the 4 perspective pins on the image")
        self.btn_reset_pins.clicked.connect(self._on_reset_perspective_pins)

        self.btn_apply_extract = QPushButton("🪄 Extract")
        self.btn_apply_extract.setObjectName("btn_apply_extract")
        self.btn_apply_extract.setToolTip("Rectifies slanted ID card/document into a flat rectangular photo")
        self.btn_apply_extract.clicked.connect(self._on_apply_extract)

        persp_btn_row.addWidget(self.btn_reset_pins)
        persp_btn_row.addWidget(self.btn_apply_extract)
        persp_layout.addLayout(persp_btn_row)

        self.container_perspective.setVisible(False)
        grp_preset_layout.addWidget(self.container_perspective)

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
        self.canvas.quadChanged.connect(self._on_canvas_quad_changed)
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

        self._sync_ai_controls_enabled()
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

    def _current_workspace(self) -> Optional[PhotoWorkspace]:
        """Returns the active PhotoWorkspace, or None if no photo is selected."""
        if 0 <= self.current_photo_idx < len(self.workspace_photos):
            return self.workspace_photos[self.current_photo_idx]
        return None

    def _refresh_thumbnail(self, row: int, img: Image.Image) -> None:
        """Updates the workspace list icon for the given row."""
        if 0 <= row < self.list_photos.count():
            thumb = img.copy()
            thumb.thumbnail((48, 48), Image.BILINEAR)
            list_item = self.list_photos.item(row)
            if list_item:
                list_item.setIcon(QIcon(pil_to_pixmap(thumb)))

    def _add_photo_to_workspace(self, img: Image.Image, name: str) -> int:
        idx = len(self.workspace_photos)
        ws = PhotoWorkspace.create(self._next_photo_id, img, name)
        self._next_photo_id += 1
        self.workspace_photos.append(ws)

        thumb = img.copy()
        thumb.thumbnail((48, 48), Image.BILINEAR)
        pix = pil_to_pixmap(thumb)

        list_item = QListWidgetItem(QIcon(pix), name)
        self.list_photos.addItem(list_item)
        return idx

    def _on_remove_photo(self):
        row = self.list_photos.currentRow()
        if 0 <= row < len(self.workspace_photos):
            # Invalidate current_photo_idx and suppress intermediate signals while mutating
            # QListWidget so the remaining item is always hydrated cleanly without leaking state.
            self.current_photo_idx = -1
            self.workspace_photos.pop(row)
            self.list_photos.blockSignals(True)
            try:
                self.list_photos.takeItem(row)
                if self.workspace_photos:
                    new_row = min(row, len(self.workspace_photos) - 1)
                    self.list_photos.setCurrentRow(new_row)
            finally:
                self.list_photos.blockSignals(False)

            if self.workspace_photos:
                self._on_photo_selected(self.list_photos.currentRow())
            else:
                self._reset_controls_to_defaults()
                self.canvas.set_pixmap(QPixmap())
                self._update_rescale_ui()
                if hasattr(self, "btn_undo"):
                    self.btn_undo.setEnabled(False)
                if hasattr(self, "btn_apply_extract"):
                    self.btn_apply_extract.setEnabled(False)

    def _sync_ui_to_workspace(self, ws: PhotoWorkspace) -> None:
        """Persists live UI control values and canvas overlays into the given workspace."""
        ws.retouch = self._collect_retouch_state()
        ws.crop.crop_mode = self.canvas.crop_mode
        ws.crop.preset_name = self.combo_presets.currentText()
        ws.crop.unit = self._current_unit
        ws.crop.dim_w_mm = self._dim_w_mm
        ws.crop.dim_h_mm = self._dim_h_mm
        ws.crop.apply_size = self.chk_apply_size.isChecked()
        ws.crop.rescale_pct = self.spin_rescale_pct.value()
        if self.canvas.crop_mode == "perspective":
            ws.crop.quad = self.canvas.get_perspective_quad()
        else:
            ws.crop.roi = self.canvas.get_roi_box()

    def _load_retouch_to_ui(self, retouch: RetouchState) -> None:
        """Applies a RetouchState to AI and Lighting controls (caller manages _block_signals)."""
        self._custom_bg_color = retouch.custom_color
        self.chk_remove_bg.setChecked(retouch.remove_bg)
        self.combo_ai_model.setCurrentIndex(1 if "MODNet" in retouch.ai_model else 0)
        self.combo_backdrop.setCurrentText(retouch.backdrop)
        self.slider_choke.setValue(retouch.choke_px)
        self.lbl_choke_val.setText(f"{retouch.choke_px} px")
        feather_slider = int(round(retouch.feather_px * 10))
        self.slider_feather.setValue(feather_slider)
        self.lbl_feather_val.setText(f"{retouch.feather_px:.1f} px")
        self._sync_ai_controls_enabled()

        bright_val = int(round(retouch.brightness * 100))
        contrast_val = int(round(retouch.contrast * 100))
        sat_val = int(round(retouch.saturation * 100))
        sharp_val = int(round(retouch.sharpness * 100))
        warmth_val = int(retouch.warmth)

        self.slider_bright.setValue(bright_val)
        self.slider_contrast.setValue(contrast_val)
        self.slider_sat.setValue(sat_val)
        self.slider_sharp.setValue(sharp_val)
        self.slider_warmth.setValue(warmth_val)
        self.lbl_bright.setText(f"{bright_val}%")
        self.lbl_contrast.setText(f"{contrast_val}%")
        self.lbl_sat.setText(f"{sat_val}%")
        self.lbl_sharp.setText(f"{sharp_val}%")
        self.lbl_warmth.setText(f"{warmth_val}")

        if retouch.edit_inside_box:
            self.radio_mode_patch.setChecked(True)
        else:
            self.radio_mode_whole.setChecked(True)

    def _load_crop_to_ui(self, crop: CropState, restore_pixmap: Optional[Image.Image] = None) -> None:
        """Applies a CropState to Crop/Straighten controls and canvas overlays."""
        self._current_unit = crop.unit
        self._dim_w_mm = crop.dim_w_mm
        self._dim_h_mm = crop.dim_h_mm
        self.combo_unit.setCurrentText(crop.unit)
        self._configure_unit_spinboxes(crop.unit)
        self.spin_custom_w.setValue(self._convert_mm_to_unit(crop.dim_w_mm, crop.unit))
        self.spin_custom_h.setValue(self._convert_mm_to_unit(crop.dim_h_mm, crop.unit))
        self.combo_presets.setCurrentText(crop.preset_name)
        self.chk_apply_size.setChecked(crop.apply_size)
        self.spin_rescale_pct.setValue(crop.rescale_pct)

        if crop.preset_name == "Freeform / Original" or crop.dim_h_mm <= 0:
            self.canvas.set_aspect_ratio(None)
        else:
            self.canvas.set_aspect_ratio(crop.dim_w_mm / crop.dim_h_mm)

        self.canvas.crop_mode = crop.crop_mode
        if restore_pixmap is not None:
            self.canvas.set_pixmap(pil_to_pixmap(restore_pixmap), keep_roi=False)

        if crop.crop_mode == "perspective":
            self.btn_mode_perspective.setChecked(True)
            self.container_presets.setVisible(False)
            self.container_box_crop.setVisible(False)
            self.container_perspective.setVisible(True)
            if crop.quad:
                self.canvas.set_perspective_quad(crop.quad)
            elif self.canvas.pixmap_item and not self.canvas.quad_item:
                self.canvas.spawn_centered_quad()
        else:
            self.btn_mode_box_crop.setChecked(True)
            self.container_perspective.setVisible(False)
            self.container_presets.setVisible(True)
            self.container_box_crop.setVisible(True)
            self.canvas.set_roi_box(crop.roi)

        self._update_crop_button_state()

    def _load_workspace_to_ui(self, ws: PhotoWorkspace) -> None:
        """Hydrates all studio UI panels and canvas overlays from a PhotoWorkspace."""
        self._block_signals = True
        try:
            self._load_retouch_to_ui(ws.retouch)
            self._load_crop_to_ui(ws.crop, restore_pixmap=ws.baked)
        finally:
            self._block_signals = False

    def _reset_controls_to_defaults(self) -> None:
        """Resets UI controls to fresh neutral defaults when workspace is empty."""
        self._block_signals = True
        try:
            self._load_retouch_to_ui(RetouchState())
            self._load_crop_to_ui(CropState(), restore_pixmap=None)
        finally:
            self._block_signals = False

    def _on_photo_selected(self, row: int):
        if 0 <= self.current_photo_idx < len(self.workspace_photos) and self.current_photo_idx != row:
            self._sync_ui_to_workspace(self.workspace_photos[self.current_photo_idx])

        if row < 0 or row >= len(self.workspace_photos):
            self.current_photo_idx = -1
            self._update_rescale_ui()
            if hasattr(self, "btn_apply_extract"):
                self.btn_apply_extract.setEnabled(False)
            return

        self.current_photo_idx = row
        ws = self.workspace_photos[row]

        self._load_workspace_to_ui(ws)

        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(ws.has_undo())
        if hasattr(self, "btn_apply_extract"):
            self.btn_apply_extract.setEnabled(True)

    def _on_undo(self):
        """Reverts the last crop, rotation, rescale, or commit operation for the current photo."""
        ws = self._current_workspace()
        if ws is None:
            return
        snapshot = ws.pop_undo()
        if snapshot is None:
            self.statusBar().showMessage("Nothing to undo for this photo.", 3000)
            if hasattr(self, "btn_undo"):
                self.btn_undo.setEnabled(False)
            return

        self._block_signals = True
        try:
            self._load_crop_to_ui(ws.crop, restore_pixmap=ws.baked)
        finally:
            self._block_signals = False

        self._refresh_thumbnail(self.current_photo_idx, ws.baked)
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self.statusBar().showMessage(f"↩️ Undid: {snapshot.desc}", 4000)
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(ws.has_undo())

    def _on_revert_to_original(self):
        """Restores the current photo back to its pristine, unedited initial state."""
        ws = self._current_workspace()
        if ws is None:
            return

        ws.revert_to_initial()
        self._load_workspace_to_ui(ws)

        self._refresh_thumbnail(self.current_photo_idx, ws.baked)
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(ws.has_undo())
        self.statusBar().showMessage("⏮️ Reverted photo to initial unedited state.", 5000)

    def _on_bake_edit(self):
        ws = self._current_workspace()
        if ws is None:
            return
        if ws.commit_retouch():
            self._block_signals = True
            try:
                self.canvas.set_roi_box(None)
                self._load_retouch_to_ui(ws.retouch)
                self._update_crop_button_state()
            finally:
                self._block_signals = False

            self._refresh_thumbnail(self.current_photo_idx, ws.baked)
            self._trigger_render()
            self._update_rescale_ui()
            if hasattr(self, "btn_undo"):
                self.btn_undo.setEnabled(ws.has_undo())
            self.statusBar().showMessage("✔️ Committed edits into base image and reset retouch controls.", 4000)

    # -------------------------------------------------------------------------
    # Resolution & Scaling Handlers (rescaler.py)
    # -------------------------------------------------------------------------

    def _on_rescale_pct_changed(self, pct: int):
        """Calculates live target pixel readout and validates against safety ceiling."""
        ws = self._current_workspace()
        if ws is None:
            self.lbl_target_res.setText("Result: No photo selected")
            return
        orig_w, orig_h = ws.baked.size
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
        ws = self._current_workspace()
        if ws is not None:
            w, h = ws.baked.size
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
        ws = self._current_workspace()
        if ws is None:
            return
        pct = self.spin_rescale_pct.value()
        if pct == 100:
            self.statusBar().showMessage("Scale is 100% (no changes applied).", 3000)
            return

        try:
            self._sync_ui_to_workspace(ws)
            ws.push_undo(f"Scale to {pct}%")

            scaled_img, (new_w, new_h) = rescaler.rescale_image(ws.baked, pct)
            ws.baked = scaled_img
            ws.orig = scaled_img
            ws.crop.roi = None
            ws.crop.quad = None
            ws.crop.rescale_pct = 100

            self._refresh_thumbnail(self.current_photo_idx, scaled_img)

            self._block_signals = True
            try:
                self.spin_rescale_pct.setValue(100)
            finally:
                self._block_signals = False

            self.canvas.set_pixmap(pil_to_pixmap(scaled_img), keep_roi=False)
            self._trigger_render()
            self.canvas.fit_image()
            self._update_rescale_ui()
            self._update_crop_button_state()

            if hasattr(self, "btn_undo"):
                self.btn_undo.setEnabled(True)
            self.statusBar().showMessage(f"⚡ Rescaled to {pct}% ({new_w} x {new_h} px). Undo with Ctrl+Z.", 5000)

        except ValueError as e:
            QMessageBox.warning(self, "Scale Limit Exceeded", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Rescaling Error", f"Failed to rescale image:\n{e}")

    def _on_ai_enhance_clicked(self):
        """Launches non-blocking AI super-resolution in background thread."""
        ws = self._current_workspace()
        if ws is None:
            return

        w, h = ws.baked.size
        if max(w, h) > rescaler.MAX_AI_INPUT_DIM:
            QMessageBox.information(
                self, "Resolution Sufficient",
                f"Image is already {w}x{h} px. AI enhancement is designed for photos under {rescaler.MAX_AI_INPUT_DIM}px."
            )
            return

        self.btn_ai_enhance.setEnabled(False)
        self.btn_apply_scale.setEnabled(False)
        self.statusBar().showMessage("🤖 Running AI Super-Resolution (2x)... Please wait.")

        self._ai_worker = SuperResWorker(ws.baked.copy())
        self._ai_worker.finished.connect(self._on_ai_enhance_finished)
        self._ai_worker.error.connect(self._on_ai_enhance_error)
        self._ai_worker.start()

    def _on_ai_enhance_finished(self, enhanced_img: Image.Image):
        """Callback when AI enhance completes successfully."""
        ws = self._current_workspace()
        if ws is None:
            return

        self._sync_ui_to_workspace(ws)
        ws.push_undo("AI Super-Resolution (2x)")

        ws.baked = enhanced_img
        ws.orig = enhanced_img
        ws.crop.roi = None
        ws.crop.quad = None

        self._refresh_thumbnail(self.current_photo_idx, enhanced_img)

        self.canvas.set_pixmap(pil_to_pixmap(enhanced_img), keep_roi=False)
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        self._update_crop_button_state()

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
        ws = self._current_workspace()
        if ws is not None:
            ws.crop.roi = box
        self._update_crop_button_state()
        self._trigger_render()

    def _on_canvas_quad_changed(self, points: List[Tuple[float, float]]):
        ws = self._current_workspace()
        if ws is not None and self.canvas.crop_mode == "perspective":
            ws.crop.quad = list(points)

    def _on_reset_roi(self):
        ws = self._current_workspace()
        if self.canvas.crop_mode == "perspective":
            self.canvas.reset_perspective_quad()
            if ws is not None:
                ws.crop.quad = self.canvas.get_perspective_quad()
            self.statusBar().showMessage("Reset 4 perspective pins to center.", 3000)
        else:
            self.canvas.set_roi_box(None)
            if ws is not None:
                ws.crop.roi = None
            self._update_crop_button_state()
            self._trigger_render()

    def _update_crop_button_state(self):
        """Updates Apply Crop button availability based on active photo, preset, and ROI box."""
        if self._current_workspace() is None:
            self.btn_apply_crop.setEnabled(False)
        elif self.combo_presets.currentText() == "Freeform / Original":
            self.btn_apply_crop.setEnabled(self.canvas.get_roi_box() is not None)
        else:
            self.btn_apply_crop.setEnabled(True)

    def _switch_to_crop_mode(self, auto_spawn_box: bool = True):
        """Activates standard Crop UI and canvas mode."""
        self.container_perspective.setVisible(False)
        self.container_presets.setVisible(True)
        self.container_box_crop.setVisible(True)
        self.canvas.set_crop_mode("standard")

        preset = self.combo_presets.currentText()
        if preset == "Freeform / Original":
            self.canvas.set_aspect_ratio(None)
        else:
            w_mm, h_mm = self._get_current_dimensions_in_mm()
            aspect = w_mm / h_mm if h_mm > 0 else 1.0
            self.canvas.set_aspect_ratio(aspect)
            if auto_spawn_box and not self.canvas.get_roi_box() and self.current_photo_idx >= 0:
                self.canvas.spawn_centered_box(aspect_ratio=aspect)
        self._update_crop_button_state()

    def _on_crop_mode_toggled(self, mode_id: int):
        ws = self._current_workspace()
        if mode_id == 1:  # Straighten
            self.container_presets.setVisible(False)
            self.container_box_crop.setVisible(False)
            self.container_perspective.setVisible(True)
            self.canvas.set_crop_mode("perspective")
            if ws is not None:
                ws.crop.crop_mode = "perspective"
                ws.crop.quad = self.canvas.get_perspective_quad()
            self.btn_apply_extract.setEnabled(self.current_photo_idx >= 0)
            self.statusBar().showMessage("Straighten mode: Drag the 4 corner pins (amber TOP = Width).", 4000)
        else:  # Crop
            self._switch_to_crop_mode(auto_spawn_box=True)
            if ws is not None:
                ws.crop.crop_mode = "standard"
            self.statusBar().showMessage("Crop mode active.", 3000)

    def _on_reset_perspective_pins(self):
        if self.canvas.crop_mode == "perspective":
            self.canvas.reset_perspective_quad()
            ws = self._current_workspace()
            if ws is not None:
                ws.crop.quad = self.canvas.get_perspective_quad()
            self.statusBar().showMessage("Reset 4 perspective pins to center.", 3000)

    def _finalize_geometry_edit(self, ws: PhotoWorkspace):
        """Refreshes workspace thumbnail, clears canvas overlays, re-renders, and updates rescale UI."""
        self._refresh_thumbnail(self.current_photo_idx, ws.baked)

        self._block_signals = True
        try:
            self.canvas.set_perspective_quad(None)
            self.canvas.set_roi_box(None)
            ws.crop.roi = None
            ws.crop.quad = None
            self._update_crop_button_state()
        finally:
            self._block_signals = False

        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(ws.has_undo())

    def _on_apply_extract(self):
        ws = self._current_workspace()
        if ws is None:
            QMessageBox.information(self, "No Photo", "Please add or select a photo first.")
            return

        quad = self.canvas.get_perspective_quad()
        if not quad or len(quad) != 4:
            QMessageBox.warning(self, "Invalid Selection", "Please position the 4 corner pins around the card or document.")
            return

        apply_size = self.chk_apply_size.isChecked()
        target_px = None
        w_mm = None
        h_mm = None

        if apply_size:
            target_px, w_mm, h_mm = self._get_target_dimensions_px_and_mm()
            if not target_px:
                QMessageBox.warning(self, "Invalid Size", "Width and Height must be greater than zero.")
                return

        w_nat, h_nat = transforms.calculate_natural_quad_dimensions(quad)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._sync_ui_to_workspace(ws)
            desc = (
                f"Extract & Fit ({target_px[0]}x{target_px[1]} px)"
                if target_px else
                f"Straighten & Extract ({w_nat}x{h_nat} px)"
            )
            ws.push_undo(desc)
            ws.baked = engine.extract_perspective_quad(ws.baked, quad, target_size=target_px)
            ws.orig = engine.extract_perspective_quad(ws.orig, quad, target_size=target_px)
            ws.target_w_mm = w_mm if target_px else None
            ws.target_h_mm = h_mm if target_px else None
            ws.crop.roi = None
            ws.crop.quad = None

            self._finalize_geometry_edit(ws)

            # Switch back to Crop mode cleanly without spawning a box over the extracted image
            self.btn_mode_box_crop.setChecked(True)
            self._switch_to_crop_mode(auto_spawn_box=False)
            ws.crop.crop_mode = "standard"

            if target_px:
                msg = f"🪄 Extracted & fitted to {ws.baked.width} x {ws.baked.height} px ({w_mm:.1f} x {h_mm:.1f} mm)"
            else:
                msg = f"🪄 Extracted & straightened to {ws.baked.width} x {ws.baked.height} px (natural)"
            self.statusBar().showMessage(msg, 6000)
        except Exception as e:
            QMessageBox.critical(self, "Extraction Error", f"Failed to straighten and extract image:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _on_rotate_90(self):
        ws = self._current_workspace()
        if ws is None:
            return
        self._sync_ui_to_workspace(ws)
        ws.push_undo("Rotate 90°")
        ws.baked = ws.baked.rotate(-90, expand=True)
        ws.crop.roi = None
        ws.crop.quad = None
        self._refresh_thumbnail(self.current_photo_idx, ws.baked)
        self.canvas.set_pixmap(pil_to_pixmap(ws.baked), keep_roi=False)
        self._update_crop_button_state()
        self._trigger_render()
        self.canvas.fit_image()
        self._update_rescale_ui()
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(ws.has_undo())

    def _on_compare_pressed(self):
        ws = self._current_workspace()
        if ws is not None:
            self.canvas.set_pixmap(pil_to_pixmap(ws.orig), keep_roi=False)

    def _on_compare_released(self):
        ws = self._current_workspace()
        if ws is not None:
            proc = ws.processed
            if proc:
                self.canvas.set_pixmap(pil_to_pixmap(proc), keep_roi=True)

    # -------------------------------------------------------------------------
    # Settings, Presets, Units & Dimension Handlers
    # -------------------------------------------------------------------------

    def _get_current_dimensions_in_mm(self) -> Tuple[float, float]:
        """Returns the current width and height in millimeters."""
        return (self._dim_w_mm, self._dim_h_mm)

    def _get_target_dimensions_px_and_mm(self) -> Tuple[Optional[Tuple[int, int]], float, float]:
        """
        Computes ((target_w_px, target_h_px), w_mm, h_mm) from the shared Unit/Width/Height controls.
        Uses exact spinbox values directly when unit is 'px', and 300 DPI conversion for 'mm'/'in'.
        """
        w_mm, h_mm = self._get_current_dimensions_in_mm()
        if w_mm <= 0 or h_mm <= 0:
            return (None, w_mm, h_mm)

        if self._current_unit == "px":
            target_w_px = max(1, int(round(self.spin_custom_w.value())))
            target_h_px = max(1, int(round(self.spin_custom_h.value())))
        else:
            target_w_px = max(1, int(round(w_mm * engine.PX_PER_MM)))
            target_h_px = max(1, int(round(h_mm * engine.PX_PER_MM)))

        return ((target_w_px, target_h_px), w_mm, h_mm)

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

    def _configure_unit_spinboxes(self, unit: str) -> None:
        """Applies precision, step, range, and suffix formatting to dimension spinboxes."""
        if unit == "in":
            self.spin_custom_w.setDecimals(2)
            self.spin_custom_h.setDecimals(2)
            self.spin_custom_w.setSingleStep(0.1)
            self.spin_custom_h.setSingleStep(0.1)
            self.spin_custom_w.setRange(0.2, 50.0)
            self.spin_custom_h.setRange(0.2, 50.0)
            self.spin_custom_w.setSuffix(" in")
            self.spin_custom_h.setSuffix(" in")
        elif unit == "px":
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

    def _on_unit_changed(self, new_unit: str):
        if self._block_signals or new_unit == self._current_unit:
            return

        new_w = self._convert_mm_to_unit(self._dim_w_mm, new_unit)
        new_h = self._convert_mm_to_unit(self._dim_h_mm, new_unit)

        self._block_signals = True
        try:
            self._configure_unit_spinboxes(new_unit)
            self.spin_custom_w.setValue(new_w)
            self.spin_custom_h.setValue(new_h)
            self._current_unit = new_unit
            ws = self._current_workspace()
            if ws is not None:
                ws.crop.unit = new_unit
        finally:
            self._block_signals = False

    def _on_preset_changed(self, text: str):
        if self._block_signals:
            return

        ws = self._current_workspace()
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

            if ws is not None:
                ws.crop.preset_name = text
                ws.crop.dim_w_mm = w_mm
                ws.crop.dim_h_mm = h_mm

            aspect = w_mm / h_mm if h_mm > 0 else 1.0
            self.canvas.set_aspect_ratio(aspect)
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=aspect)
            self._update_crop_button_state()
            self.statusBar().showMessage(
                f"Preset loaded: {text} ({w_mm:.1f} x {h_mm:.1f} mm). Frame with box, then click Apply Crop.",
                5000
            )
        elif text == "Freeform / Original":
            if ws is not None:
                ws.crop.preset_name = text
            self.canvas.set_aspect_ratio(None)
            self._update_crop_button_state()
            self.statusBar().showMessage("Freeform: Drag any box freely or leave full image.", 3000)
        elif text == "Custom Size":
            if ws is not None:
                ws.crop.preset_name = text
            w_mm, h_mm = self._get_current_dimensions_in_mm()
            aspect = w_mm / h_mm if h_mm > 0 else 1.0
            self.canvas.set_aspect_ratio(aspect)
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=aspect)
            self._update_crop_button_state()

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

        ws = self._current_workspace()
        if ws is not None:
            ws.crop.dim_w_mm = self._dim_w_mm
            ws.crop.dim_h_mm = self._dim_h_mm
            ws.crop.preset_name = "Custom Size"

        # Do not modify or spawn a rectangular crop box while in Straighten mode
        if self.canvas.crop_mode != "standard":
            return

        self._update_crop_button_state()

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
            ws = self._current_workspace()
            if ws is not None:
                ws.crop.roi = None
            self._update_crop_button_state()
            self._trigger_render()
        elif mode_id == 1:  # Patch ID
            if not self.canvas.get_roi_box():
                self.canvas.spawn_centered_box(aspect_ratio=None)
            self._update_crop_button_state()
            self._trigger_render()

    def _on_apply_crop(self):
        ws = self._current_workspace()
        if ws is None:
            QMessageBox.information(self, "No Photo", "Please add or select a photo first.")
            return

        roi_box = self.canvas.get_roi_box()
        if not roi_box:
            w, h = ws.baked.size
            roi_box = (0, 0, w, h)

        preset = self.combo_presets.currentText()
        target_px = None
        w_mm = 0.0
        h_mm = 0.0
        if preset != "Freeform / Original":
            target_px, w_mm, h_mm = self._get_target_dimensions_px_and_mm()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._sync_ui_to_workspace(ws)
            desc = f"Crop to {w_mm:.1f}x{h_mm:.1f} mm" if target_px else "Crop to Selection"
            ws.push_undo(desc)
            ws.baked = engine.crop_and_resize(ws.baked, roi_box, target_px)
            ws.orig = engine.crop_and_resize(ws.orig, roi_box, target_px)
            ws.target_w_mm = w_mm if target_px else None
            ws.target_h_mm = h_mm if target_px else None
            ws.crop.roi = None

            self._finalize_geometry_edit(ws)

            dim_text = f" ({w_mm:.1f} x {h_mm:.1f} mm)" if target_px else ""
            self.statusBar().showMessage(
                f"✂️ Cropped photo to {ws.baked.width} x {ws.baked.height} px{dim_text} with zero distortion",
                5000
            )
        except Exception as e:
            QMessageBox.critical(self, "Crop Error", f"Failed to crop image:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _sync_ai_controls_enabled(self) -> None:
        """Enables or disables AI sub-controls based on AI toggle and backdrop choice."""
        checked = self.chk_remove_bg.isChecked()
        self.combo_ai_model.setEnabled(checked)
        self.combo_backdrop.setEnabled(checked)
        self.slider_choke.setEnabled(checked)
        self.slider_feather.setEnabled(checked)
        self.btn_pick_color.setEnabled(checked and "Custom" in self.combo_backdrop.currentText())

    def _on_ai_toggled(self, checked: bool):
        self._sync_ai_controls_enabled()
        self._trigger_render()

    def _on_backdrop_changed(self, text: str):
        self._sync_ai_controls_enabled()
        self._trigger_render()

    def _on_pick_custom_color(self):
        qcolor = QColorDialog.getColor(QColor(*self._custom_bg_color), self, "Select Backdrop Color")
        if qcolor.isValid():
            self._custom_bg_color = (qcolor.red(), qcolor.green(), qcolor.blue())
            ws = self._current_workspace()
            if ws is not None:
                ws.retouch.custom_color = self._custom_bg_color
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
        ws = self._current_workspace()
        if ws is not None:
            ws.retouch.reset_lighting()
        self._trigger_render()

    def _collect_retouch_state(self) -> RetouchState:
        """Reads current AI, lighting, and box-scope controls into a RetouchState."""
        return RetouchState(
            remove_bg=self.chk_remove_bg.isChecked(),
            ai_model="RMBG-1.4" if "RMBG" in self.combo_ai_model.currentText() else "MODNet",
            backdrop=self.combo_backdrop.currentText(),
            custom_color=self._custom_bg_color,
            choke_px=self.slider_choke.value(),
            feather_px=self.slider_feather.value() / 10.0,
            brightness=self.slider_bright.value() / 100.0,
            contrast=self.slider_contrast.value() / 100.0,
            saturation=self.slider_sat.value() / 100.0,
            sharpness=self.slider_sharp.value() / 100.0,
            warmth=self.slider_warmth.value(),
            edit_inside_box=(self.bg_roi_mode.checkedId() == 1),
        )

    def _get_current_params(self) -> Dict[str, Any]:
        w_mm, h_mm = self._get_current_dimensions_in_mm()
        return self._collect_retouch_state().to_engine_params(
            self.combo_presets.currentText(), w_mm, h_mm
        )

    # -------------------------------------------------------------------------
    # Core Synchronous Rendering Pipeline
    # -------------------------------------------------------------------------

    def _trigger_render(self):
        if self._block_signals:
            return
        ws = self._current_workspace()
        if ws is None:
            return

        retouch = self._collect_retouch_state()
        ws.retouch = retouch
        w_mm, h_mm = self._get_current_dimensions_in_mm()
        params = retouch.to_engine_params(self.combo_presets.currentText(), w_mm, h_mm)
        roi_box = self.canvas.get_roi_box()
        mode_str = "patch" if retouch.edit_inside_box else "whole"

        # Synchronous execution with wait cursor
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = engine.process_image_pipeline(
                full_img=ws.baked,
                roi_box=roi_box,
                roi_mode=mode_str,
                params=params,
                seg_engine=engine.GLOBAL_SEGMENTATION_ENGINE
            )
            ws.processed = result
            if self.canvas.crop_mode == "standard":
                ws.crop.roi = roi_box

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
        ws = self._current_workspace()
        if ws is None:
            return
        proc = ws.processed
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
        ws = self._current_workspace()
        if ws is None:
            QMessageBox.information(self, "No Photo", "Please select a photo to send to print queue.")
            return
        proc = ws.processed if ws.processed else ws.baked

        if ws.target_w_mm and ws.target_h_mm:
            w_mm = ws.target_w_mm
            h_mm = ws.target_h_mm
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

        self.tab_printer.add_photo(proc, w_mm, h_mm, copies=4, label=ws.name)
        self.statusBar().showMessage(f"Added to A4 Queue: {ws.name} ({w_mm:.1f} x {h_mm:.1f} mm)", 4000)

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
