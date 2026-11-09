"""
main.py - Native Windows 11 ARM64 Photo Studio & A4 Print Studio.
Pure PySide6 desktop application with 100% offline ONNX inference and 1:1 hardware printing.
"""

import sys
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from PySide6.QtCore import (
    Qt, QRectF, QPointF, Signal, Slot, QMarginsF, QSize, QMimeData
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
    QGraphicsItem, QFrame, QStatusBar, QSizePolicy, QAbstractItemView
)
from PIL import Image

import engine
import printer


def pil_to_pixmap(pil_img: Image.Image) -> QPixmap:
    """Safely converts a PIL Image to a PySide6 QPixmap."""
    qimg = printer.pil_to_qimage(pil_img)
    return QPixmap.fromImage(qimg)


class ROIHandle(QGraphicsRectItem):
    """Interactive handle for resizing ROI rectangle."""
    HANDLE_SIZE = 10.0

    def __init__(self, position_key: str, parent: 'ROIRectItem'):
        super().__init__(-self.HANDLE_SIZE / 2, -self.HANDLE_SIZE / 2, self.HANDLE_SIZE, self.HANDLE_SIZE, parent)
        self.position_key = position_key
        self.roi_parent = parent
        self.setPen(QPen(QColor(255, 255, 255), 1.5))
        self.setBrush(QBrush(QColor(0, 160, 255)))
        self.setZValue(20)
        self.setAcceptHoverEvents(True)
        self._update_cursor()

    def _update_cursor(self):
        cursors = {
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            "tm": Qt.SizeVerCursor,   "bm": Qt.SizeVerCursor,
            "ml": Qt.SizeHorCursor,   "mr": Qt.SizeHorCursor,
        }
        self.setCursor(cursors.get(self.position_key, Qt.ArrowCursor))


class ROIRectItem(QGraphicsRectItem):
    """Interactive ROI Box with move and 8-point resize handles."""

    def __init__(self, rect: QRectF, bounds: QRectF, on_change_callback):
        super().__init__(rect)
        self.bounds = bounds
        self.on_change_callback = on_change_callback
        self.setZValue(10)

        # Dashed cyan line with subtle yellow accent
        pen = QPen(QColor(0, 220, 255), 2, Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(0, 180, 255, 30)))  # Semi-transparent fill

        self.setFlags(
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemIsFocusable
        )
        self.setCursor(Qt.SizeAllCursor)

        # Create 8 handles
        self.handles: Dict[str, ROIHandle] = {}
        for key in ["tl", "tm", "tr", "mr", "br", "bm", "bl", "ml"]:
            self.handles[key] = ROIHandle(key, self)

        self._active_handle: Optional[str] = None
        self._is_dragging_rect = False
        self._drag_start_scene = QPointF()
        self._rect_at_drag_start = QRectF()

        self.update_handle_positions()

    def update_handle_positions(self):
        r = self.rect()
        positions = {
            "tl": QPointF(r.left(), r.top()),
            "tm": QPointF(r.center().x(), r.top()),
            "tr": QPointF(r.right(), r.top()),
            "mr": QPointF(r.right(), r.center().y()),
            "br": QPointF(r.right(), r.bottom()),
            "bm": QPointF(r.center().x(), r.bottom()),
            "bl": QPointF(r.left(), r.bottom()),
            "ml": QPointF(r.left(), r.center().y()),
        }
        for k, h in self.handles.items():
            h.setPos(positions[k])

    def mousePressEvent(self, event):
        pos = event.pos()
        self._active_handle = None
        for key, handle in self.handles.items():
            if handle.contains(handle.mapFromParent(pos)):
                self._active_handle = key
                break

        self._drag_start_scene = event.scenePos()
        self._rect_at_drag_start = self.rect()

        if self._active_handle is None and self.contains(pos):
            self._is_dragging_rect = True

        event.accept()

    def mouseMoveEvent(self, event):
        delta = event.scenePos() - self._drag_start_scene
        r = QRectF(self._rect_at_drag_start)

        if self._active_handle:
            k = self._active_handle
            left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()

            if "l" in k: left += delta.x()
            if "r" in k: right += delta.x()
            if "t" in k: top += delta.y()
            if "b" in k: bottom += delta.y()

            # Constrain to bounds
            left = max(self.bounds.left(), min(left, right - 10))
            right = min(self.bounds.right(), max(right, left + 10))
            top = max(self.bounds.top(), min(top, bottom - 10))
            bottom = min(self.bounds.bottom(), max(bottom, top + 10))

            new_r = QRectF(left, top, right - left, bottom - top)
            self.setRect(new_r)
            self.update_handle_positions()
            event.accept()
            return

        elif self._is_dragging_rect:
            dx = delta.x()
            dy = delta.y()

            if r.left() + dx < self.bounds.left():
                dx = self.bounds.left() - r.left()
            if r.right() + dx > self.bounds.right():
                dx = self.bounds.right() - r.right()
            if r.top() + dy < self.bounds.top():
                dy = self.bounds.top() - r.top()
            if r.bottom() + dy > self.bounds.bottom():
                dy = self.bounds.bottom() - r.bottom()

            new_r = r.translated(dx, dy)
            self.setRect(new_r)
            self.update_handle_positions()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._active_handle = None
        self._is_dragging_rect = False
        if self.on_change_callback:
            r = self.rect().normalized()
            self.on_change_callback((int(r.left()), int(r.top()), int(r.right()), int(r.bottom())))
        event.accept()


class InteractiveCanvas(QGraphicsView):
    """
    QGraphicsView supporting pan/zoom, interactive ROI rubber-band/handles,
    and drag-and-drop file imports.
    """
    roiChanged = Signal(tuple)
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(24, 24, 27)))
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptDrops(True)

        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.roi_item: Optional[ROIRectItem] = None

        self._is_rubber_banding = False
        self._rubber_start_pt = QPointF()
        self._rubber_rect_item: Optional[QGraphicsRectItem] = None
        self._is_panning = False
        self._pan_start = QPointF()

    def set_pixmap(self, pixmap: QPixmap, keep_roi: bool = True):
        old_roi = self.get_roi_box() if (keep_roi and self.roi_item) else None
        self.scene.clear()
        self.roi_item = None
        self._rubber_rect_item = None

        if pixmap.isNull():
            return

        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        if old_roi:
            self.set_roi_box(old_roi)

    def get_roi_box(self) -> Optional[Tuple[int, int, int, int]]:
        if self.roi_item:
            r = self.roi_item.rect().normalized()
            return (int(r.left()), int(r.top()), int(r.right()), int(r.bottom()))
        return None

    def set_roi_box(self, box: Optional[Tuple[int, int, int, int]]):
        if self.roi_item:
            self.scene.removeItem(self.roi_item)
            self.roi_item = None

        if not box or not self.pixmap_item:
            return

        x1, y1, x2, y2 = box
        bounds = QRectF(self.pixmap_item.pixmap().rect())
        r = QRectF(x1, y1, x2 - x1, y2 - y1).intersected(bounds)
        if r.width() >= 10 and r.height() >= 10:
            self.roi_item = ROIRectItem(r, bounds, self._on_roi_modified)
            self.scene.addItem(self.roi_item)

    def _on_roi_modified(self, box: Tuple[int, int, int, int]):
        self.roiChanged.emit(box)

    def fit_image(self):
        if self.pixmap_item:
            self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def zoom(self, factor: float):
        self.scale(factor, factor)

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom(1.15)
        else:
            self.zoom(1.0 / 1.15)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and event.modifiers() & Qt.AltModifier):
            self._is_panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        # If click is on existing ROI handles or item, let item handle it
        item = self.itemAt(event.pos())
        if isinstance(item, (ROIHandle, ROIRectItem)):
            super().mousePressEvent(event)
            return

        # Otherwise start drawing a new ROI box with left button
        if event.button() == Qt.LeftButton and self.pixmap_item:
            scene_pt = self.mapToScene(event.pos())
            bounds = QRectF(self.pixmap_item.pixmap().rect())
            if bounds.contains(scene_pt):
                self._is_rubber_banding = True
                self._rubber_start_pt = scene_pt
                if self.roi_item:
                    self.scene.removeItem(self.roi_item)
                    self.roi_item = None
                if self._rubber_rect_item:
                    self.scene.removeItem(self._rubber_rect_item)
                self._rubber_rect_item = QGraphicsRectItem(QRectF(scene_pt, scene_pt))
                self._rubber_rect_item.setPen(QPen(QColor(0, 220, 255), 2, Qt.DashLine))
                self._rubber_rect_item.setBrush(QBrush(QColor(0, 180, 255, 30)))
                self.scene.addItem(self._rubber_rect_item)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self._is_rubber_banding and self._rubber_rect_item and self.pixmap_item:
            curr_pt = self.mapToScene(event.pos())
            bounds = QRectF(self.pixmap_item.pixmap().rect())
            curr_pt.setX(max(bounds.left(), min(curr_pt.x(), bounds.right())))
            curr_pt.setY(max(bounds.top(), min(curr_pt.y(), bounds.bottom())))
            rect = QRectF(self._rubber_start_pt, curr_pt).normalized()
            self._rubber_rect_item.setRect(rect)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if self._is_rubber_banding and self._rubber_rect_item and self.pixmap_item:
            self._is_rubber_banding = False
            final_rect = self._rubber_rect_item.rect().normalized()
            self.scene.removeItem(self._rubber_rect_item)
            self._rubber_rect_item = None

            bounds = QRectF(self.pixmap_item.pixmap().rect())
            if final_rect.width() >= 15 and final_rect.height() >= 15:
                box = (
                    int(final_rect.left()),
                    int(final_rect.top()),
                    int(final_rect.right()),
                    int(final_rect.bottom())
                )
                self.set_roi_box(box)
                self.roiChanged.emit(box)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        valid_paths = []
        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
        for url in urls:
            path = url.toLocalFile()
            if path and Path(path).suffix.lower() in valid_exts:
                valid_paths.append(path)
        if valid_paths:
            self.filesDropped.emit(valid_paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


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

        # Print queue: List of {"image": PIL.Image, "width_mm": float, "height_mm": float, "copies": int, "label": str}
        self.print_queue: List[Dict[str, Any]] = []

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
        self.tab_printer = QWidget()
        self._build_printer_tab(self.tab_printer)
        self.tabs.addTab(self.tab_printer, "🖨️ A4 Print Studio")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _build_studio_tab(self, parent_widget: QWidget):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # 1. Left Panel (Workspace & ROI Mode)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)
        left_panel.setFixedWidth(280)

        # Photo list group
        grp_workspace = QGroupBox("📁 Photo Workspace")
        grp_workspace_layout = QVBoxLayout(grp_workspace)
        grp_workspace_layout.setSpacing(6)

        btn_row_1 = QHBoxLayout()
        self.btn_add_photos = QPushButton("📂 Add Photo(s)")
        self.btn_add_photos.clicked.connect(self._on_open_files)
        self.btn_paste = QPushButton("📋 Paste (Ctrl+V)")
        self.btn_paste.clicked.connect(self._on_paste_clipboard)
        btn_row_1.addWidget(self.btn_add_photos)
        btn_row_1.addWidget(self.btn_paste)
        grp_workspace_layout.addLayout(btn_row_1)

        self.list_photos = QListWidget()
        self.list_photos.setIconSize(QSize(48, 48))
        self.list_photos.currentRowChanged.connect(self._on_photo_selected)
        grp_workspace_layout.addWidget(self.list_photos)

        self.btn_remove_photo = QPushButton("🗑️ Remove Selected")
        self.btn_remove_photo.clicked.connect(self._on_remove_photo)
        grp_workspace_layout.addWidget(self.btn_remove_photo)
        left_layout.addWidget(grp_workspace)

        # Box Selection Mode
        grp_roi_mode = QGroupBox("🔲 Box Selection Mode")
        grp_roi_layout = QVBoxLayout(grp_roi_mode)
        self.bg_roi_mode = QButtonGroup(self)

        self.radio_mode_whole = QRadioButton("Whole Image (Ignore Box)")
        self.radio_mode_patch = QRadioButton("Edit Inside Box Only (Patch ID)")
        self.radio_mode_crop = QRadioButton("Crop to Box (Extract Photo)")
        self.radio_mode_whole.setChecked(True)

        self.bg_roi_mode.addButton(self.radio_mode_whole, 0)
        self.bg_roi_mode.addButton(self.radio_mode_patch, 1)
        self.bg_roi_mode.addButton(self.radio_mode_crop, 2)
        self.bg_roi_mode.idClicked.connect(lambda _: self._trigger_render())

        grp_roi_layout.addWidget(self.radio_mode_whole)
        grp_roi_layout.addWidget(self.radio_mode_patch)
        grp_roi_layout.addWidget(self.radio_mode_crop)

        self.btn_bake_edit = QPushButton("✔️ Bake / Commit Edit to Image")
        self.btn_bake_edit.setToolTip("Permanently commits current patch or lighting into image base")
        self.btn_bake_edit.clicked.connect(self._on_bake_edit)
        grp_roi_layout.addWidget(self.btn_bake_edit)
        left_layout.addWidget(grp_roi_mode)

        # Physical Preset Sizes
        grp_preset = QGroupBox("📏 Physical Output Size")
        grp_preset_layout = QVBoxLayout(grp_preset)

        self.combo_presets = QComboBox()
        for preset_name in engine.PRESET_SIZES.keys():
            self.combo_presets.addItem(preset_name)
        self.combo_presets.currentTextChanged.connect(self._on_preset_changed)
        grp_preset_layout.addWidget(self.combo_presets)

        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("W (mm):"))
        self.spin_custom_w = QDoubleSpinBox()
        self.spin_custom_w.setRange(5.0, 300.0)
        self.spin_custom_w.setValue(35.0)
        self.spin_custom_w.setSingleStep(1.0)
        self.spin_custom_w.setEnabled(False)
        self.spin_custom_w.valueChanged.connect(lambda _: self._trigger_render())
        custom_row.addWidget(self.spin_custom_w)

        custom_row.addWidget(QLabel("H (mm):"))
        self.spin_custom_h = QDoubleSpinBox()
        self.spin_custom_h.setRange(5.0, 300.0)
        self.spin_custom_h.setValue(45.0)
        self.spin_custom_h.setSingleStep(1.0)
        self.spin_custom_h.setEnabled(False)
        self.spin_custom_h.valueChanged.connect(lambda _: self._trigger_render())
        custom_row.addWidget(self.spin_custom_h)

        grp_preset_layout.addLayout(custom_row)
        left_layout.addWidget(grp_preset)
        left_layout.addStretch()

        splitter.addWidget(left_panel)

        # 2. Center Panel (Interactive Canvas + Top Toolbar)
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_zoom_in = QPushButton("🔍+ Zoom In")
        self.btn_zoom_in.clicked.connect(lambda: self.canvas.zoom(1.2))
        self.btn_zoom_out = QPushButton("🔍- Zoom Out")
        self.btn_zoom_out.clicked.connect(lambda: self.canvas.zoom(1 / 1.2))
        self.btn_fit = QPushButton("📐 Fit to Window")
        self.btn_fit.clicked.connect(lambda: self.canvas.fit_image())
        self.btn_rotate = QPushButton("🔄 Rotate 90° CW")
        self.btn_rotate.clicked.connect(self._on_rotate_90)
        self.btn_reset_roi = QPushButton("⬜ Reset Box")
        self.btn_reset_roi.clicked.connect(self._on_reset_roi)

        self.btn_compare = QPushButton("👁️ Hold to Compare Original")
        self.btn_compare.pressed.connect(self._on_compare_pressed)
        self.btn_compare.released.connect(self._on_compare_released)

        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.btn_fit)
        toolbar.addWidget(self.btn_rotate)
        toolbar.addWidget(self.btn_reset_roi)
        toolbar.addWidget(self.btn_compare)
        toolbar.addStretch()
        center_layout.addLayout(toolbar)

        # Canvas
        self.canvas = InteractiveCanvas()
        self.canvas.roiChanged.connect(self._on_canvas_roi_changed)
        self.canvas.filesDropped.connect(self._load_image_paths)
        center_layout.addWidget(self.canvas)

        splitter.addWidget(center_panel)

        # 3. Right Panel (AI Segmentation & Lighting)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(6)
        right_panel.setFixedWidth(320)

        # AI Background Group
        grp_ai = QGroupBox("🤖 AI Background Removal")
        grp_ai_layout = QVBoxLayout(grp_ai)
        grp_ai_layout.setSpacing(6)

        self.chk_remove_bg = QCheckBox("Enable AI Background Removal")
        self.chk_remove_bg.setChecked(False)
        self.chk_remove_bg.toggled.connect(self._on_ai_toggled)
        grp_ai_layout.addWidget(self.chk_remove_bg)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self.combo_ai_model = QComboBox()
        self.combo_ai_model.addItems(["RMBG-1.4 (High Precision)", "MODNet (Fast Portrait)"])
        self.combo_ai_model.currentTextChanged.connect(lambda _: self._trigger_render())
        model_row.addWidget(self.combo_ai_model)
        grp_ai_layout.addLayout(model_row)

        backdrop_row = QHBoxLayout()
        backdrop_row.addWidget(QLabel("Backdrop:"))
        self.combo_backdrop = QComboBox()
        self.combo_backdrop.addItems([
            "Studio White", "Passport Grey", "Standard Blue",
            "Corporate Navy", "Soft Blur", "Custom Solid Color..."
        ])
        self.combo_backdrop.currentTextChanged.connect(self._on_backdrop_changed)
        backdrop_row.addWidget(self.combo_backdrop)
        grp_ai_layout.addLayout(backdrop_row)

        self.btn_pick_color = QPushButton("🎨 Pick Custom Color")
        self.btn_pick_color.setEnabled(False)
        self.btn_pick_color.clicked.connect(self._on_pick_custom_color)
        grp_ai_layout.addWidget(self.btn_pick_color)

        # Edge refinement
        lbl_choke_row = QHBoxLayout()
        lbl_choke_row.addWidget(QLabel("Edge Choke (Halo Cut):"))
        self.lbl_choke_val = QLabel("0 px")
        lbl_choke_row.addWidget(self.lbl_choke_val)
        grp_ai_layout.addLayout(lbl_choke_row)

        self.slider_choke = QSlider(Qt.Horizontal)
        self.slider_choke.setRange(0, 5)
        self.slider_choke.setValue(0)
        self.slider_choke.valueChanged.connect(self._on_choke_changed)
        grp_ai_layout.addWidget(self.slider_choke)

        lbl_feather_row = QHBoxLayout()
        lbl_feather_row.addWidget(QLabel("Edge Feather (Softness):"))
        self.lbl_feather_val = QLabel("0.0 px")
        lbl_feather_row.addWidget(self.lbl_feather_val)
        grp_ai_layout.addLayout(lbl_feather_row)

        self.slider_feather = QSlider(Qt.Horizontal)
        self.slider_feather.setRange(0, 50)
        self.slider_feather.setValue(0)
        self.slider_feather.valueChanged.connect(self._on_feather_changed)
        grp_ai_layout.addWidget(self.slider_feather)

        right_layout.addWidget(grp_ai)

        # Lighting & Color Adjustments Group
        grp_lighting = QGroupBox("☀️ Lighting & Color Grading")
        grp_lighting_layout = QVBoxLayout(grp_lighting)
        grp_lighting_layout.setSpacing(4)

        # Helper to create slider rows
        def create_slider(name: str, min_v: int, max_v: int, def_v: int, suffix: str = "%"):
            header = QHBoxLayout()
            lbl_title = QLabel(name)
            lbl_val = QLabel(f"{def_v}{suffix}")
            header.addWidget(lbl_title)
            header.addStretch()
            header.addWidget(lbl_val)
            slider = QSlider(Qt.Horizontal)
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

        # Bottom Actions
        self.btn_save_photo = QPushButton("💾 Save Single Photo (PNG/JPG)")
        self.btn_save_photo.clicked.connect(self._on_save_single_photo)
        right_layout.addWidget(self.btn_save_photo)

        self.btn_send_queue = QPushButton("➕ Send to A4 Print Queue")
        self.btn_send_queue.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 8px;")
        self.btn_send_queue.clicked.connect(self._on_send_to_print_queue)
        right_layout.addWidget(self.btn_send_queue)

        right_layout.addStretch()
        splitter.addWidget(right_panel)

        splitter.setSizes([280, 720, 320])

    def _build_printer_tab(self, parent_widget: QWidget):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Left: Queue & Layout settings
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setFixedWidth(360)
        left_layout.setContentsMargins(4, 4, 4, 4)

        grp_queue = QGroupBox("📋 A4 Print Queue")
        grp_queue_layout = QVBoxLayout(grp_queue)

        self.tbl_queue = QTableWidget(0, 4)
        self.tbl_queue.setHorizontalHeaderLabels(["Preview", "Size (mm)", "Copies", "Action"])
        self.tbl_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_queue.setSelectionBehavior(QAbstractItemView.SelectRows)
        grp_queue_layout.addWidget(self.tbl_queue)

        self.btn_clear_queue = QPushButton("🗑️ Clear Entire Queue")
        self.btn_clear_queue.clicked.connect(self._on_clear_queue)
        grp_queue_layout.addWidget(self.btn_clear_queue)
        left_layout.addWidget(grp_queue)

        grp_layout_settings = QGroupBox("📐 A4 Page Layout Settings")
        grp_settings_layout = QVBoxLayout(grp_layout_settings)

        margin_row = QHBoxLayout()
        margin_row.addWidget(QLabel("Page Margin (mm):"))
        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0.0, 30.0)
        self.spin_margin.setValue(10.0)
        self.spin_margin.setSingleStep(1.0)
        self.spin_margin.valueChanged.connect(self._regenerate_a4_preview)
        margin_row.addWidget(self.spin_margin)
        grp_settings_layout.addLayout(margin_row)

        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel("Gap Between Photos (mm):"))
        self.spin_gap = QDoubleSpinBox()
        self.spin_gap.setRange(0.0, 20.0)
        self.spin_gap.setValue(2.0)
        self.spin_gap.setSingleStep(0.5)
        self.spin_gap.valueChanged.connect(self._regenerate_a4_preview)
        gap_row.addWidget(self.spin_gap)
        grp_settings_layout.addLayout(gap_row)

        self.chk_cut_lines = QCheckBox("Draw Light-Grey Scissor Cut Lines")
        self.chk_cut_lines.setChecked(True)
        self.chk_cut_lines.toggled.connect(self._regenerate_a4_preview)
        grp_settings_layout.addWidget(self.chk_cut_lines)

        self.lbl_queue_status = QLabel("Placed: 0 photos | Overflow: 0 photos")
        self.lbl_queue_status.setStyleSheet("font-weight: bold; color: #38bdf8;")
        grp_settings_layout.addWidget(self.lbl_queue_status)

        left_layout.addWidget(grp_layout_settings)
        left_layout.addStretch()

        # Primary Output Bar
        grp_output = QGroupBox("🖨️ Hardware Printing & Export")
        grp_output_layout = QVBoxLayout(grp_output)

        self.btn_print_hw = QPushButton("🖨️ Print Directly (1:1 Hardware A4)")
        self.btn_print_hw.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 10px;")
        self.btn_print_hw.clicked.connect(self._on_print_hardware)
        grp_output_layout.addWidget(self.btn_print_hw)

        self.btn_export_png = QPushButton("💾 Save 300-DPI A4 PNG")
        self.btn_export_png.clicked.connect(self._on_export_a4_png)
        grp_output_layout.addWidget(self.btn_export_png)

        self.btn_export_pdf = QPushButton("📄 Save 300-DPI A4 PDF")
        self.btn_export_pdf.clicked.connect(self._on_export_a4_pdf)
        grp_output_layout.addWidget(self.btn_export_pdf)

        left_layout.addWidget(grp_output)
        layout.addWidget(left_panel)

        # Right: Live A4 Preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self.a4_canvas = InteractiveCanvas()
        right_layout.addWidget(self.a4_canvas)
        layout.addWidget(right_panel, stretch=1)

        self._cached_a4_sheet: Optional[Image.Image] = None

    def _setup_shortcuts(self):
        # Global Ctrl+V clipboard paste shortcut
        paste_shortcut = QShortcut(QKeySequence.Paste, self)
        paste_shortcut.activated.connect(self._on_paste_clipboard)

    def _apply_dark_style(self):
        dark_qss = """
        QMainWindow, QWidget {
            background-color: #18181b;
            color: #f4f4f5;
            font-family: 'Segoe UI', sans-serif;
            font-size: 13px;
        }
        QGroupBox {
            border: 1px solid #3f3f46;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 12px;
            font-weight: bold;
            color: #e4e4e7;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            color: #38bdf8;
        }
        QPushButton {
            background-color: #27272a;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            padding: 5px 10px;
            color: #f4f4f5;
        }
        QPushButton:hover {
            background-color: #3f3f46;
            border-color: #52525b;
        }
        QPushButton:pressed {
            background-color: #52525b;
        }
        QPushButton:disabled {
            background-color: #1f1f23;
            color: #71717a;
            border-color: #27272a;
        }
        QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #27272a;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            padding: 4px;
            color: #f4f4f5;
        }
        QComboBox::drop-down {
            border: none;
        }
        QListWidget, QTableWidget {
            background-color: #27272a;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            color: #f4f4f5;
        }
        QListWidget::item:selected, QTableWidget::item:selected {
            background-color: #0284c7;
            color: white;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #3f3f46;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #0284c7;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #38bdf8;
            width: 14px;
            margin-top: -4px;
            margin-bottom: -4px;
            border-radius: 7px;
        }
        QTabWidget::pane {
            border: 1px solid #27272a;
        }
        QTabBar::tab {
            background: #27272a;
            border: 1px solid #3f3f46;
            padding: 8px 18px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            color: #a1a1aa;
            font-weight: bold;
        }
        QTabBar::tab:selected {
            background: #3f3f46;
            color: #38bdf8;
            border-bottom-color: #3f3f46;
        }
        QHeaderView::section {
            background-color: #27272a;
            color: #e4e4e7;
            border: 1px solid #3f3f46;
            padding: 4px;
        }
        QStatusBar {
            background-color: #121214;
            color: #a1a1aa;
        }
        """
        self.setStyleSheet(dark_qss)

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
            "orig": img.copy(),
            "baked": img.copy(),
            "processed": img.copy(),
            "roi": None,
            "params": self._get_current_params()
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

    def _on_photo_selected(self, row: int):
        if row < 0 or row >= len(self.workspace_photos):
            self.current_photo_idx = -1
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
        finally:
            self._block_signals = False

        self._trigger_render()
        self.canvas.fit_image()

    def _on_bake_edit(self):
        if self.current_photo_idx < 0:
            return
        item = self.workspace_photos[self.current_photo_idx]
        if item.get("processed"):
            # Update baked image to current output
            item["baked"] = item["processed"].copy()
            item["roi"] = None
            self.canvas.set_pixmap(pil_to_pixmap(item["baked"]), keep_roi=False)
            self._on_reset_lighting()
            self._on_reset_roi()
            self.statusBar().showMessage("Current edits baked successfully into base image", 4000)

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
        item["baked"] = item["baked"].rotate(-90, expand=True)
        item["roi"] = None
        self.canvas.set_pixmap(pil_to_pixmap(item["baked"]), keep_roi=False)
        self._trigger_render()
        self.canvas.fit_image()

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
    # Settings & Parameter Handlers
    # -------------------------------------------------------------------------

    def _on_preset_changed(self, text: str):
        is_custom = (text == "Custom Size (mm)")
        self.spin_custom_w.setEnabled(is_custom)
        self.spin_custom_h.setEnabled(is_custom)
        self._trigger_render()

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
            "custom_w_mm": self.spin_custom_w.value(),
            "custom_h_mm": self.spin_custom_h.value(),
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
        mode_str = "whole"
        if mode_id == 1:
            mode_str = "patch"
        elif mode_id == 2:
            mode_str = "crop"

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
            return
        item = self.workspace_photos[self.current_photo_idx]
        proc = item.get("processed")
        if not proc:
            return

        preset = self.combo_presets.currentText()
        if preset == "Custom Size (mm)":
            w_mm = self.spin_custom_w.value()
            h_mm = self.spin_custom_h.value()
        elif preset in engine.PRESET_SIZES and engine.PRESET_SIZES[preset][0] is not None:
            w_mm, h_mm, _, _ = engine.PRESET_SIZES[preset]
        else:
            # Default to standard passport 35x45 mm if freeform
            w_mm = round(proc.width / engine.PX_PER_MM, 1)
            h_mm = round(proc.height / engine.PX_PER_MM, 1)

        queue_entry = {
            "image": proc.copy(),
            "width_mm": w_mm,
            "height_mm": h_mm,
            "copies": 4,  # default 4 copies
            "label": item["name"]
        }
        self.print_queue.append(queue_entry)
        self._refresh_queue_table()
        self.statusBar().showMessage(f"Added to A4 Queue: {item['name']} ({w_mm} x {h_mm} mm)", 4000)

    # -------------------------------------------------------------------------
    # A4 Print Studio Handlers
    # -------------------------------------------------------------------------

    def _on_tab_changed(self, idx: int):
        if idx == 1:
            # Switched to A4 Print Studio
            self._regenerate_a4_preview()

    def _refresh_queue_table(self):
        self.tbl_queue.setRowCount(0)
        for i, item in enumerate(self.print_queue):
            self.tbl_queue.insertRow(i)

            # Thumbnail
            thumb = item["image"].copy()
            thumb.thumbnail((40, 40), Image.BILINEAR)
            lbl_icon = QLabel()
            lbl_icon.setPixmap(pil_to_pixmap(thumb))
            lbl_icon.setAlignment(Qt.AlignCenter)
            self.tbl_queue.setCellWidget(i, 0, lbl_icon)

            # Dimensions
            dim_str = f"{item['width_mm']:.1f} x {item['height_mm']:.1f} mm"
            dim_item = QTableWidgetItem(dim_str)
            dim_item.setTextAlignment(Qt.AlignCenter)
            self.tbl_queue.setItem(i, 1, dim_item)

            # Copies SpinBox
            spin = QSpinBox()
            spin.setRange(1, 50)
            spin.setValue(item.get("copies", 1))
            spin.valueChanged.connect(lambda val, idx=i: self._on_queue_copies_changed(idx, val))
            self.tbl_queue.setCellWidget(i, 2, spin)

            # Remove Button
            btn_del = QPushButton("❌")
            btn_del.setFixedWidth(30)
            btn_del.clicked.connect(lambda _, idx=i: self._on_remove_queue_item(idx))
            self.tbl_queue.setCellWidget(i, 3, btn_del)

        self._regenerate_a4_preview()

    def _on_queue_copies_changed(self, idx: int, copies: int):
        if 0 <= idx < len(self.print_queue):
            self.print_queue[idx]["copies"] = copies
            self._regenerate_a4_preview()

    def _on_remove_queue_item(self, idx: int):
        if 0 <= idx < len(self.print_queue):
            self.print_queue.pop(idx)
            self._refresh_queue_table()

    def _on_clear_queue(self):
        self.print_queue.clear()
        self._refresh_queue_table()

    def _regenerate_a4_preview(self):
        margin_mm = self.spin_margin.value()
        gap_mm = self.spin_gap.value()
        cut_lines = self.chk_cut_lines.isChecked()

        sheet, placed, overflow = printer.generate_a4_sheet(
            queue_items=self.print_queue,
            margin_mm=margin_mm,
            gap_mm=gap_mm,
            draw_cut_lines=cut_lines
        )
        self._cached_a4_sheet = sheet
        self.lbl_queue_status.setText(f"Placed: {placed} photos | Overflow: {overflow} photos")

        self.a4_canvas.set_pixmap(pil_to_pixmap(sheet), keep_roi=False)
        self.a4_canvas.fit_image()

    def _on_print_hardware(self):
        if self._cached_a4_sheet is None:
            self._regenerate_a4_preview()
        if self._cached_a4_sheet is None:
            return

        ok = printer.print_a4_hardware(self, self._cached_a4_sheet)
        if ok:
            self.statusBar().showMessage("Print job sent successfully to hardware printer!", 5000)

    def _on_export_a4_png(self):
        if self._cached_a4_sheet is None:
            self._regenerate_a4_preview()
        if self._cached_a4_sheet is None:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save A4 Sheet as PNG", "PhotoStudio_A4_300DPI.png",
            "PNG Image (*.png)"
        )
        if filepath:
            try:
                printer.export_a4_png(self._cached_a4_sheet, filepath)
                self.statusBar().showMessage(f"Exported A4 PNG: {filepath}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed saving A4 PNG:\n{e}")

    def _on_export_a4_pdf(self):
        if self._cached_a4_sheet is None:
            self._regenerate_a4_preview()
        if self._cached_a4_sheet is None:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save A4 Sheet as PDF", "PhotoStudio_A4_300DPI.pdf",
            "PDF Document (*.pdf)"
        )
        if filepath:
            try:
                printer.export_a4_pdf(self._cached_a4_sheet, filepath)
                self.statusBar().showMessage(f"Exported A4 PDF: {filepath}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed saving A4 PDF:\n{e}")


def main():
    # Enable high DPI scaling on Windows
    app = QApplication(sys.argv)
    app.setApplicationName("PhotoStudioNative")

    window = PhotoStudioApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
