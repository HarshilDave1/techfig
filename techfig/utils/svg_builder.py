"""Utilities for building and manipulating SVGs.

This module provides a wrapper around drawsvg to make creating
scientific diagrams easier, with built-in styling and layout helpers.

Supported shapes: box, circle, diamond, ellipse, triangle, line, text,
callout (anchored label with leader line).
Text blocks: add_textblock for multi-line wrapped text inside a panel background.
All shapes accept optional styling: stroke_dash, fill_opacity, rotation.
"""
import logging
import re
from typing import Dict, Any, Iterable, Optional, Sequence, Tuple, Union

import drawsvg as draw

# Pillow and matplotlib are core dependencies (matplotlib>=3.8, pillow>=12.1).
# They are imported lazily inside the metrics helper so that a missing or broken
# font stack never prevents SVG generation — we fall back to the old heuristic.
from PIL import ImageFont
from techfig.styles.presets import get_style


# Default fill opacity for shapes — light pastel fill with solid stroke
DEFAULT_FILL_OPACITY = 0.15

# Module-level cache: (font_path, size) -> ImageFont.FreeTypeFont
_FONT_CACHE: Dict[Tuple[str, float], ImageFont.FreeTypeFont] = {}
# Module-level cache: family-stack-string -> resolved .ttf path (or None)
_FONT_PATH_CACHE: Dict[str, Optional[str]] = {}

# Silence matplotlib's "Font family ['Arial'] not found. Falling back" notices —
# the fallback itself is the intended behaviour and the warning is noisy.
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)


def _resolve_font_path(family_stack: str) -> Optional[str]:
    """Resolve a CSS-style font-family string (e.g. "Arial, Helvetica, sans-serif")
    to a real ``.ttf`` path via matplotlib's font_manager.

    Returns ``None`` if no font could be resolved, so callers can fall back to a
    heuristic instead of crashing.
    """
    if family_stack in _FONT_PATH_CACHE:
        return _FONT_PATH_CACHE[family_stack]

    from matplotlib import font_manager

    path: Optional[str] = None
    for fam in (f.strip().strip("'\"") for f in family_stack.split(",")):
        if not fam:
            continue
        try:
            resolved = font_manager.findfont(
                font_manager.FontProperties(family=fam),
                fallback_to_default=True,
            )
            if resolved:
                path = resolved
                break
        except Exception:
            continue

    _FONT_PATH_CACHE[family_stack] = path
    return path


def _measure_text(text: str, font_family: str, size: float) -> Optional[float]:
    """Measure the advance width of ``text`` at ``size`` px in ``font_family``.

    Returns the width in pixels, or ``None`` if the font could not be loaded
    (caller should fall back to the ``len * size * 0.6`` heuristic).
    """
    path = _resolve_font_path(font_family)
    if not path:
        return None
    cache_key = (path, size)
    font = _FONT_CACHE.get(cache_key)
    if font is None:
        try:
            font = ImageFont.truetype(path, int(round(size)))
        except Exception:
            _FONT_CACHE[cache_key] = None  # type: ignore[assignment]
            return None
        _FONT_CACHE[cache_key] = font
    if font is None:
        return None
    try:
        return float(font.getlength(text))
    except Exception:
        return None


def _text_width(text: str, font_family: str, size: float) -> float:
    """Return the pixel width of ``text``, falling back to the ``len*0.6``
    heuristic when real font metrics are unavailable."""
    measured = _measure_text(text, font_family, size)
    if measured is not None:
        return measured
    return len(text) * size * 0.6


def _boundary_intersect(
    cx: float, cy: float, w: float, h: float,
    target_x: float, target_y: float,
) -> Tuple[float, float]:
    """Find the point where a line from (cx, cy) toward (target_x, target_y)
    intersects the boundary of a rectangle centered at (cx, cy) with size w×h.
    Falls back to the center if the target is the same point.
    """
    dx = target_x - cx
    dy = target_y - cy
    if dx == 0 and dy == 0:
        return cx, cy

    half_w = w / 2
    half_h = h / 2

    # Scale factor to hit the rectangle boundary
    sx = abs(half_w / dx) if dx != 0 else float("inf")
    sy = abs(half_h / dy) if dy != 0 else float("inf")
    s = min(sx, sy)

    return cx + dx * s, cy + dy * s


def _apply_rotation(group: draw.Group, x: float, y: float, angle: float) -> None:
    """Apply a rotation transform around (x, y) if angle is non-zero."""
    if angle:
        group.args["transform"] = f"rotate({angle},{x},{y})"


class SVGBuilder:
    """Helper class for building styled SVGs.

    Shapes accept these common optional kwargs:
      - stroke_dash: str — SVG dash pattern e.g. "5,3" or "10,5,2,5"
      - fill_opacity: float — 0.0 (transparent) to 1.0 (opaque)
      - rotation: float — degrees to rotate the shape around its center
    """

    def __init__(
        self,
        width: int = 800,
        height: int = 600,
        style_config: Optional[Dict[str, Any]] = None,
    ):
        self.width = width
        self.height = height
        self.drawing = draw.Drawing(width, height, origin="center")

        # Resolve a named style preset (e.g. {"name": "nature"}) into the full
        # style dict, merging any caller-provided overrides on top. A bare dict
        # without a "name" key is used as-is (backward compatible).
        if style_config and isinstance(style_config, dict) and "name" in style_config:
            base = dict(get_style(style_config["name"]))
            for k, v in style_config.items():
                if k == "name":
                    continue
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    merged = dict(base[k])
                    merged.update(v)
                    base[k] = merged
                else:
                    base[k] = v
            self.style = base
        else:
            self.style = style_config or {
                "font_family": "Arial, Helvetica, sans-serif",
                "font_size": 14,
                "stroke": "#333333",
                "stroke_width": 2,
                "fill": "none",
                "colors": {
                    "primary": "#0072B2",
                    "secondary": "#D55E00",
                    "accent": "#009E73",
                    "background": "#FFFFFF",
                    "text": "#000000",
                },
            }

        # White background for clean PNG export
        bg = self.style.get("colors", {}).get("background", "#FFFFFF")
        self.drawing.append(
            draw.Rectangle(-width / 2, -height / 2, width, height, fill=str(bg))
        )

        # id → (x, y, w, h) for arrow connection
        self._elements: Dict[str, Tuple[float, float, float, float]] = {}

    # --- helpers --------------------------------------------------------

    def _resolve_color(self, color_key: str) -> str:
        """Resolve a semantic color name to hex, or return the value as-is."""
        return str(self.style.get("colors", {}).get(color_key, color_key))

    def _font_size(self) -> float:
        return float(str(self.style.get("font_size", 14)))

    def _font_family(self) -> str:
        return str(self.style.get("font_family", "Arial"))

    def _stroke_width(self) -> float:
        return float(str(self.style.get("stroke_width", 2)))

    def _text_color(self) -> str:
        return str(self.style.get("colors", {}).get("text", "#000000"))

    def _stroke_color(self, color_key: str = "stroke") -> str:
        """Resolve a stroke color key, falling back to the configured stroke.

        Semantic keys use the style color map; raw hex values are passed through.
        The special key ``stroke`` maps to the configured outline color.
        """
        if color_key == "stroke":
            return str(self.style.get("stroke", "#333333"))
        return self._resolve_color(color_key)

    def _extract_style_kwargs(self, kwargs: dict, default_fill_opacity: float = DEFAULT_FILL_OPACITY) -> tuple[dict, dict]:
        """Extract custom style keys from kwargs and return (style_attrs, cleaned_kwargs).

        Makes a shallow copy of kwargs internally so the caller's dict is not mutated.
        Style keys are removed from the returned cleaned_kwargs so they do not
        conflict when passed alongside style_attrs to drawsvg functions.

        If no ``fill_opacity`` is provided, the default (0.15) is applied
        so shapes get a light pastel fill with a solid stroke border.
        Pass ``default_fill_opacity=-1`` to suppress the default (e.g. for text/lines).
        """
        kw = dict(kwargs)  # shallow copy — do not mutate caller's dict
        out: dict = {}
        if "stroke_dash" in kw:
            out["stroke_dasharray"] = kw.pop("stroke_dash")
        if "fill_opacity" in kw:
            out["fill_opacity"] = kw.pop("fill_opacity")
        elif default_fill_opacity >= 0:
            out["fill_opacity"] = default_fill_opacity
        if "stroke_opacity" in kw:
            out["stroke_opacity"] = kw.pop("stroke_opacity")
        # rotation handled separately via transform
        kw.pop("rotation", None)
        return out, kw

    def _append_def(self, element: Any) -> Any:
        """Register an SVG def element on the drawing and return it."""
        self.drawing.append_def(element)
        return element

    @staticmethod
    def _normalize_stops(
        stops: Iterable[Union[Sequence[Any], dict]],
    ) -> list[tuple[Any, Any, Any | None]]:
        normalized: list[tuple[Any, Any, Any | None]] = []
        for stop in stops:
            if isinstance(stop, dict):
                offset = stop["offset"]
                color = stop["color"]
                opacity = stop.get("opacity")
            else:
                if len(stop) < 2:
                    raise ValueError("Gradient stops must provide at least offset and color")
                offset = stop[0]
                color = stop[1]
                opacity = stop[2] if len(stop) > 2 else None
            normalized.append((offset, color, opacity))
        return normalized

    def add_def(self, definition: Any) -> Any:
        """Add a raw drawsvg definition object to <defs>."""
        return self._append_def(definition)

    def add_linear_gradient(
        self,
        gradient_id: str,
        stops: Iterable[Union[Sequence[Any], dict]],
        x1: float = 0,
        y1: float = 0,
        x2: float = 1,
        y2: float = 0,
        gradient_units: str = "userSpaceOnUse",
        **kwargs,
    ) -> draw.LinearGradient:
        """Create and register a linear gradient definition."""
        gradient = draw.LinearGradient(x1, y1, x2, y2, gradientUnits=gradient_units, id=gradient_id, **kwargs)
        for offset, color, opacity in self._normalize_stops(stops):
            gradient.add_stop(offset, color, opacity=opacity)
        return self._append_def(gradient)

    def add_radial_gradient(
        self,
        gradient_id: str,
        stops: Iterable[Union[Sequence[Any], dict]],
        cx: float = 0.5,
        cy: float = 0.5,
        r: float = 0.5,
        fy: Optional[float] = None,
        gradient_units: str = "userSpaceOnUse",
        **kwargs,
    ) -> draw.RadialGradient:
        """Create and register a radial gradient definition."""
        gradient = draw.RadialGradient(cx, cy, r, gradientUnits=gradient_units, fy=fy, id=gradient_id, **kwargs)
        for offset, color, opacity in self._normalize_stops(stops):
            gradient.add_stop(offset, color, opacity=opacity)
        return self._append_def(gradient)

    def add_pattern(
        self,
        pattern_id: str,
        width: float,
        height: float,
        x: Optional[float] = None,
        y: Optional[float] = None,
        pattern_units: str = "userSpaceOnUse",
        elements: Optional[Iterable[Any]] = None,
        **kwargs,
    ) -> draw.Pattern:
        """Create and register a repeating pattern definition.

        The optional ``elements`` iterable can be used to seed the pattern body
        with drawsvg elements (rectangles, lines, shapes, etc.).
        """
        pattern = draw.Pattern(width, height, x=x, y=y, patternUnits=pattern_units, id=pattern_id, **kwargs)
        for element in elements or ():
            pattern.append(element)
        return self._append_def(pattern)

    def add_filter(
        self,
        filter_id: str,
        elements: Optional[Iterable[Any]] = None,
        **kwargs,
    ) -> draw.Filter:
        """Create and register an SVG filter definition.

        ``elements`` may contain drawsvg ``FilterItem`` nodes such as
        ``feGaussianBlur`` or ``feDropShadow`` children.
        """
        filter_def = draw.Filter(id=filter_id, **kwargs)
        for element in elements or ():
            filter_def.append(element)
        return self._append_def(filter_def)

    # --- shapes ---------------------------------------------------------

    def add_box(
        self,
        x: float, y: float, w: float, h: float,
        text: str = "", element_id: str = "",
        color: str = "primary",
        **kwargs,
    ) -> None:
        """Add a labeled rectangular node."""
        rotation = kwargs.get("rotation", 0)
        fill = self._resolve_color(color)
        stroke = self._stroke_color(kwargs.pop("stroke_color", "stroke"))
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        rect = draw.Rectangle(
            x - w / 2, y - h / 2, w, h,
            fill=fill,
            stroke=stroke,
            stroke_width=self._stroke_width(),
            rx=5, ry=5,
            **style_attrs,
            **kwargs,
        )
        group.append(rect)

        if text:
            group.append(draw.Text(
                text, self._font_size(),
                x=x, y=y, center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, w, h)

    def add_circle(
        self,
        x: float, y: float, r: float,
        text: str = "", element_id: str = "",
        color: str = "secondary",
        **kwargs,
    ) -> None:
        """Add a labeled circular node."""
        rotation = kwargs.get("rotation", 0)
        fill = self._resolve_color(color)
        stroke = self._stroke_color(kwargs.pop("stroke_color", "stroke"))
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        group.append(draw.Circle(
            x, y, r,
            fill=fill,
            stroke=stroke,
            stroke_width=self._stroke_width(),
            **style_attrs,
            **kwargs,
        ))

        if text:
            group.append(draw.Text(
                text, self._font_size(),
                x=x, y=y, center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, r * 2, r * 2)

    def add_diamond(
        self,
        x: float, y: float, w: float, h: float,
        text: str = "", element_id: str = "",
        color: str = "accent",
        **kwargs,
    ) -> None:
        """Add a labeled diamond (decision) node."""
        rotation = kwargs.get("rotation", 0)
        fill = self._resolve_color(color)
        stroke = self._stroke_color(kwargs.pop("stroke_color", "stroke"))
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        hw, hh = w / 2, h / 2
        diamond = draw.Lines(
            x, y - hh,      # top
            x + hw, y,      # right
            x, y + hh,      # bottom
            x - hw, y,      # left
            fill=fill,
            stroke=stroke,
            stroke_width=self._stroke_width(),
            close=True,
            **style_attrs,
            **kwargs,
        )
        group.append(diamond)

        if text:
            group.append(draw.Text(
                text, self._font_size() * 0.85,
                x=x, y=y, center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, w, h)

    def add_ellipse(
        self,
        x: float, y: float, rx: float, ry: float,
        text: str = "", element_id: str = "",
        color: str = "primary",
        **kwargs,
    ) -> None:
        """Add a labeled elliptical node (lenses, ovals, etc.)."""
        rotation = kwargs.get("rotation", 0)
        fill = self._resolve_color(color)
        stroke = self._stroke_color(kwargs.pop("stroke_color", "stroke"))
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        group.append(draw.Ellipse(
            x, y, rx, ry,
            fill=fill,
            stroke=stroke,
            stroke_width=self._stroke_width(),
            **style_attrs,
            **kwargs,
        ))

        if text:
            group.append(draw.Text(
                text, self._font_size(),
                x=x, y=y, center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, rx * 2, ry * 2)

    def add_triangle(
        self,
        x: float, y: float, w: float, h: float,
        text: str = "", element_id: str = "",
        color: str = "accent",
        direction: str = "up",
        **kwargs,
    ) -> None:
        """Add a labeled triangular node.

        ``direction``: 'up', 'down', 'left', 'right' — which way the apex points.
        """
        rotation = kwargs.get("rotation", 0)
        fill = self._resolve_color(color)
        stroke = self._stroke_color(kwargs.pop("stroke_color", "stroke"))
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        hw, hh = w / 2, h / 2
        points = {
            "up":    (x, y - hh, x - hw, y + hh, x + hw, y + hh),
            "down":  (x, y + hh, x - hw, y - hh, x + hw, y - hh),
            "left":  (x - hw, y, x + hw, y - hh, x + hw, y + hh),
            "right": (x + hw, y, x - hw, y - hh, x - hw, y + hh),
        }
        pts = points.get(direction, points["up"])

        tri = draw.Lines(
            *pts,
            fill=fill,
            stroke=stroke,
            stroke_width=self._stroke_width(),
            close=True,
            **style_attrs,
            **kwargs,
        )
        group.append(tri)

        if text:
            group.append(draw.Text(
                text, self._font_size() * 0.85,
                x=x, y=y, center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, w, h)

    def add_component(
        self,
        x: float, y: float, w: float, h: float,
        raw_svg: str, text: str = "", element_id: str = "",
        **kwargs,
    ) -> None:
        """Add a raw SVG component (e.g. from the component library).

        The component is scaled and translated to fit within w x h,
        centered at (x, y). Text label is drawn below it.
        """
        group = draw.Group(id=element_id) if element_id else draw.Group()

        cx = x - w / 2
        cy = y - h / 2
        wrapper = f'<svg x="{cx}" y="{cy}" width="{w}" height="{h}">{raw_svg}</svg>'
        raw_elem = draw.Raw(wrapper)
        group.append(raw_elem)

        if text:
            group.append(draw.Text(
                text, self._font_size(),
                x=x, y=y + h / 2 + self._font_size(), center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, w, h)

    def add_plot(
        self,
        x: float, y: float, w: float, h: float,
        chart_spec: Dict[str, Any],
        text: str = "",
        element_id: str = "",
        style_name: str = "nature",
        **kwargs,
    ) -> None:
        """Render a matplotlib chart inline and embed it in the SVG.

        The chart is rendered to an SVG string via the figures engine
        (``create_chart`` with the Agg backend) and embedded as a nested
        ``<svg>`` element scaled to fit ``w x h``, centered at ``(x, y)``.
        This lets a diagram contain real data plots as first-class elements
        that other elements can connect to with arrows.

        Args:
            x, y: Center coordinates of the plot panel.
            w, h: Width and height of the plot panel (SVG user units).
            chart_spec: Dict forwarded to ``create_chart``. Required keys:
                ``type`` (chart type), ``data`` (path, DataFrame, dict, or
                list). Optional: ``x_col``, ``y_col``, ``hue_col``,
                ``title``, ``xlabel``, ``ylabel``, ``style_overrides``.
            text: Optional caption drawn below the plot panel.
            element_id: If set, registers the panel bounds so arrows can
                connect to it.
            style_name: Base style preset for the embedded chart.
            **kwargs: Reserved for future styling (currently unused).
        """
        # Local import to avoid a matplotlib import at module load time
        # for users who never use the plot element.
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from techfig.engines.figures import create_chart, CHART_TYPES

        chart_type = chart_spec.get("type", "bar")
        if chart_type not in CHART_TYPES:
            raise ValueError(
                f"Unsupported plot chart type: '{chart_type}'. "
                f"Supported types: {', '.join(CHART_TYPES)}"
            )

        chart_data = chart_spec.get("data")
        if chart_data is None:
            raise ValueError("plot element requires 'data' in chart_spec")

        # Render onto our own figure/ax so we control the SVG output and
        # can close the figure explicitly (create_chart with output_path=""
        # and no ax leaks its figure and returns "").
        fig, ax = plt.subplots()
        create_chart(
            data=chart_data,
            chart_type=chart_type,
            output_path="",
            title=chart_spec.get("title", ""),
            x_col=chart_spec.get("x_col"),
            y_col=chart_spec.get("y_col"),
            hue_col=chart_spec.get("hue_col"),
            xlabel=chart_spec.get("xlabel"),
            ylabel=chart_spec.get("ylabel"),
            style_name=chart_spec.get("style", style_name),
            style_overrides=chart_spec.get("style_overrides"),
            ax=ax,
        )
        buf = io.StringIO()
        fig.savefig(buf, format="svg", bbox_inches="tight")
        plt.close(fig)
        raw_svg = buf.getvalue()

        # Strip the outer <?xml ...?> and <!DOCTYPE> declarations.
        # Then pull the inner SVG content into a transformed group so it
        # behaves like a native diagram element when embedded.
        inner = re.sub(r"<\?xml.*?\?>\s*", "", raw_svg, count=1, flags=re.DOTALL)
        inner = re.sub(r"<!DOCTYPE.*?>\s*", "", inner, count=1, flags=re.DOTALL)
        inner = inner.strip()

        viewbox = re.search(r'viewBox="([^"]+)"', inner)
        if viewbox:
            _, _, vb_w, vb_h = (float(v) for v in viewbox.group(1).split())
        else:
            vb_w, vb_h = w, h
        scale_x = w / vb_w if vb_w else 1.0
        scale_y = h / vb_h if vb_h else 1.0

        svg_open = re.search(r"<svg[^>]*>", inner)
        if not svg_open:
            raise ValueError("matplotlib plot did not produce an SVG root")
        inner_body = inner[svg_open.end():]
        inner_body = re.sub(r"</svg>\s*$", "", inner_body, count=1)

        group = draw.Group(id=element_id) if element_id else draw.Group()

        cx = x - w / 2
        cy = y - h / 2
        wrapper = f'<g transform="translate({cx},{cy}) scale({scale_x},{scale_y})">{inner_body}</g>'
        group.append(draw.Raw(wrapper))

        if text:
            group.append(draw.Text(
                text, self._font_size(),
                x=x, y=y + h / 2 + self._font_size(), center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, w, h)

    def add_text(
        self,
        x: float, y: float, text: str,
        element_id: str = "",
        font_size: Optional[float] = None,
        color: str = "text",
        **kwargs,
    ) -> None:
        """Add a free-floating text label (no shape behind it)."""
        rotation = kwargs.pop("rotation", 0)
        _ = self._extract_style_kwargs(kwargs, default_fill_opacity=-1)  # no fill-opacity for text
        fill = self._resolve_color(color)
        size = font_size or self._font_size()
        group = draw.Group(id=element_id) if element_id else draw.Group()

        group.append(draw.Text(
            text, size,
            x=x, y=y, center=True,
            font_family=self._font_family(),
            fill=fill,
            **kwargs,
        ))

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            approx_w = _text_width(text, self._font_family(), size)
            self._elements[element_id] = (x, y, approx_w, size)

    def add_textblock(
        self,
        x: float, y: float, w: float, h: float,
        text: str, element_id: str = "",
        color: str = "primary",
        align: str = "left",
        padding: float = 12.0,
        line_height: float = 1.3,
        font_size: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Add a multi-line text block with a panel (rounded-rectangle) background.

        The text is word-wrapped to fit ``w - 2*padding`` using an approximate
        glyph width of ``0.6 * font_size``. Explicit ``\\n`` newlines in ``text``
        are preserved. Lines are top-aligned within the panel and left/center/right
        aligned horizontally per ``align``.

        Args:
            x, y: Center of the panel.
            w, h: Panel width and height.
            text: Body text. Newlines start a new line; long lines are wrapped.
            element_id: Optional id (registered for arrow connections).
            color: Semantic color key (or hex) for the panel fill/stroke.
            align: "left", "center", or "right" text alignment inside the panel.
            padding: Inner padding between panel edge and text (px).
            line_height: Line height multiplier of font_size.
            font_size: Override style font_size for this block.
            **kwargs: Accepts stroke_dash, fill_opacity, stroke_opacity, rotation.
        """
        rotation = kwargs.get("rotation", 0)
        fill = self._resolve_color(color)
        size = font_size or self._font_size()
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        # 1. Panel background (rounded rect, light fill + colored stroke).
        panel = draw.Rectangle(
            x - w / 2, y - h / 2, w, h,
            fill=fill,
            stroke=fill,
            stroke_width=self._stroke_width(),
            rx=6, ry=6,
            **style_attrs,
            **kwargs,
        )
        group.append(panel)

        # 2. Word-wrap text to the available width.
        max_chars = max(1, int((w - 2 * padding) / (size * 0.6)))
        wrapped: list[str] = []
        for raw_line in text.split("\n"):
            if not raw_line.strip():
                wrapped.append("")
                continue
            words = raw_line.split()
            cur = ""
            for word in words:
                candidate = word if not cur else f"{cur} {word}"
                if len(candidate) > max_chars and cur:
                    wrapped.append(cur)
                    cur = word
                else:
                    cur = candidate
            wrapped.append(cur)

        # 3. Stack the wrapped lines vertically (top-aligned within panel).
        line_dy = size * line_height
        total_h = len(wrapped) * line_dy
        top_y = y - h / 2 + padding + size / 2
        # Shift so the block is vertically centered when it's shorter than h.
        if total_h < h - 2 * padding:
            top_y += ((h - 2 * padding) - total_h) / 2

        anchor = {"left": "start", "center": "middle", "right": "end"}[align]
        if align == "left":
            tx = x - w / 2 + padding
        elif align == "right":
            tx = x + w / 2 - padding
        else:
            tx = x

        for i, line in enumerate(wrapped):
            if line:
                group.append(draw.Text(
                    line, size,
                    x=tx, y=top_y + i * line_dy,
                    font_family=self._font_family(),
                    fill=self._text_color(),
                    text_anchor=anchor,
                    dominant_baseline="central",
                ))

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, w, h)

    def add_line(
        self,
        x1: float, y1: float, x2: float, y2: float,
        text: str = "",
        stroke_color: str = "stroke",
        **kwargs,
    ) -> None:
        """Add a plain line (no arrowhead). Supports stroke_dash for dashed lines."""
        style_attrs, kwargs = self._extract_style_kwargs(kwargs, default_fill_opacity=-1)
        label_y_override = kwargs.pop("label_y_override", None)
        color = self._stroke_color(stroke_color)

        self.drawing.append(draw.Line(
            x1, y1, x2, y2,
            stroke=color,
            stroke_width=self._stroke_width(),
            **style_attrs,
            **kwargs,
        ))

        if text:
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            label_y = label_y_override if label_y_override is not None else mid_y - 10
            self.drawing.append(draw.Text(
                text, self._font_size() * 0.8,
                x=mid_x, y=label_y,
                center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

    # --- free-form arrows and paths (first-class elements) -------------

    def add_arrow_xy(
        self,
        x1: float, y1: float, x2: float, y2: float,
        text: str = "",
        stroke_color: str = "stroke",
        curve: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Add a standalone arrow by explicit coordinates (not element ids).

        Unlike ``add_arrow`` (which connects two named elements), this draws
        an arrow between two absolute canvas points. Useful for free-form
        annotations, leader lines, and paths that don't anchor to a shape.

        ``curve``: optional quadratic-bezier curvature. Positive bows the
        arrow to the right of the start→end direction, negative to the left.
        """
        style_attrs, kwargs = self._extract_style_kwargs(kwargs, default_fill_opacity=-1)
        color = self._stroke_color(stroke_color)

        arrow_marker = draw.Marker(-0.1, -0.5, 0.9, 0.5, scale=8, orient="auto")
        arrow_marker.append(
            draw.Lines(-0.1, -0.5, -0.1, 0.5, 0.9, 0, fill=color, close=True)  # type: ignore
        )

        path = draw.Path(
            stroke=color,
            stroke_width=self._stroke_width(),
            fill="none",
            marker_end=arrow_marker,
            **style_attrs,
            **kwargs,
        )
        path.M(x1, y1)
        if curve:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            dx, dy = x2 - x1, y2 - y1
            # perpendicular offset for the control point
            nx, ny = -dy, dx
            length = (nx * nx + ny * ny) ** 0.5
            if length:
                nx, ny = nx / length, ny / length
            cx = mx + nx * curve
            cy = my + ny * curve
            path.Q(cx, cy, x2, y2)
        else:
            path.L(x2, y2)
        self.drawing.append(path)

        if text:
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            self.drawing.append(draw.Text(
                text, self._font_size() * 0.8,
                x=mid_x, y=mid_y - 10,
                center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

    def add_path(
        self,
        points: list,
        text: str = "",
        stroke_color: str = "stroke",
        closed: bool = False,
        arrowhead: str = "none",
        **kwargs,
    ) -> None:
        """Add a multi-segment path from a list of points.

        ``points``: list of (x, y) tuples; at least 2 points required.
        Each point may optionally be a 3-tuple (x, y, command) where
        command is one of "M" (moveto), "L" (lineto), "C" (cubic Bezier
        — needs two extra control points, so the next two list entries
        are consumed as controls), or "Q" (quadratic — needs one extra
        control point). Defaults to "M" for the first point and "L" for
        the rest.

        ``closed``: if True, closes the path (Z) — useful for outlines.
        ``arrowhead``: "none" (default), "end", "start", or "both".
        """
        if len(points) < 2:
            raise ValueError("add_path requires at least 2 points")

        style_attrs, kwargs = self._extract_style_kwargs(kwargs, default_fill_opacity=-1)
        color = self._stroke_color(stroke_color)

        marker = None
        if arrowhead in ("end", "both"):
            marker = draw.Marker(-0.1, -0.5, 0.9, 0.5, scale=8, orient="auto")
            marker.append(
                draw.Lines(-0.1, -0.5, -0.1, 0.5, 0.9, 0, fill=color, close=True)  # type: ignore
            )

        start_marker = None
        if arrowhead in ("start", "both"):
            start_marker = draw.Marker(0.9, -0.5, -0.1, 0.5, scale=8, orient="auto-start-reverse")
            start_marker.append(
                draw.Lines(0.9, -0.5, 0.9, 0.5, -0.1, 0, fill=color, close=True)  # type: ignore
            )

        fill = "none" if not closed else color
        path = draw.Path(
            stroke=color,
            stroke_width=self._stroke_width(),
            fill=fill,
            marker_end=marker,
            marker_start=start_marker,
            **style_attrs,
            **kwargs,
        )

        i = 0
        first = True
        while i < len(points):
            pt = points[i]
            if len(pt) == 3:
                x, y, cmd = pt
                cmd = cmd.upper()
            else:
                x, y = pt[0], pt[1]
                cmd = "M" if first else "L"

            if cmd == "M":
                path.M(x, y)
                i += 1
            elif cmd == "L":
                path.L(x, y)
                i += 1
            elif cmd == "Q":
                cx, cy = points[i + 1][0], points[i + 1][1]
                path.Q(cx, cy, x, y)
                i += 2
            elif cmd == "C":
                c1x, c1y = points[i + 1][0], points[i + 1][1]
                c2x, c2y = points[i + 2][0], points[i + 2][1]
                path.C(c1x, c1y, c2x, c2y, x, y)
                i += 3
            else:
                raise ValueError(f"Unknown path command: {cmd}")
            first = False

        if closed:
            path.Z()

        self.drawing.append(path)

        if text:
            xs = [p[0] for p in points if len(p) >= 2]
            ys = [p[1] for p in points if len(p) >= 2]
            mid_x = sum(xs) / len(xs)
            mid_y = sum(ys) / len(ys)
            self.drawing.append(draw.Text(
                text, self._font_size() * 0.8,
                x=mid_x, y=mid_y - 10,
                center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

    def add_callout(
        self,
        x: float, y: float, text: str,
        anchor_x: Optional[float] = None,
        anchor_y: Optional[float] = None,
        anchor_id: str = "",
        element_id: str = "",
        color: str = "primary",
        font_size: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Add a callout: a text label anchored to a point via a leader line.

        The label sits at (x, y) with an optional anchor dot at the anchor
        point, and a thin leader line drawn from the anchor to the label.

        Args:
            x, y: Label center position.
            text: Label text.
            anchor_x, anchor_y: The point the callout refers to. If both are
                None and ``anchor_id`` references a registered element, the
                anchor is the boundary point of that element nearest the label.
                If no anchor is provided at all, no leader line or dot is
                drawn (degenerates to a plain text label).
            anchor_id: Optional element id whose boundary is the anchor.
            element_id: Optional id for this callout element.
            color: Semantic color name or hex for the leader line and label.
            font_size: Override the default font size.

        Common style kwargs (stroke_dash, fill_opacity, stroke_opacity,
        rotation) are accepted; stroke_dash applies to the leader line and
        rotation rotates the label around (x, y).
        """
        rotation = kwargs.get("rotation", 0)
        style_attrs, kwargs = self._extract_style_kwargs(kwargs, default_fill_opacity=-1)
        stroke = self._resolve_color(color)
        text_fill = self._text_color()

        group = draw.Group(id=element_id) if element_id else draw.Group()

        # Resolve the anchor point
        ax: Optional[float] = None
        ay: Optional[float] = None
        if anchor_x is not None and anchor_y is not None:
            ax, ay = float(anchor_x), float(anchor_y)
        elif anchor_id and anchor_id in self._elements:
            fx, fy, fw, fh = self._elements[anchor_id]
            ax, ay = _boundary_intersect(fx, fy, fw, fh, x, y)

        # Draw leader line + anchor dot when an anchor was resolved
        if ax is not None and ay is not None:
            # Avoid a zero-length leader (label directly on anchor)
            if abs(ax - x) > 0.5 or abs(ay - y) > 0.5:
                leader = draw.Line(
                    ax, ay, x, y,
                    stroke=stroke,
                    stroke_width=max(1.0, self._stroke_width() * 0.6),
                    **style_attrs,
                )
                group.append(leader)
            # Small filled anchor dot at the anchor point
            group.append(draw.Circle(
                ax, ay, max(2.0, self._stroke_width() * 0.8),
                fill=stroke,
                stroke=stroke,
                stroke_width=1,
            ))

        # Label text
        size = font_size or self._font_size()
        group.append(draw.Text(
            text, size,
            x=x, y=y, center=True,
            font_family=self._font_family(),
            fill=text_fill,
            **kwargs,
        ))

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            approx_w = len(text) * size * 0.6
            self._elements[element_id] = (x, y, approx_w, size)

    def add_legend(
        self,
        x: float, y: float, w: float, h: float,
        entries: list,
        element_id: str = "",
        title: str = "",
        color: str = "stroke",
        swatch_shape: str = "rect",
        **kwargs,
    ) -> None:
        """Add a bordered legend panel with swatch + label rows.

        Args:
            x, y: Center of the panel.
            w, h: Panel size.
            entries: List of dicts, each ``{"label": str, "color": str}`` where
                ``color`` may be a semantic key (``primary``) or a hex value.
                An optional ``swatch_shape`` per-entry overrides the panel default
                (``"rect"`` or ``"circle"``).
            element_id: Optional id (registers the panel bounds for connections).
            title: Optional heading drawn at the top of the panel.
            color: Border color (semantic key or hex).
            swatch_shape: Default swatch shape — ``"rect"`` or ``"circle"``.
            **kwargs: Accepts ``stroke_dash``, ``fill_opacity``, ``rotation`` for
                the panel border (same conventions as other shapes).
        """
        rotation = kwargs.get("rotation", 0)
        border_color = self._resolve_color(color)
        if border_color == color and color != "stroke":
            # not a semantic key — use as-is
            pass
        style_attrs, kwargs = self._extract_style_kwargs(kwargs, default_fill_opacity=-1)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        # Panel background (subtle fill) + border
        panel_fill = self.style.get("colors", {}).get("background", "#FFFFFF")
        panel_opacity = style_attrs.pop("fill_opacity", 0.9)
        rx = 4
        group.append(draw.Rectangle(
            x - w / 2, y - h / 2, w, h,
            fill=panel_fill,
            fill_opacity=panel_opacity,
            stroke=border_color,
            stroke_width=self._stroke_width(),
            rx=rx, ry=rx,
            **style_attrs,
            **kwargs,
        ))

        # Layout: optional title row, then one row per entry.
        font_size = self._font_size()
        title_size = font_size * 1.0
        row_height = font_size * 1.6
        pad = font_size * 0.8
        swatch_size = font_size * 0.9
        swatch_gap = swatch_size + pad * 0.6

        top = y - h / 2 + pad
        cursor_y = top

        if title:
            group.append(draw.Text(
                title, title_size,
                x=x - w / 2 + pad, y=cursor_y + title_size * 0.35,
                font_family=self._font_family(),
                fill=self._text_color(),
                font_weight="bold",
            ))
            cursor_y += title_size * 1.4

        label_x = x - w / 2 + pad + swatch_gap
        text_color = self._text_color()

        for entry in entries:
            label = str(entry.get("label", ""))
            swatch_color = self._resolve_color(entry.get("color", "primary"))
            shape = entry.get("swatch_shape", swatch_shape)
            swatch_cx = x - w / 2 + pad + swatch_size / 2
            swatch_cy = cursor_y + font_size * 0.35

            if shape == "circle":
                group.append(draw.Circle(
                    swatch_cx, swatch_cy, swatch_size / 2,
                    fill=swatch_color,
                    stroke=swatch_color,
                    stroke_width=1,
                ))
            else:  # rect
                group.append(draw.Rectangle(
                    swatch_cx - swatch_size / 2, swatch_cy - swatch_size / 2,
                    swatch_size, swatch_size,
                    fill=swatch_color,
                    stroke=swatch_color,
                    stroke_width=1,
                    rx=2, ry=2,
                ))

            if label:
                group.append(draw.Text(
                    label, font_size,
                    x=label_x, y=cursor_y + font_size * 0.35,
                    font_family=self._font_family(),
                    fill=text_color,
                ))

            cursor_y += row_height

        _apply_rotation(group, x, y, rotation)
        self.drawing.append(group)
        if element_id:
            self._elements[element_id] = (x, y, w, h)


    # --- connections ----------------------------------------------------

    def add_arrow(
        self,
        from_id: str, to_id: str,
        text: str = "",
        stroke_color: str = "stroke",
        route: str = "straight",
        **kwargs,
    ) -> None:
        """Draw a connecting arrow between two named elements.

        Arrow endpoints are computed at the *boundary* of each element's
        bounding box, not at the center.
        """
        if from_id not in self._elements or to_id not in self._elements:
            raise ValueError(f"Cannot connect '{from_id}' → '{to_id}': element not found")

        fx, fy, fw, fh = self._elements[from_id]
        tx, ty, tw, th = self._elements[to_id]

        # Compute boundary intersection points
        start = _boundary_intersect(fx, fy, fw, fh, tx, ty)
        end = _boundary_intersect(tx, ty, tw, th, fx, fy)

        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        label_y_override = kwargs.pop("label_y_override", None)
        color = self._stroke_color(stroke_color)

        arrow_marker = draw.Marker(-0.1, -0.5, 0.9, 0.5, scale=8, orient="auto")
        arrow_marker.append(
            draw.Lines(-0.1, -0.5, -0.1, 0.5, 0.9, 0, fill=color, close=True)  # type: ignore
        )

        path = draw.Path(
            stroke=color,
            stroke_width=self._stroke_width(),
            fill="none",
            marker_end=arrow_marker,
            **style_attrs,
            **kwargs,
        )

        if route == "straight":
            path.M(*start).L(*end)
        elif route == "orthogonal":
            mid_x = (start[0] + end[0]) / 2
            path.M(*start).L(mid_x, start[1]).L(mid_x, end[1]).L(*end)

        self.drawing.append(path)

        if text:
            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2
            label_y = label_y_override if label_y_override is not None else mid_y - 10
            self.drawing.append(draw.Text(
                text, self._font_size() * 0.8,
                x=mid_x, y=label_y,
                center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

    def add_connection(
        self,
        from_id: str, to_id: str,
        text: str = "",
        stroke_color: str = "stroke",
        route: str = "straight",
        **kwargs,
    ) -> None:
        """Draw a plain line (no arrow) between two named elements."""
        if from_id not in self._elements or to_id not in self._elements:
            raise ValueError(f"Cannot connect '{from_id}' → '{to_id}': element not found")

        fx, fy, fw, fh = self._elements[from_id]
        tx, ty, tw, th = self._elements[to_id]
        start = _boundary_intersect(fx, fy, fw, fh, tx, ty)
        end = _boundary_intersect(tx, ty, tw, th, fx, fy)

        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        label_y_override = kwargs.pop("label_y_override", None)
        color = self._stroke_color(stroke_color)

        path = draw.Path(
            stroke=color,
            stroke_width=self._stroke_width(),
            fill="none",
            **style_attrs,
            **kwargs,
        )

        if route == "straight":
            path.M(*start).L(*end)
        elif route == "orthogonal":
            mid_x = (start[0] + end[0]) / 2
            path.M(*start).L(mid_x, start[1]).L(mid_x, end[1]).L(*end)

        self.drawing.append(path)

        if text:
            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2
            label_y = label_y_override if label_y_override is not None else mid_y - 10
            self.drawing.append(draw.Text(
                text, self._font_size() * 0.8,
                x=mid_x, y=label_y,
                center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

    # --- output ---------------------------------------------------------

    def save(self, output_path: str) -> None:
        """Save the diagram to a file (.svg or .png)."""
        if output_path.endswith(".svg"):
            self.drawing.save_svg(output_path)
        elif output_path.endswith(".png"):
            self.drawing.save_png(output_path)
        else:
            raise ValueError(
                f"Unsupported output format for '{output_path}'. Use .svg or .png"
            )

    def get_svg_string(self) -> str:
        """Return the raw SVG markup."""
        return self.drawing.as_svg()
