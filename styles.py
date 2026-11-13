"""
styles.py - Compatibility facade exposing DARK_THEME_QSS built from ui.theme.
"""

from ui.theme import STUDIO_DARK_THEME, build_stylesheet

DARK_THEME_QSS = build_stylesheet(STUDIO_DARK_THEME)
