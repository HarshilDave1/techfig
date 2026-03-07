"""Command-line interface for TechFig."""
import argparse
import json
import sys
from pathlib import Path

from techfig.engines.figures import create_chart
from techfig.engines.diagrams import create_flowchart
from techfig.engines.slides import create_presentation

def main():
    parser = argparse.ArgumentParser(description="TechFig: Technical Graphic Generator")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # 1. Chart Subcommand
    chart_parser = subparsers.add_parser("chart", help="Generate a statistical chart")
    chart_parser.add_argument("--data", required=True, help="Path to CSV or JSON data")
    chart_parser.add_argument("--type", required=True, choices=["bar", "line", "scatter", "box", "histogram"])
    chart_parser.add_argument("-o", "--output", required=True, help="Output file (.svg or .png)")
    chart_parser.add_argument("--x", help="X-axis column")
    chart_parser.add_argument("--y", help="Y-axis column")
    chart_parser.add_argument("--hue", help="Grouping column")
    chart_parser.add_argument("--title", default="", help="Chart title")
    chart_parser.add_argument("--style", default="nature", help="Style preset (nature, science, dark)")
    
    # 2. Diagram Subcommand
    diag_parser = subparsers.add_parser("diagram", help="Generate a structural diagram")
    diag_parser.add_argument("--input", required=True, help="JSON file containing nodes and edges")
    diag_parser.add_argument("-o", "--output", required=True, help="Output file (.svg or .png)")
    
    # 3. Slides Subcommand
    slides_parser = subparsers.add_parser("slides", help="Generate a PowerPoint presentation")
    slides_parser.add_argument("--input", required=True, help="JSON file containing slides data")
    slides_parser.add_argument("-o", "--output", required=True, help="Output file (.pptx)")
    slides_parser.add_argument("--template", help="Optional .pptx template to base styles on")
    
    args = parser.parse_args()
    
    if args.command == "chart":
        print(f"Generating {args.type} chart from {args.data}...")
        out = create_chart(
            data=args.data,
            chart_type=args.type,
            output_path=args.output,
            title=args.title,
            x_col=args.x,
            y_col=args.y,
            hue_col=args.hue,
            style_name=args.style
        )
        print(f"Chart saved to {out}")
        
    elif args.command == "diagram":
        print(f"Generating diagram from {args.input}...")
        with open(args.input, 'r') as f:
            data = json.load(f)
            
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        
        out = create_flowchart(nodes, edges, args.output)
        print(f"Diagram saved to {out}")
        
    elif args.command == "slides":
        print(f"Generating slides from {args.input}...")
        with open(args.input, 'r') as f:
            slides = json.load(f)
            
        out = create_presentation(slides, args.output, args.template)
        print(f"Presentation saved to {out}")
        
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
