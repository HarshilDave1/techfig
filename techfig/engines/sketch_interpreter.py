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
from typing import Any, Dict, List, Optional
from pathlib import Path

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
                        "enum": ["box", "circle", "diamond", "ellipse", "triangle", "text", "line"],
                    },
                    "id": {"type": "string", "description": "Unique ID for connections"},
                    "text": {"type": "string"},
                    "x": {"type": "number"}, "y": {"type": "number"},
                    "w": {"type": "number"}, "h": {"type": "number"},
                    "r": {"type": "number"},
                    "rx": {"type": "number"}, "ry": {"type": "number"},
                    "x1": {"type": "number"}, "y1": {"type": "number"},
                    "x2": {"type": "number"}, "y2": {"type": "number"},
                    "color": {"type": "string"},
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                    "font_size": {"type": "number"},
                    "stroke_dash": {"type": "string"},
                    "fill_opacity": {"type": "number"},
                    "rotation": {"type": "number"},
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

| type | required fields | optional fields | notes |
|------|----------------|-----------------|-------|
| box | id, x, y | w, h, text, color, fill_opacity, stroke_dash, rotation | Rectangle (rounded corners). Default w=100, h=60 |
| circle | id, x, y | r, text, color, fill_opacity, stroke_dash | Circle. Default r=40 |
| ellipse | id, x, y | rx, ry, text, color, fill_opacity, stroke_dash, rotation | Ellipse/oval. Good for lenses, ovals |
| diamond | id, x, y | w, h, text, color, fill_opacity | Diamond/decision node |
| triangle | id, x, y | w, h, text, color, direction(up/down/left/right), fill_opacity | Triangle. Default 60×60 |
| text | x, y, text | id, font_size, color, rotation | Free-floating label (no shape). Use for annotations |
| line | x1, y1, x2, y2 | text, color, stroke_dash | Plain line. stroke_dash="5,3" for dashed |

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
   - Match the colors you see in the original image
   - Use distinct colors for different types of shapes
3. **Size shapes appropriately:**
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
}"""


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


def validate_spec(spec: Dict[str, Any]) -> list[str]:
    """Validate a diagram spec and return a list of issues (empty = valid).

    This is a lightweight structural check — not a full JSON Schema validator.
    """
    issues: list[str] = []

    if "elements" not in spec:
        issues.append("Missing 'elements' array")
        return issues

    if not isinstance(spec["elements"], list):
        issues.append("'elements' must be a list")
        return issues

    valid_types = {"box", "circle", "diamond", "ellipse", "triangle", "text", "line"}
    ids_seen: set[str] = set()

    for i, el in enumerate(spec["elements"]):
        el_type = el.get("type")
        if el_type not in valid_types:
            issues.append(f"Element {i}: unknown type '{el_type}'")

        el_id = el.get("id")
        if el_id:
            if el_id in ids_seen:
                issues.append(f"Element {i}: duplicate id '{el_id}'")
            ids_seen.add(el_id)

        # Check position fields
        if el_type in ("box", "circle", "diamond", "ellipse", "triangle"):
            if "x" not in el or "y" not in el:
                issues.append(f"Element {i} ({el_type}): missing x or y")
            if not el_id:
                issues.append(f"Element {i} ({el_type}): shape nodes should have an id")

        elif el_type == "text":
            if "x" not in el or "y" not in el:
                issues.append(f"Element {i} (text): missing x or y")
            if not el.get("text"):
                issues.append(f"Element {i} (text): missing text content")

        elif el_type == "line":
            for coord in ("x1", "y1", "x2", "y2"):
                if coord not in el:
                    issues.append(f"Element {i} (line): missing {coord}")

    # Check connections reference valid IDs
    for i, conn in enumerate(spec.get("connections", [])):
        for key in ("from", "to"):
            ref = conn.get(key)
            if not ref:
                issues.append(f"Connection {i}: missing '{key}'")
            elif ref not in ids_seen:
                issues.append(f"Connection {i}: '{key}' references unknown id '{ref}'")

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
        raise ValueError(f"Invalid diagram spec:\n" + "\n".join(f"  - {i}" for i in issues))

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
    
    Args:
        initial_spec: The starting JSON spec.
        output_dir: Directory to save SVG iterations and log.
        reference_image_path: Optional original image to guide the aesthetic critic.
        max_rounds: Maximum number of mutation rounds.
        model: LLM model to use for mutations.
        
    Returns:
        The best JSON spec found.
    """
    from techfig.engines.autoresearch import AutoResearchLoop
    from litellm import completion
    import os

    # Load the mutator program instructions
    program_path = os.path.join(os.path.dirname(__file__), "program.md")
    with open(program_path, "r") as f:
        program_text = f.read()

    def mutator_fn(current_spec: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        """The LLM agent that mutates the spec based on feedback."""
        
        user_prompt = f"""\
Here is the current diagram spec:
```json
{json.dumps(current_spec, indent=2)}
```

Feedback on this spec:
{feedback}

Output ONLY the complete, updated valid JSON spec matching the required schema. Do not include markdown fences if possible, just the raw JSON.
"""

        messages = [
            {"role": "system", "content": program_text},
            {"role": "user", "content": user_prompt}
        ]

        response = completion(
            model=model,
            messages=messages,
            temperature=0.7  # Higher temp for mutation exploration
        )
        
        res_text = response.choices[0].message.content
        
        # Safely extract
        from techfig.engines.aesthetic_critic import extract_json_from_response
        try:
            return extract_json_from_response(res_text)
        except Exception as e:
            print(f"Failed to parse LLM mutator output: {e}\nRaw={res_text[:200]}")
            # If it fails to parse, return the current config to fall back
            return current_spec

    loop = AutoResearchLoop(
        initial_spec=initial_spec,
        output_dir=output_dir,
        reference_image_path=reference_image_path,
        max_rounds=max_rounds,
        vision_model=model
    )
    
    best_spec = loop.run(mutator_fn)
    return best_spec
