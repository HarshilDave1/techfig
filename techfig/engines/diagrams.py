"""Diagram engine to generate scientific schematics and flowcharts.

This engine processes high-level diagram descriptions (lists of nodes and edges)
and uses the SVGBuilder to generate the final graphic.

Supported shapes: box, circle, diamond, ellipse, triangle.
Standalone elements: text (free-floating labels), line (plain lines),
arrow (free-form arrow by coordinates), path (multi-segment polyline/curve),
callout (anchored label with leader line),
legend (bordered panel with swatch+label rows).
Connections: arrow (with arrowhead), connection (plain line between elements).
"""
from typing import Dict, List, Any, Optional
from pathlib import Path

from techfig.utils.svg_builder import SVGBuilder
from techfig.components import get_registry
from techfig.components.standard import render_schemdraw_component

# Shapes the engine can render as nodes
SUPPORTED_SHAPES = ("box", "circle", "diamond", "ellipse", "triangle")
# Path-like standalone elements (not anchored to a node id)
SUPPORTED_PATHS = ("line", "arrow", "path")


def _estimate_text_bbox(el: Dict[str, Any], default_font_size: float = 14.0) -> tuple[float, float, float, float]:
    """Estimate text element bounding box: (cx, cy, w, h)."""
    x = float(el.get("x", 0))
    y = float(el.get("y", 0))
    text = el.get("text", "")
    font_size = float(el.get("font_size", default_font_size))
    w = max(len(text) * font_size * 0.6, 1.0)
    h = font_size
    return x, y, w, h


def _bboxes_overlap(
    cx1: float, cy1: float, w1: float, h1: float,
    cx2: float, cy2: float, w2: float, h2: float,
    padding: float = 0.0,
) -> bool:
    """Check if two axis-aligned bounding boxes (center-based) overlap."""
    if w1 <= 0 or h1 <= 0 or w2 <= 0 or h2 <= 0:
        return False
    p = padding
    return not (
        cx1 + w1 / 2 + p <= cx2 - w2 / 2
        or cx2 + w2 / 2 + p <= cx1 - w1 / 2
        or cy1 + h1 / 2 + p <= cy2 - h2 / 2
        or cy2 + h2 / 2 + p <= cy1 - h1 / 2
    )


def _resolve_text_overlaps(elements: List[Dict[str, Any]], default_font_size: float = 14.0) -> List[Dict[str, Any]]:
    """Auto-displace text labels that overlap each other or shapes.

    Phase 1: Groups text elements at nearly-identical (x, y) and stacks
    them vertically with line spacing.
    Phase 2: Nudges text elements that overlap shapes downward.
    Phase 3: Greedy pairwise text-text de-collision — iterates all
    text-text bbox pairs and pushes overlapping labels down by one line
    height. Repeats until no overlaps remain or max iterations reached.
    This runs LAST so it catches any collisions introduced by phase 2.

    Returns a new list of elements with adjusted coordinates.
    """
    if not elements:
        return elements

    result = [dict(el) for el in elements]  # shallow copy each element

    line_height = default_font_size * 1.4

    # --- Phase 1: Stack text elements at same position vertically ---
    text_indices = [i for i, el in enumerate(result) if el.get("type") == "text"]
    if not text_indices:
        return result

    CLUSTER_TOL = 5.0
    clustered: list[list[int]] = []
    assigned = set()

    for idx, i in enumerate(text_indices):
        if i in assigned:
            continue
        el = result[i]
        cluster = [i]
        assigned.add(i)
        x1, y1 = float(el.get("x", 0)), float(el.get("y", 0))
        for j in text_indices[idx + 1:]:
            if j in assigned:
                continue
            el2 = result[j]
            x2, y2 = float(el2.get("x", 0)), float(el2.get("y", 0))
            if abs(x1 - x2) <= CLUSTER_TOL and abs(y1 - y2) <= CLUSTER_TOL:
                cluster.append(j)
                assigned.add(j)
        clustered.append(cluster)

    for cluster in clustered:
        if len(cluster) <= 1:
            continue
        cluster.sort()
        base_x = float(result[cluster[0]].get("x", 0))
        base_y = float(result[cluster[0]].get("y", 0))
        for line_idx, el_idx in enumerate(cluster):
            result[el_idx]["y"] = base_y + line_idx * line_height
            result[el_idx]["x"] = base_x

    # --- Phase 2: Nudge text that overlaps shapes ---
    shape_types = {"box", "circle", "diamond", "ellipse", "triangle"}
    shapes = []
    for el in result:
        if el.get("type") in shape_types:
            x = float(el.get("x", 0))
            y = float(el.get("y", 0))
            if el["type"] in ("box", "diamond", "triangle"):
                w = float(el.get("w", 100))
                h = float(el.get("h", 60))
            elif el["type"] == "circle":
                r = float(el.get("r", 40))
                w = h = r * 2
            elif el["type"] == "ellipse":
                w = float(el.get("rx", 50)) * 2
                h = float(el.get("ry", 30)) * 2
            else:
                continue
            shapes.append((x, y, w, h))

    for el in result:
        if el.get("type") != "text":
            continue
        tx, ty, tw, th = _estimate_text_bbox(el, default_font_size)
        for sx, sy, sw, sh in shapes:
            if _bboxes_overlap(tx, ty, tw, th, sx, sy, sw, sh, padding=4.0):
                # Nudge text downward below the shape
                el["y"] = sy + sh / 2 + th + 8.0
                tx, ty, tw, th = _estimate_text_bbox(el, default_font_size)
                break  # only nudge once per text element

    # --- Phase 3: General text-text bbox de-collision (greedy) ---
    # Runs LAST to catch collisions introduced by phase 2.
    MAX_ITERS = 30
    for _ in range(MAX_ITERS):
        text_els = [(i, result[i]) for i in range(len(result)) if result[i].get("type") == "text"]
        moved = False
        for a in range(len(text_els)):
            for b in range(a + 1, len(text_els)):
                i_a, el_a = text_els[a]
                i_b, el_b = text_els[b]
                ax, ay, aw, ah = _estimate_text_bbox(el_a, default_font_size)
                bx, by, bw, bh = _estimate_text_bbox(el_b, default_font_size)
                if _bboxes_overlap(ax, ay, aw, ah, bx, by, bw, bh, padding=2.0):
                    # Push the lower (higher y) element down by one line
                    if ay <= by:
                        result[i_b]["y"] = float(result[i_b].get("y", 0)) + line_height
                    else:
                        result[i_a]["y"] = float(result[i_a].get("y", 0)) + line_height
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break

    return result


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
            - ``arrow``: ``x1``, ``y1``, ``x2``, ``y2`` + optional ``curve``
            - ``path``: ``points`` (list of [x,y] or [x,y,cmd]) + optional
              ``closed`` (bool), ``arrowhead`` ("none"|"end"|"start"|"both")
            - ``callout``: ``x``, ``y``, ``text`` + ``anchor_x``/``anchor_y``
              or ``anchor`` (id of a previously defined element) + optional
              ``font_size``, ``color``
            - ``legend``: ``x``, ``y``, ``w``, ``h``, ``entries`` (list of
              ``{"label": str, "color": str}`` dicts) + optional ``title``
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

    # 0. Resolve text label overlaps before rendering
    font_size = 14.0
    if style_config and "font_size" in style_config:
        font_size = float(style_config["font_size"])

    # Build a lookup of element positions for computing connection label midpoints
    _el_pos: Dict[str, tuple] = {}
    for el in elements:
        eid = el.get("id", "")
        if eid and "x" in el and "y" in el:
            x, y = float(el["x"]), float(el["y"])
            if el.get("type") in ("box", "diamond", "triangle"):
                w, h = float(el.get("w", 100)), float(el.get("h", 60))
            elif el.get("type") == "circle":
                w = h = float(el.get("r", 40)) * 2
            elif el.get("type") == "ellipse":
                w = h = float(el.get("rx", 50)) * 2, float(el.get("ry", 30)) * 2
            else:
                w, h = 0, 0
            _el_pos[eid] = (x, y, w, h)

    # Inject connection labels as virtual text elements for overlap resolution
    _conn_label_map: Dict[str, tuple] = {}  # virtual_id → (conn_index, adjusted_y)
    _virtual_elements = list(elements)
    for ci, conn in enumerate(connections):
        label = conn.get("label", "")
        if not label:
            continue
        from_id = conn.get("from", "")
        to_id = conn.get("to", "")
        if from_id not in _el_pos or to_id not in _el_pos:
            continue
        fx, fy, fw, fh = _el_pos[from_id]
        tx, ty, tw, th = _el_pos[to_id]
        mid_x = (fx + tx) / 2
        mid_y = (fy + ty) / 2 - 10  # matches svg_builder offset
        vid = f"__conn_label_{ci}"
        _virtual_elements.append({
            "type": "text",
            "id": vid,
            "x": mid_x,
            "y": mid_y,
            "text": label,
            "font_size": font_size * 0.8,
        })
        _conn_label_map[vid] = (ci, mid_y)

    elements = _resolve_text_overlaps(_virtual_elements, default_font_size=font_size)

    # Extract adjusted connection label positions and strip virtual elements
    _adjusted_conn_labels: Dict[int, float] = {}
    _real_elements = []
    for el in elements:
        vid = el.get("id", "")
        if vid in _conn_label_map:
            ci, _ = _conn_label_map[vid]
            _adjusted_conn_labels[ci] = float(el.get("y", 0))
        else:
            _real_elements.append(el)
    elements = _real_elements

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
                text=text, element_id=el_id, color=color,
                stroke_color=el.get("stroke_color", "stroke"),
                **style_kw,
            )

        elif el_type == "circle":
            builder.add_circle(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("r", 40)),
                text=text, element_id=el_id, color=color,
                stroke_color=el.get("stroke_color", "stroke"),
                **style_kw,
            )

        elif el_type == "diamond":
            builder.add_diamond(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("w", 100)), float(el.get("h", 80)),
                text=text, element_id=el_id, color=color,
                stroke_color=el.get("stroke_color", "stroke"),
                **style_kw,
            )

        elif el_type == "ellipse":
            builder.add_ellipse(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("rx", 60)), float(el.get("ry", 30)),
                text=text, element_id=el_id, color=color,
                stroke_color=el.get("stroke_color", "stroke"),
                **style_kw,
            )

        elif el_type == "triangle":
            builder.add_triangle(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("w", 80)), float(el.get("h", 70)),
                text=text, element_id=el_id, color=color,
                stroke_color=el.get("stroke_color", "stroke"),
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
                text=text, stroke_color=el.get("stroke_color", color), **style_kw,
            )

        elif el_type == "arrow":
            # Free-form arrow by explicit coordinates (not anchored to ids).
            # Required: x1, y1, x2, y2. Optional: curve, label via `text`.
            curve = el.get("curve")
            builder.add_arrow_xy(
                float(el.get("x1", 0)), float(el.get("y1", 0)),
                float(el.get("x2", 100)), float(el.get("y2", 0)),
                text=text, stroke_color=color,
                curve=float(curve) if curve is not None else None,
                **style_kw,
            )

        elif el_type == "path":
            # Multi-segment polyline/curve from a `points` list.
            # Each entry: [x, y] or [x, y, "M|L|Q|C"]. Q consumes one extra
            # control point, C consumes two. Optional: closed, arrowhead.
            raw_points = el.get("points", [])
            if not raw_points or len(raw_points) < 2:
                raise ValueError(
                    f"path element '{el_id}' needs a 'points' list with at least 2 entries"
                )
            points = []
            for p in raw_points:
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    raise ValueError(
                        f"path element '{el_id}': each point must be [x, y] or [x, y, cmd]"
                    )
                points.append(tuple(float(v) if i < 2 else v for i, v in enumerate(p)))
            builder.add_path(
                points,
                text=text, stroke_color=color,
                closed=bool(el.get("closed", False)),
                arrowhead=el.get("arrowhead", "none"),
                **style_kw,
            )

        elif el_type == "callout":
            builder.add_callout(
                float(el.get("x", 0)), float(el.get("y", 0)),
                text=text,
                anchor_x=el.get("anchor_x"),
                anchor_y=el.get("anchor_y"),
                anchor_id=el.get("anchor", ""),
                element_id=el_id,
                color=color,
                font_size=el.get("font_size"),
                **style_kw,
            )

        elif el_type == "legend":
            entries = el.get("entries", [])
            builder.add_legend(
                float(el.get("x", 0)), float(el.get("y", 0)),
                float(el.get("w", 180)), float(el.get("h", 120)),
                entries=entries,
                element_id=el_id,
                title=el.get("title", ""),
                color=color,
                swatch_shape=el.get("swatch_shape", "rect"),
                **style_kw,
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
                    f"Supported: {', '.join(SUPPORTED_SHAPES)}, text, line, arrow, path, "
                    f"callout, legend, or any registered component."
                )


    # 2. Draw connections
    for ci, conn in enumerate(connections):
        from_id = conn.get("from")
        to_id = conn.get("to")
        if not from_id or not to_id:
            continue

        style = conn.get("style", "arrow")  # "arrow" or "line"
        conn_kw: Dict[str, Any] = {}
        if "stroke_dash" in conn:
            conn_kw["stroke_dash"] = conn["stroke_dash"]

        # Apply adjusted label y-offset from overlap resolver
        label = conn.get("label", "")
        if ci in _adjusted_conn_labels and label:
            # The resolver computed a target y for this label.
            # svg_builder places it at mid_y - 10, so we pass a
            # label_y_offset to compensate.
            # Compute the original mid_y the same way svg_builder does
            if from_id in builder._elements and to_id in builder._elements:
                fx, fy, fw, fh = builder._elements[from_id]
                tx, ty, tw, th = builder._elements[to_id]
                orig_mid_y = (fy + ty) / 2 - 10
                target_y = _adjusted_conn_labels[ci]
                conn_kw["label_y_override"] = target_y

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
        if "type" not in el:
            el["type"] = el.pop("shape", "box")
        elif "shape" in el:
            el.pop("shape", None)
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
