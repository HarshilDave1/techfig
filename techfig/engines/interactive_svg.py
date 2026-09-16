"""Interactive SVG runtime: parametric spec -> self-contained HTML widget.

Given a spec with ``params`` and ``{{expr}}`` bindings (see
``techfig.engines.params``), this module emits ONE self-contained HTML file:

- a ``.tf-controls`` panel with one range slider per param,
- the concrete SVG rendered at default params (via ``render_from_spec``),
- a small vanilla-JS runtime (no external dependencies) that re-evaluates
  every binding on slider input and applies it via ``setAttribute`` /
  ``textContent``.

Bindings table: each entry is ``{id, sel, attr, js, kind}`` where ``id`` is the
SVG element id, ``sel`` an optional CSS selector evaluated inside the element
group (e.g. ``"rect"`` for a box's rectangle), ``attr`` the SVG attribute (or
``textContent``), ``js`` the transpiled expression, and ``kind`` the binding
kind (``value`` = whole field, ``text`` = interpolated string).

Coordinate conventions (must mirror ``svg_builder.SVGBuilder``):
- Shape ``(x, y)`` is the CENTER; rect corners are ``x - w/2``, ``y - h/2``.
  Bound ``w``/``h`` therefore also recompute the rect corner.
- Bound ``x``/``y`` move the whole group via a ``translate(dx, dy)`` transform
  whose delta is measured from the RENDERED position — so labels displaced by
  the text-overlap resolver keep their correction when the expression value
  equals the default.
- ``line``/``arrow`` elements render as a single ``<path d="M..L..">``;
  bound endpoints recompute ``d`` (curved arrows re-derive the quadratic
  control point exactly like ``SVGBuilder.add_arrow_xy``).
- Bound ``points`` on a ``path`` element recompute ``d`` from an array
  expression via the runtime helper ``__tf_d``. ``points`` bindings on
  ``polygon``/``pen``/``compound`` are not supported (their ``d`` involves
  smoothing / boolean geometry) and raise ``ValueError``.

Unsupported binding targets raise ``ValueError`` with the element type and
field named, so spec authors fail fast instead of shipping inert controls.
"""
import copy
import html
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

from techfig.engines.model_transpile import TranspileError, expr_to_js
from techfig.engines.params import _BINDING_RE, resolve_spec
from techfig.engines.sketch_interpreter import render_from_spec
from techfig.styles.presets import get_style

_JS_NAME_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")

# Element type -> SVG child tag that carries geometry (None = the id node
# itself, used for line/arrow/path which render as bare <path> elements).
_SHAPE_SEL: Dict[str, Optional[str]] = {
    "box": "rect", "textblock": "rect", "legend": "rect", "image": "image",
    "circle": "circle", "ellipse": "ellipse",
    "diamond": "path", "triangle": "path",
    "polygon": "path", "pen": "path", "compound": "path",
    "text": "text", "callout": "text", "readout": "text",
    "line": None, "arrow": None, "path": None,
}

# Defaults mirroring diagrams.py el.get(...) fallbacks, used when reading
# constants for geometry recomputation.
_TYPE_DEFAULTS: Dict[str, Dict[str, float]] = {
    "box": {"x": 0, "y": 0, "w": 120, "h": 60},
    "textblock": {"x": 0, "y": 0, "w": 240, "h": 120},
    "legend": {"x": 0, "y": 0, "w": 180, "h": 120},
    "image": {"x": 0, "y": 0, "w": 160, "h": 120},
    "circle": {"x": 0, "y": 0, "r": 40},
    "ellipse": {"x": 0, "y": 0, "rx": 60, "ry": 30},
    "diamond": {"x": 0, "y": 0, "w": 100, "h": 80},
    "triangle": {"x": 0, "y": 0, "w": 80, "h": 70},
    "line": {"x1": 0, "y1": 0, "x2": 100, "y2": 0},
    "arrow": {"x1": 0, "y1": 0, "x2": 100, "y2": 0},
    "readout": {"x": 0, "y": 0},
}

_COMMON_STYLE = {
    "color", "stroke_color", "fill_opacity", "stroke_opacity",
    "stroke_dash", "stroke_width", "opacity", "rotation", "visible_when",
}

# Bindable fields per element type. Anything else raises ValueError.
_SUPPORTED: Dict[str, set] = {
    "box": _COMMON_STYLE | {"x", "y", "w", "h", "text"},
    "circle": _COMMON_STYLE | {"x", "y", "r", "text"},
    "ellipse": _COMMON_STYLE | {"x", "y", "rx", "ry", "text"},
    "diamond": _COMMON_STYLE | {"x", "y", "w", "h", "text"},
    "triangle": _COMMON_STYLE | {"x", "y", "w", "h", "text"},
    "text": _COMMON_STYLE | {"x", "y", "text", "font_size"},
    "textblock": _COMMON_STYLE | {"x", "y", "w", "h"},
    "callout": ({"stroke_dash", "stroke_opacity", "stroke_width", "opacity"})
    | {"x", "y", "text", "font_size", "visible_when"},
    "line": (_COMMON_STYLE - {"rotation", "fill_opacity"})
    | {"x1", "y1", "x2", "y2"},
    "arrow": (_COMMON_STYLE - {"rotation", "fill_opacity"})
    | {"x1", "y1", "x2", "y2", "curve"},
    "path": (_COMMON_STYLE - {"rotation", "fill_opacity"}) | {"points"},
    "polygon": _COMMON_STYLE | {"text"},
    "pen": _COMMON_STYLE | {"text"},
    "compound": _COMMON_STYLE | {"text"},
    "legend": _COMMON_STYLE | {"x", "y", "w", "h"},
    "image": {"opacity", "visible_when"} | {"x", "y", "w", "h"},
    "plot": {"series", "data", "visible_when"},
    "readout": _COMMON_STYLE | {"x", "y", "expr", "format", "label", "unit", "verdict", "font_size"},
}

# (field, svg attr, target) — target: "shape" (geometry child), "stroke"
# (stroke-bearing child), "self" (id node), "text" (label text child).
def _style_bindings(el_type: str) -> List[Tuple[str, str, str]]:
    sel = _SHAPE_SEL.get(el_type)
    if el_type in ("line", "arrow", "path"):
        stroke_target, fill_target = "self", "self"
    elif el_type == "pen":
        stroke_target, fill_target = "shape", "shape"
    else:
        stroke_target, fill_target = "shape", "shape"
    if el_type == "text":
        fill_target = "text"
    if el_type == "legend":
        stroke_target = "shape"  # legend color is the panel border
        fill_target = "shape"
    mappings: List[Tuple[str, str, str]] = [
        ("opacity", "opacity", "self"),
        ("stroke_dash", "stroke-dasharray", stroke_target),
        ("stroke_opacity", "stroke-opacity", stroke_target),
        ("stroke_width", "stroke-width", stroke_target),
        ("stroke_color", "stroke", stroke_target),
        ("fill_opacity", "fill-opacity", fill_target),
        ("color", "fill", fill_target),
    ]
    if el_type in ("line", "arrow", "path", "pen"):
        # These types use `color` as the stroke color (see diagrams.py).
        mappings = [m for m in mappings if m[0] != "color"]
        mappings.append(("color", "stroke", stroke_target))
    if el_type == "legend":
        mappings = [m for m in mappings if m[0] != "color"]
        mappings.append(("color", "stroke", stroke_target))
    _ = sel
    return mappings


def _numval(v: float) -> str:
    """Bare JS number literal (no parens)."""
    f = float(v)
    if f.is_integer():
        return str(int(f))
    return repr(f)


def _num(v: float) -> str:
    """Parenthesized JS number literal, matching transpiled expression style."""
    return "(" + _numval(v) + ")"


def linear_scale(
    domain: Tuple[float, float] | List[float],
    range_: Tuple[float, float] | List[float],
) -> Tuple[float, float]:
    """Compute linear mapping constants (a, b) such that screen = a * val + b.

    Args:
        domain: (d0, d1) data coordinate domain.
        range_: (r0, r1) screen/SVG coordinate range.

    Returns:
        (a, b) scale slope and offset.
    """
    d0, d1 = float(domain[0]), float(domain[1])
    r0, r1 = float(range_[0]), float(range_[1])
    if d1 == d0:
        return 0.0, r0
    a = (r1 - r0) / (d1 - d0)
    b = r0 - a * d0
    return a, b


def _fmt_coord(v: float) -> str:
    f = float(v)
    if f.is_integer():
        return str(int(f))
    return repr(f)


def compute_series_d(
    xs: Optional[List[float]],
    ys: List[float],
    ax: float,
    bx: float,
    ay: float,
    by: float,
) -> str:
    """Compute SVG path d string from coordinates and scale constants."""
    if not ys:
        return ""
    n = min(len(xs), len(ys)) if (xs is not None and len(xs) > 0) else len(ys)
    pts = []
    for i in range(n):
        x_val = xs[i] if (xs is not None and len(xs) > 0) else i
        y_val = ys[i]
        sx = ax * x_val + bx
        sy = ay * y_val + by
        pts.append(f"{_fmt_coord(sx)} {_fmt_coord(sy)}")
    return "M " + " L ".join(pts)


def _format_tick(v: float) -> str:
    if abs(v) < 1e-12:
        return "0"
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.4g}"


def _get_plot_series(el: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract list of series dicts from a plot element."""
    series = el.get("series")
    if series is None:
        series = el.get("data")
    if series is None and isinstance(el.get("chart"), dict):
        series = el["chart"].get("series") or el["chart"].get("data")
    if isinstance(series, dict):
        return [series]
    if isinstance(series, list):
        return [s for s in series if isinstance(s, dict)]
    return []


def _is_bound_plot(el: Dict[str, Any]) -> bool:
    """Return True if el is a plot element with bound series/data."""
    if el.get("type") != "plot":
        return False
    series_list = _get_plot_series(el)
    if not series_list:
        return False
    for s in series_list:
        if not isinstance(s, dict):
            continue
        if _contains_binding(s.get("x")) or _contains_binding(s.get("y")):
            return True
    return False


def _compute_plot_limits(
    el: Dict[str, Any],
    cel: Dict[str, Any],
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Determine frozen xlim and ylim for the plot element.

    If present in el (or cel), use them. Otherwise compute at default params with
    10% padding.
    """
    xlim_spec = el.get("xlim") or cel.get("xlim")
    ylim_spec = el.get("ylim") or cel.get("ylim")

    series_list = _get_plot_series(cel)
    all_xs: List[float] = []
    all_ys: List[float] = []
    for s in series_list:
        xs = s.get("x")
        ys = s.get("y")
        if isinstance(ys, list) and ys:
            all_ys.extend(float(v) for v in ys if isinstance(v, (int, float)))
            if isinstance(xs, list) and xs:
                all_xs.extend(float(v) for v in xs if isinstance(v, (int, float)))
            else:
                all_xs.extend(float(i) for i in range(len(ys)))

    if xlim_spec:
        xlim = (float(xlim_spec[0]), float(xlim_spec[1]))
    else:
        if not all_xs:
            xlim = (0.0, 1.0)
        else:
            min_x, max_x = min(all_xs), max(all_xs)
            span = max_x - min_x
            if span == 0:
                pad = 1.0 if min_x == 0 else abs(min_x) * 0.1
            else:
                pad = 0.1 * span
            xlim = (min_x - pad, max_x + pad)

    if ylim_spec:
        ylim = (float(ylim_spec[0]), float(ylim_spec[1]))
    else:
        if not all_ys:
            ylim = (0.0, 1.0)
        else:
            min_y, max_y = min(all_ys), max(all_ys)
            span = max_y - min_y
            if span == 0:
                pad = 1.0 if min_y == 0 else abs(min_y) * 0.1
            else:
                pad = 0.1 * span
            ylim = (min_y - pad, max_y + pad)

    return xlim, ylim


def _render_native_plot_svg(
    el: Dict[str, Any],
    cel: Dict[str, Any],
    el_id: str,
    spec_style: Any = None,
) -> str:
    """Render native SVG markup for a bound plot element."""
    xlim, ylim = _compute_plot_limits(el, cel)
    w = float(el.get("w", cel.get("w", 300)))
    h = float(el.get("h", cel.get("h", 200)))
    pad_left = min(50.0, w * 0.25)
    pad_bottom = min(40.0, h * 0.25)
    pad_top = min(20.0, h * 0.15)
    pad_right = min(20.0, w * 0.15)
    x = float(el.get("x", cel.get("x", 0)))
    y = float(el.get("y", cel.get("y", 0)))
    fx = (x - w / 2) + pad_left
    fy = (y - h / 2) + pad_top
    fw = w - pad_left - pad_right
    fh = h - pad_top - pad_bottom

    ax, bx = linear_scale(xlim, (fx, fx + fw))
    ay, by = linear_scale(ylim, (fy + fh, fy))

    style_name = "nature"
    if isinstance(spec_style, dict):
        style_name = spec_style.get("name", "nature")
    elif isinstance(spec_style, str):
        style_name = spec_style
    preset = get_style(style_name)
    colors = preset.get("colors", {})
    palette = [
        colors.get("primary", "#0072B2"),
        colors.get("secondary", "#D55E00"),
        colors.get("accent", "#009E73"),
        colors.get("warning", "#F0E442"),
        colors.get("muted", "#56B4E9"),
    ]
    font_family = preset.get("font_family", "DejaVu Sans, Liberation Sans, sans-serif")
    font_size = float(preset.get("font_size", 12))
    tick_font_size = max(9.0, font_size * 0.8)
    text_color = colors.get("text", "#000000")
    axis_color = colors.get("text", "#333333")

    parts = [f'<g id="{html.escape(str(el_id), quote=True)}" class="tf-plot">']
    # Frame rect
    parts.append(
        f'<rect class="tf-plot-frame" x="{_fmt_coord(fx)}" y="{_fmt_coord(fy)}" '
        f'width="{_fmt_coord(fw)}" height="{_fmt_coord(fh)}" '
        f'fill="none" stroke="{axis_color}" stroke-width="1" />'
    )

    # 5 linear ticks on x axis
    for i in range(5):
        t_val = xlim[0] + i * (xlim[1] - xlim[0]) / 4
        sx = ax * t_val + bx
        parts.append(
            f'<line x1="{_fmt_coord(sx)}" y1="{_fmt_coord(fy + fh)}" '
            f'x2="{_fmt_coord(sx)}" y2="{_fmt_coord(fy + fh + 5)}" '
            f'stroke="{axis_color}" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{_fmt_coord(sx)}" y="{_fmt_coord(fy + fh + 5 + tick_font_size)}" '
            f'text-anchor="middle" font-family="{font_family}" '
            f'font-size="{_fmt_coord(tick_font_size)}" fill="{text_color}">'
            f'{_format_tick(t_val)}</text>'
        )

    # 5 linear ticks on y axis
    for j in range(5):
        t_val = ylim[0] + j * (ylim[1] - ylim[0]) / 4
        sy = ay * t_val + by
        parts.append(
            f'<line x1="{_fmt_coord(fx)}" y1="{_fmt_coord(sy)}" '
            f'x2="{_fmt_coord(fx - 5)}" y2="{_fmt_coord(sy)}" '
            f'stroke="{axis_color}" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{_fmt_coord(fx - 8)}" y="{_fmt_coord(sy + tick_font_size * 0.35)}" '
            f'text-anchor="end" font-family="{font_family}" '
            f'font-size="{_fmt_coord(tick_font_size)}" fill="{text_color}">'
            f'{_format_tick(t_val)}</text>'
        )

    # Axis labels
    xlabel = el.get("xlabel") or cel.get("xlabel")
    if xlabel:
        parts.append(
            f'<text class="tf-axis-label-x" x="{_fmt_coord(fx + fw / 2)}" '
            f'y="{_fmt_coord(fy + fh + pad_bottom - 4)}" text-anchor="middle" '
            f'font-family="{font_family}" font-size="{_fmt_coord(font_size)}" '
            f'fill="{text_color}">{html.escape(str(xlabel), quote=True)}</text>'
        )

    ylabel = el.get("ylabel") or cel.get("ylabel")
    if ylabel:
        yl_x = fx - pad_left + 14
        yl_y = fy + fh / 2
        parts.append(
            f'<text class="tf-axis-label-y" x="{_fmt_coord(yl_x)}" y="{_fmt_coord(yl_y)}" '
            f'text-anchor="middle" font-family="{font_family}" '
            f'font-size="{_fmt_coord(font_size)}" fill="{text_color}" '
            f'transform="rotate(-90, {_fmt_coord(yl_x)}, {_fmt_coord(yl_y)})">{html.escape(str(ylabel), quote=True)}</text>'
        )

    title = el.get("title") or cel.get("title")
    if title:
        parts.append(
            f'<text class="tf-plot-title" x="{_fmt_coord(fx + fw / 2)}" '
            f'y="{_fmt_coord(fy - 6)}" text-anchor="middle" '
            f'font-family="{font_family}" font-size="{_fmt_coord(font_size)}" '
            f'font-weight="bold" fill="{text_color}">{html.escape(str(title), quote=True)}</text>'
        )

    caption = el.get("text") or cel.get("text")
    if caption:
        parts.append(
            f'<text class="tf-plot-caption" x="{_fmt_coord(x)}" '
            f'y="{_fmt_coord(y + h / 2 + font_size)}" text-anchor="middle" '
            f'font-family="{font_family}" font-size="{_fmt_coord(font_size)}" '
            f'fill="{text_color}">{html.escape(str(caption), quote=True)}</text>'
        )

    # Series paths
    spec_series = _get_plot_series(el)
    cel_series = _get_plot_series(cel)
    for k, s in enumerate(cel_series):
        orig_s = spec_series[k] if k < len(spec_series) else s
        series_path_id = orig_s.get("id") or s.get("id") or f"{el_id}-s{k}"
        series_path_id = html.escape(str(series_path_id), quote=True)
        color = s.get("color") or orig_s.get("color")
        if color in colors:
            stroke = colors[color]
        elif color:
            stroke = html.escape(str(color), quote=True)
        else:
            stroke = palette[k % len(palette)]
        sw = float(s.get("stroke_width", orig_s.get("stroke_width", 2.0)))
        xs = s.get("x")
        ys = s.get("y")
        initial_d = compute_series_d(xs, ys, ax, bx, ay, by)
        extra_attrs = ""
        dash = s.get("stroke_dash") or orig_s.get("stroke_dash")
        if dash:
            extra_attrs += f' stroke-dasharray="{html.escape(str(dash), quote=True)}"'
        parts.append(
            f'<path id="{series_path_id}" class="tf-series" d="{initial_d}" '
            f'fill="none" stroke="{stroke}" stroke-width="{_fmt_coord(sw)}"{extra_attrs} />'
        )

    parts.append("</g>")
    return "\n".join(parts)


def _plot_series_bindings(
    el: Dict[str, Any],
    cel: Dict[str, Any],
    el_id: str,
    model_funcs: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    xlim, ylim = _compute_plot_limits(el, cel)
    w = float(el.get("w", cel.get("w", 300)))
    h = float(el.get("h", cel.get("h", 200)))
    pad_left = min(50.0, w * 0.25)
    pad_bottom = min(40.0, h * 0.25)
    pad_top = min(20.0, h * 0.15)
    pad_right = min(20.0, w * 0.15)
    x = float(el.get("x", cel.get("x", 0)))
    y = float(el.get("y", cel.get("y", 0)))
    fx = (x - w / 2) + pad_left
    fy = (y - h / 2) + pad_top
    fw = w - pad_left - pad_right
    fh = h - pad_top - pad_bottom

    ax, bx = linear_scale(xlim, (fx, fx + fw))
    ay, by = linear_scale(ylim, (fy + fh, fy))

    spec_series = _get_plot_series(el)
    cel_series = _get_plot_series(cel)

    for k, s in enumerate(spec_series):
        if not _contains_binding(s.get("x")) and not _contains_binding(s.get("y")):
            continue
        series_path_id = s.get("id") or (cel_series[k].get("id") if k < len(cel_series) else None) or f"{el_id}-s{k}"
        x_val = s.get("x")
        y_val = s.get("y")
        if x_val is not None and _contains_binding(x_val):
            x_js = _value_to_js(x_val, extra_funcs=model_funcs)[0]
        elif x_val is not None:
            x_js = json.dumps(x_val)
        else:
            x_js = "null"

        if y_val is not None and _contains_binding(y_val):
            y_js = _value_to_js(y_val, extra_funcs=model_funcs)[0]
        elif y_val is not None:
            y_js = json.dumps(y_val)
        else:
            y_js = "null"

        js_expr = f"__tf_series_d({x_js}, {y_js}, {_fmt_coord(ax)}, {_fmt_coord(bx)}, {_fmt_coord(ay)}, {_fmt_coord(by)})"
        entries.append(_entry(series_path_id, None, "d", js_expr, "value"))

    return entries


def _contains_binding(value: Any) -> bool:
    if isinstance(value, str):
        return _BINDING_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_binding(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_binding(v) for v in value.values())
    return False


def _value_to_js(value: Any, extra_funcs: Iterable[str] = ()) -> Tuple[str, str]:
    """Convert a spec field value (possibly containing bindings) to JS source.

    Returns ``(js, kind)`` where kind is ``'value'`` for whole-field bindings
    and ``'text'`` for interpolated strings.  ``extra_funcs`` whitelists model
    function names as call targets.
    """
    if isinstance(value, str):
        if not _BINDING_RE.search(value):
            return json.dumps(value), "value"
        stripped = value.strip()
        m = _BINDING_RE.fullmatch(stripped)
        if m:
            return expr_to_js(m.group(1).strip(), extra_funcs=extra_funcs), "value"
        parts: List[str] = []
        last = 0
        for bm in _BINDING_RE.finditer(value):
            lit = value[last:bm.start()]
            if lit:
                parts.append(json.dumps(lit))
            parts.append("(" + expr_to_js(bm.group(1).strip(), extra_funcs=extra_funcs) + ")")
            last = bm.end()
        lit = value[last:]
        if lit:
            parts.append(json.dumps(lit))
        if not parts:
            parts = ['""']
        return " + ".join(parts), "text"
    if isinstance(value, list):
        items = []
        for item in value:
            item_js, _ = _value_to_js(item, extra_funcs)
            items.append(item_js)
        return "[" + ", ".join(items) + "]", "value"
    if isinstance(value, bool):
        return ("true" if value else "false"), "value"
    if isinstance(value, (int, float)):
        return _num(value), "value"
    if value is None:
        return "null", "value"
    raise TranspileError(f"Cannot transpile value of type {type(value).__name__}")


# ---- SVG parsing helpers -------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_by_id(root: ET.Element, el_id: str) -> Optional[ET.Element]:
    for node in root.iter():
        if node.get("id") == el_id:
            return node
    return None


def _first_child(node: ET.Element, tag: str) -> Optional[ET.Element]:
    for child in node:
        if _local(child.tag) == tag:
            return child
    return None


def _svg_label_pos(node: Optional[ET.Element]) -> Optional[Tuple[float, float]]:
    """Rendered (x, y) of the <text> child of a group (post overlap-resolver)."""
    if node is None:
        return None
    child = _first_child(node, "text")
    if child is None:
        return None
    try:
        return float(child.get("x")), float(child.get("y"))
    except (TypeError, ValueError):
        return None


# ---- binding entry construction -------------------------------------------


def _entry(el_id: str, sel: Optional[str], attr: str, js: str, kind: str) -> Dict[str, Any]:
    return {"id": el_id, "sel": sel, "attr": attr, "js": js, "kind": kind}


def _const(cel: Dict[str, Any], el_type: str, field: str) -> float:
    return float(cel.get(field, _TYPE_DEFAULTS.get(el_type, {}).get(field, 0)))


def _bound_or_const(bound: Dict[str, Tuple[str, str]], field: str, const: float) -> str:
    if field in bound:
        return bound[field][0]
    return _num(const)


def _transform_js(
    bound: Dict[str, Tuple[str, str]],
    cx: float, cy: float,
    orig_transform: Optional[str],
) -> str:
    dx = "(%s) - %s" % (bound["x"][0], _num(cx)) if "x" in bound else "0"
    dy = "(%s) - %s" % (bound["y"][0], _num(cy)) if "y" in bound else "0"
    core = "translate(${%s}, ${%s})" % (dx, dy)
    if orig_transform:
        return "`%s %s`" % (orig_transform, core)
    return "`%s`" % core


def _line_arrow_d(
    cel: Dict[str, Any], el_type: str, bound: Dict[str, Tuple[str, str]]
) -> str:
    """Recompute `d` for line/arrow endpoints (curved arrows included)."""
    x1 = _bound_or_const(bound, "x1", _const(cel, el_type, "x1"))
    y1 = _bound_or_const(bound, "y1", _const(cel, el_type, "y1"))
    x2 = _bound_or_const(bound, "x2", _const(cel, el_type, "x2"))
    y2 = _bound_or_const(bound, "y2", _const(cel, el_type, "y2"))
    curve_const = cel.get("curve")
    curved = "curve" in bound or (el_type == "arrow" and curve_const)
    if not curved:
        return "`M ${%s} ${%s} L ${%s} ${%s}`" % (x1, y1, x2, y2)
    c = bound["curve"][0] if "curve" in bound else _num(float(curve_const))
    # Replicates SVGBuilder.add_arrow_xy quadratic control-point math.
    return (
        "(function () {{ var x1 = {x1}; var y1 = {y1}; var x2 = {x2}; var y2 = {y2};"
        " var c = {c};\n"
        "  var mx = (x1 + x2) / 2, my = (y1 + y2) / 2;\n"
        "  var dx = x2 - x1, dy = y2 - y1, nx = -dy, ny = dx;"
        " var l = Math.sqrt(nx * nx + ny * ny);\n"
        "  if (l) {{ nx /= l; ny /= l; }}\n"
        "  var qx = mx + nx * c, qy = my + ny * c;\n"
        '  return "M " + x1 + " " + y1 + " Q " + qx + " " + qy'
        ' + " " + x2 + " " + y2; }})()'
    ).format(x1=x1, y1=y1, x2=x2, y2=y2, c=c)


_TRIANGLE_POINTS: Dict[str, List[Tuple[str, str]]] = {
    # direction -> [(x-expr-template, y-expr-template)] * 3, matching svg_builder
    "up":    [("{x}", "{y} - ({h} / 2)"), ("{x} - ({w} / 2)", "{y} + ({h} / 2)"),
              ("{x} + ({w} / 2)", "{y} + ({h} / 2)")],
    "down":  [("{x}", "{y} + ({h} / 2)"), ("{x} - ({w} / 2)", "{y} - ({h} / 2)"),
              ("{x} + ({w} / 2)", "{y} - ({h} / 2)")],
    "left":  [("{x} - ({w} / 2)", "{y}"), ("{x} + ({w} / 2)", "{y} - ({h} / 2)"),
              ("{x} + ({w} / 2)", "{y} + ({h} / 2)")],
    "right": [("{x} + ({w} / 2)", "{y}"), ("{x} - ({w} / 2)", "{y} - ({h} / 2)"),
              ("{x} - ({w} / 2)", "{y} + ({h} / 2)")],
}


def _diamond_triangle_d(
    cel: Dict[str, Any], el_type: str, bound: Dict[str, Tuple[str, str]]
) -> str:
    x = _bound_or_const(bound, "x", _const(cel, el_type, "x"))
    y = _bound_or_const(bound, "y", _const(cel, el_type, "y"))
    w = _bound_or_const(bound, "w", _const(cel, el_type, "w"))
    h = _bound_or_const(bound, "h", _const(cel, el_type, "h"))
    if el_type == "diamond":
        pts = ["{x}, {y} - ({h} / 2)", "{x} + ({w} / 2), {y}",
               "{x}, {y} + ({h} / 2)", "{x} - ({w} / 2), {y}"]
    else:
        direction = str(cel.get("direction", "up"))
        pts = [px + ", " + py for px, py in _TRIANGLE_POINTS.get(direction,
               _TRIANGLE_POINTS["up"])]
    body = " ".join("L " + p for p in pts[1:])
    return "`M {m} {b} Z`".format(m=pts[0], b=body).format(x=x, y=y, w=w, h=h)


def _path_d(cel: Dict[str, Any], bound: Dict[str, Tuple[str, str]]) -> str:
    points_js = bound["points"][0]
    js = "__tf_d(%s)" % points_js
    if cel.get("closed"):
        js = "(%s) + ' Z'" % js
    return js


def _entries_for_element(
    el: Dict[str, Any],
    cel: Dict[str, Any],
    el_id: str,
    el_type: str,
    bound: Dict[str, Tuple[str, str]],
    svg_root: ET.Element,
) -> List[Dict[str, Any]]:
    if el_type not in _SUPPORTED:
        raise ValueError(
            f"interactive bindings on element type '{el_type}' are not supported"
        )
    unknown = sorted(set(bound) - _SUPPORTED[el_type])
    if unknown:
        raise ValueError(
            f"interactive binding on {el_type}.{unknown[0]} is not supported"
        )

    entries: List[Dict[str, Any]] = []
    node = _find_by_id(svg_root, el_id)
    orig_transform = node.get("transform") if node is not None else None
    sel = _SHAPE_SEL.get(el_type)

    # --- position (x/y) -> group translate transform -----------------------
    pos_bound = [f for f in ("x", "y") if f in bound]
    if pos_bound:
        if "rotation" in bound:
            raise ValueError(
                f"binding both rotation and x/y on {el_type} is not supported"
            )
        if el_type in ("text", "callout"):
            pos = _svg_label_pos(node) or (
                _const(cel, el_type, "x"), _const(cel, el_type, "y")
            )
            cx, cy = pos
        else:
            cx, cy = _const(cel, el_type, "x"), _const(cel, el_type, "y")
        entries.append(_entry(
            el_id, None, "transform",
            _transform_js(bound, cx, cy, orig_transform), "value",
        ))
    elif "rotation" in bound:
        if el_type in ("text", "callout"):
            pos = _svg_label_pos(node) or (
                _const(cel, el_type, "x"), _const(cel, el_type, "y")
            )
            cx, cy = pos
        else:
            cx, cy = _const(cel, el_type, "x"), _const(cel, el_type, "y")
        js = "`rotate(${{{0}}}, {1}, {2})`".format(
            bound["rotation"][0], _numval(cx), _numval(cy)
        )
        entries.append(_entry(el_id, None, "transform", js, bound["rotation"][1]))

    # --- geometry recomputes -> d attribute --------------------------------
    if el_type in ("line", "arrow"):
        if any(f in bound for f in ("x1", "y1", "x2", "y2", "curve")):
            entries.append(_entry(
                el_id, None, "d", _line_arrow_d(cel, el_type, bound), "value",
            ))
    elif el_type == "path":
        entries.append(_entry(el_id, None, "d", _path_d(cel, bound), bound["points"][1]))
    elif el_type in ("diamond", "triangle"):
        if any(f in bound for f in ("x", "y", "w", "h")):
            entries.append(_entry(
                el_id, "path", "d", _diamond_triangle_d(cel, el_type, bound), "value",
            ))

    # --- size fields -> width/height (+ corner recompute, center origin) ---
    if el_type in ("box", "textblock", "legend", "image"):
        cx, cy = _const(cel, el_type, "x"), _const(cel, el_type, "y")
        if "w" in bound:
            wjs = bound["w"][0]
            entries.append(_entry(el_id, sel, "width", wjs, bound["w"][1]))
            entries.append(_entry(
                el_id, sel, "x",
                "`${%s - ((%s) / 2)}`" % (_num(cx), wjs), "value",
            ))
        if "h" in bound:
            hjs = bound["h"][0]
            entries.append(_entry(el_id, sel, "height", hjs, bound["h"][1]))
            entries.append(_entry(
                el_id, sel, "y",
                "`${%s - ((%s) / 2)}`" % (_num(cy), hjs), "value",
            ))
    elif el_type == "circle" and "r" in bound:
        entries.append(_entry(el_id, sel, "r", bound["r"][0], bound["r"][1]))
    elif el_type == "ellipse":
        if "rx" in bound:
            entries.append(_entry(el_id, sel, "rx", bound["rx"][0], bound["rx"][1]))
        if "ry" in bound:
            entries.append(_entry(el_id, sel, "ry", bound["ry"][0], bound["ry"][1]))

    # --- label text -> textContent ------------------------------------------
    if "text" in bound:
        entries.append(_entry(
            el_id, "text", "textContent", bound["text"][0], bound["text"][1],
        ))
    if "font_size" in bound:
        entries.append(_entry(
            el_id, "text", "font-size", bound["font_size"][0], bound["font_size"][1],
        ))

    # --- style fields -------------------------------------------------------
    target_sel = {"shape": sel, "self": None, "text": "text"}
    for field, attr, target in _style_bindings(el_type):
        if field in bound:
            entries.append(_entry(
                el_id, target_sel[target], attr, bound[field][0], bound[field][1],
            ))
    return entries


def _readout_bindings(
    el: Dict[str, Any],
    cel: Dict[str, Any],
    el_id: str,
    model_funcs: Iterable[str] = (),
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    attr_entries: List[Dict[str, Any]] = []
    class_entries: List[Dict[str, Any]] = []

    # 1. Value text binding
    expr_val = el.get("expr", "")
    clean_expr = str(expr_val).strip()
    if clean_expr.startswith("{{") and clean_expr.endswith("}}"):
        clean_expr = clean_expr[2:-2].strip()
    expr_js = expr_to_js(clean_expr, extra_funcs=model_funcs)

    fmt = el.get("format")
    if fmt:
        val_js = f"__fmt({expr_js}, {json.dumps(fmt)})"
    else:
        val_js = f"String({expr_js})"

    unit = el.get("unit")
    if unit:
        val_js = f"({val_js}) + {json.dumps(' ' + unit)}"

    label = el.get("label")
    if label:
        text_js = f"{json.dumps(label + ': ')} + ({val_js})"
    else:
        text_js = val_js

    attr_entries.append(_entry(el_id, ".tf-readout-text", "textContent", text_js, "text"))

    # 2. Verdict text and class bindings
    verdict = el.get("verdict")
    if isinstance(verdict, dict):
        v_expr = verdict.get("expr", "")
        clean_v = str(v_expr).strip()
        if clean_v.startswith("{{") and clean_v.endswith("}}"):
            clean_v = clean_v[2:-2].strip()
        v_js = expr_to_js(clean_v, extra_funcs=model_funcs)
        true_text = verdict.get("true", "")
        false_text = verdict.get("false", "")
        verdict_text_js = f"Boolean({v_js}) ? {json.dumps(true_text)} : {json.dumps(false_text)}"
        attr_entries.append(_entry(el_id, ".tf-readout-verdict", "textContent", verdict_text_js, "text"))
        class_entries.append({
            "id": el_id,
            "kind": "class",
            "js": f"Boolean({v_js})",
            "trueClass": "tf-verdict-true",
            "falseClass": "tf-verdict-false",
        })

    return attr_entries, class_entries


def _build_bindings(
    spec: Dict[str, Any],
    concrete: Dict[str, Any],
    svg_root: ET.Element,
    model_funcs: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    attr_entries: List[Dict[str, Any]] = []
    class_entries: List[Dict[str, Any]] = []
    vis_entries: List[Dict[str, Any]] = []

    elements = spec.get("elements", [])
    concrete_elements = concrete.get("elements", [])
    for idx, el in enumerate(elements):
        el_type = el.get("type", "box")
        el_id = el.get("id", "")
        cel = concrete_elements[idx] if idx < len(concrete_elements) else {}

        if "visible_when" in el:
            vw = el["visible_when"]
            clean_vw = str(vw).strip()
            if clean_vw.startswith("{{") and clean_vw.endswith("}}"):
                clean_vw = clean_vw[2:-2].strip()
            vw_js = expr_to_js(clean_vw, extra_funcs=model_funcs)
            vis_entries.append({
                "id": el_id,
                "kind": "visibility",
                "js": f"Boolean({vw_js})",
            })

        if el_type == "plot":
            if _is_bound_plot(el):
                attr_entries.extend(_plot_series_bindings(el, cel, el_id, model_funcs=model_funcs))
            continue

        if el_type == "readout":
            r_attr, r_class = _readout_bindings(el, cel, el_id, model_funcs=model_funcs)
            attr_entries.extend(r_attr)
            class_entries.extend(r_class)
            bound: Dict[str, Tuple[str, str]] = {}
            for field, value in el.items():
                if field in ("type", "id", "expr", "format", "label", "unit", "verdict", "visible_when"):
                    continue
                if _contains_binding(value):
                    bound[field] = _value_to_js(value, extra_funcs=model_funcs)
            if bound:
                attr_entries.extend(_entries_for_element(el, cel, el_id, el_type, bound, svg_root))
            continue

        bound = {}
        for field, value in el.items():
            if field in ("type", "id", "visible_when"):
                continue
            if _contains_binding(value):
                bound[field] = _value_to_js(value, extra_funcs=model_funcs)
        if not bound:
            continue
        if el_type in ("polygon", "pen", "compound") and "points" in bound:
            raise ValueError(
                f"interactive binding on {el_type}.points is not supported "
                "(the rendered path involves smoothing/boolean geometry)"
            )
        attr_entries.extend(_entries_for_element(el, cel, el_id, el_type, bound, svg_root))

    connections = spec.get("connections", [])
    for ci, conn in enumerate(connections):
        if "visible_when" in conn:
            conn_id = conn.get("id") or f"tf-conn-{ci}"
            clean_vw = str(conn["visible_when"]).strip()
            if clean_vw.startswith("{{") and clean_vw.endswith("}}"):
                clean_vw = clean_vw[2:-2].strip()
            vw_js = expr_to_js(clean_vw, extra_funcs=model_funcs)
            vis_entries.append({
                "id": conn_id,
                "kind": "visibility",
                "js": f"Boolean({vw_js})",
            })

    return attr_entries + class_entries + vis_entries


# ---- runtime (vanilla JS, no deps) ----------------------------------------

_RUNTIME_JS = r"""(function () {
  function __fmt(x, spec) {
    var v = Number(x);
    var m = /^\.(\d+)f$/.exec(spec);
    if (m) return v.toFixed(parseInt(m[1], 10));
    m = /^\.(\d+)%$/.exec(spec);
    if (m) return (v * 100).toFixed(parseInt(m[1], 10)) + "%";
    m = /^\.(\d+)e$/.exec(spec);
    if (m) {
      var s = v.toExponential(parseInt(m[1], 10));
      return s.replace(/e([+-])(\d)$/, function (_, sign, digits) {
        return "e" + sign + (digits.length < 2 ? "0" + digits : digits);
      });
    }
    if (spec === "d") return String(Math.round(v));
    return String(v);
  }
  function __tf_sum(xs) {
    var s = 0;
    for (var i = 0; i < xs.length; i++) s += xs[i];
    return s;
  }
  function __tf_d(pts) {
    if (!pts || pts.length < 2) return "";
    var s = "M" + pts[0][0] + "," + pts[0][1];
    for (var i = 1; i < pts.length; i++) s += " L" + pts[i][0] + "," + pts[i][1];
    return s;
  }
  function __tf_series_d(xs, ys, ax, bx, ay, by) {
    if (!ys || ys.length === 0) return "";
    var n = (xs && xs.length) ? Math.min(xs.length, ys.length) : ys.length;
    var getX = function (i) { return (xs && xs.length) ? xs[i] : i; };
    var s = "M " + (ax * getX(0) + bx) + " " + (ay * ys[0] + by);
    for (var i = 1; i < n; i++) {
      s += " L " + (ax * getX(i) + bx) + " " + (ay * ys[i] + by);
    }
    return s;
  }

  function valueOf(b, params, model) {
    params = params || {};
    model = model || {};
    var paramNames = Object.keys(params);
    var modelNames = Object.keys(model);
    var args = paramNames.concat(modelNames).concat(["__fmt", "__tf_sum", "__tf_d", "__tf_series_d"]);
    if (!b._fn) {
      b._fn = new Function(args.join(","), "return (" + b.js + ");");
    }
    var vals = [];
    for (var i = 0; i < paramNames.length; i++) {
      vals.push(params[paramNames[i]]);
    }
    for (var j = 0; j < modelNames.length; j++) {
      vals.push(model[modelNames[j]]);
    }
    vals.push(__fmt, __tf_sum, __tf_d, __tf_series_d);
    return b._fn.apply(null, vals);
  }

  function applyBinding(b, params, model) {
    if (typeof document === "undefined" || !document.getElementById) return;
    var el = document.getElementById(b.id);
    if (!el) return;
    if (b.sel) {
      el = el.querySelector(b.sel);
      if (!el) return;
    }
    if (b.kind === "class" || b.kind === "classToggle") {
      var cond = Boolean(valueOf(b, params, model));
      if (cond) {
        if (b.falseClass) el.classList.remove(b.falseClass);
        if (b.trueClass) el.classList.add(b.trueClass);
      } else {
        if (b.trueClass) el.classList.remove(b.trueClass);
        if (b.falseClass) el.classList.add(b.falseClass);
      }
      return;
    }
    if (b.kind === "visibility") {
      var visible = Boolean(valueOf(b, params, model));
      el.style.display = visible ? "" : "none";
      return;
    }
    var v = valueOf(b, params, model);
    if (b.attr === "textContent") {
      el.textContent = v;
      return;
    }
    el.setAttribute(b.attr, String(v));
  }

  function updateFig(fig) {
    if (typeof document === "undefined" || !document.querySelectorAll) return;
    var sel = fig.id ? '.tf-param[data-fig="' + fig.id + '"]' : '.tf-param';
    var controls = document.querySelectorAll(sel);
    for (var i = 0; i < controls.length; i++) {
      var name = controls[i].getAttribute("data-name");
      var v = controls[i].tagName === "SELECT" ? controls[i].value : parseFloat(controls[i].value);
      fig.params[name] = v;
      var outSel = fig.id
        ? 'output.tf-value[data-fig="' + fig.id + '"][data-name="' + name + '"]'
        : 'output.tf-value[data-name="' + name + '"]';
      var outs = document.querySelectorAll(outSel);
      for (var j = 0; j < outs.length; j++) {
        var unit = outs[j].getAttribute("data-unit");
        outs[j].textContent = String(v) + (unit ? " " + unit : "");
      }
    }
    for (var k = 0; k < fig.bindings.length; k++) {
      var b = fig.bindings[k];
      if (b.kind !== "class" && b.kind !== "classToggle" && b.kind !== "visibility") {
        applyBinding(b, fig.params, fig.model);
      }
    }
    for (var k = 0; k < fig.bindings.length; k++) {
      var b = fig.bindings[k];
      if (b.kind === "class" || b.kind === "classToggle") {
        applyBinding(b, fig.params, fig.model);
      }
    }
    for (var k = 0; k < fig.bindings.length; k++) {
      var b = fig.bindings[k];
      if (b.kind === "visibility") {
        applyBinding(b, fig.params, fig.model);
      }
    }
  }

  function register(figId, bindings, params, model) {
    figId = figId || "";
    var fig = {
      id: figId,
      bindings: bindings || [],
      params: params || {},
      model: model || {},
      update: function () { updateFig(fig); }
    };
    tf.figs[figId] = fig;
    if (!tf.bindings || figId === "") {
      tf.bindings = fig.bindings;
      tf.params = fig.params;
      tf.model = fig.model;
      tf.update = function () {
        for (var f in tf.figs) {
          if (tf.figs[f] && tf.figs[f].update) {
            tf.figs[f].update();
          }
        }
      };
    }
    var _forbidden = {
      location: 1, name: 1, top: 1, onload: 1, document: 1,
      window: 1, self: 1, frames: 1, parent: 1, history: 1,
      navigator: 1, status: 1, close: 1, closed: 1, alert: 1,
      confirm: 1, prompt: 1, open: 1, focus: 1, blur: 1,
      origin: 1, event: 1
    };
    for (var p in fig.params) {
      if (typeof globalThis !== "undefined" && typeof globalThis[p] === "undefined") {
        if (!_forbidden[p] && (typeof window === "undefined" || !(p in window))) {
          globalThis[p] = fig.params[p];
        }
      }
    }
    var sel = figId ? '.tf-param[data-fig="' + figId + '"]' : '.tf-param';
    var controls = (typeof document !== "undefined" && document.querySelectorAll) ? document.querySelectorAll(sel) : [];
    for (var n = 0; n < controls.length; n++) {
      controls[n].addEventListener("input", fig.update);
      controls[n].addEventListener("change", fig.update);
    }
    fig.update();
    return fig;
  }

  var tf = (typeof window !== "undefined" && window.__tf) ? window.__tf : {};
  tf.figs = tf.figs || {};
  tf.fmt = __fmt;
  tf.sum = __tf_sum;
  tf.d = __tf_d;
  tf.series_d = __tf_series_d;
  tf.register = register;
  if (typeof window !== "undefined") {
    window.__tf = tf;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__tf = tf;
    globalThis.__tf_series_d = __tf_series_d;
  }
  if (typeof __TF_PARAMS !== "undefined" && typeof __TF_BINDINGS !== "undefined") {
    register("", __TF_BINDINGS, __TF_PARAMS, typeof __TF_MODEL !== "undefined" ? __TF_MODEL : (typeof __tf_model !== "undefined" ? __tf_model : {}));
  }
})();"""


def runtime_js() -> str:
    """Return the vanilla-JS runtime script for interactive figures."""
    return _RUNTIME_JS


# ---- page assembly ---------------------------------------------------------


def _fmt_num(v: float) -> str:
    f = float(v)
    if f.is_integer():
        return str(int(f))
    return repr(f)


def _control_html(p: Dict[str, Any], fig_id: str = "") -> str:
    name = str(p["name"])
    esc_name = html.escape(name, quote=True)
    esc_fig_id = html.escape(fig_id, quote=True) if fig_id else ""
    ctrl_id = f"{esc_fig_id}-p-{esc_name}" if esc_fig_id else f"tf-p-{esc_name}"
    data_fig = f' data-fig="{esc_fig_id}"' if esc_fig_id else ""
    esc_label = html.escape(str(p.get("label", "")), quote=True)
    if p.get("kind") == "state":
        options_html = []
        for opt in p.get("options", []):
            sel = " selected" if opt == p["value"] else ""
            esc_opt = html.escape(str(opt), quote=True)
            options_html.append(f'      <option value="{esc_opt}"{sel}>{esc_opt}</option>')
        opts_str = "\n".join(options_html)
        return (
            f'  <div class="tf-control">\n'
            f'    <label for="{ctrl_id}">{esc_label}</label>\n'
            f'    <select class="tf-param" data-name="{esc_name}"{data_fig} id="{ctrl_id}">\n'
            f'{opts_str}\n'
            f'    </select>\n'
            f'  </div>'
        )
    val = _fmt_num(p["value"])
    unit = str(p["unit"]) if p.get("unit") else ""
    esc_unit = html.escape(unit, quote=True)
    out_text = html.escape(f"{val} {unit}".rstrip(), quote=True)
    data_unit = f' data-unit="{esc_unit}"' if unit else ""
    return (
        f'  <div class="tf-control">\n'
        f'    <label for="{ctrl_id}">{esc_label}</label>\n'
        f'    <input type="range" class="tf-param" data-name="{esc_name}"{data_fig} '
        f'id="{ctrl_id}" min="{_fmt_num(p["min"])}" max="{_fmt_num(p["max"])}" '
        f'step="{_fmt_num(p["step"])}" value="{val}">\n'
        f'    <output class="tf-value" data-name="{esc_name}"{data_fig}{data_unit} '
        f'for="{ctrl_id}">{out_text}</output>\n'
        f"  </div>"
    )


def _css_vars(spec: Dict[str, Any]) -> str:
    style = spec.get("style") or {}
    name = style.get("name", "nature") if isinstance(style, dict) else "nature"
    st = get_style(name)
    colors = st.get("colors", {})
    return (
        f'--tf-primary: {colors.get("primary", "#0072B2")};\n'
        f'--tf-bg: {colors.get("background", "#FFFFFF")};\n'
        f'--tf-fg: {colors.get("text", "#000000")};\n'
        f'--tf-accent: {colors.get("accent", "#009E73")};\n'
        f'--tf-muted: {colors.get("muted", "#888888")};\n'
        f'--tf-gray: #888888;'
    )


def render_interactive_fragment(
    spec: Dict[str, Any],
    fig_id: str = "",
    base_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Render an interactive SVG fragment (controls, SVG, bindings, model).

    Args:
        spec: Diagram spec with optional ``params`` and ``{{expr}}`` bindings.
        fig_id: Optional figure identifier for namespacing (e.g. 'fig1').
        base_dir: Base directory for resolving a relative ``model.file``.

    Returns:
        Dict with keys:
            svg: Inlined SVG markup.
            controls_html: HTML markup for sliders/selects.
            bindings_js: JS code registering bindings and params with the runtime.
            model_js: Transpiled model functions if present.
    """
    spec = copy.deepcopy(spec)

    # 0. Load the model (validates the restricted source on both sides).
    from techfig.engines.model_transpile import module_to_js
    from techfig.engines.params import load_model, load_model_source

    model_js = ""
    model_funcs: List[str] = []
    clean_id = re.sub(r"[^a-zA-Z0-9_]", "_", fig_id) if fig_id else ""
    if spec.get("model"):
        model_source = load_model_source(spec["model"], base_dir)
        raw_model_js = module_to_js(model_source)
        model_funcs = sorted(load_model(spec, base_dir))
        returns_str = ", ".join(f'"{fn}": {fn}' for fn in model_funcs)
        if clean_id:
            model_js = (
                f"var __tf_model_{clean_id} = (function () {{\n"
                f"{raw_model_js}\n"
                f"return {{{returns_str}}};\n"
                f"}})();\n"
            )
        else:
            model_js = (
                f"{raw_model_js}\n"
                f"var __tf_model = {{{returns_str}}};\n"
            )
            _forbidden_globals = {
                "location", "name", "top", "onload", "document", "window", "self",
                "frames", "parent", "history", "navigator", "status", "close",
                "closed", "alert", "confirm", "prompt", "open", "focus", "blur", "origin", "event",
            }
            for fn in model_funcs:
                if fn not in _forbidden_globals:
                    model_js += (
                        f"if (typeof globalThis !== 'undefined' && "
                        f"(typeof window === 'undefined' || !('{fn}' in window))) "
                        f"globalThis.{fn} = {fn};\n"
                    )

    # 1. Validate params.
    raw_params = spec.get("params", [])
    if not isinstance(raw_params, list):
        raise ValueError("'params' must be a list")
    controls: List[Dict[str, Any]] = []
    seen_names = set()
    for p in raw_params:
        if not isinstance(p, dict) or not p.get("name"):
            raise ValueError("Each param must be a dict with a 'name'")
        name = str(p["name"])
        if name in seen_names:
            raise ValueError(f"Duplicate param name: '{name}'")
        seen_names.add(name)
        if not _JS_NAME_RE.match(name):
            raise ValueError(f"Param name '{name}' is not a valid JS identifier")
        kind = p.get("kind", "range")
        if kind not in ("range", "state"):
            raise ValueError(f"Unknown param kind: '{kind}'")
        if kind == "state":
            options = p.get("options")
            if not options or not isinstance(options, list):
                raise ValueError(f"State param '{name}' requires non-empty 'options' list")
            val = str(p.get("value", options[0]))
            controls.append({
                "name": name,
                "kind": "state",
                "options": [str(opt) for opt in options],
                "value": val,
                "label": str(p.get("label") or name),
                "unit": "",
            })
        else:
            for key in ("min", "max", "step", "value"):
                if key not in p:
                    raise ValueError(f"Param '{name}' is missing '{key}'")
            controls.append({
                "name": name,
                "kind": "range",
                "min": float(p["min"]),
                "max": float(p["max"]),
                "step": float(p["step"]),
                "value": float(p["value"]),
                "label": str(p.get("label") or name),
                "unit": str(p.get("unit") or ""),
            })

    prefix = f"{fig_id}-" if fig_id else ""
    elements = spec.get("elements", [])
    connections = spec.get("connections", [])
    id_map = {}
    if prefix:
        for el in elements:
            if el.get("id"):
                old_id = el["id"]
                new_id = f"{prefix}{old_id}"
                id_map[old_id] = new_id
                el["id"] = new_id
        for conn in connections:
            if conn.get("from") in id_map:
                conn["from"] = id_map[conn["from"]]
            if conn.get("to") in id_map:
                conn["to"] = id_map[conn["to"]]
            if conn.get("id"):
                old_id = conn["id"]
                new_id = f"{prefix}{old_id}"
                id_map[old_id] = new_id
                conn["id"] = new_id

    # 2. Ensure every bound element and connection carries an id BEFORE rendering.
    used_ids = {el.get("id") for el in elements if el.get("id")}
    used_ids.update(conn.get("id") for conn in connections if conn.get("id"))
    for idx, el in enumerate(elements):
        has_binding = (
            el.get("type") == "readout"
            or "visible_when" in el
            or any(
                _contains_binding(v)
                for f, v in el.items()
                if f not in ("type", "id")
            )
        )
        if not has_binding or el.get("id"):
            continue
        gen = f"{prefix}tf-el-{idx}"
        while gen in used_ids:
            gen += "x"
        el["id"] = gen
        used_ids.add(gen)

    for ci, conn in enumerate(connections):
        if "visible_when" in conn and not conn.get("id"):
            conn_id = f"{prefix}tf-conn-{ci}"
            while conn_id in used_ids:
                conn_id += "x"
            conn["id"] = conn_id
            used_ids.add(conn_id)

    # 3. Render the concrete SVG at default params via the existing pipeline.
    render_spec = copy.deepcopy(spec)
    bound_plot_ids = set()
    for el in render_spec.get("elements", []):
        if _is_bound_plot(el):
            bound_plot_ids.add(el["id"])
            el["type"] = "box"
            el["opacity"] = 0
            el["stroke_opacity"] = 0
            el["fill_opacity"] = 0
            el.pop("series", None)
            el.pop("data", None)
            el.pop("chart", None)

    tmpdir = tempfile.mkdtemp(prefix="tf_interactive_")
    svg_file = str(Path(tmpdir) / "static.svg")
    render_from_spec(render_spec, svg_file, base_dir=base_dir, skip_hidden=False)
    svg_text = Path(svg_file).read_text(encoding="utf-8")

    # 4. Resolve the concrete spec (same defaults) for geometry constants.
    concrete, _ = resolve_spec(spec, base_dir=base_dir)

    # Replace placeholder groups with native SVG plot groups
    if bound_plot_ids:
        concrete_elements = {cel.get("id"): cel for cel in concrete.get("elements", []) if cel.get("id")}
        for el in spec.get("elements", []):
            if el.get("id") in bound_plot_ids:
                el_id = el["id"]
                cel = concrete_elements.get(el_id, el)
                plot_svg = _render_native_plot_svg(el, cel, el_id, spec.get("style"))
                pat = re.compile(rf'<g id="{re.escape(el_id)}"[^>]*>.*?</g>', re.DOTALL)
                svg_text = pat.sub(plot_svg, svg_text, count=1)

    # Namespace any internal defs/markers not already prefixed
    if prefix:
        def_ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', svg_text))
        unprefixed = [i for i in def_ids if not i.startswith(prefix)]
        unprefixed.sort(key=len, reverse=True)
        for old_id in unprefixed:
            new_id = f"{prefix}{old_id}"
            svg_text = re.sub(r'\bid=(["\'])' + re.escape(old_id) + r'\1', f'id=\\1{new_id}\\1', svg_text)
            svg_text = re.sub(r'url\((["\']?)#' + re.escape(old_id) + r'\1\)', f'url(\\1#{new_id}\\1)', svg_text)
            svg_text = re.sub(r'(href=["\']?)#' + re.escape(old_id) + r'(["\']?)', f'\\1#{new_id}\\2', svg_text)

    # 5. Parse the rendered SVG (rendered label positions, transforms).
    svg_root = ET.fromstring(svg_text.encode("utf-8"))

    # 6. Build the bindings table.
    entries = _build_bindings(spec, concrete, svg_root, model_funcs=model_funcs)

    # 7. Assemble fragment components.
    svg_inline = re.sub(r"^<\?xml[^>]*\?>\s*", "", svg_text).strip()
    bindings_json = json.dumps(entries).replace("<", "\\u003c")
    params_json = json.dumps({c["name"]: c["value"] for c in controls}).replace("<", "\\u003c")
    ctrl_items = [_control_html(c, fig_id=fig_id) for c in controls]
    if ctrl_items:
        ctrl_id_attr = f' id="{html.escape(fig_id, quote=True)}-controls"' if fig_id else ""
        ctrl_fig_attr = f' data-fig="{html.escape(fig_id, quote=True)}"' if fig_id else ""
        controls_html = f'<div class="tf-controls"{ctrl_id_attr}{ctrl_fig_attr}>\n' + "\n".join(ctrl_items) + "\n</div>"
    else:
        controls_html = ""

    if clean_id and model_funcs:
        model_arg = f', typeof __tf_model_{clean_id} !== "undefined" ? __tf_model_{clean_id} : {{}}'
    elif model_funcs:
        model_arg = ', typeof __tf_model !== "undefined" ? __tf_model : {}'
    else:
        model_arg = ""

    bindings_js = f'__tf.register("{fig_id}", {bindings_json}, {params_json}{model_arg});'

    return {
        "svg": svg_inline,
        "controls_html": controls_html,
        "bindings_js": bindings_js,
        "model_js": model_js,
        "entries": entries,
        "controls": controls,
        "bindings_json": bindings_json,
        "params_json": params_json,
    }


def create_interactive_svg(
    spec: dict,
    output_path: str,
    title: str | None = None,
    base_dir: str | None = None,
) -> str:
    """Create a self-contained interactive HTML widget from a parametric spec.

    Args:
        spec: Diagram spec with optional ``params`` and ``{{expr}}`` bindings.
        output_path: Where to write the HTML file.
        title: Optional page title (heading + <title>).
        base_dir: Base directory for resolving a relative ``model.file``
            (typically the directory of the JSON spec file).

    Returns:
        Absolute path to the generated HTML file.
    """
    spec = copy.deepcopy(spec)
    frag = render_interactive_fragment(spec, fig_id="", base_dir=base_dir)

    title_text = title or "Interactive figure"
    heading = f'<h1 class="tf-title">{html.escape(title, quote=True)}</h1>\n' if title else ""
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title_text, quote=True)}</title>
<style>
:root {{
{_css_vars(spec)}
}}
body {{
  font-family: Arial, Helvetica, sans-serif;
  background: var(--tf-bg);
  color: var(--tf-fg);
  max-width: 1000px;
  margin: 24px auto;
  padding: 0 16px;
}}
.tf-title {{ color: var(--tf-primary); }}
.tf-controls {{
  display: flex;
  flex-wrap: wrap;
  gap: 10px 28px;
  padding: 12px 16px;
  border: 1px solid var(--tf-primary);
  border-radius: 8px;
  margin-bottom: 16px;
}}
.tf-control {{ display: flex; align-items: center; gap: 10px; }}
.tf-control label {{ font-weight: 600; font-size: 14px; }}
.tf-control input[type="range"] {{ accent-color: var(--tf-primary); width: 150px; }}
.tf-control select.tf-param {{
  background: var(--tf-bg);
  color: var(--tf-fg);
  border: 1px solid var(--tf-primary);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 14px;
}}
.tf-value {{ min-width: 4.5em; font-variant-numeric: tabular-nums; font-size: 14px; }}
figure {{ margin: 0; }}
figure svg {{ max-width: 100%; height: auto; display: block; }}
.tf-verdict-true {{ fill: var(--tf-accent, #009E73); color: var(--tf-accent, #009E73); }}
.tf-verdict-false {{ fill: var(--tf-muted, #888888); color: var(--tf-muted, #888888); }}
.tf-verdict-true .tf-readout-verdict {{ fill: var(--tf-accent, #009E73); }}
.tf-verdict-false .tf-readout-verdict {{ fill: var(--tf-muted, #888888); }}
</style>
</head>
<body>
{heading}{frag['controls_html']}
<figure>
{frag['svg']}
</figure>
<script>
{frag['model_js']}var __TF_BINDINGS = {frag['bindings_json']};
var __TF_PARAMS = {frag['params_json']};
var __TF_MODEL = typeof __tf_model !== "undefined" ? __tf_model : {{}};
{runtime_js()}
{frag['bindings_js']}
</script>
</body>
</html>
"""
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return str(out)

