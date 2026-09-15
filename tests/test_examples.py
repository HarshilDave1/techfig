"""Tests for example pipelines (T8: ARC thin film explainer example)."""
import json
import re
from pathlib import Path

from techfig.engines.explain import assemble_explainer_page
from techfig.engines.interactive_svg import create_interactive_svg
from techfig.engines.model_transpile import verify_model
from techfig.engines.params import load_model_source
from techfig.engines.sketch_interpreter import render_from_json


def test_arc_thin_film_example(tmp_path):
    """Build the arc_thin_film example via the Python API and verify programmatic assertions."""
    repo_root = Path(__file__).resolve().parent.parent
    example_dir = repo_root / "examples" / "arc_thin_film"
    spec_path = example_dir / "spec.json"
    explainer_path = example_dir / "explainer.md"

    assert spec_path.is_file(), f"Missing {spec_path}"
    assert explainer_path.is_file(), f"Missing {explainer_path}"

    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    # 1. verify-model ok
    assert "model" in spec
    source = load_model_source(spec["model"], base_dir=str(example_dir))
    param_ranges = {
        p["name"]: (float(p["min"]), float(p["max"]))
        for p in spec.get("params", [])
        if isinstance(p, dict) and "min" in p and "max" in p
    }
    report = verify_model(source, param_ranges)
    # If node is present, verify numerical cross-check succeeds; if absent, ok is None (skipped)
    assert report.get("ok") in (True, None)
    assert report.get("mismatches") == []

    # Also cross-check R across its physical parameter ranges
    r_ranges = {
        "n0": (1.0, 1.0),
        "n1": (1.2, 2.4),
        "n2": (1.5, 1.5),
        "d": (50.0, 200.0),
        "lam": (400.0, 800.0),
    }
    r_report = verify_model(source, r_ranges)
    assert r_report.get("ok") in (True, None)
    if r_report.get("ok") is True:
        assert r_report["n_checked"] > 0
        assert r_report["max_abs_err"] < 1e-9

    # 2. static SVG > 2 KB
    out_svg = tmp_path / "diagram.svg"
    render_from_json(str(spec_path), str(out_svg))
    assert out_svg.is_file()
    assert out_svg.stat().st_size > 2048, f"Static SVG size ({out_svg.stat().st_size} bytes) <= 2 KB"

    # 3. interactive HTML contains 3 range inputs + 1 select
    out_html = tmp_path / "widget.html"
    create_interactive_svg(spec, str(out_html), base_dir=str(example_dir))
    assert out_html.is_file()
    html_text = out_html.read_text(encoding="utf-8")

    range_inputs = re.findall(r'<input[^>]*type=[\'"]range[\'"]', html_text)
    select_inputs = re.findall(r"<select\b", html_text)
    assert len(range_inputs) == 3, f"Expected 3 range inputs, found {len(range_inputs)}"
    assert len(select_inputs) == 1, f"Expected 1 select input, found {len(select_inputs)}"

    # 4. Explainer page assembly
    out_explainer = tmp_path / "explainer.html"
    assemble_explainer_page(explainer_path, out_explainer)
    assert out_explainer.is_file()
    assert out_explainer.stat().st_size > 2048
