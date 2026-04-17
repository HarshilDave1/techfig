"""Deterministic critique engine for diagram specs.

Provides critique_report() — a purely deterministic function that renders a
spec to SVG and scores it using the geometric linter. No LLM calls, no API
keys needed.

The self-improvement loop is **agent-driven**: the agent calls critique_report(),
reviews the output (and optionally the SVG visually), modifies the spec, and
repeats until satisfied.
"""

import json
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from techfig.engines.geo_linter import lint_spec
from techfig.engines.sketch_interpreter import render_from_spec


@dataclass
class Experiment:
    """A record of one iteration of an improvement loop."""
    generation: int
    spec: Dict[str, Any]
    svg_path: str
    score: float
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


def critique_report(
    spec_dict: Dict[str, Any],
    svg_path: str,
) -> Dict[str, Any]:
    """Render a spec to SVG and produce a deterministic critique report.

    This is a purely geometric analysis — no LLM calls, no API keys needed.
    It is the first-pass deterministic critique that agents can use in their
    self-improvement loops.

    Args:
        spec_dict: The diagram spec JSON as a Python dict.
        svg_path: Path to write the rendered SVG file.

    Returns:
        A dict with keys:
            score: float 0.0–1.0 (geometric quality)
            issues: list of strings describing detected problems
            suggestions: list of strings suggesting fixes
            svg_path: path to the rendered SVG
            spec: the input spec_dict (echoed for convenience)
    """
    # Render spec to SVG
    render_from_spec(spec_dict, svg_path)

    # Run geometric linter
    geo_report = lint_spec(spec_dict)

    # Gather issues
    issues = (
        geo_report.alignment_issues
        + geo_report.grid_issues
        + geo_report.overlap_issues
    )

    # Generate suggestions from issues
    suggestions: List[str] = []
    if geo_report.grid_issues:
        suggestions.append(
            "Snap coordinates to a consistent grid (e.g., 10px or 20px)."
        )
    if geo_report.alignment_issues:
        suggestions.append(
            "Align nearly-aligned elements to the same row or column."
        )
    if geo_report.overlap_issues:
        suggestions.append(
            "Increase spacing between overlapping elements."
        )
    if geo_report.score >= 0.9:
        suggestions.append(
            "Geometric quality is good. Consider reviewing the SVG "
            "visually for aesthetic improvements."
        )

    return {
        "score": geo_report.score,
        "issues": issues,
        "suggestions": suggestions,
        "svg_path": svg_path,
        "spec": spec_dict,
    }
