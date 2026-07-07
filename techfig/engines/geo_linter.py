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
    Text elements are NOT snapped — they have sub-pixel offsets that are
    intentional for label positioning, and snapping them to the same grid
    point creates label collisions.
    """
    new_spec = copy.deepcopy(spec)
    
    def snap(val):
        if not _is_numeric(val):
            return val
        return round(float(val) / grid_size) * grid_size

    keys_to_snap = ["x", "y", "w", "h", "r", "rx", "ry", "x1", "y1", "x2", "y2", "anchor_x", "anchor_y", "curve"]

    for el in new_spec.get("elements", []):
        if el.get("type") == "text":
            continue  # don't snap text labels
        for k in keys_to_snap:
            if k in el and _is_numeric(el[k]):
                el[k] = snap(el[k])
        # Snap path point coordinates too
        if el.get("type") == "path" and isinstance(el.get("points"), list):
            new_points = []
            for p in el["points"]:
                if isinstance(p, (list, tuple)):
                    new_points.append([snap(v) if i < 2 and _is_numeric(v) else v for i, v in enumerate(p)])
                else:
                    new_points.append(p)
            el["points"] = new_points

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
        # Skip text elements — force-aligning them creates label collisions
        perp = "y" if axis == "x" else "x"
        els = [e for e in elements if axis in e and _is_numeric(e[axis]) and e.get("type") != "text"]
        if not els:
            return

        els.sort(key=lambda e: float(e[axis]))

        groups = []
        current_group = [els[0]]

        for e in els[1:]:
            # Close on the target axis AND close on perpendicular axis => diagonal,
            # not a genuine row/column. Start a new group to avoid collapsing it.
            close_axis = float(e[axis]) - float(current_group[-1][axis]) <= tolerance
            prev = current_group[-1]
            close_perp = (
                perp in e and perp in prev
                and _is_numeric(e[perp]) and _is_numeric(prev[perp])
                and abs(float(e[perp]) - float(prev[perp])) <= tolerance
            )
            if close_axis and not close_perp:
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
        pass  # Simplified for now, just snapping elements

    return new_spec


def fix_text_overlaps(spec: Dict[str, Any], default_font_size: float = 14.0) -> Dict[str, Any]:
    """De-collide text labels that overlap each other.
    
    Phase 1: Groups text elements within 5px of each other and stacks them
    vertically with line spacing.
    Phase 2: Greedy pairwise de-collision — pushes any overlapping text
    bboxes down by one line height, repeating until clear.
    
    This is the deterministic fix for the most common LLM-generated spec
    problem: multi-line labels emitted as separate text elements at
    identical or near-identical coordinates.
    
    Returns a deep copy of the spec with adjusted text coordinates.
    """
    new_spec = copy.deepcopy(spec)
    elements = new_spec.get("elements", [])
    if not elements:
        return new_spec

    text_indices = [i for i, el in enumerate(elements) if el.get("type") == "text"]
    if not text_indices:
        return new_spec

    line_height = default_font_size * 1.4

    # Phase 1: cluster and stack
    CLUSTER_TOL = 5.0
    clustered: list[list[int]] = []
    assigned: set[int] = set()

    for idx, i in enumerate(text_indices):
        if i in assigned:
            continue
        el = elements[i]
        cluster = [i]
        assigned.add(i)
        x1, y1 = float(el.get("x", 0)), float(el.get("y", 0))
        for j in text_indices[idx + 1:]:
            if j in assigned:
                continue
            el2 = elements[j]
            x2, y2 = float(el2.get("x", 0)), float(el2.get("y", 0))
            if abs(x1 - x2) <= CLUSTER_TOL and abs(y1 - y2) <= CLUSTER_TOL:
                cluster.append(j)
                assigned.add(j)
        clustered.append(cluster)

    for cluster in clustered:
        if len(cluster) <= 1:
            continue
        cluster.sort()
        base_x = float(elements[cluster[0]].get("x", 0))
        base_y = float(elements[cluster[0]].get("y", 0))
        for line_idx, el_idx in enumerate(cluster):
            elements[el_idx]["y"] = base_y + line_idx * line_height
            elements[el_idx]["x"] = base_x

    # Phase 2: greedy pairwise de-collision
    def _text_bbox(el):
        x = float(el.get("x", 0))
        y = float(el.get("y", 0))
        text = el.get("text", "")
        fs = float(el.get("font_size", default_font_size))
        w = max(len(text) * fs * 0.6, 1.0)
        h = fs
        return x, y, w, h

    def _overlap(a, b, padding=2.0):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (
            ax + aw / 2 + padding <= bx - bw / 2
            or bx + bw / 2 + padding <= ax - aw / 2
            or ay + ah / 2 + padding <= by - bh / 2
            or by + bh / 2 + padding <= ay - ah / 2
        )

    MAX_ITERS = 20
    for _ in range(MAX_ITERS):
        moved = False
        text_els = [(i, elements[i]) for i in range(len(elements)) if elements[i].get("type") == "text"]
        for a in range(len(text_els)):
            for b in range(a + 1, len(text_els)):
                i_a, el_a = text_els[a]
                i_b, el_b = text_els[b]
                if _overlap(_text_bbox(el_a), _text_bbox(el_b)):
                    ay = float(el_a.get("y", 0))
                    by = float(el_b.get("y", 0))
                    if ay <= by:
                        elements[i_b]["y"] = by + line_height
                    else:
                        elements[i_a]["y"] = ay + line_height
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break

    return new_spec


def lint_spec(spec: Dict[str, Any], grid_size: float = 20.0, align_tolerance: float = 30.0) -> LintReport:
    """Analyze a spec and return a score and diagnostic issues."""
    shapes = extract_shapes(spec)
    all_els = spec.get("elements", [])
    
    align_issues = []
    grid_issues = []
    overlap_issues = []
    
    # Check grid snapping
    keys_to_check = ["x", "y", "w", "h", "x1", "y1", "x2", "y2", "r", "rx", "ry", "anchor_x", "anchor_y", "curve"]
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

        # Check path points
        if type_str == "path" and isinstance(el.get("points"), list):
            for idx, p in enumerate(el["points"]):
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    continue
                for axis_idx, axis_name in enumerate(("px", "py")):
                    v = p[axis_idx]
                    if _is_numeric(v):
                        total_checks += 1
                        val = float(v)
                        snapped = round(val / grid_size) * grid_size
                        dist = abs(val - snapped)
                        if dist > 1e-5:
                            failed_grid_checks += 1
                            if dist > 2:
                                grid_issues.append(
                                    f"Path '{el_id}' point[{idx}] {axis_name}={val} is not aligned to {grid_size}px grid"
                                )
                        
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
    text_bboxes = []  # track text-text overlaps separately for higher penalty
    for el in all_els:
        el_type = el.get("type", "")
        el_id = el.get("id", f"{el_type}_no_id_{id(el)}")
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
            entry = (el_id, x - w / 2, y - h / 2, x + w / 2, y + h / 2, el_type)
            bboxes.append(entry)
            if el_type == "text":
                text_bboxes.append(entry)
        except (ValueError, TypeError):
            continue

    text_overlap_count = 0
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            id1, xmin1, ymin1, xmax1, ymax1, type1 = bboxes[i]
            id2, xmin2, ymin2, xmax2, ymax2, type2 = bboxes[j]
            if not (xmax1 <= xmin2 or xmax2 <= xmin1 or ymax1 <= ymin2 or ymax2 <= ymin1):
                if type1 == "text" and type2 == "text":
                    text_overlap_count += 1
                    overlap_issues.append(f"Text labels '{id1}' and '{id2}' overlap (unreadable)")
                else:
                    overlap_issues.append(f"Elements '{id1}' and '{id2}' overlap")

    # Calculate score
    # Start with 1.0. Deduct for each category of issue.
    # Text-text overlaps are heavily penalized — they make labels unreadable.
    penalty = 0.0

    if total_checks > 0:
        grid_fail_ratio = failed_grid_checks / total_checks
        penalty += min(0.4, grid_fail_ratio)

    penalty += min(0.4, len(align_issues) * 0.1)
    penalty += min(0.2, (len(overlap_issues) - text_overlap_count) * 0.05)  # shape overlaps
    penalty += min(0.5, text_overlap_count * 0.15)  # text-text overlaps: up to 0.5 penalty
    
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
