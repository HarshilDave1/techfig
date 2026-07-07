"""Equation rendering engine using matplotlib mathtext.

Allows rendering LaTeX math strings to SVG/PNG without needing
an external full LaTeX installation.  Matplotlib's mathtext
parser supports the core LaTeX math syntax used in scientific
writing (fractions, subscripts/superscripts, Greek letters,
matrices, etc.) but not macros or full LaTeX packages.

If a string already carries ``$...$`` or ``\\(...\\)`` math
delimiters they are honoured; otherwise the whole string is
wrapped in ``$...$`` so a plain ``\\nabla \\cdot E`` works.
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib

matplotlib.use("Agg")  # headless backend — safe on servers
import matplotlib.pyplot as plt  # noqa: E402

from techfig.styles.presets import get_style  # noqa: E402

logger = logging.getLogger(__name__)


def _ensure_math_delimiters(latex_str: str) -> str:
    """Wrap a LaTeX snippet in ``$...$`` if it is not already delimited.

    Recognised delimiters are ``$...$``, ``$$...$$``, ``\\(...\\)``
    and ``\\[...\\]``.  Anything already wrapped is returned untouched.
    """
    stripped = latex_str.strip()
    if not stripped:
        raise ValueError("latex_str must not be empty")

    if (
        stripped.startswith("$")
        or stripped.startswith(r"\(")
        or stripped.startswith(r"\[")
    ):
        return latex_str
    return f"${latex_str}$"


def render_equation(
    latex_str: str,
    output_path: str,
    style_name: str = "nature",
    style_overrides: Optional[Dict[str, Any]] = None,
    fontsize: int = 24,
    transparent: bool = True,
    dpi: Optional[int] = None,
) -> str:
    """Render a LaTeX equation to an image file via matplotlib mathtext.

    Args:
        latex_str: The LaTeX math string (e.g., r"\\nabla \\cdot \\mathbf{E}
            = \\frac{\\rho}{\\varepsilon_0}").  If it does not already carry
            ``$...$`` / ``\\(...\\)`` / ``\\[...\\]`` delimiters it is
            wrapped in ``$...$`` automatically.
        output_path: Where to save the output file (.svg, .png, etc.).
        style_name: Style preset for font and color overrides.
        style_overrides: Additional rcParams overrides merged on top of the
            style preset.
        fontsize: Base font size for the equation (pt).
        transparent: Whether to save with a transparent background.
        dpi: Override DPI for raster output (PNG).  When ``None`` the
            style preset's ``figure.dpi`` is used, falling back to 300.

    Returns:
        The absolute path to the generated file.

    Raises:
        ValueError: If ``latex_str`` is empty or contains mathtext that
            matplotlib cannot parse.
    """
    latex_str = _ensure_math_delimiters(latex_str)

    base_style = get_style(style_name)

    rc_params: Dict[str, Any] = {
        "text.usetex": False,  # rely on mathtext, not an external LaTeX install
        "mathtext.fontset": "cm",  # Computer Modern — closest to real LaTeX
        "mathtext.default": "it",
    }

    # Pull DPI from the style preset (e.g. nature=300, presentation=150)
    # unless the caller overrides it.
    effective_dpi = dpi if dpi is not None else base_style.get("figure.dpi", 300)
    rc_params["figure.dpi"] = effective_dpi
    rc_params["savefig.dpi"] = effective_dpi

    if "colors" in base_style and "text" in base_style["colors"]:
        rc_params["text.color"] = base_style["colors"]["text"]

    if style_overrides:
        rc_params.update(style_overrides)

    out_file = Path(output_path).resolve()
    fmt = out_file.suffix.lstrip(".")
    if not fmt:
        fmt = "svg"
        out_file = out_file.with_suffix(".svg")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with plt.rc_context(rc_params):
        # Tiny figure — bbox_inches="tight" trims to the text extent so the
        # figure size only needs to be non-zero.
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.text(0, 0, latex_str, fontsize=fontsize, ha="center", va="center")

        try:
            fig.savefig(
                str(out_file),
                format=fmt,
                dpi=effective_dpi,
                transparent=transparent,
                bbox_inches="tight",
                pad_inches=0.1,
            )
        except ValueError as exc:
            # matplotlib raises ValueError for unparseable mathtext.
            raise ValueError(
                f"Failed to render equation (invalid mathtext?): {exc}"
            ) from exc
        finally:
            # Always release the figure handle — safe even on the success path.
            plt.close(fig)

    logger.debug("Rendered equation to %s (dpi=%s, style=%s)", out_file, effective_dpi, style_name)
    return str(out_file)
