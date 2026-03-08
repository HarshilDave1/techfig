"""Format conversion utilities.

Handles SVG → PNG and SVG → PDF conversions using available system tools.
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def convert_format(
    input_path: str,
    output_path: str,
    dpi: int = 300,
    width: Optional[int] = None,
) -> str:
    """Convert a figure between formats.

    Supports:
    - SVG → PNG  (via cairosvg, rsvg-convert, or inkscape)
    - SVG → PDF  (via cairosvg, rsvg-convert, or inkscape)

    Args:
        input_path: Source file path.
        output_path: Destination file path (format inferred from extension).
        dpi: Dots-per-inch for rasterization (PNG only).
        width: Optional pixel width for the output image.

    Returns:
        Absolute path to the converted file.

    Raises:
        FileNotFoundError: If ``input_path`` doesn't exist.
        ValueError: If the conversion pair is unsupported.
        RuntimeError: If no conversion backend is available.
    """
    src = Path(input_path).resolve()
    dst = Path(output_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        raise FileNotFoundError(f"Source file not found: {src}")

    in_fmt = src.suffix.lower()
    out_fmt = dst.suffix.lower()

    if in_fmt == ".svg" and out_fmt == ".png":
        _svg_to_raster(str(src), str(dst), fmt="png", dpi=dpi, width=width)
    elif in_fmt == ".svg" and out_fmt == ".pdf":
        _svg_to_raster(str(src), str(dst), fmt="pdf", dpi=dpi, width=width)
    elif in_fmt == out_fmt:
        # Same format — just copy
        import shutil
        shutil.copy2(str(src), str(dst))
    else:
        raise ValueError(
            f"Unsupported conversion: {in_fmt} → {out_fmt}. "
            "Supported: SVG→PNG, SVG→PDF."
        )

    return str(dst)


def _svg_to_raster(
    src: str, dst: str,
    fmt: str = "png",
    dpi: int = 300,
    width: Optional[int] = None,
) -> None:
    """Convert SVG to PNG or PDF using the best available backend."""
    errors: list[str] = []

    # Strategy 1: cairosvg (Python)
    try:
        import cairosvg
        kwargs: dict = {"url": src, "write_to": dst, "dpi": dpi}
        if width:
            kwargs["output_width"] = width
        if fmt == "png":
            cairosvg.svg2png(**kwargs)
        elif fmt == "pdf":
            cairosvg.svg2pdf(**kwargs)
        return
    except ImportError:
        errors.append("cairosvg not installed")
    except Exception as exc:
        errors.append(f"cairosvg failed: {exc}")

    # Strategy 2: rsvg-convert
    try:
        cmd = ["rsvg-convert", "-f", fmt, "-o", dst, src]
        if fmt == "png" and width:
            cmd.extend(["-w", str(width)])
        elif fmt == "png":
            cmd.extend(["--dpi-x", str(dpi), "--dpi-y", str(dpi)])
        subprocess.run(cmd, check=True, capture_output=True)
        return
    except FileNotFoundError:
        errors.append("rsvg-convert not found")
    except subprocess.CalledProcessError as exc:
        errors.append(f"rsvg-convert failed: {exc}")

    # Strategy 3: inkscape CLI
    try:
        export_type = fmt  # "png" or "pdf"
        cmd = [
            "inkscape", src,
            f"--export-type={export_type}",
            f"--export-filename={dst}",
        ]
        if fmt == "png":
            cmd.append(f"--export-dpi={dpi}")
            if width:
                cmd.append(f"--export-width={width}")
        subprocess.run(cmd, check=True, capture_output=True)
        return
    except FileNotFoundError:
        errors.append("inkscape not found")
    except subprocess.CalledProcessError as exc:
        errors.append(f"inkscape failed: {exc}")

    raise RuntimeError(
        f"No backend could convert '{src}' to {fmt}. "
        f"Install cairosvg (pip), librsvg (brew), or inkscape. "
        f"Errors: {'; '.join(errors)}"
    )
