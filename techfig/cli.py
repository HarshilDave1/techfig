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
from techfig.utils.config import load_config, set_config_val


def main():
    parser = argparse.ArgumentParser(
        description="TechFig: Technical Graphic Generator for Scientists",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    cfg = load_config()

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
    chart_p.add_argument("--style", default=cfg["style"], help="Style preset")
    chart_p.add_argument("-i", "--interactive", action="store_true", help="Generate interactive HTML plot (Plotly) instead of static image")

    # ---- diagram ---------------------------------------------------------
    diag_p = subparsers.add_parser("diagram", help="Generate a structural diagram")
    diag_p.add_argument("--input", required=True, help="JSON file with nodes and edges")
    diag_p.add_argument("-o", "--output", required=True, help="Output file (.svg/.png)")
    diag_p.add_argument("--pretty", action="store_true", help="Generate a stylized rendering using an AI image model")
    diag_p.add_argument("--pretty-model", default="openai/dall-e-3", help="Model to use for --pretty rendering (e.g. vertex_ai/imagen-3.0-generate-001)")

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
    export_p.add_argument("--dpi", type=int, default=cfg["dpi"], help="DPI for rasterization")

    # ---- batch -----------------------------------------------------------
    batch_p = subparsers.add_parser("batch", help="Generate all items from a manifest")
    batch_p.add_argument("--input", required=True, help="YAML or JSON manifest file")
    batch_p.add_argument("-o", "--output-dir", help="Override output directory")

    # ---- sketch ----------------------------------------------------------
    sketch_p = subparsers.add_parser("sketch", help="End-to-end: convert sketch image to diagram SVG")
    sketch_p.add_argument("input", help="Path to input image (e.g. photo.jpg or sketch.png)")
    sketch_p.add_argument("-o", "--output", required=True, help="Output SVG file")
    sketch_p.add_argument("--model", default=cfg.get("sketch_model", "gemini/gemini-2.5-pro"), help="Vision model to use")
    sketch_p.add_argument("--auto-refine", action="store_true", help="Launch autonomous visual refinement loop")
    sketch_p.add_argument("--max-rounds", type=int, default=cfg["max_rounds"], help="Max auto-refinement rounds")

    # ---- reconstruct -----------------------------------------------------
    recon_p = subparsers.add_parser(
        "reconstruct",
        help="Render a clean SVG from a diagram spec JSON (output from sketch interpreter)",
    )
    recon_p.add_argument("input", help="JSON file with diagram spec")
    recon_p.add_argument("-o", "--output", required=True, help="Output SVG file")
    recon_p.add_argument("--auto-refine", action="store_true", help="Launch the autonomous autoresearch visual refinement loop")
    recon_p.add_argument("--max-rounds", type=int, default=cfg["max_rounds"], help="Max auto-refinement rounds")
    recon_p.add_argument("--ref-image", help="Optional original sketch image for aesthetic scoring context")
    recon_p.add_argument("--pretty", action="store_true", help="Generate a stylized rendering using an AI image model")
    recon_p.add_argument("--pretty-model", default=cfg["pretty_model"], help="Model to use for --pretty rendering (e.g. vertex_ai/imagen-3.0-generate-001)")


    # ---- critique --------------------------------------------------------
    crit_p = subparsers.add_parser(
        "critique",
        help="Render a spec to SVG and run deterministic geometric critique (no LLM needed)",
    )
    crit_p.add_argument("--input", required=True, help="JSON file with diagram spec")
    crit_p.add_argument("--svg-output", required=True, help="Output SVG file path")
    crit_p.add_argument("--fix", action="store_true", help="Apply auto-fixes (snapping to grid and aligning rows/cols) directly to the spec")

    # ---- animate ---------------------------------------------------------
    anim_p = subparsers.add_parser(
        "animate",
        help="Generate MP4 animation from a diagram spec JSON",
    )
    anim_p.add_argument("input", help="JSON file with diagram spec")
    anim_p.add_argument("-o", "--output", required=True, help="Output MP4 file")
    anim_p.add_argument("--quality", choices=["l", "m", "h", "p", "k"], default=cfg["quality"], help="Video quality (l=480p, m=720p, h=1080p, p=1440p, k=2160p)")
    anim_p.add_argument("--preview", action="store_true", help="Auto-play animation after rendering")

    # ---- panel -----------------------------------------------------------
    panel_p = subparsers.add_parser(
        "panel",
        help="Generate a multi-panel figure from a JSON spec",
    )
    panel_p.add_argument("input", help="JSON file with panel spec")
    panel_p.add_argument("-o", "--output", required=True, help="Output file (.png/.svg)")

    # ---- equation --------------------------------------------------------
    eq_p = subparsers.add_parser(
        "equation",
        help="Render a LaTeX math equation to SVG/PNG using mathtext",
    )
    eq_p.add_argument("latex", help="The LaTeX math string (e.g. \\nabla \\cdot E)")
    eq_p.add_argument("-o", "--output", required=True, help="Output file")
    eq_p.add_argument("--style", default="nature", help="Style preset")
    eq_p.add_argument("--fontsize", type=int, default=24, help="Font size")

    # ---- animate-svg -----------------------------------------------------
    anim_svg_p = subparsers.add_parser(
        "animate-svg",
        help="Apply simple CSS/SMIL animations to an existing SVG",
    )
    anim_svg_p.add_argument("input", help="Input SVG file")
    anim_svg_p.add_argument("-o", "--output", required=True, help="Output animated SVG file")
    anim_svg_p.add_argument("--type", choices=["draw", "fade", "pulse"], default="draw", help="Animation type")
    anim_svg_p.add_argument("--duration", type=float, default=2.0, help="Animation duration (s)")
    anim_svg_p.add_argument("--stagger", type=float, default=0.5, help="Stagger delay between elements (s)")

    # ---- math-widget -----------------------------------------------------
    math_p = subparsers.add_parser(
        "math-widget",
        help="Generate an interactive HTML math widget",
    )
    math_p.add_argument("input", help="JSON file with widget spec (equation + variables)")
    math_p.add_argument("-o", "--output", required=True, help="Output HTML file")

    # ---- diagram-anim ----------------------------------------------------
    diaganim_p = subparsers.add_parser(
        "diagram-anim",
        help="Animate a diagram spec as an MP4 via Manim (requires manim/ffmpeg)",
    )
    diaganim_p.add_argument("input", help="JSON diagram spec file")
    diaganim_p.add_argument("-o", "--output", required=True, help="Output MP4 file")
    diaganim_p.add_argument("--quality", choices=["l", "m", "h", "p", "k"], default="l", help="Video quality")

    # ---- prompt ----------------------------------------------------------
    subparsers.add_parser(
        "prompt",
        help="Print the system prompt for LLM-based sketch interpretation",
    )

    # ---- styles ----------------------------------------------------------
    subparsers.add_parser("styles", help="List available style presets")

    # ---- config ----------------------------------------------------------
    cfg_p = subparsers.add_parser("config", help="Manage TechFig configuration")
    cfg_sub = cfg_p.add_subparsers(dest="cfg_command", help="Config command")
    cfg_sub.add_parser("list", help="List current configuration")
    cfg_set = cfg_sub.add_parser("set", help="Set a configuration value")
    cfg_set.add_argument("key", help="Configuration key (e.g. style, pretty_model, dpi)")
    cfg_set.add_argument("value", help="Configuration value")

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
    comp_render.add_argument("-f", "--fallback", action="store_true", help="Allow LLM to generate missing components dynamically")
    
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
        if args.interactive:
            from techfig.engines.interactive import create_interactive_chart
            out = create_interactive_chart(
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
        else:
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
        
        if getattr(args, "pretty", False):
            from techfig.engines.pretty import generate_pretty_image
            import os
            base_name, _ = os.path.splitext(out)
            pretty_out = f"{base_name}_pretty.png"
            print(f"Generating pretty rendering using {args.pretty_model}...")
            final_out = generate_pretty_image(out, pretty_out, model=args.pretty_model)
            print(f"Pretty rendering saved to {final_out}")

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

    elif args.command == "sketch":
        from techfig.engines.sketch_interpreter import sketch_to_diagram
        out = sketch_to_diagram(
            image_path=args.input,
            output_path=args.output,
            model=args.model,
            auto_refine_rounds=args.max_rounds if args.auto_refine else 0
        )
        print(f"Diagram successfully generated: {out}")

    elif args.command == "reconstruct":
        if getattr(args, "auto_refine", False):
            from techfig.engines.sketch_interpreter import auto_refine
            import os
            print(f"Starting auto-refinement loop for {args.input}...")
            with open(args.input) as f:
                spec = json.load(f)
            best_spec = auto_refine(
                initial_spec=spec,
                output_dir=os.path.dirname(args.output) or ".",
                reference_image_path=args.ref_image,
                max_rounds=args.max_rounds
            )
            # Render best spec to final output
            from techfig.engines.sketch_interpreter import render_from_spec
            out = render_from_spec(best_spec, args.output)
            print(f"Auto-refinement complete! Best SVG saved to {out}")
        else:
            print(f"Rendering diagram spec {args.input} → {args.output}...")
            out = render_from_json(args.input, args.output)
            print(f"SVG saved to {out}")
            
        if getattr(args, "pretty", False):
            from techfig.engines.pretty import generate_pretty_image
            import os
            base_name, _ = os.path.splitext(out)
            pretty_out = f"{base_name}_pretty.png"
            print(f"Generating pretty rendering using {args.pretty_model}...")
            final_out = generate_pretty_image(out, pretty_out, model=args.pretty_model)
            print(f"Pretty rendering saved to {final_out}")

    elif args.command == "critique":
        from techfig.engines.autoresearch import critique_report
        print(f"Critiquing {args.input} → {args.svg_output}...")
        with open(args.input) as f:
            spec = json.load(f)

        if getattr(args, "fix", False):
            from techfig.engines.geo_linter import snap_to_grid, align_rows_and_cols, fix_text_overlaps
            spec = fix_text_overlaps(spec)  # de-collide text labels first
            spec = snap_to_grid(spec, grid_size=10.0)
            spec = align_rows_and_cols(spec, tolerance=25.0)
            with open(args.input, "w") as f:
                json.dump(spec, f, indent=2)
            print(f"Applied auto-fixes (text de-collision + grid snap + alignment) and updated {args.input}")

        report = critique_report(spec, args.svg_output)
        # Print human-readable summary
        print(f"\nScore: {report['score']:.3f}")
        if report['issues']:
            print(f"Issues ({len(report['issues'])}):")
            for issue in report['issues']:
                print(f"  - {issue}")
        if report['suggestions']:
            print("Suggestions:")
            for s in report['suggestions']:
                print(f"  → {s}")
        # Also output JSON to stdout for programmatic use
        print("\nJSON output:")
        print(json.dumps({k: v for k, v in report.items() if k != 'spec'}, indent=2))
    elif args.command == "animate":
        from techfig.engines.animations import create_animation
        print(f"Rendering Manim animation {args.input} -> {args.output}...")
        try:
            out = create_animation(args.input, args.output, quality=args.quality, preview=args.preview)
            if isinstance(out, dict):
                print(f"Animation saved. Metadata:\n{json.dumps(out, indent=2)}")
            else:
                print(f"Animation saved to {out}")
        except Exception as e:
            print(f"Error: {e}")

    elif args.command == "panel":
        from techfig.engines.panels import create_figure_panel
        print(f"Rendering multi-panel figure {args.input} -> {args.output}...")
        out = create_figure_panel(args.input, args.output)
        print(f"Panel saved to {out}")

    elif args.command == "equation":
        from techfig.engines.equations import render_equation
        print(f"Rendering equation -> {args.output}...")
        out = render_equation(args.latex, args.output, style_name=args.style, fontsize=args.fontsize)
        print(f"Equation saved to {out}")

    elif args.command == "animate-svg":
        from techfig.engines.svg_animator import animate_svg
        print(f"Animating SVG {args.input} ({args.type}) -> {args.output}...")
        out = animate_svg(args.input, args.output, args.type, args.duration, args.stagger)
        print(f"Animated SVG saved to {out}")

    elif args.command == "math-widget":
        from techfig.engines.interactive_math import create_math_widget
        with open(args.input, "r") as f:
            spec = json.load(f)
        
        print(f"Generating math widget {args.input} -> {args.output}...")
        out = create_math_widget(
            spec.get("equation", ""),
            args.output,
            spec.get("variables", []),
            title=spec.get("title", "Interactive Math Widget"),
            description=spec.get("description", "")
        )
        print(f"Math widget saved to {out}")

    elif args.command == "diagram-anim":
        from techfig.engines.diagram_manim_bridge import render_diagram_animation
        with open(args.input, "r") as f:
            spec = json.load(f)
        out_path = args.output if args.output.endswith(".mp4") else args.output + ".mp4"
        print(f"Animating diagram {args.input} -> {out_path} (quality={args.quality})...")
        try:
            out = render_diagram_animation(spec, out_path, quality=args.quality)
            print(f"Animation saved to {out}")
        except ImportError as e:
            print(f"Error: {e}")
        except RuntimeError as e:
            print(f"Manim rendering failed: {e}")

    elif args.command == "prompt":
        print(get_sketch_prompt())

    elif args.command == "styles":
        styles = get_available_styles()
        print("Available style presets:")
        for s in styles:
            print(f"  - {s}")

    elif args.command == "components":
        _handle_components_command(args)

    elif args.command == "config":
        if args.cfg_command == "list":
            for k, v in cfg.items():
                print(f"{k}: {v}")
        elif args.cfg_command == "set":
            set_config_val(args.key, args.value)
            print(f"Set config '{args.key}' to '{args.value}'")
        else:
            print("Usage: techfig config [list|set] [key] [value]")
            
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
            
            svg = render_schemdraw_component(args.name, output_path=args.output, allow_fallback=args.fallback, **kwargs)
            
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
