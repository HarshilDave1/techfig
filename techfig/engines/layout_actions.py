"""Shape-move action space module for geometric de-collision.

This module provides tools to list shapes, detect bounding box overlaps,
enumerate valid candidate translation moves within canvas boundaries, apply
actions to produce updated specs, and generate JSON-serializable state vectors.

Termination discipline: the action space is bounded by the ``SHAPE_TYPES``
whitelist.  An element whose type is a typo or a novel/unsupported type never
enters the action space, so an empty action list must never be read as "clean".
``list_shapes``/``enumerate_actions`` warn loudly (or raise in ``strict`` mode)
when unsupported types are present, and ``layout_status`` reports shape
coverage so a caller can assert ``empty != done``.
"""

from __future__ import annotations

import copy
import warnings
from typing import Any, Dict, List, Optional, Sequence, Tuple

from techfig.engines.geo_linter import (
    _bboxes_overlap,
    _shape_bbox,
    extract_shapes,
    score_geometry,
    unsupported_elements,
    SHAPE_TYPES,
)

# Coarse-to-fine default magnitudes: a 100px correction lands in one move
# instead of five fixed 20px moves.  Largest first.
DEFAULT_MOVE_STEPS: Tuple[float, ...] = (80.0, 40.0, 20.0)


class UnsupportedShapeTypeError(ValueError):
    """Raised in strict mode when elements carry an unsupported ``type``."""


class UnsupportedShapeTypeWarning(UserWarning):
    """Warned when elements carry an unsupported ``type`` (typo / novel type)."""


def _unsupported_message(spec: Dict[str, Any], bad: List[Dict[str, Any]]) -> str:
    detail = ", ".join(
        f"elements[{b['el_index']}].type={b['type']!r}" for b in bad
    )
    return (
        f"{len(bad)} element(s) have an unsupported type and cannot enter the action "
        f"space: {detail}. Known shape types: {sorted(SHAPE_TYPES)}. "
        f"An empty shape/action list is NOT a clean layout."
    )


def list_shapes(spec: Dict[str, Any], strict: bool = False) -> List[Dict[str, Any]]:
    """List all physical shapes in the spec with bounding boxes and indices.

    Each entry contains:
      - id: element id, or a synthesized stable id (e.g. 'shape_<el_index>')
      - type: element shape type
      - bbox: (left, top, right, bottom) in center-based coordinates
      - el_index: index of the element within spec['elements']

    Elements whose ``type`` is neither a shape nor a known DIAGRAM_SCHEMA type
    (typo / novel type / missing ``type``) are *unsupported*: they are reported
    loudly because they would otherwise reduce the action space to nothing
    without any signal.  Pass ``strict=True`` to raise instead of warning.
    """
    bad = unsupported_elements(spec)
    if bad:
        msg = _unsupported_message(spec, bad)
        if strict:
            raise UnsupportedShapeTypeError(msg)
        warnings.warn(msg, UnsupportedShapeTypeWarning, stacklevel=2)

    raw_shapes = {id(el) for el in extract_shapes(spec)}
    shapes: List[Dict[str, Any]] = []
    elements = spec.get("elements", [])
    for idx, el in enumerate(elements):
        if not isinstance(el, dict):
            continue
        if id(el) in raw_shapes:
            bbox = _shape_bbox(el)
            shape_id = el.get("id") or f"shape_{idx}"
            shapes.append({
                "id": str(shape_id),
                "type": el.get("type"),
                "bbox": bbox,
                "el_index": idx,
            })
    return shapes


def layout_status(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Report whether the spec has a usable action space (empty != done).

    Returns::

        {
          "elements": <int total elements>,
          "shapes": <int movable shapes>,
          "unsupported": [{"el_index": int, "type": Any}, ...],
          "overlaps": [[id_a, id_b], ...],
          "geometry_score": <float>,
          "usable": <bool>   # True only when >= 1 movable shape exists
        }
    """
    shapes = list_shapes(spec)
    return {
        "elements": len(spec.get("elements", []) or []),
        "shapes": len(shapes),
        "unsupported": unsupported_elements(spec),
        "overlaps": [list(pair) for pair in find_overlaps(spec)],
        "geometry_score": float(score_geometry(spec)),
        "usable": len(shapes) > 0,
    }



def find_overlaps(spec: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Find all overlapping shape pairs in the spec using strict AABB overlap.

    Returns a deterministic list of (id_a, id_b) pairs in order of appearance.
    """
    shapes = list_shapes(spec)
    overlaps: List[Tuple[str, str]] = []
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            if _bboxes_overlap(shapes[i]["bbox"], shapes[j]["bbox"]):
                overlaps.append((shapes[i]["id"], shapes[j]["id"]))
    return overlaps


def enumerate_actions(
    spec: Dict[str, Any],
    step: float = 20.0,
    steps: Optional[Sequence[float]] = None,
    strict: bool = False,
) -> List[Dict[str, Any]]:
    """Enumerate candidate 4-axis translation moves for all shapes.

    Each action is a dict:
      {"shape_id": <str>, "dx": <float>, "dy": <float>, "el_index": <int>}

    Moves that would push any part of the resulting shape bounding box outside
    the canvas rect (0, 0, width, height) are excluded when canvas is present.

    ``steps`` selects coarse-first scaled moves: pass a sequence of magnitudes
    (e.g. ``DEFAULT_MOVE_STEPS = (80, 40, 20)``) and each magnitude contributes
    its own 4 axis moves, sorted largest-first, so a large correction lands in
    one move instead of N fixed 20px moves.  ``step`` is ignored when ``steps``
    is given.  Magnitudes whose move would leave the canvas are dropped
    individually, so the fine steps remain available near an edge.

    When unsupported (typo/novel) element types are present they never enter
    the action space: this function warns loudly, or raises with
    ``strict=True``, since an empty result is not a clean layout.
    """
    if steps is None:
        magnitudes: List[float] = [float(step)]
    else:
        magnitudes = [float(s) for s in steps]
        if not magnitudes:
            raise ValueError("steps must be a non-empty sequence of magnitudes")
        if any(m <= 0 for m in magnitudes):
            raise ValueError("steps magnitudes must be positive")
        # Coarse first, deduped, regardless of caller ordering.
        magnitudes = sorted(set(magnitudes), reverse=True)

    shapes = list_shapes(spec, strict=strict)
    canvas = spec.get("canvas")
    canvas_bounds: Optional[Tuple[float, float]] = None
    if isinstance(canvas, dict):
        w = canvas.get("width", canvas.get("w"))
        h = canvas.get("height", canvas.get("h"))
        if w is not None and h is not None:
            try:
                canvas_bounds = (float(w), float(h))
            except (TypeError, ValueError):
                canvas_bounds = None

    moves: List[Tuple[float, float]] = []
    for mag in magnitudes:
        moves.extend([
            (-mag, 0.0),
            (mag, 0.0),
            (0.0, -mag),
            (0.0, mag),
        ])

    actions: List[Dict[str, Any]] = []
    for shape in shapes:
        bbox = shape["bbox"]
        if bbox is None:
            continue
        left, top, right, bottom = bbox
        for dx, dy in moves:
            if canvas_bounds is not None:
                cw, ch = canvas_bounds
                nl = left + dx
                nt = top + dy
                nr = right + dx
                nb = bottom + dy
                if nl < -1e-9 or nt < -1e-9 or nr > cw + 1e-9 or nb > ch + 1e-9:
                    continue
            actions.append({
                "shape_id": shape["id"],
                "dx": dx,
                "dy": dy,
                "el_index": shape["el_index"],
            })
    return actions


def apply_action(spec: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new deep-copied spec with the target shape's center offset by dx/dy.

    The original spec is not mutated. Raises ValueError if shape_id is unknown.
    """
    shape_id = action.get("shape_id")
    if shape_id is None:
        raise ValueError("Action must contain 'shape_id'")

    new_spec = copy.deepcopy(spec)
    shapes = list_shapes(new_spec)
    target_shape = None
    for s in shapes:
        if s["id"] == str(shape_id):
            target_shape = s
            break

    if target_shape is None:
        raise ValueError(f"Unknown shape_id: {shape_id!r}")

    dx = float(action.get("dx", 0.0))
    dy = float(action.get("dy", 0.0))
    el = new_spec.get("elements", [])[target_shape["el_index"]]
    el["x"] = float(el.get("x", 0.0)) + dx
    el["y"] = float(el.get("y", 0.0)) + dy
    return new_spec


def state_vector(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a JSON-safe summary dictionary representing the figure state.

    Returns:
      {
        "canvas": {...},
        "shapes": [{"id": ..., "type": ..., "bbox": [...]}, ...],
        "overlaps": [[id_a, id_b], ...],
        "geometry_score": <float>
      }
    """
    shapes = list_shapes(spec)
    shapes_list = [
        {
            "id": s["id"],
            "type": s["type"],
            "bbox": list(s["bbox"]) if s["bbox"] is not None else None,
        }
        for s in shapes
    ]
    overlaps = [list(pair) for pair in find_overlaps(spec)]
    canvas_val = spec.get("canvas")
    canvas_dict = copy.deepcopy(canvas_val) if isinstance(canvas_val, dict) else {}
    score = float(score_geometry(spec))
    return {
        "canvas": canvas_dict,
        "shapes": shapes_list,
        "overlaps": overlaps,
        "geometry_score": score,
    }
