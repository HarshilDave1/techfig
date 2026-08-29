"""Boolean geometry for filled diagram shapes.

Converts primitive shapes (circle, ellipse, box, diamond, triangle,
polygon) to occupancy, combines them with union / difference /
intersection, and extracts closed rings via marching squares.

No extra dependencies beyond numpy (already required via matplotlib).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

Point = Tuple[float, float]
Ring = List[Point]
Shape = Dict[str, Any]

_OPS = {
    "union": "union",
    "or": "union",
    "difference": "difference",
    "cut": "difference",
    "subtract": "difference",
    "intersection": "intersection",
    "intersect": "intersection",
    "and": "intersection",
}


def shape_bounds(el: Shape) -> Tuple[float, float, float, float]:
    """Return (xmin, ymin, xmax, ymax) in canvas coordinates."""
    t = el.get("type")
    if t == "circle":
        x, y, r = float(el.get("x", 0)), float(el.get("y", 0)), float(el.get("r", 40))
        return x - r, y - r, x + r, y + r
    if t == "ellipse":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        rx, ry = float(el.get("rx", 50)), float(el.get("ry", 30))
        return x - rx, y - ry, x + rx, y + ry
    if t in ("box", "diamond", "triangle"):
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("w", 100)), float(el.get("h", 60))
        return x - w / 2, y - h / 2, x + w / 2, y + h / 2
    if t in ("polygon", "pen", "path"):
        pts = list(el.get("points") or ())
        if not pts:
            raise ValueError(f"{t} has no points")
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    raise ValueError(f"unsupported shape type '{t}' for boolean bounds")


def _triangle_points(el: Shape) -> List[Point]:
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    w, h = float(el.get("w", 80)), float(el.get("h", 70))
    hw, hh = w / 2, h / 2
    direction = el.get("direction", "up")
    pts = {
        "up": [(x, y - hh), (x - hw, y + hh), (x + hw, y + hh)],
        "down": [(x, y + hh), (x - hw, y - hh), (x + hw, y - hh)],
        "left": [(x - hw, y), (x + hw, y - hh), (x + hw, y + hh)],
        "right": [(x + hw, y), (x - hw, y - hh), (x - hw, y + hh)],
    }
    return pts.get(direction, pts["up"])


def _diamond_points(el: Shape) -> List[Point]:
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    w, h = float(el.get("w", 100)), float(el.get("h", 80))
    return [(x, y - h / 2), (x + w / 2, y), (x, y + h / 2), (x - w / 2, y)]


def _point_in_poly(px: float, py: float, pts: Sequence[Sequence[float]]) -> bool:
    """Even-odd point-in-polygon."""
    n = len(pts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(pts[i][0]), float(pts[i][1])
        xj, yj = float(pts[j][0]), float(pts[j][1])
        if (yi > py) != (yj > py):
            xint = (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi
            if px < xint:
                inside = not inside
        j = i
    return inside


def _contains(el: Shape, px: float, py: float) -> bool:
    t = el.get("type")
    if t == "circle":
        dx = px - float(el.get("x", 0))
        dy = py - float(el.get("y", 0))
        r = float(el.get("r", 40))
        return dx * dx + dy * dy <= r * r
    if t == "ellipse":
        rx = float(el.get("rx", 50)) or 1e-12
        ry = float(el.get("ry", 30)) or 1e-12
        dx = (px - float(el.get("x", 0))) / rx
        dy = (py - float(el.get("y", 0))) / ry
        return dx * dx + dy * dy <= 1.0
    if t == "box":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("w", 100)), float(el.get("h", 60))
        return abs(px - x) <= w / 2 and abs(py - y) <= h / 2
    if t == "diamond":
        return _point_in_poly(px, py, _diamond_points(el))
    if t == "triangle":
        return _point_in_poly(px, py, _triangle_points(el))
    if t in ("polygon", "pen", "path"):
        pts = el.get("points") or []
        if len(pts) < 3:
            return False
        inside = _point_in_poly(px, py, pts)
        for hole in el.get("holes") or ():
            if _point_in_poly(px, py, hole):
                inside = False
                break
        return inside
    raise ValueError(f"unsupported shape type '{t}' for boolean raster")


def _combine(masks: List[np.ndarray], op: str) -> np.ndarray:
    if not masks:
        raise ValueError("boolean_paths requires at least one shape")
    acc = masks[0].copy()
    for m in masks[1:]:
        if op == "union":
            acc |= m
        elif op == "difference":
            acc &= ~m
        else:
            acc &= m
    return acc


def _edge_point(edge: str, i: int, j: int, ox: float, oy: float, cell: float) -> Point:
    """Midpoint of a cell edge in world coordinates.

    Cell (i, j) has sample corners:
      TL (j, i), TR (j+1, i), BL (j, i+1), BR (j+1, i+1)
    """
    if edge == "top":
        return (ox + (j + 0.5) * cell, oy + i * cell)
    if edge == "right":
        return (ox + (j + 1) * cell, oy + (i + 0.5) * cell)
    if edge == "bottom":
        return (ox + (j + 0.5) * cell, oy + (i + 1) * cell)
    if edge == "left":
        return (ox + j * cell, oy + (i + 0.5) * cell)
    raise ValueError(edge)


# case = TL*8 + TR*4 + BR*2 + BL*1  → directed (start, end) edge pairs
# Interior is kept on the left when walking start→end (y-down canvas).
_MS_CASES: Dict[int, List[Tuple[str, str]]] = {
    0: [],
    1: [("left", "bottom")],
    2: [("bottom", "right")],
    3: [("left", "right")],
    4: [("right", "top")],
    5: [("left", "top"), ("bottom", "right")],
    6: [("bottom", "top")],
    7: [("left", "top")],
    8: [("top", "left")],
    9: [("top", "bottom")],
    10: [("top", "right"), ("left", "bottom")],
    11: [("top", "right")],
    12: [("right", "left")],
    13: [("right", "bottom")],
    14: [("bottom", "left")],
    15: [],
}


def _key(p: Point) -> Tuple[int, int]:
    return (round(p[0] * 1000), round(p[1] * 1000))


def _marching_squares(grid: np.ndarray, ox: float, oy: float, cell: float) -> List[Ring]:
    """Extract closed isolines of a binary occupancy grid."""
    ny, nx = grid.shape
    graph: Dict[Tuple[int, int], List[Point]] = {}
    lookup: Dict[Tuple[int, int], Point] = {}

    for i in range(ny - 1):
        for j in range(nx - 1):
            tl = 1 if grid[i, j] else 0
            tr = 1 if grid[i, j + 1] else 0
            br = 1 if grid[i + 1, j + 1] else 0
            bl = 1 if grid[i + 1, j] else 0
            case = (tl << 3) | (tr << 2) | (br << 1) | bl
            for start_e, end_e in _MS_CASES[case]:
                a = _edge_point(start_e, i, j, ox, oy, cell)
                b = _edge_point(end_e, i, j, ox, oy, cell)
                ka, kb = _key(a), _key(b)
                lookup[ka] = a
                lookup[kb] = b
                graph.setdefault(ka, []).append(b)

    rings: List[Ring] = []
    unused = {k: list(v) for k, v in graph.items()}
    while unused:
        start_k = next(iter(unused))
        start = lookup[start_k]
        ring: Ring = [start]
        cur_k = start_k
        guard = 0
        max_steps = (ny * nx * 4) + 8
        while guard < max_steps:
            guard += 1
            dests = unused.pop(cur_k, [])
            if not dests:
                break
            nxt = dests.pop()
            if dests:
                unused[cur_k] = dests
            if _key(nxt) == start_k:
                break
            ring.append(nxt)
            cur_k = _key(nxt)
        if len(ring) >= 3:
            rings.append(ring)

    rings.sort(key=_ring_area, reverse=True)
    return [_chaikin(r, iterations=2) for r in rings]


def _chaikin(ring: Ring, iterations: int = 2) -> Ring:
    """Corner-cutting smoother for closed marching-squares rings."""
    pts = list(ring)
    if len(pts) < 4:
        return pts
    for _ in range(max(iterations, 0)):
        nxt: Ring = []
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            nxt.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            nxt.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        pts = nxt
    return pts


def _ring_area(ring: Ring) -> float:
    if len(ring) < 3:
        return 0.0
    acc = 0.0
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % len(ring)]
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5


def boolean_paths(
    shapes: Sequence[Shape],
    op: str = "union",
    resolution: float = 1.5,
) -> List[Ring]:
    """Combine ``shapes`` with ``op`` and return closed rings.

    The largest ring is first (outer). Subsequent rings are holes or
    additional disjoint outers — emit them all with even-odd fill.

    ``op``: ``union`` / ``difference`` (alias ``cut``) / ``intersection``.
    """
    if not shapes:
        raise ValueError("boolean_paths requires at least one shape")
    canonical = _OPS.get(str(op).lower())
    if canonical is None:
        raise ValueError(f"unknown boolean op '{op}' (use union, difference/cut, intersection)")

    bounds = [shape_bounds(s) for s in shapes]
    xmin = min(b[0] for b in bounds) - 4.0
    ymin = min(b[1] for b in bounds) - 4.0
    xmax = max(b[2] for b in bounds) + 4.0
    ymax = max(b[3] for b in bounds) + 4.0
    cell = max(float(resolution), 0.5)

    nx = max(int(math.ceil((xmax - xmin) / cell)) + 1, 4)
    ny = max(int(math.ceil((ymax - ymin) / cell)) + 1, 4)
    xs = xmin + np.arange(nx) * cell
    ys = ymin + np.arange(ny) * cell
    XX, YY = np.meshgrid(xs, ys)

    masks: List[np.ndarray] = []
    for s in shapes:
        # Vectorized fast paths for the common primitives; fall back to
        # point-wise for polygons / diamonds / triangles.
        t = s.get("type")
        if t == "circle":
            dx = XX - float(s.get("x", 0))
            dy = YY - float(s.get("y", 0))
            r = float(s.get("r", 40))
            masks.append((dx * dx + dy * dy) <= r * r)
        elif t == "ellipse":
            rx = float(s.get("rx", 50)) or 1e-12
            ry = float(s.get("ry", 30)) or 1e-12
            dx = (XX - float(s.get("x", 0))) / rx
            dy = (YY - float(s.get("y", 0))) / ry
            masks.append((dx * dx + dy * dy) <= 1.0)
        elif t == "box":
            x, y = float(s.get("x", 0)), float(s.get("y", 0))
            w, h = float(s.get("w", 100)), float(s.get("h", 60))
            masks.append((np.abs(XX - x) <= w / 2) & (np.abs(YY - y) <= h / 2))
        else:
            flat = np.zeros((ny, nx), dtype=bool)
            for i in range(ny):
                for j in range(nx):
                    flat[i, j] = _contains(s, float(XX[i, j]), float(YY[i, j]))
            masks.append(flat)

    occupancy = _combine(masks, canonical)
    if not occupancy.any():
        return []
    return _marching_squares(occupancy, xmin, ymin, cell)
