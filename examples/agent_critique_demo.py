#!/usr/bin/env python3
"""Agent Critique Demo — Using techfig's deterministic critique_report API.

This script demonstrates how an AI agent (or any orchestrator) can use
techfig's deterministic geometric critique to iteratively improve a
diagram spec — without any LLM API calls.

The self-improvement loop is **agent-driven**: the agent calls
critique_report(), reviews the output, modifies the spec, and repeats.

Usage:
    python examples/agent_critique_demo.py

Outputs land in:  output/agent_critique/
    v1.svg, v2.svg, ..., experiment_log.json
"""

import json
import sys
from pathlib import Path
import copy

# ── project root on path ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from techfig.engines.autoresearch import critique_report  # noqa: E402
from techfig.engines.geo_linter import snap_to_grid, align_rows_and_cols  # noqa: E402

OUT_DIR = ROOT / "output" / "agent_critique"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_demo_spec() -> dict:
    """Load a deliberately flawed spec for demonstration."""
    optical_path = ROOT / "examples" / "optical_diagram_spec.json"
    if optical_path.exists():
        with open(optical_path) as f:
            return json.load(f)

    # Fallback: a flowchart with off-grid coordinates
    return {
        "canvas": {"width": 800, "height": 400},
        "elements": [
            {"type": "box", "id": "start", "x": 103, "y": 55, "w": 80, "h": 40,
             "text": "Start", "color": "#0072B2"},
            {"type": "diamond", "id": "check", "x": 303, "y": 57, "w": 100, "h": 60,
             "text": "Check?", "color": "#D55E00"},
            {"type": "box", "id": "done", "x": 503, "y": 53, "w": 80, "h": 40,
             "text": "Done", "color": "#009E73"},
            {"type": "box", "id": "error", "x": 303, "y": 155, "w": 80, "h": 40,
             "text": "Error", "color": "#CC0000"},
        ],
        "connections": [
            {"from": "start", "to": "check", "style": "arrow"},
            {"from": "check", "to": "done", "style": "arrow", "label": "yes"},
            {"from": "check", "to": "error", "style": "arrow", "label": "no"},
        ],
    }


def rule_based_fix(spec: dict, feedback: list[str], suggestions: list[str]) -> dict:
    """Apply deterministic fixes based on critique feedback.

    In a real agent-driven loop, the AI agent decides what to change.
    Here we use simple rule-based fixes as a demonstration.
    """
    new_spec = copy.deepcopy(spec)
    fb = " ".join(feedback + suggestions).lower()

    # Always snap to grid
    new_spec = snap_to_grid(new_spec, grid_size=10.0)

    # Align nearly-aligned rows/cols if misalignment detected
    if "misalign" in fb or "alignment" in fb:
        new_spec = align_rows_and_cols(new_spec, tolerance=25.0)

    # Normalize thin strokes
    style = new_spec.get("style", {})
    if style.get("stroke_width", 2) < 1.5:
        style["stroke_width"] = 2.0
        new_spec["style"] = style

    return new_spec


def main():
    spec = load_demo_spec()
    log = []
    max_rounds = 3

    print("=" * 60)
    print("  TechFig Agent Critique Demo")
    print("  Demonstrating agent-driven self-improvement loop")
    print("=" * 60)
    for round_num in range(1, max_rounds + 1):
        svg_path = str(OUT_DIR / f"v{round_num}.svg")
        report = critique_report(spec, svg_path)

        score = report["score"]
        issues = report["issues"]
        suggestions = report["suggestions"]

        log.append({
            "round": round_num,
            "svg_path": svg_path,
            "score": round(score, 4),
            "issues": issues,
            "suggestions": suggestions,
        })

        print(f"\n  Round {round_num} | Score: {score:.3f} | SVG: {Path(svg_path).name}")
        if issues:
            print(f"  Issues ({len(issues)}):")
            for i in issues:
                print(f"    - {i}")
        if suggestions:
            print("  Suggestions:")
            for s in suggestions:
                print(f"    → {s}")

        # Agent decision: stop if score is good enough
        if score >= 0.9:
            print("\n  ✓ Score >= 0.9 — figure looks good!")
            break

        # Apply fixes (in a real loop, the AI agent decides what to change)
        spec = rule_based_fix(spec, issues, suggestions)

    # Write experiment log
    log_path = OUT_DIR / "experiment_log.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"\n  Log saved to {log_path}")
    print(f"  Final score: {log[-1]['score']}")


if __name__ == "__main__":
    main()
