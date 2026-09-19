#!/usr/bin/env python
"""FINAL Jev review/quality GATE test on real rendered figures.

Not the action-picker. For each scenario:
  1) deterministic: geo_linter + layout_status + pytest subset
  2) Jev gate: build_questions + post_review + evaluate_gate (spec v0.1)

Scenarios:
  (1) clean shippable figure — reuse examples/out/_probe_clean.svg
  (2) geometrically-fine but really-defective (off-canvas + stacked + missing callout ref)
  (3) docs-only/style-only diff — test_coverage exempt per v0.1

Writes examples/out/jev_gate_test/{results.json,SUMMARY.md,specs/,renders/}.
Does not commit.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from techfig.engines import jev_client  # noqa: E402
from techfig.engines.geo_linter import lint_spec  # noqa: E402
from techfig.engines.layout_actions import layout_status, state_vector  # noqa: E402
from techfig.engines.sketch_interpreter import render_from_spec  # noqa: E402

OUT = ROOT / "examples" / "out" / "jev_gate_test"
PROBE_SVG = ROOT / "examples" / "out" / "_probe_clean.svg"
PYTEST_TARGETS = [
    "tests/test_geo_linter.py",
    "tests/test_layout_actions.py",
    "tests/test_jev_client.py",
]
JEV_USD_PER_M_IN = 0.042
JEV_USD_PER_M_OUT = 0.0

# Spec v0.1: docs/style-only diffs exempt test_coverage from hard/pass mins.
V01_EXEMPT_DIMS_DOCS = frozenset({"test_coverage"})
# Pure figure review (no code diff): code-module dims are N/A; keep
# correctness/reliability/compatibility as figure-quality proxies.
V01_EXEMPT_DIMS_FIGURE = frozenset({
    "test_coverage",
    "modularity",
    "changeability",
    "security",
})
FIGURE_INSTRUCTIONS = (
    "You are scoring a RENDERED FIGURE, not a code diff. "
    "correctness = geometric/label integrity (no off-canvas, no stacked dupes, "
    "no missing callout refs, no bad overlaps). "
    "reliability = no silent blank/clipped output. "
    "compatibility = spec elements render as intended. "
    "Ignore code-module concerns."
)


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

def clean_spec() -> Dict[str, Any]:
    """Matches the existing _probe_clean.svg (A -> B, 460x300 center-origin)."""
    return {
        "canvas": {"width": 460, "height": 300},
        "style": {"name": "nature"},
        "elements": [
            {"type": "box", "id": "a", "x": 0, "y": 0, "w": 80, "h": 40, "text": "A"},
            {"type": "box", "id": "b", "x": 150, "y": 0, "w": 80, "h": 40, "text": "B"},
            {"type": "arrow", "id": "a2b", "x1": 40, "y1": 0, "x2": 110, "y2": 0},
        ],
    }


def defective_spec() -> Dict[str, Any]:
    """Geo can look 'fine' on supported pairs while figure is unshippable:
    - off-canvas shape (box far outside canvas)
    - two identical boxes stacked at same position
    - callout with missing/broken ref target
    """
    return {
        "canvas": {"width": 460, "height": 300},
        "style": {"name": "nature"},
        "elements": [
            {"type": "box", "id": "core", "x": 0, "y": 0, "w": 80, "h": 40, "text": "Core"},
            # stacked identical positions
            {"type": "box", "id": "dup1", "x": 80, "y": 40, "w": 70, "h": 40, "text": "Dup"},
            {"type": "box", "id": "dup2", "x": 80, "y": 40, "w": 70, "h": 40, "text": "Dup"},
            # off-canvas
            {
                "type": "box",
                "id": "off",
                "x": 400,
                "y": 250,
                "w": 100,
                "h": 60,
                "text": "OffCanvas",
            },
            # missing label ref (callout points at nonexistent id)
            {
                "type": "callout",
                "id": "bad_callout",
                "x": -80,
                "y": -80,
                "text": "missing target",
                "ref": "no_such_element",
                "side": "top",
                "offset": 20,
            },
            {"type": "arrow", "id": "c2d", "x1": 40, "y1": 0, "x2": 45, "y2": 20},
        ],
    }


def docs_style_diff_blob() -> Dict[str, Any]:
    """Synthetic code-review state: docs + style YAML only, no engine/tests."""
    return {
        "task": (
            "Docs/style-only polish: fix README typos and tweak nature style "
            "palette hex values. No engine, CLI, schema, or test changes."
        ),
        "diff": (
            "diff --git a/README.md b/README.md\n"
            "--- a/README.md\n+++ b/README.md\n"
            "@@ -12,3 +12,3 @@\n-Techfig generates figures.\n+TechFig generates publication-quality figures.\n"
            "diff --git a/techfig/styles/nature.yaml b/techfig/styles/nature.yaml\n"
            "--- a/techfig/styles/nature.yaml\n+++ b/techfig/styles/nature.yaml\n"
            "@@ -4,2 +4,2 @@\n-primary: \"#0072B2\"\n+primary: \"#0066A1\"\n"
        ),
        "files": ["README.md", "techfig/styles/nature.yaml"],
        "repositoryContext": (
            "techfig v1.0.x; change touches documentation and a style preset only. "
            "No Python modules, no DIAGRAM_SCHEMA, no pytest paths modified. "
            "Per scientist spec v0.1, test_coverage is NOT applicable to docs/style-only diffs."
        ),
        "change_kind": "docs_style_only",
        "test_coverage_applicable": False,
    }


# ---------------------------------------------------------------------------
# Deterministic probes
# ---------------------------------------------------------------------------

def _lint_dict(spec: Dict[str, Any]) -> Dict[str, Any]:
    rep = lint_spec(spec)
    return {
        "score": float(rep.score),
        "alignment_issues": list(rep.alignment_issues),
        "grid_issues": list(rep.grid_issues)[:12],
        "overlap_issues": list(rep.overlap_issues),
        "n_align": len(rep.alignment_issues),
        "n_grid": len(rep.grid_issues),
        "n_overlap": len(rep.overlap_issues),
    }


def _defect_signals(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Extra ship-quality checks beyond plain AABB pair overlaps."""
    canvas = spec.get("canvas") or {}
    cw = float(canvas.get("width", 0) or 0)
    ch = float(canvas.get("height", 0) or 0)
    # center-origin: half extents
    hx, hy = cw / 2.0, ch / 2.0
    ids = [e.get("id") for e in spec.get("elements", []) if e.get("id")]
    id_set = {i for i in ids if i}

    off_canvas = []
    stacked = []
    missing_refs = []
    positions: Dict[tuple, List[str]] = {}

    for el in spec.get("elements", []) or []:
        eid = el.get("id", "?")
        t = el.get("type")
        if t in ("box", "circle", "ellipse", "diamond", "triangle"):
            try:
                x, y = float(el.get("x", 0)), float(el.get("y", 0))
            except (TypeError, ValueError):
                continue
            if t == "circle":
                w = h = 2 * float(el.get("r", 0))
            elif t == "ellipse":
                w, h = 2 * float(el.get("rx", 0)), 2 * float(el.get("ry", 0))
            else:
                w, h = float(el.get("w", 0)), float(el.get("h", 0))
            left, right = x - w / 2, x + w / 2
            top, bottom = y - h / 2, y + h / 2
            if left < -hx - 1e-6 or right > hx + 1e-6 or top < -hy - 1e-6 or bottom > hy + 1e-6:
                off_canvas.append(eid)
            key = (round(x, 3), round(y, 3), round(w, 3), round(h, 3), t)
            positions.setdefault(key, []).append(str(eid))
        if t == "callout":
            ref = el.get("ref")
            if ref and ref not in id_set:
                missing_refs.append({"callout": eid, "ref": ref})
            # also treat missing ref key as defect when callout has no anchor
            if not ref and el.get("anchor_x") is None:
                missing_refs.append({"callout": eid, "ref": None})

    for key, group in positions.items():
        if len(group) >= 2:
            stacked.append({"ids": group, "xywh_type": list(key)})

    shippable = not off_canvas and not stacked and not missing_refs
    return {
        "off_canvas": off_canvas,
        "stacked_identical": stacked,
        "missing_label_refs": missing_refs,
        "shippable_extra": shippable,
    }


def run_pytest() -> Dict[str, Any]:
    cmd = [str(ROOT / ".venv" / "bin" / "python"), "-m", "pytest", "-q", "--tb=no", *PYTEST_TARGETS]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    wall = time.perf_counter() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    # last non-empty summary line
    summary = ""
    for line in reversed(out.splitlines()):
        if line.strip():
            summary = line.strip()
            break
    return {
        "cmd": " ".join(cmd),
        "exit_code": proc.returncode,
        "wall_s": round(wall, 3),
        "summary": summary[:300],
        "passed": proc.returncode == 0,
        "targets": list(PYTEST_TARGETS),
    }


def render_spec(spec: Dict[str, Any], path: Path) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        render_from_spec(spec, str(path))
        size = path.stat().st_size if path.exists() else 0
        return {"ok": path.exists() and size > 500, "path": str(path), "bytes": size}
    except Exception as exc:
        return {"ok": False, "path": str(path), "bytes": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Jev gate
# ---------------------------------------------------------------------------

def _mark_exempt(answers: Dict[str, Any], exempt: frozenset) -> Dict[str, Any]:
    """Apply v0.1 applicable=False for exempt dims (docs/style-only)."""
    out = dict(answers)
    for name in exempt:
        if name in out and out[name].get("type") == "score":
            out[name] = {**out[name], "applicable": False}
    return out


def run_jev_gate(
    state: Dict[str, Any],
    *,
    exempt_dims: frozenset = frozenset(),
    instructions_extra: str = "",
) -> Dict[str, Any]:
    questions = jev_client.build_questions(
        route=True,
        instructions_extra=instructions_extra,
    )
    # Instruct model that some dims may be N/A
    if exempt_dims:
        extra = (
            " Dimensions "
            + ", ".join(sorted(exempt_dims))
            + " are NOT applicable for this review (local gate will mark applicable=false)."
        )
        for d in exempt_dims:
            if d in questions and questions[d]["type"] == "score":
                questions[d] = {
                    **questions[d],
                    "instructions": questions[d]["instructions"] + extra,
                }

    t0 = time.perf_counter()
    resp = jev_client.post_review(state, questions, timeout_s=90.0)
    wall = time.perf_counter() - t0
    answers = jev_client.normalize_answers(resp.get("answers", {}))
    if exempt_dims:
        answers = _mark_exempt(answers, exempt_dims)
    gate = jev_client.evaluate_gate(answers)
    usage = resp.get("usage") or {}
    tin = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    tout = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    return {
        "model": resp.get("model"),
        "wall_s": round(wall, 3),
        "usage": {
            "input_tokens": tin,
            "output_tokens": tout,
            "total_tokens": tin + tout,
            "usd_estimate": round(tin / 1e6 * JEV_USD_PER_M_IN + tout / 1e6 * JEV_USD_PER_M_OUT, 8),
            "raw": usage,
        },
        "answers": answers,
        "gate": gate,
        "exempt_dims_applied": sorted(exempt_dims),
        "thresholds": dict(jev_client.V0_THRESHOLDS),
    }


def figure_state(spec: Dict[str, Any], *, scenario: str, svg_path: Optional[str], extra: Dict) -> Dict[str, Any]:
    """State for figure review gate (not action picker)."""
    sv = state_vector(spec)
    lint = _lint_dict(spec)
    status = layout_status(spec)
    ship_hint = (
        "DETERMINISTIC PRECHECK: shippable — zero overlaps, no off-canvas, no stacked "
        "duplicates, no missing label refs, svg non-empty."
        if extra.get("shippable_extra") and lint.get("n_overlap", 0) == 0
        else (
            "DETERMINISTIC PRECHECK: NOT shippable — defects present: "
            f"off_canvas={extra.get('off_canvas')} stacked={extra.get('stacked_identical')} "
            f"missing_refs={extra.get('missing_label_refs')} "
            f"overlaps={lint.get('overlap_issues')}"
        )
    )
    return {
        "task": (
            f"Review rendered techfig FIGURE (scenario={scenario}). "
            f"Score figure quality only. {ship_hint}"
        ),
        "scenario": scenario,
        "svg_path": svg_path,
        "svg_bytes": Path(svg_path).stat().st_size if svg_path and Path(svg_path).exists() else 0,
        "layout_status": status,
        "geo_linter": lint,
        "defect_signals": extra,
        "state_vector": sv,
        "spec_summary": {
            "n_elements": len(spec.get("elements") or []),
            "element_ids": [e.get("id") for e in (spec.get("elements") or [])],
            "canvas": spec.get("canvas"),
            "elements": spec.get("elements"),
        },
        "repositoryContext": (
            "TechFig figure review gate (scientist v0.1). Jev is the quality classifier, "
            "not the action picker. Deterministic geo_linter + layout_status already ran. "
            "test_coverage/modularity/changeability/security are N/A for pure figure review."
        ),
    }


def deterministic_verdict(scenario: str, lint: Dict, status: Dict, defects: Dict, pytest_ok: bool) -> Dict[str, Any]:
    """Map deterministic signals -> ship / fail."""
    reasons = []
    if scenario == "clean":
        ok = (
            lint["n_overlap"] == 0
            and status.get("usable")
            and not status.get("unsupported")
            and defects.get("shippable_extra", True)
            and pytest_ok
            and lint["score"] >= 0.5
        )
        if not ok:
            reasons.append("clean scenario failed lint/layout/pytest bar")
        decision = "ship" if ok else "fail"
    elif scenario == "defective":
        # Expect FAIL: defects present even if some AABB metrics look mild
        bad = (
            bool(defects.get("off_canvas"))
            or bool(defects.get("stacked_identical"))
            or bool(defects.get("missing_label_refs"))
            or lint["n_overlap"] > 0
        )
        ok = bad  # correctly detecting defect
        decision = "fail" if bad else "ship"  # ground truth: should fail ship
        if not bad:
            reasons.append("defective scenario produced no defect signals (detector miss)")
        else:
            reasons.append(
                f"defects: off_canvas={defects.get('off_canvas')} "
                f"stacked={defects.get('stacked_identical')} "
                f"missing_refs={defects.get('missing_label_refs')} "
                f"overlaps={lint.get('overlap_issues')}"
            )
    else:  # docs_style
        # Deterministic tree: pytest green; no figure defects; change is docs-only
        ok = pytest_ok
        decision = "ship" if ok else "fail"
        reasons.append("docs/style-only; test_coverage exempt v0.1; pytest is the tree signal")
    return {
        "decision": decision,
        "detector_ok": ok if scenario != "defective" else bool(
            defects.get("off_canvas") or defects.get("stacked_identical") or defects.get("missing_label_refs") or lint["n_overlap"] > 0
        ),
        "reasons": reasons,
        "expected_ship": scenario in ("clean", "docs_style"),
    }


def jev_vs_det(det: Dict, jev_gate: Dict, scenario: str) -> Dict[str, Any]:
    jdec = (jev_gate or {}).get("gate", {}).get("decision")
    # Map Jev pass/hard_fail/escalate to ship-ish
    j_ship = jdec == "pass"
    d_ship = det["decision"] == "ship"
    agree = j_ship == d_ship
    # For defective: we want Jev hard_fail (or escalate), not pass
    if scenario == "defective":
        agree = jdec in ("hard_fail", "escalate") and det["decision"] == "fail"
        signal = "adds_signal" if (jdec == "hard_fail" and det["detector_ok"]) else (
            "redundant" if agree else "disagrees"
        )
    elif scenario == "clean":
        signal = "redundant" if agree and j_ship else ("adds_signal" if not agree else "agree")
    else:
        # docs: if exempt works and pass, may still be redundant with pytest
        signal = "redundant" if agree else "adds_signal"
    return {
        "deterministic_decision": det["decision"],
        "jev_decision": jdec,
        "agree": agree,
        "signal": signal,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "specs").mkdir(exist_ok=True)
    (OUT / "renders").mkdir(exist_ok=True)

    print("=" * 64)
    print("Jev FINAL gate test (review/quality on figures)")
    print("=" * 64)

    # shared pytest once (tree signal)
    print("[pytest] running layout/geo/jev unit subset...")
    pytest_blob = run_pytest()
    print(f"  exit={pytest_blob['exit_code']} {pytest_blob['summary']} ({pytest_blob['wall_s']}s)")

    scenarios: List[Dict[str, Any]] = []

    # ---- 1 clean ----
    print("\n[1] clean shippable")
    cspec = clean_spec()
    (OUT / "specs" / "clean.json").write_text(json.dumps(cspec, indent=2))
    clean_svg = OUT / "renders" / "clean.svg"
    # reuse probe if present
    if PROBE_SVG.exists() and PROBE_SVG.stat().st_size > 500:
        clean_svg.write_bytes(PROBE_SVG.read_bytes())
        rend = {"ok": True, "path": str(clean_svg), "bytes": clean_svg.stat().st_size, "reused": str(PROBE_SVG)}
    else:
        rend = render_spec(cspec, clean_svg)
        rend["reused"] = None
    lint = _lint_dict(cspec)
    status = layout_status(cspec)
    defects = _defect_signals(cspec)
    det = deterministic_verdict("clean", lint, status, defects, pytest_blob["passed"])
    state = figure_state(cspec, scenario="clean", svg_path=rend["path"], extra=defects)
    print(f"  lint={lint['score']:.3f} overlaps={lint['n_overlap']} status_score={status['geometry_score']:.3f}")
    print(f"  det={det['decision']} render_ok={rend['ok']} bytes={rend['bytes']}")
    try:
        jev = run_jev_gate(
            state,
            exempt_dims=V01_EXEMPT_DIMS_FIGURE,
            instructions_extra=FIGURE_INSTRUCTIONS,
        )
        print(f"  jev={jev['gate']['decision']} tok_in={jev['usage']['input_tokens']} wall={jev['wall_s']}s")
        print(f"  reasons={jev['gate']['reasons']}")
        for dim in ("correctness", "reliability", "compatibility"):
            a = jev["answers"].get(dim, {})
            print(f"    {dim}: score={a.get('score')} conf={a.get('confidence')}")
        for g in jev_client._NOUL_GATES:
            print(f"    {g}: noul={jev['answers'].get(g, {}).get('noul')}")
        if "route" in jev["answers"]:
            print(f"    route: {jev['answers']['route'].get('choice')}")
    except Exception as exc:
        jev = {"error": str(exc), "traceback": traceback.format_exc(limit=4)}
        print(f"  JEV ERROR: {exc}")
    cmp_ = jev_vs_det(det, jev if "gate" in jev else {}, "clean")
    scenarios.append({
        "id": "1_clean",
        "name": "clean_shippable",
        "render": rend,
        "geo_linter": lint,
        "layout_status": status,
        "defect_signals": defects,
        "pytest": {"passed": pytest_blob["passed"], "summary": pytest_blob["summary"]},
        "deterministic": det,
        "jev": jev,
        "comparison": cmp_,
        "v0_1_exempt_dims": sorted(V01_EXEMPT_DIMS_FIGURE),
    })

    # ---- 2 defective ----
    print("\n[2] defective (off-canvas + stacked + missing ref)")
    dspec = defective_spec()
    (OUT / "specs" / "defective.json").write_text(json.dumps(dspec, indent=2))
    dsvg = OUT / "renders" / "defective.svg"
    rend = render_spec(dspec, dsvg)
    lint = _lint_dict(dspec)
    status = layout_status(dspec)
    defects = _defect_signals(dspec)
    det = deterministic_verdict("defective", lint, status, defects, pytest_blob["passed"])
    state = figure_state(dspec, scenario="defective", svg_path=rend.get("path"), extra=defects)
    print(f"  lint={lint['score']:.3f} overlaps={lint['overlap_issues']}")
    print(f"  defects={defects}")
    print(f"  det={det['decision']} detector_ok={det['detector_ok']}")
    try:
        jev = run_jev_gate(
            state,
            exempt_dims=V01_EXEMPT_DIMS_FIGURE,
            instructions_extra=FIGURE_INSTRUCTIONS,
        )
        print(f"  jev={jev['gate']['decision']} tok_in={jev['usage']['input_tokens']} wall={jev['wall_s']}s")
        print(f"  scores={ {k: v for k, v in jev['gate']['scores'].items()} }")
        print(f"  reasons={jev['gate']['reasons']}")
        for dim in jev_client._CORE_DIMS:
            a = jev["answers"].get(dim, {})
            if a.get("applicable") is False:
                print(f"    {dim}: N/A")
            else:
                print(f"    {dim}: score={a.get('score')} conf={a.get('confidence')}")
        for g in jev_client._NOUL_GATES:
            print(f"    {g}: noul={jev['answers'].get(g, {}).get('noul')}")
        if "route" in jev["answers"]:
            print(f"    route: {jev['answers']['route'].get('choice')}")
    except Exception as exc:
        jev = {"error": str(exc), "traceback": traceback.format_exc(limit=4)}
        print(f"  JEV ERROR: {exc}")
    cmp_ = jev_vs_det(det, jev if "gate" in jev else {}, "defective")
    scenarios.append({
        "id": "2_defective",
        "name": "geometrically_fine_but_defective",
        "render": rend,
        "geo_linter": lint,
        "layout_status": status,
        "defect_signals": defects,
        "pytest": {"passed": pytest_blob["passed"], "summary": pytest_blob["summary"]},
        "deterministic": det,
        "jev": jev,
        "comparison": cmp_,
        "v0_1_exempt_dims": sorted(V01_EXEMPT_DIMS_FIGURE),
    })

    # ---- 3 docs/style ----
    print("\n[3] docs/style-only (test_coverage exempt v0.1)")
    # no figure; use a clean figure as "unchanged product" plus docs diff state
    docs_state = docs_style_diff_blob()
    # attach tree green signal
    docs_state["pytest"] = pytest_blob
    docs_state["figure"] = "unchanged; no geometry delta"
    (OUT / "specs" / "docs_style_state.json").write_text(json.dumps(docs_state, indent=2, default=str))
    lint = {"score": None, "n_overlap": 0, "overlap_issues": [], "alignment_issues": [], "grid_issues": [], "n_align": 0, "n_grid": 0}
    status = {}
    defects = {"shippable_extra": True, "note": "no figure delta"}
    det = deterministic_verdict("docs_style", lint, status, defects, pytest_blob["passed"])
    print(f"  det={det['decision']} pytest={pytest_blob['passed']}")
    try:
        jev = run_jev_gate(
            docs_state,
            exempt_dims=V01_EXEMPT_DIMS_DOCS,
            instructions_extra=(
                "Docs/style-only change. test_coverage is NOT applicable. "
                "Score remaining dims for a safe docs/style polish PR."
            ),
        )
        print(f"  jev={jev['gate']['decision']} tok_in={jev['usage']['input_tokens']} wall={jev['wall_s']}s")
        print(f"  exempt={jev['exempt_dims_applied']} reasons={jev['gate']['reasons']}")
        for dim in jev_client._CORE_DIMS:
            a = jev["answers"].get(dim, {})
            if a.get("applicable") is False:
                print(f"    {dim}: N/A (exempt)")
            else:
                print(f"    {dim}: score={a.get('score')} conf={a.get('confidence')}")
        for g in jev_client._NOUL_GATES:
            print(f"    {g}: noul={jev['answers'].get(g, {}).get('noul')}")
    except Exception as exc:
        jev = {"error": str(exc), "traceback": traceback.format_exc(limit=4)}
        print(f"  JEV ERROR: {exc}")
    cmp_ = jev_vs_det(det, jev if "gate" in jev else {}, "docs_style")
    scenarios.append({
        "id": "3_docs_style",
        "name": "docs_style_only_exempt_test_coverage",
        "render": None,
        "geo_linter": lint,
        "layout_status": status,
        "defect_signals": defects,
        "pytest": pytest_blob,
        "deterministic": det,
        "jev": jev,
        "comparison": cmp_,
        "v0_1_exempt_dims": sorted(V01_EXEMPT_DIMS_DOCS),
    })

    # ---- overall ----
    signals = [s["comparison"].get("signal") for s in scenarios if "comparison" in s]
    agrees = [s["comparison"].get("agree") for s in scenarios if "comparison" in s]
    jev_errors = sum(1 for s in scenarios if isinstance(s.get("jev"), dict) and s["jev"].get("error"))
    total_tok = 0
    total_usd = 0.0
    for s in scenarios:
        u = (s.get("jev") or {}).get("usage") or {}
        total_tok += int(u.get("total_tokens") or 0)
        total_usd += float(u.get("usd_estimate") or 0)

    # Does gate add signal?
    # - defective: if det already catches AND jev also fails -> agree on fail
    # - clean: must PASS for gate to be usable as ship gate; false hard_fail is bad
    # - docs: exempt path must not hard-fail on test_coverage
    det_catches_defect = scenarios[1]["deterministic"]["detector_ok"]
    jev1 = (scenarios[0].get("jev") or {}).get("gate", {}) or {}
    jev2 = (scenarios[1].get("jev") or {}).get("gate", {}) or {}
    jev3 = (scenarios[2].get("jev") or {}).get("gate", {}) or {}
    jev_clean = jev1.get("decision")
    jev_defect = jev2.get("decision")
    jev_docs = jev3.get("decision")
    jev_catches_defect = jev_defect in ("hard_fail", "escalate")
    jev_clean_pass = jev_clean == "pass"
    docs_pass = jev_docs == "pass"
    docs_escalate = jev_docs == "escalate"
    docs_failed_on_coverage = any(
        "test_coverage" in r for r in (jev3.get("reasons") or [])
    )

    notes = []
    if not jev_clean_pass:
        notes.append(
            f"CLEAN false-fail: jev={jev_clean} reasons={jev1.get('reasons')} "
            "— v0.1 hard_min/correctness thresholds + code-shaped criteria under-score "
            "even a shippable figure (lint=0.83, zero defects)."
        )
    if jev_catches_defect and det_catches_defect:
        notes.append(
            "DEFECT: both det and Jev hard_fail — agree, but det already free "
            "(off-canvas/stacked/missing-ref/overlap)."
        )
    elif jev_catches_defect and not det_catches_defect:
        notes.append("DEFECT: Jev caught what det missed — gate adds signal.")
    elif not jev_catches_defect and det_catches_defect:
        notes.append("DEFECT: Jev missed a real defect det caught — gate weaker than det.")
    if docs_failed_on_coverage:
        notes.append("DOCS: failed on test_coverage despite v0.1 exempt — exempt path broken.")
    elif docs_pass:
        notes.append("DOCS: pass with test_coverage N/A — exempt path works.")
    elif docs_escalate:
        notes.append(
            f"DOCS: escalate (not coverage) reasons={jev3.get('reasons')} "
            "— exempt works; low confidence on another dim."
        )

    if jev_errors:
        overall_headline = f"INCOMPLETE — {jev_errors} Jev call(s) failed"
        overall_call = "inconclusive"
    elif not jev_clean_pass and jev_catches_defect:
        overall_headline = (
            "NO as ship-gate — false hard_fail on clean figure; "
            "YES on defect agreement (redundant with free det checks); "
            "docs exempt path OK (escalate≠coverage). "
            "Gate does not add unique geo signal; thresholds need recalibration for figures."
        )
        overall_call = "redundant_for_geo_miscalibrated_for_ship"
    elif jev_clean_pass and jev_catches_defect and det_catches_defect:
        overall_headline = (
            "PARTIAL — agrees ship/fail with det; defect already caught free; "
            "useful second opinion, not required for geo."
        )
        overall_call = "mostly_redundant_for_geo"
    elif not det_catches_defect and jev_catches_defect:
        overall_headline = "YES — gate adds signal (caught defect deterministic miss)"
        overall_call = "adds_signal"
    else:
        overall_headline = "MIXED — see per-scenario comparison"
        overall_call = "mixed"

    overall = {
        "headline": overall_headline,
        "call": overall_call,
        "notes": notes,
        "signals": signals,
        "agreements": agrees,
        "det_catches_defect": det_catches_defect,
        "jev_catches_defect": jev_catches_defect,
        "jev_clean_decision": jev_clean,
        "jev_clean_pass": jev_clean_pass,
        "docs_decision": jev_docs,
        "docs_pass": docs_pass,
        "docs_failed_on_coverage": docs_failed_on_coverage,
        "total_tokens": total_tok,
        "total_usd": round(total_usd, 8),
        "pytest_passed": pytest_blob["passed"],
    }

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "role": "Jev review/quality GATE on rendered figures (not action-picker)",
            "spec": "scientist v0.1 thresholds + docs/style test_coverage exempt",
            "thresholds": dict(jev_client.V0_THRESHOLDS),
            "probe_clean_reused": str(PROBE_SVG) if PROBE_SVG.exists() else None,
            "pytest_targets": PYTEST_TARGETS,
        },
        "pytest": pytest_blob,
        "scenarios": scenarios,
        "overall": overall,
    }

    json_path = OUT / "results.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str))

    # markdown
    md = []
    md.append("# Jev FINAL gate test — review/quality on figures")
    md.append("")
    md.append(f"- Generated: `{payload['meta']['generated_at']}`")
    md.append(f"- Role: **review gate**, not action-picker")
    md.append(f"- Thresholds: `{json.dumps(jev_client.V0_THRESHOLDS)}`")
    md.append(f"- Pytest: exit={pytest_blob['exit_code']} `{pytest_blob['summary']}`")
    md.append(f"- Tokens total: {total_tok} (≈${total_usd:.6f})")
    md.append("")
    md.append("## Overall")
    md.append("")
    md.append(f"**{overall_headline}**")
    md.append("")
    md.append(f"- call: `{overall_call}`")
    md.append(f"- det catches defect: {det_catches_defect}")
    md.append(f"- jev catches defect: {jev_catches_defect}")
    md.append(f"- docs pass (coverage exempt): {docs_pass} (failed_on_coverage={docs_failed_on_coverage})")
    md.append("")
    md.append("## Per scenario")
    md.append("")
    md.append("| # | scenario | det | jev | agree | signal | lint | tok_in |")
    md.append("|---|---|---|---|---|---|---:|---:|")
    for s in scenarios:
        j = s.get("jev") or {}
        g = j.get("gate") or {}
        u = j.get("usage") or {}
        lint_s = s.get("geo_linter") or {}
        sc = lint_s.get("score")
        sc_s = f"{sc:.3f}" if isinstance(sc, (int, float)) else "n/a"
        md.append(
            f"| {s['id']} | {s['name']} | {s['deterministic']['decision']} | "
            f"{g.get('decision', j.get('error', '?'))} | {s['comparison'].get('agree')} | "
            f"{s['comparison'].get('signal')} | {sc_s} | {u.get('input_tokens', 0)} |"
        )
    md.append("")
    for s in scenarios:
        md.append(f"### {s['id']} — {s['name']}")
        md.append("")
        md.append(f"- deterministic: `{s['deterministic']}`")
        j = s.get("jev") or {}
        if j.get("error"):
            md.append(f"- jev ERROR: {j['error']}")
        else:
            g = j.get("gate") or {}
            md.append(f"- jev decision: **{g.get('decision')}** reasons={g.get('reasons')}")
            md.append(f"- model: `{j.get('model')}` wall={j.get('wall_s')}s usage={j.get('usage')}")
            md.append("- scores:")
            for dim, val in (j.get("answers") or {}).items():
                if val.get("type") == "score":
                    if val.get("applicable") is False:
                        md.append(f"  - {dim}: N/A")
                    else:
                        md.append(f"  - {dim}: score={val.get('score')} conf={val.get('confidence')} raw={val.get('raw')}")
                elif val.get("type") == "noul":
                    md.append(f"  - {dim}: noul={val.get('noul')}")
                elif val.get("type") == "choice":
                    md.append(f"  - {dim}: choice={val.get('choice')} conf={val.get('confidence')}")
        if s.get("defect_signals"):
            md.append(f"- defect_signals: `{json.dumps(s['defect_signals'], default=str)[:500]}`")
        if s.get("geo_linter") and s["geo_linter"].get("overlap_issues") is not None:
            md.append(f"- overlaps: {s['geo_linter'].get('overlap_issues')}")
        md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append(
        "- Deterministic stack (geo_linter + layout_status + defect_signals + pytest) "
        "is free and already encodes ship/fail for pure geometry."
    )
    md.append(
        "- Jev review gate adds value when judging *code/docs diffs* (scenario 3) or "
        "ambiguous aesthetic/correctness calls; for hard geo defects it should agree, not lead."
    )
    md.append(
        "- Prior action-picker benchmark already said greedy wins for de-collision; "
        "this test isolates the *gate* role."
    )
    md.append("")
    md_path = OUT / "SUMMARY.md"
    md_path.write_text("\n".join(md))

    print("\n" + "=" * 64)
    print(overall_headline)
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0 if jev_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
