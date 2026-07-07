"""Tests for SVGBuilder <defs> helpers."""
from pathlib import Path

import drawsvg as draw

from techfig.utils.svg_builder import SVGBuilder


def test_linear_gradient_def_and_usage(tmp_path):
    builder = SVGBuilder(200, 120)
    builder.add_linear_gradient(
        "grad1",
        stops=[
            (0, "#ffffff"),
            (1, "#000000"),
        ],
        x1=0,
        y1=0,
        x2=200,
        y2=0,
    )
    builder.add_box(100, 60, 140, 70, text="Gradient", color="url(#grad1)", element_id="box1")

    out = tmp_path / "gradient.svg"
    builder.save(str(out))
    content = Path(out).read_text()

    assert "<defs>" in content
    assert '<linearGradient' in content
    assert 'id="grad1"' in content
    assert 'fill="url(#grad1)"' in content


def test_pattern_def_and_usage(tmp_path):
    builder = SVGBuilder(160, 160)
    builder.add_pattern(
        "pattern1",
        width=12,
        height=12,
        elements=[
            draw.Rectangle(0, 0, 12, 12, fill="#ffffff"),
            draw.Line(0, 0, 12, 12, stroke="#666666", stroke_width=1),
        ],
    )
    builder.add_circle(80, 80, 45, text="Pattern", color="url(#pattern1)", element_id="circle1")

    out = tmp_path / "pattern.svg"
    builder.save(str(out))
    content = Path(out).read_text()

    assert '<pattern' in content
    assert 'id="pattern1"' in content
    assert 'fill="url(#pattern1)"' in content


def test_filter_def_and_usage(tmp_path):
    builder = SVGBuilder(160, 120)
    blur = draw.FilterItem("feGaussianBlur", stdDeviation=3)
    builder.add_filter("blur1", elements=[blur])
    builder.drawing.append(draw.Circle(80, 60, 30, fill="#ff0000", filter="url(#blur1)"))

    out = tmp_path / "filter.svg"
    builder.save(str(out))
    content = Path(out).read_text()

    assert '<filter id="blur1"' in content
    assert 'feGaussianBlur' in content
    assert 'filter="url(#blur1)"' in content


def test_add_def_registers_raw_definition(tmp_path):
    builder = SVGBuilder(120, 120)
    gradient = draw.LinearGradient(0, 0, 120, 0, id="rawgrad")
    gradient.add_stop(0, "#fff")
    gradient.add_stop(1, "#000")

    builder.add_def(gradient)
    builder.add_box(60, 60, 90, 50, text="Raw", color="url(#rawgrad)", element_id="rawbox")

    out = tmp_path / "rawdef.svg"
    builder.save(str(out))
    content = Path(out).read_text()

    assert 'id="rawgrad"' in content
    assert 'fill="url(#rawgrad)"' in content
