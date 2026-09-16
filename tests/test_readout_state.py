"""Tests for readout element, state param kind, and visible_when conditions (T5)."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from techfig.engines.interactive_svg import create_interactive_svg
from techfig.engines.params import UnsafeExpression, resolve_spec
from techfig.engines.sketch_interpreter import render_from_spec, validate_spec


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="tf_test_t5_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def test_readout_static_svg_contains_formatted_text(temp_dir):
    spec = {
        "params": [
            {"name": "R_min", "min": 0.0, "max": 1.0, "step": 0.001, "value": 0.05123, "label": "R_min"},
        ],
        "elements": [
            {
                "type": "readout",
                "id": "r1",
                "x": 100,
                "y": 100,
                "expr": "R_min",
                "format": ".3f",
                "label": "R_min",
                "unit": "%",
                "verdict": {
                    "expr": "R_min < 0.1",
                    "true": "BEATS floor",
                    "false": "—",
                },
            }
        ],
    }

    out_svg = temp_dir / "readout_static.svg"
    render_from_spec(spec, str(out_svg))
    svg_text = out_svg.read_text(encoding="utf-8")

    # Formatted value text: R_min: 0.051 %
    assert "R_min: 0.051 %" in svg_text
    # Second line verdict text
    assert "BEATS floor" in svg_text
    # Verdict class applied to element group
    assert "tf-verdict-true" in svg_text


def test_readout_verdict_false_static_svg(temp_dir):
    spec = {
        "params": [
            {"name": "loss", "min": 0.0, "max": 1.0, "step": 0.01, "value": 0.85},
        ],
        "elements": [
            {
                "type": "readout",
                "id": "r_loss",
                "x": 200,
                "y": 150,
                "expr": "loss",
                "format": ".1f",
                "label": "Loss",
                "verdict": {
                    "expr": "loss < 0.5",
                    "true": "OPTIMAL",
                    "false": "SUB-PAR",
                },
            }
        ],
    }

    out_svg = temp_dir / "readout_loss.svg"
    render_from_spec(spec, str(out_svg))
    svg_text = out_svg.read_text(encoding="utf-8")

    assert "Loss: 0.8" in svg_text
    assert "SUB-PAR" in svg_text
    assert "tf-verdict-false" in svg_text


def test_verdict_class_present_in_interactive_html(temp_dir):
    spec = {
        "params": [
            {"name": "eff", "min": 0, "max": 100, "step": 1, "value": 95},
        ],
        "elements": [
            {
                "type": "readout",
                "id": "r_eff",
                "x": 120,
                "y": 80,
                "expr": "eff",
                "format": "d",
                "label": "Efficiency",
                "unit": "%",
                "verdict": {
                    "expr": "eff >= 90",
                    "true": "PASS",
                    "false": "FAIL",
                },
            }
        ],
    }

    out_html = temp_dir / "readout_interactive.html"
    create_interactive_svg(spec, str(out_html))
    html_text = out_html.read_text(encoding="utf-8")

    # CSS classes present in style
    assert ".tf-verdict-true" in html_text
    assert ".tf-verdict-false" in html_text
    # Initial rendered SVG has the true class at default value (eff=95 >= 90)
    assert "tf-verdict-true" in html_text

    # Check bindings table has class binding
    m = re.search(r"var __TF_BINDINGS = (\[.*?\]);", html_text, re.DOTALL)
    assert m is not None, "__TF_BINDINGS table not found in HTML"
    bindings = json.loads(m.group(1))

    class_bindings = [b for b in bindings if b.get("kind") in ("class", "classToggle")]
    assert len(class_bindings) == 1
    cb = class_bindings[0]
    assert cb["id"] == "r_eff"
    assert cb["trueClass"] == "tf-verdict-true"
    assert cb["falseClass"] == "tf-verdict-false"

    # Value and verdict text bindings
    text_bindings = [b for b in bindings if b.get("attr") == "textContent"]
    assert len(text_bindings) == 2


def test_state_param_renders_select_with_options_and_default(temp_dir):
    spec = {
        "params": [
            {
                "name": "mode",
                "kind": "state",
                "options": ["before", "after", "compare"],
                "value": "before",
                "label": "View Mode",
            }
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": 80, "h": 40, "text": "Base"}
        ],
    }

    out_html = temp_dir / "state_param.html"
    create_interactive_svg(spec, str(out_html))
    html_text = out_html.read_text(encoding="utf-8")

    # Must contain a <select> with class="tf-param" and data-name="mode"
    assert '<select class="tf-param" data-name="mode"' in html_text
    # Default selected option
    assert '<option value="before" selected>before</option>' in html_text
    assert '<option value="after">after</option>' in html_text
    assert '<option value="compare">compare</option>' in html_text
    # Should not render a range input for state params
    assert '<input type="range"' not in html_text


def test_visible_when_hides_statically_and_emits_visibility_binding(temp_dir):
    spec = {
        "params": [
            {
                "name": "state",
                "kind": "state",
                "options": ["before", "after"],
                "value": "before",
            },
        ],
        "elements": [
            {"type": "box", "id": "box_common", "x": 100, "y": 100, "text": "Common"},
            {
                "type": "box",
                "id": "box_after",
                "x": 250,
                "y": 100,
                "text": "Only After",
                "visible_when": "{{state=='after'}}",
            },
        ],
        "connections": [
            {
                "from": "box_common",
                "to": "box_after",
                "id": "conn_after",
                "visible_when": "{{state=='after'}}",
            }
        ],
    }

    # 1. Static SVG: state='before' by default -> box_after and conn_after skipped
    out_svg = temp_dir / "visible_when_static.svg"
    render_from_spec(spec, str(out_svg))
    svg_text = out_svg.read_text(encoding="utf-8")

    assert "Common" in svg_text
    assert "Only After" not in svg_text
    assert 'id="box_after"' not in svg_text

    # 2. Interactive HTML: elements are emitted with visibility bindings
    out_html = temp_dir / "visible_when_interactive.html"
    create_interactive_svg(spec, str(out_html))
    html_text = out_html.read_text(encoding="utf-8")

    # In interactive HTML, the SVG contains box_after so runtime can display it
    assert 'id="box_after"' in html_text

    # Extract bindings table
    m = re.search(r"var __TF_BINDINGS = (\[.*?\]);", html_text, re.DOTALL)
    assert m is not None
    bindings = json.loads(m.group(1))

    vis_bindings = [b for b in bindings if b.get("kind") == "visibility"]
    vis_ids = {b["id"] for b in vis_bindings}
    assert "box_after" in vis_ids
    assert "conn_after" in vis_ids


def test_schema_validation_accepts_readout_and_visible_when_rejects_unknown_kind():
    # Valid spec with readout, visible_when on element and connection, and state param
    valid_spec = {
        "params": [
            {"name": "mode", "kind": "state", "options": ["off", "on"], "value": "off"},
            {"name": "val", "kind": "range", "min": 0, "max": 10, "step": 1, "value": 5},
        ],
        "elements": [
            {
                "type": "readout",
                "id": "r1",
                "x": 50,
                "y": 50,
                "expr": "val",
                "format": ".1f",
                "label": "Reading",
                "unit": "V",
                "verdict": {
                    "expr": "val > 3",
                    "true": "HIGH",
                    "false": "LOW",
                },
                "visible_when": "{{mode=='on'}}",
            },
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": 50, "h": 50},
        ],
        "connections": [
            {"from": "r1", "to": "b1", "visible_when": "{{mode=='on'}}"},
        ],
    }
    issues = validate_spec(valid_spec)
    assert issues == [], f"Expected valid spec to have no issues, got: {issues}"

    # Invalid spec with unknown param kind
    invalid_spec = {
        "params": [
            {"name": "bad_param", "kind": "unknown_kind", "value": 123},
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 10, "y": 10},
        ],
    }
    issues_bad = validate_spec(invalid_spec)
    assert any("unknown kind" in issue.lower() for issue in issues_bad), (
        f"Expected unknown kind error, got: {issues_bad}"
    )


def test_interactive_script_node_syntax_check(temp_dir):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available on PATH")

    spec = {
        "params": [
            {"name": "state", "kind": "state", "options": ["idle", "active"], "value": "idle"},
            {"name": "p_val", "min": 0, "max": 10, "step": 1, "value": 3},
        ],
        "elements": [
            {
                "type": "readout",
                "id": "r_node",
                "x": 100,
                "y": 100,
                "expr": "p_val * 2",
                "format": "d",
                "label": "Double",
                "verdict": {
                    "expr": "p_val > 2",
                    "true": "YES",
                    "false": "NO",
                },
                "visible_when": "{{state=='active'}}",
            }
        ],
    }

    out_html = temp_dir / "node_check.html"
    create_interactive_svg(spec, str(out_html))
    html = out_html.read_text(encoding="utf-8")

    # Extract all <script> contents
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    assert scripts, "No <script> tag found"
    combined_script = "\n".join(scripts)

    # Validate syntax via node --check
    res = subprocess.run(
        [node, "--check"],
        input=combined_script,
        text=True,
        capture_output=True,
    )
    assert res.returncode == 0, f"node --check failed:\n{res.stderr}"


def test_resolve_spec_state_and_readout():
    spec = {
        "params": [
            {"name": "status", "kind": "state", "options": ["idle", "running"], "value": "idle"},
            {"name": "score", "kind": "range", "min": 0, "max": 100, "step": 1, "value": 75},
        ],
        "elements": [
            {
                "type": "readout",
                "expr": "score",
                "verdict": {"expr": "score >= 50", "true": "PASS", "false": "FAIL"},
                "visible_when": "{{status == 'running'}}",
            }
        ],
    }

    # At defaults (status='idle')
    concrete_default, _ = resolve_spec(spec)
    assert concrete_default["elements"][0]["value"] == 75
    assert concrete_default["elements"][0]["verdict"]["value"] is True
    assert concrete_default["elements"][0]["visible_when"] is False

    # Overridden param values (status='running')
    concrete_running, _ = resolve_spec(spec, param_values={"status": "running", "score": 40})
    assert concrete_running["elements"][0]["value"] == 40
    assert concrete_running["elements"][0]["verdict"]["value"] is False
    assert concrete_running["elements"][0]["visible_when"] is True


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_readout_parity_python_and_node(temp_dir):
    """Readout parity test comparing static Python rendering vs live Node JS evaluation."""
    spec = {
        "canvas": {"width": 800, "height": 600},
        "params": [
            {"name": "a", "min": 0, "max": 10, "step": 0.5, "value": 2.5},
            {"name": "b", "min": 0, "max": 10, "step": 1, "value": 0},
            {"name": "c", "min": 0, "max": 10, "step": 0.5, "value": 3.5},
        ],
        "elements": [
            {"type": "readout", "id": "r1", "x": 0, "y": 0, "expr": "a", "format": ".0f", "label": "fmt_half_2_5"},
            {"type": "readout", "id": "r2", "x": 0, "y": 30, "expr": "c", "format": ".0f", "label": "fmt_half_3_5"},
            {"type": "readout", "id": "r3", "x": 0, "y": 60, "expr": "round(a/3, 2)", "label": "round_2arg"},
            {"type": "readout", "id": "r4", "x": 0, "y": 90, "expr": "round(a)", "label": "round_1arg"},
            {"type": "readout", "id": "r5", "x": 0, "y": 120, "expr": "b or 7", "label": "or"},
            {"type": "readout", "id": "r6", "x": 0, "y": 150, "expr": "b != 0 and 1/b > 1", "label": "guard"},
            {"type": "readout", "id": "r7", "x": 0, "y": 180, "expr": "a", "format": "d", "label": "fmt_d"},
            {"type": "readout", "id": "r8", "x": 0, "y": 210, "expr": "min([10, 20, 5])", "label": "min_list"},
            {"type": "readout", "id": "r9", "x": 0, "y": 240, "expr": "max([10, 20, 5])", "label": "max_list"},
        ],
    }
    out_html = temp_dir / "parity_test.html"
    create_interactive_svg(spec, str(out_html))
    html_src = out_html.read_text(encoding="utf-8")

    # Static values from Python rendered SVG
    static_readouts = re.findall(r'class="tf-readout-text"[^>]*>([^<]*)<', html_src)

    # Evaluate in Node
    scripts = re.findall(r"<script(?:\s+[^>]*)?>(.*?)</script>", html_src, re.DOTALL)
    runtime_script = scripts[-1] if scripts else ""

    harness = f"""
function makeEl(id) {{
  var valNode = {{ textContent: "" }};
  return {{
    id: id,
    querySelector: function(sel) {{ return valNode; }},
    valNode: valNode,
    classList: {{ add: function() {{}}, remove: function() {{}} }},
    style: {{}}
  }};
}}
var elements = {{}};
var ids = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8', 'r9'];
for (var i = 0; i < ids.length; i++) {{
  elements[ids[i]] = makeEl(ids[i]);
}}
global.window = {{ __tf: null }};
global.document = {{
  querySelectorAll: function(sel) {{ return []; }},
  getElementById: function(id) {{ return elements[id] || null; }}
}};
{runtime_script}
var live_texts = [];
for (var j = 0; j < ids.length; j++) {{
  live_texts.push(elements[ids[j]].valNode.textContent);
}}
console.log(JSON.stringify(live_texts));
"""
    harness_file = temp_dir / "readout_parity_harness.js"
    harness_file.write_text(harness, encoding="utf-8")
    res = subprocess.run([NODE, str(harness_file)], capture_output=True, text=True)
    assert res.returncode == 0, f"Node run failed: {res.stderr}"
    live_readouts = json.loads(res.stdout)

    assert static_readouts == live_readouts
    # Specific assertions ensuring parity matches requirements
    assert "fmt_half_2_5: 2" in static_readouts
    assert "fmt_half_3_5: 4" in static_readouts
    assert "round_2arg: 0.83" in static_readouts
    assert "or: 7" in static_readouts
    assert "guard: false" in static_readouts
    assert "fmt_d: 2" in static_readouts
    assert "min_list: 5" in static_readouts
    assert "max_list: 20" in static_readouts


def test_swallowed_errors_propagate_unbraced_readout_expr(temp_dir):
    bad = {
        "canvas": {"width": 300, "height": 200},
        "elements": [{"type": "readout", "id": "r", "x": 0, "y": 0, "expr": "undefined_name * 2"}],
    }
    with pytest.raises(UnsafeExpression, match="undefined_name"):
        resolve_spec(bad)
    with pytest.raises(UnsafeExpression, match="undefined_name"):
        render_from_spec(bad, str(temp_dir / "bad_unbraced_readout.svg"))


def test_swallowed_errors_propagate_braced_readout_expr(temp_dir):
    bad = {
        "canvas": {"width": 300, "height": 200},
        "elements": [{"type": "readout", "id": "r", "x": 0, "y": 0, "expr": "{{undefined_name * 2}}"}],
    }
    with pytest.raises(UnsafeExpression, match="undefined_name"):
        resolve_spec(bad)
    with pytest.raises(UnsafeExpression, match="undefined_name"):
        render_from_spec(bad, str(temp_dir / "bad_braced_readout.svg"))


def test_swallowed_errors_propagate_unbraced_visible_when(temp_dir):
    bad = {
        "canvas": {"width": 300, "height": 200},
        "elements": [{"type": "text", "id": "t", "x": 0, "y": 50, "text": "hi", "visible_when": "typo_state == 'x'"}],
    }
    with pytest.raises(UnsafeExpression, match="typo_state"):
        resolve_spec(bad)
    with pytest.raises(UnsafeExpression, match="typo_state"):
        render_from_spec(bad, str(temp_dir / "bad_unbraced_vw.svg"))


def test_swallowed_errors_propagate_braced_visible_when(temp_dir):
    bad = {
        "canvas": {"width": 300, "height": 200},
        "elements": [{"type": "text", "id": "t", "x": 0, "y": 50, "text": "hi", "visible_when": "{{typo_state == 'x'}}"}],
    }
    with pytest.raises(UnsafeExpression, match="typo_state"):
        resolve_spec(bad)
    with pytest.raises(UnsafeExpression, match="typo_state"):
        render_from_spec(bad, str(temp_dir / "bad_braced_vw.svg"))


def test_swallowed_errors_propagate_verdict_expr(temp_dir):
    bad = {
        "canvas": {"width": 300, "height": 200},
        "elements": [
            {
                "type": "readout",
                "id": "r",
                "x": 0,
                "y": 0,
                "expr": "1",
                "verdict": {"expr": "undefined_cond > 0", "true": "yes", "false": "no"},
            }
        ],
    }
    with pytest.raises(UnsafeExpression, match="undefined_cond"):
        resolve_spec(bad)
    with pytest.raises(UnsafeExpression, match="undefined_cond"):
        render_from_spec(bad, str(temp_dir / "bad_verdict.svg"))


