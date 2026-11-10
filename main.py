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
    QGraphicsItem, QFrame, QStatusBar, QSizePolicy, QAbstractItemView,
    QScrollArea, QGridLayout, QLayout
)
from PIL import Image

import engine
import printer


PRESET_MAP = {
    "Freeform / Original": None,
    "Standard Passport (35 x 45 mm)": (35.0, 45.0),
    "Indian Passport / US Visa (2 x 2 in)": (50.8, 50.8),
    "PAN / ID Portrait (25 x 35 mm)": (25.0, 35.0),
    "Indian Stamp Size (20 x 25 mm)": (20.0, 25.0),
    "Standard ID Card (85.6 x 54 mm)": (85.6, 54.0),
    "Custom Size": None,
}


def pil_to_pixmap(pil_img: Image.Image) -> QPixmap:
    """Safely converts a PIL Image to a PySide6 QPixmap."""
    qimg = printer.pil_to_qimage(pil_img)
    return QPixmap.fromImage(qimg)


class ROIHandle(QGraphicsRectItem):
    """Interactive handle for resizing ROI rectangle."""
    HANDLE_SIZE = 12.0

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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.roi_parent.start_handle_drag(self.position_key, event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.roi_parent.continue_handle_drag(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.roi_parent.end_handle_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ROIRectItem(QGraphicsRectItem):
    """Interactive ROI Box with move and aspect-ratio locked resize handles."""

    def __init__(self, rect: QRectF, bounds: QRectF, on_change_callback, aspect_ratio: Optional[float] = None):
        super().__init__(rect)
        self.bounds = bounds
        self.on_change_callback = on_change_callback
        self.aspect_ratio = aspect_ratio
        self.setZValue(10)

        # Dashed cyan line with semi-transparent fill
        pen = QPen(QColor(0, 220, 255), 2, Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(0, 180, 255, 30)))

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

        self._sync_handle_visibility()
        self.update_handle_positions()

    def set_aspect_ratio(self, ratio: Optional[float]):
        self.aspect_ratio = ratio
        self._sync_handle_visibility()
        self.update_handle_positions()

    def _sync_handle_visibility(self):
        # In fixed aspect-ratio mode, hide mid-edge handles to prevent aspect distortion
        is_fixed = (self.aspect_ratio is not None and self.aspect_ratio > 0)
        for key in ["tm", "bm", "ml", "mr"]:
            if key in self.handles:
                self.handles[key].setVisible(not is_fixed)

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

    def start_handle_drag(self, handle_key: str, scene_pos: QPointF):
        self._active_handle = handle_key
        self._is_dragging_rect = False
        self._drag_start_scene = scene_pos
        self._rect_at_drag_start = QRectF(self.rect())

    def continue_handle_drag(self, scene_pos: QPointF):
        if not self._active_handle:
            return
        r = QRectF(self._rect_at_drag_start)
        k = self._active_handle

        if self.aspect_ratio and self.aspect_ratio > 0:
            ratio = self.aspect_ratio
            if k == "br":
                ax, ay = r.left(), r.top()
                vx = max(15.0, scene_pos.x() - ax)
                vy = max(15.0, scene_pos.y() - ay)
                w = max(vx, vy * ratio)
                max_w = self.bounds.right() - ax
                max_h = self.bounds.bottom() - ay
                w = min(w, max_w, max_h * ratio)
                h = w / ratio
                new_r = QRectF(ax, ay, w, h)
            elif k == "tl":
                ax, ay = r.right(), r.bottom()
                vx = max(15.0, ax - scene_pos.x())
                vy = max(15.0, ay - scene_pos.y())
                w = max(vx, vy * ratio)
                max_w = ax - self.bounds.left()
                max_h = ay - self.bounds.top()
                w = min(w, max_w, max_h * ratio)
                h = w / ratio
                new_r = QRectF(ax - w, ay - h, w, h)
            elif k == "tr":
                ax, ay = r.left(), r.bottom()
                vx = max(15.0, scene_pos.x() - ax)
                vy = max(15.0, ay - scene_pos.y())
                w = max(vx, vy * ratio)
                max_w = self.bounds.right() - ax
                max_h = ay - self.bounds.top()
                w = min(w, max_w, max_h * ratio)
                h = w / ratio
                new_r = QRectF(ax, ay - h, w, h)
            elif k == "bl":
                ax, ay = r.right(), r.top()
                vx = max(15.0, ax - scene_pos.x())
                vy = max(15.0, scene_pos.y() - ay)
                w = max(vx, vy * ratio)
                max_w = ax - self.bounds.left()
                max_h = self.bounds.bottom() - ay
                w = min(w, max_w, max_h * ratio)
                h = w / ratio
                new_r = QRectF(ax - w, ay, w, h)
            else:
                return
        else:
            delta = scene_pos - self._drag_start_scene
            left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
            if "l" in k: left += delta.x()
            if "r" in k: right += delta.x()
            if "t" in k: top += delta.y()
            if "b" in k: bottom += delta.y()

            left = max(self.bounds.left(), min(left, right - 10))
            right = min(self.bounds.right(), max(right, left + 10))
            top = max(self.bounds.top(), min(top, bottom - 10))
            bottom = min(self.bounds.bottom(), max(bottom, top + 10))
            new_r = QRectF(left, top, right - left, bottom - top)

        self.setRect(new_r)
        self.update_handle_positions()

    def end_handle_drag(self):
        self._active_handle = None
        self._is_dragging_rect = False
        if self.on_change_callback:
            r = self.rect().normalized()
            self.on_change_callback((int(r.left()), int(r.top()), int(r.right()), int(r.bottom())))

    def mousePressEvent(self, event):
        pos = event.pos()
        self._active_handle = None

        # Check handles first
        for key, handle in self.handles.items():
            if handle.contains(handle.mapFromParent(pos)):
                self.start_handle_drag(key, event.scenePos())
                event.accept()
                return

        self._drag_start_scene = event.scenePos()
        self._rect_at_drag_start = self.rect()

        if self.contains(pos):
            self._is_dragging_rect = True

        event.accept()

    def mouseMoveEvent(self, event):
        if self._active_handle:
            self.continue_handle_drag(event.scenePos())
            event.accept()
            return
        elif self._is_dragging_rect:
            delta = event.scenePos() - self._drag_start_scene
            r = QRectF(self._rect_at_drag_start)
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
        if self._active_handle:
            self.end_handle_drag()
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
        self.aspect_ratio: Optional[float] = None

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
            self.roi_item = ROIRectItem(r, bounds, self._on_roi_modified, aspect_ratio=self.aspect_ratio)
            self.scene.addItem(self.roi_item)

    def spawn_centered_box(self, aspect_ratio: Optional[float] = None) -> Optional[Tuple[int, int, int, int]]:
        """Spawns an interactive box centered on the image with the specified aspect ratio."""
        if not self.pixmap_item:
            return None
        bounds = QRectF(self.pixmap_item.pixmap().rect())
        if bounds.width() < 20 or bounds.height() < 20:
            return None

        if aspect_ratio and aspect_ratio > 0:
            avail_w = bounds.width() * 0.75
            avail_h = bounds.height() * 0.75
            if avail_w / avail_h > aspect_ratio:
                box_h = avail_h
                box_w = box_h * aspect_ratio
            else:
                box_w = avail_w
                box_h = box_w / aspect_ratio
        else:
            box_w = bounds.width() * 0.65
            box_h = bounds.height() * 0.65

        x1 = max(0, int(bounds.center().x() - box_w / 2))
        y1 = max(0, int(bounds.center().y() - box_h / 2))
        x2 = min(int(bounds.width()), int(x1 + box_w))
        y2 = min(int(bounds.height()), int(y1 + box_h))
        box = (x1, y1, x2, y2)
        self.set_roi_box(box)
        self.roiChanged.emit(box)
        return box

    def _on_roi_modified(self, box: Tuple[int, int, int, int]):
        self.roiChanged.emit(box)

    def set_aspect_ratio(self, ratio: Optional[float]):
        """Sets the active aspect ratio and dynamically updates any existing crop box."""
        self.aspect_ratio = ratio
        if self.roi_item:
            self.roi_item.set_aspect_ratio(ratio)
            if ratio and ratio > 0 and self.pixmap_item:
                r = self.roi_item.rect().normalized()
                bounds = QRectF(self.pixmap_item.pixmap().rect())
                cx, cy = r.center().x(), r.center().y()
                curr_h = r.height()
                new_w = curr_h * ratio
                new_h = curr_h
                if new_w > bounds.width():
                    new_w = bounds.width() * 0.90
                    new_h = new_w / ratio
                if new_h > bounds.height():
                    new_h = bounds.height() * 0.90
                    new_w = new_h * ratio
                x1 = max(bounds.left(), min(cx - new_w / 2, bounds.right() - new_w))
                y1 = max(bounds.top(), min(cy - new_h / 2, bounds.bottom() - new_h))
                new_r = QRectF(x1, y1, new_w, new_h)
                self.roi_item.setRect(new_r)
                self.roi_item.update_handle_positions()
                box = (int(new_r.left()), int(new_r.top()), int(new_r.right()), int(new_r.bottom()))
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

            start_x = self._rubber_start_pt.x()
            start_y = self._rubber_start_pt.y()
            dx = curr_pt.x() - start_x
            dy = curr_pt.y() - start_y

            if self.aspect_ratio and self.aspect_ratio > 0:
                sign_x = 1 if dx >= 0 else -1
                sign_y = 1 if dy >= 0 else -1

                max_w = (bounds.right() - start_x) if sign_x > 0 else (start_x - bounds.left())
                max_h = (bounds.bottom() - start_y) if sign_y > 0 else (start_y - bounds.top())

                desired_w = max(abs(dx), abs(dy) * self.aspect_ratio)
                allowed_w = min(desired_w, max_w, max_h * self.aspect_ratio)
                allowed_h = allowed_w / self.aspect_ratio

                x1 = start_x if sign_x > 0 else start_x - allowed_w
                y1 = start_y if sign_y > 0 else start_y - allowed_h
                rect = QRectF(x1, y1, allowed_w, allowed_h)
            else:
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
        self._current_unit: str = "mm"
        self._dim_w_mm: float = 35.0
        self._dim_h_mm: float = 45.0

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

        # 1. Left Panel (Workspace & ROI Mode) - Compact fixed width, NO horizontal scroll
        left_panel = QWidget()
        left_panel.setFixedWidth(250)
        left_panel.setMinimumWidth(240)
        left_panel.setMaximumWidth(280)
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

        self.combo_presets = QComboBox()
        for preset_name in PRESET_MAP.keys():
            self.combo_presets.addItem(preset_name)
        self.combo_presets.currentTextChanged.connect(self._on_preset_changed)
        grp_preset_layout.addWidget(self.combo_presets)

        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel("Unit:"))
        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["mm", "in", "px"])
        self.combo_unit.currentTextChanged.connect(self._on_unit_changed)
        unit_row.addWidget(self.combo_unit)
        grp_preset_layout.addLayout(unit_row)

        dim_grid = QGridLayout()
        dim_grid.setContentsMargins(0, 2, 0, 0)
        dim_grid.setSpacing(5)

        lbl_w = QLabel("Width:")
        self.spin_custom_w = QDoubleSpinBox()
        self.spin_custom_w.setRange(5.0, 1000.0)
        self.spin_custom_w.setValue(35.0)
        self.spin_custom_w.setSingleStep(1.0)
        self.spin_custom_w.setDecimals(1)
        self.spin_custom_w.setSuffix(" mm")
        self.spin_custom_w.valueChanged.connect(self._on_spinbox_dimension_changed)

        lbl_h = QLabel("Height:")
        self.spin_custom_h = QDoubleSpinBox()
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

        self.btn_zoom_in = QPushButton("🔍+ In")
        self.btn_zoom_in.setToolTip("Zoom In (Mouse Wheel Up)")
        self.btn_zoom_in.clicked.connect(lambda: self.canvas.zoom(1.2))

        self.btn_zoom_out = QPushButton("🔍- Out")
        self.btn_zoom_out.setToolTip("Zoom Out (Mouse Wheel Down)")
        self.btn_zoom_out.clicked.connect(lambda: self.canvas.zoom(1 / 1.2))

        self.btn_fit = QPushButton("📐 Fit")
        self.btn_fit.setToolTip("Fit Image to Window")
        self.btn_fit.clicked.connect(lambda: self.canvas.fit_image())

        self.btn_rotate = QPushButton("🔄 Rotate")
        self.btn_rotate.setToolTip("Rotate 90° Clockwise")
        self.btn_rotate.clicked.connect(self._on_rotate_90)

        self.btn_reset_roi = QPushButton("⬜ Reset Box")
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

        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.btn_fit)
        toolbar.addWidget(self.btn_rotate)
        toolbar.addWidget(self.btn_reset_roi)
        toolbar.addWidget(self.btn_undo)
        toolbar.addWidget(self.btn_revert)
        toolbar.addWidget(self.btn_compare)
        toolbar.addStretch()
        center_layout.addLayout(toolbar)

        # Canvas
        self.canvas = InteractiveCanvas()
        self.canvas.roiChanged.connect(self._on_canvas_roi_changed)
        self.canvas.filesDropped.connect(self._load_image_paths)
        center_layout.addWidget(self.canvas)

        splitter.addWidget(center_panel)

        # 3. Right Panel (AI Segmentation & Lighting) - Compact fixed width
        right_panel = QWidget()
        right_panel.setFixedWidth(260)
        right_panel.setMinimumWidth(250)
        right_panel.setMaximumWidth(285)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)
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

        self.slider_choke = QSlider(Qt.Horizontal)
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

        self.slider_feather = QSlider(Qt.Horizontal)
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
        self.btn_send_queue.setObjectName("btn_send_queue")
        self.btn_send_queue.clicked.connect(self._on_send_to_print_queue)
        right_layout.addWidget(self.btn_send_queue)

        right_layout.addStretch()
        splitter.addWidget(right_panel)

        # Configure splitter behavior: fixed side panes, center expands
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([250, 835, 255])

    def _build_printer_tab(self, parent_widget: QWidget):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Left: Queue & Layout settings - wrapped in QScrollArea with minimum height
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setFixedWidth(380)
        left_scroll.verticalScrollBar().setSingleStep(25)

        left_panel = QWidget()
        left_panel.setMinimumHeight(600)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSizeConstraint(QLayout.SetMinimumSize)
        left_layout.setContentsMargins(4, 4, 14, 8)
        left_layout.setSpacing(6)

        grp_queue = QGroupBox("📋 A4 Print Queue")
        grp_queue_layout = QVBoxLayout(grp_queue)
        grp_queue_layout.setSpacing(5)

        self.tbl_queue = QTableWidget(0, 4)
        self.tbl_queue.setHorizontalHeaderLabels(["Preview", "Size (mm)", "Copies", "Action"])
        self.tbl_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_queue.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_queue.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_queue.setMinimumHeight(110)
        self.tbl_queue.setMaximumHeight(160)
        grp_queue_layout.addWidget(self.tbl_queue)

        self.btn_clear_queue = QPushButton("🗑️ Clear Entire Queue")
        self.btn_clear_queue.clicked.connect(self._on_clear_queue)
        grp_queue_layout.addWidget(self.btn_clear_queue)
        left_layout.addWidget(grp_queue)

        grp_layout_settings = QGroupBox("📐 A4 Page Layout Settings")
        grp_settings_layout = QVBoxLayout(grp_layout_settings)
        grp_settings_layout.setSpacing(4)

        margin_row = QHBoxLayout()
        margin_row.addWidget(QLabel("Page Margin (mm):"))
        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(0.0, 30.0)
        self.spin_margin.setValue(10.0)
        self.spin_margin.setSingleStep(1.0)
        self.spin_margin.setSuffix(" mm")
        self.spin_margin.valueChanged.connect(self._regenerate_a4_preview)
        margin_row.addWidget(self.spin_margin)
        grp_settings_layout.addLayout(margin_row)

        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel("Gap Between Photos (mm):"))
        self.spin_gap = QDoubleSpinBox()
        self.spin_gap.setRange(0.0, 20.0)
        self.spin_gap.setValue(2.0)
        self.spin_gap.setSingleStep(0.5)
        self.spin_gap.setSuffix(" mm")
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

        # Primary Output Bar - stacked directly below settings, then stretch
        grp_output = QGroupBox("🖨️ Hardware Printing && Export")
        grp_output_layout = QVBoxLayout(grp_output)
        grp_output_layout.setSpacing(5)

        self.btn_print_hw = QPushButton("🖨️ Print Directly (1:1 Hardware A4)")
        self.btn_print_hw.setObjectName("btn_print_hw")
        self.btn_print_hw.clicked.connect(self._on_print_hardware)
        grp_output_layout.addWidget(self.btn_print_hw)

        self.btn_export_png = QPushButton("💾 Save 300-DPI A4 PNG")
        self.btn_export_png.clicked.connect(self._on_export_a4_png)
        grp_output_layout.addWidget(self.btn_export_png)

        self.btn_export_pdf = QPushButton("📄 Save 300-DPI A4 PDF")
        self.btn_export_pdf.clicked.connect(self._on_export_a4_pdf)
        grp_output_layout.addWidget(self.btn_export_pdf)

        left_layout.addWidget(grp_output)
        left_layout.addSpacing(20)
        left_layout.addStretch()

        left_scroll.setWidget(left_panel)
        layout.addWidget(left_scroll)

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

        # Global Ctrl+Z undo shortcut
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self._on_undo)

    def _apply_dark_style(self):
        dark_qss = """
        QMainWindow, QWidget {
            background-color: #18181b;
            color: #f4f4f5;
            font-family: 'Segoe UI', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif;
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
            min-height: 24px;
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
            color: #a1a1aa;
            border-color: #27272a;
        }
        QPushButton#btn_send_queue {
            background-color: #0284c7;
            color: #ffffff;
            font-weight: bold;
            border: 1px solid #38bdf8;
            border-radius: 4px;
            padding: 8px 12px;
        }
        QPushButton#btn_send_queue:hover {
            background-color: #0369a1;
        }
        QPushButton#btn_send_queue:pressed {
            background-color: #075985;
        }
        QPushButton#btn_apply_crop {
            background-color: #d97706;
            color: #ffffff;
            font-weight: bold;
            border: 1px solid #f59e0b;
            border-radius: 4px;
            padding: 6px 10px;
        }
        QPushButton#btn_apply_crop:hover {
            background-color: #b45309;
        }
        QPushButton#btn_apply_crop:pressed {
            background-color: #92400e;
        }
        QPushButton#btn_apply_crop:disabled {
            background-color: #27272a;
            color: #71717a;
            border-color: #3f3f46;
        }
        QPushButton#btn_print_hw {
            background-color: #16a34a;
            color: #ffffff;
            font-weight: bold;
            border: 1px solid #22c55e;
            border-radius: 4px;
            padding: 10px 14px;
        }
        QPushButton#btn_print_hw:hover {
            background-color: #15803d;
        }
        QPushButton#btn_print_hw:pressed {
            background-color: #166534;
        }
        QPushButton#btn_pick_color {
            background-color: #2563eb;
            color: #ffffff;
            font-weight: bold;
        }
        QPushButton#btn_pick_color:disabled {
            background-color: #1f1f23;
            color: #a1a1aa;
            border-color: #27272a;
        }
        QComboBox, QSpinBox, QDoubleSpinBox {
            background-color: #27272a;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            padding: 3px 6px;
            color: #f4f4f5;
            min-height: 22px;
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
        QScrollArea {
            border: none;
            background-color: transparent;
        }
        QScrollBar:vertical {
            background-color: #27272a;
            width: 12px;
            margin: 0px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background-color: #52525b;
            min-height: 30px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #71717a;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
        QScrollBar:horizontal {
            background-color: #18181b;
            height: 10px;
            margin: 0px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal {
            background-color: #3f3f46;
            min-width: 25px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal:hover {
            background-color: #52525b;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
            background: none;
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

        queue_entry = {
            "image": proc.copy(),
            "width_mm": w_mm,
            "height_mm": h_mm,
            "copies": 4,  # default 4 copies
            "label": item["name"]
        }
        self.print_queue.append(queue_entry)
        self._refresh_queue_table()
        self.statusBar().showMessage(f"Added to A4 Queue: {item['name']} ({w_mm:.1f} x {h_mm:.1f} mm)", 4000)

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
