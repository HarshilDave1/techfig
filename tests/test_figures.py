"""Test the figure engine by generating sample charts."""
import os
import pytest
import pandas as pd
from techfig.engines.figures import create_chart, CHART_TYPES


@pytest.fixture
def sample_data():
    """Create a sample pandas dataframe for testing."""
    return pd.DataFrame({
        "category": ["A", "B", "C", "D", "E"],
        "value": [10, 15, 7, 22, 12],
        "group": ["G1", "G1", "G2", "G2", "G1"],
    })


@pytest.fixture
def sample_csv(tmp_path, sample_data):
    """Write sample data to a CSV and return the path."""
    path = tmp_path / "data.csv"
    sample_data.to_csv(path, index=False)
    return str(path)


def test_create_bar_chart(tmp_path, sample_data):
    out = str(tmp_path / "bar.svg")
    result = create_chart(
        data=sample_data, chart_type="bar", output_path=out,
        title="Sample Bar", x_col="category", y_col="value",
        hue_col="group", style_name="nature",
    )
    assert result == out
    assert os.path.exists(out)
    with open(out) as f:
        content = f.read()
        assert "<svg" in content
        assert "Sample Bar" in content


def test_create_line_chart(tmp_path, sample_data):
    out = str(tmp_path / "line.png")
    result = create_chart(
        data=sample_data, chart_type="line", output_path=out,
        title="Line Chart", x_col="category", y_col="value",
        style_name="science",
    )
    assert result == out
    assert os.path.getsize(out) > 100


def test_create_scatter_chart(tmp_path, sample_data):
    out = str(tmp_path / "scatter.svg")
    result = create_chart(
        data=sample_data, chart_type="scatter", output_path=out,
        x_col="category", y_col="value",
    )
    assert os.path.exists(result)


def test_create_histogram(tmp_path, sample_data):
    out = str(tmp_path / "hist.svg")
    result = create_chart(
        data=sample_data, chart_type="histogram", output_path=out,
        x_col="value",
    )
    assert os.path.exists(result)


def test_create_heatmap_correlation(tmp_path):
    """Heatmap without explicit x/y should show correlation matrix."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    out = str(tmp_path / "heatmap.svg")
    result = create_chart(data=df, chart_type="heatmap", output_path=out)
    assert os.path.exists(result)


def test_create_heatmap_pivot(tmp_path):
    """Heatmap with x/y columns should pivot the data."""
    df = pd.DataFrame({
        "row": ["R1", "R1", "R2", "R2"],
        "col": ["C1", "C2", "C1", "C2"],
        "val": [1, 2, 3, 4],
    })
    out = str(tmp_path / "heatmap_pivot.svg")
    result = create_chart(
        data=df, chart_type="heatmap", output_path=out,
        x_col="col", y_col="row", hue_col="val",
    )
    assert os.path.exists(result)


def test_chart_from_csv(tmp_path, sample_csv):
    out = str(tmp_path / "csv_chart.svg")
    result = create_chart(
        data=sample_csv, chart_type="bar", output_path=out,
        x_col="category", y_col="value",
    )
    assert os.path.exists(result)


def test_dark_style(tmp_path, sample_data):
    out = str(tmp_path / "dark.svg")
    result = create_chart(
        data=sample_data, chart_type="bar", output_path=out,
        x_col="category", y_col="value", style_name="dark",
    )
    assert os.path.exists(result)


def test_xlabel_ylabel(tmp_path, sample_data):
    out = str(tmp_path / "labeled.svg")
    result = create_chart(
        data=sample_data, chart_type="bar", output_path=out,
        x_col="category", y_col="value",
        xlabel="My X", ylabel="My Y",
    )
    assert os.path.exists(result)
    with open(result) as f:
        content = f.read()
        assert "My X" in content
        assert "My Y" in content


def test_unsupported_chart_type(tmp_path, sample_data):
    with pytest.raises(ValueError, match="Unsupported chart type"):
        create_chart(data=sample_data, chart_type="pie", output_path=str(tmp_path / "x.svg"))
