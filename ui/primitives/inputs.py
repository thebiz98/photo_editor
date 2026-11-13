"""
ui/primitives/inputs.py - Wheel-safe Qt input controls for scrollable sidebars and tables.
"""

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSlider, QSpinBox


class _NoWheelMixin:
    """Ignores wheel events so parent QScrollAreas scroll without altering control values."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelSlider(_NoWheelMixin, QSlider):
    """Horizontal/vertical QSlider that ignores mouse wheel events."""


class NoWheelSpinBox(_NoWheelMixin, QSpinBox):
    """QSpinBox that ignores mouse wheel events."""


class NoWheelDoubleSpinBox(_NoWheelMixin, QDoubleSpinBox):
    """QDoubleSpinBox that ignores mouse wheel events."""


class NoWheelComboBox(_NoWheelMixin, QComboBox):
    """QComboBox that ignores mouse wheel events when closed."""
