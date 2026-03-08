"""Diagram engine to generate scientific schematics and flowcharts.

This engine processes high-level diagram descriptions (lists of nodes and edges)
and uses the SVGBuilder to generate the final graphic.
"""
from typing import Dict, List, Any, Optional
from pathlib import Path

from techfig.utils.svg_builder import SVGBuilder

# Shapes the engine can render
SUPPORTED_SHAPES = ("box", "circle", "diamond")


def create_flowchart(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    output_path: str,
    width: int = 800,
    height: int = 600,
    style_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a flowchart-style diagram from node and edge definitions.

    Args:
        nodes: List of node dicts.  Each must have ``id``, ``text``, ``x``, ``y``.
            Optional keys: ``shape`` (box|circle|diamond), ``color``, ``w``/``h``/``r``.
        edges: List of edge dicts with ``from``, ``to``, and optionally
            ``label``, ``route`` (straight|orthogonal), ``color``.
        output_path: Where to save the SVG/PNG file.
        width: Canvas width in pixels.
        height: Canvas height in pixels.
        style_config: Optional style dict to pass to SVGBuilder.

    Returns:
        Absolute path to the generated file.

    Raises:
        ValueError: On unknown shape types.
    """
    builder = SVGBuilder(width=width, height=height, style_config=style_config)

    # 1. Register all nodes
    for node in nodes:
        node_id = node.get("id", "")
        shape = node.get("shape", "box")
        x = float(node.get("x", 0))
        y = float(node.get("y", 0))
        text = node.get("text", "")
        color = node.get("color", "primary")

        if shape == "box":
            w = float(node.get("w", 120))
            h = float(node.get("h", 60))
            builder.add_box(x, y, w, h, text=text, element_id=node_id, color=color)
        elif shape == "circle":
            r = float(node.get("r", 40))
            builder.add_circle(x, y, r, text=text, element_id=node_id, color=color)
        elif shape == "diamond":
            w = float(node.get("w", 100))
            h = float(node.get("h", 80))
            builder.add_diamond(x, y, w, h, text=text, element_id=node_id, color=color)
        else:
            raise ValueError(
                f"Unknown shape type: '{shape}'. "
                f"Supported: {', '.join(SUPPORTED_SHAPES)}"
            )

    # 2. Draw edges
    for edge in edges:
        from_id = edge.get("from")
        to_id = edge.get("to")
        if not from_id or not to_id:
            continue

        builder.add_arrow(
            from_id, to_id,
            text=edge.get("label", ""),
            route=edge.get("route", "straight"),
            stroke_color=edge.get("color", "stroke"),
        )

    # 3. Save
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    builder.save(str(out_file))
    return str(out_file)


def generate_from_description(
    description: str,
    output_path: str,
    style_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a diagram from a natural-language description.

    This is a stub for the AI Agent layer. The engine layer requires
    structured data (nodes/edges). The agent translates ``description``
    into ``nodes`` and ``edges`` then calls :func:`create_flowchart`.
    """
    raise NotImplementedError(
        "Engine layer requires structured nodes/edges. "
        "Use the Agent layer to translate descriptions to structures."
    )
