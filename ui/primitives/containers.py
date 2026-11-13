"""
ui/primitives/containers.py - Theme-aware section container primitives.
"""

from typing import Optional

from PySide6.QtWidgets import QGroupBox, QLayout, QVBoxLayout, QWidget

from ui.theme.stylesheet import set_widget_props
from ui.theme.themes import STUDIO_DARK_THEME
from ui.theme.tokens import ThemeConfig


class SectionBox(QGroupBox):
    """
    Titled group container bound to a section_id (and optional zone_id) in ThemeConfig.
    Applies configured layout margins/spacing and exposes QSS [section]/[zone] hooks.
    """

    def __init__(
        self,
        title: str,
        section_id: str,
        zone_id: str = "",
        theme: ThemeConfig = STUDIO_DARK_THEME,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(title, parent)
        self.section_id = section_id
        self.zone_id = zone_id

        props = {"section": section_id}
        if zone_id:
            props["zone"] = zone_id
        set_widget_props(self, repolish=False, **props)

        sec_style = theme.get_section_style(section_id)
        self.body_layout = QVBoxLayout(self)
        self.body_layout.setContentsMargins(*sec_style.margins)
        self.body_layout.setSpacing(sec_style.spacing)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.body_layout.addWidget(widget, stretch)

    def add_layout(self, layout: QLayout, stretch: int = 0) -> None:
        self.body_layout.addLayout(layout, stretch)
