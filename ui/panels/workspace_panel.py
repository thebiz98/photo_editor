"""
ui/panels/workspace_panel.py - Photo workspace list and ingest/removal actions panel.
"""

from typing import Optional

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QWidget

from ui.primitives import AppButton, SectionBox
from ui.theme import STUDIO_DARK_THEME, ThemeConfig


class WorkspacePanel(SectionBox):
    """Left-sidebar panel managing loaded photos in the current studio session."""

    openFilesRequested = Signal()
    pasteRequested = Signal()
    photoSelected = Signal(int)
    removeRequested = Signal()

    def __init__(self, theme: ThemeConfig = STUDIO_DARK_THEME, parent: Optional[QWidget] = None):
        super().__init__(
            title="📁 Photo Workspace",
            section_id="workspace",
            zone_id="sidebar-left",
            theme=theme,
            parent=parent,
        )
        layout_tokens = theme.layout

        btn_row = QHBoxLayout()
        btn_row.setSpacing(theme.spacing.sm)

        self.btn_add_photos = AppButton(
            "📂 Add",
            variant="default",
            ui_size="md",
            tooltip="Open photo(s) from disk",
            parent=self,
        )
        self.btn_add_photos.clicked.connect(self.openFilesRequested)

        self.btn_paste = AppButton(
            "📋 Paste",
            variant="default",
            ui_size="md",
            tooltip="Paste image from clipboard (Ctrl+V)",
            parent=self,
        )
        self.btn_paste.clicked.connect(self.pasteRequested)

        btn_row.addWidget(self.btn_add_photos)
        btn_row.addWidget(self.btn_paste)
        self.add_layout(btn_row)

        self.list_photos = QListWidget(self)
        icon_px = layout_tokens.workspace_icon_px
        self.list_photos.setIconSize(QSize(icon_px, icon_px))
        min_h, max_h = layout_tokens.workspace_list_h
        self.list_photos.setMinimumHeight(min_h)
        self.list_photos.setMaximumHeight(max_h)
        self.list_photos.currentRowChanged.connect(self.photoSelected)
        self.add_widget(self.list_photos)

        self.btn_remove_photo = AppButton(
            "🗑️ Remove Selected",
            variant="default",
            ui_size="md",
            parent=self,
        )
        self.btn_remove_photo.clicked.connect(self.removeRequested)
        self.add_widget(self.btn_remove_photo)

    def add_photo_item(self, thumb_pixmap: QPixmap, name: str) -> None:
        """Appends a photo entry with thumbnail icon to the workspace list."""
        self.list_photos.addItem(QListWidgetItem(QIcon(thumb_pixmap), name))

    def update_thumbnail(self, row: int, thumb_pixmap: QPixmap) -> None:
        """Updates the icon for an existing workspace list item."""
        if 0 <= row < self.list_photos.count():
            item = self.list_photos.item(row)
            if item is not None:
                item.setIcon(QIcon(thumb_pixmap))

    def remove_row(self, row: int) -> None:
        """Removes a row while suppressing intermediate currentRowChanged signals."""
        if not (0 <= row < self.list_photos.count()):
            return
        self.list_photos.blockSignals(True)
        try:
            self.list_photos.takeItem(row)
            remaining = self.list_photos.count()
            if remaining > 0:
                self.list_photos.setCurrentRow(min(row, remaining - 1))
        finally:
            self.list_photos.blockSignals(False)

    def current_row(self) -> int:
        return self.list_photos.currentRow()

    def set_current_row(self, row: int) -> None:
        self.list_photos.setCurrentRow(row)

    def count(self) -> int:
        return self.list_photos.count()
