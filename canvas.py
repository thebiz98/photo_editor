"""
canvas.py - Interactive 2D Graphics Viewport and Coordinate Mapping.
Encapsulates zoom, pan, rubber-band drawing, and viewport coordinate transforms.
Delegates scene overlay items (ROIRectItem, PerspectiveQuadItem) to canvas_items.py.
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
from canvas_items import (
    BaseHandle, ROIHandle, PerspectivePin,
    ROIRectItem, PerspectiveQuadItem
)
from ui.theme import STUDIO_DARK_THEME, CanvasOverlayTokens


def pil_to_pixmap(pil_img: Image.Image) -> QPixmap:
    """Safely converts a PIL Image to a PySide6 QPixmap."""
    qimg = printer.pil_to_qimage(pil_img)
    return QPixmap.fromImage(qimg)


class InteractiveCanvas(QGraphicsView):
    """
    QGraphicsView supporting pan/zoom, interactive ROI rubber-band/handles,
    4-corner perspective quad overlays, and drag-and-drop file imports.
    """
    roiChanged = Signal(tuple)
    quadChanged = Signal(list)
    filesDropped = Signal(list)

    def __init__(
        self,
        parent=None,
        overlay_tokens: Optional[CanvasOverlayTokens] = None,
        badge_font_family: str = STUDIO_DARK_THEME.typography.font_family_raw,
    ):
        super().__init__(parent)
        self._overlay_tokens = overlay_tokens or STUDIO_DARK_THEME.canvas
        self._badge_font_family = badge_font_family
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(*self._overlay_tokens.viewport_bg)))
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.roi_item: Optional[ROIRectItem] = None
        self.quad_item: Optional[PerspectiveQuadItem] = None
        self.aspect_ratio: Optional[float] = None
        self.crop_mode: str = "standard"  # "standard" or "perspective"

        self._is_rubber_banding = False
        self._rubber_start_pt = QPointF()
        self._rubber_rect_item: Optional[QGraphicsRectItem] = None
        self._is_panning = False
        self._pan_start = QPointF()

    def set_pixmap(self, pixmap: QPixmap, keep_roi: bool = True):
        old_roi = self.get_roi_box() if (keep_roi and self.roi_item) else None
        old_quad = self.get_perspective_quad() if (keep_roi and self.quad_item) else None

        self.scene.clear()
        self.roi_item = None
        self.quad_item = None
        self._rubber_rect_item = None

        if pixmap.isNull():
            return

        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        if self.crop_mode == "perspective":
            if old_quad:
                self.set_perspective_quad(old_quad)
            else:
                self.spawn_centered_quad()
        else:
            if old_roi:
                self.set_roi_box(old_roi)

    def set_crop_mode(self, mode: str):
        """Switches active overlay between 'standard' (box) and 'perspective' (4-corner quad)."""
        if mode not in ("standard", "perspective"):
            mode = "standard"
        self.crop_mode = mode

        if mode == "perspective":
            if self.roi_item:
                self.roi_item.setVisible(False)
            if not self.quad_item and self.pixmap_item:
                self.spawn_centered_quad()
            elif self.quad_item:
                self.quad_item.setVisible(True)
        else:
            if self.quad_item:
                self.quad_item.setVisible(False)
            if self.roi_item:
                self.roi_item.setVisible(True)

    # -------------------------------------------------------------------------
    # Standard Rectangular ROI Box
    # -------------------------------------------------------------------------

    def get_roi_box(self) -> Optional[Tuple[int, int, int, int]]:
        if self.roi_item and self.roi_item.isVisible():
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
            self.roi_item = ROIRectItem(
                r,
                bounds,
                self._on_roi_modified,
                aspect_ratio=self.aspect_ratio,
                tokens=self._overlay_tokens,
            )
            self.roi_item.setVisible(self.crop_mode == "standard")
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

    # -------------------------------------------------------------------------
    # 4-Corner Perspective Quadrilateral
    # -------------------------------------------------------------------------

    def get_perspective_quad(self) -> Optional[List[Tuple[float, float]]]:
        """Returns [TL, TR, BR, BL] coordinates if perspective quad is active, else None."""
        if self.quad_item and self.quad_item.isVisible():
            return self.quad_item.get_quad_points()
        return None

    def set_perspective_quad(self, points: Optional[List[Tuple[float, float]]]):
        if self.quad_item:
            self.scene.removeItem(self.quad_item)
            self.quad_item = None

        if not points or not self.pixmap_item or len(points) != 4:
            return

        bounds = QRectF(self.pixmap_item.pixmap().rect())
        q_points = [QPointF(x, y) for (x, y) in points]
        self.quad_item = PerspectiveQuadItem(
            q_points,
            bounds,
            self._on_quad_modified,
            tokens=self._overlay_tokens,
            badge_font_family=self._badge_font_family,
        )
        self.quad_item.setVisible(self.crop_mode == "perspective")
        self.scene.addItem(self.quad_item)

    def spawn_centered_quad(self) -> Optional[List[Tuple[float, float]]]:
        """Spawns a perspective quad placed symmetrically around the center of the image."""
        if not self.pixmap_item:
            return None
        bounds = QRectF(self.pixmap_item.pixmap().rect())
        w, h = bounds.width(), bounds.height()
        cx, cy = bounds.center().x(), bounds.center().y()

        qw = w * 0.70
        qh = h * 0.70
        x1 = max(bounds.left(), cx - qw / 2)
        x2 = min(bounds.right(), cx + qw / 2)
        y1 = max(bounds.top(), cy - qh / 2)
        y2 = min(bounds.bottom(), cy + qh / 2)

        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        self.set_perspective_quad(pts)
        self.quadChanged.emit(pts)
        return pts

    def reset_perspective_quad(self):
        """Resets the perspective quad to standard centered coordinates."""
        self.spawn_centered_quad()

    def _on_quad_modified(self, points: List[Tuple[float, float]]):
        self.quadChanged.emit(points)

    # -------------------------------------------------------------------------
    # Viewport Zoom & Navigation
    # -------------------------------------------------------------------------

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

        # In perspective mode, check if click is on perspective pins or quad
        if self.crop_mode == "perspective":
            item = self.itemAt(event.pos())
            if isinstance(item, (PerspectivePin, PerspectiveQuadItem)):
                super().mousePressEvent(event)
                return
            # Do not start rubber-band rectangle in perspective mode
            super().mousePressEvent(event)
            return

        # In standard mode: if click is on existing ROI handles or item, let item handle it
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
                self._rubber_rect_item.setPen(
                    QPen(QColor(*self._overlay_tokens.roi_stroke), self._overlay_tokens.roi_stroke_width, Qt.DashLine)
                )
                self._rubber_rect_item.setBrush(QBrush(QColor(*self._overlay_tokens.roi_fill)))
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
        if self.crop_mode == "perspective" and self.quad_item and self.pixmap_item:
            key = event.key()
            if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                step = 10.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0
                dx, dy = 0.0, 0.0
                if key == Qt.Key_Left: dx = -step
                elif key == Qt.Key_Right: dx = step
                elif key == Qt.Key_Up: dy = -step
                elif key == Qt.Key_Down: dy = step
                self.quad_item.nudge(dx, dy)
                event.accept()
                return

        if self.crop_mode == "standard" and self.roi_item and self.pixmap_item:
            key = event.key()
            if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
                step = 10.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0
                dx, dy = 0.0, 0.0
                if key == Qt.Key_Left: dx = -step
                elif key == Qt.Key_Right: dx = step
                elif key == Qt.Key_Up: dy = -step
                elif key == Qt.Key_Down: dy = step
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
