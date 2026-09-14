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
    "text": "text", "callout": "text",
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
}

_COMMON_STYLE = {
    "color", "stroke_color", "fill_opacity", "stroke_opacity",
    "stroke_dash", "stroke_width", "opacity", "rotation",
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
    | {"x", "y", "text", "font_size"},
    "line": (_COMMON_STYLE - {"rotation", "fill_opacity"})
    | {"x1", "y1", "x2", "y2"},
    "arrow": (_COMMON_STYLE - {"rotation", "fill_opacity"})
    | {"x1", "y1", "x2", "y2", "curve"},
    "path": (_COMMON_STYLE - {"rotation", "fill_opacity"}) | {"points"},
    "polygon": _COMMON_STYLE | {"text"},
    "pen": _COMMON_STYLE | {"text"},
    "compound": _COMMON_STYLE | {"text"},
    "legend": _COMMON_STYLE | {"x", "y", "w", "h"},
    "image": {"opacity"} | {"x", "y", "w", "h"},
    "plot": set(),
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


def _contains_binding(value: Any) -> bool:
    if isinstance(value, str):
        return _BINDING_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_binding(v) for v in value)
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


def _build_bindings(
    spec: Dict[str, Any],
    concrete: Dict[str, Any],
    svg_root: ET.Element,
    model_funcs: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    elements = spec.get("elements", [])
    concrete_elements = concrete.get("elements", [])
    for idx, el in enumerate(elements):
        bound: Dict[str, Tuple[str, str]] = {}
        for field, value in el.items():
            if field in ("type", "id"):
                continue
            if _contains_binding(value):
                bound[field] = _value_to_js(value, extra_funcs=model_funcs)
        if not bound:
            continue
        el_id = el.get("id", "")
        el_type = el.get("type", "box")
        cel = concrete_elements[idx]
        if el_type in ("polygon", "pen", "compound") and "points" in bound:
            raise ValueError(
                f"interactive binding on {el_type}.points is not supported "
                "(the rendered path involves smoothing/boolean geometry)"
            )
        entries.extend(_entries_for_element(el, cel, el_id, el_type, bound, svg_root))
    return entries


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
  var PARAM_NAMES = Object.keys(__TF_PARAMS);
  var ARGS = PARAM_NAMES.concat(["__fmt", "__tf_sum", "__tf_d"]);
  function valueOf(b) {
    if (!b._fn) {
      b._fn = new Function(ARGS.join(","), "return (" + b.js + ");");
    }
    var vals = [];
    for (var i = 0; i < PARAM_NAMES.length; i++) {
      vals.push(__TF_PARAMS[PARAM_NAMES[i]]);
    }
    vals.push(__fmt, __tf_sum, __tf_d);
    return b._fn.apply(null, vals);
  }
  function applyBinding(b) {
    var el = document.getElementById(b.id);
    if (!el) return;
    if (b.sel) {
      el = el.querySelector(b.sel);
      if (!el) return;
    }
    var v = valueOf(b);
    if (b.attr === "textContent") {
      el.textContent = v;
      return;
    }
    el.setAttribute(b.attr, String(v));
  }
  function update() {
    var inputs = document.querySelectorAll("input.tf-param");
    for (var i = 0; i < inputs.length; i++) {
      var name = inputs[i].getAttribute("data-name");
      var v = parseFloat(inputs[i].value);
      __TF_PARAMS[name] = v;
      var outs = document.querySelectorAll('output.tf-value[data-name="' + name + '"]');
      for (var j = 0; j < outs.length; j++) {
        var unit = outs[j].getAttribute("data-unit");
        outs[j].textContent = String(v) + (unit ? " " + unit : "");
      }
    }
    for (var k = 0; k < __TF_BINDINGS.length; k++) applyBinding(__TF_BINDINGS[k]);
  }
  var inputs = document.querySelectorAll("input.tf-param");
  for (var n = 0; n < inputs.length; n++) {
    inputs[n].addEventListener("input", update);
  }
  window.__tf = { params: __TF_PARAMS, update: update, bindings: __TF_BINDINGS, fmt: __fmt };
  update();
})();"""


# ---- page assembly ---------------------------------------------------------


def _fmt_num(v: float) -> str:
    f = float(v)
    if f.is_integer():
        return str(int(f))
    return repr(f)


def _control_html(p: Dict[str, Any]) -> str:
    name = p["name"]
    val = _fmt_num(p["value"])
    out_text = f"{val} {p['unit']}".rstrip()
    data_unit = f' data-unit="{p["unit"]}"' if p["unit"] else ""
    return (
        f'  <div class="tf-control">\n'
        f'    <label for="tf-p-{name}">{p["label"]}</label>\n'
        f'    <input type="range" class="tf-param" data-name="{name}" '
        f'id="tf-p-{name}" min="{_fmt_num(p["min"])}" max="{_fmt_num(p["max"])}" '
        f'step="{_fmt_num(p["step"])}" value="{val}">\n'
        f'    <output class="tf-value" data-name="{name}"{data_unit} '
        f'for="tf-p-{name}">{out_text}</output>\n'
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
        f'--tf-accent: {colors.get("accent", "#009E73")};'
    )


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

    # 0. Load the model (validates the restricted source on both sides).
    from techfig.engines.model_transpile import module_to_js
    from techfig.engines.params import load_model, load_model_source

    model_js = ""
    model_funcs: List[str] = []
    if spec.get("model"):
        model_source = load_model_source(spec["model"], base_dir)
        model_js = module_to_js(model_source) + "\n"
        model_funcs = sorted(load_model(spec, base_dir))

    # 0. Validate params.
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
        for key in ("min", "max", "step", "value"):
            if key not in p:
                raise ValueError(f"Param '{name}' is missing '{key}'")
        controls.append({
            "name": name,
            "min": float(p["min"]),
            "max": float(p["max"]),
            "step": float(p["step"]),
            "value": float(p["value"]),
            "label": str(p.get("label") or name),
            "unit": str(p.get("unit") or ""),
        })

    # 1. Ensure every bound element carries an id BEFORE rendering.
    elements = spec.get("elements", [])
    used_ids = {el.get("id") for el in elements if el.get("id")}
    for idx, el in enumerate(elements):
        has_binding = any(
            _contains_binding(v)
            for f, v in el.items()
            if f not in ("type", "id")
        )
        if not has_binding or el.get("id"):
            continue
        gen = f"tf-el-{idx}"
        while gen in used_ids:
            gen += "x"
        el["id"] = gen
        used_ids.add(gen)

    # 2. Render the concrete SVG at default params via the existing pipeline.
    tmpdir = tempfile.mkdtemp(prefix="tf_interactive_")
    svg_file = str(Path(tmpdir) / "static.svg")
    render_from_spec(spec, svg_file, base_dir=base_dir)
    svg_text = Path(svg_file).read_text(encoding="utf-8")

    # 3. Resolve the concrete spec (same defaults) for geometry constants.
    concrete, _ = resolve_spec(spec, base_dir=base_dir)

    # 4. Parse the rendered SVG (rendered label positions, transforms).
    svg_root = ET.fromstring(svg_text.encode("utf-8"))

    # 5. Build the bindings table.
    entries = _build_bindings(spec, concrete, svg_root, model_funcs=model_funcs)

    # 6. Assemble the page.
    svg_inline = re.sub(r"^<\?xml[^>]*\?>\s*", "", svg_text).strip()
    bindings_json = json.dumps(entries).replace("</", "<\\/")
    params_json = json.dumps({c["name"]: c["value"] for c in controls})
    controls_html = "\n".join(_control_html(c) for c in controls)
    title_text = title or "Interactive figure"
    heading = f'<h1 class="tf-title">{title}</h1>\n' if title else ""
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_text}</title>
<style>
:root {{
{_css_vars(spec)}
}}
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
.tf-value {{ min-width: 4.5em; font-variant-numeric: tabular-nums; font-size: 14px; }}
figure {{ margin: 0; }}
figure svg {{ max-width: 100%; height: auto; display: block; }}
</style>
</head>
<body>
{heading}<div class="tf-controls">
{controls_html}
</div>
<figure>
{svg_inline}
</figure>
<script>
{model_js}var __TF_BINDINGS = {bindings_json};
var __TF_PARAMS = {params_json};
{_RUNTIME_JS}
</script>
</body>
</html>
"""
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return str(out)
