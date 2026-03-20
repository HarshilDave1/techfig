"""Tests for the geometric linter and auto-correction."""

import pytest
from techfig.engines.geo_linter import (
    snap_to_grid,
    align_rows_and_cols,
    lint_spec,
    score_geometry
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
