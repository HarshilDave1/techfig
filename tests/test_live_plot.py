"""Tests for T4: live native-SVG plot element in interactive mode.

Covers:
- Native SVG rendering for bound plot elements in create_interactive_svg.
- Point count assertion (count of L commands == len(xs) - 1).
- ylim respected (all y coordinates in path d within frame).
- Static matplotlib path preserved for unbound plots in interactive mode.
- Python initial d equals string produced by evaluating JS binding in Node.
- linear_scale helper behavior.
"""
import json
import re
import shutil
import subprocess
from xml.etree import ElementTree as ET

import pytest

from techfig.engines.interactive_svg import create_interactive_svg, linear_scale

NODE = shutil.which("node")

_MODEL_SOURCE = """def get_xs():
    res = []
    for i in range(16):
        res.append(i * 1.0)
    return res

def get_ys(amp):
    res = []
    for i in range(16):
        res.append(amp * (i * 0.1))
    return res
"""


def _bound_plot_spec(xlim=None, ylim=None):
    el = {
        "type": "plot",
        "id": "plot1",
        "x": 0,
        "y": 0,
        "w": 400,
        "h": 300,
        "xlabel": "Time (s)",
        "ylabel": "Signal",
        "series": [
            {
                "x": "{{get_xs()}}",
                "y": "{{get_ys(amp)}}",
                "label": "Response",
            }
        ],
    }
    if xlim is not None:
        el["xlim"] = xlim
    if ylim is not None:
        el["ylim"] = ylim
    return {
        "canvas": {"width": 800, "height": 600},
        "style": {"name": "nature"},
        "params": [
            {"name": "amp", "min": 0, "max": 10, "step": 1, "value": 2.0, "label": "Amplitude"},
        ],
        "model": {"source": _MODEL_SOURCE},
        "elements": [el],
    }


def _extract_path_points(d_str: str):
    """Parse 'M x y L x y ...' path into [(cmd, x, y), ...]."""
    tokens = d_str.strip().split()
    points = []
    i = 0
    cmd = None
    while i < len(tokens):
        if tokens[i] in ("M", "L"):
            cmd = tokens[i]
            x = float(tokens[i + 1])
            y = float(tokens[i + 2])
            points.append((cmd, x, y))
            i += 3
        else:
            i += 1
    return points


def test_linear_scale_helper():
    # Regular mapping
    a, b = linear_scale([0, 10], [100, 300])
    assert abs(a - 20.0) < 1e-9
    assert abs(b - 100.0) < 1e-9
    assert abs(a * 0 + b - 100) < 1e-9
    assert abs(a * 10 + b - 300) < 1e-9
    assert abs(a * 5 + b - 200) < 1e-9

    # Inverted y mapping
    ay, by = linear_scale([0, 1], [300, 100])
    assert abs(ay - (-200.0)) < 1e-9
    assert abs(by - 300.0) < 1e-9
    assert abs(ay * 0 + by - 300) < 1e-9
    assert abs(ay * 1 + by - 100) < 1e-9

    # Constant domain edge case
    a_zero, b_zero = linear_scale([5, 5], [50, 100])
    assert a_zero == 0.0
    assert b_zero == 50.0


def test_bound_plot_contains_path_with_n_points(tmp_path):
    spec = _bound_plot_spec(xlim=[0, 15], ylim=[0, 5])
    out_file = tmp_path / "plot.html"
    create_interactive_svg(spec, str(out_file))

    content = out_file.read_text(encoding="utf-8")
    assert "<svg" in content

    # Find the plot group and series path
    root = ET.fromstring(re.search(r"<svg[^>]*>.*?</svg>", content, re.DOTALL).group(0))
    series_paths = [p for p in root.iter() if "tf-series" in p.get("class", "")]
    assert len(series_paths) == 1, "Expected exactly 1 tf-series path"

    d = series_paths[0].get("d", "")
    assert d.startswith("M ")

    # Number of points in get_xs() is 16
    pts = _extract_path_points(d)
    assert len(pts) == 16

    # Actual point counts: exactly 15 'L' commands (len(xs) - 1)
    l_commands = [cmd for cmd, _, _ in pts if cmd == "L"]
    assert len(l_commands) == 15

    # Count of 'L' commands via string search matches len(xs) - 1
    assert d.count(" L ") == 15


def test_bound_plot_ylim_respected(tmp_path):
    # Set explicit ylim [0, 4]
    spec = _bound_plot_spec(xlim=[0, 15], ylim=[0, 4])
    out_file = tmp_path / "plot.html"
    create_interactive_svg(spec, str(out_file))

    content = out_file.read_text(encoding="utf-8")
    root = ET.fromstring(re.search(r"<svg[^>]*>.*?</svg>", content, re.DOTALL).group(0))

    # Frame rect
    frame_rects = [r for r in root.iter() if "tf-plot-frame" in r.get("class", "")]
    assert len(frame_rects) == 1
    rect = frame_rects[0]
    frame_y = float(rect.get("y"))
    frame_h = float(rect.get("height"))
    top = frame_y
    bottom = frame_y + frame_h

    # Series path
    series_paths = [p for p in root.iter() if "tf-series" in p.get("class", "")]
    pts = _extract_path_points(series_paths[0].get("d", ""))

    for _, _, py in pts:
        assert top - 1e-6 <= py <= bottom + 1e-6, f"y={py} out of frame [{top}, {bottom}]"


def test_bound_plot_auto_limits_with_padding(tmp_path):
    # Spec without xlim/ylim: auto-computed with 10% padding
    spec = _bound_plot_spec(xlim=None, ylim=None)
    out_file = tmp_path / "plot.html"
    create_interactive_svg(spec, str(out_file))

    content = out_file.read_text(encoding="utf-8")
    root = ET.fromstring(re.search(r"<svg[^>]*>.*?</svg>", content, re.DOTALL).group(0))

    frame_rects = [r for r in root.iter() if "tf-plot-frame" in r.get("class", "")]
    assert len(frame_rects) == 1
    rect = frame_rects[0]
    frame_y = float(rect.get("y"))
    frame_h = float(rect.get("height"))
    top = frame_y
    bottom = frame_y + frame_h

    series_paths = [p for p in root.iter() if "tf-series" in p.get("class", "")]
    pts = _extract_path_points(series_paths[0].get("d", ""))

    # All points must be strictly within frame bounds (because 10% padding was added)
    for _, _, py in pts:
        assert top <= py <= bottom


def test_unbound_plot_embeds_matplotlib(tmp_path):
    spec = {
        "canvas": {"width": 800, "height": 600},
        "style": {"name": "nature"},
        "elements": [
            {
                "type": "plot",
                "id": "static_chart",
                "x": 0,
                "y": 0,
                "w": 300,
                "h": 200,
                "chart": {
                    "type": "bar",
                    "data": {"category": ["A", "B", "C"], "value": [10, 20, 15]},
                },
            }
        ],
    }
    out_file = tmp_path / "unbound.html"
    create_interactive_svg(spec, str(out_file))

    content = out_file.read_text(encoding="utf-8")
    # Must preserve matplotlib output marker
    assert (
        "matplotlib" in content
        or "figure_1" in content
        or "patch_1" in content
        or "axes_1" in content
    ), "Matplotlib output marker not found in unbound plot"
    assert "tf-series" not in content


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_python_initial_d_matches_node_evaluation(tmp_path):
    spec = _bound_plot_spec(xlim=[0, 15], ylim=[0, 5])
    out_file = tmp_path / "plot.html"
    create_interactive_svg(spec, str(out_file))

    content = out_file.read_text(encoding="utf-8")

    # Extract initial d from the SVG
    root = ET.fromstring(re.search(r"<svg[^>]*>.*?</svg>", content, re.DOTALL).group(0))
    series_paths = [p for p in root.iter() if "tf-series" in p.get("class", "")]
    assert len(series_paths) == 1
    py_initial_d = series_paths[0].get("d")

    # Find the d binding in __TF_BINDINGS
    m_bindings = re.search(r"var __TF_BINDINGS = (\[.*?\]);\n", content, re.DOTALL)
    assert m_bindings, "bindings table not found"
    bindings = json.loads(m_bindings.group(1))
    d_bindings = [b for b in bindings if b.get("attr") == "d"]
    assert len(d_bindings) == 1

    # Extract runtime script
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", content, re.DOTALL)
    assert scripts
    script_text = scripts[-1]

    # Evaluate in node: execute the script harness and evaluate the binding at defaults
    harness = f"""
global.window = {{__tf: null}};
global.document = {{
    querySelectorAll: function () {{ return []; }},
    getElementById: function () {{ return null; }}
}};
{script_text}
var targetBinding = window.__tf.bindings.filter(function (b) {{ return b.attr === 'd'; }})[0];
var nodeD = (new Function("return (" + targetBinding.js + ");"))();
console.log(JSON.stringify(nodeD));
"""
    harness_file = tmp_path / "eval_harness.js"
    harness_file.write_text(harness, encoding="utf-8")

    res = subprocess.run([NODE, str(harness_file)], capture_output=True, text=True)
    assert res.returncode == 0, f"Node execution failed: {res.stderr}"
    node_d = json.loads(res.stdout.strip())

    assert py_initial_d == node_d, f"Python initial d != node evaluated d:\nPy:   {py_initial_d}\nNode: {node_d}"


def test_multiple_series_plot(tmp_path):
    model_source = """def curve1():
    return [1.0, 2.0, 3.0, 4.0]

def curve2():
    return [4.0, 3.0, 2.0, 1.0]

def get_x():
    return [0.0, 1.0, 2.0, 3.0]
"""
    spec = {
        "canvas": {"width": 800, "height": 600},
        "style": {"name": "nature"},
        "params": [{"name": "p", "min": 0, "max": 1, "step": 1, "value": 0}],
        "model": {"source": model_source},
        "elements": [
            {
                "type": "plot",
                "id": "multi_plot",
                "x": 0,
                "y": 0,
                "w": 400,
                "h": 300,
                "series": [
                    {"x": "{{get_x()}}", "y": "{{curve1()}}", "label": "Up"},
                    {"x": "{{get_x()}}", "y": "{{curve2()}}", "label": "Down"},
                ],
            }
        ],
    }
    out_file = tmp_path / "multi.html"
    create_interactive_svg(spec, str(out_file))

    content = out_file.read_text(encoding="utf-8")
    root = ET.fromstring(re.search(r"<svg[^>]*>.*?</svg>", content, re.DOTALL).group(0))

    series_paths = [p for p in root.iter() if "tf-series" in p.get("class", "")]
    assert len(series_paths) == 2

    # Different stroke colors from palette
    stroke0 = series_paths[0].get("stroke")
    stroke1 = series_paths[1].get("stroke")
    assert stroke0 != stroke1

    # Both paths have bindings
    m_bindings = re.search(r"var __TF_BINDINGS = (\[.*?\]);\n", content, re.DOTALL)
    bindings = json.loads(m_bindings.group(1))
    d_bindings = [b for b in bindings if b.get("attr") == "d"]
    assert len(d_bindings) == 2
    assert {b["id"] for b in d_bindings} == {series_paths[0].get("id"), series_paths[1].get("id")}
