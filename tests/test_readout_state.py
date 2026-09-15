"""Tests for readout element, state param kind, and visible_when conditions (T5)."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from techfig.engines.interactive_svg import create_interactive_svg
from techfig.engines.params import resolve_spec
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

