"""Tests for P2-E: arrows and paths as first-class elements.

Covers the new SVGBuilder.add_arrow_xy / add_path primitives and the
`arrow` and `path` element types in the diagram engine.
"""
from pathlib import Path

import pytest

from techfig.utils.svg_builder import SVGBuilder
from techfig.engines.diagrams import create_diagram, SUPPORTED_PATHS
from techfig.engines.geo_linter import snap_to_grid, lint_spec


# ---- SVGBuilder.add_arrow_xy ----------------------------------------------

class TestAddArrowXY:
    def test_basic_arrow(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_arrow_xy(0, 0, 100, 0, text="flow")
        out = str(tmp_path / "arrow.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<path" in content
        assert "flow" in content
        # arrowhead marker should be referenced
        assert "marker" in content.lower()

    def test_curved_arrow(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_arrow_xy(0, 0, 100, 0, curve=30)
        out = str(tmp_path / "arrow_curve.svg")
        b.save(out)
        content = Path(out).read_text()
        # quadratic Bezier produces a Q command in the path
        assert "Q" in content or "q" in content

    def test_dashed_arrow(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_arrow_xy(0, 0, 100, 0, stroke_dash="5,3")
        out = str(tmp_path / "arrow_dash.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "stroke-dasharray" in content

    def test_arrow_independent_of_elements(self, tmp_path):
        """An arrow_xy should not require any element ids to be registered."""
        b = SVGBuilder(400, 300)
        # No boxes/circles added — arrow alone
        b.add_arrow_xy(-50, -50, 50, 50)
        out = str(tmp_path / "arrow_solo.svg")
        b.save(out)
        assert Path(out).exists()


# ---- SVGBuilder.add_path ---------------------------------------------------

class TestAddPath:
    def test_polyline(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_path([(0, 0), (100, 0), (100, 100), (0, 100)])
        out = str(tmp_path / "polyline.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<path" in content

    def test_closed_path(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_path([(0, 0), (100, 0), (100, 100), (0, 100)], closed=True)
        out = str(tmp_path / "closed.svg")
        b.save(out)
        content = Path(out).read_text()
        # closed path ends with Z
        assert "Z" in content or "z" in content

    def test_path_with_arrowhead_end(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_path([(0, 0), (100, 0)], arrowhead="end")
        out = str(tmp_path / "path_arrow_end.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "marker" in content.lower()

    def test_path_with_arrowhead_both(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_path([(0, 0), (100, 0)], arrowhead="both")
        out = str(tmp_path / "path_arrow_both.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "marker" in content.lower()

    def test_quadratic_bezier(self, tmp_path):
        b = SVGBuilder(400, 300)
        # [x, y, "Q"] consumes the next entry as the control point
        b.add_path([(0, 0, "Q"), (50, -50), (100, 0)])
        out = str(tmp_path / "quad.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "Q" in content or "q" in content

    def test_cubic_bezier(self, tmp_path):
        b = SVGBuilder(400, 300)
        # [x, y, "C"] consumes the next two entries as control points
        b.add_path([(0, 0, "C"), (33, -50), (66, 50), (100, 0)])
        out = str(tmp_path / "cubic.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "C" in content or "c" in content

    def test_path_text_label(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_path([(0, 0), (100, 0), (100, 100)], text="route")
        out = str(tmp_path / "path_label.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "route" in content

    def test_too_few_points_raises(self):
        b = SVGBuilder(400, 300)
        with pytest.raises(ValueError, match="at least 2 points"):
            b.add_path([(0, 0)])

    def test_unknown_command_raises(self):
        b = SVGBuilder(400, 300)
        with pytest.raises(ValueError, match="Unknown path command"):
            b.add_path([(0, 0, "X"), (100, 0)])


# ---- create_diagram engine: arrow & path element types --------------------

class TestDiagramArrowPathElements:
    def test_arrow_element(self, tmp_path):
        elements = [
            {"type": "arrow", "x1": -100, "y1": 0, "x2": 100, "y2": 0, "text": "go"},
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_arrow.svg"))
        content = Path(out).read_text()
        assert "<path" in content
        assert "go" in content
        assert "marker" in content.lower()

    def test_arrow_element_curved(self, tmp_path):
        elements = [
            {"type": "arrow", "x1": -100, "y1": 0, "x2": 100, "y2": 0, "curve": 40},
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_arrow_curve.svg"))
        content = Path(out).read_text()
        assert "Q" in content or "q" in content

    def test_path_element(self, tmp_path):
        elements = [
            {"type": "path", "points": [[0, 0], [100, 0], [100, 100]]},
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_path.svg"))
        assert Path(out).exists()

    def test_path_element_closed_with_arrowhead(self, tmp_path):
        elements = [
            {
                "type": "path",
                "points": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "closed": True,
                "arrowhead": "end",
            },
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_path_closed.svg"))
        content = Path(out).read_text()
        assert "marker" in content.lower()

    def test_path_element_with_commands(self, tmp_path):
        elements = [
            {
                "type": "path",
                "points": [[0, 0, "Q"], [50, -50], [100, 0]],
            },
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_path_cmd.svg"))
        content = Path(out).read_text()
        assert "Q" in content or "q" in content

    def test_path_element_too_few_points_raises(self, tmp_path):
        elements = [{"type": "path", "id": "p1", "points": [[0, 0]]}]
        with pytest.raises(ValueError, match="at least 2"):
            create_diagram(elements, [], str(tmp_path / "err.svg"))

    def test_path_element_missing_points_raises(self, tmp_path):
        elements = [{"type": "path", "id": "p2"}]
        with pytest.raises(ValueError, match="points"):
            create_diagram(elements, [], str(tmp_path / "err2.svg"))

    def test_path_element_bad_point_shape_raises(self, tmp_path):
        elements = [{"type": "path", "id": "p3", "points": [[0, 0], "not_a_point"]}]
        with pytest.raises(ValueError, match="each point must be"):
            create_diagram(elements, [], str(tmp_path / "err3.svg"))

    def test_arrow_path_in_mixed_diagram(self, tmp_path):
        """Arrow + path + shape + connection all coexist."""
        elements = [
            {"type": "box", "id": "b", "x": 0, "y": 0, "text": "Box"},
            {"type": "arrow", "x1": -200, "y1": -150, "x2": -100, "y2": -100, "text": "in"},
            {"type": "path", "points": [[200, -100], [250, -50, "Q"], [275, -75], [300, -100]]},
        ]
        connections = [{"from": "b", "to": "b"}]  # self-loop just to exercise conn path
        out = create_diagram(elements, connections, str(tmp_path / "mixed.svg"))
        content = Path(out).read_text()
        assert "Box" in content
        assert "in" in content

    def test_supported_paths_constant(self):
        assert "arrow" in SUPPORTED_PATHS
        assert "path" in SUPPORTED_PATHS
        assert "line" in SUPPORTED_PATHS


# ---- geo_linter integration ------------------------------------------------

class TestGeoLinterArrowPath:
    def test_snap_arrow_coords(self):
        spec = {
            "elements": [
                {"type": "arrow", "x1": 7, "y1": 13, "x2": 103, "y2": 37},
            ],
        }
        snapped = snap_to_grid(spec, grid_size=20.0)
        a = snapped["elements"][0]
        assert a["x1"] == 0
        assert a["y1"] == 20
        assert a["x2"] == 100
        assert a["y2"] == 40

    def test_snap_path_points(self):
        spec = {
            "elements": [
                {"type": "path", "points": [[7, 13], [103, 37]]},
            ],
        }
        snapped = snap_to_grid(spec, grid_size=20.0)
        pts = snapped["elements"][0]["points"]
        assert pts[0][0] == 0
        assert pts[0][1] == 20
        assert pts[1][0] == 100
        assert pts[1][1] == 40

    def test_lint_flags_off_grid_arrow(self):
        spec = {
            "elements": [
                {"type": "arrow", "x1": 7, "y1": 0, "x2": 103, "y2": 0},
            ],
        }
        report = lint_spec(spec, grid_size=20.0)
        # 7 and 103 are off the 20px grid by more than 2px
        assert any("x1" in i or "x2" in i for i in report.grid_issues)

    def test_lint_flags_off_grid_path_points(self):
        spec = {
            "elements": [
                {"type": "path", "id": "p", "points": [[7, 0], [103, 0]]},
            ],
        }
        report = lint_spec(spec, grid_size=20.0)
        assert any("point" in i for i in report.grid_issues)
