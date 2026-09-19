"""De-collision loop driver: state_vector -> enumerate -> pick -> apply -> score.

This is the J2 loop the Jev demo runs.  It closes the J1 gaps into the loop:

* Unsupported (typo / novel) element types are surfaced by ``list_shapes`` /
  ``layout_status``; ``run_dejumble_loop`` reports ``clean=False`` whenever the
  action space is empty or carries unsupported types, so **empty != done**.
* Coarse-first scaled moves (``DEFAULT_MOVE_STEPS``) are the default, so a
  100px correction lands in one move instead of five fixed 20px moves.

The chooser is pluggable.  ``greedy_pick`` is the deterministic fallback;
the Jev demo passes a picker backed by ``jev_client``.  A picker has the
signature::

    picker(state: dict, candidates: list[dict]) -> (action | None, meta: dict)

where ``candidates`` are the overlap-reducing moves ranked best-first (each a
dict with ``id``/``action``/``overlaps_after``/``score_after``/``description``)
and ``meta`` is free-form provenance recorded in the trace (e.g. Jev's chosen
id, confidence, probabilities).  Returning ``(None, meta)`` declines to move.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from techfig.engines.geo_linter import _shape_bbox, extract_shapes, score_geometry
from techfig.engines.layout_actions import (
    DEFAULT_MOVE_STEPS,
    apply_action,
    enumerate_actions,
    find_overlaps,
    layout_status,
    state_vector,
)

Picker = Callable[
    [Dict[str, Any], List[Dict[str, Any]]],
    Tuple[Optional[Dict[str, Any]], Dict[str, Any]],
]


def _total_overlap_area(spec: Dict[str, Any]) -> float:
    """Sum of pairwise AABB intersection areas over all movable shapes.

    A continuous progress measure: count alone can stay flat while a large
    overlap shrinks, so ranking on area lets the loop walk a >step correction
    instead of stalling on the first non-separating move.
    """
    boxes = [
        bbox
        for bbox in (_shape_bbox(el) for el in extract_shapes(spec))
        if bbox is not None
    ]
    total = 0.0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            l1, t1, r1, b1 = boxes[i]
            l2, t2, r2, b2 = boxes[j]
            iw = min(r1, r2) - max(l1, l2)
            ih = min(b1, b2) - max(t1, t2)
            if iw > 0 and ih > 0:
                total += iw * ih
    return total


def _describe(action: Dict[str, Any], overlaps_before: int, score_before: float,
              overlaps_after: int, score_after: float,
              area_before: float = 0.0, area_after: float = 0.0) -> str:
    """Human/LLM-readable one-liner for a candidate move."""
    def _dir(v: float, pos: str, neg: str) -> str:
        if v > 0:
            return f"{+v:g} {pos}"
        if v < 0:
            return f"{v:g} {neg}"
        return "0"

    parts = []
    if action["dx"]:
        parts.append(_dir(action["dx"], "right", "left"))
    if action["dy"]:
        parts.append(_dir(action["dy"], "down", "up"))
    move = ", ".join(parts) if parts else "no-op"
    return (
        f"Move {action['shape_id']!r} {move}: overlaps {overlaps_before} -> "
        f"{overlaps_after}, overlap area {area_before:g} -> {area_after:g} px^2, "
        f"geometry score {score_before:.3f} -> {score_after:.3f}"
    )


def rank_moves(
    spec: Dict[str, Any],
    steps: Optional[Sequence[float]] = None,
    top_k: Optional[int] = 6,
    strict: bool = False,
) -> List[Dict[str, Any]]:
    """Rank candidate moves by how well they resolve overlaps (best first).

    A move is kept only if it *strictly* reduces the overlap area or the
    overlap count, so an empty list means "no improving move", never "already
    clean".  Ordering is by overlap count (the terminal metric), then the
    higher resulting geometry score, then overlap area, then the smaller step
    (cheapest correction) -- so a coarse step still lands a large correction in
    one move while tie-breaking keeps the cleanest-scoring layout.
    """
    if steps is None:
        steps = DEFAULT_MOVE_STEPS
    overlaps_before = len(find_overlaps(spec))
    area_before = _total_overlap_area(spec)
    score_before = float(score_geometry(spec))

    candidates: List[Dict[str, Any]] = []
    for action in enumerate_actions(spec, steps=steps, strict=strict):
        moved = apply_action(spec, action)
        overlaps_after = len(find_overlaps(moved))
        area_after = _total_overlap_area(moved)
        improves = (area_after < area_before - 1e-9) or (
            overlaps_after < overlaps_before
        )
        if not improves:
            continue
        score_after = float(score_geometry(moved))
        cost = abs(action["dx"]) + abs(action["dy"])
        candidates.append({
            "action": action,
            "overlaps_before": overlaps_before,
            "overlaps_after": overlaps_after,
            "area_before": area_before,
            "area_after": area_after,
            "score_before": score_before,
            "score_after": score_after,
            "cost": cost,
            "description": _describe(action, overlaps_before, score_before,
                                     overlaps_after, score_after,
                                     area_before, area_after),
        })

    # Stable sort, then label the surviving shortlist m1..mK by rank so the ids
    # handed to the picker (and to Jev) are dense and rank-ordered.
    for order, cand in enumerate(candidates):
        cand["_order"] = order
    candidates.sort(
        key=lambda c: (c["overlaps_after"], -c["score_after"], c["area_after"],
                       c["cost"], c["_order"])
    )
    if top_k is not None:
        candidates = candidates[:top_k]
    for rank, cand in enumerate(candidates, start=1):
        cand.pop("_order", None)
        cand["id"] = f"m{rank}"
        cand["rank"] = rank
    return candidates


def greedy_pick(
    state: Dict[str, Any], candidates: List[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Deterministic fallback: take the best-ranked (first) candidate."""
    if not candidates:
        return None, {"picker": "greedy", "reason": "no candidates"}
    best = candidates[0]
    return best["action"], {
        "picker": "greedy",
        "picked_id": best["id"],
        "picked_description": best["description"],
    }


def make_jev_picker(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_s: float = 60.0,
) -> Picker:
    """Build a picker that asks Jev which candidate move to apply.

    Jev is a classifier: the candidates become a ``choice`` question and the
    returned ``choice`` id is mapped back to the action.  A choice of ``other``
    (or an id that is not in the shortlist) declines the move -- the caller
    decides whether to fall back.
    """
    def picker(
        state: Dict[str, Any], candidates: List[Dict[str, Any]]
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        from techfig.engines import jev_client  # local import: keep this module offline

        result = jev_client.pick_action(
            state,
            candidates,
            model=model or jev_client.DEFAULT_MODEL,
            api_key=api_key,
            timeout_s=timeout_s,
        )
        meta = {
            "picker": "jev",
            "model": result.get("model"),
            "raw_choice": result.get("choice"),
            "confidence": result.get("confidence"),
            "probabilities": result.get("probabilities"),
            # Pass through response usage so benchmarks can sum tokens/cost.
            "usage": result.get("usage"),
        }
        choice = result.get("choice")
        for cand in candidates:
            if cand["id"] == choice:
                meta["picked_id"] = cand["id"]
                meta["picked_description"] = cand["description"]
                return cand["action"], meta
        meta["reason"] = f"jev chose {choice!r}, not a shortlisted move; declining"
        return None, meta

    return picker


def run_dejumble_loop(
    spec: Dict[str, Any],
    picker: Optional[Picker] = None,
    *,
    steps: Optional[Sequence[float]] = None,
    top_k: Optional[int] = 6,
    max_iters: int = 12,
    strict: bool = False,
) -> Dict[str, Any]:
    """Run state_vector -> enumerate/rank -> pick -> apply -> score until clean.

    Stops when the layout is clean (zero overlaps over a non-empty, fully
    supported action space), when no move reduces overlaps, when the picker
    declines, or after ``max_iters``.

    Returns::

        {
          "clean": bool,               # True only for a certified-clean layout
          "stopped_reason": str,
          "iterations": int,
          "initial_status": {...},     # layout_status of the input spec
          "final_status": {...},       # layout_status of the final spec
          "final_spec": {...},
          "trace": [ {...per-iteration...} ],
        }
    """
    picker = picker or greedy_pick
    current = copy.deepcopy(spec)
    initial_status = layout_status(current)
    trace: List[Dict[str, Any]] = []

    def finish(clean: bool, reason: str, iters: int) -> Dict[str, Any]:
        return {
            "clean": clean,
            "stopped_reason": reason,
            "iterations": iters,
            "initial_status": initial_status,
            "final_status": layout_status(current),
            "final_spec": current,
            "trace": trace,
        }

    for it in range(1, max_iters + 1):
        status = layout_status(current)  # warns loudly on unsupported types
        overlaps = len(status["overlaps"])
        score = status["geometry_score"]

        # --- clean requires a non-empty, fully supported action space ---
        if overlaps == 0:
            if status["shapes"] == 0:
                trace.append({
                    "iter": it, "event": "no_action_space",
                    "overlaps": 0, "score": score,
                    "unsupported": status["unsupported"],
                })
                return finish(False, "empty action space: zero movable shapes "
                                     "(empty != done)", it - 1)
            if status["unsupported"]:
                trace.append({
                    "iter": it, "event": "unsupported_types",
                    "overlaps": 0, "score": score,
                    "unsupported": status["unsupported"],
                })
                return finish(False, "unsupported element types present; cannot "
                                     "certify a clean layout", it - 1)
            trace.append({
                "iter": it, "event": "clean", "overlaps": 0, "score": score,
            })
            return finish(True, "clean", it - 1)

        state = state_vector(current)
        candidates = rank_moves(current, steps=steps, top_k=top_k, strict=strict)
        if not candidates:
            trace.append({
                "iter": it, "event": "stalled", "overlaps": overlaps,
                "score": score, "reason": "no overlap-reducing move available",
            })
            return finish(False, "stalled: no move reduces the overlap count", it)

        action, meta = picker(state, candidates)
        if action is None:
            trace.append({
                "iter": it, "event": "picker_declined", "overlaps": overlaps,
                "score": score, "picker": meta,
            })
            return finish(False, "picker declined to move", it)

        # Identify which shortlisted candidate the picker landed on (by action).
        picked_id = meta.get("picked_id")
        matched = next(
            (c for c in candidates if c["action"] == action), None
        )
        if matched is not None:
            picked_id = picked_id or matched["id"]
            predicted_after = matched["overlaps_after"]
        else:
            predicted_after = None

        current = apply_action(current, action)
        after = layout_status(current)
        trace.append({
            "iter": it,
            "event": "apply",
            "overlaps": overlaps,
            "overlaps_after": len(after["overlaps"]),
            "score": score,
            "score_after": after["geometry_score"],
            "action": action,
            "picked_id": picked_id,
            "predicted_overlaps_after": predicted_after,
            "picker": meta,
        })

    return finish(False, f"max_iters ({max_iters}) reached", max_iters)
