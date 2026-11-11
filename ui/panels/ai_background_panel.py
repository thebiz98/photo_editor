"""
ui/panels/ai_background_panel.py - AI segmentation, backdrop preset, and matte edge panel.
"""

from typing import Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QWidget

from ui.primitives import AppButton, FormRow, LabeledSlider, NoWheelComboBox, SectionBox
from ui.theme import STUDIO_DARK_THEME, ThemeConfig


class AiBackgroundPanel(SectionBox):
    """Right-inspector section controlling offline AI background removal and edge refinement."""

    settingsChanged = Signal()
    pickCustomColorRequested = Signal()

    def __init__(self, theme: ThemeConfig = STUDIO_DARK_THEME, parent: Optional[QWidget] = None):
        super().__init__(
            title="🤖 AI Background Removal",
            section_id="ai_background",
            zone_id="inspector-right",
            theme=theme,
            parent=parent,
        )
        self._custom_bg_color: Tuple[int, int, int] = (255, 255, 255)
        self._internal_block = False

        self.chk_remove_bg = QCheckBox("Enable AI Background Removal", self)
        self.chk_remove_bg.setChecked(False)
        self.chk_remove_bg.toggled.connect(self._on_toggle_or_backdrop)
        self.add_widget(self.chk_remove_bg)

        self.combo_ai_model = NoWheelComboBox(self)
        self.combo_ai_model.addItems(["RMBG-1.4 (High Precision)", "MODNet (Fast Portrait)"])
        self.combo_ai_model.currentTextChanged.connect(lambda _: self._emit_if_unblocked())
        self.add_widget(FormRow("Model:", self.combo_ai_model, spacing=theme.spacing.md, parent=self))

        self.combo_backdrop = NoWheelComboBox(self)
        self.combo_backdrop.addItems([
            "Studio White",
            "Passport Grey",
            "Standard Blue",
            "Corporate Navy",
            "Soft Blur",
            "Custom Solid Color...",
        ])
        self.combo_backdrop.currentTextChanged.connect(self._on_toggle_or_backdrop)
        self.add_widget(FormRow("Backdrop:", self.combo_backdrop, spacing=theme.spacing.md, parent=self))

        self.btn_pick_color = AppButton(
            "🎨 Pick Custom Color",
            variant="secondary",
            ui_size="md",
            parent=self,
        )
        self.btn_pick_color.setEnabled(False)
        self.btn_pick_color.clicked.connect(self.pickCustomColorRequested)
        self.add_widget(self.btn_pick_color)

        self.slider_choke = LabeledSlider(
            label="Edge Choke (Halo Cut):",
            min_val=0,
            max_val=5,
            default_val=0,
            suffix=" px",
            parent=self,
        )
        self.slider_choke.valueChanged.connect(lambda _: self._emit_if_unblocked())
        self.add_widget(self.slider_choke)

        self.slider_feather = LabeledSlider(
            label="Edge Feather (Softness):",
            min_val=0,
            max_val=50,
            default_val=0,
            formatter=lambda v: f"{v / 10.0:.1f} px",
            parent=self,
        )
        self.slider_feather.valueChanged.connect(lambda _: self._emit_if_unblocked())
        self.add_widget(self.slider_feather)

        self.sync_controls_enabled()

    def _emit_if_unblocked(self) -> None:
        if not self._internal_block:
            self.settingsChanged.emit()

    def _on_toggle_or_backdrop(self, *_args) -> None:
        self.sync_controls_enabled()
        self._emit_if_unblocked()

    def sync_controls_enabled(self) -> None:
        """Enables or disables AI sub-controls based on AI toggle and backdrop selection."""
        checked = self.chk_remove_bg.isChecked()
        self.combo_ai_model.setEnabled(checked)
        self.combo_backdrop.setEnabled(checked)
        self.slider_choke.setEnabled(checked)
        self.slider_feather.setEnabled(checked)
        self.btn_pick_color.setEnabled(checked and "Custom" in self.combo_backdrop.currentText())

    def custom_color(self) -> Tuple[int, int, int]:
        return self._custom_bg_color

    def set_custom_color(self, rgb: Tuple[int, int, int]) -> None:
        self._custom_bg_color = rgb

    def load_values(
        self,
        remove_bg: bool,
        ai_model: str,
        backdrop: str,
        custom_color: Tuple[int, int, int],
        choke_px: int,
        feather_px: float,
    ) -> None:
        """Populates AI controls cleanly without emitting settingsChanged."""
        self._internal_block = True
        try:
            self._custom_bg_color = custom_color
            self.chk_remove_bg.setChecked(remove_bg)
            self.combo_ai_model.setCurrentIndex(1 if "MODNet" in ai_model else 0)
            self.combo_backdrop.setCurrentText(backdrop)
            self.slider_choke.set_value(choke_px, block_signals=True)
            self.slider_feather.set_value(int(round(feather_px * 10)), block_signals=True)
            self.sync_controls_enabled()
        finally:
            self._internal_block = False

    def values(self) -> dict:
        """Returns raw AI settings matching RetouchState fields."""
        return {
            "remove_bg": self.chk_remove_bg.isChecked(),
            "ai_model": "RMBG-1.4" if "RMBG" in self.combo_ai_model.currentText() else "MODNet",
            "backdrop": self.combo_backdrop.currentText(),
            "custom_color": self._custom_bg_color,
            "choke_px": self.slider_choke.value(),
            "feather_px": self.slider_feather.value() / 10.0,
        }
