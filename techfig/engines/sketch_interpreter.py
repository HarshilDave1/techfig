"""Sketch interpreter -- bridge between LLM vision and the diagram engine.

This module provides:
1. A JSON schema for structured diagram descriptions
2. System prompts for LLM vision analysis (initial + refinement)
3. Functions to validate, render, and iteratively refine diagram specs

The two-step workflow:
    Step 1: LLM sees the image + SKETCH_PROMPT  outputs JSON matching DIAGRAM_SCHEMA
    Step 2: render_from_spec(json_spec, output_path)  clean editable SVG

The agentic refinement loop (optional):
    Pass 1: LLM + SKETCH_PROMPT  initial JSON spec  render SVG
    Pass 2+: LLM + REFINE_PROMPT + original image + current SVG  refined JSON  re-render
    Repeat until quality is acceptable or max iterations reached.
"""
import copy
import json
from typing import Any, Dict, List, Optional
from pathlib import Path

from techfig.engines.diagrams import create_diagram


#  JSON Schema for diagram specs 

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
                        "enum": ["box", "circle", "diamond", "ellipse", "triangle", "text", "line", "legend"],
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


#  System prompt for INITIAL analysis 

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
| triangle | id, x, y | w, h, text, color, direction(up/down/left/right), fill_opacity | Triangle. Default 6060 |
| text | x, y, text | id, font_size, color, rotation | Free-floating label (no shape). Use for annotations |
| line | x1, y1, x2, y2 | text, color, stroke_dash | Plain line. stroke_dash="5,3" for dashed |
| legend | x, y | w, h, id, title, color, entries, swatch_shape, stroke_dash, fill_opacity, rotation | Bordered panel with swatch+label rows. ``entries`` is a list of {label, color, swatch_shape?}. ``swatch_shape`` defaults to "rect" (or "circle"). Good for color keys |

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
- Default canvas is 1200800
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
4. Approximate the layout from the image -- use center-relative coordinates
5. Match colors, sizes, opacity, and proportions from the original
6. Prefer simple shapes over complex paths

## Output format

Return ONLY valid JSON (no markdown fences, no explanation):

{
  "canvas": {"width": 1200, "height": 800},
  "elements": [...],
  "connections": [...]
}
 
IMPORTANT: Every element MUST include a "type" field matching one of the types listed above (e.g. "box", "circle", "text", "line", "diamond", "ellipse", "triangle", "legend").
Example element with type: {"type": "box", "id": "mybox", "x": 0, "y": 0, "w": 100, "h": 60, "text": "Box", "color": "#0072B2", "fill_opacity": 1.0}
Do NOT omit the "type" field from any element.
"""


#  Refinement prompt for pass 2+ 

REFINE_PROMPT = """\
You are refining a diagram reconstruction. You have the ORIGINAL image
and the CURRENT rendered SVG side by side.

## Current JSON spec

```json
{current_spec}
```

## Your task

Compare the current rendering with the original image and fix any issues.
Common problems to look for:

1. **Wrong colors** -- shapes that should be blue are red, etc. Fix with explicit hex `color` values
2. **Wrong opacity** -- shapes that look solid but should be transparent, or vice versa. Fix `fill_opacity`
3. **Wrong sizes** -- shapes too small/large. Adjust w, h, r, rx, ry
4. **Wrong positions** -- shapes overlapping or too far apart. Adjust x, y coordinates
5. **Missing elements** -- labels, lines, or shapes present in original but missing
6. **Extra elements** -- shapes in the reconstruction that don't exist in the original
7. **Wrong text** -- labels that don't match the original
8. **Wrong connections** -- arrows/lines going to wrong targets, missing arrowheads
9. **Wrong line style** -- solid lines that should be dashed, or vice versa
10. **Wrong shape type** -- using a box where the original has a circle, etc.

## Rules

- Output the COMPLETE updated JSON spec (not a diff)
- Keep all existing element IDs stable (don't rename them)
- You may add or remove elements as needed
- Return ONLY valid JSON (no markdown fences, no explanation)"""
