"""
ui/primitives/labels.py - Role- and tone-driven labels and section dividers.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ui.theme.stylesheet import set_widget_props


class AppLabel(QLabel):
    """QLabel styled by semantic typography role and color tone with automatic repolish."""

    def __init__(
        self,
        text: str = "",
        role: str = "body",
        tone: str = "default",
        align: Optional[Qt.AlignmentFlag] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        if align is not None:
            self.setAlignment(align)
        set_widget_props(self, repolish=False, role=role, tone=tone)

    def set_tone(self, tone: str) -> None:
        """Updates the semantic color tone (e.g. 'muted', 'accent', 'danger') and repolishes."""
        if self.property("tone") != tone:
            set_widget_props(self, repolish=True, tone=tone)

    def set_role(self, role: str) -> None:
        """Updates the semantic typography role (e.g. 'body', 'caption', 'value') and repolishes."""
        if self.property("role") != role:
            set_widget_props(self, repolish=True, role=role)


class SectionDivider(QFrame):
    """Styled horizontal separator line for splitting sub-workflows inside a SectionBox."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        set_widget_props(self, repolish=False, role="divider")
