"""Theme definitions for graph rendering."""

from __future__ import annotations

from .models import ThemeConfig, ThemeName

# --------------------------------------------------------------------------- #
# Dark theme: deep navy background, neon-style glowing edges, vibrant nodes
# --------------------------------------------------------------------------- #
DARK_THEME = ThemeConfig(
    name="dark",
    bg_color="#1a1a2e",
    node_colors=[
        "#c0392b",  # deep red
        "#2874a6",  # steel blue
        "#7d3c98",  # plum purple
        "#d4730e",  # burnt orange
        "#1a8a7d",  # dark teal
        "#b9770e",  # dark gold
        "#2e86c1",  # medium blue
        "#a93226",  # brick red
        "#117a65",  # forest teal
        "#884ea0",  # medium purple
        "#cb4335",  # vermillion
        "#2471a3",  # cobalt
    ],
    edge_color="#4a4e6980",
    edge_highlight_color="#e94560",
    font_family="Segoe UI, Roboto, sans-serif",
    font_color="#e0e0e0",
    font_size=13,
    highlight_color="#e94560",
    node_border_color="#ffffff30",
    node_border_width=1,
    node_shape="box",
)

# --------------------------------------------------------------------------- #
# Light theme: clean white background, pastel institution colors
# --------------------------------------------------------------------------- #
LIGHT_THEME = ThemeConfig(
    name="light",
    bg_color="#f8f9fa",
    node_colors=[
        "#4361ee",  # blue
        "#f72585",  # pink
        "#7209b7",  # purple
        "#3a0ca3",  # indigo
        "#4cc9f0",  # light blue
        "#f77f00",  # orange
        "#2a9d8f",  # teal
        "#e63946",  # red
        "#457b9d",  # steel blue
        "#6a994e",  # green
        "#bc6c25",  # brown
        "#9b5de5",  # violet
    ],
    edge_color="#adb5bd80",
    edge_highlight_color="#4361ee",
    font_family="Inter, Segoe UI, sans-serif",
    font_color="#212529",
    font_size=14,
    highlight_color="#4361ee",
    node_border_color="#dee2e6",
    node_border_width=2,
    node_shape="box",
)

# --------------------------------------------------------------------------- #
# Academic theme: cream/parchment background, elegant serif fonts, muted tones
# --------------------------------------------------------------------------- #
ACADEMIC_THEME = ThemeConfig(
    name="academic",
    bg_color="#faf8f0",
    node_colors=[
        "#6b4c3b",  # dark brown
        "#8b6f47",  # warm brown
        "#5b7065",  # sage green
        "#7a5c61",  # mauve
        "#4a6670",  # slate teal
        "#8c6e4f",  # caramel
        "#5a6e5c",  # moss
        "#7d6b7d",  # dusty purple
        "#6a7b8b",  # blue grey
        "#9c7a5a",  # tan
        "#5c7a6e",  # sea green
        "#8a6565",  # rose brown
    ],
    edge_color="#c4b8a860",
    edge_highlight_color="#6b4c3b",
    font_family="Georgia, Palatino, serif",
    font_color="#3d3229",
    font_size=13,
    highlight_color="#6b4c3b",
    node_border_color="#c4b8a8",
    node_border_width=1,
    node_shape="box",
)


THEMES: dict[ThemeName, ThemeConfig] = {
    ThemeName.DARK: DARK_THEME,
    ThemeName.LIGHT: LIGHT_THEME,
    ThemeName.ACADEMIC: ACADEMIC_THEME,
}


def get_theme(name: ThemeName) -> ThemeConfig:
    """Look up a theme by name."""
    return THEMES[name]
