"""
ui/panels/lighting_panel.py - Lighting, color grading, local patch scope, and commit panel.
"""

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from ui.primitives import AppButton, LabeledSlider, SectionBox
from ui.theme import STUDIO_DARK_THEME, ThemeConfig


class LightingPanel(SectionBox):
    """Right-inspector section for lighting/color sliders, box scoping, and committing edits."""

    lightingChanged = Signal()
    editInsideBoxToggled = Signal(bool)
    resetRequested = Signal()
    commitRequested = Signal()

    def __init__(self, theme: ThemeConfig = STUDIO_DARK_THEME, parent: Optional[QWidget] = None):
        super().__init__(
            title="☀️ Lighting && Color Grading",
            section_id="lighting",
            zone_id="inspector-right",
            theme=theme,
            parent=parent,
        )
        self._internal_block = False

        self.slider_bright = LabeledSlider("Brightness", 50, 150, 100, suffix="%", parent=self)
        self.slider_contrast = LabeledSlider("Contrast", 50, 150, 100, suffix="%", parent=self)
        self.slider_sat = LabeledSlider("Saturation", 0, 200, 100, suffix="%", parent=self)
        self.slider_sharp = LabeledSlider("Sharpness", 0, 300, 100, suffix="%", parent=self)
        self.slider_warmth = LabeledSlider("Warmth", -30, 30, 0, suffix="", parent=self)

        for slider in (
            self.slider_bright,
            self.slider_contrast,
            self.slider_sat,
            self.slider_sharp,
            self.slider_warmth,
        ):
            slider.valueChanged.connect(lambda _: self._emit_lighting_changed())
            self.add_widget(slider)

        self.chk_edit_inside_box = QCheckBox("Edit inside box", self)
        self.chk_edit_inside_box.setChecked(False)
        self.chk_edit_inside_box.setToolTip(
            "When checked, applies lighting and AI background edits only inside the selection box "
            "(automatically switches from Straighten to Crop mode if active)"
        )
        self.chk_edit_inside_box.toggled.connect(self._on_edit_inside_toggled)
        self.add_widget(self.chk_edit_inside_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(theme.spacing.md)

        self.btn_reset_lighting = AppButton(
            "🔄 Reset",
            variant="default",
            ui_size="md",
            tooltip="Reset lighting and color grading sliders to defaults",
            parent=self,
        )
        self.btn_reset_lighting.clicked.connect(self.resetRequested)

        self.btn_commit_retouch = AppButton(
            "✔️ Commit",
            variant="success",
            ui_size="md",
            tooltip="Permanently commits current lighting and AI backdrop edits into base image and resets retouch controls",
            parent=self,
        )
        self.btn_commit_retouch.clicked.connect(self.commitRequested)

        btn_row.addWidget(self.btn_reset_lighting)
        btn_row.addWidget(self.btn_commit_retouch)
        self.add_layout(btn_row)

    def _emit_lighting_changed(self) -> None:
        if not self._internal_block:
            self.lightingChanged.emit()

    def _on_edit_inside_toggled(self, checked: bool) -> None:
        if not self._internal_block:
            self.editInsideBoxToggled.emit(checked)

    def load_values(
        self,
        brightness: float,
        contrast: float,
        saturation: float,
        sharpness: float,
        warmth: int,
        edit_inside_box: bool,
    ) -> None:
        """Populates lighting sliders and box scope without emitting change signals."""
        self._internal_block = True
        try:
            self.slider_bright.set_value(int(round(brightness * 100)), block_signals=True)
            self.slider_contrast.set_value(int(round(contrast * 100)), block_signals=True)
            self.slider_sat.set_value(int(round(saturation * 100)), block_signals=True)
            self.slider_sharp.set_value(int(round(sharpness * 100)), block_signals=True)
            self.slider_warmth.set_value(int(warmth), block_signals=True)
            self.chk_edit_inside_box.setChecked(edit_inside_box)
        finally:
            self._internal_block = False

    def reset_sliders(self) -> None:
        """Resets all lighting sliders back to neutral defaults silently."""
        self._internal_block = True
        try:
            for slider in (
                self.slider_bright,
                self.slider_contrast,
                self.slider_sat,
                self.slider_sharp,
                self.slider_warmth,
            ):
                slider.reset(block_signals=True)
        finally:
            self._internal_block = False

    def values(self) -> dict:
        """Returns lighting parameters matching RetouchState fields."""
        return {
            "brightness": self.slider_bright.value() / 100.0,
            "contrast": self.slider_contrast.value() / 100.0,
            "saturation": self.slider_sat.value() / 100.0,
            "sharpness": self.slider_sharp.value() / 100.0,
            "warmth": self.slider_warmth.value(),
            "edit_inside_box": self.chk_edit_inside_box.isChecked(),
        }
