"""
ui/theme/stylesheet.py - Dynamic QSS compiler and Qt property polish helpers.
Generates cohesive QSS from a ThemeConfig without duplicating variant blocks.
"""

from typing import Any, List

from ui.theme.tokens import AccentSwatch, ButtonSizeSpec, ColorTokens, ThemeConfig


def repolish_widget(widget: Any) -> None:
    """Forces Qt to re-evaluate QSS rules after a dynamic property changes."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def set_widget_props(widget: Any, repolish: bool = True, **props: Any) -> None:
    """Assigns one or more dynamic Qt properties and optionally repolishes the widget."""
    for key, val in props.items():
        widget.setProperty(key, val)
    if repolish:
        repolish_widget(widget)


def _button_variant_qss(
    selector: str,
    swatch: AccentSwatch,
    colors: ColorTokens,
    disabled_bg: str,
    disabled_border: str,
) -> str:
    """Generates normal/hover/pressed/disabled QSS rules for an AccentSwatch button variant."""
    return f"""
{selector} {{
    background-color: {swatch.bg};
    color: {colors.text_on_accent};
    font-weight: bold;
    border: 1px solid {swatch.border};
}}
{selector}:hover {{
    background-color: {swatch.hover};
}}
{selector}:pressed {{
    background-color: {swatch.pressed};
}}
{selector}:disabled {{
    background-color: {disabled_bg};
    color: {colors.text_disabled};
    border-color: {disabled_border};
}}
"""


def _button_size_qss(size_key: str, spec: ButtonSizeSpec) -> str:
    return f"""
QPushButton[uiSize="{size_key}"] {{
    padding: {spec.pad_v}px {spec.pad_h}px;
    min-height: {spec.min_height}px;
}}
"""


def _zone_and_section_qss(theme: ThemeConfig) -> str:
    """Emits targeted overrides for any ZoneConfig or SectionStyle specifying visual fields."""
    blocks: List[str] = []

    for zone_id, zone in theme.zones.items():
        rules: List[str] = []
        if zone.surface_bg:
            rules.append(f"background-color: {zone.surface_bg};")
        if zone.font_size is not None:
            rules.append(f"font-size: {theme.typography.scaled(zone.font_size)}px;")
        if rules:
            joined = "\n    ".join(rules)
            blocks.append(f'QWidget[zone="{zone_id}"] {{\n    {joined}\n}}')

    for section_id, sec in theme.sections.items():
        box_rules: List[str] = []
        if sec.surface_bg:
            box_rules.append(f"background-color: {sec.surface_bg};")
        if sec.border_color:
            box_rules.append(f"border-color: {sec.border_color};")
        if sec.font_size is not None:
            box_rules.append(f"font-size: {theme.typography.scaled(sec.font_size)}px;")
        if box_rules:
            joined = "\n    ".join(box_rules)
            blocks.append(f'QGroupBox[section="{section_id}"] {{\n    {joined}\n}}')
        if sec.title_color:
            blocks.append(
                f'QGroupBox[section="{section_id}"]::title {{\n    color: {sec.title_color};\n}}'
            )

    return "\n".join(blocks)


def build_stylesheet(theme: ThemeConfig) -> str:
    """Builds the complete PySide6 QSS stylesheet from a ThemeConfig."""
    c = theme.colors
    t = theme.typography
    r = theme.radii
    ctrl = theme.controls

    base_font = t.scaled(t.size_sm)
    xs_font = t.scaled(t.size_xs)
    md_font = t.scaled(t.size_md)
    lg_font = t.scaled(t.size_lg)
    accent_text = c.primary.text_accent or c.primary.border

    # Semantic button variants
    variant_rules = "".join([
        _button_variant_qss(
            'QPushButton[variant="primary"]',
            c.primary, c, c.bg_surface, c.border_default,
        ),
        _button_variant_qss(
            'QPushButton[variant="secondary"]',
            c.secondary, c, c.bg_disabled, c.border_subtle,
        ),
        _button_variant_qss(
            'QPushButton[variant="success"]',
            c.success, c, c.bg_disabled, c.border_subtle,
        ),
        _button_variant_qss(
            'QPushButton[variant="warning"]',
            c.warning, c, c.bg_surface, c.border_default,
        ),
        _button_variant_qss(
            'QPushButton[variant="compute"]',
            c.compute, c, c.bg_surface, c.border_default,
        ),
        _button_variant_qss(
            'QPushButton[variant="ai"]',
            c.ai, c, c.bg_surface, c.border_default,
        ),
    ])

    size_rules = "".join([
        _button_size_qss("sm", ctrl.btn_sm),
        _button_size_qss("md", ctrl.btn_md),
        _button_size_qss("lg", ctrl.btn_lg),
        _button_size_qss("xl", ctrl.btn_xl),
        f"""
QPushButton[variant="segmented"] {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_default};
    border-radius: {r.md}px;
    padding: {ctrl.btn_segmented.pad_v}px {ctrl.btn_segmented.pad_h}px;
    color: {c.text_muted};
    font-weight: 500;
}}
QPushButton[variant="segmented"]:checked {{
    background-color: {c.primary.bg};
    border-color: {c.primary.border};
    color: {c.text_on_accent};
    font-weight: bold;
}}
QPushButton[variant="segmented"]:hover:!checked {{
    background-color: {c.bg_elevated};
    color: {c.text_primary};
}}
QPushButton[variant="icon"] {{
    padding: 2px 4px;
    min-height: {ctrl.btn_sm.min_height}px;
    max-width: {ctrl.icon_btn_max_w}px;
}}
""",
    ])

    section_overrides = _zone_and_section_qss(theme)

    return f"""
QMainWindow, QWidget {{
    background-color: {c.bg_app};
    color: {c.text_primary};
    font-family: {t.font_family};
    font-size: {base_font}px;
}}
QGroupBox {{
    border: 1px solid {c.border_default};
    border-radius: {r.lg}px;
    margin-top: 8px;
    padding-top: 10px;
    font-weight: bold;
    font-size: {md_font}px;
    color: {c.text_secondary};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: {accent_text};
}}
/* Semantic Labels & Dividers */
QLabel {{
    background-color: transparent;
}}
QLabel[role="caption"] {{
    font-size: {xs_font}px;
    font-weight: normal;
}}
QLabel[role="value"] {{
    font-size: {xs_font}px;
    color: {c.text_secondary};
}}
QLabel[role="title"] {{
    font-size: {lg_font}px;
    font-weight: bold;
}}
QLabel[tone="muted"] {{
    color: {c.text_muted};
    font-weight: normal;
}}
QLabel[tone="accent"] {{
    color: {accent_text};
}}
QLabel[tone="accent-bold"] {{
    color: {accent_text};
    font-weight: bold;
}}
QLabel[tone="danger"] {{
    color: {c.danger_text};
    font-weight: bold;
}}
QLabel[tone="success"] {{
    color: {c.success.border};
    font-weight: bold;
}}
QLabel[tone="warning"] {{
    color: {c.warning.border};
    font-weight: bold;
}}
QFrame[role="divider"] {{
    color: {c.border_default};
    margin: 4px 0;
}}
/* Radio Buttons & High-Contrast Selected Indicator */
QRadioButton {{
    color: {c.text_primary};
    spacing: 6px;
    font-size: {base_font}px;
    background-color: transparent;
}}
QRadioButton::indicator {{
    width: {ctrl.indicator_size}px;
    height: {ctrl.indicator_size}px;
    border-radius: {r.pill}px;
    border: 2px solid {c.border_strong};
    background-color: {c.bg_surface};
}}
QRadioButton::indicator:hover {{
    border-color: {c.primary.border};
    background-color: {c.bg_elevated};
}}
QRadioButton::indicator:checked {{
    border: 2px solid {c.primary.border};
    background: qradialgradient(
        cx: 0.5, cy: 0.5, radius: 0.45, fx: 0.5, fy: 0.5,
        stop: 0 {c.primary.border},
        stop: 0.55 {c.primary.border},
        stop: 0.65 {c.bg_surface},
        stop: 1.0 {c.bg_surface}
    );
}}
QRadioButton::indicator:disabled {{
    border-color: {c.border_default};
    background-color: {c.bg_disabled};
}}
/* Checkboxes & Checkmark Indicator */
QCheckBox {{
    color: {c.text_primary};
    spacing: 6px;
    font-size: {base_font}px;
    background-color: transparent;
}}
QCheckBox::indicator {{
    width: {ctrl.indicator_size}px;
    height: {ctrl.indicator_size}px;
    border-radius: {r.sm}px;
    border: 2px solid {c.border_strong};
    background-color: {c.bg_surface};
}}
QCheckBox::indicator:hover {{
    border-color: {c.primary.border};
    background-color: {c.bg_elevated};
}}
QCheckBox::indicator:checked {{
    border: 2px solid {c.primary.border};
    background-color: {c.primary.bg};
}}
QCheckBox::indicator:disabled {{
    border-color: {c.border_default};
    background-color: {c.bg_disabled};
}}
/* Buttons */
QPushButton {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_default};
    border-radius: {r.md}px;
    padding: {ctrl.btn_md.pad_v}px {ctrl.btn_md.pad_h}px;
    color: {c.text_primary};
    min-height: {ctrl.btn_md.min_height}px;
}}
QPushButton:hover {{
    background-color: {c.bg_elevated};
    border-color: {c.border_strong};
}}
QPushButton:pressed {{
    background-color: {c.border_strong};
}}
QPushButton:disabled {{
    background-color: {c.bg_disabled};
    color: {c.text_muted};
    border-color: {c.border_subtle};
}}
{variant_rules}
{size_rules}
/* Inputs & Collections */
QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_default};
    border-radius: {r.md}px;
    padding: 2px 6px;
    color: {c.text_primary};
    min-height: {ctrl.input_min_h}px;
}}
QComboBox::drop-down {{
    border: none;
}}
QListWidget, QTableWidget {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_default};
    border-radius: {r.md}px;
    color: {c.text_primary};
}}
QListWidget::item:selected, QTableWidget::item:selected {{
    background-color: {c.primary.bg};
    color: {c.text_on_accent};
}}
/* Sliders */
QSlider {{
    min-height: {ctrl.slider_min_h}px;
    max-height: {ctrl.slider_max_h}px;
}}
QSlider::groove:horizontal {{
    height: {ctrl.slider_groove_h}px;
    background: {c.bg_elevated};
    border-radius: {r.xs}px;
}}
QSlider::sub-page:horizontal {{
    background: {c.primary.bg};
    border-radius: {r.xs}px;
}}
QSlider::handle:horizontal {{
    background: {c.primary.border};
    width: {ctrl.slider_handle_d}px;
    height: {ctrl.slider_handle_d}px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: {ctrl.slider_handle_d // 2}px;
}}
/* Tabs, Headers & Chrome */
QTabWidget::pane {{
    border: 1px solid {c.border_subtle};
}}
QTabBar::tab {{
    background: {c.bg_surface};
    border: 1px solid {c.border_default};
    padding: {ctrl.tab_pad_v}px {ctrl.tab_pad_h}px;
    margin-right: 2px;
    border-top-left-radius: {r.md}px;
    border-top-right-radius: {r.md}px;
    color: {c.text_muted};
    font-weight: bold;
}}
QTabBar::tab:selected {{
    background: {c.bg_elevated};
    color: {accent_text};
    border-bottom-color: {c.bg_elevated};
}}
QHeaderView::section {{
    background-color: {c.bg_surface};
    color: {c.text_secondary};
    border: 1px solid {c.border_default};
    padding: 4px;
}}
QStatusBar {{
    background-color: {c.bg_statusbar};
    color: {c.text_muted};
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background-color: {c.bg_surface};
    width: 12px;
    margin: 0px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical {{
    background-color: {c.border_strong};
    min-height: 30px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {c.border_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background-color: {c.bg_app};
    height: 10px;
    margin: 0px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background-color: {c.bg_elevated};
    min-width: 25px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {c.border_strong};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}
QSplitter::handle:horizontal {{
    background-color: {c.bg_surface};
    width: 4px;
}}
QSplitter::handle:horizontal:hover {{
    background-color: {c.primary.bg};
}}
{section_overrides}
"""
