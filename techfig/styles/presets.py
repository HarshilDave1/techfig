"""Style presets for technical figures and diagrams.

Provides a unified styling dictionary that can be applied
to matplotlib figures or SVG diagrams.  Each preset contains:

- ``colors`` dict with semantic names (primary, secondary, etc.)
- ``font_family`` / ``font_size`` / ``stroke_width`` for diagrams
- matplotlib ``rcParams`` keys (axes.labelsize, etc.) for figures
"""
import logging
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---- Colorblind-safe palette (Wong 2011) --------------------------------
COLORS_PRIMARY = "#0072B2"
COLORS_SECONDARY = "#D55E00"
COLORS_ACCENT = "#009E73"
COLORS_WARNING = "#F0E442"
COLORS_MUTED = "#56B4E9"

# ---- Base styles --------------------------------------------------------

_COMMON_COLORS: Dict[str, str] = {
    "primary": COLORS_PRIMARY,
    "secondary": COLORS_SECONDARY,
    "accent": COLORS_ACCENT,
    "warning": COLORS_WARNING,
    "muted": COLORS_MUTED,
    "background": "#FFFFFF",
    "text": "#000000",
    "stroke": "#000000",
}

# ---- Base Publication Styles ----------------------------------------------

# General guidelines for Nature, Science, Cell:
# - Sans-serif fonts (Arial, Helvetica)
# - Single column width: ~89 mm (3.5 inches)
# - Double column width: ~183 mm (7.2 inches)
# - Text size: 5-7 pt (Nature) or 7-9 pt (Science)
# - Line weights: 0.25 - 1.0 pt

NATURE_STYLE: Dict[str, Any] = {
    # Diagram-specific keys
    "font_family": "DejaVu Sans, Liberation Sans, sans-serif",
    "font_size": 7,
    "stroke_width": 0.75,
    "colors": dict(_COMMON_COLORS),
    # Matplotlib rcParams
    "figure.figsize": (3.5, 2.625),  # 89mm width, 4:3 aspect ratio
    "figure.dpi": 300,
    "font.size": 7,
    "axes.labelsize": 7,
    "axes.titlesize": 7,
    "xtick.labelsize": 6,
    "ytick.labelsize": 6,
    "legend.fontsize": 6,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Noto Sans"],
    "lines.linewidth": 1.0,
    "axes.linewidth": 0.5,
    "grid.linewidth": 0.5,
    "savefig.bbox": "tight",
}

SCIENCE_STYLE: Dict[str, Any] = {
    **NATURE_STYLE,
    "font_size": 8,
    "figure.figsize": (3.5, 2.5),
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "colors": dict(_COMMON_COLORS),
}

# General guidelines for IEEE conferences & journals:
# - Single column width: 3.5 inches
# - Font size: 8-10 pt (usually matching column text or slightly smaller)
# - Font family: Times New Roman, Arial, or Helvetica
IEEE_STYLE: Dict[str, Any] = {
    **NATURE_STYLE,
    "font_family": "Times New Roman, Times, serif",
    "font_size": 8,
    "stroke_width": 1.0,
    "figure.figsize": (3.5, 2.5),
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "serif"],
    "lines.linewidth": 1.25,
    "axes.linewidth": 0.8,
    "grid.linewidth": 0.5,
    "colors": dict(_COMMON_COLORS),
}

# General guidelines for Optica (formerly OSA):
# - Column width: ~3.25 inches to 3.5 inches
# - Font size: 9-10 pt
OPTICA_STYLE: Dict[str, Any] = {
    **IEEE_STYLE,
    "font_family": "Arial, Helvetica, sans-serif",
    "font_size": 9,
    "figure.figsize": (3.25, 2.5),
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 10,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Noto Sans"],
    "lines.linewidth": 1.5,
    "colors": dict(_COMMON_COLORS),
}

# General guidelines for SPIE proceedings:
# - Column width: ~3.4 inches (or full width 6.75)
# - Font size: 10 pt
SPIE_STYLE: Dict[str, Any] = {
    **IEEE_STYLE,
    "font_family": "DejaVu Sans, Liberation Sans, sans-serif",
    "font_size": 10,
    "figure.figsize": (3.4, 2.5),
    "font.size": 10,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Noto Sans"],
    "colors": dict(_COMMON_COLORS),
}

# ---- Alternative Styles -------------------------------------------------

DARK_STYLE: Dict[str, Any] = {
    **NATURE_STYLE,  # Base sizing
    "colors": {
        "primary": "#56B4E9",
        "secondary": "#E69F00",
        "accent": "#009E73",
        "warning": "#F0E442",
        "muted": "#CC79A7",
        "background": "#121212",
        "text": "#E0E0E0",
        "stroke": "#B0B0B0",
    },
    "axes.facecolor": "#121212",
    "figure.facecolor": "#121212",
    "axes.edgecolor": "#B0B0B0",
    "axes.labelcolor": "#E0E0E0",
    "xtick.color": "#B0B0B0",
    "ytick.color": "#B0B0B0",
    "text.color": "#E0E0E0",
    "grid.color": "#333333",
}

PRESENTATION_STYLE: Dict[str, Any] = {
    **NATURE_STYLE,
    "font_size": 24,
    "stroke_width": 3.0,
    "axes.labelsize": 22,
    "axes.titlesize": 26,
    "xtick.labelsize": 18,
    "ytick.labelsize": 18,
    "legend.fontsize": 18,
    "lines.linewidth": 3.0,
    "figure.figsize": (10.0, 5.625),  # 16:9 ratio
    "figure.dpi": 150,
    "colors": dict(_COMMON_COLORS),
}

MINIMAL_STYLE: Dict[str, Any] = {
    **NATURE_STYLE,
    "font_family": "DejaVu Sans, Liberation Sans, sans-serif",
    "stroke_width": 0.75,
    "axes.linewidth": 0.5,
    "grid.linewidth": 0.25,
    "lines.linewidth": 1.0,
    "axes.grid": False,
    "colors": {
        **_COMMON_COLORS,
        "stroke": "#666666",
    },
}

# ---- Registry -----------------------------------------------------------

_BUILT_IN_STYLES: Dict[str, Dict[str, Any]] = {
    "nature": NATURE_STYLE,
    "science": SCIENCE_STYLE,
    "ieee": IEEE_STYLE,
    "optica": OPTICA_STYLE,
    "spie": SPIE_STYLE,
    "dark": DARK_STYLE,
    "presentation": PRESENTATION_STYLE,
    "minimal": MINIMAL_STYLE,
}


def get_available_styles() -> List[str]:
    """Return the names of all built-in style presets."""
    return sorted(_BUILT_IN_STYLES.keys())


def load_custom_style(yaml_path: str) -> Dict[str, Any]:
    """Load a user-defined style from a YAML file.

    The file should have the same structure as the built-in style dicts
    (flat keys for rcParams, nested ``colors`` dict, etc.).
    Missing keys are filled in from the ``nature`` base style.
    """
    import yaml  # lazy import — pyyaml is a dep

    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Style file not found: {yaml_path}")

    with open(path) as f:
        custom: Dict[str, Any] = yaml.safe_load(f) or {}

    # Merge onto nature base so every key has a sensible default
    merged = dict(NATURE_STYLE)
    if "colors" in custom:
        merged["colors"] = {**merged.get("colors", {}), **custom.pop("colors")}
    merged.update(custom)
    return merged


def get_style(style_name: str) -> Dict[str, Any]:
    """Get a style dictionary by name.

    Checks built-in presets first, then looks for a ``.yaml`` file
    at the given path.  Falls back to ``nature`` on failure.
    """
    name = style_name.lower()

    # Built-in?
    if name in _BUILT_IN_STYLES:
        return _BUILT_IN_STYLES[name]

    # Treat as YAML path?
    if Path(style_name).suffix in (".yaml", ".yml") and Path(style_name).exists():
        try:
            return load_custom_style(style_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load custom style '%s': %s", style_name, exc)

    warnings.warn(
        f"Unknown style '{style_name}', falling back to 'nature'. "
        f"Available: {', '.join(get_available_styles())}",
        stacklevel=2,
    )
    return NATURE_STYLE
