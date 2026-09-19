#!/usr/bin/env python
"""Jev A/B benchmark: does the quality-gate/action-picker earn its tokens?

Arm A (baseline): greedy picker only — geo_linter + pytest discipline, no Jev.
Arm B (jev): full loop with Jev picking (optional --review gate).

Green-trap specs deliberately include unsupported types ('boxx', 'hexagon') so a
naive "zero overlaps => clean" baseline can look green while lying.

Usage (from repo root)::

    .venv/bin/python examples/run_jev_benchmark.py
    .venv/bin/python examples/run_jev_benchmark.py --repeats 3 --review
    .venv/bin/python examples/run_jev_benchmark.py --arms greedy,jev --max-iters 12

Writes JSON + markdown under examples/out/jev_benchmark/.
Does not commit.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jev_benchmark_specs import SPECS, materialize  # noqa: E402

from techfig.engines.layout_actions import (  # noqa: E402
    DEFAULT_MOVE_STEPS,
    UnsupportedShapeTypeWarning,
    layout_status,
)
from techfig.engines.layout_loop import (  # noqa: E402
    greedy_pick,
    make_jev_picker,
    run_dejumble_loop,
)

# OpenRouter / TypeSafe list price (2026-09): $0.042 / M input, $0 output.
JEV_USD_PER_M_INPUT = 0.042
JEV_USD_PER_M_OUTPUT = 0.0


def _sum_usage(trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    calls = 0
    tin = 0
    tout = 0
    per_call: List[Dict[str, Any]] = []
    for step in trace:
        if step.get("event") != "apply":
            continue
        meta = step.get("picker") or {}
        usage = meta.get("usage") or {}
        if meta.get("picker") != "jev" and "usage" not in meta:
            continue
        if not usage and meta.get("picker") != "jev":
            continue
        if usage or meta.get("picker") == "jev":
            calls += 1
            ii = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            oo = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
            tin += ii
            tout += oo
            per_call.append({
                "iter": step.get("iter"),
                "input_tokens": ii,
                "output_tokens": oo,
                "picked_id": step.get("picked_id"),
                "confidence": meta.get("confidence"),
                "fallback": meta.get("fallback"),
            })
    cost = (tin / 1e6) * JEV_USD_PER_M_INPUT + (tout / 1e6) * JEV_USD_PER_M_OUTPUT
    return {
        "jev_calls": calls,
        "input_tokens": tin,
        "output_tokens": tout,
        "total_tokens": tin + tout,
        "usd_estimate": round(cost, 8),
        "per_call": per_call,
        "pricing": {
            "usd_per_m_input": JEV_USD_PER_M_INPUT,
            "usd_per_m_output": JEV_USD_PER_M_OUTPUT,
            "source": "openrouter/typesafe jev-1.13 list (2026-09)",
        },
    }


def _moves_metrics(trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    applied = [s for s in trace if s.get("event") == "apply"]
    total_px = 0.0
    for s in applied:
        act = s.get("action") or {}
        total_px += abs(float(act.get("dx") or 0)) + abs(float(act.get("dy") or 0))
    return {
        "moves_applied": len(applied),
        "total_px_moved": total_px,
    }


def _correctness(
    result: Dict[str, Any],
    expected_clean: bool,
    expected_unsupported: bool,
) -> Dict[str, Any]:
    """Honest verdict vs ground-truth expectations for the scenario."""
    final = result["final_status"]
    clean = bool(result["clean"])
    unsupported = list(final.get("unsupported") or [])
    has_unsup = len(unsupported) > 0
    overlaps = len(final.get("overlaps") or [])

    reasons: List[str] = []
    ok = True

    if clean != expected_clean:
        ok = False
        reasons.append(
            f"clean={clean} expected={expected_clean} "
            f"(stopped_reason={result.get('stopped_reason')!r})"
        )
    if expected_unsupported and not has_unsup and expected_clean is False:
        # traps must surface unsupported OR empty action space stop reason
        reason = (result.get("stopped_reason") or "").lower()
        if "unsupported" not in reason and "empty action space" not in reason:
            ok = False
            reasons.append(
                "expected unsupported/empty-space handling; "
                f"got stopped_reason={result.get('stopped_reason')!r}"
            )
    if expected_clean and overlaps != 0:
        ok = False
        reasons.append(f"expected zero final overlaps, got {overlaps}")
    if expected_clean and has_unsup:
        ok = False
        reasons.append("clean expected but unsupported types remain")
    # Lying-green detection: clean claimed while unsupported present
    lying_green = clean and has_unsup
    if lying_green:
        ok = False
        reasons.append("LYING GREEN: clean=True with unsupported types present")

    naive_overlap_clean = overlaps == 0 and final.get("shapes", 0) >= 0
    return {
        "ok": ok,
        "lying_green": lying_green,
        "naive_zero_overlap_would_pass": naive_overlap_clean and not has_unsup
        if not expected_unsupported
        else (overlaps == 0),  # trap: naive may pass on zero overlaps
        "reasons": reasons,
        "expected_clean": expected_clean,
        "expected_unsupported": expected_unsupported,
        "got_clean": clean,
        "got_unsupported_count": len(unsupported),
        "got_overlaps": overlaps,
        "stopped_reason": result.get("stopped_reason"),
    }


def _build_picker(arm: str, model: Optional[str], timeout_s: float, strict: bool):
    if arm == "greedy":
        return greedy_pick, "greedy"

    jev_picker = make_jev_picker(model=model, timeout_s=timeout_s)

    def picker(state, candidates):
        try:
            action, meta = jev_picker(state, candidates)
        except Exception as exc:
            if strict:
                raise
            action, meta = greedy_pick(state, candidates)
            meta = {**meta, "fallback": "jev_error", "error": str(exc)}
            return action, meta
        if action is None and not strict:
            g_action, gmeta = greedy_pick(state, candidates)
            meta = {**meta, "fallback": "jev_declined"}
            return g_action, {**gmeta, **meta}
        return action, meta

    label = "jev_strict" if strict else "jev (+greedy fallback)"
    return picker, label


def _maybe_review(spec: Dict[str, Any], do_review: bool) -> Optional[Dict[str, Any]]:
    if not do_review:
        return None
    from techfig.engines import jev_client
    from techfig.engines.layout_actions import state_vector

    questions = jev_client.build_questions(route=True)
    resp = jev_client.post_review(state_vector(spec), questions)
    answers = jev_client.normalize_answers(resp.get("answers", {}))
    gate = jev_client.evaluate_gate(answers)
    usage = resp.get("usage") or {}
    return {
        "model": resp.get("model"),
        "gate": gate,
        "usage": usage,
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
    }


def run_one(
    entry: Dict[str, Any],
    arm: str,
    *,
    model: Optional[str],
    timeout_s: float,
    max_iters: int,
    top_k: int,
    review: bool,
    strict_jev: bool,
    repeat_idx: int,
) -> Dict[str, Any]:
    spec = materialize(entry)
    picker, picker_label = _build_picker(arm, model, timeout_s, strict_jev)

    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UnsupportedShapeTypeWarning)
        result = run_dejumble_loop(
            spec, picker=picker, top_k=top_k, max_iters=max_iters
        )
    wall = time.perf_counter() - t0

    moves = _moves_metrics(result["trace"])
    usage = _sum_usage(result["trace"])
    review_blob = None
    try:
        review_blob = _maybe_review(result["final_spec"], review and arm.startswith("jev"))
    except Exception as exc:
        review_blob = {"error": str(exc)}

    if review_blob and "input_tokens" in review_blob:
        usage["review_input_tokens"] = review_blob["input_tokens"]
        usage["review_output_tokens"] = review_blob["output_tokens"]
        usage["input_tokens"] += review_blob["input_tokens"]
        usage["output_tokens"] += review_blob["output_tokens"]
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
        usage["usd_estimate"] = round(
            (usage["input_tokens"] / 1e6) * JEV_USD_PER_M_INPUT
            + (usage["output_tokens"] / 1e6) * JEV_USD_PER_M_OUTPUT,
            8,
        )

    corr = _correctness(
        result, entry["expected_clean"], entry["expected_unsupported"]
    )
    final = result["final_status"]
    initial = result["initial_status"]

    warn_msgs = [str(w.message)[:200] for w in caught]

    return {
        "spec": entry["name"],
        "family": entry["family"],
        "nastiness": entry["nastiness"],
        "arm": arm,
        "picker_label": picker_label,
        "repeat": repeat_idx,
        "wall_s": round(wall, 4),
        "iterations": result["iterations"],
        "moves_applied": moves["moves_applied"],
        "total_px_moved": moves["total_px_moved"],
        "initial_overlaps": len(initial.get("overlaps") or []),
        "final_overlaps": len(final.get("overlaps") or []),
        "initial_geometry_score": initial.get("geometry_score"),
        "final_geometry_score": final.get("geometry_score"),
        "clean": result["clean"],
        "stopped_reason": result["stopped_reason"],
        "unsupported": final.get("unsupported") or [],
        "unsupported_handling": {
            "present": bool(final.get("unsupported")),
            "count": len(final.get("unsupported") or []),
            "warned": any("unsupported" in m.lower() for m in warn_msgs),
        },
        "usage": usage,
        "review": review_blob,
        "correctness": corr,
        "trace": result["trace"],
        "note": entry.get("note"),
    }


def _aggregate(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per (spec, arm) means over repeats."""
    from collections import defaultdict

    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in runs:
        groups[(r["spec"], r["arm"])].append(r)

    rows = []
    for (spec, arm), rs in sorted(groups.items()):
        def mean(key, default=0.0):
            vals = [float(r.get(key) or 0) for r in rs]
            return statistics.mean(vals) if vals else default

        def mean_nested(*path):
            vals = []
            for r in rs:
                cur: Any = r
                for p in path:
                    cur = (cur or {}).get(p) if isinstance(cur, dict) else None
                if cur is not None:
                    vals.append(float(cur))
            return statistics.mean(vals) if vals else 0.0

        ok_rate = sum(1 for r in rs if r["correctness"]["ok"]) / len(rs)
        lying = sum(1 for r in rs if r["correctness"]["lying_green"])
        clean_rate = sum(1 for r in rs if r["clean"]) / len(rs)
        rows.append({
            "spec": spec,
            "arm": arm,
            "family": rs[0]["family"],
            "n": len(rs),
            "ok_rate": round(ok_rate, 3),
            "lying_green_count": lying,
            "clean_rate": round(clean_rate, 3),
            "mean_iterations": round(mean("iterations"), 3),
            "mean_moves": round(mean("moves_applied"), 3),
            "mean_px_moved": round(mean("total_px_moved"), 2),
            "mean_final_score": round(mean("final_geometry_score"), 4),
            "mean_final_overlaps": round(mean("final_overlaps"), 3),
            "mean_wall_s": round(mean("wall_s"), 4),
            "mean_jev_calls": round(mean_nested("usage", "jev_calls"), 3),
            "mean_input_tokens": round(mean_nested("usage", "input_tokens"), 1),
            "mean_output_tokens": round(mean_nested("usage", "output_tokens"), 1),
            "mean_usd": round(mean_nested("usage", "usd_estimate"), 8),
            "stopped_reasons": sorted({r["stopped_reason"] for r in rs}),
        })
    return {"by_spec_arm": rows}


def _verdict(agg: Dict[str, Any], runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = agg["by_spec_arm"]
    pure = [r for r in rows if r["family"] == "pure_overlap"]
    traps = [r for r in rows if r["family"] == "green_trap"]

    def pair_map(family_rows):
        m = {}
        for r in family_rows:
            m.setdefault(r["spec"], {})[r["arm"]] = r
        return m

    pure_m = pair_map(pure)
    trap_m = pair_map(traps)

    # Efficiency on pure: lower iters/px/tokens wins; equal clean ok_rate assumed
    jev_efficiency_wins = []
    greedy_enough = []
    for spec, arms in pure_m.items():
        g, j = arms.get("greedy"), arms.get("jev")
        if not g or not j:
            continue
        # both should be correct on pure
        if j["ok_rate"] >= 0.99 and g["ok_rate"] >= 0.99:
            # Jev "wins" efficiency only if fewer moves/px with similar clean
            if j["mean_moves"] + 0.25 < g["mean_moves"] or j["mean_px_moved"] + 5 < g["mean_px_moved"]:
                jev_efficiency_wins.append(spec)
            else:
                greedy_enough.append(spec)
        elif j["ok_rate"] > g["ok_rate"]:
            jev_efficiency_wins.append(spec)
        else:
            greedy_enough.append(spec)

    # Correctness on traps: both arms use same loop — should both refuse clean.
    # The "lying baseline" is the naive zero-overlap check, measured separately.
    trap_correct = []
    trap_fail = []
    for spec, arms in trap_m.items():
        for arm, r in arms.items():
            if r["ok_rate"] >= 0.99 and r["lying_green_count"] == 0:
                trap_correct.append(f"{spec}/{arm}")
            else:
                trap_fail.append(f"{spec}/{arm}")

    # Naive lying: on green traps, would zero-overlap alone claim success?
    naive_lie_specs = []
    for r in runs:
        if r["family"] != "green_trap":
            continue
        if r["arm"] != "greedy":
            continue
        # zero final overlaps but expected not clean
        if r["final_overlaps"] == 0 and not r["correctness"]["expected_clean"]:
            # if arm correctly set clean=False, loop is honest; naive would lie
            if not r["clean"]:
                naive_lie_specs.append(r["spec"])

    total_jev_tokens = sum(
        (r.get("usage") or {}).get("input_tokens", 0) for r in runs if r["arm"] == "jev"
    )
    total_jev_usd = sum(
        (r.get("usage") or {}).get("usd_estimate", 0.0) for r in runs if r["arm"] == "jev"
    )
    total_jev_wall = sum(r["wall_s"] for r in runs if r["arm"] == "jev")
    total_g_wall = sum(r["wall_s"] for r in runs if r["arm"] == "greedy")

    # Worth-it criteria (honest):
    # 1) On pure overlap, Jev does not beat greedy on moves/px enough to justify
    #    tokens+latency UNLESS it finds better paths.
    # 2) On green traps, the *loop* (not Jev picker) earns honesty; Jev review
    #    gate is optional extra. Picker tokens don't buy trap detection —
    #    layout_status does.
    worth = False
    reasons = []
    if jev_efficiency_wins and not greedy_enough:
        worth = True
        reasons.append(
            f"Jev beat greedy on move-efficiency for all pure specs: {jev_efficiency_wins}"
        )
    elif jev_efficiency_wins:
        reasons.append(
            f"Jev efficiency edge on {jev_efficiency_wins}; greedy enough on {greedy_enough}"
        )
        # marginal: only worth if edge is large — checked below via token cost
        worth = False  # default marginal -> not worth for picker-only
    else:
        reasons.append(
            f"Greedy matched or beat Jev efficiency on pure specs: {greedy_enough or list(pure_m)}"
        )

    if trap_fail:
        reasons.append(f"Trap correctness failures: {trap_fail}")
    else:
        reasons.append(
            "Both arms correctly refuse clean on green-traps "
            "(honesty comes from layout_status unsupported/empty checks, not Jev pick)."
        )

    if naive_lie_specs:
        reasons.append(
            f"Naive zero-overlap baseline WOULD LIE on: {sorted(set(naive_lie_specs))} "
            "— the loop's unsupported gate is what earns correctness here, free of tokens."
        )

    reasons.append(
        f"Jev total input_tokens={total_jev_tokens}, usd≈${total_jev_usd:.6f}, "
        f"wall_jev={total_jev_wall:.2f}s vs wall_greedy={total_g_wall:.2f}s"
    )

    # Final call
    if worth:
        headline = "YES — Jev picker worth tokens (clear efficiency or correctness edge)."
    elif jev_efficiency_wins:
        headline = (
            "MARGINAL — Jev wins some pure specs on path quality, but greedy is enough "
            "for most; trap honesty is free via layout_status."
        )
    else:
        headline = (
            "NO — for de-collision picking, greedy is enough. "
            "Jev tokens buy little over rank_moves[0]; "
            "green-trap honesty is already in the deterministic loop."
        )

    return {
        "headline": headline,
        "worth_it": worth,
        "jev_efficiency_wins": jev_efficiency_wins,
        "greedy_enough": greedy_enough,
        "trap_correct": trap_correct,
        "trap_fail": trap_fail,
        "naive_lie_specs": sorted(set(naive_lie_specs)),
        "totals": {
            "jev_input_tokens": total_jev_tokens,
            "jev_usd_estimate": round(total_jev_usd, 8),
            "jev_wall_s": round(total_jev_wall, 3),
            "greedy_wall_s": round(total_g_wall, 3),
        },
        "reasons": reasons,
    }


def _md_table(agg: Dict[str, Any], verdict: Dict[str, Any], meta: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Jev A/B Benchmark — TechFig de-collision loop")
    lines.append("")
    lines.append(f"- Generated: `{meta['generated_at']}`")
    lines.append(f"- Model: `{meta.get('model')}`")
    lines.append(f"- Repeats: {meta['repeats']} · max_iters={meta['max_iters']} · top_k={meta['top_k']}")
    lines.append(f"- Arms: {', '.join(meta['arms'])}")
    lines.append(f"- Review gate: {meta['review']}")
    lines.append(
        f"- Pricing: ${JEV_USD_PER_M_INPUT}/M input, "
        f"${JEV_USD_PER_M_OUTPUT}/M output (TypeSafe/OpenRouter list)"
    )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{verdict['headline']}**")
    lines.append("")
    for r in verdict["reasons"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## Summary table (means over repeats)")
    lines.append("")
    hdr = (
        "| spec | arm | family | ok | lie | clean | iters | moves | px | "
        "score | ovlp | wall_s | jev_calls | tok_in | tok_out | usd |"
    )
    sep = (
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    lines.append(hdr)
    lines.append(sep)
    for r in agg["by_spec_arm"]:
        lines.append(
            f"| {r['spec']} | {r['arm']} | {r['family']} | {r['ok_rate']:.2f} | "
            f"{r['lying_green_count']} | {r['clean_rate']:.2f} | {r['mean_iterations']:.2f} | "
            f"{r['mean_moves']:.2f} | {r['mean_px_moved']:.1f} | {r['mean_final_score']:.3f} | "
            f"{r['mean_final_overlaps']:.2f} | {r['mean_wall_s']:.3f} | {r['mean_jev_calls']:.2f} | "
            f"{r['mean_input_tokens']:.0f} | {r['mean_output_tokens']:.0f} | {r['mean_usd']:.6f} |"
        )
    lines.append("")
    lines.append("## Design notes")
    lines.append("")
    lines.append(
        "- **Arm A (greedy)**: `greedy_pick` = first ranked improving move from "
        "`rank_moves` (count → score → area → cost). No Jev API."
    )
    lines.append(
        "- **Arm B (jev)**: `make_jev_picker` choice over the same shortlist; "
        "optional review gate via `build_questions` + `evaluate_gate`."
    )
    lines.append(
        "- **Green-trap**: unsupported types (`boxx`, `hexagon`) so zero "
        "supported-shape overlaps can look clean while the layout is not "
        "certifiable. Correct `clean=False` comes from `layout_status`, not the picker."
    )
    lines.append(
        "- **Metrics**: iterations, moves, total px, geometry_score, overlaps, "
        "clean, unsupported handling, wall time, Jev usage (input/output tokens "
        "from response `usage`), correctness vs expected."
    )
    lines.append("")
    lines.append("## Where each arm wins")
    lines.append("")
    lines.append(f"- Jev efficiency edge: {verdict['jev_efficiency_wins'] or '(none)'}")
    lines.append(f"- Greedy enough: {verdict['greedy_enough'] or '(none)'}")
    lines.append(f"- Trap correct: {verdict['trap_correct'] or '(none)'}")
    lines.append(f"- Trap fail: {verdict['trap_fail'] or '(none)'}")
    lines.append(
        f"- Specs where naive zero-overlap would lie: "
        f"{verdict['naive_lie_specs'] or '(none)'}"
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Jev A/B benchmark for TechFig")
    ap.add_argument("--out", default=str(ROOT / "examples" / "out" / "jev_benchmark"))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--max-iters", type=int, default=12)
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--model", default=None)
    ap.add_argument("--arms", default="greedy,jev",
                    help="comma list: greedy,jev")
    ap.add_argument("--review", action="store_true",
                    help="run Jev review gate on jev-arm finals")
    ap.add_argument("--strict-jev", action="store_true")
    ap.add_argument("--specs", default="",
                    help="comma subset of spec names (default: all)")
    args = ap.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ("greedy", "jev"):
            print(f"unknown arm: {a}", file=sys.stderr)
            return 2

    entries = SPECS
    if args.specs:
        want = {s.strip() for s in args.specs.split(",") if s.strip()}
        entries = [e for e in SPECS if e["name"] in want]
        missing = want - {e["name"] for e in entries}
        if missing:
            print(f"unknown specs: {missing}", file=sys.stderr)
            return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Materialize specs to disk for audit
    specs_dir = out_dir / "specs"
    specs_dir.mkdir(exist_ok=True)
    for e in entries:
        (specs_dir / f"{e['name']}.json").write_text(
            json.dumps(materialize(e), indent=2)
        )

    runs: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    total = len(entries) * len(arms) * args.repeats
    n = 0
    print("=" * 72)
    print("Jev A/B benchmark")
    print(f"specs={len(entries)} arms={arms} repeats={args.repeats} total_runs={total}")
    print(f"move_steps={DEFAULT_MOVE_STEPS}")
    print("=" * 72)

    for e in entries:
        for arm in arms:
            for rep in range(args.repeats):
                n += 1
                tag = f"[{n}/{total}] {e['name']} / {arm} / r{rep}"
                print(tag, flush=True)
                try:
                    row = run_one(
                        e, arm,
                        model=args.model,
                        timeout_s=args.timeout,
                        max_iters=args.max_iters,
                        top_k=args.top_k,
                        review=args.review,
                        strict_jev=args.strict_jev,
                        repeat_idx=rep,
                    )
                    runs.append(row)
                    u = row["usage"]
                    print(
                        f"    clean={row['clean']} ok={row['correctness']['ok']} "
                        f"iters={row['iterations']} moves={row['moves_applied']} "
                        f"px={row['total_px_moved']:.0f} "
                        f"score={row['final_geometry_score']:.3f} "
                        f"wall={row['wall_s']:.2f}s "
                        f"tok_in={u.get('input_tokens', 0)} "
                        f"usd={u.get('usd_estimate', 0):.6f} "
                        f"reason={row['stopped_reason']}",
                        flush=True,
                    )
                except Exception as exc:
                    tb = traceback.format_exc(limit=5)
                    print(f"    ERROR: {exc}", flush=True)
                    errors.append({
                        "spec": e["name"], "arm": arm, "repeat": rep,
                        "error": str(exc), "traceback": tb,
                    })

    agg = _aggregate(runs)
    verdict = _verdict(agg, runs)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model or "jev-latest",
        "repeats": args.repeats,
        "max_iters": args.max_iters,
        "top_k": args.top_k,
        "arms": arms,
        "review": args.review,
        "strict_jev": args.strict_jev,
        "n_runs": len(runs),
        "n_errors": len(errors),
        "pricing_usd_per_m_input": JEV_USD_PER_M_INPUT,
        "pricing_usd_per_m_output": JEV_USD_PER_M_OUTPUT,
    }

    payload = {
        "meta": meta,
        "aggregate": agg,
        "verdict": verdict,
        "runs": runs,
        "errors": errors,
    }
    json_path = out_dir / "results.json"
    md_path = out_dir / "SUMMARY.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str))
    md_path.write_text(_md_table(agg, verdict, meta))

    # slim CSV-ish lines for quick glance
    slim = [{
        k: r[k] for k in (
            "spec", "arm", "repeat", "clean", "iterations", "moves_applied",
            "total_px_moved", "final_geometry_score", "final_overlaps",
            "wall_s", "stopped_reason",
        )
    } | {
        "ok": r["correctness"]["ok"],
        "lying_green": r["correctness"]["lying_green"],
        "input_tokens": r["usage"].get("input_tokens", 0),
        "output_tokens": r["usage"].get("output_tokens", 0),
        "usd": r["usage"].get("usd_estimate", 0),
        "jev_calls": r["usage"].get("jev_calls", 0),
    } for r in runs]
    (out_dir / "runs_slim.json").write_text(json.dumps(slim, indent=2))

    print("=" * 72)
    print(verdict["headline"])
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"errors={len(errors)}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
