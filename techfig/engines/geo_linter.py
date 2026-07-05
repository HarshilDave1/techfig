"""Deterministic geometric scoring and auto-correction.

This module provides tools to score a JSON diagram spec on geometric precision
(alignment, uniformity, grid adherence) and apply automatic corrections.
"""

from typing import Dict, Any, List
from dataclasses import dataclass
import copy


@dataclass
class LintReport:
    """Detailed geometric linting report and score."""
    score: float                # 0.0 - 1.0 (1.0 = perfect alignment)
    alignment_issues: List[str] # Detailed messages about detected issues
    grid_issues: List[str]      # Issues with grid conformance
    overlap_issues: List[str]   # Elements colliding unintentionally
    
    @property
    def total_issues(self) -> int:
        return len(self.alignment_issues) + len(self.grid_issues) + len(self.overlap_issues)


def extract_shapes(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return all elements that represent physical shapes."""
    types = {"box", "circle", "diamond", "ellipse", "triangle"}
    return [el for el in spec.get("elements", []) if el.get("type") in types]


def _is_numeric(val: Any) -> bool:
    return isinstance(val, (int, float))

def snap_to_grid(spec: Dict[str, Any], grid_size: float = 20.0) -> Dict[str, Any]:
    """Auto-correct a spec by snapping coordinates and sizes to a grid.
    
    Returns a deep copy of the spec with snapped values.
    """
    new_spec = copy.deepcopy(spec)
    
    def snap(val):
        if not _is_numeric(val):
            return val
        return round(float(val) / grid_size) * grid_size

    keys_to_snap = ["x", "y", "w", "h", "r", "rx", "ry", "x1", "y1", "x2", "y2"]
    
    for el in new_spec.get("elements", []):
        for k in keys_to_snap:
            if k in el and _is_numeric(el[k]):
                el[k] = snap(el[k])
                
    return new_spec


def _shape_bbox(el: Dict[str, Any]) -> tuple:
    """Return (left, top, right, bottom) bbox for a shape element.

    Coordinates are center-based (x, y = center of the shape), matching the
    SVGBuilder convention. Returns None-like sentinel (inf bbox) for elements
    we cannot size, so they are ignored by overlap checks.
    """
    t = el.get("type")
    if t == "circle":
        r = float(el.get("r", 0))
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        return (x - r, y - r, x + r, y + r)
    if t == "ellipse":
        rx = float(el.get("rx", 0))
        ry = float(el.get("ry", 0))
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        return (x - rx, y - ry, x + rx, y + ry)
    if t in ("box", "diamond", "triangle"):
        w = float(el.get("w", 0))
        h = float(el.get("h", 0))
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    # text / line / unknown -> no reliable bbox for overlap purposes
    return None


def _bboxes_overlap(b1: tuple, b2: tuple) -> bool:
    """Strict AABB overlap test (touching edges do NOT count as overlap)."""
    if b1 is None or b2 is None:
        return False
    return (b1[0] < b2[2] and b2[0] < b1[2] and
            b1[1] < b2[3] and b2[1] < b1[3])


def align_rows_and_cols(spec: Dict[str, Any], tolerance: float = 30.0) -> Dict[str, Any]:
    """Force elements that are almost aligned by Y (rows) or X (columns) to align exactly.

    Groups elements whose X or Y differ by <= tolerance, and averages them,
    setting all elements in the group to the exact same value.

    Safety: a group is only aligned if doing so does NOT create any new
    overlaps between its members. Elements that would be pulled into an
    overlap (e.g. a deliberately-offset diagonal/staircase whose steps are
    within tolerance on both axes) are left untouched. This prevents the
    resolver from destroying good intentional layouts.
    """
    new_spec = copy.deepcopy(spec)
    elements = new_spec.get("elements", [])

    if not elements:
        return new_spec

    # Precompute bboxes for overlap checking. Bboxes are recomputed after each
    # axis pass since coordinates may have changed.
    def bboxes():
        return {id(el): _shape_bbox(el) for el in elements}

    def would_create_overlap(group, axis: str, new_val: float) -> bool:
        """Check if setting `axis` to `new_val` on every member of `group`
        would cause any pair in the group to overlap that did not before."""
        # Build candidate bboxes with the proposed coordinate applied.
        cand = {}
        cur = bboxes()
        for el in group:
            bb = cur.get(id(el))
            if bb is None:
                continue
            # Replace the two coords on `axis` with the new centered value.
            # axis is 'x' or 'y'; bbox layout is (left, top, right, bottom).
            if axis == "x":
                w = bb[2] - bb[0]
                cand[id(el)] = (new_val - w / 2, bb[1], new_val + w / 2, bb[3])
            else:
                h = bb[3] - bb[1]
                cand[id(el)] = (bb[0], new_val - h / 2, bb[2], new_val + h / 2)
        # Compare every pair: a new overlap that was NOT present before counts.
        ids = [id(el) for el in group if id(el) in cand]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = cand[ids[i]], cand[ids[j]]
                if _bboxes_overlap(a, b):
                    # Was this overlap already present in the current layout?
                    if not _bboxes_overlap(cur[ids[i]], cur[ids[j]]):
                        return True
        return False

    def align_axis(axis: str):
        # find groups of elements that share roughly the same coordinate along 'axis'
        # sort elements by the coordinate
        els = [e for e in elements if axis in e and _is_numeric(e[axis])]
        if not els:
            return

        els.sort(key=lambda e: float(e[axis]))

        groups = []
        current_group = [els[0]]

        for e in els[1:]:
            if float(e[axis]) - float(current_group[-1][axis]) <= tolerance:
                current_group.append(e)
            else:
                groups.append(current_group)
                current_group = [e]
        groups.append(current_group)

        # average and apply -- but only if it does not create new overlaps
        for group in groups:
            if len(group) > 1:
                avg = sum(float(e[axis]) for e in group) / len(group)
                avg = round(avg, 2)
                if would_create_overlap(group, axis, avg):
                    # Aligning this group would destroy a good layout: skip it.
                    continue
                for e in group:
                    e[axis] = avg

    align_axis("x")
    align_axis("y")

    # Also align line endpoints
    def align_lines(axis1: str, axis2: str, target: str):
        # E.g. x1 and x2 matching nearby shape x's
        pass # Simplified for now, just snapping elements

    return new_spec


def lint_spec(spec: Dict[str, Any], grid_size: float = 20.0, align_tolerance: float = 30.0) -> LintReport:
    """Analyze a spec and return a score and diagnostic issues."""
    shapes = extract_shapes(spec)
    all_els = spec.get("elements", [])
    
    align_issues = []
    grid_issues = []
    overlap_issues = []
    
    # Check grid snapping
    keys_to_check = ["x", "y", "w", "h", "x1", "y1", "x2", "y2", "r", "rx", "ry"]
    total_checks = 0
    failed_grid_checks = 0
    
    for el in all_els:
        type_str = el.get("type", "unknown")
        el_id = el.get("id", f"{type_str}_no_id")
        
        for k in keys_to_check:
            if k in el and _is_numeric(el[k]):
                total_checks += 1
                val = float(el[k])
                # Use epsilon-based check to avoid floating point precision issues with modulo
                snapped = round(val / grid_size) * grid_size
                dist = abs(val - snapped)
                if dist > 1e-5:
                    failed_grid_checks += 1
                    if dist > 2:  # Only complain if visibly off-grid
                        grid_issues.append(f"Element '{el_id}' {k}={val} is not aligned to {grid_size}px grid")
                        
    # Check alignment (almost aligned but not quite)
    for axis in ["x", "y"]:
        pts = [(float(e[axis]), e.get("id", "")) for e in shapes if axis in e and _is_numeric(e[axis])]
        pts.sort()
        for i in range(len(pts)-1):
            val1, id1 = pts[i]
            val2, id2 = pts[i+1]
            diff = val2 - val1
            if 0.5 < diff <= align_tolerance:
                align_issues.append(f"Elements '{id1}' and '{id2}' are misaligned in {axis.upper()} by {diff:.1f}px")
                
    # Calculate score
    # Start with 1.0. Deduct 0.1 for each major category of issue, max 0.0
    penalty = 0.0
    
    if total_checks > 0:
        grid_fail_ratio = failed_grid_checks / total_checks
        penalty += min(0.4, grid_fail_ratio)
        
    penalty += min(0.4, len(align_issues) * 0.1)
    
    score = max(0.0, 1.0 - penalty)
    
    return LintReport(
        score=score,
        alignment_issues=align_issues,
        grid_issues=grid_issues,
        overlap_issues=overlap_issues
    )

def score_geometry(spec: Dict[str, Any]) -> float:
    """Shortcut function to return just the 0-1 geometric score."""
    return lint_spec(spec).score
