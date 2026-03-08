"""Utilities for building and manipulating SVGs.

This module provides a wrapper around drawsvg to make creating
scientific diagrams easier, with built-in styling and layout helpers.
"""
import math
import re
from typing import Dict, Any, Optional, Tuple

import drawsvg as draw


def _with_alpha(hex_color: str, alpha_hex: str = "33") -> str:
    """Append alpha to a 6-digit hex color.  Returns as-is for non-hex colors."""
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_color):
        return hex_color + alpha_hex
    return hex_color


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


class SVGBuilder:
    """Helper class for building styled SVGs."""

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

    # --- shapes ---------------------------------------------------------

    def add_box(
        self,
        x: float, y: float, w: float, h: float,
        text: str = "", element_id: str = "",
        color: str = "primary",
        **kwargs,
    ) -> None:
        """Add a labeled rectangular node."""
        fill = self._resolve_color(color)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        rect = draw.Rectangle(
            x - w / 2, y - h / 2, w, h,
            fill=_with_alpha(fill),
            stroke=fill,
            stroke_width=self._stroke_width(),
            rx=5, ry=5,
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
        fill = self._resolve_color(color)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        group.append(draw.Circle(
            x, y, r,
            fill=_with_alpha(fill),
            stroke=fill,
            stroke_width=self._stroke_width(),
            **kwargs,
        ))

        if text:
            group.append(draw.Text(
                text, self._font_size(),
                x=x, y=y, center=True,
                font_family=self._font_family(),
                fill=self._text_color(),
            ))

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
        fill = self._resolve_color(color)
        group = draw.Group(id=element_id) if element_id else draw.Group()

        hw, hh = w / 2, h / 2
        diamond = draw.Lines(
            x, y - hh,      # top
            x + hw, y,      # right
            x, y + hh,      # bottom
            x - hw, y,      # left
            fill=_with_alpha(fill),
            stroke=fill,
            stroke_width=self._stroke_width(),
            close=True,
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
