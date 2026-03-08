"""Vectorize engine — convert raster images (PNG/JPG/BMP) to editable SVG.

Uses `vtracer` for high-quality bitmap tracing. This produces clean vector
paths that can be edited in Inkscape, Illustrator, or any SVG editor.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def vectorize_image(
    input_path: str,
    output_path: str,
    *,
    color_mode: str = "color",
    hierarchical: str = "stacked",
    filter_speckle: int = 4,
    color_precision: int = 6,
    corner_threshold: int = 60,
    length_threshold: float = 4.0,
    splice_threshold: int = 45,
    mode: str = "polygon",
) -> str:
    """Convert a raster image (PNG, JPG, BMP, etc.) to an editable SVG.

    Parameters
    ----------
    input_path : str
        Path to the source raster image.
    output_path : str
        Path for the output SVG file.
    color_mode : str
        "color" for full color tracing, "binary" for black/white.
    hierarchical : str
        "stacked" (layers on top) or "cutout" (shapes cut from each other).
    filter_speckle : int
        Remove speckles of this many pixels or fewer (noise removal).
    color_precision : int
        Number of significant bits for color quantization (1-8).
        Lower = fewer colors = simpler SVG.
    corner_threshold : int
        Angle threshold for corner detection (degrees).
    length_threshold : float
        Minimum path segment length.
    splice_threshold : int
        Angle threshold for splicing paths together (degrees).
    mode : str
        "polygon" for polygon output, "spline" for smooth curves.

    Returns
    -------
    str
        Path to the generated SVG file.

    Raises
    ------
    FileNotFoundError
        If input image does not exist.
    RuntimeError
        If vectorization fails.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input image not found: {input_path}")

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Ensure output has .svg extension
    if not output_path.lower().endswith(".svg"):
        output_path = output_path + ".svg"

    try:
        import vtracer
    except ImportError as exc:
        raise RuntimeError(
            "vtracer is required for image vectorization. "
            "Install it with: pip install vtracer"
        ) from exc

    logger.info("Vectorizing %s → %s (mode=%s, colors=%s)", input_path, output_path, mode, color_mode)

    try:
        vtracer.convert_image_to_svg_py(
            image_path=input_path,
            out_path=output_path,
            colormode=color_mode,
            hierarchical=hierarchical,
            filter_speckle=filter_speckle,
            color_precision=color_precision,
            corner_threshold=corner_threshold,
            length_threshold=length_threshold,
            splice_threshold=splice_threshold,
            mode=mode,
        )
    except Exception as exc:
        raise RuntimeError(f"Vectorization failed: {exc}") from exc

    if not os.path.exists(output_path):
        raise RuntimeError(f"vtracer did not produce output at {output_path}")

    file_size = os.path.getsize(output_path)
    logger.info("Vectorization complete: %s (%d bytes)", output_path, file_size)
    return output_path


# Presets for common use cases
VECTORIZE_PRESETS = {
    "detailed": {
        "color_mode": "color",
        "color_precision": 8,
        "filter_speckle": 2,
        "mode": "spline",
    },
    "simplified": {
        "color_mode": "color",
        "color_precision": 4,
        "filter_speckle": 8,
        "mode": "polygon",
    },
    "sketch": {
        "color_mode": "binary",
        "color_precision": 6,
        "filter_speckle": 4,
        "mode": "spline",
    },
    "logo": {
        "color_mode": "color",
        "color_precision": 3,
        "filter_speckle": 10,
        "mode": "polygon",
    },
}


def vectorize_with_preset(
    input_path: str,
    output_path: str,
    preset: str = "detailed",
) -> str:
    """Vectorize using a named preset for common use cases.

    Presets:
        - "detailed": High-fidelity color tracing with smooth curves
        - "simplified": Fewer colors, cleaner shapes
        - "sketch": Black & white line art (good for hand-drawn sketches)
        - "logo": Very few colors, bold shapes (good for logos/icons)
    """
    if preset not in VECTORIZE_PRESETS:
        raise ValueError(
            f"Unknown preset '{preset}'. Available: {', '.join(VECTORIZE_PRESETS)}"
        )
    params = VECTORIZE_PRESETS[preset]
    return vectorize_image(input_path, output_path, **params)
