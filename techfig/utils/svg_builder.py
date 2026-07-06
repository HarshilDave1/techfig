"""Utilities for building and manipulating SVGs.

This module provides a wrapper around drawsvg to make creating
scientific diagrams easier, with built-in styling and layout helpers.

Supported shapes: box, circle, diamond, ellipse, triangle, line, text.
All shapes accept optional styling: stroke_dash, fill_opacity, rotation.
"""
from typing import Dict, Any, Optional, Tuple

import drawsvg as draw


# Default fill opacity for shapes — light pastel fill with solid stroke
DEFAULT_FILL_OPACITY = 0.15


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
        """Extract custom style keys from kwargs and return SVG-compatible attrs.

        Returns a new dict with SVG style attrs without mutating the input kwargs.
        If no ``fill_opacity`` is provided, the default (0.15) is applied
        so shapes get a light pastel fill with a solid stroke border.
        Pass ``default_fill_opacity=-1`` to suppress the default (e.g. for text/lines).
        """
        out: dict = {}
        if "stroke_dash" in kwargs:
            out["stroke_dasharray"] = kwargs["stroke_dash"]
        if "fill_opacity" in kwargs:
            out["fill_opacity"] = kwargs["fill_opacity"]
        elif default_fill_opacity >= 0:
            out["fill_opacity"] = default_fill_opacity
        if "stroke_opacity" in kwargs:
            out["stroke_opacity"] = kwargs["stroke_opacity"]
        # rotation handled separately via transform (not an SVG attr here)
        return out

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
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        rect = draw.Rectangle(
            x - w / 2, y - h / 2, w, h,
            fill=fill,
            stroke=fill,
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
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        group.append(draw.Circle(
            x, y, r,
            fill=fill,
            stroke=fill,
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
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        hw, hh = w / 2, h / 2
        diamond = draw.Lines(
            x, y - hh,      # top
            x + hw, y,      # right
            x, y + hh,      # bottom
            x - hw, y,      # left
            fill=fill,
            stroke=fill,
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
        style_attrs, kwargs = self._extract_style_kwargs(kwargs)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        group.append(draw.Ellipse(
            x, y, rx, ry,
            fill=fill,
            stroke=fill,
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
            stroke=fill,
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
            approx_w = len(text) * size * 0.6
            self._elements[element_id] = (x, y, approx_w, size)

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
        color = self._resolve_color(stroke_color)
        if color == stroke_color:
            color = str(self.style.get("colors", {}).get("stroke", stroke_color))

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
        color = self._resolve_color(stroke_color)
        if color == stroke_color:
            color = str(self.style.get("colors", {}).get("stroke", stroke_color))

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

    def add_line(
        self,
        x1: float, y1: float, x2: float, y2: float,
        text: str = "",
        stroke_color: str = "stroke",
        **kwargs,
    ) -> None:
        """Add a plain line (no arrowhead). Supports stroke_dash for dashed lines."""
        style_attrs, kwargs = self._extract_style_kwargs(kwargs, default_fill_opacity=-1)
        color = self._resolve_color(stroke_color)
        if color == stroke_color:
            color = str(self.style.get("colors", {}).get("stroke", stroke_color))

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
            self.drawing.append(draw.Text(
                text, self._font_size() * 0.8,
                x=mid_x, y=mid_y - 10,
                center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))


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
        color = self._resolve_color(stroke_color)
        if color == stroke_color:  # wasn't in colors dict
            color = str(self.style.get("colors", {}).get("stroke", stroke_color))

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
            self.drawing.append(draw.Text(
                text, self._font_size() * 0.8,
                x=mid_x, y=mid_y - 10,
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
        color = self._resolve_color(stroke_color)
        if color == stroke_color:
            color = str(self.style.get("colors", {}).get("stroke", stroke_color))

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
            self.drawing.append(draw.Text(
                text, self._font_size() * 0.8,
                x=mid_x, y=mid_y - 10,
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
