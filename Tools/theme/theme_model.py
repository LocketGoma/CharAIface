from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThemePalette:
    window_bg: str
    panel_bg: str
    chat_bg: str
    user_bubble_bg: str
    assistant_bubble_bg: str
    text_primary: str
    text_secondary: str
    border: str
    accent: str
    accent_text: str
    input_bg: str
    input_border: str
    error: str
    warning: str
    success: str


@dataclass
class ThemeDefinition:
    id: str
    name: str
    palette: ThemePalette
