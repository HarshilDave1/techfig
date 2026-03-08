"""Test the TikZ export engine."""
import os
import pytest
import pandas as pd
from techfig.engines.tikz_export import chart_to_tikz, diagram_to_tikz, _escape_tex


@pytest.fixture
def sample_data():
    return pd.DataFrame({
        "category": ["A", "B", "C"],
        "value": [10, 20, 30],
    })


def test_chart_to_tikz_bar(tmp_path, sample_data):
    out = str(tmp_path / "bar.tex")
    result = chart_to_tikz(
        data=sample_data, chart_type="bar", output_path=out,
        title="Bar Chart", x_col="category", y_col="value",
    )
    assert os.path.exists(result)
    content = open(result).read()
    assert r"\begin{tikzpicture}" in content
    assert "pgfplots" in content
    assert "Bar Chart" in content
    assert "ybar" in content


def test_chart_to_tikz_line(tmp_path, sample_data):
    out = str(tmp_path / "line.tex")
    result = chart_to_tikz(
        data=sample_data, chart_type="line", output_path=out,
        x_col="category", y_col="value",
    )
    content = open(result).read()
    assert "mark=*" in content


def test_chart_to_tikz_scatter(tmp_path, sample_data):
    out = str(tmp_path / "scatter.tex")
    result = chart_to_tikz(
        data=sample_data, chart_type="scatter", output_path=out,
        x_col="category", y_col="value",
    )
    content = open(result).read()
    assert "only marks" in content


def test_diagram_to_tikz(tmp_path):
    nodes = [
        {"id": "a", "text": "Start", "x": 0, "y": 0, "shape": "box"},
        {"id": "b", "text": "End", "x": 200, "y": 0, "shape": "circle"},
        {"id": "c", "text": "Decision?", "x": 100, "y": 100, "shape": "diamond"},
    ]
    edges = [
        {"from": "a", "to": "c", "label": "check"},
        {"from": "c", "to": "b"},
    ]
    out = str(tmp_path / "diagram.tex")
    result = diagram_to_tikz(nodes, edges, out)
    content = open(result).read()
    assert r"\node[box]" in content
    assert r"\node[circ]" in content
    assert r"\node[diam]" in content
    assert r"\draw[->]" in content
    assert "check" in content


def test_escape_tex():
    assert _escape_tex("A & B") == r"A \& B"
    assert _escape_tex("100%") == r"100\%"
    assert _escape_tex("x_1") == r"x\_1"
    assert _escape_tex("plain") == "plain"
