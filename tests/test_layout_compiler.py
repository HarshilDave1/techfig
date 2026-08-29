"""Layout compiler: fit canvas and park labels so dense reconstructs stay on-frame.

Vision-bench failure mode: models emit a valid schema, then walk content off a
centered 1200×800 canvas. compile_layout() is a deterministic post-LLM pass.
"""
from techfig.engines.geo_linter import compile_layout


def _overflow_two_boxes():
    return {
        "canvas": {"width": 400, "height": 200},
        "elements": [
            {"type": "box", "id": "a", "x": -300, "y": 0, "w": 200, "h": 80, "text": "A"},
            {"type": "box", "id": "b", "x": 300, "y": 0, "w": 200, "h": 80, "text": "B"},
        ],
        "connections": [],
    }


def test_fit_canvas_expands_when_content_overflows():
    """Boxes at x=±300, w=200 span [-400, 400]. Canvas 400 is too small.

    After compile, half-width >= 400 + margin so nothing clips.
    """
    out = compile_layout(_overflow_two_boxes(), margin=40)
    # content x-span is 800; plus 40px each side → width >= 880
    assert out["canvas"]["width"] >= 880
    # box h=80; plus 40px each side → height >= 160
    assert out["canvas"]["height"] >= 160
    # original element positions are preserved (we grow the frame, not the scene)
    ids = {el["id"]: el for el in out["elements"]}
    assert ids["a"]["x"] == -300
    assert ids["b"]["x"] == 300


def test_park_labels_moves_text_out_of_shape():
    """A text label centered on a box must leave the box after compile."""
    spec = {
        "canvas": {"width": 800, "height": 400},
        "elements": [
            {"type": "box", "id": "cell", "x": 0, "y": 0, "w": 200, "h": 80},
            {"type": "text", "id": "lbl", "x": 0, "y": 0, "text": "absorber", "font_size": 14},
        ],
        "connections": [],
    }
    out = compile_layout(spec, margin=40)
    text = next(el for el in out["elements"] if el["id"] == "lbl")
    box = next(el for el in out["elements"] if el["id"] == "cell")
    # text center must sit outside the box AABB (with a small gutter)
    half_w, half_h = box["w"] / 2, box["h"] / 2
    dx = abs(text["x"] - box["x"])
    dy = abs(text["y"] - box["y"])
    outside = dx > half_w or dy > half_h
    assert outside, f"label still inside box at ({text['x']}, {text['y']})"


def test_compile_layout_does_not_shrink_already_fitting_canvas():
    spec = {
        "canvas": {"width": 1200, "height": 800},
        "elements": [
            {"type": "box", "id": "a", "x": 0, "y": 0, "w": 100, "h": 40},
        ],
        "connections": [],
    }
    out = compile_layout(spec, margin=40)
    assert out["canvas"]["width"] == 1200
    assert out["canvas"]["height"] == 800


def test_render_from_spec_grows_canvas_to_fit(tmp_path):
    """reconstruct must compile layout before drawing, not clip overflow."""
    from techfig.engines.sketch_interpreter import render_from_spec

    spec = _overflow_two_boxes()
    out = tmp_path / "fit.svg"
    render_from_spec(spec, str(out))
    svg = out.read_text()
    # drawsvg viewBox / width should reflect the grown canvas (>= 880)
    assert 'width="880"' in svg or 'width="881"' in svg or 'width="882"' in svg
    # original boxes still present
    assert "A" in svg and "B" in svg
