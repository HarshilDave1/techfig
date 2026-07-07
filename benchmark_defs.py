"""Benchmark diagram generator exercising new techfig features.

This script demonstrates the features that are NOT reachable through the JSON
spec format alone:
  - SVGBuilder <defs> support: linear & radial gradients, patterns, filters
  - Material preset style lookups (metal, semiconductor, glass, dielectric, substrate)
  - Real font metrics (PIL-based text width measurement)
  - Stroke != fill (explicit stroke_color separate from fill color)
  - Typography roles: title, subtitle, label, annotation, tick (via font_size tiers)
  - Math text via matplotlib mathtext (rendered as separate SVGs and referenced)

It also re-uses the JSON-spec-rendered benchmark.svg (from benchmark_spec.json)
as the primary diagram. This script produces:
  - benchmark_defs.svg    — gradient + defs + material presets showcase
  - equation_Jsc.svg      — math text: J_sc equation
  - equation_eta.svg      — math text: efficiency equation
"""
import sys
from pathlib import Path

# Ensure the project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import drawsvg as draw  # noqa: E402

from techfig.utils.svg_builder import SVGBuilder  # noqa: E402
from techfig.styles.presets import get_style  # noqa: E402
from techfig.engines.equations import render_equation  # noqa: E402


def build_defs_benchmark(output_path: str) -> str:
    """Build an SVG that exercises <defs>, gradients, patterns, filters,
    material preset colors, stroke != fill, and typography roles."""
    # Use the semiconductor material preset as the base style
    style = get_style("semiconductor")
    builder = SVGBuilder(width=1000, height=700, style_config=style)

    # --- <defs>: linear gradient for silicon absorber ---
    silicon_gradient = builder.add_linear_gradient(
        "siliconGrad",
        stops=[
            (0, "#1D4ED8", 1.0),
            (0.5, "#2563EB", 0.95),
            (1, "#1E3A8A", 1.0),
        ],
        x1=0, y1=0, x2=0, y2=200,
        gradient_units="userSpaceOnUse",
    )

    # --- <defs>: radial gradient for metal contact sheen ---
    metal_gradient = builder.add_radial_gradient(
        "metalGrad",
        stops=[
            (0, "#D1D5DB", 1.0),
            (0.6, "#9CA3AF", 1.0),
            (1, "#4B5563", 1.0),
        ],
        cx=0, cy=0, r=80,
        gradient_units="userSpaceOnUse",
    )

    # --- <defs>: pattern for the BSF hatching ---
    hatch = builder.add_pattern(
        "bsfHatch",
        width=8, height=8,
        pattern_units="userSpaceOnUse",
        elements=[
            draw.Line(0, 0, 8, 8, stroke="#172554", stroke_width=1),
            draw.Line(0, 8, 8, 0, stroke="#172554", stroke_width=1),
        ],
    )

    # --- <defs>: drop-shadow filter ---
    shadow = builder.add_filter(
        "dropShadow",
        elements=[draw.FilterItem("feGaussianBlur", stdDeviation=3, result="blur")],
    )

    # --- Typography roles (font_size tiers) ---
    # title: 26px bold, subtitle: 16px, label: 14px, annotation: 12px, tick: 10px
    builder.add_text(0, -300, "Defs & Material Preset Benchmark", font_size=26, color="text")
    builder.add_text(0, -270, "Gradients, patterns, filters, stroke != fill, typography roles",
                     font_size=16, color="muted")

    # --- Silicon layer with gradient fill (uses defs) ---
    # drawsvg boxes don't directly accept gradient id via the builder, so we
    # append a raw rectangle referencing the gradient.
    silicon_rect = draw.Rectangle(
        -300, -200, 600, 160,
        fill=silicon_gradient,  # gradient object
        stroke="#1E3A8A", stroke_width=2,
        rx=3, ry=3,
    )
    builder.drawing.append(silicon_rect)
    builder.add_text(0, -120, "p-Si absorber (gradient fill)", font_size=14, color="#FFFFFF")

    # --- Metal contact with radial gradient ---
    metal_rect = draw.Rectangle(
        -300, 100, 600, 40,
        fill=metal_gradient,
        stroke="#374151", stroke_width=2,
        rx=3, ry=3,
    )
    builder.drawing.append(metal_rect)
    builder.add_text(0, 120, "Al back contact (radial gradient)", font_size=14, color="#111827")

    # --- BSF layer with pattern fill ---
    bsf_rect = draw.Rectangle(
        -300, 60, 600, 30,
        fill=hatch,
        stroke="#172554", stroke_width=1.5,
        rx=2, ry=2,
    )
    builder.drawing.append(bsf_rect)
    builder.add_text(0, 75, "p+ BSF (pattern fill)", font_size=12, color="#451A03")

    # --- Glass layer (from glass material preset) ---
    glass_style = get_style("glass")
    glass_fill = glass_style["colors"]["primary"]
    glass_stroke = glass_style["colors"]["stroke"]
    builder.add_box(
        0, -230, 600, 40,
        text="Glass cover (glass preset)",
        color=glass_fill,
        stroke_color=glass_stroke,
        fill_opacity=0.4,
    )

    # --- Stroke != fill demonstration ---
    # A box where fill is blue but stroke is red (impossible before P2-C)
    builder.add_box(
        -200, 200, 160, 50,
        text="stroke != fill",
        color="#2563EB",        # blue fill
        stroke_color="#DC2626", # red stroke
        fill_opacity=0.6,
    )

    # --- Typography role labels (tick tier) ---
    for i, label in enumerate(["0 um", "50 um", "100 um", "150 um", "200 um"]):
        builder.add_text(-310 + i * 60, 260, label, font_size=10, color="muted")

    builder.add_text(0, 290, "tick labels (10px) — real font metrics prevent overlap",
                     font_size=12, color="muted")

    # --- Annotation with callout ---
    builder.add_callout(
        280, -120, "gradient fill\nvia <defs>",
        anchor_x=200, anchor_y=-120,
        color="#7C3AED", font_size=12,
    )

    builder.save(output_path)
    return str(Path(output_path).resolve())


def render_math_equations(out_dir: str) -> list[str]:
    """Render math equations via matplotlib mathtext."""
    paths = []
    eq1 = render_equation(
        r"J_{sc} = q \int_{0}^{\lambda_g} \Phi(\lambda) \, d\lambda",
        f"{out_dir}/equation_Jsc.svg",
        style_name="semiconductor",
        fontsize=28,
    )
    paths.append(eq1)

    eq2 = render_equation(
        r"\eta = \frac{J_{sc} \cdot V_{oc} \cdot FF}{P_{in}}",
        f"{out_dir}/equation_eta.svg",
        style_name="semiconductor",
        fontsize=28,
    )
    paths.append(eq2)

    eq3 = render_equation(
        r"V_{oc} = \frac{k_B T}{q} \ln\!\left(\frac{J_{sc}}{J_0} + 1\right)",
        f"{out_dir}/equation_Voc.svg",
        style_name="semiconductor",
        fontsize=28,
    )
    paths.append(eq3)

    return paths


if __name__ == "__main__":
    out_dir = str(PROJECT_ROOT)
    svg_path = build_defs_benchmark(f"{out_dir}/benchmark_defs.svg")
    print(f"Defs benchmark saved to: {svg_path}")
    eq_paths = render_math_equations(out_dir)
    for p in eq_paths:
        print(f"Equation saved to: {p}")
