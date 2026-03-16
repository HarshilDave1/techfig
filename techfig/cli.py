"""Command-line interface for TechFig."""
import argparse
import json
import sys

from techfig.engines.figures import create_chart, CHART_TYPES
from techfig.engines.diagrams import create_flowchart
from techfig.engines.slides import create_presentation
from techfig.engines.tikz_export import chart_to_tikz, diagram_to_tikz
from techfig.engines.batch import batch_generate
from techfig.engines.sketch_interpreter import render_from_json, get_sketch_prompt
from techfig.utils.export import convert_format
from techfig.styles.presets import get_available_styles


def main():
    parser = argparse.ArgumentParser(
        description="TechFig: Technical Graphic Generator for Scientists",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ---- chart -----------------------------------------------------------
    chart_p = subparsers.add_parser("chart", help="Generate a statistical chart")
    chart_p.add_argument("--data", required=True, help="Path to CSV/JSON data")
    chart_p.add_argument("--type", required=True, choices=list(CHART_TYPES), dest="chart_type")
    chart_p.add_argument("-o", "--output", required=True, help="Output file (.svg/.png)")
    chart_p.add_argument("--x", dest="x_col", help="X-axis column")
    chart_p.add_argument("--y", dest="y_col", help="Y-axis column")
    chart_p.add_argument("--hue", help="Grouping column")
    chart_p.add_argument("--xlabel", help="Custom X-axis label")
    chart_p.add_argument("--ylabel", help="Custom Y-axis label")
    chart_p.add_argument("--title", default="", help="Chart title")
    chart_p.add_argument("--style", default="nature", help="Style preset")

    # ---- diagram ---------------------------------------------------------
    diag_p = subparsers.add_parser("diagram", help="Generate a structural diagram")
    diag_p.add_argument("--input", required=True, help="JSON file with nodes and edges")
    diag_p.add_argument("-o", "--output", required=True, help="Output file (.svg/.png)")

    # ---- slides ----------------------------------------------------------
    slides_p = subparsers.add_parser("slides", help="Generate a PowerPoint presentation")
    slides_p.add_argument("--input", required=True, help="JSON file with slides data")
    slides_p.add_argument("-o", "--output", required=True, help="Output file (.pptx)")
    slides_p.add_argument("--template", help="Optional .pptx template")

    # ---- tikz ------------------------------------------------------------
    tikz_p = subparsers.add_parser("tikz", help="Export to LaTeX/TikZ")
    tikz_p.add_argument("--mode", required=True, choices=["chart", "diagram"])
    tikz_p.add_argument("--data", help="CSV/JSON data (for chart mode)")
    tikz_p.add_argument("--chart-type", default="bar", choices=["bar", "line", "scatter"])
    tikz_p.add_argument("--input", help="JSON file with nodes/edges (for diagram mode)")
    tikz_p.add_argument("-o", "--output", required=True, help="Output file (.tex)")
    tikz_p.add_argument("--x", dest="x_col", help="X-axis column")
    tikz_p.add_argument("--y", dest="y_col", help="Y-axis column")
    tikz_p.add_argument("--title", default="")

    # ---- export ----------------------------------------------------------
    export_p = subparsers.add_parser("export", help="Convert between formats")
    export_p.add_argument("input", help="Source file (e.g. figure.svg)")
    export_p.add_argument("-o", "--output", required=True, help="Destination file (.png/.pdf)")
    export_p.add_argument("--dpi", type=int, default=300, help="DPI for rasterization")

    # ---- batch -----------------------------------------------------------
    batch_p = subparsers.add_parser("batch", help="Generate all items from a manifest")
    batch_p.add_argument("--input", required=True, help="YAML or JSON manifest file")
    batch_p.add_argument("-o", "--output-dir", help="Override output directory")

    # ---- reconstruct -----------------------------------------------------
    recon_p = subparsers.add_parser(
        "reconstruct",
        help="Render a clean SVG from a diagram spec JSON (output from sketch interpreter)",
    )
    recon_p.add_argument("input", help="JSON file with diagram spec")
    recon_p.add_argument("-o", "--output", required=True, help="Output SVG file")

    # ---- prompt ----------------------------------------------------------
    subparsers.add_parser(
        "prompt",
        help="Print the system prompt for LLM-based sketch interpretation",
    )

    # ---- styles ----------------------------------------------------------
    subparsers.add_parser("styles", help="List available style presets")

    # ---- dispatch --------------------------------------------------------
    args = parser.parse_args()

    if args.command == "chart":
        print(f"Generating {args.chart_type} chart from {args.data}...")
        out = create_chart(
            data=args.data,
            chart_type=args.chart_type,
            output_path=args.output,
            title=args.title,
            x_col=args.x_col,
            y_col=args.y_col,
            hue_col=args.hue,
            xlabel=args.xlabel,
            ylabel=args.ylabel,
            style_name=args.style,
        )
        print(f"Chart saved to {out}")

    elif args.command == "diagram":
        print(f"Generating diagram from {args.input}...")
        with open(args.input) as f:
            data = json.load(f)
        out = create_flowchart(data.get("nodes", []), data.get("edges", []), args.output)
        print(f"Diagram saved to {out}")

    elif args.command == "slides":
        print(f"Generating slides from {args.input}...")
        with open(args.input) as f:
            slides = json.load(f)
        out = create_presentation(slides, args.output, args.template)
        print(f"Presentation saved to {out}")

    elif args.command == "tikz":
        if args.mode == "chart":
            if not args.data:
                print("Error: --data is required for chart mode", file=sys.stderr)
                sys.exit(1)
            out = chart_to_tikz(
                data=args.data,
                chart_type=args.chart_type,
                output_path=args.output,
                title=args.title,
                x_col=args.x_col,
                y_col=args.y_col,
            )
        elif args.mode == "diagram":
            if not args.input:
                print("Error: --input is required for diagram mode", file=sys.stderr)
                sys.exit(1)
            with open(args.input) as f:
                data = json.load(f)
            out = diagram_to_tikz(data.get("nodes", []), data.get("edges", []), args.output)
        print(f"TikZ file saved to {out}")

    elif args.command == "export":
        print(f"Converting {args.input} → {args.output}...")
        out = convert_format(args.input, args.output, dpi=args.dpi)
        print(f"Exported to {out}")

    elif args.command == "batch":
        print(f"Processing manifest {args.input}...")
        results = batch_generate(args.input, output_dir=args.output_dir)
        print(f"Generated {len(results)} files:")
        for r in results:
            print(f"  {r}")

    elif args.command == "reconstruct":
        print(f"Rendering diagram spec {args.input} → {args.output}...")
        out = render_from_json(args.input, args.output)
        print(f"SVG saved to {out}")

    elif args.command == "prompt":
        print(get_sketch_prompt())

    elif args.command == "styles":
        styles = get_available_styles()
        print("Available style presets:")
        for s in styles:
            print(f"  - {s}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
