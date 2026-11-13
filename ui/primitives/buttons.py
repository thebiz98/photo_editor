"""
ui/primitives/buttons.py - Semantic variant buttons and exclusive segmented toggle strips.
"""

from typing import Any, Dict, Optional, Sequence, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ui.theme.stylesheet import set_widget_props


class AppButton(QPushButton):
    """PushButton styled by semantic variant and size tier rather than per-instance IDs."""

    def __init__(
        self,
        text: str = "",
        variant: str = "default",
        ui_size: str = "md",
        tooltip: str = "",
        checkable: bool = False,
        checked: bool = False,
        object_name: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        if object_name:
            self.setObjectName(object_name)
        if tooltip:
            self.setToolTip(tooltip)
        if checkable:
            self.setCheckable(True)
            self.setChecked(checked)
        set_widget_props(self, repolish=False, variant=variant, uiSize=ui_size)

    def set_variant(self, variant: str) -> None:
        """Updates the semantic button variant and refreshes QSS styling."""
        set_widget_props(self, repolish=True, variant=variant)

    def set_ui_size(self, ui_size: str) -> None:
        """Updates the semantic button size tier and refreshes QSS styling."""
        set_widget_props(self, repolish=True, uiSize=ui_size)


class SegmentedButtonGroup(QWidget):
    """Exclusive horizontal toggle button strip backed by a QButtonGroup."""

    selectionChanged = Signal(object)

    def __init__(
        self,
        items: Sequence[Tuple[Any, str, str]],
        active_key: Optional[Any] = None,
        spacing: int = 4,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: Dict[Any, AppButton] = {}
        self._key_by_id: Dict[int, Any] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)

        for idx, (key, label, tooltip) in enumerate(items):
            is_active = (key == active_key) if active_key is not None else (idx == 0)
            btn = AppButton(
                text=label,
                variant="segmented",
                ui_size="md",
                tooltip=tooltip,
                checkable=True,
                checked=is_active,
                parent=self,
            )
            self._group.addButton(btn, idx)
            self._buttons[key] = btn
            self._key_by_id[idx] = key
            layout.addWidget(btn)

        self._group.idClicked.connect(self._on_id_clicked)

    def _on_id_clicked(self, btn_id: int) -> None:
        key = self._key_by_id.get(btn_id)
        if key is not None:
            self.selectionChanged.emit(key)

    def set_active(self, key: Any) -> None:
        """Selects the button matching key without emitting selectionChanged."""
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setChecked(True)

    def active_key(self) -> Optional[Any]:
        """Returns the currently checked item's key."""
        checked_id = self._group.checkedId()
        return self._key_by_id.get(checked_id)

    def button(self, key: Any) -> Optional[AppButton]:
        """Returns the underlying AppButton for a given item key."""
        return self._buttons.get(key)
