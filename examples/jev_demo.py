#!/usr/bin/env python
"""Jev de-collision demo for TechFig (the J2 loop).

Runs the full loop on a spec with deliberate overlaps::

    state_vector -> enumerate_actions (coarse-first) -> jav pick -> apply -> score_geometry

...until the layout is clean or the loop stops for a reason it names.

Usage::

    python examples/jev_demo.py                      # examples/overlap_demo_spec.json
    python examples/jev_demo.py --no-jev             # deterministic greedy picker
    python examples/jev_demo.py --spec my.json --out examples/out
    python examples/jev_demo.py --review             # + Jev review gate on the result

Exit code is 0 only when the resolved layout is certified clean.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make `techfig` importable when run as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from techfig.engines.layout_actions import DEFAULT_MOVE_STEPS, state_vector  # noqa: E402
from techfig.engines.layout_loop import (  # noqa: E402
    greedy_pick,
    make_jev_picker,
    run_dejumble_loop,
)


def _print_state(label: str, state: Dict[str, Any]) -> None:
    print(f"  {label}: shapes={len(state['shapes'])} "
          f"overlaps={len(state['overlaps'])} "
          f"geometry_score={state['geometry_score']:.4f}")
    for pair in state["overlaps"]:
        print(f"      overlap: {pair[0]} <-> {pair[1]}")


def _build_picker(args) -> Tuple[Any, str]:
    """Return (picker, label).  Wraps Jev with a logged greedy fallback."""
    if args.no_jev:
        return greedy_pick, "greedy"

    jev_picker = make_jev_picker(model=args.model, timeout_s=args.timeout)

    def picker(state: Dict[str, Any], candidates: List[Dict[str, Any]]):
        try:
            action, meta = jev_picker(state, candidates)
        except Exception as exc:  # transport / HTTP / missing key
            if args.strict_jev:
                raise
            print(f"  [warn] Jev call failed ({exc}); falling back to greedy")
            action, meta = greedy_pick(state, candidates)
            meta = {**meta, "fallback": "jev_error", "error": str(exc)}
            return action, meta
        if action is None and not args.strict_jev:
            greedy_action, gmeta = greedy_pick(state, candidates)
            meta = {**meta, "fallback": "jev_declined"}
            return greedy_action, {**gmeta, **meta}
        return action, meta

    return picker, "jev (+greedy fallback)" if not args.strict_jev else "jev (strict)"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Jev de-collision loop demo")
    ap.add_argument("--spec", default=str(
        Path(__file__).resolve().parent / "overlap_demo_spec.json"))
    ap.add_argument("--out", default=str(
        Path(__file__).resolve().parent / "out"))
    ap.add_argument("--model", default=None, help="Jev model (default jev-latest)")
    ap.add_argument("--max-iters", type=int, default=12)
    ap.add_argument("--top-k", type=int, default=6,
                    help="shortlist size handed to the picker")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--no-jev", action="store_true",
                    help="use the deterministic greedy picker only")
    ap.add_argument("--strict-jev", action="store_true",
                    help="do not fall back to greedy if Jev fails/declines")
    ap.add_argument("--review", action="store_true",
                    help="run the Jev review gate on the resolved spec")
    args = ap.parse_args(argv)

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text())

    print("=" * 72)
    print("TechFig Jev de-collision demo")
    print("=" * 72)
    print(f"spec: {spec_path}")
    print(f"coarse-first move steps: {DEFAULT_MOVE_STEPS}")

    print("\n[1] initial state (state_vector)")
    initial_state = state_vector(spec)
    _print_state("before", initial_state)

    picker, picker_label = _build_picker(args)
    print(f"\n[2] running loop  (picker: {picker_label})")

    result = run_dejumble_loop(
        spec, picker=picker, top_k=args.top_k, max_iters=args.max_iters
    )

    for step in result["trace"]:
        event = step["event"]
        if event == "apply":
            meta = step["picker"]
            src = meta.get("picker", "?")
            fallback = meta.get("fallback")
            tag = f"{src}" + (f"/{fallback}" if fallback else "")
            extra = ""
            if src == "jev":
                conf = meta.get("confidence")
                extra = f" conf={conf}" if conf is not None else ""
            print(f"    iter {step['iter']}: {tag:16s} {step['picked_id'] or '?'} "
                  f"overlaps {step['overlaps']} -> {step['overlaps_after']} "
                  f"score {step['score']:.3f} -> {step['score_after']:.3f}{extra}")
            print(f"        {meta.get('picked_description', '')}")
        elif event == "clean":
            print(f"    iter {step['iter']}: CLEAN "
                  f"(score {step['score']:.4f})")
        else:
            print(f"    iter {step['iter']}: {event} -- "
                  f"{step.get('reason', step.get('unsupported', ''))}")

    print("\n[3] final state")
    _print_state("after", state_vector(result["final_spec"]))
    print(f"    clean={result['clean']}  iterations={result['iterations']}  "
          f"stopped_reason={result['stopped_reason']}")

    review = None
    if args.review:
        from techfig.engines import jev_client

        print("\n[4] Jev review gate on the resolved spec")
        questions = jev_client.build_questions(route=True)
        resp = jev_client.post_review(state_vector(result["final_spec"]), questions)
        answers = jev_client.normalize_answers(resp.get("answers", {}))
        gate = jev_client.evaluate_gate(answers)
        review = {"model": resp.get("model"), "answers": answers, "gate": gate}
        print(f"    decision={gate['decision']} reasons={gate['reasons']}")

    # --- evidence on disk ---
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = spec_path.stem
    resolved_path = out_dir / f"{stem}_resolved.json"
    report_path = out_dir / f"{stem}_report.json"
    resolved_path.write_text(json.dumps(result["final_spec"], indent=2))
    report = {
        "spec": str(spec_path),
        "clean": result["clean"],
        "iterations": result["iterations"],
        "stopped_reason": result["stopped_reason"],
        "picker": picker_label,
        "move_steps": list(DEFAULT_MOVE_STEPS),
        "initial_status": result["initial_status"],
        "final_status": result["final_status"],
        "trace": result["trace"],
        "review": review,
    }
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nwrote: {resolved_path}")
    print(f"wrote: {report_path}")
    print(f"\nRESULT: {'CLEAN' if result['clean'] else 'NOT CLEAN'} "
          f"({result['stopped_reason']})")
    return 0 if result["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
