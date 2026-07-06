"""Test the diagram engine by generating sample SVGs."""
import os
import pytest
from techfig.engines.diagrams import create_flowchart, create_diagram
from techfig.utils.svg_builder import SVGBuilder


def test_create_basic_flowchart(tmp_path):
    out = str(tmp_path / "flowchart.svg")
    nodes = [
        {"id": "data", "text": "Raw Data", "x": -200, "y": 0, "color": "secondary"},
        {"id": "process", "text": "Analysis", "x": 0, "y": 0},
        {"id": "result", "text": "Figure", "x": 200, "y": 0, "shape": "circle"},
    ]
    edges = [
        {"from": "data", "to": "process", "label": "load"},
        {"from": "process", "to": "result", "label": "render"},
    ]
    result = create_flowchart(nodes, edges, out)
    assert result == out
    assert os.path.exists(out)

    with open(out) as f:
        content = f.read()
        assert "<svg" in content
        assert "Raw Data" in content
        assert "Analysis" in content
        assert "Figure" in content
        assert "load" in content
        assert "render" in content


def test_diamond_shape(tmp_path):
    """Diamond (decision) nodes should render without error."""
    out = str(tmp_path / "diamond.svg")
    nodes = [
        {"id": "start", "text": "Start", "x": 0, "y": -100, "shape": "box"},
        {"id": "decide", "text": "OK?", "x": 0, "y": 0, "shape": "diamond"},
        {"id": "yes", "text": "Yes", "x": -150, "y": 100, "shape": "circle"},
        {"id": "no", "text": "No", "x": 150, "y": 100, "shape": "circle"},
    ]
    edges = [
        {"from": "start", "to": "decide"},
        {"from": "decide", "to": "yes", "label": "yes"},
        {"from": "decide", "to": "no", "label": "no"},
    ]
    result = create_flowchart(nodes, edges, out)
    assert os.path.exists(result)
    content = open(result).read()
    assert "OK?" in content


def test_orthogonal_routing(tmp_path):
    out = str(tmp_path / "ortho.svg")
    nodes = [
        {"id": "a", "text": "A", "x": -100, "y": -100},
        {"id": "b", "text": "B", "x": 100, "y": 100},
    ]
    edges = [
        {"from": "a", "to": "b", "route": "orthogonal"},
    ]
    result = create_flowchart(nodes, edges, out)
    assert os.path.exists(result)


def test_unsupported_shape(tmp_path):
    nodes = [{"id": "x", "text": "X", "x": 0, "y": 0, "shape": "hexagon"}]
    with pytest.raises(ValueError, match="Unknown element type"):
        create_flowchart(nodes, [], str(tmp_path / "fail.svg"))


def test_missing_edge_element(tmp_path):
    nodes = [{"id": "a", "text": "A", "x": 0, "y": 0}]
    edges = [{"from": "a", "to": "nonexistent"}]
    with pytest.raises(ValueError, match="element not found"):
        create_flowchart(nodes, edges, str(tmp_path / "fail.svg"))


def test_custom_dimensions(tmp_path):
    """Passing custom width/height should not crash."""
    out = str(tmp_path / "wide.svg")
    nodes = [{"id": "a", "text": "Wide", "x": 0, "y": 0}]
    result = create_flowchart(nodes, [], out, width=1200, height=400)
    assert os.path.exists(result)


def test_component_rendering(tmp_path):
    """Test that registered components can be rendered as nodes."""
    from techfig.components import get_registry
    from techfig.components.standard import load_standard_components
    
    load_standard_components(get_registry())
    
    out = str(tmp_path / "comp.svg")
    nodes = [
        {"id": "v1", "text": "V", "x": 0, "y": 0, "shape": "source_v"},
        {"id": "r1", "text": "R", "x": 100, "y": 0, "shape": "resistor"},
    ]
    edges = [{"from": "v1", "to": "r1"}]
    result = create_flowchart(nodes, edges, out)
    
    assert os.path.exists(result)
    with open(result) as f:
        content = f.read()
        assert "V" in content
        assert "R" in content
        # There should be embedded SVGs internally, so > 1.
        assert content.count("<svg") > 1


def test_textblock_element_renders_and_wraps(tmp_path):
    out = str(tmp_path / "textblock.svg")
    elements = [
        {
            "type": "textblock",
            "id": "note",
            "x": 0,
            "y": 0,
            "w": 240,
            "h": 140,
            "text": "This is a long text block that should wrap into multiple lines.\nSecond paragraph stays separate.",
            "color": "secondary",
            "align": "left",
            "padding": 10,
        },
    ]
    result = create_diagram(elements, [], out)
    assert os.path.exists(result)
    content = open(result).read()
    assert "<svg" in content
    assert "text-anchor=\"start\"" in content
    assert "rx=\"6\"" in content
    assert "This is a long" in content
    assert "that should wrap into" in content
    assert "multiple lines." in content
    assert "Second paragraph" in content


def test_textblock_alignment_center_and_right(tmp_path):
    builder = SVGBuilder(width=300, height=200)
    builder.add_textblock(0, 0, 180, 90, "Center aligned", align="center", element_id="c")
    builder.add_textblock(0, 120, 180, 90, "Right aligned", align="right", element_id="r")
    svg = builder.get_svg_string()
    assert svg.count("<text") == 2
    assert 'text-anchor="middle"' in svg
    assert 'text-anchor="end"' in svg

