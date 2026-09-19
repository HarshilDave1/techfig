#!/usr/bin/env python
"""Demo: Jev picks the move to de-collide two overlapping boxes.

Runs one live Jev call using JEV_API_KEY (env or ~/.hermes/.env).  This is
the action-picker framing: state = spec + geometry, action = a candidate
move from enumerate_actions, Jev chooses, the engine applies.

Usage:
    .venv/bin/python examples/j1_jev_loop_demo.py
"""

from __future__ import annotations

import json
import sys

from techfig.engines.geo_linter import score_geometry
from techfig.engines.jev_client import load_api_key, post_review, normalize_answers
from techfig.engines.layout_actions import apply_action, enumerate_actions, list_shapes


def build_demo_spec() -> dict:
    """Two 100x100 boxes, 40px overlap on x."""
    return {
        "elements": [
            {"id": "a", "type": "box", "x": 0, "y": 0, "w": 100, "h": 100},
            {"id": "b", "type": "box", "x": 60, "y": 0, "w": 100, "h": 100},
        ]
    }


def action_desc(a: dict) -> str:
    dx, dy = a["dx"], a["dy"]
    return f"Move shape {a['shape_id']} {'right' if dx > 0 else 'left' if dx < 0 else ''} {'down' if dy > 0 else 'up' if dy < 0 else ''} by {abs(dx or dy):.0f}px"


def main() -> int:
    if not load_api_key():
        print("No JEV_API_KEY found in env or ~/.hermes/.env — cannot run demo.")
        return 2

    spec = build_demo_spec()
    print("== State ==")
    print("shapes:", [(s["id"], s["bbox"]) for s in list_shapes(spec)])
    print("score_geometry:", score_geometry(spec))

    actions = enumerate_actions(spec)
    if not actions:
        print("No candidate moves. Nothing to demo.")
        return 1
    print(f"\n== {len(actions)} candidate actions ==")
    for a in actions[:10]:
        print(" ", a["shape_id"], a["dx"], a["dy"], "-", action_desc(a))

    # Jev picks the action: one choice question + one stop-gate noul.
    criteria = {}
    for a in actions[:10]:  # stay well under the token ceiling
        criteria[a["shape_id"] + f"_{a['dx']:+g}_{a['dy']:+g}"] = action_desc(a)
    criteria["none"] = "No move needed; layout is acceptable as-is"

    state = {
        "task": "Pick the single best next move to remove shape overlap in this TechFig spec.",
        "repositoryContext": (
            "TechFig spec; two 100x100 boxes overlap by 40px on x. "
            "score_geometry returns 1.0 only when no shapes overlap. "
            "Canvas is unbounded for this demo."
        ),
        "geometry": {"score_geometry": score_geometry(spec)},
    }
    questions = {
        "next_action": {
            "type": "choice",
            "instructions": (
                "Which move best removes the overlap with minimal change? "
                "Prefer the smallest displacement that clears the collision."
            ),
            "criteria": criteria,
        },
        "layout_acceptable": {
            "type": "noul",
            "instructions": "The current layout is already acceptable and needs no move.",
        },
    }

    print("\n== Jev ==")
    resp = post_review(state, questions)
    answers = normalize_answers(resp.get("answers", {}))
    pick = answers["next_action"]["choice"]
    print("model:", resp.get("model"))
    print("next_action ->", pick)
    print("layout_acceptable noul:", answers["layout_acceptable"]["noul"])

    if pick == "none":
        print("Jev says no move needed.")
        return 0

    chosen = None
    for a in actions[:10]:
        key = a["shape_id"] + f"_{a['dx']:+g}_{a['dy']:+g}"
        if key == pick:
            chosen = a
            break
    if chosen is None:
        print("Jev picked an action not in the candidate set — skipping apply.")
        return 1

    new_spec = apply_action(spec, chosen)
    print("\n== Applied ==")
    print("action:", chosen["shape_id"], f"dx={chosen['dx']:g}", f"dy={chosen['dy']:g}")
    print("score_geometry before:", score_geometry(spec))
    print("score_geometry after :", score_geometry(new_spec))
    print("shapes after:", [(s["id"], s["bbox"]) for s in list_shapes(new_spec)])
    print("input unmutated:", spec["elements"][0]["x"] == 0)
    print("\nDemo done. Run again to watch Jev iterate the loop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
