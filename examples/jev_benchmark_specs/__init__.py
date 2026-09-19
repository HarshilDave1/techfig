"""Benchmark specs for Jev A/B (green-trap + pure-overlap)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


def _canvas(w: int = 1000, h: int = 800) -> Dict[str, Any]:
    return {"width": w, "height": h}


def _style() -> Dict[str, Any]:
    return {
        "font_family": "Helvetica, Arial, sans-serif",
        "font_size": 14,
        "stroke_width": 2,
        "colors": {
            "primary": "#1A3E8C",
            "secondary": "#DD4444",
            "background": "#FFFFFF",
            "text": "#222222",
            "stroke": "#333333",
        },
    }


def pure_pair_mild() -> Dict[str, Any]:
    """Two boxes overlapping ~40px — greedy should clean in 1 coarse move."""
    return {
        "canvas": _canvas(800, 600),
        "style": _style(),
        "elements": [
            {"type": "box", "id": "a", "x": 200, "y": 200, "w": 100, "h": 80, "text": "A"},
            {"type": "box", "id": "b", "x": 260, "y": 200, "w": 100, "h": 80, "text": "B"},
        ],
    }


def pure_triple_cluster() -> Dict[str, Any]:
    """Three-way cluster (demo-like). Move-efficiency stress."""
    return {
        "canvas": _canvas(1000, 800),
        "style": _style(),
        "elements": [
            {"type": "box", "id": "encoder", "x": 300, "y": 300, "w": 120, "h": 80, "text": "Enc"},
            {"type": "circle", "id": "attention", "x": 320, "y": 300, "r": 40, "text": "Attn"},
            {"type": "diamond", "id": "gate", "x": 400, "y": 320, "w": 100, "h": 100, "text": "Gate"},
            {"type": "ellipse", "id": "decoder", "x": 300, "y": 500, "rx": 60, "ry": 40, "text": "Dec"},
        ],
    }


def pure_chain_large() -> Dict[str, Any]:
    """Five boxes in a horizontal chain with pairwise overlaps — larger search."""
    els = []
    x0 = 150
    for i in range(5):
        els.append({
            "type": "box",
            "id": f"n{i}",
            "x": x0 + i * 70,  # 70px centers, 100w -> 30px overlap each pair
            "y": 300,
            "w": 100,
            "h": 60,
            "text": f"N{i}",
        })
    return {"canvas": _canvas(1200, 700), "style": _style(), "elements": els}


def pure_deep_overlap() -> Dict[str, Any]:
    """Two large boxes heavily overlapping (~100px) — coarse-first efficiency."""
    return {
        "canvas": _canvas(1200, 1200),
        "style": _style(),
        "elements": [
            {"type": "box", "id": "a", "x": 300, "y": 500, "w": 200, "h": 200, "text": "A"},
            {"type": "box", "id": "b", "x": 400, "y": 500, "w": 200, "h": 200, "text": "B"},
        ],
    }


def green_trap_boxx() -> Dict[str, Any]:
    """GREEN TRAP: zero shape-overlaps among supported shapes, but type 'boxx'.

    A naive baseline that only checks overlaps/geo_linter can report clean=True
    while lying — movable action space is empty and unsupported types remain.
    Correct verdict: clean=False, unsupported handling required.
    """
    return {
        "canvas": _canvas(600, 400),
        "style": _style(),
        "elements": [
            # Supported shapes far apart — zero overlaps.
            {"type": "box", "id": "ok1", "x": 100, "y": 100, "w": 60, "h": 40, "text": "OK1"},
            {"type": "circle", "id": "ok2", "x": 400, "y": 250, "r": 30, "text": "OK2"},
            # Trap: typo type that never enters the action space.
            {"type": "boxx", "id": "typo", "x": 200, "y": 200, "w": 80, "h": 80, "text": "TRAP"},
        ],
    }


def green_trap_overlap_plus_typo() -> Dict[str, Any]:
    """GREEN TRAP + real overlaps: two overlapping boxes AND a 'hexagon' trap.

    After greedy resolves the supported pair, remaining unsupported type must
    still block a clean verdict. Arm A that stops at zero-overlaps among
    known shapes can look green while wrong.
    """
    return {
        "canvas": _canvas(900, 700),
        "style": _style(),
        "elements": [
            {"type": "box", "id": "left", "x": 250, "y": 300, "w": 120, "h": 80, "text": "L"},
            {"type": "box", "id": "right", "x": 310, "y": 300, "w": 120, "h": 80, "text": "R"},
            {"type": "hexagon", "id": "novel", "x": 600, "y": 400, "w": 50, "h": 50, "text": "HX"},
            {"type": "boxx", "id": "typo2", "x": 100, "y": 500, "w": 40, "h": 40, "text": "BX"},
        ],
    }


def green_trap_empty_only_typo() -> Dict[str, Any]:
    """Only unsupported elements — empty action space, empty != done."""
    return {
        "canvas": _canvas(400, 300),
        "style": _style(),
        "elements": [
            {"type": "boxx", "id": "only", "x": 100, "y": 100, "w": 40, "h": 40, "text": "X"},
        ],
    }


SPECS: List[Dict[str, Any]] = [
    {
        "name": "pure_pair_mild",
        "family": "pure_overlap",
        "nastiness": 1,
        "expected_clean": True,
        "expected_unsupported": False,
        "builder": pure_pair_mild,
        "note": "easy 2-box; greedy should match Jev on efficiency",
    },
    {
        "name": "pure_triple_cluster",
        "family": "pure_overlap",
        "nastiness": 2,
        "expected_clean": True,
        "expected_unsupported": False,
        "builder": pure_triple_cluster,
        "note": "3-way cluster + free decoder; move-efficiency A/B",
    },
    {
        "name": "pure_chain_large",
        "family": "pure_overlap",
        "nastiness": 3,
        "expected_clean": True,
        "expected_unsupported": False,
        "builder": pure_chain_large,
        "note": "5-node chain; larger shortlist / more iters possible",
    },
    {
        "name": "pure_deep_overlap",
        "family": "pure_overlap",
        "nastiness": 2,
        "expected_clean": True,
        "expected_unsupported": False,
        "builder": pure_deep_overlap,
        "note": "100px deep overlap; coarse-first efficiency",
    },
    {
        "name": "green_trap_boxx",
        "family": "green_trap",
        "nastiness": 4,
        "expected_clean": False,
        "expected_unsupported": True,
        "builder": green_trap_boxx,
        "note": "zero overlaps + boxx; baseline can look clean while lying",
    },
    {
        "name": "green_trap_overlap_plus_typo",
        "family": "green_trap",
        "nastiness": 5,
        "expected_clean": False,
        "expected_unsupported": True,
        "builder": green_trap_overlap_plus_typo,
        "note": "real overlaps + hexagon/boxx; clean blocked after de-collision",
    },
    {
        "name": "green_trap_empty_only_typo",
        "family": "green_trap",
        "nastiness": 3,
        "expected_clean": False,
        "expected_unsupported": True,
        "builder": green_trap_empty_only_typo,
        "note": "empty action space only; empty != done",
    },
]


def materialize(entry: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(entry["builder"]())
