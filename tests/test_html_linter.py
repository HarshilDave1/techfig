"""Tests for HTML linter (T7: critique --html)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from techfig.engines.html_linter import lint_html
from techfig.engines.interactive_svg import create_interactive_svg

try:
    import playwright  # noqa: F401
    from playwright.sync_api import sync_playwright  # noqa: F401
    PLAYWRIGHT_AVAILABLE = True
except (ImportError, Exception):
    PLAYWRIGHT_AVAILABLE = False

skip_without_playwright = pytest.mark.skipif(
    not PLAYWRIGHT_AVAILABLE, reason="playwright is not available"
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="tf_test_t7_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@skip_without_playwright
def test_report_keys_present(temp_dir):
    """Verify that report keys (score, issues, inert_controls, text_overlaps, js_errors) are present."""
    spec = {
        "params": [
            {"name": "width", "min": 50, "max": 150, "step": 5, "value": 100},
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": "{{width}}", "h": 60},
        ],
    }
    out_html = temp_dir / "valid_page.html"
    create_interactive_svg(spec, str(out_html))

    report = lint_html(str(out_html))

    for key in ("score", "issues", "inert_controls", "text_overlaps", "js_errors"):
        assert key in report, f"Expected key '{key}' in report"

    assert isinstance(report["score"], float)
    assert 0.0 <= report["score"] <= 1.0
    assert isinstance(report["issues"], list)
    assert isinstance(report["inert_controls"], list)
    assert isinstance(report["text_overlaps"], dict)
    assert isinstance(report["js_errors"], list)
    assert report["score"] == 1.0
    assert len(report["inert_controls"]) == 0
    assert len(report["js_errors"]) == 0


@skip_without_playwright
def test_inert_control_detected(temp_dir):
    """Build an interactive page where one param is deliberately unused.

    The unused slider is reported inert and the used one is not.
    """
    spec = {
        "params": [
            {"name": "used_param", "min": 20, "max": 120, "step": 5, "value": 50},
            {"name": "dead_param", "min": 10, "max": 90, "step": 1, "value": 30},
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": "{{used_param}}", "h": 60},
            {"type": "text", "id": "t1", "x": 100, "y": 100, "text": "Label"},
        ],
    }
    out_html = temp_dir / "inert_test.html"
    create_interactive_svg(spec, str(out_html))

    report = lint_html(str(out_html))

    assert "dead_param" in report["inert_controls"]
    assert "used_param" not in report["inert_controls"]
    # Score has 0.3 deduction for inert controls
    assert report["score"] <= 0.7


@skip_without_playwright
def test_readouts_populated(temp_dir):
    """Readouts populated correctly at load; invalid or missing readouts flagged."""
    spec = {
        "params": [
            {"name": "val", "min": 10, "max": 50, "step": 5, "value": 20},
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": "{{val * 2}}", "h": 60},
            {
                "type": "readout",
                "id": "r1",
                "x": 200,
                "y": 100,
                "expr": "val * 2",
                "format": "d",
                "label": "Metric",
                "verdict": {
                    "expr": "val > 15",
                    "true": "OK",
                    "false": "LOW",
                },
            },
        ],
    }
    out_html = temp_dir / "readout_page.html"
    create_interactive_svg(spec, str(out_html))

    report = lint_html(str(out_html))
    readout_issues = [i for i in report["issues"] if "readout" in i.lower() or "value" in i.lower()]
    assert len(readout_issues) == 0

    # Inject an unpopulated readout element into an HTML page
    raw_html = out_html.read_text(encoding="utf-8")
    bad_html = raw_html.replace(
        "</body>",
        '<output class="tf-value" id="val_uninit">-</output>'
        '<g class="tf-readout" id="readout_uninit">NaN</g></body>',
    )
    bad_page = temp_dir / "bad_readout.html"
    bad_page.write_text(bad_html, encoding="utf-8")

    report_bad = lint_html(str(bad_page))
    bad_issues = [i for i in report_bad["issues"] if "readout" in i.lower() or "value" in i.lower()]
    assert len(bad_issues) >= 2
    assert any("val_uninit" in i for i in bad_issues)
    assert any("readout_uninit" in i for i in bad_issues)


@skip_without_playwright
def test_text_overlaps_at_max_state(temp_dir):
    """A page with two overlapping texts at max state reports an overlap pair."""
    spec = {
        "params": [
            {"name": "pos", "min": 0, "max": 400, "step": 1, "value": 0},
        ],
        "elements": [
            {"type": "text", "id": "txt1", "x": 400, "y": 100, "text": "COLLIDE_ALPHA"},
            {"type": "text", "id": "txt2", "x": "{{pos}}", "y": 100, "text": "COLLIDE_BETA"},
        ],
    }
    out_html = temp_dir / "overlap_page.html"
    create_interactive_svg(spec, str(out_html))

    report = lint_html(str(out_html), states=("min", "mid", "max"))

    assert "max" in report["text_overlaps"]
    max_overlaps = report["text_overlaps"]["max"]
    assert len(max_overlaps) >= 1

    flat_pairs = [set(p) for p in max_overlaps]
    # Check that txt1 and txt2 are reported as an overlapping pair
    assert any({"txt1", "txt2"}.issubset(p) or {"COLLIDE_ALPHA", "COLLIDE_BETA"}.issubset(p) for p in flat_pairs)

    # At min state (pos=0), txt1 is at 400, txt2 is at 0: no overlap
    assert len(report["text_overlaps"].get("min", [])) == 0


@skip_without_playwright
def test_http_server_fallback(temp_dir):
    """Test fallback to ephemeral HTTP server when file:// navigation fails."""
    spec = {
        "params": [
            {"name": "w", "min": 50, "max": 100, "step": 5, "value": 75},
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": "{{w}}", "h": 50},
        ],
    }
    out_html = temp_dir / "server_fallback.html"
    create_interactive_svg(spec, str(out_html))

    # _force_http_server forces the linter to use ephemeral http.server
    report = lint_html(str(out_html), _force_http_server=True)
    assert report["ok"] is True
    assert report["score"] == 1.0


@skip_without_playwright
def test_cli_critique_html(temp_dir):
    """Test CLI `techfig critique --html page.html [--json]`."""
    import subprocess
    import sys

    spec = {
        "params": [
            {"name": "w", "min": 20, "max": 80, "step": 5, "value": 40},
            {"name": "dead", "min": 0, "max": 10, "step": 1, "value": 5},
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": "{{w}}", "h": 50},
        ],
    }
    out_html = temp_dir / "cli_test.html"
    create_interactive_svg(spec, str(out_html))

    # Test human-readable output
    res = subprocess.run(
        [sys.executable, "-m", "techfig.cli", "critique", "--html", str(out_html)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "HTML Critique Report" in res.stdout
    assert "Score:" in res.stdout
    assert "dead" in res.stdout

    # Test --json output
    res_json = subprocess.run(
        [sys.executable, "-m", "techfig.cli", "critique", "--html", str(out_html), "--json"],
        capture_output=True,
        text=True,
    )
    assert res_json.returncode == 0
    data = json.loads(res_json.stdout)
    assert data["ok"] is True
    assert "dead" in data["inert_controls"]
    assert "score" in data


@skip_without_playwright
def test_multi_figure_identical_labels_no_cross_figure_overlap(temp_dir):
    """Two figures on the same page with identical labels must not report cross-figure overlaps."""
    page_html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
  <div id="fig1">
    <svg width="400" height="200">
      <text id="fig1-title" x="50" y="50">Diagram Title</text>
      <text id="fig1-axis" x="50" y="100">Wavelength (nm)</text>
    </svg>
  </div>
  <div id="fig2">
    <svg width="400" height="200">
      <text id="fig2-title" x="50" y="50">Diagram Title</text>
      <text id="fig2-axis" x="50" y="100">Wavelength (nm)</text>
    </svg>
  </div>
</body>
</html>"""
    html_file = temp_dir / "two_figures.html"
    html_file.write_text(page_html, encoding="utf-8")

    report = lint_html(str(html_file))
    assert report["ok"] is True
    assert report["score"] == 1.0
    all_overlaps = [p for pairs in report["text_overlaps"].values() for p in pairs]
    assert len(all_overlaps) == 0


@skip_without_playwright
def test_deeply_nested_hidden_element_not_flagged(temp_dir):
    """Text nested deeper than 1 parent inside a display:none group must not count towards overlaps."""
    page_html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
  <svg width="400" height="200">
    <text id="visible_txt" x="50" y="50">Visible Text</text>
    <g style="display: none">
      <g>
        <g>
          <text id="deep_hidden_txt" x="50" y="50">Visible Text</text>
        </g>
      </g>
    </g>
  </svg>
</body>
</html>"""
    html_file = temp_dir / "deep_hidden.html"
    html_file.write_text(page_html, encoding="utf-8")

    report = lint_html(str(html_file))
    assert report["ok"] is True
    all_overlaps = [p for pairs in report["text_overlaps"].values() for p in pairs]
    assert len(all_overlaps) == 0


@skip_without_playwright
def test_shipped_explainer_clean_score():
    """Shipped arc_thin_film explainer.html should have 0 overlap pairs and clean score."""
    repo_root = Path(__file__).resolve().parent.parent
    explainer_html = repo_root / "examples" / "arc_thin_film" / "explainer.html"
    assert explainer_html.is_file()

    report = lint_html(str(explainer_html))
    assert report["ok"] is True
    all_overlaps = [p for pairs in report["text_overlaps"].values() for p in pairs]
    # Zero within-figure or cross-figure overlaps
    assert len(all_overlaps) == 0
    assert report["score"] == 1.0

