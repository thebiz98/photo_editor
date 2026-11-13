"""
ui/panels/canvas_toolbar.py - Horizontal action toolbar above the interactive studio canvas.
"""

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ui.primitives import AppButton
from ui.theme import STUDIO_DARK_THEME, ThemeConfig, set_widget_props


class CanvasToolbar(QWidget):
    """Top canvas action strip for viewport zoom, history, compare, and print queueing."""

    zoomInRequested = Signal()
    zoomOutRequested = Signal()
    fitRequested = Signal()
    rotateRequested = Signal()
    resetRoiRequested = Signal()
    undoRequested = Signal()
    revertRequested = Signal()
    comparePressed = Signal()
    compareReleased = Signal()
    sendToPrintRequested = Signal()

    def __init__(self, theme: ThemeConfig = STUDIO_DARK_THEME, parent: Optional[QWidget] = None):
        super().__init__(parent)
        zone_cfg = theme.get_zone_config("toolbar")
        set_widget_props(self, repolish=False, zone="toolbar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(*zone_cfg.margins)
        layout.setSpacing(zone_cfg.spacing)

        click_actions = [
            ("btn_zoom_in", "🔍+", "Zoom In (Mouse Wheel Up)", "default", self.zoomInRequested),
            ("btn_zoom_out", "🔍-", "Zoom Out (Mouse Wheel Down)", "default", self.zoomOutRequested),
            ("btn_fit", "📐 Fit", "Fit Image to Window", "default", self.fitRequested),
            ("btn_rotate", "🔄 Rotate", "Rotate 90° Clockwise", "default", self.rotateRequested),
            ("btn_reset_roi", "⬜ Reset", "Reset / Clear Selection Box", "default", self.resetRoiRequested),
            ("btn_undo", "↩️ Undo", "Undo Last Action / Crop (Ctrl+Z)", "default", self.undoRequested),
            ("btn_revert", "⏮️ Revert", "Revert Photo to Pristine Original State", "default", self.revertRequested),
        ]

        for attr_name, label, tip, variant, sig in click_actions:
            btn = AppButton(label, variant=variant, ui_size="md", tooltip=tip, parent=self)
            btn.clicked.connect(sig)
            setattr(self, attr_name, btn)
            layout.addWidget(btn)

        self.btn_undo.setEnabled(False)

        self.btn_compare = AppButton(
            "👁️ Compare",
            variant="default",
            ui_size="md",
            tooltip="Hold to Compare Original (Unedited) Photo",
            parent=self,
        )
        self.btn_compare.pressed.connect(self.comparePressed)
        self.btn_compare.released.connect(self.compareReleased)
        layout.addWidget(self.btn_compare)

        self.btn_send_queue = AppButton(
            "➕ Print",
            variant="primary",
            ui_size="md",
            tooltip="Add Current Photo to A4 Print Queue",
            parent=self,
        )
        self.btn_send_queue.clicked.connect(self.sendToPrintRequested)
        layout.addWidget(self.btn_send_queue)
        layout.addStretch()

    def set_undo_enabled(self, enabled: bool) -> None:
        self.btn_undo.setEnabled(enabled)
