"""
ui/primitives/composites.py - Reusable multi-widget controls (LabeledSlider, FormRow).
"""

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ui.primitives.inputs import NoWheelSlider
from ui.primitives.labels import AppLabel


class LabeledSlider(QWidget):
    """
    Compact title + formatted readout + wheel-safe horizontal slider block.
    Keeps its numeric readout synchronized even when signals are programmatically blocked.
    """

    valueChanged = Signal(int)

    def __init__(
        self,
        label: str,
        min_val: int,
        max_val: int,
        default_val: int,
        suffix: str = "",
        formatter: Optional[Callable[[int], str]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._default_val = default_val
        self._formatter = formatter or (lambda v: f"{v}{suffix}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(1)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.lbl_title = AppLabel(label, role="body", parent=self)
        self.lbl_value = AppLabel(self._formatter(default_val), role="value", parent=self)
        header.addWidget(self.lbl_title)
        header.addStretch()
        header.addWidget(self.lbl_value)

        self.slider = NoWheelSlider(Qt.Horizontal, self)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default_val)
        self.slider.valueChanged.connect(self._on_slider_changed)

        root.addLayout(header)
        root.addWidget(self.slider)

    def _on_slider_changed(self, val: int) -> None:
        self.lbl_value.setText(self._formatter(val))
        self.valueChanged.emit(val)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, val: int, block_signals: bool = False) -> None:
        """Sets slider position and always updates the readout text."""
        if block_signals:
            self.slider.blockSignals(True)
            try:
                self.slider.setValue(val)
            finally:
                self.slider.blockSignals(False)
            self.lbl_value.setText(self._formatter(self.slider.value()))
        else:
            self.slider.setValue(val)
            self.lbl_value.setText(self._formatter(self.slider.value()))

    def reset(self, block_signals: bool = False) -> None:
        """Resets slider to its default value."""
        self.set_value(self._default_val, block_signals=block_signals)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.lbl_title.set_tone("muted" if not enabled else "default")
        self.lbl_value.set_tone("muted" if not enabled else "default")


class FormRow(QWidget):
    """Horizontal label + input widget pair with consistent spacing."""

    def __init__(
        self,
        label_text: str,
        field_widget: QWidget,
        spacing: int = 6,
        stretch_field: bool = True,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)

        self.label = AppLabel(label_text, role="body", parent=self)
        self.field = field_widget
        layout.addWidget(self.label)
        layout.addWidget(field_widget, 1 if stretch_field else 0)
