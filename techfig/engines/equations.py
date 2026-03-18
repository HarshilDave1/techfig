"""Equation rendering engine using matplotlib mathtext.

Allows rendering LaTeX math strings to SVG/PNG without needing
an external full LaTeX installation.
"""
import logging
from pathlib import Path
from typing import Optional, Any, Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from techfig.styles.presets import get_style

logger = logging.getLogger(__name__)

def render_equation(
    latex_str: str,
    output_path: str,
    style_name: str = "nature",
    style_overrides: Optional[Dict[str, Any]] = None,
    fontsize: int = 24,
    transparent: bool = True
) -> str:
    """Render a LaTeX equation to an image file.
    
    Args:
        latex_str: The LaTeX math string (e.g., r"\\nabla \\cdot \\mathbf{E} = \\frac{\\rho}{\\varepsilon_0}").
            If it does not contain '$', it will be wrapped in '$...$'.
        output_path: Where to save the output file (.svg, .png, etc.)
        style_name: Style preset for font and color overrides.
        style_overrides: Additional rcParams overrides.
        fontsize: Base font size for the equation.
        transparent: Whether to save with a transparent background.
        
    Returns:
        The absolute path to the generated file.
    """
    if not latex_str.strip().startswith("$") and not latex_str.strip().startswith("\\["):
        latex_str = f"${latex_str}$"
        
    base_style = get_style(style_name)
    
    rc_params = {
        "text.usetex": False,  # Rely on mathtext, not external LaTeX
        "mathtext.fontset": "cm", # Computer Modern
        "mathtext.default": "it"
    }
    
    if "colors" in base_style and "text" in base_style["colors"]:
        rc_params["text.color"] = base_style["colors"]["text"]
        
    if style_overrides:
        rc_params.update(style_overrides)
        
    with plt.rc_context(rc_params):
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.text(0, 0, latex_str, fontsize=fontsize, ha='center', va='center')
        
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        fmt = out_file.suffix.lstrip(".")
        if not fmt:
            fmt = "svg"
            out_file = out_file.with_suffix(".svg")
            
        fig.savefig(
            str(out_file),
            format=fmt,
            dpi=rc_params.get("figure.dpi", 300),
            transparent=transparent,
            bbox_inches="tight",
            pad_inches=0.1
        )
        plt.close(fig)
        
    return str(out_file)
