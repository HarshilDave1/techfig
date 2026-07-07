"""Format conversion utilities.

Handles SVG → PNG and SVG → PDF conversions using available system tools.

Backend priority for PNG rasterization (highest fidelity first):

1. **Playwright (Chromium)** — full browser rendering pipeline; the most
   faithful rasterization for complex SVGs (filters, CSS, web fonts, foreign
   objects). Requires the ``playwright`` package and an installed browser.
2. **rsvg-convert / resvg** — fast, high-quality native SVG rasterizer
   (``librsvg`` or ``resvg`` CLI). Preferred when Playwright is unavailable.
3. **cairosvg** — pure-Python fallback; good for simple SVGs but misses
   some CSS/filter features.
4. **inkscape** — last-resort CLI fallback.

PDF conversion uses rsvg-convert → cairosvg → inkscape (Playwright does not
target SVG→PDF directly).
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
    - SVG → PNG  (via Playwright, rsvg-convert, cairosvg, or inkscape)
    - SVG → PDF  (via rsvg-convert, cairosvg, or inkscape)

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
    """Convert SVG to PNG or PDF using the best available backend.

    PNG order: Playwright → rsvg-convert → cairosvg → inkscape.
    PDF order: rsvg-convert → cairosvg → inkscape.
    """
    errors: list[str] = []

    if fmt == "png":
        # Strategy 1: Playwright (Chromium) — highest fidelity
        try:
            _svg_to_png_playwright(src, dst, dpi=dpi, width=width)
            return
        except ImportError:
            errors.append("playwright not installed")
        except Exception as exc:  # noqa: BLE001 — any failure falls through
            errors.append(f"playwright failed: {exc}")

        # Strategy 2: rsvg-convert / resvg
        if _try_rsvg(src, dst, fmt="png", dpi=dpi, width=width, errors=errors):
            return

        # Strategy 3: cairosvg
        if _try_cairosvg(src, dst, fmt="png", dpi=dpi, width=width, errors=errors):
            return

        # Strategy 4: inkscape
        if _try_inkscape(src, dst, fmt="png", dpi=dpi, width=width, errors=errors):
            return

    elif fmt == "pdf":
        # Playwright does not target SVG→PDF; start with rsvg-convert.
        if _try_rsvg(src, dst, fmt="pdf", dpi=dpi, width=width, errors=errors):
            return
        if _try_cairosvg(src, dst, fmt="pdf", dpi=dpi, width=width, errors=errors):
            return
        if _try_inkscape(src, dst, fmt="pdf", dpi=dpi, width=width, errors=errors):
            return

    else:
        raise ValueError(f"Unsupported raster format: {fmt!r}")

    raise RuntimeError(
        f"No backend could convert '{src}' to {fmt}. "
        f"Install playwright (pip + `playwright install chromium`), "
        f"librsvg/resvg, cairosvg, or inkscape. "
        f"Errors: {'; '.join(errors)}"
    )


def _svg_to_png_playwright(
    src: str, dst: str, dpi: int = 300, width: Optional[int] = None,
) -> None:
    """Render an SVG to PNG via a headless Chromium browser.

    Screenshots the ``<svg>`` element directly so the output is clipped to
    the drawing (no surrounding viewport whitespace). ``dpi`` is honoured via
    Playwright's ``device_scale_factor`` (CSS px → device px at 96 dpi base).
    """
    from playwright.sync_api import sync_playwright

    svg_path = Path(src).resolve()
    scale = max(dpi / 96.0, 1.0)

    # Read the SVG to discover its intrinsic size; fall back to a generous
    # default canvas when width/height are absent.
    svg_markup = svg_path.read_text(encoding="utf-8")
    vw, vh = _svg_intrinsic_size(svg_markup, default=(1200, 800))
    if width:
        # Preserve aspect ratio when an explicit width is requested.
        ratio = vh / vw if vw else 0.75
        vh = int(round(width * ratio))
        vw = width

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": int(vw), "height": int(vh)},
                device_scale_factor=scale,
            )
            html = (
                "<!DOCTYPE html><html><head><style>"
                "html,body{margin:0;padding:0;background:transparent;}"
                "</style></head><body>"
                f"{svg_markup}"
                "</body></html>"
            )
            page.set_content(html)
            # Wait a frame for fonts/filters to settle.
            page.wait_for_timeout(100)
            svg_el = page.locator("svg").first
            svg_el.screenshot(path=dst, omit_background=True)
        finally:
            browser.close()


def _svg_intrinsic_size(markup: str, default=(1200, 800)):
    """Best-effort parse of an SVG's width/height or viewBox attributes."""
    import re

    w = h = None
    m = re.search(r'\bwidth\s*=\s*"([^"]+)"', markup)
    if m:
        w = _parse_svg_len(m.group(1))
    m = re.search(r'\bheight\s*=\s*"([^"]+)"', markup)
    if m:
        h = _parse_svg_len(m.group(1))
    if w and h:
        return w, h
    # Fall back to viewBox
    m = re.search(r'\bviewBox\s*=\s*"([^"]+)"', markup)
    if m:
        parts = m.group(1).replace(",", " ").split()
        if len(parts) >= 4:
            try:
                vb_w = float(parts[2])
                vb_h = float(parts[3])
                return (w or int(vb_w), h or int(vb_h))
            except ValueError:
                pass
    return default


def _parse_svg_len(value: str) -> Optional[int]:
    """Parse an SVG length like '800', '800px', '21cm' into integer pixels."""
    import re

    m = re.match(r"^\s*([0-9.]+)\s*(px|pt|in|cm|mm)?", value)
    if not m:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    unit = (m.group(2) or "px").lower()
    if unit == "px":
        return int(round(num))
    if unit == "pt":
        return int(round(num * 96.0 / 72.0))
    if unit == "in":
        return int(round(num * 96.0))
    if unit == "cm":
        return int(round(num * 96.0 / 2.54))
    if unit == "mm":
        return int(round(num * 96.0 / 25.4))
    return int(round(num))


def _try_rsvg(src, dst, fmt, dpi, width, errors) -> bool:
    """Attempt rsvg-convert (or resvg alias). Returns True on success."""
    try:
        cmd = ["rsvg-convert", "-f", fmt, "-o", dst, src]
        if fmt == "png" and width:
            cmd.extend(["-w", str(width)])
        elif fmt == "png":
            cmd.extend(["--dpi-x", str(dpi), "--dpi-y", str(dpi)])
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except FileNotFoundError:
        errors.append("rsvg-convert not found")
    except subprocess.CalledProcessError as exc:
        errors.append(f"rsvg-convert failed: {exc}")
    return False


def _try_cairosvg(src, dst, fmt, dpi, width, errors) -> bool:
    """Attempt cairosvg. Returns True on success."""
    try:
        import cairosvg
        kwargs: dict = {"url": src, "write_to": dst, "dpi": dpi}
        if width:
            kwargs["output_width"] = width
        if fmt == "png":
            cairosvg.svg2png(**kwargs)
        elif fmt == "pdf":
            cairosvg.svg2pdf(**kwargs)
        return True
    except ImportError:
        errors.append("cairosvg not installed")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"cairosvg failed: {exc}")
    return False


def _try_inkscape(src, dst, fmt, dpi, width, errors) -> bool:
    """Attempt inkscape CLI. Returns True on success."""
    try:
        cmd = [
            "inkscape", src,
            f"--export-type={fmt}",
            f"--export-filename={dst}",
        ]
        if fmt == "png":
            cmd.append(f"--export-dpi={dpi}")
            if width:
                cmd.append(f"--export-width={width}")
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except FileNotFoundError:
        errors.append("inkscape not found")
    except subprocess.CalledProcessError as exc:
        errors.append(f"inkscape failed: {exc}")
    return False
