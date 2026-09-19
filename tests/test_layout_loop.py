"""Unit tests for the de-collision loop driver (task J2): offline, no network."""

import json
import warnings
from pathlib import Path

import pytest

from techfig.engines.layout_actions import (
    UnsupportedShapeTypeWarning,
    find_overlaps,
    state_vector,
)
from techfig.engines.layout_loop import (
    _total_overlap_area,
    greedy_pick,
    rank_moves,
    run_dejumble_loop,
)
from techfig.engines.geo_linter import score_geometry

DEMO_SPEC = Path(__file__).resolve().parent.parent / "examples" / "overlap_demo_spec.json"


@pytest.fixture
def demo_spec():
    return json.loads(DEMO_SPEC.read_text())


def test_rank_moves_only_improving_and_best_first(demo_spec):
    before = len(find_overlaps(demo_spec))
    candidates = rank_moves(demo_spec)
    assert before == 3
    assert candidates, "the overlapping demo spec must offer moves"
    # every candidate strictly improves overlap area or overlap count
    assert all(
        (c["area_after"] < c["area_before"] - 1e-9)
        or (c["overlaps_after"] < c["overlaps_before"])
        for c in candidates
    )
    # sorted best-first: count, then higher score, then area, then cheaper step
    keys = [(c["overlaps_after"], -c["score_after"], c["area_after"], c["cost"])
            for c in candidates]
    assert keys == sorted(keys)
    assert [c["rank"] for c in candidates] == list(range(1, len(candidates) + 1))
    assert [c["id"] for c in candidates] == [f"m{i}" for i in range(1, len(candidates) + 1)]
    # descriptions are populated for the Jev choice question
    assert all(c["description"] for c in candidates)


def test_loop_walks_large_overlap_coarse_first(demo_spec):
    """A single pair overlapping by more than the largest step still resolves.

    Count-only ranking would stall (1 pair stays 1 pair); area ranking lets the
    coarse-first loop walk the correction in a couple of moves.
    """
    spec = {
        "canvas": {"width": 1200, "height": 1200},
        "elements": [
            {"type": "box", "id": "a", "x": 300, "y": 500, "w": 200, "h": 200},
            {"type": "box", "id": "b", "x": 400, "y": 500, "w": 200, "h": 200},
        ],
    }
    assert _total_overlap_area(spec) == 100 * 200  # 100px overlap on x
    coarse = run_dejumble_loop(spec, picker=greedy_pick, max_iters=10)
    assert coarse["clean"] is True
    assert coarse["iterations"] < 5  # coarse steps, not five 20px moves

    fixed = run_dejumble_loop(spec, picker=greedy_pick, steps=(20.0,), max_iters=10)
    assert fixed["clean"] is True
    assert fixed["iterations"] > coarse["iterations"]


def test_greedy_loop_reaches_clean(demo_spec):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a supported spec must not warn
        result = run_dejumble_loop(demo_spec, picker=greedy_pick)

    assert result["clean"] is True
    assert result["stopped_reason"] == "clean"
    assert result["iterations"] >= 1
    assert find_overlaps(result["final_spec"]) == []
    assert score_geometry(result["final_spec"]) == pytest.approx(1.0)
    # input spec is not mutated
    assert len(find_overlaps(demo_spec)) == 3
    # every non-terminal trace step is an applied move
    assert result["trace"][-1]["event"] == "clean"


def test_empty_action_space_is_not_clean():
    """Zero shapes must never read as a finished loop (J1 empty != done)."""
    spec = {
        "canvas": {"width": 400, "height": 300},
        "elements": [
            {"type": "boxx", "id": "typo", "x": 100, "y": 100, "w": 40, "h": 40},
        ],
    }
    with pytest.warns(UnsupportedShapeTypeWarning):
        result = run_dejumble_loop(spec, picker=greedy_pick)
    assert result["clean"] is False
    assert "empty action space" in result["stopped_reason"]
    assert result["trace"][0]["event"] == "no_action_space"


def test_unsupported_types_block_a_clean_verdict():
    """Zero overlaps over an unsupported type is NOT certifiable as clean."""
    spec = {
        "canvas": {"width": 400, "height": 300},
        "elements": [
            {"type": "box", "id": "b1", "x": 100, "y": 100, "w": 40, "h": 40},
            {"type": "hexagon", "id": "novel", "x": 300, "y": 100, "w": 40, "h": 40},
        ],
    }
    with pytest.warns(UnsupportedShapeTypeWarning):
        result = run_dejumble_loop(spec, picker=greedy_pick)
    assert result["clean"] is False
    assert "unsupported element types" in result["stopped_reason"]
    assert result["trace"][0]["event"] == "unsupported_types"


def test_picker_is_called_with_state_and_shortlist(demo_spec):
    calls = []

    def scripted(state, candidates):
        calls.append((state, candidates))
        meta = {"picker": "test", "picked_id": candidates[0]["id"]}
        return candidates[0]["action"], meta

    result = run_dejumble_loop(demo_spec, picker=scripted, top_k=3)
    assert result["clean"] is True
    assert calls, "the picker must be invoked"
    state, candidates = calls[0]
    assert set(state.keys()) >= {"canvas", "shapes", "overlaps", "geometry_score"}
    assert len(candidates) <= 3
    # provenance is recorded in the trace
    applied = [s for s in result["trace"] if s["event"] == "apply"]
    assert applied and applied[0]["picker"]["picker"] == "test"
    assert applied[0]["picked_id"] == "m1"


def test_picker_declining_stops_loop_without_claiming_clean(demo_spec):
    def declining(state, candidates):
        return None, {"picker": "test", "reason": "declined"}

    result = run_dejumble_loop(demo_spec, picker=declining)
    assert result["clean"] is False
    assert result["stopped_reason"] == "picker declined to move"
    assert result["trace"][0]["event"] == "picker_declined"
    # nothing was applied: overlaps unchanged
    assert len(find_overlaps(result["final_spec"])) == 3


def test_max_iters_is_reported_not_masked():
    spec = {
        "canvas": {"width": 1000, "height": 1000},
        "elements": [
            {"type": "box", "id": "a", "x": 200, "y": 200, "w": 80, "h": 80},
            {"type": "box", "id": "b", "x": 240, "y": 200, "w": 80, "h": 80},
        ],
    }
    # max_iters=0 -> the loop body never runs; must not claim clean.
    result = run_dejumble_loop(spec, picker=greedy_pick, max_iters=0)
    assert result["clean"] is False
    assert "max_iters" in result["stopped_reason"]


def test_state_vector_drives_the_loop(demo_spec):
    """The first picker call receives a JSON-serializable state_vector."""
    seen = {}

    def picker(state, candidates):
        json.dumps(state)  # must not raise
        seen.setdefault("state", state)
        return candidates[0]["action"], {"picker": "test"}

    run_dejumble_loop(demo_spec, picker=picker)
    assert seen["state"]["geometry_score"] == pytest.approx(
        state_vector(demo_spec)["geometry_score"]
    )
    assert seen["state"]["overlaps"] == state_vector(demo_spec)["overlaps"]


def test_make_jev_picker_maps_choice_back_to_action(demo_spec, monkeypatch):
    from techfig.engines import jev_client
    from techfig.engines.layout_loop import make_jev_picker

    def fake_pick_action(state, candidates, model=None, api_key=None, timeout_s=60.0):
        # choose the second candidate -> must map back to its action
        return {"choice": candidates[1]["id"], "confidence": 0.7,
                "probabilities": {}, "model": "jev-test", "usage": None}

    monkeypatch.setattr(jev_client, "pick_action", fake_pick_action)
    picker = make_jev_picker()
    candidates = rank_moves(demo_spec, top_k=4)
    action, meta = picker(state_vector(demo_spec), candidates)
    assert action == candidates[1]["action"]
    assert meta["picker"] == "jev"
    assert meta["picked_id"] == candidates[1]["id"]
    assert meta["confidence"] == 0.7


def test_make_jev_picker_declines_on_unknown_choice(demo_spec, monkeypatch):
    from techfig.engines import jev_client
    from techfig.engines.layout_loop import make_jev_picker

    def fake_pick_action(state, candidates, model=None, api_key=None, timeout_s=60.0):
        return {"choice": "other", "confidence": 0.5, "probabilities": {},
                "model": "jev-test", "usage": None}

    monkeypatch.setattr(jev_client, "pick_action", fake_pick_action)
    candidates = rank_moves(demo_spec, top_k=4)
    action, meta = make_jev_picker()(state_vector(demo_spec), candidates)
    assert action is None
    assert "declining" in meta["reason"]
