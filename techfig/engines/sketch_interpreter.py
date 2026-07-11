"""Sketch interpreter — bridge between LLM vision and the diagram engine.

This module provides:
1. A JSON schema for structured diagram descriptions
2. System prompts for LLM vision analysis (initial + refinement)
3. Functions to validate, render, and iteratively refine diagram specs

The two-step workflow:
    Step 1: LLM sees the image + SKETCH_PROMPT → outputs JSON matching DIAGRAM_SCHEMA
    Step 2: render_from_spec(json_spec, output_path) → clean editable SVG

The agentic refinement loop (optional):
    Pass 1: LLM + SKETCH_PROMPT → initial JSON spec → render SVG
    Pass 2+: LLM + REFINE_PROMPT + original image + current SVG → refined JSON → re-render
    Repeat until quality is acceptable or max iterations reached.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from techfig.engines.diagrams import create_diagram



# ── JSON Schema for diagram specs ─────────────────────────────────────────

DIAGRAM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "canvas": {
            "type": "object",
            "properties": {
                "width": {"type": "integer", "default": 1200},
                "height": {"type": "integer", "default": 800},
            },
        },
        "style": {
            "type": "object",
            "description": "Optional style overrides",
            "properties": {
                "font_family": {"type": "string"},
                "font_size": {"type": "integer"},
                "stroke_width": {"type": "number"},
                "colors": {
                    "type": "object",
                    "properties": {
                        "primary": {"type": "string"},
                        "secondary": {"type": "string"},
                        "accent": {"type": "string"},
                        "background": {"type": "string"},
                        "text": {"type": "string"},
                    },
                },
            },
        },
        "elements": {
            "type": "array",
            "description": "List of visual elements on the canvas",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["box", "circle", "diamond", "ellipse", "triangle", "text", "textblock", "line", "arrow", "path", "callout", "legend"],
                    },
                    "id": {"type": "string", "description": "Unique ID for connections"},
                    "text": {"type": "string"},
                    "x": {"type": "number"}, "y": {"type": "number"},
                    "w": {"type": "number"}, "h": {"type": "number"},
                    "r": {"type": "number"}, "rx": {"type": "number"}, "ry": {"type": "number"},
                    "x1": {"type": "number"}, "y1": {"type": "number"},
                    "x2": {"type": "number"}, "y2": {"type": "number"},
                    "color": {"type": "string"},
                    "stroke_color": {"type": "string"},
                    "curve": {"type": "number", "description": "Arrow curvature offset (quadratic Bezier)"},
                    "points": {
                        "type": "array",
                        "description": "Path points: list of [x,y] or [x,y,cmd] where cmd is M/L/Q/C",
                        "items": {"type": "array", "items": {"type": ["number", "string"]}},
                    },
                    "closed": {"type": "boolean", "description": "Close path with Z (outline)"},
                    "arrowhead": {"type": "string", "enum": ["none", "end", "start", "both"]},
                    "anchor_x": {"type": "number"},
                    "anchor_y": {"type": "number"},
                    "anchor": {"type": "string"},
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                    "align": {"type": "string", "enum": ["left", "center", "right"]},
                    "padding": {"type": "number"},
                    "line_height": {"type": "number"},
                    "font_size": {"type": "number"},
                    "stroke_dash": {"type": "string"},
                    "fill_opacity": {"type": "number"},
                    "rotation": {"type": "number"},
                    "title": {"type": "string", "description": "Legend panel heading"},
                    "swatch_shape": {"type": "string", "enum": ["rect", "circle"], "description": "Legend default swatch shape"},
                    "entries": {
                        "type": "array",
                        "description": "Legend rows: list of {label, color, swatch_shape?}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "color": {"type": "string"},
                                "swatch_shape": {"type": "string", "enum": ["rect", "circle"]},
                            },
                            "required": ["label", "color"],
                        },
                    },
                },
                "required": ["type"],
            },
        },
        "connections": {
            "type": "array",
            "description": "Lines/arrows between elements (referenced by id)",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "label": {"type": "string"},
                    "style": {"type": "string", "enum": ["arrow", "line"]},
                    "route": {"type": "string", "enum": ["straight", "orthogonal"]},
                    "color": {"type": "string"},
                    "stroke_dash": {"type": "string"},
                },
                "required": ["from", "to"],
            },
        },
    },
    "required": ["elements"],
}


# ── System prompt for INITIAL analysis ────────────────────────────────────

SKETCH_PROMPT = """\
You are a diagram reconstruction assistant. The user will show you an image \
of a diagram, schematic, or technical figure. Your job is to analyze the image \
and output a JSON specification that recreates it using clean geometric primitives.

## Available element types

> **Note:** `arrow` and `path` below are *standalone* elements placed by absolute coordinates. Use the `connections` array (below) for arrows/lines that link two named element ids.

| type | required fields | optional fields | notes |
|------|----------------|-----------------|-------|
| box | id, x, y | w, h, text, color, stroke_color, fill_opacity, stroke_dash, rotation | Rectangle (rounded corners). Default w=100, h=60 |
| circle | id, x, y | r, text, color, stroke_color, fill_opacity, stroke_dash | Circle. Default r=40 |
| ellipse | id, x, y | rx, ry, text, color, stroke_color, fill_opacity, stroke_dash, rotation | Ellipse/oval. Good for lenses, ovals |
| diamond | id, x, y | w, h, text, color, stroke_color, fill_opacity | Diamond/decision node |
| triangle | id, x, y | w, h, text, color, stroke_color, direction(up/down/left/right), fill_opacity | Triangle. Default 60×60 |
| text | x, y, text | id, font_size, color, rotation | Free-floating label (no shape). Use for annotations |
| textblock | x, y, w, h, text | id, align, padding, line_height, font_size, color, fill_opacity, stroke_dash, rotation | Multi-line wrapped text inside a panel background |
| line | x1, y1, x2, y2 | text, color, stroke_dash | Plain line. stroke_dash="5,3" for dashed |
| arrow | x1, y1, x2, y2 | text, color, stroke_dash, curve | Free-form arrow with arrowhead at (x2,y2). `curve` is a perpendicular offset in px for a quadratic Bezier bow (positive bows right of travel direction, negative left). Use for annotations/leader lines that don't anchor to a shape id |
| path | points | text, color, stroke_dash, closed, arrowhead, fill_opacity | Multi-segment polyline/curve. `points` is a list of [x,y] or [x,y,cmd] where cmd is "M","L","Q" (next entry is control point), or "C" (next two entries are control points). `closed`: true closes the outline (Z). `arrowhead`: "none" (default), "end", "start", or "both". Use for wavy lines, brackets, curved annotations, custom outlines |
| callout | x, y, text | anchor_x, anchor_y (or anchor=element id), id, color, font_size, stroke_dash, rotation | Anchored label with a leader line from the anchor point to the label, plus a small anchor dot. Use to annotate a specific point or element. If `anchor` is an element id, the leader attaches to that element's boundary; if `anchor_x`/`anchor_y` are given they pin the leader to that coordinate. |
| legend | x, y | w, h, id, title, color, entries, swatch_shape, stroke_dash, fill_opacity, rotation | Bordered panel with swatch+label rows. `entries` is a list of {label, color, swatch_shape?}. `swatch_shape` defaults to "rect" (or "circle"). Good for color keys |

## Connections (arrows and lines between elements)

Reference elements by their `id`. Each connection has:
- `from`, `to`: element IDs (required)
- `style`: "arrow" (with arrowhead, default) or "line" (plain)
- `route`: "straight" (default) or "orthogonal" (right-angle path)
- `label`: optional text along the connection
- `stroke_dash`: "5,3" for dashed connections
- `color`: hex color for the line/arrow

## Coordinate system

- Origin (0,0) is at the CENTER of the canvas
- x increases rightward, y increases downward
- Default canvas is 1200×800
- Position elements relative to center

## CRITICAL: Styling rules

1. **Always set explicit `fill_opacity`** on every shape:
   - Solid filled shapes: `fill_opacity: 1.0`
   - Semi-transparent: `fill_opacity: 0.3` to `0.7`
   - Outline-only (no fill): `fill_opacity: 0.0`
   - Light fill: `fill_opacity: 0.1` to `0.2`
2. **Always set explicit `color`** using hex (e.g. "#0072B2", "#FF6B6B", "#009E73")
   - Match the fill colors you see in the original image
   - Use distinct colors for different types of shapes
3. **When the outline should differ from the fill, set `stroke_color` explicitly**
   - The renderer uses a dark default stroke when `stroke_color` is omitted
   - Use a visible outline color that contrasts with the fill
4. **Size shapes appropriately:**
   - Make shapes large enough to be readable (min w=60, h=40 for boxes)
   - Match proportions from the original image
   - Triangles, circles should be sized to match visually

## Rules

1. Every shape that needs connections MUST have a unique `id`
2. Use `text` elements for labels that float near shapes
3. For dashed borders, use stroke_dash="5,3" or "10,5,2,5" (dash-dot)
4. Approximate the layout from the image — use center-relative coordinates
5. Match colors, sizes, opacity, and proportions from the original
6. Prefer simple shapes over complex paths

## Output format

Return ONLY valid JSON (no markdown fences, no explanation):

{
  "canvas": {"width": 1200, "height": 800},
  "elements": [...],
  "connections": [...]
}

IMPORTANT: Every element MUST include a "type" field matching one of the types listed above (e.g. "box", "circle", "text", "line", "arrow", "path", "callout", "diamond", "ellipse", "triangle", "legend").
Example element with type: {"type": "box", "id": "mybox", "x": 0, "y": 0, "w": 100, "h": 60, "text": "Box", "color": "#0072B2", "fill_opacity": 1.0}
Example arrow: {"type": "arrow", "x1": -50, "y1": 0, "x2": 50, "y2": 0, "text": "flow", "color": "#333"}
Example path: {"type": "path", "points": [[0,0], [50,0,"Q"], [75,-20], [100,0]], "closed": false, "arrowhead": "end"}
Do NOT omit the "type" field from any element.
"""


# ── Refinement prompt for pass 2+ ────────────────────────────────────────

REFINE_PROMPT = """\
You are refining a diagram reconstruction. You have the ORIGINAL image \
and the CURRENT rendered SVG side by side.

## Current JSON spec

```json
{current_spec}
```

## Your task

Compare the current rendering with the original image and fix any issues. \
Common problems to look for:

1. **Wrong colors** — shapes that should be blue are red, etc. Fix with explicit hex `color` values
2. **Wrong opacity** — shapes that look solid but should be transparent, or vice versa. Fix `fill_opacity`
3. **Wrong sizes** — shapes too small/large. Adjust w, h, r, rx, ry
4. **Wrong positions** — shapes overlapping or too far apart. Adjust x, y coordinates
5. **Missing elements** — labels, lines, or shapes present in original but missing
6. **Extra elements** — shapes in the reconstruction that don't exist in the original
7. **Wrong text** — labels that don't match the original
8. **Wrong connections** — arrows/lines going to wrong targets, missing arrowheads
9. **Wrong line style** — solid lines that should be dashed, or vice versa
10. **Wrong shape type** — using a box where the original has a circle, etc.

## Rules

- Output the COMPLETE updated JSON spec (not a diff)
- Keep all existing element IDs stable (don't rename them)
- You may add or remove elements as needed
- Return ONLY valid JSON (no markdown fences, no explanation)"""


# ── Functions ─────────────────────────────────────────────────────────────

def get_sketch_prompt() -> str:
    """Return the system prompt for initial LLM vision analysis."""
    return SKETCH_PROMPT


def get_refine_prompt(current_spec: Dict[str, Any]) -> str:
    """Return the refinement prompt with the current spec embedded.

    This prompt is used in pass 2+ of the agentic refinement loop.
    The caller should provide both the original image and the current
    rendered SVG alongside this prompt to the LLM.

    Args:
        current_spec: The current diagram specification dict.

    Returns:
        The formatted refinement prompt string.
    """
    spec_json = json.dumps(current_spec, indent=2)
    return REFINE_PROMPT.replace("{current_spec}", spec_json)


def get_diagram_schema() -> Dict[str, Any]:
    """Return the JSON schema for diagram specifications."""
    return DIAGRAM_SCHEMA


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """Validate a diagram spec and return human-readable issues.

    The validation is intentionally lightweight: it catches the schema
    mistakes covered by the test suite and the CLI pipeline without
    re-implementing a full JSON-schema validator.
    """
    issues: List[str] = []
    if not isinstance(spec, dict):
        return ["spec must be a mapping"]

    elements = spec.get("elements")
    if not isinstance(elements, list) or not elements:
        issues.append("missing elements")
        return issues

    known_ids = set()
    allowed_types = set(DIAGRAM_SCHEMA["properties"]["elements"]["items"]["properties"]["type"]["enum"])
    for idx, el in enumerate(elements):
        if not isinstance(el, dict):
            issues.append(f"element {idx}: must be an object")
            continue

        el_type = el.get("type")
        if not el_type:
            issues.append(f"element {idx}: missing type")
            continue

        if el_type not in allowed_types:
            issues.append(f"element {idx}: unknown type '{el_type}'")

        el_id = el.get("id")
        if el_id:
            if el_id in known_ids:
                issues.append(f"element {idx}: duplicate id '{el_id}'")
            known_ids.add(el_id)

        if el_type in {"box", "circle", "diamond", "ellipse", "triangle", "text"}:
            if "x" not in el or "y" not in el:
                issues.append(f"element {idx}: missing x or y")
        if el_type == "text" and not el.get("text"):
            issues.append(f"element {idx}: missing text")
        if el_type == "line" and any(k not in el for k in ("x1", "y1", "x2", "y2")):
            issues.append(f"element {idx}: missing line endpoints")
        if el_type == "arrow" and any(k not in el for k in ("x1", "y1", "x2", "y2")):
            issues.append(f"element {idx}: missing arrow endpoints")
        if el_type == "path" and "points" not in el:
            issues.append(f"element {idx}: missing path points")
        if el_type == "callout":
            if not el.get("text"):
                issues.append(f"element {idx}: missing text")
            if "anchor_x" in el and "anchor_y" not in el:
                issues.append(f"element {idx}: anchor_x provided without anchor_y")
            if "anchor_y" in el and "anchor_x" not in el:
                issues.append(f"element {idx}: anchor_y provided without anchor_x")

    for idx, conn in enumerate(spec.get("connections", []) or []):
        if not isinstance(conn, dict):
            issues.append(f"connection {idx}: must be an object")
            continue
        from_id = conn.get("from")
        to_id = conn.get("to")
        if not from_id or not to_id:
            issues.append(f"connection {idx}: missing from/to")
            continue
        if from_id not in known_ids or to_id not in known_ids:
            issues.append(f"connection {idx}: unknown id reference")

    return issues


def render_from_spec(
    spec: Dict[str, Any],
    output_path: str,
    style_config: Dict[str, Any] | None = None,
) -> str:
    """Render a diagram from a validated JSON spec.

    Args:
        spec: Diagram specification dict (canvas, elements, connections).
        output_path: Where to save the SVG.
        style_config: Optional style overrides. Merged with spec's own style.

    Returns:
        Absolute path to the generated SVG.

    Raises:
        ValueError: If spec validation fails.
    """
    issues = validate_spec(spec)
    if issues:
        raise ValueError("Invalid diagram spec:\n" + "\n".join(f"  - {i}" for i in issues))

    canvas = spec.get("canvas", {})
    width = canvas.get("width", 1200)
    height = canvas.get("height", 800)

    # Merge style: spec style < explicit style_config
    merged_style = spec.get("style", {})
    if style_config:
        merged_style.update(style_config)

    return create_diagram(
        elements=spec["elements"],
        connections=spec.get("connections", []),
        output_path=output_path,
        width=width,
        height=height,
        style_config=merged_style or None,
    )


def render_from_json(
    json_path: str,
    output_path: str,
    style_config: Dict[str, Any] | None = None,
) -> str:
    """Load a diagram spec from a JSON file and render it.

    Args:
        json_path: Path to JSON file containing diagram spec.
        output_path: Where to save the SVG.
        style_config: Optional style overrides.

    Returns:
        Absolute path to the generated SVG.
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {json_path}")

    with open(path) as f:
        spec = json.load(f)

    return render_from_spec(spec, output_path, style_config)


def format_refinement_context(
    current_spec: Dict[str, Any],
    issues: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Package the current state for an agentic refinement pass.

    Returns a dict that the caller can use to construct the LLM prompt:
    - refine_prompt: The formatted refinement prompt text
    - current_spec: The current spec as a dict
    - validation_issues: Any spec validation issues

    Args:
        current_spec: The current diagram specification.
        issues: Optional list of known visual issues to fix.

    Returns:
        Context dict for the refinement pass.
    """
    return {
        "refine_prompt": get_refine_prompt(current_spec),
        "current_spec": current_spec,
        "validation_issues": validate_spec(current_spec),
        "known_issues": issues or [],
        "instructions": (
            "Show the LLM: (1) the original image, "
            "(2) the current rendered SVG, and (3) this refine_prompt. "
            "The LLM returns an updated JSON spec. "
            "Render again with render_from_spec()."
        ),
    }


def auto_refine(
    initial_spec: Dict[str, Any],
    output_dir: str,
    reference_image_path: Optional[str] = None,
    max_rounds: int = 5,
    model: str = "anthropic/claude-3-5-sonnet-20241022",
) -> Dict[str, Any]:
    """Run an autonomous autoresearch loop to iteratively improve a diagram spec.
    
    Uses deterministic geo-linter scoring (no LLM needed for critique).
    Optionally uses an LLM for mutation if a model is provided.

    Args:
        initial_spec: The starting JSON spec.
        output_dir: Directory to save SVG iterations and log.
        reference_image_path: Optional original image (unused in deterministic mode).
        max_rounds: Maximum number of mutation rounds.
        model: LLM model to use for mutations. If empty string, uses rule-based mutation.
        
    Returns:
        The best JSON spec found.
    """
    import os
    import copy
    from techfig.engines.autoresearch import critique_report
    from techfig.engines.geo_linter import snap_to_grid, align_rows_and_cols
    from litellm import completion as litellm_completion

    program_text = """You are an autonomous diagram improvement agent.

Your goal is to maximize the geometric and aesthetic quality score of a
diagram specification. Modify only the JSON diagram specification. Make one
targeted fix per round. Prioritize layout fixes when geometric score is low;
prioritize colors, opacity, and shape choices when aesthetic score is low. If
the previous mutation was rejected, try a different approach.
"""

    best_spec = copy.deepcopy(initial_spec)
    svg_path = os.path.join(output_dir, "gen_0.svg")
    report = critique_report(best_spec, svg_path)
    best_score = report["score"]
    last_feedback = "; ".join(report["issues"] + report["suggestions"])

    # Write experiment log
    log_data = [{"generation": 0, "score": best_score, "kept": True, "svg_path": svg_path}]

    print(f"  Gen 0 | Geo score={best_score:.3f} | ★ BASELINE")

    for gen in range(1, max_rounds + 1):
        try:
            if model:
                # LLM-based mutation
                user_prompt = f"""\
Here is the current diagram spec:
```json
{json.dumps(best_spec, indent=2)}
```

Feedback on this spec:
{last_feedback}

Output ONLY the complete, updated valid JSON spec matching the required schema. Do not include markdown fences if possible, just the raw JSON.
"""
                messages = [
                    {"role": "system", "content": program_text},
                    {"role": "user", "content": user_prompt}
                ]
                response = litellm_completion(
                    model=model,
                    messages=messages,
                    temperature=0.7
                )
                res_text = response.choices[0].message.content

                from techfig.engines.aesthetic_critic import extract_json_from_response
                try:
                    candidate = extract_json_from_response(res_text)
                except Exception as e:
                    print(f"  Gen {gen} | Failed to parse LLM mutator output: {e}")
                    continue
            else:
                # Rule-based mutation
                candidate = snap_to_grid(best_spec, grid_size=10.0)
                candidate = align_rows_and_cols(candidate, tolerance=25.0)

            c_svg_path = os.path.join(output_dir, f"gen_{gen}.svg")
            c_report = critique_report(candidate, c_svg_path)
            c_score = c_report["score"]

            kept = c_score > best_score
            if kept:
                best_spec = candidate
                best_score = c_score
                last_feedback = "; ".join(c_report["issues"] + c_report["suggestions"])
                mark = "✓ KEPT"
            else:
                last_feedback = (
                    f"PREVIOUS MUTATION REJECTED (Score {c_score:.3f} not > {best_score:.3f}). "
                    f"Issues: {'; '.join(c_report['issues'])}. Try a DIFFERENT approach."
                )
                mark = "✗ REJECT"

            log_data.append({"generation": gen, "score": round(c_score, 4), "kept": kept, "svg_path": c_svg_path})
            print(f"  Gen {gen} | Geo score={c_score:.3f} | {mark}")

        except Exception as e:
            print(f"  Gen {gen} | ERROR: {e}")

    # Write experiment log
    log_path = os.path.join(output_dir, "experiment_log.json")
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)

    print(f"\n  Best score: {best_score:.3f}")
    return best_spec


def sketch_to_diagram(
    image_path: str,
    output_path: str,
    model: str = "gemini/gemini-2.5-pro",
    auto_refine_rounds: int = 0,
) -> str:
    """End-to-end command: take an image, use a Vision LLM to get a JSON spec, and render it.

    Args:
        image_path: Path to the input image (sketch/whiteboard).
        output_path: Path to save the resulting SVG.
        model: Litellm-compatible vision model.
        auto_refine_rounds: If > 0, launches autoresearch loop to fix alignment/aesthetics.

    Returns:
        Absolute path to the final generated SVG.
    """
    import base64
    from litellm import completion
    from techfig.engines.aesthetic_critic import extract_json_from_response
    import mimetypes
    import os

    # 1. Read and encode image
    with open(image_path, "rb") as f:
        img_data = f.read()
    b64_image = base64.b64encode(img_data).decode("utf-8")
    
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"

    # 2. Call Vision LLM
    print(f"Analyzing {image_path} with {model}...")
    messages = [
        {"role": "system", "content": SKETCH_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Reconstruct this diagram into a JSON spec."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_image}"},
                },
            ],
        },
    ]

    response = completion(model=model, messages=messages)
    reply_text = response.choices[0].message.content

    # 3. Extract JSON spec
    try:
        spec = extract_json_from_response(reply_text)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON from Vision LLM response.\nModel replied: {reply_text[:200]}...\nError: {e}")

    # 4. Auto-refine if requested
    if auto_refine_rounds > 0:
        print(f"Refining output for up to {auto_refine_rounds} rounds...")
        output_dir = os.path.dirname(output_path) or "."
        spec = auto_refine(
            initial_spec=spec,
            output_dir=output_dir,
            reference_image_path=image_path,
            max_rounds=auto_refine_rounds,
            model=model,
        )

    # 5. Render
    print(f"Rendering SVG to {output_path}...")
    return render_from_spec(spec, output_path)
