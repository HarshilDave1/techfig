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


def align_rows_and_cols(spec: Dict[str, Any], tolerance: float = 30.0) -> Dict[str, Any]:
    """Force elements that are almost aligned by Y (rows) or X (columns) to align exactly.
    
    Groups elements whose X or Y differ by <= tolerance, and averages them, 
    setting all elements in the group to the exact same value.
    """
    new_spec = copy.deepcopy(spec)
    elements = new_spec.get("elements", [])
    
    if not elements:
        return new_spec
        
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
        
        # average and apply
        for group in groups:
            if len(group) > 1:
                avg = sum(float(e[axis]) for e in group) / len(group)
                # optionally round to nearest int if sensible
                avg = round(avg, 2)
                for e in group:
                    e[axis] = avg
                    
    align_axis("x")
    align_axis("y")

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
                
    # Check overlaps between shapes (and text)
    bboxes = []
    for el in all_els:
        el_type = el.get("type", "")
        el_id = el.get("id", f"{el_type}_no_id")
        if el_type == "line":
            continue
        if "x" not in el or "y" not in el:
            continue
        try:
            x = float(el["x"])
            y = float(el["y"])
            if el_type in ("box", "diamond", "triangle"):
                w = float(el.get("w", 100))
                h = float(el.get("h", 60))
            elif el_type == "circle":
                r = float(el.get("r", 40))
                w = h = r * 2
            elif el_type == "ellipse":
                rx = float(el.get("rx", 50))
                ry = float(el.get("ry", 30))
                w = rx * 2
                h = ry * 2
            elif el_type == "text":
                text = el.get("text", "")
                font_size = float(el.get("font_size", 14))
                w = len(text) * font_size * 0.6
                h = font_size
            else:
                continue
            bboxes.append((el_id, x - w / 2, y - h / 2, x + w / 2, y + h / 2))
        except (ValueError, TypeError):
            continue

    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            id1, xmin1, ymin1, xmax1, ymax1 = bboxes[i]
            id2, xmin2, ymin2, xmax2, ymax2 = bboxes[j]
            if not (xmax1 <= xmin2 or xmax2 <= xmin1 or ymax1 <= ymin2 or ymax2 <= ymin1):
                overlap_issues.append(f"Elements '{id1}' and '{id2}' overlap")

    # Calculate score
    # Start with 1.0. Deduct 0.1 for each major category of issue, max 0.0
    penalty = 0.0
    
    if total_checks > 0:
        grid_fail_ratio = failed_grid_checks / total_checks
        penalty += min(0.4, grid_fail_ratio)
        
    penalty += min(0.4, len(align_issues) * 0.1)
    penalty += min(0.2, len(overlap_issues) * 0.05)
    
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
