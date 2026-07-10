"""Tests for the geometric linter and auto-correction."""

from techfig.engines.geo_linter import (
    snap_to_grid,
    align_rows_and_cols,
    lint_spec
)

def test_snap_to_grid():
    spec = {
        "elements": [
            {"type": "box", "id": "b1", "x": 103.5, "y": 198.2, "w": 100, "h": 60},
            {"type": "circle", "id": "c1", "x": 199.9, "y": 301.1, "r": 41.5}
        ]
    }
    
    snapped = snap_to_grid(spec, grid_size=20)
    
    # 103.5 / 20 = 5.175 -> 5 * 20 = 100
    assert snapped["elements"][0]["x"] == 100
    # 198.2 / 20 = 9.91 -> 10 * 20 = 200
    assert snapped["elements"][0]["y"] == 200
    
    assert snapped["elements"][1]["x"] == 200
    assert snapped["elements"][1]["y"] == 300
    
    # Check r
    assert snapped["elements"][1]["r"] == 40


def test_align_rows_and_cols():
    # Misaligned row (y coordinates are close but not exact)
    spec = {
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 202},
            {"type": "box", "id": "b2", "x": 300, "y": 198},
            {"type": "box", "id": "b3", "x": 500, "y": 200},
            
            # Substantially different row
            {"type": "box", "id": "b4", "x": 100, "y": 400}
        ]
    }
    
    aligned = align_rows_and_cols(spec, tolerance=10)
    
    y1 = aligned["elements"][0]["y"]
    y2 = aligned["elements"][1]["y"]
    y3 = aligned["elements"][2]["y"]
    
    assert y1 == y2 == y3 == 200.0
    assert aligned["elements"][3]["y"] == 400.0
    
def test_score_geometry_perfect():
    spec = {
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 200, "w": 100, "h": 60},
            {"type": "box", "id": "b2", "x": 300, "y": 200, "w": 100, "h": 60}
        ]
    }
    
    report = lint_spec(spec, grid_size=20)
    assert report.score == 1.0
    assert not report.alignment_issues
    assert not report.grid_issues

def test_score_geometry_messy():
    spec = {
        "elements": [
            {"type": "box", "id": "b1", "x": 103, "y": 202, "w": 100, "h": 60},
            {"type": "box", "id": "b2", "x": 305, "y": 198, "w": 100, "h": 60}
        ]
    }
    
    report = lint_spec(spec, grid_size=20, align_tolerance=20)
    assert report.score < 1.0
    assert len(report.alignment_issues) > 0
    assert len(report.grid_issues) > 0


def _boxes_overlap_x(b1, b2):
    """Check if two boxes overlap on the x-axis given center x and width w."""
    left1, right1 = b1["x"] - b1["w"] / 2, b1["x"] + b1["w"] / 2
    left2, right2 = b2["x"] - b2["w"] / 2, b2["x"] + b2["w"] / 2
    return left1 < right2 and left2 < right1


def _boxes_overlap_y(b1, b2):
    """Check if two boxes overlap on the y-axis given center y and height h."""
    top1, bot1 = b1["y"] - b1["h"] / 2, b1["y"] + b1["h"] / 2
    top2, bot2 = b2["y"] - b2["h"] / 2, b2["y"] + b2["h"] / 2
    return top1 < bot2 and top2 < bot1


def _boxes_overlap(b1, b2):
    return _boxes_overlap_x(b1, b2) and _boxes_overlap_y(b1, b2)


def test_align_does_not_destroy_diagonal_layout():
    """A staircase/diagonal of small boxes must NOT be collapsed into an overlap.

    Previously align_rows_and_cols averaged the coordinates of boxes that were
    within tolerance on BOTH axes, pulling a deliberately-offset diagonal pair
    to the exact same point and creating a full overlap -- destroying a good
    intentional layout. This is the core 'stop destroying good layouts' case.
    """
    # Two small boxes offset diagonally. Within tolerance on both axes, but
    # they do NOT overlap in the input (centers 25px apart, boxes 20px wide).
    spec = {
        "elements": [
            {"type": "box", "id": "a", "x": 100, "y": 100, "w": 20, "h": 20},
            {"type": "box", "id": "b", "x": 125, "y": 125, "w": 20, "h": 20},
        ]
    }
    assert not _boxes_overlap(spec["elements"][0], spec["elements"][1])

    aligned = align_rows_and_cols(spec, tolerance=30.0)

    a, b = aligned["elements"][0], aligned["elements"][1]
    assert not _boxes_overlap(a, b), (
        f"align_rows_and_cols destroyed a good diagonal layout: "
        f"a={a}, b={b} now overlap"
    )


def test_align_does_not_create_overlaps_from_false_row():
    """A staircase of three small boxes must not collapse to a single point.

    The old code grouped purely by one-axis proximity, so a diagonal staircase
    whose steps were within tolerance on both axes got every element averaged
    to the same (x, y), stacking three non-overlapping boxes on top of each
    other.
    """
    # Staircase: each step is offset on both x and y. None overlap
    # (20x20 boxes, centers 25px apart on each axis).
    spec = {
        "elements": [
            {"type": "box", "id": "s1", "x": 100, "y": 100, "w": 20, "h": 20},
            {"type": "box", "id": "s2", "x": 125, "y": 125, "w": 20, "h": 20},
            {"type": "box", "id": "s3", "x": 150, "y": 150, "w": 20, "h": 20},
        ]
    }
    for i in range(len(spec["elements"])):
        for j in range(i + 1, len(spec["elements"])):
            assert not _boxes_overlap(spec["elements"][i], spec["elements"][j])

    aligned = align_rows_and_cols(spec, tolerance=30.0)

    els = aligned["elements"]
    for i in range(len(els)):
        for j in range(i + 1, len(els)):
            assert not _boxes_overlap(els[i], els[j]), (
                f"align_rows_and_cols created an overlap between "
                f"{els[i]} and {els[j]}"
            )


def test_align_still_aligns_genuine_row():
    """Genuine rows (near on x AND near on y) must still be aligned.

    This guards against the fix being too conservative and breaking the
    original, legitimate use case.
    """
    spec = {
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 202, "w": 100, "h": 60},
            {"type": "box", "id": "b2", "x": 300, "y": 198, "w": 100, "h": 60},
            {"type": "box", "id": "b3", "x": 500, "y": 201, "w": 100, "h": 60},
        ]
    }

    aligned = align_rows_and_cols(spec, tolerance=10.0)

    ys = [el["y"] for el in aligned["elements"]]
    assert ys[0] == ys[1] == ys[2], (
        f"genuine row was not aligned: ys={ys}"
    )


def test_align_does_not_collapse_far_apart_on_aligned_axis():
    """Elements whose value on the target axis differs by MORE than tolerance
    must never be pulled together, even if they look like a row otherwise.
    """
    spec = {
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 200, "w": 100, "h": 60},
            {"type": "box", "id": "b2", "x": 300, "y": 260, "w": 100, "h": 60},
        ]
    }
    # y differs by 60, tolerance is 10 -> must not align y.
    aligned = align_rows_and_cols(spec, tolerance=10.0)
    assert aligned["elements"][0]["y"] == 200
    assert aligned["elements"][1]["y"] == 260
