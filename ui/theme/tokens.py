"""
ui/theme/tokens.py - Pure typed design tokens and zone/section style configurations.
Supports global visual consistency, per-section style overrides, and future UI scaling.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class AccentSwatch:
    """Four-state color palette for semantic buttons, highlights, and accents."""
    bg: str
    hover: str
    pressed: str
    border: str
    text_accent: Optional[str] = None


@dataclass(frozen=True)
class ColorTokens:
    """Semantic surface, border, text, and action color palette."""
    # Surfaces
    bg_app: str
    bg_surface: str
    bg_elevated: str
    bg_disabled: str
    bg_statusbar: str

    # Borders
    border_subtle: str
    border_default: str
    border_strong: str
    border_hover: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    text_on_accent: str

    # Semantic swatches
    primary: AccentSwatch
    secondary: AccentSwatch
    success: AccentSwatch
    warning: AccentSwatch
    compute: AccentSwatch
    ai: AccentSwatch
    danger_text: str


@dataclass(frozen=True)
class TypographyTokens:
    """Typography family and size hierarchy (ready for future ui_scale multiplication)."""
    font_family: str = "'Segoe UI', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif"
    font_family_raw: str = "Segoe UI"
    size_xs: int = 11
    size_sm: int = 11
    size_md: int = 11
    size_lg: int = 12
    ui_scale: float = 1.0

    def scaled(self, px: int) -> int:
        return max(8, int(round(px * self.ui_scale)))


@dataclass(frozen=True)
class SpacingTokens:
    """Consistent margin and layout spacing scale (px)."""
    xxs: int = 1
    xs: int = 2
    sm: int = 4
    md: int = 6
    lg: int = 8
    xl: int = 12


@dataclass(frozen=True)
class RadiusTokens:
    """Corner radius scale (px)."""
    xs: int = 2
    sm: int = 3
    md: int = 4
    lg: int = 6
    pill: int = 8


@dataclass(frozen=True)
class ButtonSizeSpec:
    """Padding and minimum height specification for a semantic button size tier."""
    pad_v: int
    pad_h: int
    min_height: int


@dataclass(frozen=True)
class ControlSizeTokens:
    """Sizing tiers for buttons, inputs, sliders, and selection indicators."""
    btn_sm: ButtonSizeSpec = field(default_factory=lambda: ButtonSizeSpec(pad_v=3, pad_h=6, min_height=20))
    btn_md: ButtonSizeSpec = field(default_factory=lambda: ButtonSizeSpec(pad_v=4, pad_h=8, min_height=22))
    btn_lg: ButtonSizeSpec = field(default_factory=lambda: ButtonSizeSpec(pad_v=6, pad_h=10, min_height=22))
    btn_xl: ButtonSizeSpec = field(default_factory=lambda: ButtonSizeSpec(pad_v=10, pad_h=14, min_height=26))
    btn_segmented: ButtonSizeSpec = field(default_factory=lambda: ButtonSizeSpec(pad_v=5, pad_h=4, min_height=22))
    icon_btn_max_w: int = 30
    input_min_h: int = 20
    slider_min_h: int = 16
    slider_max_h: int = 18
    slider_groove_h: int = 4
    slider_handle_d: int = 12
    indicator_size: int = 14
    tab_pad_v: int = 8
    tab_pad_h: int = 18


@dataclass(frozen=True)
class LayoutTokens:
    """Window, splitter, sidebar, and collection bounds."""
    window_default_size: Tuple[int, int] = (1340, 880)
    window_min_size: Tuple[int, int] = (1000, 700)
    left_panel_range: Tuple[int, int] = (240, 300)
    center_panel_min_w: int = 380
    right_panel_range: Tuple[int, int] = (260, 450)
    splitter_sizes: Tuple[int, int, int] = (250, 815, 275)
    print_sidebar_range: Tuple[int, int] = (360, 420)
    print_sidebar_min_h: int = 600
    workspace_list_h: Tuple[int, int] = (110, 150)
    workspace_icon_px: int = 40
    workspace_thumb_px: int = 48
    print_table_h: Tuple[int, int] = (110, 160)
    print_thumb_px: int = 40


@dataclass(frozen=True)
class CanvasOverlayTokens:
    """QPainter colors and dimensions for InteractiveCanvas and scene overlay items."""
    viewport_bg: Tuple[int, int, int] = (24, 24, 27)
    roi_stroke: Tuple[int, int, int] = (0, 220, 255)
    roi_fill: Tuple[int, int, int, int] = (0, 180, 255, 30)
    roi_stroke_width: float = 2.0
    handle_fill: Tuple[int, int, int] = (0, 160, 255)
    handle_hover: Tuple[int, int, int] = (0, 200, 255)
    handle_border: Tuple[int, int, int] = (255, 255, 255)
    handle_border_width: float = 1.5
    handle_size: float = 12.0
    pin_fill: Tuple[int, int, int] = (0, 220, 255)
    pin_hover: Tuple[int, int, int] = (255, 180, 0)
    pin_border: Tuple[int, int, int] = (255, 255, 255)
    pin_border_width: float = 2.0
    pin_size: float = 18.0
    quad_fill: Tuple[int, int, int, int] = (0, 180, 255, 35)
    top_edge_amber: Tuple[int, int, int] = (245, 158, 11)
    top_edge_width: float = 2.5
    badge_text_dark: Tuple[int, int, int] = (24, 24, 27)
    badge_font_pt: int = 8


@dataclass(frozen=True)
class ZoneConfig:
    """Layout density configuration for a major UI zone (sidebar, toolbar, inspector, etc.)."""
    margins: Tuple[int, int, int, int] = (4, 4, 4, 4)
    spacing: int = 5
    font_size: Optional[int] = None
    surface_bg: Optional[str] = None


@dataclass(frozen=True)
class SectionStyle:
    """
    Per-section layout and visual overrides applied via SectionBox and QSS [section="..."].
    Any None visual property inherits the global theme default.
    """
    margins: Tuple[int, int, int, int] = (8, 6, 8, 8)
    spacing: int = 5
    title_color: Optional[str] = None
    surface_bg: Optional[str] = None
    border_color: Optional[str] = None
    font_size: Optional[int] = None


@dataclass(frozen=True)
class ThemeConfig:
    """Root theme specification combining tokens, zone configs, and section overrides."""
    name: str
    colors: ColorTokens
    typography: TypographyTokens = field(default_factory=TypographyTokens)
    spacing: SpacingTokens = field(default_factory=SpacingTokens)
    radii: RadiusTokens = field(default_factory=RadiusTokens)
    controls: ControlSizeTokens = field(default_factory=ControlSizeTokens)
    layout: LayoutTokens = field(default_factory=LayoutTokens)
    canvas: CanvasOverlayTokens = field(default_factory=CanvasOverlayTokens)
    zones: Dict[str, ZoneConfig] = field(default_factory=dict)
    sections: Dict[str, SectionStyle] = field(default_factory=dict)

    def get_zone_config(self, zone_id: str) -> ZoneConfig:
        """Returns the configured ZoneConfig or a sensible default."""
        return self.zones.get(zone_id, ZoneConfig())

    def get_section_style(self, section_id: str) -> SectionStyle:
        """Returns the configured SectionStyle or a sensible default."""
        return self.sections.get(section_id, SectionStyle())
