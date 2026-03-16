#!/usr/bin/env python3
"""Example: Mach-Zehnder Interferometer (MZI) Diagram.

This script generates an optical MZI diagram using the TechFig diagram engine
and SVGBuilder, demonstrating:

1. Native vector MZI — clean schematic using built-in shapes (boxes, lines, arrows)
2. Component-library MZI — embeds PNG optical components from the gwoptics library

An MZI consists of:
  Laser → BS1 (50:50 beam splitter) →  upper arm  → BS2 → Detector
                                    ↘  lower arm  ↗
  with a phase shifter on one arm and mirrors to redirect beams.

Components needed:
  - 2× beam splitters (BS1, BS2)
  - 2× mirrors (M1, M2) 
  - 1× phase shifter (φ)
  - 1× laser source
  - 1× detector
  - beam paths (lines/arrows)
"""

import os
import sys
from pathlib import Path

# Add project root to path so we can import techfig
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from techfig.engines.diagrams import create_diagram
from techfig.utils.svg_builder import SVGBuilder
import drawsvg as draw


# ---------------------------------------------------------------------------
# 1) Native vector MZI using the diagram engine
# ---------------------------------------------------------------------------

def make_native_mzi(output_path: str) -> str:
    """Create a clean MZI diagram using native SVGBuilder shapes."""

    # Layout constants  (origin = center, so coords are relative)
    #
    #  Laser ---> [BS1] ---> [M1] ---> [BS2] ---> Det
    #               |                    ↑
    #               ↓                    |
    #             [M2] ----> [φ] --------┘
    #

    elements = [
        # Laser source
        {"type": "box", "id": "laser", "x": -380, "y": 0,
         "w": 80, "h": 40, "text": "Laser", "color": "secondary"},

        # Beam splitter 1 (50:50)
        {"type": "diamond", "id": "bs1", "x": -220, "y": 0,
         "w": 60, "h": 60, "text": "BS₁", "color": "primary"},

        # Mirror 1 (upper arm, top-right)
        {"type": "box", "id": "m1", "x": 80, "y": 0,
         "w": 14, "h": 60, "text": "", "color": "accent"},

        # Mirror 2 (lower arm, bottom-left)
        {"type": "box", "id": "m2", "x": -220, "y": 180,
         "w": 60, "h": 14, "text": "", "color": "accent"},

        # Phase shifter (lower arm)
        {"type": "triangle", "id": "phase", "x": -70, "y": 180,
         "w": 50, "h": 40, "text": "φ", "color": "primary",
         "direction": "right"},

        # Beam splitter 2 (50:50)
        {"type": "diamond", "id": "bs2", "x": 80, "y": 180,
         "w": 60, "h": 60, "text": "BS₂", "color": "primary"},

        # Detector
        {"type": "circle", "id": "det", "x": 220, "y": 180,
         "r": 30, "text": "Det", "color": "secondary"},

        # Labels
        {"type": "text", "x": -70, "y": -30, "text": "Upper arm",
         "font_size": 12, "color": "text"},
        {"type": "text", "x": -70, "y": 215, "text": "Lower arm",
         "font_size": 12, "color": "text"},
        {"type": "text", "x": -70, "y": -140, "text": "Mach-Zehnder Interferometer",
         "font_size": 20, "color": "text"},
    ]

    connections = [
        # Laser → BS1
        {"from": "laser", "to": "bs1", "label": "", "style": "arrow",
         "color": "secondary"},

        # BS1 → M1 (upper arm, transmitted beam)
        {"from": "bs1", "to": "m1", "label": "", "style": "arrow",
         "color": "secondary"},

        # BS1 → M2 (lower arm, reflected beam)
        {"from": "bs1", "to": "m2", "label": "", "style": "arrow",
         "color": "secondary"},

        # M2 → Phase shifter
        {"from": "m2", "to": "phase", "label": "", "style": "arrow",
         "color": "secondary"},

        # Phase → BS2
        {"from": "phase", "to": "bs2", "label": "", "style": "arrow",
         "color": "secondary"},

        # M1 → BS2
        {"from": "m1", "to": "bs2", "label": "", "style": "arrow",
         "color": "secondary"},

        # BS2 → Detector
        {"from": "bs2", "to": "det", "label": "", "style": "arrow",
         "color": "secondary"},
    ]

    style_config = {
        "font_family": "Inter, Helvetica, Arial, sans-serif",
        "font_size": 13,
        "stroke": "#333333",
        "stroke_width": 2,
        "fill": "none",
        "colors": {
            "primary": "#0072B2",
            "secondary": "#D55E00",
            "accent": "#56B4E9",
            "background": "#FFFFFF",
            "text": "#222222",
            "stroke": "#333333",
        },
    }

    return create_diagram(
        elements, connections, output_path,
        width=1000, height=400,
        style_config=style_config,
    )


# ---------------------------------------------------------------------------
# 2) Component-library MZI using embedded PNG optical components
# ---------------------------------------------------------------------------

def _embed_png_component(
    builder_drawing: draw.Drawing,
    png_path: str,
    x: float, y: float,
    w: float, h: float,
    element_id: str = "",
    label: str = "",
    label_offset_y: float = 0,
) -> None:
    """Embed a PNG optical component as an <image> element in the SVG."""
    import base64

    with open(png_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")

    href = f"data:image/png;base64,{data}"
    img = draw.Raw(
        f'<image x="{x - w/2}" y="{y - h/2}" width="{w}" height="{h}" '
        f'href="{href}" preserveAspectRatio="xMidYMid meet" />'
    )
    g = draw.Group(id=element_id) if element_id else draw.Group()
    g.append(img)

    if label:
        g.append(draw.Text(
            label, 12,
            x=x, y=y + h / 2 + 14 + label_offset_y,
            center=True,
            font_family="Inter, Helvetica, Arial, sans-serif",
            fill="#222",
        ))

    builder_drawing.append(g)


def _draw_beam(
    builder_drawing: draw.Drawing,
    x1: float, y1: float,
    x2: float, y2: float,
    color: str = "#D55E00",
    width: float = 2.5,
) -> None:
    """Draw a beam path (colored line with arrowhead)."""
    marker = draw.Marker(-0.1, -0.5, 0.9, 0.5, scale=8, orient="auto")
    marker.append(draw.Lines(-0.1, -0.5, -0.1, 0.5, 0.9, 0, fill=color, close=True))
    builder_drawing.append(draw.Line(
        x1, y1, x2, y2,
        stroke=color, stroke_width=width,
        marker_end=marker,
    ))


def make_component_mzi(output_path: str) -> str:
    """Create an MZI using embedded PNG optical components from the gwoptics library."""

    comp_dir = project_root / "techfig" / "components" / "optical_diagram_components" / "png"

    # Check component PNGs exist
    required = ["b-bsp.png", "b-mir.png", "b-phase.png", "c-laser1.png", "e-photodiode.png"]
    missing = [f for f in required if not (comp_dir / f).exists()]
    if missing:
        # Fallback: try without photodiode
        if "e-photodiode.png" in missing:
            required.remove("e-photodiode.png")
            missing = [f for f in required if not (comp_dir / f).exists()]
        if missing:
            print(f"Missing component PNGs: {missing}")
            print(f"Looked in: {comp_dir}")
            return ""

    has_photodiode = (comp_dir / "e-photodiode.png").exists()

    # Create drawing
    d = draw.Drawing(1000, 450, origin="center")

    # White background
    d.append(draw.Rectangle(-500, -225, 1000, 450, fill="white"))

    # Title
    d.append(draw.Text(
        "Mach–Zehnder Interferometer (Component Library)",
        18, x=-370, y=-190, center=False,
        font_family="Inter, Helvetica, Arial, sans-serif",
        fill="#222", font_weight="bold",
    ))

    comp_size = 55  # component image size

    # Layout (approximate positions — shifted inward for no clipping):
    # Laser(-380,0) → BS1(-210,0) → M1(60,0)
    #                     ↓                ↓
    #                  M2(-210,170) → φ(-40,170) → BS2(60,170) → Det(230,170)

    # Laser
    _embed_png_component(d, str(comp_dir / "c-laser1.png"),
                         -380, 0, comp_size * 1.3, comp_size * 0.7,
                         element_id="laser", label="Laser")

    # BS1
    _embed_png_component(d, str(comp_dir / "b-bsp.png"),
                         -210, 0, comp_size, comp_size,
                         element_id="bs1", label="BS₁ (50:50)")

    # M1 (upper-right mirror, rotated conceptually)
    _embed_png_component(d, str(comp_dir / "b-mir.png"),
                         60, 0, comp_size * 0.5, comp_size,
                         element_id="m1", label="M₁")

    # M2 (lower-left mirror)
    _embed_png_component(d, str(comp_dir / "b-mir.png"),
                         -210, 170, comp_size * 0.5, comp_size,
                         element_id="m2", label="M₂")

    # Phase shifter
    _embed_png_component(d, str(comp_dir / "b-phase.png"),
                         -40, 170, comp_size * 0.5, comp_size * 0.9,
                         element_id="phase", label="φ")

    # BS2
    _embed_png_component(d, str(comp_dir / "b-bsp.png"),
                         60, 170, comp_size, comp_size,
                         element_id="bs2", label="BS₂ (50:50)")

    # Detector
    if has_photodiode:
        _embed_png_component(d, str(comp_dir / "e-photodiode.png"),
                             230, 170, comp_size, comp_size * 0.8,
                             element_id="det", label="Detector")
    else:
        # Draw a simple circle detector
        d.append(draw.Circle(230, 170, 22,
                             fill="#D55E00", fill_opacity=0.2,
                             stroke="#D55E00", stroke_width=2))
        d.append(draw.Text("Det", 13, x=230, y=175, center=True,
                           font_family="Inter, Helvetica, Arial, sans-serif",
                           fill="#222"))
        d.append(draw.Text("Detector", 12, x=230, y=200, center=True,
                           font_family="Inter, Helvetica, Arial, sans-serif",
                           fill="#222"))

    # Draw beam paths
    beam_color = "#D55E00"

    # Laser → BS1
    _draw_beam(d, -340, 0, -240, 0, beam_color)

    # BS1 → M1 (upper arm — horizontal)
    _draw_beam(d, -180, 0, 35, 0, beam_color)

    # BS1 → M2 (reflected — vertical down)
    _draw_beam(d, -210, 30, -210, 140, beam_color)

    # M2 → Phase (lower arm — horizontal)
    _draw_beam(d, -185, 170, -60, 170, beam_color)

    # Phase → BS2 (lower arm — continues horizontal)
    _draw_beam(d, -20, 170, 35, 170, beam_color)

    # M1 → BS2 (upper arm — vertical down)
    _draw_beam(d, 60, 30, 60, 140, beam_color)

    # BS2 → Detector
    _draw_beam(d, 90, 170, 205, 170, beam_color)

    # Arm labels
    d.append(draw.Text("Upper arm", 11, x=-60, y=-30, center=True,
                       font_family="Inter, Helvetica, sans-serif",
                       fill="#666", font_style="italic"))
    d.append(draw.Text("Lower arm", 11, x=-120, y=153, center=True,
                       font_family="Inter, Helvetica, sans-serif",
                       fill="#666", font_style="italic"))

    # Save
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    d.save_svg(str(out))
    print(f"Component MZI saved → {out}")
    return str(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    out_dir = project_root / "output"
    out_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("  MZI Diagram Generator")
    print("=" * 60)

    # 1) Native vector MZI
    print("\n[1/2] Generating native vector MZI...")
    path1 = make_native_mzi(str(out_dir / "mzi_native.svg"))
    print(f"  → {path1}")

    # 2) Component library MZI
    print("\n[2/2] Generating component-library MZI...")
    path2 = make_component_mzi(str(out_dir / "mzi_components.svg"))
    if path2:
        print(f"  → {path2}")
    else:
        print("  ⚠ Skipped (missing component PNGs)")

    print("\n✅ Done!")
