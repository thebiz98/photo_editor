"""
canvas.py - Interactive 2D Graphics Viewport, Aspect-Locked ROI Box, and Resize Handles.
Encapsulates zoom, pan, rubber-band drawing, and spatial coordinate transforms.
"""

from typing import Optional, Tuple, List, Dict, Any
from pathlib import Path
from PIL import Image

from PySide6.QtCore import (
    Qt, QRectF, QPointF, Signal, Slot, QSize
)
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QBrush, QColor, QCursor
)
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsItem, QFrame
)
import printer

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

    def nudge(self, dx: float, dy: float) -> bool:
        """
        Nudges the ROI box by (dx, dy) scene pixels, strictly clamping inside self.bounds.
        Returns True if the box moved, False otherwise.
        """
        r = self.rect()
        max_left = max(self.bounds.left(), self.bounds.right() - r.width())
        new_left = max(self.bounds.left(), min(r.left() + dx, max_left))

        max_top = max(self.bounds.top(), self.bounds.bottom() - r.height())
        new_top = max(self.bounds.top(), min(r.top() + dy, max_top))

        actual_dx = new_left - r.left()
        actual_dy = new_top - r.top()

        if abs(actual_dx) < 1e-4 and abs(actual_dy) < 1e-4:
            return False

        new_r = r.translated(actual_dx, actual_dy)
        self.setRect(new_r)
        self.update_handle_positions()
        if self.on_change_callback:
            norm_r = new_r.normalized()
            self.on_change_callback((
                int(norm_r.left()),
                int(norm_r.top()),
                int(norm_r.right()),
                int(norm_r.bottom())
            ))
        return True

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 10.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0
            dx, dy = 0.0, 0.0
            if key == Qt.Key_Left:
                dx = -step
            elif key == Qt.Key_Right:
                dx = step
            elif key == Qt.Key_Up:
                dy = -step
            elif key == Qt.Key_Down:
                dy = step
            self.nudge(dx, dy)
            event.accept()
            return
        super().keyPressEvent(event)


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
        self.setFocusPolicy(Qt.StrongFocus)

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
        self.setFocus()
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

    def keyPressEvent(self, event):
        if self.roi_item and self.pixmap_item:
            key = event.key()
            if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                step = 10.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0
                dx, dy = 0.0, 0.0
                if key == Qt.Key_Left:
                    dx = -step
                elif key == Qt.Key_Right:
                    dx = step
                elif key == Qt.Key_Up:
                    dy = -step
                elif key == Qt.Key_Down:
                    dy = step
                self.roi_item.nudge(dx, dy)
                event.accept()
                return
        super().keyPressEvent(event)

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


