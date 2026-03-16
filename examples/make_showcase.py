#!/usr/bin/env python3
"""Showcase: Generate one example per TechFig engine.

This script demonstrates the full TechFig toolkit by generating:
  1. Multi-chart gallery   — Figures engine (matplotlib/seaborn)
  2. Neural network diagram — Diagram engine (SVG)
  3. LaTeX/TikZ export      — TikZ engine (pgfplots + tikz)
  4. Interactive chart       — Interactive engine (Plotly HTML)

All outputs land in  output/showcase_*

Run:
    python examples/make_showcase.py
"""

import os
import sys
from pathlib import Path

# Ensure project root on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

OUT = project_root / "output"
OUT.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1)  FIGURES  — Multi-chart gallery
# ═══════════════════════════════════════════════════════════════════════════

def showcase_figures():
    """Generate four chart types using the figures engine."""
    from techfig.engines.figures import create_chart

    data_path = str(project_root / "examples" / "sample_data.csv")

    configs = [
        ("bar",       "showcase_bar.svg",       "Treatment vs Control",   "nature"),
        ("line",      "showcase_line.svg",       "Trend Over Categories",  "science"),
        ("scatter",   "showcase_scatter.svg",    "Measurement Scatter",    "dark"),
        ("histogram", "showcase_histogram.svg",  "Value Distribution",     "presentation"),
    ]

    paths = []
    for chart_type, filename, title, style in configs:
        out = str(OUT / filename)
        try:
            p = create_chart(
                data=data_path,
                chart_type=chart_type,
                output_path=out,
                title=title,
                x_col="category",
                y_col="value",
                hue_col="group",
                xlabel="Experiment",
                ylabel="Measurement (units)",
                style_name=style,
            )
            paths.append(p)
            print(f"   ✓ {chart_type:10s} → {filename}  [{style}]")
        except Exception as e:
            print(f"   ✗ {chart_type:10s} — {e}")

    return paths


# ═══════════════════════════════════════════════════════════════════════════
# 2)  DIAGRAMS  — Neural network schematic
# ═══════════════════════════════════════════════════════════════════════════

def showcase_neural_network():
    """Generate a feed-forward neural network diagram (3 layers)."""
    from techfig.engines.diagrams import create_diagram

    # Layer positions (centered to avoid right-side clipping)
    layers = {
        "input":  {"x": -250, "nodes": 4, "color": "secondary", "label": "Input"},
        "hidden": {"x": 0,    "nodes": 5, "color": "primary",   "label": "Hidden"},
        "output": {"x": 250,  "nodes": 3, "color": "accent",    "label": "Output"},
    }
    spacing_y = 70
    elements = []
    connections = []

    # Title
    elements.append({
        "type": "text", "x": 0, "y": -210,
        "text": "Feed-Forward Neural Network", "font_size": 20, "color": "text",
    })

    # Create nodes for each layer
    for layer_name, cfg in layers.items():
        n = cfg["nodes"]
        x = cfg["x"]
        top_y = -((n - 1) * spacing_y) / 2

        # Layer label
        elements.append({
            "type": "text", "x": x, "y": top_y - 40,
            "text": cfg["label"], "font_size": 14, "color": "text",
        })

        for i in range(n):
            nid = f"{layer_name}_{i}"
            y = top_y + i * spacing_y
            elements.append({
                "type": "circle", "id": nid, "x": x, "y": y,
                "r": 22, "text": "", "color": cfg["color"],
            })

    # Fully-connected edges: input→hidden, hidden→output
    for from_layer, to_layer in [("input", "hidden"), ("hidden", "output")]:
        for i in range(layers[from_layer]["nodes"]):
            for j in range(layers[to_layer]["nodes"]):
                connections.append({
                    "from": f"{from_layer}_{i}",
                    "to": f"{to_layer}_{j}",
                    "label": "",
                    "style": "connection",   # plain line, no arrowhead
                    "color": "muted",
                })

    style_config = {
        "font_family": "Inter, Helvetica, Arial, sans-serif",
        "font_size": 13,
        "stroke": "#333333",
        "stroke_width": 1.5,
        "fill": "none",
        "colors": {
            "primary":    "#0072B2",
            "secondary":  "#D55E00",
            "accent":     "#009E73",
            "background": "#FFFFFF",
            "text":       "#222222",
            "stroke":     "#333333",
            "muted":      "#BBBBBB",
        },
    }

    out = str(OUT / "showcase_neural_net.svg")
    path = create_diagram(
        elements, connections, out,
        width=900, height=500,
        style_config=style_config,
    )
    print(f"   ✓ neural network diagram → showcase_neural_net.svg")
    return path


# ═══════════════════════════════════════════════════════════════════════════
# 3)  TIKZ EXPORT  — Chart + Diagram as LaTeX files
# ═══════════════════════════════════════════════════════════════════════════

def showcase_tikz():
    """Export a chart and a diagram as standalone .tex files."""
    from techfig.engines.tikz_export import chart_to_tikz, diagram_to_tikz

    data_path = str(project_root / "examples" / "sample_data.csv")
    paths = []

    # Chart → pgfplots
    try:
        p = chart_to_tikz(
            data=data_path,
            chart_type="bar",
            output_path=str(OUT / "showcase_chart.tex"),
            title="Treatment vs Control",
            x_col="category",
            y_col="value",
            xlabel="Experiment",
            ylabel="Units",
        )
        paths.append(p)
        print(f"   ✓ pgfplots chart  → showcase_chart.tex")
    except Exception as e:
        print(f"   ✗ pgfplots chart  — {e}")

    # Diagram → TikZ
    nodes = [
        {"id": "start", "text": "Start",   "x": 0,   "y": 0,   "shape": "circle"},
        {"id": "proc",  "text": "Process",  "x": 250, "y": 0,   "shape": "box"},
        {"id": "dec",   "text": "OK?",      "x": 500, "y": 0,   "shape": "diamond"},
        {"id": "end",   "text": "Done",     "x": 700, "y": 0,   "shape": "circle"},
        {"id": "retry", "text": "Retry",    "x": 500, "y": 160, "shape": "box"},
    ]
    edges = [
        {"from": "start", "to": "proc",  "label": "begin"},
        {"from": "proc",  "to": "dec",   "label": "check"},
        {"from": "dec",   "to": "end",   "label": "yes"},
        {"from": "dec",   "to": "retry", "label": "no"},
        {"from": "retry", "to": "proc",  "label": "loop"},
    ]
    try:
        p = diagram_to_tikz(nodes, edges, str(OUT / "showcase_diagram.tex"))
        paths.append(p)
        print(f"   ✓ tikz diagram    → showcase_diagram.tex")
    except Exception as e:
        print(f"   ✗ tikz diagram    — {e}")

    return paths


# ═══════════════════════════════════════════════════════════════════════════
# 4)  INTERACTIVE  — Plotly HTML widget
# ═══════════════════════════════════════════════════════════════════════════

def showcase_interactive():
    """Generate an interactive Plotly scatter chart as an HTML widget."""
    from techfig.engines.interactive import create_interactive_chart

    data_path = str(project_root / "examples" / "sample_data.csv")
    out = str(OUT / "showcase_interactive.html")

    try:
        p = create_interactive_chart(
            data=data_path,
            chart_type="scatter",
            output_path=out,
            title="Interactive Measurement Scatter",
            x_col="category",
            y_col="value",
            hue_col="group",
            xlabel="Experiment",
            ylabel="Measurement (units)",
            style_name="nature",
        )
        print(f"   ✓ interactive scatter → showcase_interactive.html")
        return p
    except ImportError:
        print(f"   ⚠ skipped (plotly not installed)")
        return None
    except Exception as e:
        print(f"   ✗ interactive scatter — {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  TechFig Showcase — All Engines")
    print("=" * 60)

    print("\n[1/4] Figures engine — multi-chart gallery")
    showcase_figures()

    print("\n[2/4] Diagram engine — neural network schematic")
    showcase_neural_network()

    print("\n[3/4] TikZ engine — LaTeX export")
    showcase_tikz()

    print("\n[4/4] Interactive engine — Plotly HTML")
    showcase_interactive()

    print("\n" + "=" * 60)
    print(f"  ✅  All outputs in:  {OUT}")
    print("=" * 60)
