"""
styles.py - Centralized Dark Theme Styling (QSS) for Windows 11 Native Photo Studio.
Provides high-contrast controls, custom bullseye radio indicators, and accessible dark scrollbars.
"""

DARK_THEME_QSS = """
QMainWindow, QWidget {
    background-color: #18181b;
    color: #f4f4f5;
    font-family: 'Segoe UI', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #3f3f46;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 12px;
    font-weight: bold;
    color: #e4e4e7;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: #38bdf8;
}
/* Radio Buttons & High-Contrast Selected Indicator */
QRadioButton {
    color: #f4f4f5;
    spacing: 8px;
    font-size: 13px;
    background-color: transparent;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 9px;
    border: 2px solid #52525b;
    background-color: #27272a;
}
QRadioButton::indicator:hover {
    border-color: #38bdf8;
    background-color: #3f3f46;
}
QRadioButton::indicator:checked {
    border: 2px solid #38bdf8;
    background: qradialgradient(
        cx: 0.5, cy: 0.5, radius: 0.45, fx: 0.5, fy: 0.5,
        stop: 0 #38bdf8,
        stop: 0.55 #38bdf8,
        stop: 0.65 #27272a,
        stop: 1.0 #27272a
    );
}
QRadioButton::indicator:disabled {
    border-color: #3f3f46;
    background-color: #1f1f23;
}
/* Checkboxes & Checkmark Indicator */
QCheckBox {
    color: #f4f4f5;
    spacing: 8px;
    font-size: 13px;
    background-color: transparent;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 2px solid #52525b;
    background-color: #27272a;
}
QCheckBox::indicator:hover {
    border-color: #38bdf8;
    background-color: #3f3f46;
}
QCheckBox::indicator:checked {
    border: 2px solid #38bdf8;
    background-color: #0284c7;
}
QCheckBox::indicator:disabled {
    border-color: #3f3f46;
    background-color: #1f1f23;
}
QPushButton {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 4px;
    padding: 5px 10px;
    color: #f4f4f5;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #3f3f46;
    border-color: #52525b;
}
QPushButton:pressed {
    background-color: #52525b;
}
QPushButton:disabled {
    background-color: #1f1f23;
    color: #a1a1aa;
    border-color: #27272a;
}
QPushButton#btn_send_queue {
    background-color: #0284c7;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #38bdf8;
    border-radius: 4px;
    padding: 8px 12px;
}
QPushButton#btn_send_queue:hover {
    background-color: #0369a1;
}
QPushButton#btn_send_queue:pressed {
    background-color: #075985;
}
QPushButton#btn_apply_crop {
    background-color: #d97706;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #f59e0b;
    border-radius: 4px;
    padding: 6px 10px;
}
QPushButton#btn_apply_crop:hover {
    background-color: #b45309;
}
QPushButton#btn_apply_crop:pressed {
    background-color: #92400e;
}
QPushButton#btn_apply_crop:disabled {
    background-color: #27272a;
    color: #71717a;
    border-color: #3f3f46;
}
QPushButton#btn_apply_scale {
    background-color: #0d9488;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #14b8a6;
    border-radius: 4px;
    padding: 6px 10px;
}
QPushButton#btn_apply_scale:hover {
    background-color: #0f766e;
}
QPushButton#btn_apply_scale:pressed {
    background-color: #115e59;
}
QPushButton#btn_apply_scale:disabled {
    background-color: #27272a;
    color: #71717a;
    border-color: #3f3f46;
}
QPushButton#btn_ai_enhance {
    background-color: #7c3aed;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #8b5cf6;
    border-radius: 4px;
    padding: 6px 10px;
}
QPushButton#btn_ai_enhance:hover {
    background-color: #6d28d9;
}
QPushButton#btn_ai_enhance:pressed {
    background-color: #5b21b6;
}
QPushButton#btn_ai_enhance:disabled {
    background-color: #27272a;
    color: #71717a;
    border-color: #3f3f46;
}
QPushButton#btn_print_hw {
    background-color: #16a34a;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #22c55e;
    border-radius: 4px;
    padding: 10px 14px;
}
QPushButton#btn_print_hw:hover {
    background-color: #15803d;
}
QPushButton#btn_print_hw:pressed {
    background-color: #166534;
}
QPushButton#btn_pick_color {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#btn_pick_color:disabled {
    background-color: #1f1f23;
    color: #a1a1aa;
    border-color: #27272a;
}
QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 4px;
    padding: 3px 6px;
    color: #f4f4f5;
    min-height: 22px;
}
QComboBox::drop-down {
    border: none;
}
QListWidget, QTableWidget {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 4px;
    color: #f4f4f5;
}
QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #0284c7;
    color: white;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #3f3f46;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #0284c7;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #38bdf8;
    width: 14px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: 7px;
}
QTabWidget::pane {
    border: 1px solid #27272a;
}
QTabBar::tab {
    background: #27272a;
    border: 1px solid #3f3f46;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    color: #a1a1aa;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #3f3f46;
    color: #38bdf8;
    border-bottom-color: #3f3f46;
}
QHeaderView::section {
    background-color: #27272a;
    color: #e4e4e7;
    border: 1px solid #3f3f46;
    padding: 4px;
}
QStatusBar {
    background-color: #121214;
    color: #a1a1aa;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    background-color: #27272a;
    width: 12px;
    margin: 0px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background-color: #52525b;
    min-height: 30px;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover {
    background-color: #71717a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar:horizontal {
    background-color: #18181b;
    height: 10px;
    margin: 0px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background-color: #3f3f46;
    min-width: 25px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #52525b;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
"""
