"""Unit tests for the shape-move layout actions module (task J1)."""

import copy
import json
import pytest

from techfig.engines.layout_actions import (
    DEFAULT_MOVE_STEPS,
    UnsupportedShapeTypeError,
    UnsupportedShapeTypeWarning,
    apply_action,
    enumerate_actions,
    find_overlaps,
    layout_status,
    list_shapes,
    state_vector,
)


def test_whitelist_in_lockstep_with_diagram_schema():
    """The shape whitelist must stay in lockstep with DIAGRAM_SCHEMA's enum."""
    from techfig.engines.sketch_interpreter import DIAGRAM_SCHEMA
    from techfig.engines import geo_linter

    enum = set(
        DIAGRAM_SCHEMA["properties"]["elements"]["items"]["properties"]["type"]["enum"]
    )
    assert enum == set(geo_linter.DIAGRAM_ELEMENT_TYPES)
    assert geo_linter.SHAPE_TYPES <= enum
    assert geo_linter.SHAPE_TYPES == {"box", "circle", "diamond", "ellipse", "triangle"}
    assert not (geo_linter.NON_SHAPE_TYPES & geo_linter.SHAPE_TYPES)


def test_unsupported_type_warns_loudly_and_never_looks_clean():
    """A typo'd / novel type must warn; zero shapes must not read as done."""
    spec = {
        "canvas": {"width": 400, "height": 300},
        "elements": [
            {"type": "boxx", "id": "typo_box", "x": 100, "y": 100, "w": 40, "h": 20},
            {"type": "hexagon", "id": "novel", "x": 100, "y": 100, "w": 40, "h": 20},
            {"type": "text", "id": "t1", "x": 10, "y": 10, "text": "hi"},
        ],
    }

    with pytest.warns(UnsupportedShapeTypeWarning) as rec:
        shapes = list_shapes(spec)
    msg = str(rec[0].message)
    assert "elements[0].type='boxx'" in msg
    assert "elements[1].type='hexagon'" in msg
    assert "NOT a clean layout" in msg
    assert shapes == []

    # The action space is empty -- and the status says why, rather than "done".
    with pytest.warns(UnsupportedShapeTypeWarning):
        status = layout_status(spec)
    assert status["shapes"] == 0
    assert status["usable"] is False
    assert status["unsupported"] == [
        {"el_index": 0, "type": "boxx"},
        {"el_index": 1, "type": "hexagon"},
    ]
    assert status["overlaps"] == []

    # Strict mode raises instead of warning.
    with pytest.raises(UnsupportedShapeTypeError, match="hexagon"):
        list_shapes(spec, strict=True)
    with pytest.raises(UnsupportedShapeTypeError):
        enumerate_actions(spec, strict=True)


def test_known_non_shape_types_do_not_warn():
    """Valid DIAGRAM_SCHEMA non-shape types (text/line/path/...) stay silent."""
    import warnings as _w

    spec = {
        "canvas": {"width": 400, "height": 300},
        "elements": [
            {"type": "text", "id": "t1", "x": 10, "y": 10, "text": "hi"},
            {"type": "line", "x1": 0, "y1": 0, "x2": 5, "y2": 5},
            {"type": "path", "points": [[0, 0], [1, 1]]},
            {"type": "legend", "id": "lg", "x": 300, "y": 200, "w": 60, "h": 40},
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": 40, "h": 20},
        ],
    }
    with _w.catch_warnings():
        _w.simplefilter("error")
        shapes = list_shapes(spec)
    assert [s["id"] for s in shapes] == ["b1"]
    with _w.catch_warnings():
        _w.simplefilter("error")
        status = layout_status(spec)
    assert status["unsupported"] == []
    assert status["usable"] is True


def test_enumerate_actions_coarse_first_scaled_steps():
    """Scaled steps offer coarse magnitudes first, so 100px lands in one move."""
    spec = {
        "canvas": {"width": 1000, "height": 1000},
        "elements": [
            {"type": "box", "id": "far", "x": 200, "y": 200, "w": 40, "h": 40},
        ],
    }

    # Fixed 20px step needs 5 iterations to cover 100px.
    fixed = enumerate_actions(spec, step=20.0)
    assert len(fixed) == 4
    assert {(a["dx"], a["dy"]) for a in fixed} == {
        (20.0, 0.0), (-20.0, 0.0), (0.0, 20.0), (0.0, -20.0)
    }

    # Scaled steps: coarse-first ordering, and the 100px correction is available.
    scaled = enumerate_actions(spec, steps=DEFAULT_MOVE_STEPS)
    assert len(scaled) == 12
    assert (scaled[0]["dx"], scaled[0]["dy"]) == (-80.0, 0.0)
    assert {(a["dx"], a["dy"]) for a in scaled[:4]} == {
        (-80.0, 0.0), (80.0, 0.0), (0.0, -80.0), (0.0, 80.0)
    }
    magnitudes_seen = {abs(a["dx"]) or abs(a["dy"]) for a in scaled}
    assert magnitudes_seen == {80.0, 40.0, 20.0}
    assert scaled.index({"shape_id": "far", "dx": 80.0, "dy": 0.0, "el_index": 0}) < 4
    # Coarse ordering is enforced even when the caller passes fine-first.
    assert enumerate_actions(spec, steps=(20.0, 80.0))[0]["dx"] == -80.0
    # Deduped.
    assert len(enumerate_actions(spec, steps=(20.0, 20.0, 40.0))) == 8

    # Bad inputs are rejected explicitly.
    with pytest.raises(ValueError, match="non-empty"):
        enumerate_actions(spec, steps=())
    with pytest.raises(ValueError, match="positive"):
        enumerate_actions(spec, steps=(0.0, 20.0))


def test_coarse_step_dropped_near_edge_keeps_fine_steps():
    """A coarse move that leaves the CENTRED canvas is dropped; the fine step survives."""
    spec = {
        "canvas": {"width": 200, "height": 200},
        "elements": [
            {"type": "box", "id": "near_edge", "x": 60, "y": 0, "w": 40, "h": 40},
        ],
    }
    actions = enumerate_actions(spec, steps=DEFAULT_MOVE_STEPS)
    dirs = {(a["dx"], a["dy"]) for a in actions}
    # Canvas is CENTRED: x, y in -100..100 (origin is the canvas centre).
    # bbox (40, -20, 80, 20). On +x: +80 -> right 160 (out), +40 -> right 120
    # (out), +20 -> right 100 (exactly on the edge, kept).
    assert (80.0, 0.0) not in dirs
    assert (40.0, 0.0) not in dirs
    assert (20.0, 0.0) in dirs
    # Coarse -x stays inside the centred canvas.
    assert (-80.0, 0.0) in dirs
    assert len(actions) == 10


def test_list_shapes_finds_shapes_and_synthesizes_ids():
    """Verify list_shapes detects shapes, ignores non-shapes, and synthesizes stable ids."""
    spec = {
        "canvas": {"width": 400, "height": 300},
        "elements": [
            {"type": "text", "id": "t1", "x": 50, "y": 50, "text": "Heading"},
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": 40, "h": 20},
            {"type": "line", "x1": 0, "y1": 0, "x2": 50, "y2": 50},
            {"type": "circle", "x": 200, "y": 150, "r": 25},  # missing id
            {"type": "diamond", "x": 300, "y": 200, "w": 30, "h": 30},  # missing id
        ],
    }

    shapes = list_shapes(spec)
    assert len(shapes) == 3

    # Shape 0: b1
    assert shapes[0]["id"] == "b1"
    assert shapes[0]["type"] == "box"
    assert shapes[0]["el_index"] == 1
    assert shapes[0]["bbox"] == (80.0, 90.0, 120.0, 110.0)

    # Shape 1: circle, synthesized id shape_3
    assert shapes[1]["id"] == "shape_3"
    assert shapes[1]["type"] == "circle"
    assert shapes[1]["el_index"] == 3
    assert shapes[1]["bbox"] == (175.0, 125.0, 225.0, 175.0)

    # Shape 2: diamond, synthesized id shape_4
    assert shapes[2]["id"] == "shape_4"
    assert shapes[2]["type"] == "diamond"
    assert shapes[2]["el_index"] == 4
    assert shapes[2]["bbox"] == (285.0, 185.0, 315.0, 215.0)


def test_find_overlaps_detects_overlapping_pair_and_clean_layout():
    """Verify find_overlaps flags overlapping pairs and returns empty for non-overlapping."""
    # Clean layout (separated shapes)
    clean_spec = {
        "canvas": {"width": 500, "height": 500},
        "elements": [
            {"type": "box", "id": "box_left", "x": 100, "y": 100, "w": 50, "h": 50},
            {"type": "box", "id": "box_right", "x": 300, "y": 100, "w": 50, "h": 50},
        ],
    }
    clean_overlaps = find_overlaps(clean_spec)
    assert clean_overlaps == []

    # Overlapping layout (box_a and box_b overlap)
    overlapping_spec = {
        "canvas": {"width": 500, "height": 500},
        "elements": [
            {"type": "box", "id": "box_a", "x": 100, "y": 100, "w": 60, "h": 60},
            {"type": "circle", "id": "circle_b", "x": 120, "y": 110, "r": 20},
            {"type": "box", "id": "box_far", "x": 400, "y": 400, "w": 50, "h": 50},
        ],
    }
    overlaps = find_overlaps(overlapping_spec)
    assert len(overlaps) == 1
    assert overlaps[0] == ("box_a", "circle_b")


def test_enumerate_actions_excludes_out_of_canvas_moves():
    """Verify out-of-canvas moves are omitted under the CENTRED canvas rect."""
    # Canvas is CENTRED: a 100x100 canvas spans x, y in -50..50.
    # Shape x=20, y=20, w=30, h=30 -> bbox (5, 5, 35, 35).
    #   -20 on x -> left -15, right 15   (inside)  -> included
    #   -20 on y -> top -15, bottom 15   (inside)  -> included
    #   +20 on x -> right 55 > 50        (outside) -> excluded
    #   +20 on y -> bottom 55 > 50       (outside) -> excluded
    spec = {
        "canvas": {"width": 100, "height": 100},
        "elements": [
            {"type": "box", "id": "corner_box", "x": 20, "y": 20, "w": 30, "h": 30},
        ],
    }

    actions = enumerate_actions(spec, step=20.0)
    assert len(actions) == 2
    move_directions = [(a["dx"], a["dy"]) for a in actions]
    assert (-20.0, 0.0) in move_directions
    assert (0.0, -20.0) in move_directions
    assert (20.0, 0.0) not in move_directions
    assert (0.0, 20.0) not in move_directions

    # Without canvas, all 4 moves should be generated
    spec_no_canvas = {
        "elements": [
            {"type": "box", "id": "corner_box", "x": 20, "y": 20, "w": 30, "h": 30},
        ],
    }
    actions_no_canvas = enumerate_actions(spec_no_canvas, step=20.0)
    assert len(actions_no_canvas) == 4


def test_apply_action_does_not_mutate_input_and_moves_target():
    """Verify apply_action returns a new spec, does not mutate original, and updates coords."""
    original_spec = {
        "canvas": {"width": 400, "height": 400},
        "elements": [
            {"type": "box", "id": "b1", "x": 100.0, "y": 100.0, "w": 50, "h": 50},
            {"type": "circle", "id": "c1", "x": 200.0, "y": 200.0, "r": 25},
        ],
    }
    spec_copy = copy.deepcopy(original_spec)

    action = {"shape_id": "b1", "dx": 20.0, "dy": -10.0, "el_index": 0}
    new_spec = apply_action(original_spec, action)

    # Input spec must NOT be mutated
    assert original_spec == spec_copy
    assert original_spec["elements"][0]["x"] == 100.0
    assert original_spec["elements"][0]["y"] == 100.0

    # New spec must reflect the move
    assert new_spec["elements"][0]["x"] == 120.0
    assert new_spec["elements"][0]["y"] == 90.0
    # Other element unchanged
    assert new_spec["elements"][1]["x"] == 200.0
    assert new_spec["elements"][1]["y"] == 200.0

    # Unknown shape_id raises ValueError
    with pytest.raises(ValueError, match="Unknown shape_id"):
        apply_action(original_spec, {"shape_id": "nonexistent", "dx": 10, "dy": 10})


def test_apply_action_reduces_overlaps():
    """Verify that moving an overlapping shape apart reduces find_overlaps count."""
    spec = {
        "canvas": {"width": 600, "height": 600},
        "elements": [
            {"type": "box", "id": "box1", "x": 200.0, "y": 200.0, "w": 80, "h": 80},
            {"type": "box", "id": "box2", "x": 240.0, "y": 200.0, "w": 80, "h": 80},
        ],
    }

    initial_overlaps = find_overlaps(spec)
    assert len(initial_overlaps) == 1
    assert initial_overlaps[0] == ("box1", "box2")

    # Move box2 far to the right (+100 px)
    move_action = {"shape_id": "box2", "dx": 100.0, "dy": 0.0}
    resolved_spec = apply_action(spec, move_action)

    resolved_overlaps = find_overlaps(resolved_spec)
    assert len(resolved_overlaps) == 0


def test_state_vector_is_json_serializable():
    """Verify state_vector produces expected keys, converts tuples to lists, and dumps to JSON."""
    spec = {
        "canvas": {"width": 500, "height": 400},
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": 50, "h": 40},
            {"type": "circle", "id": "c1", "x": 120, "y": 110, "r": 30},
        ],
    }

    sv = state_vector(spec)
    assert "canvas" in sv
    assert sv["canvas"] == {"width": 500, "height": 400}

    assert "shapes" in sv
    assert len(sv["shapes"]) == 2
    for s in sv["shapes"]:
        assert set(s.keys()) == {"id", "type", "bbox"}
        assert isinstance(s["bbox"], list)
        assert len(s["bbox"]) == 4

    assert "overlaps" in sv
    assert sv["overlaps"] == [["b1", "c1"]]
    assert isinstance(sv["overlaps"][0], list)

    assert "geometry_score" in sv
    assert isinstance(sv["geometry_score"], float)

    # Must be cleanly json.dumps-able
    json_str = json.dumps(sv)
    assert isinstance(json_str, str)
    decoded = json.loads(json_str)
    assert decoded["canvas"] == sv["canvas"]
    assert decoded["overlaps"] == [["b1", "c1"]]


def test_enumerate_actions_handles_centred_canvas_coordinates():
    """Regression: techfig's origin is the canvas CENTRE, so a real (LLM-authored)
    figure has negative x/y. The canvas-bounds filter must use the centred rect
    (-w/2..w/2, -h/2..h/2); a top-left rect rejected every move and silently
    returned zero candidates, so the cleanup loop could never fix such figures.
    """
    spec = {
        "canvas": {"width": 1200, "height": 800},
        "elements": [
            {"type": "box", "id": "boxA", "x": -180, "y": -30, "w": 220, "h": 140},
            {"type": "box", "id": "boxB", "x": -40, "y": 40, "w": 220, "h": 140},
        ],
    }
    assert find_overlaps(spec) == [("boxA", "boxB")], "sanity: the two boxes overlap"

    actions = enumerate_actions(spec, steps=DEFAULT_MOVE_STEPS)
    assert actions, "centred (negative-coordinate) figures must still yield candidates"

    reduced = [
        a
        for a in actions
        if len(find_overlaps(apply_action(spec, a))) < len(find_overlaps(spec))
    ]
    assert reduced, "at least one candidate move must reduce the overlap count"
