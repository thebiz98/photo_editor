"""
ui/panels/crop_straighten_panel.py - Dual-mode Crop & 4-Point Perspective Straighten panel.
"""

from typing import Dict, Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ui.primitives import (
    AppButton,
    AppLabel,
    FormRow,
    NoWheelComboBox,
    NoWheelDoubleSpinBox,
    SectionBox,
    SegmentedButtonGroup,
)
from ui.theme import STUDIO_DARK_THEME, ThemeConfig


_UNIT_SPECS = {
    "in": {"decimals": 2, "step": 0.1, "range": (0.2, 50.0), "suffix": " in"},
    "px": {"decimals": 0, "step": 10.0, "range": (20.0, 10000.0), "suffix": " px"},
    "mm": {"decimals": 1, "step": 1.0, "range": (5.0, 1000.0), "suffix": " mm"},
}


class CropStraightenPanel(SectionBox):
    """Left-sidebar panel managing crop presets, physical/pixel dimensions, and perspective extraction."""

    modeChanged = Signal(str)
    presetChanged = Signal(str)
    unitChanged = Signal(str)
    dimensionsChanged = Signal(float, float)
    applyCropRequested = Signal()
    resetPinsRequested = Signal()
    applyExtractRequested = Signal()

    def __init__(
        self,
        preset_map: Dict[str, Optional[Tuple[float, float]]],
        px_per_mm: float,
        theme: ThemeConfig = STUDIO_DARK_THEME,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(
            title="📏 Crop && Straighten",
            section_id="crop_straighten",
            zone_id="sidebar-left",
            theme=theme,
            parent=parent,
        )
        self._preset_map = preset_map
        self._px_per_mm = px_per_mm
        self._current_unit = "mm"
        self._dim_w_mm = 35.0
        self._dim_h_mm = 45.0
        self._internal_block = False

        # Mode Selector Buttons
        self.mode_selector = SegmentedButtonGroup(
            items=[
                ("standard", "✂️ Crop", "Standard rectangular crop with physical presets and aspect locking"),
                ("perspective", "📐 Straighten", "Drag the 4 corner pins onto your ID/document corners (amber TOP edge = Width)"),
            ],
            active_key="standard",
            spacing=theme.spacing.sm,
            parent=self,
        )
        self.mode_selector.selectionChanged.connect(self._on_mode_clicked)
        self.add_widget(self.mode_selector)

        # Crop-only Presets container
        self.container_presets = QWidget(self)
        presets_layout = QVBoxLayout(self.container_presets)
        presets_layout.setContentsMargins(0, 0, 0, 0)
        presets_layout.setSpacing(theme.spacing.sm)

        self.combo_presets = NoWheelComboBox(self.container_presets)
        for preset_name in preset_map.keys():
            self.combo_presets.addItem(preset_name)
        self.combo_presets.currentTextChanged.connect(self._on_preset_selected)
        presets_layout.addWidget(self.combo_presets)
        self.add_widget(self.container_presets)

        # Shared Unit & Dimensions
        self.combo_unit = NoWheelComboBox(self)
        self.combo_unit.addItems(["mm", "in", "px"])
        self.combo_unit.currentTextChanged.connect(self._on_unit_selected)
        self.add_widget(FormRow("Unit:", self.combo_unit, spacing=theme.spacing.md, parent=self))

        dim_grid = QGridLayout()
        dim_grid.setContentsMargins(0, 2, 0, 0)
        dim_grid.setSpacing(5)

        self.spin_custom_w = NoWheelDoubleSpinBox(self)
        self.spin_custom_h = NoWheelDoubleSpinBox(self)
        self._configure_unit_spinboxes("mm")
        self.spin_custom_w.setValue(self._dim_w_mm)
        self.spin_custom_h.setValue(self._dim_h_mm)
        self.spin_custom_w.valueChanged.connect(self._on_spinbox_changed)
        self.spin_custom_h.valueChanged.connect(self._on_spinbox_changed)

        dim_grid.addWidget(AppLabel("Width:", parent=self), 0, 0)
        dim_grid.addWidget(self.spin_custom_w, 0, 1)
        dim_grid.addWidget(AppLabel("Height:", parent=self), 1, 0)
        dim_grid.addWidget(self.spin_custom_h, 1, 1)
        self.add_layout(dim_grid)

        # Mode 1 Actions: Standard Crop
        self.container_box_crop = QWidget(self)
        box_crop_layout = QVBoxLayout(self.container_box_crop)
        box_crop_layout.setContentsMargins(0, 2, 0, 0)
        box_crop_layout.setSpacing(5)

        self.btn_apply_crop = AppButton(
            "✂️ Apply Crop / Dimensions",
            variant="warning",
            ui_size="lg",
            parent=self.container_box_crop,
        )
        self.btn_apply_crop.clicked.connect(self.applyCropRequested)
        box_crop_layout.addWidget(self.btn_apply_crop)
        self.add_widget(self.container_box_crop)

        # Mode 2 Actions: Straighten / Perspective Extraction
        self.container_perspective = QWidget(self)
        persp_layout = QVBoxLayout(self.container_perspective)
        persp_layout.setContentsMargins(0, 2, 0, 0)
        persp_layout.setSpacing(theme.spacing.md)

        self.chk_apply_size = QCheckBox("Apply Size", self.container_perspective)
        self.chk_apply_size.setChecked(False)
        self.chk_apply_size.setToolTip(
            "When checked, fits the extracted selection to Width × Height above (300 DPI for mm/in). "
            "When unchecked, extracts at natural pixel resolution."
        )
        persp_layout.addWidget(self.chk_apply_size)

        persp_btn_row = QHBoxLayout()
        persp_btn_row.setSpacing(theme.spacing.md)

        self.btn_reset_pins = AppButton(
            "🔄 Reset",
            variant="default",
            ui_size="md",
            tooltip="Re-centers the 4 perspective pins on the image",
            parent=self.container_perspective,
        )
        self.btn_reset_pins.clicked.connect(self.resetPinsRequested)

        self.btn_apply_extract = AppButton(
            "🪄 Extract",
            variant="primary",
            ui_size="lg",
            tooltip="Rectifies slanted ID card/document into a flat rectangular photo",
            parent=self.container_perspective,
        )
        self.btn_apply_extract.clicked.connect(self.applyExtractRequested)

        persp_btn_row.addWidget(self.btn_reset_pins)
        persp_btn_row.addWidget(self.btn_apply_extract)
        persp_layout.addLayout(persp_btn_row)

        self.container_perspective.setVisible(False)
        self.add_widget(self.container_perspective)

    # -------------------------------------------------------------------------
    # Unit Conversion & Spinbox Formatting
    # -------------------------------------------------------------------------

    def convert_mm_to_unit(self, val_mm: float, target_unit: str) -> float:
        if target_unit == "in":
            return round(val_mm / 25.4, 2)
        if target_unit == "px":
            return float(round(val_mm * self._px_per_mm))
        return round(val_mm, 1)

    def convert_unit_to_mm(self, val: float, source_unit: str) -> float:
        if source_unit == "in":
            return val * 25.4
        if source_unit == "px":
            return val / self._px_per_mm
        return val

    def _configure_unit_spinboxes(self, unit: str) -> None:
        spec = _UNIT_SPECS.get(unit, _UNIT_SPECS["mm"])
        for spin in (self.spin_custom_w, self.spin_custom_h):
            spin.setDecimals(spec["decimals"])
            spin.setSingleStep(spec["step"])
            spin.setRange(*spec["range"])
            spin.setSuffix(spec["suffix"])

    # -------------------------------------------------------------------------
    # Internal Handlers
    # -------------------------------------------------------------------------

    def _on_mode_clicked(self, mode: str) -> None:
        if self._internal_block:
            return
        self.set_mode_containers(mode)
        self.modeChanged.emit(mode)

    def _on_preset_selected(self, text: str) -> None:
        if self._internal_block:
            return
        dims_mm = self._preset_map.get(text)
        if dims_mm is not None:
            w_mm, h_mm = dims_mm
            self._dim_w_mm = w_mm
            self._dim_h_mm = h_mm
            unit_w = self.convert_mm_to_unit(w_mm, self._current_unit)
            unit_h = self.convert_mm_to_unit(h_mm, self._current_unit)
            self._internal_block = True
            try:
                self.spin_custom_w.setValue(unit_w)
                self.spin_custom_h.setValue(unit_h)
            finally:
                self._internal_block = False
        self.presetChanged.emit(text)

    def _on_unit_selected(self, new_unit: str) -> None:
        if self._internal_block or new_unit == self._current_unit:
            return
        new_w = self.convert_mm_to_unit(self._dim_w_mm, new_unit)
        new_h = self.convert_mm_to_unit(self._dim_h_mm, new_unit)
        self._internal_block = True
        try:
            self._configure_unit_spinboxes(new_unit)
            self.spin_custom_w.setValue(new_w)
            self.spin_custom_h.setValue(new_h)
            self._current_unit = new_unit
        finally:
            self._internal_block = False
        self.unitChanged.emit(new_unit)

    def _on_spinbox_changed(self) -> None:
        if self._internal_block:
            return
        w_val = self.spin_custom_w.value()
        h_val = self.spin_custom_h.value()
        self._dim_w_mm = self.convert_unit_to_mm(w_val, self._current_unit)
        self._dim_h_mm = self.convert_unit_to_mm(h_val, self._current_unit)

        if self.combo_presets.currentText() != "Custom Size":
            self._internal_block = True
            try:
                self.combo_presets.setCurrentText("Custom Size")
            finally:
                self._internal_block = False

        self.dimensionsChanged.emit(self._dim_w_mm, self._dim_h_mm)

    # -------------------------------------------------------------------------
    # Public State API
    # -------------------------------------------------------------------------

    def set_mode_containers(self, mode: str) -> None:
        """Switches visibility between standard Crop controls and Straighten controls."""
        is_persp = (mode == "perspective")
        self.mode_selector.set_active("perspective" if is_persp else "standard")
        self.container_presets.setVisible(not is_persp)
        self.container_box_crop.setVisible(not is_persp)
        self.container_perspective.setVisible(is_persp)

    def load_crop_state(
        self,
        crop_mode: str,
        preset_name: str,
        unit: str,
        dim_w_mm: float,
        dim_h_mm: float,
        apply_size: bool,
    ) -> None:
        """Populates panel controls from a CropState without emitting user signals."""
        self._internal_block = True
        try:
            self._current_unit = unit
            self._dim_w_mm = dim_w_mm
            self._dim_h_mm = dim_h_mm
            self.combo_unit.setCurrentText(unit)
            self._configure_unit_spinboxes(unit)
            self.spin_custom_w.setValue(self.convert_mm_to_unit(dim_w_mm, unit))
            self.spin_custom_h.setValue(self.convert_mm_to_unit(dim_h_mm, unit))
            self.combo_presets.setCurrentText(preset_name)
            self.chk_apply_size.setChecked(apply_size)
            self.set_mode_containers(crop_mode)
        finally:
            self._internal_block = False

    def current_unit(self) -> str:
        return self._current_unit

    def preset_name(self) -> str:
        return self.combo_presets.currentText()

    def dimensions_mm(self) -> Tuple[float, float]:
        return (self._dim_w_mm, self._dim_h_mm)

    def apply_size_checked(self) -> bool:
        return self.chk_apply_size.isChecked()

    def target_dimensions_px_and_mm(self) -> Tuple[Optional[Tuple[int, int]], float, float]:
        """Returns ((target_w_px, target_h_px), w_mm, h_mm) using 300 DPI for mm/in or exact px."""
        w_mm, h_mm = self._dim_w_mm, self._dim_h_mm
        if w_mm <= 0 or h_mm <= 0:
            return (None, w_mm, h_mm)
        if self._current_unit == "px":
            target_w_px = max(1, int(round(self.spin_custom_w.value())))
            target_h_px = max(1, int(round(self.spin_custom_h.value())))
        else:
            target_w_px = max(1, int(round(w_mm * self._px_per_mm)))
            target_h_px = max(1, int(round(h_mm * self._px_per_mm)))
        return ((target_w_px, target_h_px), w_mm, h_mm)

    def set_apply_crop_enabled(self, enabled: bool) -> None:
        self.btn_apply_crop.setEnabled(enabled)

    def set_extract_enabled(self, enabled: bool) -> None:
        self.btn_apply_extract.setEnabled(enabled)
