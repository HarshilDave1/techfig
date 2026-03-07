"""Style presets for technical figures and diagrams.

Provides a unified styling dictionary that can be applied
to matplotlib figures or SVG diagrams.
"""
from typing import Dict, Any

# Primary colorblind safe palette (Wong 2011)
COLORS_PRIMARY = "#0072B2"
COLORS_SECONDARY = "#D55E00"
COLORS_ACCENT = "#009E73"
COLORS_WARNING = "#F0E442"
COLORS_MUTED = "#56B4E9"

NATURE_STYLE: Dict[str, Any] = {
    # Diagram Specifics
    "font_family": "Arial, Helvetica, sans-serif",
    "font_size": 18,
    "stroke_width": 2.5,
    "colors": {
        "primary": COLORS_PRIMARY,
        "secondary": COLORS_SECONDARY,
        "accent": COLORS_ACCENT,
        "warning": COLORS_WARNING,
        "muted": COLORS_MUTED,
        "background": "#FFFFFF",
        "text": "#000000",
        "stroke": "#000000"
    },
    
    # Matplotlib Specifics (to be used by figures engine)
    "axes.labelsize": 18,
    "axes.titlesize": 20,
    "xtick.labelsize": 16,
    "ytick.labelsize": 16,
    "legend.fontsize": 16,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "Nimbus Sans L", "Liberation Sans", "sans-serif"],
    "lines.linewidth": 2.5,
    "axes.linewidth": 1.5,
    "grid.linewidth": 1.0,
    "figure.figsize": (8.0, 6.0),
    "figure.dpi": 300,
    "savefig.bbox": "tight"
}

SCIENCE_STYLE: Dict[str, Any] = {
    **NATURE_STYLE,
    # Small tweaks for another journal type if needed
    "font_family": "Times New Roman, Times, serif",
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "Liberation Serif", "serif"]
}

DARK_STYLE: Dict[str, Any] = {
    **NATURE_STYLE,
    "colors": {
        "primary": "#56B4E9",     # Lighter blue
        "secondary": "#E69F00",   # Muted orange
        "accent": "#009E73",      # Green
        "warning": "#F0E442",     # Yellow
        "muted": "#CC79A7",       # Pinkish purple
        "background": "#121212",  # Near black
        "text": "#E0E0E0",        # Off white
        "stroke": "#B0B0B0"       # Light gray
    },
    # Matplotlib dark overrides
    "axes.facecolor": "#121212",
    "figure.facecolor": "#121212",
    "axes.edgecolor": "#B0B0B0",
    "axes.labelcolor": "#E0E0E0",
    "xtick.color": "#B0B0B0",
    "ytick.color": "#B0B0B0",
    "text.color": "#E0E0E0",
    "grid.color": "#333333"
}

def get_style(style_name: str) -> Dict[str, Any]:
    """Get a style dictionary by name."""
    name = style_name.lower()
    if name == "nature":
        return NATURE_STYLE
    elif name == "science":
        return SCIENCE_STYLE
    elif name == "dark":
        return DARK_STYLE
    
    # Default to nature
    return NATURE_STYLE
