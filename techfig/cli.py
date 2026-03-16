"""Command-line interface for TechFig."""
import argparse
import json
import sys

from techfig.engines.figures import create_chart, CHART_TYPES
from techfig.engines.diagrams import create_flowchart
from techfig.engines.slides import create_presentation
from techfig.engines.tikz_export import chart_to_tikz, diagram_to_tikz
from techfig.engines.batch import batch_generate
from techfig.engines.vectorize import vectorize_image, vectorize_with_preset, VECTORIZE_PRESETS
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

    # ---- vectorize -------------------------------------------------------
    vec_p = subparsers.add_parser("vectorize", help="Convert a raster image to editable SVG")
    vec_p.add_argument("input", help="Source image (PNG, JPG, BMP, etc.)")
    vec_p.add_argument("-o", "--output", required=True, help="Output SVG file")
    vec_p.add_argument(
        "--preset", choices=list(VECTORIZE_PRESETS),
        help="Vectorization preset (detailed, simplified, sketch, logo)",
    )
    vec_p.add_argument(
        "--color-mode", choices=["color", "binary"], default="color",
        help="Color mode: 'color' for full color, 'binary' for B&W (default: color)",
    )
    vec_p.add_argument(
        "--color-precision", type=int, default=6,
        help="Color quantization precision 1-8 (fewer = simpler SVG, default: 6)",
    )

    # ---- styles ----------------------------------------------------------
    subparsers.add_parser("styles", help="List available style presets")

    # ---- components ------------------------------------------------------
    comp_p = subparsers.add_parser("components", help="Manage component library")
    comp_sub = comp_p.add_subparsers(dest="comp_command", help="Component command")
    
    # components list
    comp_list = comp_sub.add_parser("list", help="List available components")
    comp_list.add_argument("--category", "-c", help="Filter by category (circuit, physics, optics, etc.)")
    comp_list.add_argument("--source", "-s", help="Filter by source (standard, lab_folder)")
    comp_list.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    # components search
    comp_search = comp_sub.add_parser("search", help="Search components")
    comp_search.add_argument("query", help="Search query")
    comp_search.add_argument("--category", "-c", help="Filter by category")
    comp_search.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    # components index
    comp_index = comp_sub.add_parser("index", help="Index lab folder components")
    comp_index.add_argument("--folder", "-f", help="Custom lab folder path")
    
    # components render
    comp_render = comp_sub.add_parser("render", help="Render a component to SVG")
    comp_render.add_argument("name", help="Component name (e.g., resistor, capacitor)")
    comp_render.add_argument("-o", "--output", help="Output SVG file (prints to stdout if not set)")
    comp_render.add_argument("--label", "-l", help="Component label")
    
    # components stats
    comp_stats = comp_sub.add_parser("stats", help="Show component library statistics")
    comp_stats.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    # components show
    comp_show = comp_sub.add_parser("show", help="Show component details")
    comp_show.add_argument("name", help="Component name")

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
        print(f"Converting {args.input} -> {args.output}...")
        out = convert_format(args.input, args.output, dpi=args.dpi)
        print(f"Exported to {out}")

    elif args.command == "batch":
        print(f"Processing manifest {args.input}...")
        results = batch_generate(args.input, output_dir=args.output_dir)
        print(f"Generated {len(results)} files:")
        for r in results:
            print(f"  {r}")

    elif args.command == "vectorize":
        print(f"Vectorizing {args.input} -> {args.output}...")
        if args.preset:
            out = vectorize_with_preset(args.input, args.output, preset=args.preset)
        else:
            out = vectorize_image(
                args.input, args.output,
                color_mode=args.color_mode,
                color_precision=args.color_precision,
            )
        print(f"SVG saved to {out}")

    elif args.command == "styles":
        styles = get_available_styles()
        print("Available style presets:")
        for s in styles:
            print(f"  - {s}")

    elif args.command == "components":
        _handle_components_command(args)

    else:
        parser.print_help()
        sys.exit(1)


def _handle_components_command(args):
    """Handle component library commands."""
    from techfig.components import (
        get_registry,
        load_standard_components,
        get_lab_folder,
        render_schemdraw_component,
        ComponentCategory,
    )
    
    # Initialize registry and load components
    registry = get_registry()
    load_standard_components(registry)
    
    if args.comp_command == "list":
        # Filter by category if provided
        category = None
        if args.category:
            try:
                category = ComponentCategory(args.category.lower())
            except ValueError:
                print(f"Unknown category: {args.category}", file=sys.stderr)
                print(f"Valid categories: {', '.join(c.value for c in ComponentCategory)}", file=sys.stderr)
                sys.exit(1)
        
        components = registry.list_all(category=category)
        
        # Filter by source if provided
        if args.source:
            components = [c for c in components if c.source == args.source]
        
        if args.json:
            print(json.dumps([c.to_dict() for c in components], indent=2))
        else:
            print(f"Found {len(components)} components:")
            for comp in components:
                print(f"  {comp.name:<20} [{comp.category.value:<10}] ({comp.source})")
    
    elif args.comp_command == "search":
        category = None
        if args.category:
            try:
                category = ComponentCategory(args.category.lower())
            except ValueError:
                pass
        
        results = registry.search(args.query, category=category)
        
        if args.json:
            print(json.dumps([c.to_dict() for c in results], indent=2))
        else:
            if results:
                print(f"Search results for '{args.query}':")
                for comp in results:
                    print(f"  {comp.name:<20} [{comp.category.value:<10}] - {comp.description}")
            else:
                print(f"No components found matching '{args.query}'")
    
    elif args.comp_command == "index":
        lab_folder = get_lab_folder(args.folder)
        indexed = lab_folder.index_components(registry)
        print(f"Indexed {indexed} components from {lab_folder.folder}")
        print(f"Total components in registry: {len(registry.list_all())}")
    
    elif args.comp_command == "render":
        try:
            kwargs = {}
            if args.label:
                kwargs["label"] = args.label
            
            svg = render_schemdraw_component(args.name, output_path=args.output, **kwargs)
            
            if args.output:
                print(f"Component '{args.name}' saved to {args.output}")
            else:
                print(svg)
        except Exception as e:
            print(f"Error rendering component '{args.name}': {e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.comp_command == "stats":
        stats = registry.get_stats()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print("Component Library Statistics:")
            print(f"  Total components: {stats['total_components']}")
            print(f"  Lab folder: {stats['lab_folder']}")
            print("  By category:")
            for cat, count in stats['categories'].items():
                print(f"    {cat}: {count}")
            print("  By source:")
            for src, count in stats['sources'].items():
                print(f"    {src}: {count}")
    
    elif args.comp_command == "show":
        comp = registry.get(args.name)
        if comp:
            print(f"Component: {comp.name}")
            print(f"  Category: {comp.category.value}")
            print(f"  Source: {comp.source}")
            print(f"  Tags: {', '.join(comp.tags) if comp.tags else 'none'}")
            print(f"  Description: {comp.description}")
            if comp.file_path:
                print(f"  File: {comp.file_path}")
            if comp.schemdraw_element:
                print(f"  Schemdraw: {comp.schemdraw_element}")
        else:
            print(f"Component '{args.name}' not found", file=sys.stderr)
            sys.exit(1)
    
    else:
        print("Unknown component command. Use: list, search, index, render, stats, show")
        sys.exit(1)


if __name__ == "__main__":
    main()
