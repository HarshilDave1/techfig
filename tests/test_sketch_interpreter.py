"""Tests for enhanced SVG primitives and the sketch interpreter pipeline."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from techfig.utils.svg_builder import SVGBuilder
from techfig.engines.diagrams import create_diagram, create_flowchart
from techfig.engines.sketch_interpreter import (
    validate_spec,
    render_from_spec,
    render_from_json,
    get_sketch_prompt,
    get_diagram_schema,
)


# ---- SVGBuilder new primitives ─────────────────────────────────────────

class TestSVGBuilderEllipse:
    def test_add_ellipse(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_ellipse(0, 0, rx=80, ry=40, text="Oval", element_id="e1")
        out = str(tmp_path / "ellipse.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<ellipse" in content
        assert "Oval" in content

    def test_ellipse_dashed(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_ellipse(0, 0, rx=50, ry=30, text="D", element_id="e2", stroke_dash="5,3")
        out = str(tmp_path / "ellipse_dash.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "stroke-dasharray" in content


class TestSVGBuilderTriangle:
    def test_add_triangle(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_triangle(0, 0, w=80, h=70, text="T", element_id="t1")
        out = str(tmp_path / "tri.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<path" in content
        assert "T" in content

    def test_triangle_directions(self, tmp_path):
        for direction in ("up", "down", "left", "right"):
            b = SVGBuilder(400, 300)
            b.add_triangle(0, 0, w=60, h=60, text=direction, element_id=f"t_{direction}",
                           direction=direction)
            out = str(tmp_path / f"tri_{direction}.svg")
            b.save(out)
            assert Path(out).exists()


class TestSVGBuilderText:
    def test_add_text(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_text(0, 0, text="Hello World", element_id="txt1")
        out = str(tmp_path / "text.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "Hello World" in content

    def test_text_custom_size(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_text(0, 0, text="Big", font_size=32, element_id="txt2")
        out = str(tmp_path / "text_big.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "32" in content


class TestSVGBuilderLine:
    def test_add_line(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_line(0, 0, 100, 100, text="")
        out = str(tmp_path / "line.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<path" in content or "<line" in content

    def test_dashed_line(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_line(0, 0, 100, 0, text="", stroke_dash="5,3")
        out = str(tmp_path / "dashed_line.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "stroke-dasharray" in content


class TestSVGBuilderConnection:
    def test_add_connection(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_box(0, 0, 60, 40, text="A", element_id="a")
        b.add_box(150, 0, 60, 40, text="B", element_id="b")
        b.add_connection("a", "b", text="")
        out = str(tmp_path / "conn.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<path" in content or "<line" in content


class TestSVGBuilderStyling:
    def test_fill_opacity(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_box(0, 0, 80, 50, text="X", element_id="x", fill_opacity=0.3)
        out = str(tmp_path / "opacity.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "fill-opacity" in content or "opacity" in content
        assert 'stroke="#333333"' in content

    def test_stroke_color_override(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_box(0, 0, 80, 50, text="X", element_id="x", stroke_color="#ff0000")
        out = str(tmp_path / "stroke_override.svg")
        b.save(out)
        content = Path(out).read_text()
        assert 'stroke="#ff0000"' in content

    def test_rotation(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_box(0, 0, 80, 50, text="R", element_id="r", rotation=45)
        out = str(tmp_path / "rotate.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "rotate" in content


# ---- create_diagram engine ─────────────────────────────────────────────

class TestCreateDiagram:
    def test_basic_diagram(self, tmp_path):
        elements = [
            {"type": "box", "id": "b1", "x": 0, "y": 0, "text": "Start"},
            {"type": "circle", "id": "c1", "x": 200, "y": 0, "text": "End", "r": 40},
        ]
        connections = [{"from": "b1", "to": "c1", "style": "arrow"}]
        out = create_diagram(elements, connections, str(tmp_path / "diag.svg"))
        assert Path(out).exists()

    def test_all_shapes(self, tmp_path):
        elements = [
            {"type": "box", "id": "b", "x": 0, "y": 0, "text": "B"},
            {"type": "circle", "id": "c", "x": 150, "y": 0, "text": "C"},
            {"type": "diamond", "id": "d", "x": 300, "y": 0, "text": "D"},
            {"type": "ellipse", "id": "e", "x": 0, "y": 150, "text": "E"},
            {"type": "triangle", "id": "t", "x": 150, "y": 150, "text": "T"},
            {"type": "text", "x": 300, "y": 150, "text": "Label"},
            {"type": "line", "x1": 0, "y1": 300, "x2": 300, "y2": 300},
        ]
        out = create_diagram(elements, [], str(tmp_path / "all_shapes.svg"))
        content = Path(out).read_text()
        assert "<ellipse" in content
        assert "<path" in content

    def test_unknown_type_raises(self, tmp_path):
        elements = [{"type": "hexagon", "id": "h", "x": 0, "y": 0, "text": "H"}]
        with pytest.raises(ValueError, match="Unknown element type"):
            create_diagram(elements, [], str(tmp_path / "err.svg"))

    def test_backward_compat_flowchart(self, tmp_path):
        """create_flowchart should still work."""
        nodes = [
            {"id": "a", "text": "A", "x": 0, "y": 0, "shape": "box"},
            {"id": "b", "text": "B", "x": 200, "y": 0, "shape": "circle"},
        ]
        edges = [{"from": "a", "to": "b"}]
        out = create_flowchart(nodes, edges, str(tmp_path / "compat.svg"))
        assert Path(out).exists()


# ---- Sketch Interpreter ─────────────────────────────────────────────────

class TestValidateSpec:
    def test_valid_spec(self):
        spec = {
            "elements": [
                {"type": "box", "id": "b1", "x": 0, "y": 0, "text": "A"},
                {"type": "circle", "id": "c1", "x": 100, "y": 0},
            ],
            "connections": [{"from": "b1", "to": "c1"}],
        }
        assert validate_spec(spec) == []

    def test_missing_elements(self):
        assert len(validate_spec({})) > 0

    def test_unknown_type(self):
        spec = {"elements": [{"type": "star", "id": "s", "x": 0, "y": 0}]}
        issues = validate_spec(spec)
        assert any("unknown type" in i for i in issues)

    def test_dup_ids(self):
        spec = {
            "elements": [
                {"type": "box", "id": "dup", "x": 0, "y": 0},
                {"type": "box", "id": "dup", "x": 100, "y": 0},
            ],
        }
        issues = validate_spec(spec)
        assert any("duplicate" in i for i in issues)

    def test_missing_position(self):
        spec = {"elements": [{"type": "box", "id": "b"}]}
        issues = validate_spec(spec)
        assert any("missing x or y" in i for i in issues)

    def test_bad_conn_ref(self):
        spec = {
            "elements": [{"type": "box", "id": "b1", "x": 0, "y": 0}],
            "connections": [{"from": "b1", "to": "nonexistent"}],
        }
        issues = validate_spec(spec)
        assert any("unknown id" in i for i in issues)

    def test_text_needs_text(self):
        spec = {"elements": [{"type": "text", "x": 0, "y": 0}]}
        issues = validate_spec(spec)
        assert any("missing text" in i for i in issues)


class TestRenderFromSpec:
    def test_renders_valid_spec(self, tmp_path):
        spec = {
            "canvas": {"width": 400, "height": 300},
            "elements": [
                {"type": "box", "id": "b1", "x": 0, "y": 0, "w": 80, "h": 50, "text": "Hi"},
            ],
        }
        out = render_from_spec(spec, str(tmp_path / "out.svg"))
        assert Path(out).exists()
        assert "<svg" in Path(out).read_text()

    def test_rejects_invalid_spec(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid diagram spec"):
            render_from_spec({}, str(tmp_path / "bad.svg"))


class TestRenderFromJSON:
    def test_load_and_render(self, tmp_path):
        spec = {
            "elements": [
                {"type": "circle", "id": "c1", "x": 0, "y": 0, "r": 30, "text": "Go"},
            ],
        }
        json_file = tmp_path / "spec.json"
        json_file.write_text(json.dumps(spec))
        out = render_from_json(str(json_file), str(tmp_path / "rendered.svg"))
        assert Path(out).exists()

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            render_from_json(str(tmp_path / "nope.json"), str(tmp_path / "out.svg"))


class TestPromptAndSchema:
    def test_prompt_nonempty(self):
        prompt = get_sketch_prompt()
        assert "element types" in prompt
        assert len(prompt) > 200

    def test_schema_has_elements(self):
        schema = get_diagram_schema()
        assert "elements" in schema["properties"]
        assert "connections" in schema["properties"]


# ---- Full optical diagram spec test ────────────────────────────────────

class TestOpticalDiagramSpec:
    def test_render_optical_diagram(self):
        """Renders the example optical diagram spec, verifying it passes validation."""
        spec_path = Path(__file__).parent.parent / "examples" / "optical_diagram_spec.json"
        if not spec_path.exists():
            pytest.skip("Demo spec file not found")

        with open(spec_path) as f:
            spec = json.load(f)

        issues = validate_spec(spec)
        assert issues == [], f"Spec has issues: {issues}"

        with tempfile.TemporaryDirectory() as td:
            out = render_from_spec(spec, str(Path(td) / "optical.svg"))
            content = Path(out).read_text()
            assert "<svg" in content
            assert "<ellipse" in content  # lens/SLM
            assert "Detector" in content
            assert "Lens" in content
