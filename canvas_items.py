"""
canvas_items.py - Reusable Interactive Scene Overlay Items and Handles.
Encapsulates BaseHandle, ROIRectItem (standard 8-handle crop box),
and PerspectiveQuadItem (4-corner quadrilateral for deskewing / extraction).
"""

from typing import Dict, List, Optional, Tuple, Callable
import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPen, QBrush, QColor, QPainter, QPolygonF, QCursor
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsRectItem, QGraphicsPolygonItem
)


class BaseHandle(QGraphicsItem):
    """
    Abstract reusable interactive handle that forwards drag gestures to a parent container
    and provides visual hover/active feedback.
    """
    def __init__(self, position_key: str, parent: QGraphicsItem, size: float = 12.0):
        super().__init__(parent)
        self.position_key = position_key
        self.handle_size = size
        self.is_hovered = False
        self.setZValue(25)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        half = self.handle_size / 2.0
        # Slightly enlarged bounding rect to make grabbing easier
        return QRectF(-half - 2.0, -half - 2.0, self.handle_size + 4.0, self.handle_size + 4.0)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            parent = self.parentItem()
            if hasattr(parent, "start_handle_drag"):
                parent.start_handle_drag(self.position_key, event.scenePos())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            parent = self.parentItem()
            if hasattr(parent, "continue_handle_drag"):
                parent.continue_handle_drag(event.scenePos())
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            parent = self.parentItem()
            if hasattr(parent, "end_handle_drag"):
                parent.end_handle_drag()
                event.accept()
                return
        super().mouseReleaseEvent(event)


class ROIHandle(BaseHandle):
    """Square handle for resizing the standard rectangular crop box."""
    def __init__(self, position_key: str, parent: 'ROIRectItem'):
        super().__init__(position_key, parent, size=12.0)
        self._update_cursor()

    def _update_cursor(self):
        cursors = {
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            "tm": Qt.SizeVerCursor,   "bm": Qt.SizeVerCursor,
            "ml": Qt.SizeHorCursor,   "mr": Qt.SizeHorCursor,
        }
        self.setCursor(cursors.get(self.position_key, Qt.ArrowCursor))

    def paint(self, painter: QPainter, option, widget=None):
        half = self.handle_size / 2.0
        rect = QRectF(-half, -half, self.handle_size, self.handle_size)
        color = QColor(0, 200, 255) if self.is_hovered else QColor(0, 160, 255)
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.setBrush(QBrush(color))
        painter.drawRect(rect)


class PerspectivePin(BaseHandle):
    """Circular pin handle with bullseye center for precise 4-corner placement."""
    def __init__(self, position_key: str, parent: 'PerspectiveQuadItem'):
        super().__init__(position_key, parent, size=18.0)
        self.setCursor(Qt.CrossCursor)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        half = self.handle_size / 2.0
        rect = QRectF(-half, -half, self.handle_size, self.handle_size)

        # Outer ring
        outer_pen = QPen(QColor(255, 255, 255), 2.0)
        fill_color = QColor(255, 180, 0) if self.is_hovered else QColor(0, 220, 255)
        painter.setPen(outer_pen)
        painter.setBrush(QBrush(fill_color))
        painter.drawEllipse(rect)

        # Inner pinpoint dot
        inner_rect = QRectF(-2.5, -2.5, 5.0, 5.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(inner_rect)


class ROIRectItem(QGraphicsRectItem):
    """Interactive ROI Box with move and aspect-ratio locked resize handles."""

    def __init__(self, rect: QRectF, bounds: QRectF, on_change_callback: Optional[Callable] = None, aspect_ratio: Optional[float] = None):
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


class PerspectiveQuadItem(QGraphicsPolygonItem):
    """
    Interactive 4-Corner Quadrilateral with draggable pins for de-skewing & perspective extraction.
    Corners are ordered: TL (0), TR (1), BR (2), BL (3).
    """

    def __init__(
        self,
        quad_points: List[QPointF],
        bounds: QRectF,
        on_change_callback: Optional[Callable] = None
    ):
        super().__init__()
        self.bounds = bounds
        self.on_change_callback = on_change_callback
        self.setZValue(12)

        # High-visibility cyan dashed line with semi-transparent fill
        pen = QPen(QColor(0, 220, 255), 2, Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(0, 180, 255, 35)))

        self.setFlags(
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemIsFocusable
        )
        self.setCursor(Qt.SizeAllCursor)

        # 4 Corner Pins
        self.handles: Dict[str, PerspectivePin] = {
            "tl": PerspectivePin("tl", self),
            "tr": PerspectivePin("tr", self),
            "br": PerspectivePin("br", self),
            "bl": PerspectivePin("bl", self),
        }

        self._points: Dict[str, QPointF] = {
            "tl": quad_points[0],
            "tr": quad_points[1],
            "br": quad_points[2],
            "bl": quad_points[3],
        }

        self._active_handle: Optional[str] = None
        self._is_dragging_quad = False
        self._drag_start_scene = QPointF()
        self._points_at_drag_start: Dict[str, QPointF] = {}

        self._refresh_polygon()

    def _refresh_polygon(self):
        poly = QPolygonF([
            self._points["tl"],
            self._points["tr"],
            self._points["br"],
            self._points["bl"],
        ])
        self.setPolygon(poly)
        for k, h in self.handles.items():
            h.setPos(self._points[k])

    def get_quad_points(self) -> List[Tuple[float, float]]:
        """Returns quad coordinates as a list of 4 (x, y) tuples: [TL, TR, BR, BL]."""
        return [
            (self._points["tl"].x(), self._points["tl"].y()),
            (self._points["tr"].x(), self._points["tr"].y()),
            (self._points["br"].x(), self._points["br"].y()),
            (self._points["bl"].x(), self._points["bl"].y()),
        ]

    def set_quad_points(self, points: List[Tuple[float, float]]):
        if len(points) != 4:
            return
        keys = ["tl", "tr", "br", "bl"]
        for k, pt in zip(keys, points):
            clamped_x = max(self.bounds.left(), min(pt[0], self.bounds.right()))
            clamped_y = max(self.bounds.top(), min(pt[1], self.bounds.bottom()))
            self._points[k] = QPointF(clamped_x, clamped_y)
        self._refresh_polygon()
        if self.on_change_callback:
            self.on_change_callback(self.get_quad_points())

    def start_handle_drag(self, handle_key: str, scene_pos: QPointF):
        self._active_handle = handle_key
        self._is_dragging_quad = False

    def continue_handle_drag(self, scene_pos: QPointF):
        if not self._active_handle:
            return
        # Clamp point to image bounds
        clamped_x = max(self.bounds.left(), min(scene_pos.x(), self.bounds.right()))
        clamped_y = max(self.bounds.top(), min(scene_pos.y(), self.bounds.bottom()))
        self._points[self._active_handle] = QPointF(clamped_x, clamped_y)
        self._refresh_polygon()

    def end_handle_drag(self):
        self._active_handle = None
        if self.on_change_callback:
            self.on_change_callback(self.get_quad_points())

    def mousePressEvent(self, event):
        pos = event.pos()
        self._active_handle = None

        # Check pins first
        for key, handle in self.handles.items():
            if handle.contains(handle.mapFromParent(pos)):
                self.start_handle_drag(key, event.scenePos())
                event.accept()
                return

        # Click inside polygon to drag entire quad
        if self.contains(pos):
            self._is_dragging_quad = True
            self._drag_start_scene = event.scenePos()
            self._points_at_drag_start = {k: QPointF(pt) for k, pt in self._points.items()}
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._active_handle:
            self.continue_handle_drag(event.scenePos())
            event.accept()
            return
        elif self._is_dragging_quad:
            delta = event.scenePos() - self._drag_start_scene
            dx = delta.x()
            dy = delta.y()

            # Check bounds for all 4 corners simultaneously
            min_dx = min(self.bounds.left() - self._points_at_drag_start[k].x() for k in self._points_at_drag_start)
            max_dx = max(self.bounds.right() - self._points_at_drag_start[k].x() for k in self._points_at_drag_start)
            min_dy = min(self.bounds.top() - self._points_at_drag_start[k].y() for k in self._points_at_drag_start)
            max_dy = max(self.bounds.bottom() - self._points_at_drag_start[k].y() for k in self._points_at_drag_start)

            dx = max(min_dx, min(dx, max_dx))
            dy = max(min_dy, min(dy, max_dy))

            for k in self._points:
                self._points[k] = QPointF(
                    self._points_at_drag_start[k].x() + dx,
                    self._points_at_drag_start[k].y() + dy
                )
            self._refresh_polygon()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._active_handle:
            self.end_handle_drag()
        self._is_dragging_quad = False
        if self.on_change_callback:
            self.on_change_callback(self.get_quad_points())
        event.accept()

    def nudge(self, dx: float, dy: float) -> bool:
        """Nudges the whole quad by (dx, dy) within image bounds."""
        min_dx = min(self.bounds.left() - self._points[k].x() for k in self._points)
        max_dx = max(self.bounds.right() - self._points[k].x() for k in self._points)
        min_dy = min(self.bounds.top() - self._points[k].y() for k in self._points)
        max_dy = max(self.bounds.bottom() - self._points[k].y() for k in self._points)

        actual_dx = max(min_dx, min(dx, max_dx))
        actual_dy = max(min_dy, min(dy, max_dy))

        if abs(actual_dx) < 1e-4 and abs(actual_dy) < 1e-4:
            return False

        for k in self._points:
            self._points[k] = QPointF(
                self._points[k].x() + actual_dx,
                self._points[k].y() + actual_dy
            )
        self._refresh_polygon()
        if self.on_change_callback:
            self.on_change_callback(self.get_quad_points())
        return True
