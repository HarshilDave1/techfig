"""Diagram → Manim animation bridge.

Converts a TechFig diagram spec JSON into a rich, sequenced Manim scene.
Supports:
  - Step-by-step element reveals (sequential, grouped, or all-at-once)
  - Full color palette mapping from TechFig style presets → Manim colors
  - Per-element labels, captions, and on-screen time control
  - Typed element shapes: box, circle, pill, diamond
  - Directional arrows with optional labels
  - Global title and subtitle overlays

Usage example:

.. code-block:: json

    {
      "type": "diagram",
      "title": "Signal Processing Pipeline",
      "subtitle": "Data flows left to right",
      "style": "dark",
      "animation": "step_by_step",
      "elements": [
        {"id": "in",  "type": "circle",  "x": 0,   "y": 0,   "text": "Input",     "role": "accent"},
        {"id": "fft", "type": "box",     "x": 150,  "y": 0,   "text": "FFT",       "caption": "Fast Fourier Transform"},
        {"id": "fil", "type": "box",     "x": 300,  "y": 0,   "text": "Filter",    "group": 1},
        {"id": "ift", "type": "box",     "x": 300,  "y": 100, "text": "IFT",       "group": 1},
        {"id": "out", "type": "circle",  "x": 450,  "y": 0,   "text": "Output",    "role": "accent"}
      ],
      "connections": [
        {"from": "in",  "to": "fft", "label": "raw"},
        {"from": "fft", "to": "fil"},
        {"from": "fft", "to": "ift"},
        {"from": "fil", "to": "out"},
        {"from": "ift", "to": "out"}
      ]
    }
"""
import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Color palette mapping (TechFig role → Manim ManimColor-compatible strings)
# ---------------------------------------------------------------------------
ROLE_COLORS: Dict[str, Dict[str, str]] = {
    "dark": {
        "default":  "#4A90D9",
        "accent":   "#E07B39",
        "success":  "#5BB55E",
        "warning":  "#D4B84A",
        "danger":   "#D9534F",
        "neutral":  "#6B7280",
        "text":     "#F8FAFC",
        "bg":       "#1E293B",
        "arrow":    "#94A3B8",
    },
    "nature": {
        "default":  "#3B82F6",
        "accent":   "#F59E0B",
        "success":  "#10B981",
        "warning":  "#F59E0B",
        "danger":   "#EF4444",
        "neutral":  "#6B7280",
        "text":     "#1E293B",
        "bg":       "#FFFFFF",
        "arrow":    "#374151",
    },
    "science": {
        "default":  "#1D6FA4",
        "accent":   "#C0392B",
        "success":  "#27AE60",
        "warning":  "#D35400",
        "danger":   "#E74C3C",
        "neutral":  "#7F8C8D",
        "text":     "#2C3E50",
        "bg":       "#FAFAFA",
        "arrow":    "#555555",
    },
}


def _get_palette(style_name: str) -> Dict[str, str]:
    return ROLE_COLORS.get(style_name, ROLE_COLORS["nature"])


# ---------------------------------------------------------------------------
# Coordinate helpers: TechFig pixel space → Manim world coords
# ---------------------------------------------------------------------------

def _to_manim_coords(
    x: float, y: float,
    all_elements: List[Dict],
    canvas_w: float = 14.0,
    canvas_h: float = 8.0,
) -> Tuple[float, float]:
    """Map TechFig pixel positions to Manim world coordinates."""
    if not all_elements:
        return 0.0, 0.0
    xs = [float(e.get("x", 0)) for e in all_elements]
    ys = [float(e.get("y", 0)) for e in all_elements]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1)
    span_y = max(max_y - min_y, 1)
    # Normalize to [-canvas_w/2, canvas_w/2] x [-canvas_h/2, canvas_h/2]
    # with Y flipped (TechFig Y grows down, Manim Y grows up)
    mx = ((x - min_x) / span_x - 0.5) * canvas_w * 0.85
    my = -((y - min_y) / span_y - 0.5) * canvas_h * 0.75
    return mx, my


# ---------------------------------------------------------------------------
# Scene generator: writes a self-contained Manim .py file
# ---------------------------------------------------------------------------

SCENE_TEMPLATE = '''#!/usr/bin/env python
"""Auto-generated Manim scene by TechFig diagram_manim_bridge."""
from manim import (
    Scene, Rectangle, Circle, RoundedRectangle, Polygon,
    Text, MarkupText, VGroup, Arrow, CurvedArrow,
    FadeIn, Create, Write, GrowArrow, Indicate, Wait,
    config, UP, DOWN, LEFT, RIGHT, ORIGIN,
    ManimColor
)
import numpy as np

BG     = ManimColor("{bg}")
COLORS = {color_dict}

class DiagramScene(Scene):
    def construct(self):
        self.camera.background_color = BG

        # ---------- build mobjects ----------
        mobs = {{}}
{element_code}

        # ---------- title overlay ----------
{title_code}

        # ---------- animation sequence ----------
{anim_code}

        # ---------- connections ----------
{connection_code}

        self.wait(1.5)
'''


def _build_element_code(elements: List[Dict], palette: Dict[str, str], canvas_w: float = 14.0, canvas_h: float = 8.0) -> str:
    lines = []

    # Fixed sensible sizes in Manim world units (16:9 canvas ≈ 14 × 8)
    # These look good at medium label density.
    DEFAULT_CIRCLE_R  = 0.7   # radius
    DEFAULT_BOX_W     = 2.5   # width
    DEFAULT_BOX_H     = 1.0   # height
    DEFAULT_PILL_R    = 0.5   # corner radius
    DEFAULT_DIAMOND_W = 1.6
    DEFAULT_DIAMOND_H = 1.0

    for el in elements:
        eid = el.get("id", f"el{len(lines)}")
        etype = el.get("type", "box")
        text = el.get("text", "")
        role = el.get("role", "default")
        color = palette.get(role, palette["default"])
        txt_color = palette.get("text", "#FFFFFF")
        cap = el.get("caption", "")
        mx = el.get("_mx", 0.0)
        my = el.get("_my", 0.0)

        lines.append(f"        # Element: {eid}")
        if etype == "circle":
            r = DEFAULT_CIRCLE_R
            lines.append(f"        _shape_{eid} = Circle(radius={r:.2f}, color=ManimColor('{color}'), fill_color=ManimColor('{color}'), fill_opacity=0.25, stroke_width=2.5)")
        elif etype == "pill":
            w, h = DEFAULT_BOX_W, DEFAULT_BOX_H
            lines.append(f"        _shape_{eid} = RoundedRectangle(corner_radius={DEFAULT_PILL_R:.2f}, width={w:.2f}, height={h:.2f}, color=ManimColor('{color}'), fill_color=ManimColor('{color}'), fill_opacity=0.25, stroke_width=2.5)")
        elif etype == "diamond":
            dw, dh = DEFAULT_DIAMOND_W, DEFAULT_DIAMOND_H
            lines.append(f"        _shape_{eid} = Polygon(np.array([0,{dh/2:.2f},0]), np.array([{dw/2:.2f},0,0]), np.array([0,-{dh/2:.2f},0]), np.array([-{dw/2:.2f},0,0]), color=ManimColor('{color}'), fill_color=ManimColor('{color}'), fill_opacity=0.25, stroke_width=2.5)")
        else:  # box (default)
            w, h = DEFAULT_BOX_W, DEFAULT_BOX_H
            lines.append(f"        _shape_{eid} = Rectangle(width={w:.2f}, height={h:.2f}, color=ManimColor('{color}'), fill_color=ManimColor('{color}'), fill_opacity=0.25, stroke_width=2.5)")

        lines.append(f"        _shape_{eid}.move_to([{mx:.2f}, {my:.2f}, 0])")

        if text:
            fs = 22
            lines.append(f"        _label_{eid} = Text('{text}', font_size={fs}, color=ManimColor('{txt_color}'))")
            lines.append(f"        _label_{eid}.move_to(_shape_{eid}.get_center())")
            if cap:
                cap_color = palette.get("neutral", "#888888")
                lines.append(f"        _cap_{eid} = Text('{cap}', font_size=14, color=ManimColor('{cap_color}'))")
                lines.append(f"        _cap_{eid}.next_to(_shape_{eid}, DOWN, buff=0.08)")
                lines.append(f"        mobs['{eid}'] = VGroup(_shape_{eid}, _label_{eid}, _cap_{eid})")
            else:
                lines.append(f"        mobs['{eid}'] = VGroup(_shape_{eid}, _label_{eid})")
        else:
            lines.append(f"        mobs['{eid}'] = _shape_{eid}")

        lines.append("")

    return "\n".join(lines)


def _build_title_code(title: str, subtitle: str, palette: Dict[str, str]) -> str:
    if not title:
        return "        pass  # no title"
    txt_color = palette.get("text", "#FFFFFF")
    sub_color = palette.get("neutral", "#888888")
    lines = [
        f"        _title = Text('{title}', font_size=32, color=ManimColor('{txt_color}'))",
        f"        _title.to_edge(UP, buff=0.3)",
        f"        self.add(_title)",
    ]
    if subtitle:
        lines += [
            f"        _sub = Text('{subtitle}', font_size=20, color=ManimColor('{sub_color}'))",
            f"        _sub.next_to(_title, DOWN, buff=0.1)",
            f"        self.add(_sub)",
        ]
    return "\n".join(lines)


def _build_anim_code(elements: List[Dict], animation_type: str) -> str:
    """Build the animation play() sequence."""
    ids = [e.get("id") for e in elements]
    lines = []

    if animation_type == "all_at_once":
        args = ", ".join(f"FadeIn(mobs['{eid}'])" for eid in ids)
        lines.append(f"        self.play({args}, run_time=1.5)")

    elif animation_type == "step_by_step":
        for eid in ids:
            cap = next((e.get("caption", "") for e in elements if e.get("id") == eid), "")
            lines.append(f"        self.play(FadeIn(mobs['{eid}']), run_time=0.7)")
            if cap:
                lines.append(f"        self.wait(0.4)")

    elif animation_type == "grouped":
        groups: Dict[int, List[str]] = {}
        ungrouped: List[str] = []
        for el in elements:
            g = el.get("group")
            if g is not None:
                groups.setdefault(int(g), []).append(el.get("id"))
            else:
                ungrouped.append(el.get("id"))
        # First individual ungrouped, then groups
        for eid in ungrouped:
            lines.append(f"        self.play(FadeIn(mobs['{eid}']), run_time=0.7)")
        for g_id in sorted(groups):
            grp_ids = groups[g_id]
            args = ", ".join(f"FadeIn(mobs['{eid}'])" for eid in grp_ids)
            lines.append(f"        self.play({args}, run_time=0.9)  # group {g_id}")

    else:
        # fallback
        args = ", ".join(f"FadeIn(mobs['{eid}'])" for eid in ids)
        lines.append(f"        self.play({args}, run_time=1.5)")

    lines.append("        self.wait(0.5)")
    return "\n".join(lines)


def _build_connection_code(connections: List[Dict], elements: List[Dict], palette: Dict[str, str]) -> str:
    arrow_color = palette.get("arrow", "#888888")
    label_color = palette.get("neutral", "#888888")
    lines = []
    arrow_plays = []
    for conn in connections:
        src = conn.get("from")
        dst = conn.get("to")
        lbl = conn.get("label", "")
        curved = conn.get("curved", False)
        if not src or not dst:
            continue
        lines.append(f"        if '{src}' in mobs and '{dst}' in mobs:")
        if curved:
            lines.append(f"            _arr_{src}_{dst} = CurvedArrow(mobs['{src}'].get_right(), mobs['{dst}'].get_left(), color=ManimColor('{arrow_color}'), stroke_width=2)")
        else:
            lines.append(f"            _arr_{src}_{dst} = Arrow(mobs['{src}'].get_right(), mobs['{dst}'].get_left(), buff=0.1, color=ManimColor('{arrow_color}'), stroke_width=2, max_tip_length_to_length_ratio=0.2)")
        arrow_plays.append(f"GrowArrow(_arr_{src}_{dst})")
        if lbl:
            lines.append(f"            _albl_{src}_{dst} = Text('{lbl}', font_size=14, color=ManimColor('{label_color}'))")
            lines.append(f"            _albl_{src}_{dst}.next_to(_arr_{src}_{dst}, UP, buff=0.05)")
            arrow_plays.append(f"FadeIn(_albl_{src}_{dst})")

    if arrow_plays:
        lines.append(f"        self.play({', '.join(arrow_plays)}, run_time=1.2)")

    return "\n".join(lines) if lines else "        pass  # no connections"


def generate_manim_scene_file(spec: Dict[str, Any], scene_py_path: str) -> str:
    """Generate a self-contained .py file containing a `DiagramScene` Manim class.

    Returns the path to the generated .py file.
    """
    elements = spec.get("elements", [])
    connections = spec.get("connections", [])
    style_name = spec.get("style", "dark")
    animation_type = spec.get("animation", "step_by_step")
    title = spec.get("title", "").replace("'", "\\'")
    subtitle = spec.get("subtitle", "").replace("'", "\\'")

    palette = _get_palette(style_name)

    # Compute Manim coords and attach to elements
    for el in elements:
        mx, my = _to_manim_coords(
            float(el.get("x", 0)),
            float(el.get("y", 0)),
            elements,
        )
        el["_mx"] = mx
        el["_my"] = my

    element_code = _build_element_code(elements, palette)
    title_code = _build_title_code(title, subtitle, palette)
    anim_code = _build_anim_code(elements, animation_type)
    connection_code = _build_connection_code(connections, elements, palette)

    color_dict_str = "{\n" + ",\n".join(
        f"    '{k}': ManimColor('{v}')" for k, v in palette.items()
    ) + "\n}"

    scene_content = SCENE_TEMPLATE.format(
        bg=palette["bg"],
        color_dict=color_dict_str,
        element_code=element_code,
        title_code=title_code,
        anim_code=anim_code,
        connection_code=connection_code,
    )

    Path(scene_py_path).parent.mkdir(parents=True, exist_ok=True)
    with open(scene_py_path, "w", encoding="utf-8") as f:
        f.write(scene_content)

    return scene_py_path


def render_diagram_animation(
    spec: Dict[str, Any],
    output_path: str,
    quality: str = "l",
    preview: bool = False,
) -> str:
    """Render a TechFig diagram spec to an MP4 animation via Manim.

    Generates a temporary Python scene file, calls Manim, then moves
    the output to ``output_path``.
    """
    try:
        import manim  # noqa: F401
        from manim import config as manim_config
    except ImportError:
        raise ImportError(
            "Manim is not installed. Install it with:\n"
            "  conda install -c conda-forge manim ffmpeg\n"
            "or\n"
            "  pip install manim"
        )

    import subprocess
    import shutil
    import glob

    # --- tmp scene file ---
    out_dir = Path(output_path).parent
    scene_py = str(out_dir / "_techfig_diagram_scene.py")
    generate_manim_scene_file(spec, scene_py)

    quality_flag = {
        "l": "-ql",
        "m": "-qm",
        "h": "-qh",
        "p": "-qp",
        "k": "-qk",
    }.get(quality, "-ql")

    cmd = [
        "python", "-m", "manim",
        quality_flag,
        "--output_file", "DiagramSceneOut",
        "--media_dir", str(out_dir / "_manim_media"),
        scene_py,
        "DiagramScene",
    ]

    logger.info("Running Manim: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Manim stderr:\n%s", result.stderr)
        raise RuntimeError(f"Manim rendering failed:\n{result.stderr[-2000:]}")

    # --- find and move output ---
    pattern = str(out_dir / "_manim_media" / "videos" / "**" / "*.mp4")
    found = sorted(glob.glob(pattern, recursive=True), key=os.path.getmtime)
    if not found:
        raise FileNotFoundError("Manim finished but no MP4 was found.")

    shutil.move(found[-1], output_path)
    # cleanup generated scene helper
    try:
        Path(scene_py).unlink()
    except OSError:
        pass

    return output_path
