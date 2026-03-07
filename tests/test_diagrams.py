"""Test the diagram engine by generating a sample SVG."""
import os
import pytest
from techfig.engines.diagrams import create_flowchart

def test_create_basic_flowchart(tmp_path):
    """Test generating a simple flowchart SVG."""
    out_path = str(tmp_path / "test_flowchart.svg")
    
    nodes = [
        {"id": "data", "text": "Raw Data", "x": -200, "y": 0, "color": "secondary"},
        {"id": "process", "text": "Analysis", "x": 0, "y": 0},
        {"id": "result", "text": "Figure", "x": 200, "y": 0, "shape": "circle"}
    ]
    
    edges = [
        {"from": "data", "to": "process", "label": "load"},
        {"from": "process", "to": "result", "label": "render"}
    ]
    
    returned_path = create_flowchart(nodes, edges, out_path)
    
    assert returned_path == out_path
    assert os.path.exists(out_path)
    
    # Check that it's actually an SVG
    with open(out_path, 'r') as f:
        content = f.read()
        assert "<svg" in content
        assert "Raw Data" in content
        assert "Analysis" in content
        assert "Figure" in content
        assert "load" in content
        assert "render" in content
