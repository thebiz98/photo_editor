"""
ui/panels/rescale_panel.py - Compute Lanczos rescaling and offline AI 2x super-resolution panel.
"""

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ui.primitives import AppButton, AppLabel, FormRow, NoWheelSpinBox, SectionBox, SectionDivider
from ui.theme import STUDIO_DARK_THEME, ThemeConfig


class RescalePanel(SectionBox):
    """Right-inspector section displaying active pixel dimensions, scaling, and AI 2x enhance."""

    scalePercentageChanged = Signal(int)
    applyScaleRequested = Signal(int)
    aiEnhanceRequested = Signal()

    def __init__(
        self,
        min_scale_pct: int,
        max_scale_pct: int,
        theme: ThemeConfig = STUDIO_DARK_THEME,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(
            title="📐 Resolution && Scaling",
            section_id="rescale",
            zone_id="inspector-right",
            theme=theme,
            parent=parent,
        )
        self._internal_block = False

        self.lbl_current_res = AppLabel("Current: None", role="body", tone="muted", parent=self)
        self.add_widget(self.lbl_current_res)

        self.spin_rescale_pct = NoWheelSpinBox(self)
        self.spin_rescale_pct.setRange(min_scale_pct, max_scale_pct)
        self.spin_rescale_pct.setValue(100)
        self.spin_rescale_pct.setSingleStep(10)
        self.spin_rescale_pct.setSuffix(" %")
        self.spin_rescale_pct.valueChanged.connect(self._on_pct_changed)
        self.add_widget(FormRow("Scale:", self.spin_rescale_pct, spacing=theme.spacing.md, parent=self))

        self.lbl_target_res = AppLabel("Result: 100% (Original)", role="caption", tone="accent", parent=self)
        self.add_widget(self.lbl_target_res)

        self.btn_apply_scale = AppButton(
            "⚡ Apply Scale",
            variant="compute",
            ui_size="lg",
            tooltip="Apply compute-based Lanczos rescaling to current image",
            parent=self,
        )
        self.btn_apply_scale.clicked.connect(lambda: self.applyScaleRequested.emit(self.spin_rescale_pct.value()))
        self.add_widget(self.btn_apply_scale)

        self.add_widget(SectionDivider(self))

        self.btn_ai_enhance = AppButton(
            "✨ AI Enhance (2x)",
            variant="ai",
            ui_size="lg",
            tooltip="Reconstruct sharp details and textures using offline AI (for blurry/small photos)",
            parent=self,
        )
        self.btn_ai_enhance.clicked.connect(self.aiEnhanceRequested)
        self.add_widget(self.btn_ai_enhance)

    def _on_pct_changed(self, pct: int) -> None:
        if not self._internal_block:
            self.scalePercentageChanged.emit(pct)

    def scale_pct(self) -> int:
        return self.spin_rescale_pct.value()

    def set_scale_pct(self, pct: int, block_signals: bool = True) -> None:
        if block_signals:
            self._internal_block = True
            self.spin_rescale_pct.blockSignals(True)
            try:
                self.spin_rescale_pct.setValue(pct)
            finally:
                self.spin_rescale_pct.blockSignals(False)
                self._internal_block = False
        else:
            self.spin_rescale_pct.setValue(pct)

    def set_current_resolution(self, width: int, height: int) -> None:
        self.lbl_current_res.setText(f"Current: {width} x {height} px")

    def update_target_preview(
        self,
        target_w: int,
        target_h: int,
        within_limits: bool,
        max_safe_dim: int,
    ) -> None:
        """Updates live target pixel readout and tone without inline setStyleSheet."""
        if within_limits:
            self.lbl_target_res.setText(f"Result: {target_w} x {target_h} px")
            self.lbl_target_res.set_tone("accent")
            self.btn_apply_scale.setEnabled(True)
        else:
            self.lbl_target_res.setText(f"Result: {target_w}x{target_h} px (⚠️ Exceeds {max_safe_dim}px Cap!)")
            self.lbl_target_res.set_tone("danger")
            self.btn_apply_scale.setEnabled(False)

    def show_no_photo(self) -> None:
        self.lbl_current_res.setText("Current: None")
        self.lbl_target_res.setText("Result: None")
        self.lbl_target_res.set_tone("accent")
        self.set_scale_pct(100, block_signals=True)
        self.btn_apply_scale.setEnabled(False)
        self.btn_ai_enhance.setEnabled(False)

    def set_ai_status(self, enabled: bool, tooltip: str) -> None:
        self.btn_ai_enhance.setEnabled(enabled)
        self.btn_ai_enhance.setToolTip(tooltip)

    def set_busy(self, busy: bool) -> None:
        self.btn_ai_enhance.setEnabled(not busy)
        self.btn_apply_scale.setEnabled(not busy)
