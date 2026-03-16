"""Diagram engine to generate scientific schematics and flowcharts.

This engine processes high-level diagram descriptions (lists of nodes and edges)
and uses the SVGBuilder to generate the final graphic.

Supported shapes: box, circle, diamond, ellipse, triangle.
Standalone elements: text (free-floating labels), line (plain lines).
Connections: arrow (with arrowhead), connection (plain line between elements).
"""
from typing import Dict, List, Any, Optional
from pathlib import Path

from techfig.utils.svg_builder import SVGBuilder
from techfig.components import get_registry
from techfig.components.standard import render_schemdraw_component

# Shapes the engine can render as nodes
SUPPORTED_SHAPES = ("box", "circle", "diamond", "ellipse", "triangle")


def create_diagram(
    elements: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
    output_path: str,
    width: int = 1200,
    height: int = 800,
    style_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a diagram from element and connection definitions.

    This is the enhanced version of create_flowchart, supporting all
    shape types, free text labels, plain lines, and styling options.

    Args:
        elements: List of element dicts. Each must have ``type`` and
            type-specific fields:
            - shape nodes: ``id``, ``x``, ``y`` + shape-specific (w/h, r, rx/ry)
            - ``text``: ``x``, ``y``, ``text`` + optional ``font_size``
            - ``line``: ``x1``, ``y1``, ``x2``, ``y2``
            All can include: ``color``, ``stroke_dash``, ``fill_opacity``, ``rotation``
        connections: List of connection dicts with ``from``, ``to``, and optionally
            ``label``, ``route`` (straight|orthogonal), ``color``, ``style`` (arrow|line),
            ``stroke_dash``.
        output_path: Where to save the SVG file.
        width: Canvas width in pixels.
        height: Canvas height in pixels.
        style_config: Optional style dict.

    Returns:
        Absolute path to the generated file.
    """
    builder = SVGBuilder(width=width, height=height, style_config=style_config)

    # 1. Process all elements
    for el in elements:
        el_type = el.get("type", "box")
        el_id = el.get("id", "")
        text = el.get("text", "")
        color = el.get("color", "primary")

        # Collect optional style kwargs
        style_kw: Dict[str, Any] = {}
        for key in ("stroke_dash", "fill_opacity", "stroke_opacity", "rotation"):
            if key in el:
                style_kw[key] = el[key]

        if el_type == "box":
            builder.add_box(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("w", 120)), float(el.get("h", 60)),
                text=text, element_id=el_id, color=color, **style_kw,
            )

        elif el_type == "circle":
            builder.add_circle(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("r", 40)),
                text=text, element_id=el_id, color=color, **style_kw,
            )

        elif el_type == "diamond":
            builder.add_diamond(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("w", 100)), float(el.get("h", 80)),
                text=text, element_id=el_id, color=color, **style_kw,
            )

        elif el_type == "ellipse":
            builder.add_ellipse(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("rx", 60)), float(el.get("ry", 30)),
                text=text, element_id=el_id, color=color, **style_kw,
            )

        elif el_type == "triangle":
            builder.add_triangle(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("w", 80)), float(el.get("h", 70)),
                text=text, element_id=el_id, color=color,
                direction=el.get("direction", "up"), **style_kw,
            )

        elif el_type == "text":
            builder.add_text(
                float(el.get("x", 0)), float(el.get("y", 0)),
                text=text, element_id=el_id,
                font_size=el.get("font_size"),
                color=color, **style_kw,
            )

        elif el_type == "line":
            builder.add_line(
                float(el.get("x1", 0)), float(el.get("y1", 0)),
                float(el.get("x2", 100)), float(el.get("y2", 0)),
                text=text, stroke_color=color, **style_kw,
            )

        else:
            # Try component registry for custom/lab-folder components
            registry = get_registry()
            meta = registry.get(el_type)
            if meta:
                x = float(el.get("x", 0))
                y = float(el.get("y", 0))
                w = float(el.get("w", 100))
                h = float(el.get("h", 100))
                raw_svg = ""
                if meta.source == "standard":
                    raw_svg = render_schemdraw_component(el_type)
                elif meta.file_path:
                    try:
                        with open(meta.file_path, "r", encoding="utf-8") as f:
                            raw_svg = f.read()
                    except Exception:
                        pass
                builder.add_component(x, y, w, h, raw_svg, text=text, element_id=el_id)
            else:
                raise ValueError(
                    f"Unknown element type: '{el_type}'. "
                    f"Supported: {', '.join(SUPPORTED_SHAPES)}, text, line, or any registered component."
                )


    # 2. Draw connections
    for conn in connections:
        from_id = conn.get("from")
        to_id = conn.get("to")
        if not from_id or not to_id:
            continue

        style = conn.get("style", "arrow")  # "arrow" or "line"
        conn_kw: Dict[str, Any] = {}
        if "stroke_dash" in conn:
            conn_kw["stroke_dash"] = conn["stroke_dash"]

        if style == "line":
            builder.add_connection(
                from_id, to_id,
                text=conn.get("label", ""),
                route=conn.get("route", "straight"),
                stroke_color=conn.get("color", "stroke"),
                **conn_kw,
            )
        else:
            builder.add_arrow(
                from_id, to_id,
                text=conn.get("label", ""),
                route=conn.get("route", "straight"),
                stroke_color=conn.get("color", "stroke"),
                **conn_kw,
            )

    # 3. Save
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    builder.save(str(out_file))
    return str(out_file)


# Keep the old function as an alias for backward compatibility
def create_flowchart(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    output_path: str,
    width: int = 800,
    height: int = 600,
    style_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a flowchart from node/edge defs. Delegates to create_diagram.

    This is the original API from Phase 1. All node dicts are converted to
    the new element format (type = shape).
    """
    elements = []
    for node in nodes:
        el = dict(node)
        el["type"] = el.pop("shape", "box")
        elements.append(el)

    connections = []
    for edge in edges:
        conn = {
            "from": edge.get("from"),
            "to": edge.get("to"),
            "label": edge.get("label", ""),
            "route": edge.get("route", "straight"),
            "color": edge.get("color", "stroke"),
            "style": "arrow",
        }
        connections.append(conn)

    return create_diagram(elements, connections, output_path, width, height, style_config)
