"""Test the diagram engine by generating sample SVGs."""
import os
import pytest
from techfig.engines.diagrams import create_flowchart, SUPPORTED_SHAPES


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


# ---- Legend element (P3-E) ──────────────────────────────────────────────


def test_svgbuilder_legend_basic(tmp_path):
    """SVGBuilder.add_legend renders a bordered panel with swatch+label rows."""
    from techfig.utils.svg_builder import SVGBuilder

    b = SVGBuilder(400, 300)
    b.add_legend(
        0, 0, 180, 120,
        entries=[
            {"label": "Signal A", "color": "primary"},
            {"label": "Signal B", "color": "#D55E00"},
            {"label": "Control", "color": "accent"},
        ],
        title="Conditions",
        element_id="leg1",
    )
    out = str(tmp_path / "legend_basic.svg")
    b.save(out)
    content = open(out).read()

    # Panel border + at least one rect swatch
    assert "<rect" in content
    assert "Conditions" in content
    assert "Signal A" in content
    assert "Signal B" in content
    assert "Control" in content
    # element_id should be registered for connections
    assert "leg1" in content


def test_svgbuilder_legend_circle_swatch(tmp_path):
    """Per-entry swatch_shape='circle' renders a <circle> swatch."""
    from techfig.utils.svg_builder import SVGBuilder

    b = SVGBuilder(400, 300)
    b.add_legend(
        0, 0, 160, 100,
        entries=[
            {"label": "X", "color": "#0072B2", "swatch_shape": "circle"},
            {"label": "Y", "color": "#009E73", "swatch_shape": "circle"},
        ],
        swatch_shape="rect",
    )
    out = str(tmp_path / "legend_circle.svg")
    b.save(out)
    content = open(out).read()
    assert "<circle" in content
    assert ">X<" in content or "X" in content


def test_svgbuilder_legend_no_title(tmp_path):
    """A legend without a title still renders entries."""
    from techfig.utils.svg_builder import SVGBuilder

    b = SVGBuilder(400, 300)
    b.add_legend(
        0, 0, 140, 90,
        entries=[{"label": "only", "color": "secondary"}],
    )
    out = str(tmp_path / "legend_notitle.svg")
    b.save(out)
    content = open(out).read()
    assert "only" in content
    assert "<rect" in content


def test_svgbuilder_legend_dashed_border(tmp_path):
    """stroke_dash on the legend panel border is honoured."""
    from techfig.utils.svg_builder import SVGBuilder

    b = SVGBuilder(400, 300)
    b.add_legend(
        0, 0, 140, 90,
        entries=[{"label": "d", "color": "primary"}],
        stroke_dash="5,3",
    )
    out = str(tmp_path / "legend_dash.svg")
    b.save(out)
    content = open(out).read()
    assert "stroke-dasharray" in content


def test_svgbuilder_legend_connection(tmp_path):
    """A legend registered with an id can be the endpoint of a connection."""
    from techfig.utils.svg_builder import SVGBuilder

    b = SVGBuilder(400, 300)
    b.add_box(0, 0, 60, 40, text="Src", element_id="src")
    b.add_legend(150, 0, 120, 80, entries=[{"label": "L", "color": "primary"}],
                 element_id="leg")
    b.add_arrow("src", "leg")
    out = str(tmp_path / "legend_conn.svg")
    b.save(out)
    content = open(out).read()
    assert "<path" in content


def test_diagram_legend_element(tmp_path):
    """create_diagram accepts a 'legend' element type and renders it."""
    from techfig.engines.diagrams import create_diagram

    elements = [
        {"type": "box", "id": "b1", "x": -200, "y": 0, "text": "Data"},
        {
            "type": "legend", "id": "leg", "x": 200, "y": 0,
            "w": 200, "h": 140, "title": "Legend",
            "color": "#333333",
            "entries": [
                {"label": "Series A", "color": "#0072B2"},
                {"label": "Series B", "color": "#D55E00", "swatch_shape": "circle"},
            ],
        },
    ]
    connections = [{"from": "b1", "to": "leg"}]
    out = create_diagram(elements, connections, str(tmp_path / "diag_legend.svg"))
    content = open(out).read()
    assert "Legend" in content
    assert "Series A" in content
    assert "Series B" in content
    assert "<rect" in content
    assert "<circle" in content
    # connection should have been drawn (path element)
    assert "<path" in content


def test_diagram_legend_default_size(tmp_path):
    """A legend element with no w/h uses sensible defaults and still renders."""
    from techfig.engines.diagrams import create_diagram

    elements = [
        {
            "type": "legend", "id": "leg", "x": 0, "y": 0,
            "entries": [{"label": "ok", "color": "primary"}],
        },
    ]
    out = create_diagram(elements, [], str(tmp_path / "diag_legend_default.svg"))
    content = open(out).read()
    assert "ok" in content


def test_diagram_legend_in_schema_enum():
    """The sketch interpreter schema should list 'legend' in the element type enum."""
    from techfig.engines.sketch_interpreter import DIAGRAM_SCHEMA, SKETCH_PROMPT

    el_props = DIAGRAM_SCHEMA["properties"]["elements"]["items"]["properties"]
    assert "legend" in el_props["type"]["enum"]
    # legend-specific fields present
    assert "entries" in el_props
    assert "title" in el_props
    assert "swatch_shape" in el_props
    # prompt documents the legend type
    assert "| legend |" in SKETCH_PROMPT
    assert "legend" in SKETCH_PROMPT.split("IMPORTANT")[1]
