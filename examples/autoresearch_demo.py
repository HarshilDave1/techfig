#!/usr/bin/env python3
"""Autoresearch Demo — Agent-in-the-Loop

Runs the diagram autoresearch refinement loop in two modes:

  --mode geo_only   Fully offline. Geo linter scores; rule-based mutator auto-fixes.
  --mode agent      I (the AI agent) view each rendered SVG and provide visual feedback.
                    No API key needed — agent replaces the LLM aesthetic critic.

Usage:
    python examples/autoresearch_demo.py --mode geo_only  [--rounds 3] [--scenario all]
    python examples/autoresearch_demo.py --mode agent     [--rounds 3] [--scenario flowchart]

Outputs land in:  output/autoresearch/<scenario>/
    gen_0.svg, gen_1.svg, ..., gen_N.svg, experiment_log.json
"""

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ── project root on path ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from techfig.engines.geo_linter import lint_spec, snap_to_grid, align_rows_and_cols  # noqa: E402
from techfig.engines.sketch_interpreter import render_from_spec  # noqa: E402

OUT_BASE = ROOT / "output" / "autoresearch"


# ══════════════════════════════════════════════════════════════════════════════
# Starting specs — deliberately flawed so the loop has something to fix
# ══════════════════════════════════════════════════════════════════════════════

def _load_optical_spec() -> Dict[str, Any]:
    path = ROOT / "examples" / "optical_diagram_spec.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    # Minimal fallback
    return {
        "canvas": {"width": 1200, "height": 600},
        "elements": [
            {"type": "box",    "id": "src",  "x": -400, "y": 0, "w": 80, "h": 60, "text": "Source"},
            {"type": "ellipse","id": "lens", "x": -200, "y": 0, "rx": 15, "ry": 55, "text": "Lens"},
            {"type": "box",    "id": "det",  "x":  200, "y": 0, "w": 60, "h": 60, "text": "Detector"},
        ],
        "connections": [{"from": "src", "to": "det", "style": "line"}],
    }


SCENARIOS: Dict[str, Dict[str, Any]] = {

    # ── 1. Neural Network ─────────────────────────────────────────────────────
    # Flaws: nodes not on a grid, X-positions slightly off across layers,
    #        inconsistent circle radii, stroke too thin.
    "neural_net": {
        "canvas": {"width": 900, "height": 560},
        "style": {
            "font_family": "Inter, Helvetica, Arial, sans-serif",
            "font_size": 13,
            "stroke_width": 1,          # ← too thin
            "colors": {
                "primary": "#0072B2",
                "secondary": "#D55E00",
                "accent": "#009E73",
                "background": "#FFFFFF",
                "text": "#222222",
                "stroke": "#888888",    # ← washed-out
                "muted": "#DDDDDD",
            },
        },
        "elements": [
            # Title
            {"type": "text", "x": 0, "y": -243, "text": "Feed-Forward Neural Network",
             "font_size": 18, "color": "#222222"},
            # Layer labels
            {"type": "text", "x": -248, "y": -183, "text": "Input",  "font_size": 13},
            {"type": "text", "x":    3, "y": -218, "text": "Hidden", "font_size": 13},
            {"type": "text", "x":  252, "y": -183, "text": "Output", "font_size": 13},
            # Input layer (4 nodes) – x slightly off from -250
            {"type": "circle", "id": "i0", "x": -248, "y": -105, "r": 21, "text": "", "color": "#D55E00"},
            {"type": "circle", "id": "i1", "x": -250, "y":  -35, "r": 22, "text": "", "color": "#D55E00"},
            {"type": "circle", "id": "i2", "x": -252, "y":   35, "r": 20, "text": "", "color": "#D55E00"},
            {"type": "circle", "id": "i3", "x": -249, "y":  105, "r": 21, "text": "", "color": "#D55E00"},
            # Hidden layer (5 nodes) – x slightly off from 0
            {"type": "circle", "id": "h0", "x":   3, "y": -140, "r": 22, "text": "", "color": "#0072B2"},
            {"type": "circle", "id": "h1", "x":   0, "y":  -70, "r": 22, "text": "", "color": "#0072B2"},
            {"type": "circle", "id": "h2", "x":  -2, "y":    0, "r": 21, "text": "", "color": "#0072B2"},
            {"type": "circle", "id": "h3", "x":   1, "y":   70, "r": 22, "text": "", "color": "#0072B2"},
            {"type": "circle", "id": "h4", "x":   2, "y":  140, "r": 23, "text": "", "color": "#0072B2"},
            # Output layer (3 nodes) – x slightly off from 250
            {"type": "circle", "id": "o0", "x": 252, "y":  -70, "r": 22, "text": "", "color": "#009E73"},
            {"type": "circle", "id": "o1", "x": 249, "y":    0, "r": 22, "text": "", "color": "#009E73"},
            {"type": "circle", "id": "o2", "x": 251, "y":   70, "r": 21, "text": "", "color": "#009E73"},
        ],
        "connections": [
            *[{"from": f"i{i}", "to": f"h{j}", "style": "connection", "color": "muted"}
              for i in range(4) for j in range(5)],
            *[{"from": f"h{i}", "to": f"o{j}", "style": "connection", "color": "muted"}
              for i in range(5) for j in range(3)],
        ],
    },

    # ── 2. Flowchart ──────────────────────────────────────────────────────────
    # Flaws: boxes crowded together, Y-positions not on grid, clashing orange+purple.
    "flowchart": {
        "canvas": {"width": 1000, "height": 500},
        "style": {
            "font_family": "Helvetica, Arial, sans-serif",
            "font_size": 14,
            "stroke_width": 2,
            "colors": {
                "primary":    "#FF6600",  # ← harsh orange
                "secondary":  "#770077",  # ← clashing purple
                "accent":     "#00AA00",
                "background": "#F0F0F0",  # ← grey bg (noisy)
                "text":       "#000000",
                "stroke":     "#000000",
            },
        },
        "elements": [
            {"type": "box",     "id": "start",   "x": -383, "y": -27, "w": 110, "h": 55,
             "text": "Start",   "color": "#FF6600"},
            {"type": "diamond", "id": "valid",   "x": -183, "y": -29, "w": 110, "h": 60,
             "text": "Valid?",  "color": "#770077"},
            {"type": "box",     "id": "process", "x":   17, "y": -29, "w": 130, "h": 58,
             "text": "Process", "color": "#FF6600"},
            {"type": "box",     "id": "error",   "x": -183, "y":  91, "w": 110, "h": 55,
             "text": "Error",   "color": "#CC0000"},
            {"type": "box",     "id": "done",    "x":  220, "y": -29, "w": 110, "h": 56,
             "text": "Done",    "color": "#00AA00"},
        ],
        "connections": [
            {"from": "start",   "to": "valid",   "style": "arrow", "label": "submit"},
            {"from": "valid",   "to": "process", "style": "arrow", "label": "yes"},
            {"from": "valid",   "to": "error",   "style": "arrow", "label": "no"},
            {"from": "process", "to": "done",    "style": "arrow", "label": "complete"},
        ],
    },

    # ── 3. Optical Interferometer (from examples/optical_diagram_spec.json) ──
    # We use the existing real spec — it's already reasonable but the loop
    # may tighten coordinate grid adherence and improve spacing.
    "optical": _load_optical_spec(),
}


# ══════════════════════════════════════════════════════════════════════════════
# Critics
# ══════════════════════════════════════════════════════════════════════════════

class GeoCritic:
    """Fully offline deterministic critic using only the geometric linter."""

    def score(self, spec: Dict[str, Any], svg_path: str) -> Tuple[float, str]:
        report = lint_spec(spec)
        issues = report.alignment_issues + report.grid_issues + report.overlap_issues
        feedback = (
            "Geometric Issues to fix:\n- " + "\n- ".join(issues)
            if issues
            else "No major geometric issues. Consider improving color contrast and readability."
        )
        return report.score, feedback


class AgentCritic:
    """
    Critic backed by the AI agent's own visual judgment.

    In interactive mode, the script pauses. The agent can use view_file to
    read the SVG source code (or open the browser), then uses send_command_input
    to provide the score and text feedback.
    """
    def score(self, spec: Dict[str, Any], svg_path: str) -> Tuple[float, str]:
        geo_report = lint_spec(spec)
        geo_score = geo_report.score

        print(f"\n[AgentCritic] Generated: {svg_path}")
        print(f"[AgentCritic] Geo score baseline: {geo_score:.3f}")
        
        try:
            agent_score_str = input("[AgentCritic] Enter visual score (0.0 - 1.0) or press Enter to skip: ").strip()
            if not agent_score_str:
                issues = geo_report.alignment_issues + geo_report.grid_issues
                return geo_score, "\n".join(issues) or "Looking good geometrically."
            
            agent_score = float(agent_score_str)
            agent_feedback = input("[AgentCritic] Enter feedback / issues to fix: ").strip()
            
            blended = 0.4 * geo_score + 0.6 * agent_score
            return blended, agent_feedback
        except Exception as e:
            print(f"[AgentCritic] Error reading input: {e}")
            issues = geo_report.alignment_issues + geo_report.grid_issues
            return geo_score, "\n".join(issues) or "Looking good geometrically."


# ══════════════════════════════════════════════════════════════════════════════
# Rule-based mutator (offline)
# ══════════════════════════════════════════════════════════════════════════════

def rule_mutator(spec: Dict[str, Any], feedback: str) -> Dict[str, Any]:
    """
    Apply targeted fixes based on geo_linter feedback text.

    Reads the feedback string (from either GeoCritic or AgentCritic) and applies:
      - Grid snapping  (if any grid issues mentioned)
      - Row/col alignment (if any misalignment mentioned)
      - Stroke width normalization (if stroke_width < 1.5)
      - Radius normalization (if circles have inconsistent radii)
    """
    new_spec = copy.deepcopy(spec)

    fb_lower = feedback.lower()

    # Always snap to grid
    new_spec = snap_to_grid(new_spec, grid_size=10.0)

    # Align rows + cols
    if "misaligned" in fb_lower or "alignment" in fb_lower:
        new_spec = align_rows_and_cols(new_spec, tolerance=25.0)

    # Normalize stroke width
    style = new_spec.get("style", {})
    if style.get("stroke_width", 2) < 1.5:
        style["stroke_width"] = 2.0
        new_spec["style"] = style

    # Normalize circle radii within the same layer (make them all the same)
    circles = [e for e in new_spec.get("elements", []) if e.get("type") == "circle"]
    if len(circles) > 1:
        # Compute median radius
        radii = sorted(float(c.get("r", 20)) for c in circles)
        median_r = radii[len(radii) // 2]
        for c in circles:
            c["r"] = median_r

    # Improve color palette if feedback flags colors
    if any(kw in fb_lower for kw in ("color", "contrast", "harsh", "clash", "orange", "purple")):
        _apply_palette_fix(new_spec)

    # Improve background color
    style = new_spec.get("style", {})
    colors = style.get("colors", {})
    if colors.get("background") in ("#F0F0F0", "#EEEEEE", "#E0E0E0"):
        colors["background"] = "#FFFFFF"
        new_spec["style"]["colors"] = colors

    return new_spec


def _apply_palette_fix(spec: Dict[str, Any]):
    """Replace harsh/clashing colors with a clean colorblind-friendly palette."""
    PALETTE = {
        "#FF6600": "#0072B2",   # harsh orange → professional blue
        "#770077": "#E69F00",   # clashing purple → warm amber
        "#888888": "#555555",   # washed-out stroke → stronger grey
        "#DDDDDD": "#CCCCCC",   # muted connections → slightly stronger
    }
    style = spec.get("style", {})
    colors = style.get("colors", {})
    for old, new in PALETTE.items():
        if colors.get("primary") == old:
            colors["primary"] = new
        if colors.get("secondary") == old:
            colors["secondary"] = new
        if colors.get("stroke") == old:
            colors["stroke"] = new
        if colors.get("muted") == old:
            colors["muted"] = new

    # Also patch individual element colors
    for el in spec.get("elements", []):
        c = el.get("color", "")
        if c in PALETTE:
            el["color"] = PALETTE[c]


# ══════════════════════════════════════════════════════════════════════════════
# Loop runner
# ══════════════════════════════════════════════════════════════════════════════

class LocalResearchLoop:
    """
    Stripped-down autoresearch loop using only local tools (geo linter + rule mutator).
    Mirrors the interface of AutoResearchLoop but needs no LLM API.
    """

    def __init__(
        self,
        scenario_name: str,
        initial_spec: Dict[str, Any],
        output_dir: str,
        critic,
        max_rounds: int = 3,
    ):
        self.name = scenario_name
        self.initial_spec = copy.deepcopy(initial_spec)
        self.output_dir = Path(output_dir)
        self.critic = critic
        self.max_rounds = max_rounds
        self.log: List[Dict[str, Any]] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _render(self, spec: Dict[str, Any], gen: int) -> str:
        path = str(self.output_dir / f"gen_{gen}.svg")
        render_from_spec(spec, path)
        return path

    def run(self) -> Dict[str, Any]:
        print(f"\n{'─'*60}")
        print(f"  Scenario: {self.name}  ({self.max_rounds} rounds)")
        print(f"  Output:   {self.output_dir}")
        print(f"{'─'*60}")

        best_spec = copy.deepcopy(self.initial_spec)
        svg_path = self._render(best_spec, 0)
        best_score, feedback = self.critic.score(best_spec, svg_path)

        self.log.append({"gen": 0, "score": round(best_score, 4),
                         "kept": True, "svg": svg_path})
        print(f"  Gen 0 │ score={best_score:.3f} │ ★ BASELINE  → {Path(svg_path).name}")

        for gen in range(1, self.max_rounds + 1):
            try:
                candidate = rule_mutator(best_spec, feedback)
                svg_path = self._render(candidate, gen)
                score, new_feedback = self.critic.score(candidate, svg_path)

                kept = score >= best_score
                if kept:
                    best_spec = candidate
                    best_score = score
                    feedback = new_feedback
                    mark = "✓ KEPT   "
                else:
                    mark = "✗ REJECT "

                self.log.append({"gen": gen, "score": round(score, 4),
                                 "kept": kept, "svg": svg_path})
                print(f"  Gen {gen} │ score={score:.3f} │ {mark} → {Path(svg_path).name}")

            except Exception as e:
                print(f"  Gen {gen} │ ERROR: {e}")

        # Write log
        log_path = self.output_dir / "experiment_log.json"
        with open(log_path, "w") as f:
            json.dump(self.log, f, indent=2)

        print(f"\n  Best score: {best_score:.3f}  |  Log: {log_path.name}")
        return best_spec


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="TechFig Autoresearch Demo")
    parser.add_argument(
        "--mode", choices=["geo_only", "agent"], default="geo_only",
        help="geo_only: fully offline rule-based; agent: agent acts as visual critic",
    )
    parser.add_argument("--rounds", type=int, default=3,
                        help="Refinement rounds per scenario (default: 3)")
    parser.add_argument(
        "--scenario", default="all",
        choices=["all"] + list(SCENARIOS.keys()),
        help="Which scenario to run (default: all)",
    )
    args = parser.parse_args()

    scenarios = SCENARIOS if args.scenario == "all" else {args.scenario: SCENARIOS[args.scenario]}

    print("=" * 60)
    print("  TechFig Autoresearch Demo")
    print(f"  Mode: {args.mode}   Rounds: {args.rounds}")
    print("=" * 60)

    summary = []

    for name, spec in scenarios.items():
        out_dir = OUT_BASE / name
        critic = GeoCritic() if args.mode == "geo_only" else AgentCritic()

        loop = LocalResearchLoop(
            scenario_name=name,
            initial_spec=spec,
            output_dir=str(out_dir),
            critic=critic,
            max_rounds=args.rounds,
        )
        best = loop.run()

        # Save final best spec
        best_spec_path = out_dir / "best_spec.json"
        with open(best_spec_path, "w") as f:
            json.dump(best, f, indent=2)

        scores = [e["score"] for e in loop.log]
        summary.append({
            "scenario": name,
            "start_score": scores[0],
            "end_score": scores[-1],
            "delta": round(scores[-1] - scores[0], 4),
            "output_dir": str(out_dir),
        })

    print("\n" + "=" * 60)
    print("  Score Summary")
    print("=" * 60)
    print(f"  {'Scenario':<20} {'Start':>7} {'End':>7} {'Delta':>7}")
    print(f"  {'-'*46}")
    for s in summary:
        delta_str = f"+{s['delta']:.3f}" if s['delta'] >= 0 else f"{s['delta']:.3f}"
        print(f"  {s['scenario']:<20} {s['start_score']:>7.3f} {s['end_score']:>7.3f} {delta_str:>7}")

    print(f"\n  All SVGs in: {OUT_BASE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
