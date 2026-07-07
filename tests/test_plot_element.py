"""Tests for the plot element: inline matplotlib charts embedded in diagrams.

Covers SVGBuilder.add_plot and the create_diagram ``plot`` element type.
"""
import os
import pytest

from techfig.engines.diagrams import create_diagram
from techfig.utils.svg_builder import SVGBuilder


# Reusable inline dataset so tests don't depend on a file path.
_SAMPLE_DATA = {
    "category": ["A", "B", "C", "D"],
    "value": [10, 15, 7, 22],
}


def _bar_spec():
    return {
        "type": "bar",
        "data": _SAMPLE_DATA,
        "x_col": "category",
        "y_col": "value",
        "title": "Sample",
    }


# ---------------------------------------------------------------------------
# SVGBuilder.add_plot
# ---------------------------------------------------------------------------

def test_add_plot_embeds_nested_svg(tmp_path):
    """add_plot should embed a nested <svg> with the chart markup inside."""
    builder = SVGBuilder(width=800, height=600)
    builder.add_plot(0, 0, 300, 200, chart_spec=_bar_spec(), element_id="p1")
    out = str(tmp_path / "plot.svg")
    builder.save(out)

    assert os.path.exists(out)
    content = open(out).read()
    # Outer drawing svg plus the embedded matplotlib markup.
    assert content.count("<svg") >= 1
    # The chart title should appear somewhere in the embedded markup.
    assert "Sample" in content


def test_add_plot_registers_element_for_connections(tmp_path):
    """An id'd plot should be connectable by arrows to other elements."""
    builder = SVGBuilder(width=800, height=600)
    builder.add_plot(-200, 0, 200, 150, chart_spec=_bar_spec(), element_id="chart")
    builder.add_box(200, 0, 120, 60, text="Result", element_id="result")
    builder.add_arrow("chart", "result")
    out = str(tmp_path / "connected.svg")
    builder.save(out)

    assert os.path.exists(out)


def test_add_plot_rejects_bad_chart_type(tmp_path):
    with pytest.raises(ValueError, match="Unsupported plot chart type"):
        SVGBuilder().add_plot(0, 0, 100, 100, chart_spec={"type": "pie", "data": _SAMPLE_DATA})


def test_add_plot_requires_data(tmp_path):
    with pytest.raises(ValueError, match="requires 'data'"):
        SVGBuilder().add_plot(0, 0, 100, 100, chart_spec={"type": "bar"})


# ---------------------------------------------------------------------------
# create_diagram plot element
# ---------------------------------------------------------------------------

def test_diagram_plot_element(tmp_path):
    """create_diagram should render a plot element alongside other nodes."""
    out = str(tmp_path / "diag.svg")
    elements = [
        {"type": "box", "id": "src", "text": "Data", "x": -300, "y": 0},
        {
            "type": "plot", "id": "chart", "x": 0, "y": 0, "w": 320, "h": 200,
            "text": "Fig. 1",
            "chart": _bar_spec(),
        },
        {"type": "box", "id": "out", "text": "Publish", "x": 300, "y": 0},
    ]
    connections = [
        {"from": "src", "to": "chart"},
        {"from": "chart", "to": "out"},
    ]
    result = create_diagram(elements, connections, out)
    assert os.path.exists(result)
    content = open(result).read()
    assert content.count("<svg") >= 1  # outer + embedded chart content
    assert "Sample" in content  # chart title
    assert "Fig. 1" in content  # caption
    assert "Publish" in content


def test_diagram_plot_missing_chart_raises(tmp_path):
    out = str(tmp_path / "bad.svg")
    elements = [{"type": "plot", "id": "p", "x": 0, "y": 0}]
    with pytest.raises(ValueError, match="requires a 'chart' dict"):
        create_diagram(elements, [], out)


def test_diagram_plot_supports_all_chart_types(tmp_path):
    """bar, line, scatter, box, histogram, heatmap should all embed cleanly."""
    out_dir = tmp_path
    for ctype in ("bar", "line", "scatter", "box", "histogram", "heatmap"):
        spec = {"type": ctype, "data": _SAMPLE_DATA}
        if ctype in ("bar", "line", "scatter", "box"):
            spec["x_col"] = "category"
            spec["y_col"] = "value"
        elif ctype == "histogram":
            spec["x_col"] = "value"
        # heatmap without x/y falls back to correlation matrix
        elements = [{"type": "plot", "id": "p", "x": 0, "y": 0, "chart": spec}]
        out = str(out_dir / f"{ctype}.svg")
        result = create_diagram(elements, [], out)
        assert os.path.exists(result), f"{ctype} plot did not produce a file"
        assert open(result).read().count("<svg") >= 1
