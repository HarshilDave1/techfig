"""Test the batch generation engine."""
import json
import os
import pytest
import pandas as pd
from techfig.engines.batch import batch_generate


@pytest.fixture
def sample_csv(tmp_path):
    df = pd.DataFrame({"x": ["A", "B", "C"], "y": [1, 2, 3]})
    path = tmp_path / "data.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def sample_diagram_json(tmp_path):
    data = {
        "nodes": [
            {"id": "a", "text": "A", "x": 0, "y": 0},
            {"id": "b", "text": "B", "x": 200, "y": 0},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }
    path = tmp_path / "diagram.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_batch_chart(tmp_path, sample_csv):
    manifest = {
        "output_dir": str(tmp_path / "out"),
        "items": [
            {
                "type": "chart",
                "data": sample_csv,
                "chart_type": "bar",
                "x_col": "x",
                "y_col": "y",
                "output": "chart.svg",
            },
        ],
    }
    spec = tmp_path / "manifest.json"
    spec.write_text(json.dumps(manifest))

    results = batch_generate(str(spec))
    assert len(results) == 1
    assert os.path.exists(results[0])


def test_batch_diagram(tmp_path, sample_diagram_json):
    manifest = {
        "output_dir": str(tmp_path / "out"),
        "items": [
            {
                "type": "diagram",
                "input": sample_diagram_json,
                "output": "diagram.svg",
            },
        ],
    }
    spec = tmp_path / "manifest.json"
    spec.write_text(json.dumps(manifest))

    results = batch_generate(str(spec))
    assert len(results) == 1
    assert os.path.exists(results[0])


def test_batch_tikz_chart(tmp_path, sample_csv):
    manifest = {
        "output_dir": str(tmp_path / "out"),
        "items": [
            {
                "type": "tikz_chart",
                "data": sample_csv,
                "chart_type": "bar",
                "x_col": "x",
                "y_col": "y",
                "output": "chart.tex",
            },
        ],
    }
    spec = tmp_path / "manifest.json"
    spec.write_text(json.dumps(manifest))

    results = batch_generate(str(spec))
    assert len(results) == 1
    assert results[0].endswith(".tex")


def test_batch_yaml(tmp_path, sample_csv):
    """Test YAML manifest format."""
    manifest_text = f"""
output_dir: {tmp_path / "out"}
style: dark
items:
  - type: chart
    data: {sample_csv}
    chart_type: line
    x_col: x
    y_col: "y"
    output: line_chart.svg
"""
    spec = tmp_path / "manifest.yaml"
    spec.write_text(manifest_text)

    results = batch_generate(str(spec))
    assert len(results) == 1


def test_batch_unknown_type_skips(tmp_path):
    """Unknown item types should be skipped, not crash."""
    manifest = {
        "output_dir": str(tmp_path / "out"),
        "items": [
            {"type": "unknown_thing", "output": "x.svg"},
        ],
    }
    spec = tmp_path / "manifest.json"
    spec.write_text(json.dumps(manifest))

    results = batch_generate(str(spec))
    assert len(results) == 0


def test_batch_missing_manifest():
    with pytest.raises(FileNotFoundError):
        batch_generate("/nonexistent/manifest.yaml")
