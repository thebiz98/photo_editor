"""
ui/theme/themes.py - Predefined ThemeConfig instances.
STUDIO_DARK_THEME preserves visual parity with the existing dark studio palette while
providing structured zone and per-section style hooks.
"""

from ui.theme.tokens import (
    AccentSwatch,
    CanvasOverlayTokens,
    ColorTokens,
    ControlSizeTokens,
    LayoutTokens,
    RadiusTokens,
    SectionStyle,
    SpacingTokens,
    ThemeConfig,
    TypographyTokens,
    ZoneConfig,
)


STUDIO_DARK_COLORS = ColorTokens(
    bg_app="#18181b",
    bg_surface="#27272a",
    bg_elevated="#3f3f46",
    bg_disabled="#1f1f23",
    bg_statusbar="#121214",
    border_subtle="#27272a",
    border_default="#3f3f46",
    border_strong="#52525b",
    border_hover="#71717a",
    text_primary="#f4f4f5",
    text_secondary="#e4e4e7",
    text_muted="#a1a1aa",
    text_disabled="#71717a",
    text_on_accent="#ffffff",
    primary=AccentSwatch(
        bg="#0284c7",
        hover="#0369a1",
        pressed="#075985",
        border="#38bdf8",
        text_accent="#38bdf8",
    ),
    secondary=AccentSwatch(
        bg="#2563eb",
        hover="#1d4ed8",
        pressed="#1e40af",
        border="#3b82f6",
    ),
    success=AccentSwatch(
        bg="#16a34a",
        hover="#15803d",
        pressed="#166534",
        border="#22c55e",
    ),
    warning=AccentSwatch(
        bg="#d97706",
        hover="#b45309",
        pressed="#92400e",
        border="#f59e0b",
    ),
    compute=AccentSwatch(
        bg="#0d9488",
        hover="#0f766e",
        pressed="#115e59",
        border="#14b8a6",
    ),
    ai=AccentSwatch(
        bg="#7c3aed",
        hover="#6d28d9",
        pressed="#5b21b6",
        border="#8b5cf6",
    ),
    danger_text="#ef4444",
)


STUDIO_DARK_THEME = ThemeConfig(
    name="studio-dark",
    colors=STUDIO_DARK_COLORS,
    typography=TypographyTokens(),
    spacing=SpacingTokens(),
    radii=RadiusTokens(),
    controls=ControlSizeTokens(),
    layout=LayoutTokens(),
    canvas=CanvasOverlayTokens(),
    zones={
        "sidebar-left": ZoneConfig(margins=(4, 4, 4, 4), spacing=5),
        "toolbar": ZoneConfig(margins=(0, 0, 0, 0), spacing=6),
        "center": ZoneConfig(margins=(4, 4, 4, 4), spacing=6),
        "inspector-right": ZoneConfig(margins=(4, 4, 10, 8), spacing=5),
        "print-sidebar": ZoneConfig(margins=(4, 4, 14, 8), spacing=6),
        "print-preview": ZoneConfig(margins=(4, 4, 4, 4), spacing=6),
    },
    sections={
        "workspace": SectionStyle(margins=(8, 6, 8, 8), spacing=5),
        "crop_straighten": SectionStyle(margins=(8, 6, 8, 8), spacing=6),
        "ai_background": SectionStyle(margins=(8, 6, 8, 8), spacing=4),
        "lighting": SectionStyle(margins=(8, 6, 8, 8), spacing=4),
        "rescale": SectionStyle(margins=(8, 6, 8, 8), spacing=5),
        "print_queue": SectionStyle(margins=(8, 6, 8, 8), spacing=5),
        "print_layout": SectionStyle(margins=(8, 6, 8, 8), spacing=4),
        "print_output": SectionStyle(margins=(8, 6, 8, 8), spacing=5),
    },
)
