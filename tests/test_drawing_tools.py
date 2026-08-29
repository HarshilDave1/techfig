"""Tests for freehand pen, filled polygons, holes, and boolean compounds.

These primitives let reconstruct specs build organic scientific figures
(clouds, trees, bacteria) from overlapping and cut geometry rather than
only boxes/circles/open paths.
"""
from pathlib import Path

import pytest

from techfig.utils.svg_builder import SVGBuilder
from techfig.engines.diagrams import create_diagram
from techfig.engines.sketch_interpreter import validate_spec, get_diagram_schema
from techfig.utils.boolean import boolean_paths, shape_bounds


# ---- SVGBuilder.add_polygon ------------------------------------------------

class TestAddPolygon:
    def test_filled_closed_polygon(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_polygon([(0, -40), (50, 40), (-50, 40)], color="primary")
        out = str(tmp_path / "poly.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<path" in content or "<polygon" in content
        assert 'fill="none"' not in content.split("<path")[-1][:400]
        assert "Z" in content or "z" in content or "<polygon" in content

    def test_polygon_with_hole_uses_evenodd(self, tmp_path):
        """A hole must punch through the fill (even-odd / nonzero cut)."""
        b = SVGBuilder(400, 300)
        outer = [(-80, -60), (80, -60), (80, 60), (-80, 60)]
        hole = [(-30, -20), (30, -20), (30, 20), (-30, 20)]
        b.add_polygon(outer, holes=[hole], color="#4C9BE8", fill_opacity=1.0)
        out = str(tmp_path / "poly_hole.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "evenodd" in content.lower() or "even-odd" in content.lower()
        # two closed subpaths: outer + hole
        assert content.lower().count("z") >= 2

    def test_polygon_too_few_points_raises(self):
        b = SVGBuilder(400, 300)
        with pytest.raises(ValueError, match="at least 3"):
            b.add_polygon([(0, 0), (10, 0)])

    def test_polygon_registers_element_id(self):
        b = SVGBuilder(400, 300)
        b.add_polygon(
            [(-20, -20), (20, -20), (20, 20), (-20, 20)],
            element_id="leaf",
        )
        assert "leaf" in b._elements
        x, y, w, h = b._elements["leaf"]
        assert w == pytest.approx(40)
        assert h == pytest.approx(40)
        assert x == pytest.approx(0)
        assert y == pytest.approx(0)


# ---- SVGBuilder.add_pen ----------------------------------------------------

class TestAddPen:
    def test_pen_stroke_is_unfilled(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_pen([(0, 0), (40, -20), (80, 10), (120, -5)])
        out = str(tmp_path / "pen.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<path" in content
        assert 'fill="none"' in content

    def test_pen_smooth_uses_cubic_or_quadratic(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_pen([(0, 0), (40, -30), (80, 20), (120, 0)], smooth=True)
        out = str(tmp_path / "pen_smooth.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "C" in content or "c" in content or "Q" in content or "q" in content

    def test_pen_closed_loop(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_pen([(-30, 0), (0, -40), (30, 0), (0, 40)], closed=True)
        out = str(tmp_path / "pen_closed.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "Z" in content or "z" in content

    def test_pen_too_few_points_raises(self):
        b = SVGBuilder(400, 300)
        with pytest.raises(ValueError, match="at least 2"):
            b.add_pen([(0, 0)])

    def test_pen_respects_stroke_width(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_pen([(0, 0), (80, 0)], stroke_width=7)
        out = str(tmp_path / "pen_w.svg")
        b.save(out)
        content = Path(out).read_text()
        assert 'stroke-width="7' in content or "stroke-width:7" in content


# ---- boolean geometry (union / cut / intersection) -------------------------


def _circle(x, y, r):
    return {"type": "circle", "x": x, "y": y, "r": r}


def _box(x, y, w, h):
    return {"type": "box", "x": x, "y": y, "w": w, "h": h}


class TestBooleanGeometry:
    def test_union_of_overlapping_circles_is_one_outer_ring(self):
        rings = boolean_paths([_circle(-20, 0, 40), _circle(20, 0, 40)], op="union")
        assert len(rings) == 1
        assert len(rings[0]) >= 12
        xs = [p[0] for p in rings[0]]
        assert min(xs) < -50
        assert max(xs) > 50

    def test_difference_punches_a_hole(self):
        rings = boolean_paths([_circle(0, 0, 50), _circle(0, 0, 20)], op="difference")
        assert len(rings) == 2
        outer, hole = rings[0], rings[1]
        assert max(p[0] for p in outer) > max(p[0] for p in hole)

    def test_intersection_is_smaller_than_either(self):
        rings = boolean_paths([_circle(-15, 0, 40), _circle(15, 0, 40)], op="intersection")
        assert len(rings) == 1
        xs = [p[0] for p in rings[0]]
        assert max(xs) - min(xs) < 70

    def test_cut_alias_is_difference(self):
        a = boolean_paths([_box(0, 0, 80, 80), _circle(0, 0, 20)], op="cut")
        b = boolean_paths([_box(0, 0, 80, 80), _circle(0, 0, 20)], op="difference")
        assert len(a) == len(b) == 2

    def test_unknown_op_raises(self):
        with pytest.raises(ValueError, match="op"):
            boolean_paths([_circle(0, 0, 10)], op="xor")

    def test_shape_bounds_circle(self):
        xmin, ymin, xmax, ymax = shape_bounds(_circle(10, -5, 20))
        assert xmin == pytest.approx(-10)
        assert xmax == pytest.approx(30)
        assert ymin == pytest.approx(-25)
        assert ymax == pytest.approx(15)


class TestAddCompound:
    def test_union_renders_single_filled_path(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_compound(
            [_circle(-25, 0, 40), _circle(25, 0, 40)],
            op="union",
            color="#8ecae6",
            fill_opacity=1.0,
            element_id="cloud",
        )
        out = str(tmp_path / "union.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "<path" in content
        assert "cloud" in b._elements

    def test_difference_uses_evenodd(self, tmp_path):
        b = SVGBuilder(400, 300)
        b.add_compound(
            [_circle(0, 0, 50), _circle(15, -5, 18)],
            op="difference",
            color="#d55e00",
            fill_opacity=1.0,
        )
        out = str(tmp_path / "cut.svg")
        b.save(out)
        content = Path(out).read_text()
        assert "evenodd" in content.lower()
        assert content.lower().count("z") >= 2


# ---- diagram engine + spec schema ------------------------------------------

class TestDiagramElementTypes:
    def test_polygon_element(self, tmp_path):
        elements = [
            {
                "type": "polygon",
                "id": "leaf",
                "points": [[0, -50], [40, 30], [-40, 30]],
                "color": "#2d6a4f",
                "fill_opacity": 1.0,
                "text": "leaf",
            }
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_poly.svg"))
        content = Path(out).read_text()
        assert "leaf" in content
        assert "<path" in content or "<polygon" in content

    def test_polygon_element_with_holes(self, tmp_path):
        elements = [
            {
                "type": "polygon",
                "points": [[-80, -60], [80, -60], [80, 60], [-80, 60]],
                "holes": [[[-20, -15], [20, -15], [20, 15], [-20, 15]]],
                "color": "#4C9BE8",
                "fill_opacity": 1.0,
            }
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_poly_hole.svg"))
        content = Path(out).read_text()
        assert "evenodd" in content.lower()

    def test_pen_element_smooth(self, tmp_path):
        elements = [
            {
                "type": "pen",
                "points": [[-80, 20], [-40, -30], [0, 10], [40, -20], [80, 5]],
                "smooth": True,
                "color": "#333333",
            }
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_pen.svg"))
        content = Path(out).read_text()
        assert "<path" in content
        assert "C" in content or "c" in content

    def test_compound_union_element(self, tmp_path):
        elements = [
            {
                "type": "compound",
                "id": "cloud",
                "op": "union",
                "shapes": [
                    {"type": "circle", "x": -30, "y": 10, "r": 35},
                    {"type": "circle", "x": 10, "y": -5, "r": 40},
                    {"type": "circle", "x": 40, "y": 15, "r": 28},
                ],
                "color": "#90caf9",
                "fill_opacity": 1.0,
            }
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_compound.svg"))
        content = Path(out).read_text()
        assert "<path" in content

    def test_compound_cut_element(self, tmp_path):
        elements = [
            {
                "type": "compound",
                "op": "cut",
                "shapes": [
                    {"type": "circle", "x": 0, "y": 0, "r": 50},
                    {"type": "circle", "x": 18, "y": -8, "r": 16},
                ],
                "color": "#d55e00",
                "fill_opacity": 1.0,
            }
        ]
        out = create_diagram(elements, [], str(tmp_path / "el_cut.svg"))
        content = Path(out).read_text()
        assert "evenodd" in content.lower()

    def test_polygon_missing_points_raises(self, tmp_path):
        with pytest.raises(ValueError, match="points"):
            create_diagram([{"type": "polygon", "id": "p"}], [], str(tmp_path / "err.svg"))

    def test_compound_missing_shapes_raises(self, tmp_path):
        with pytest.raises(ValueError, match="shapes"):
            create_diagram([{"type": "compound", "id": "c"}], [], str(tmp_path / "err.svg"))


class TestSpecSchema:
    def test_schema_includes_new_types(self):
        enum = get_diagram_schema()["properties"]["elements"]["items"]["properties"]["type"]["enum"]
        for t in ("polygon", "pen", "compound"):
            assert t in enum

    def test_validate_accepts_polygon_pen_compound(self):
        spec = {
            "elements": [
                {"type": "polygon", "id": "p", "points": [[0, 0], [10, 0], [5, 8]]},
                {"type": "pen", "id": "ink", "points": [[0, 0], [20, 10]]},
                {
                    "type": "compound",
                    "id": "u",
                    "op": "union",
                    "shapes": [
                        {"type": "circle", "x": 0, "y": 0, "r": 20},
                        {"type": "circle", "x": 15, "y": 0, "r": 20},
                    ],
                },
            ]
        }
        assert validate_spec(spec) == []

    def test_validate_polygon_needs_points(self):
        issues = validate_spec({"elements": [{"type": "polygon", "id": "p"}]})
        assert any("points" in i for i in issues)

    def test_validate_compound_needs_shapes(self):
        issues = validate_spec({"elements": [{"type": "compound", "id": "c"}]})
        assert any("shapes" in i for i in issues)
