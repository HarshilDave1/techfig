"""Test the figure engine by generating sample charts."""
import os
import pytest
import pandas as pd
from techfig.engines.figures import create_chart

@pytest.fixture
def sample_data():
    """Create a sample pandas dataframe for testing."""
    return pd.DataFrame({
        'category': ['A', 'B', 'C', 'D', 'E'],
        'value': [10, 15, 7, 22, 12],
        'group': ['G1', 'G1', 'G2', 'G2', 'G1']
    })

def test_create_bar_chart(tmp_path, sample_data):
    """Test generating a simple bar chart."""
    out_path = str(tmp_path / "test_bar.svg")
    
    returned_path = create_chart(
        data=sample_data,
        chart_type="bar",
        output_path=out_path,
        title="Sample Bar Chart",
        x_col="category",
        y_col="value",
        hue_col="group",
        style_name="nature"
    )
    
    assert returned_path == out_path
    assert os.path.exists(out_path)
    
    # Check that it's actually an SVG
    with open(out_path, 'r') as f:
        content = f.read()
        assert "<svg" in content
        assert "Sample Bar Chart" in content

def test_create_line_chart(tmp_path, sample_data):
    """Test generating a simple line chart."""
    out_path = str(tmp_path / "test_line.png")
    
    returned_path = create_chart(
        data=sample_data,
        chart_type="line",
        output_path=out_path,
        title="Sample Line Chart",
        x_col="category",
        y_col="value",
        style_name="science"
    )
    
    assert returned_path == out_path
    assert os.path.exists(out_path)
    
    # Check that it's a non-empty PNG
    assert os.path.getsize(out_path) > 100
