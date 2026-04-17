import pytest
import os
import tempfile
import json

plotly = pytest.importorskip("plotly", reason="plotly required for interactive chart tests")

from techfig.engines.interactive import create_interactive_chart


@pytest.fixture
def sample_data():
    return [
        {"day": "Mon", "value": 10, "group": "A"},
        {"day": "Tue", "value": 15, "group": "A"},
        {"day": "Mon", "value": 5, "group": "B"},
        {"day": "Tue", "value": 8, "group": "B"}
    ]


def test_create_interactive_chart_bar(sample_data, tmp_path):
    out_path = str(tmp_path / "test_bar.html")
    result = create_interactive_chart(
        data=sample_data,
        chart_type="bar",
        output_path=out_path,
        title="Test Bar",
        x_col="day",
        y_col="value",
        hue_col="group"
    )
    
    assert os.path.exists(result)
    assert result.endswith(".html")
    
    with open(result, "r") as f:
        content = f.read()
        assert "plotly" in content.lower()
        assert "Test Bar" in content


def test_create_interactive_chart_scatter(sample_data, tmp_path):
    out_path = str(tmp_path / "test_scatter")
    # Provide no extension, it should append .html
    result = create_interactive_chart(
        data=sample_data,
        chart_type="scatter",
        output_path=out_path,
        title="Test Scatter",
        x_col="day",
        y_col="value",
        hue_col="group"
    )
    
    assert os.path.exists(result)
    assert result.endswith(".html")
    
    with open(result, "r") as f:
        content = f.read()
        assert "plotly" in content.lower()
