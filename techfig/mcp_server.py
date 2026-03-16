"""Model Context Protocol (MCP) Server for TechFig.

Exposes the visualization engines as callable tools to LLM assistants
like Claude Desktop, Cursor, Windsurf, or custom agents.
"""
import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent

from techfig.engines.figures import create_chart, CHART_TYPES
from techfig.engines.diagrams import create_flowchart, SUPPORTED_SHAPES
from techfig.engines.slides import create_presentation
from techfig.engines.tikz_export import chart_to_tikz, diagram_to_tikz
from techfig.engines.batch import batch_generate
from techfig.engines.vectorize import vectorize_image, vectorize_with_preset, VECTORIZE_PRESETS
from techfig.utils.export import convert_format
from techfig.styles.presets import get_available_styles

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("techfig_mcp")

app = Server("techfig")


# ---- Tool definitions ---------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available visualization tools."""
    chart_types = list(CHART_TYPES)
    shapes = list(SUPPORTED_SHAPES)
    styles = get_available_styles()

    return [
        Tool(
            name="create_chart",
            description=(
                "Generate a statistical chart (bar, line, scatter, box, histogram, heatmap) "
                "using seaborn/matplotlib and save as SVG/PNG."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "data_json": {
                        "type": "string",
                        "description": "JSON string of tabular data (array of objects or dict of lists).",
                    },
                    "chart_type": {"type": "string", "enum": chart_types},
                    "output_path": {
                        "type": "string",
                        "description": "Absolute path for the output file (.svg or .png).",
                    },
                    "title": {"type": "string"},
                    "x_col": {"type": "string"},
                    "y_col": {"type": "string"},
                    "hue_col": {"type": "string"},
                    "xlabel": {"type": "string", "description": "Custom X-axis label"},
                    "ylabel": {"type": "string", "description": "Custom Y-axis label"},
                    "style": {"type": "string", "enum": styles, "default": "nature"},
                },
                "required": ["data_json", "chart_type", "output_path"],
            },
        ),
        Tool(
            name="create_diagram",
            description="Generate a structural flowchart or diagram and save as SVG/PNG.",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": "string"},
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "shape": {
                                    "type": "string",
                                    "description": "Basic shapes (box, circle, diamond) or component names (e.g., resistor)"
                                },
                                "color": {"type": "string"},
                                "w": {"type": "number"},
                                "h": {"type": "number"},
                                "r": {"type": "number"},
                            },
                            "required": ["id", "text", "x", "y"],
                        },
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "label": {"type": "string"},
                                "route": {"type": "string", "enum": ["straight", "orthogonal"]},
                            },
                            "required": ["from", "to"],
                        },
                    },
                    "output_path": {"type": "string"},
                },
                "required": ["nodes", "edges", "output_path"],
            },
        ),
        Tool(
            name="create_slides",
            description="Generate a PowerPoint (.pptx) presentation with optional speaker notes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "slides": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string", "description": "Bullet text (newline-separated)"},
                                "image": {"type": "string", "description": "Absolute path to image"},
                                "notes": {"type": "string", "description": "Speaker notes text"},
                            },
                            "required": ["title"],
                        },
                    },
                    "output_path": {"type": "string"},
                    "template_path": {"type": "string", "description": "Optional .pptx template"},
                },
                "required": ["slides", "output_path"],
            },
        ),
        Tool(
            name="export_tikz",
            description="Export a chart or diagram specification to a LaTeX/TikZ .tex file for paper integration.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["chart", "diagram"]},
                    "data_json": {
                        "type": "string",
                        "description": "For charts: JSON tabular data. Ignored for diagrams.",
                    },
                    "chart_type": {"type": "string", "enum": ["bar", "line", "scatter"]},
                    "nodes": {"type": "array", "description": "For diagrams: node list"},
                    "edges": {"type": "array", "description": "For diagrams: edge list"},
                    "output_path": {"type": "string"},
                    "title": {"type": "string"},
                    "x_col": {"type": "string"},
                    "y_col": {"type": "string"},
                },
                "required": ["mode", "output_path"],
            },
        ),
        Tool(
            name="list_styles",
            description="List all available style presets for figures and diagrams.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_components",
            description="List available diagram components from the registry.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="export_figure",
            description="Convert a figure between formats (e.g. SVG → PNG, SVG → PDF).",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string"},
                    "output_path": {"type": "string"},
                    "dpi": {"type": "integer", "default": 300},
                },
                "required": ["input_path", "output_path"],
            },
        ),
        Tool(
            name="batch_generate",
            description="Generate all figures/diagrams/slides from a YAML or JSON manifest file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "spec_path": {"type": "string", "description": "Path to the manifest file"},
                    "output_dir": {"type": "string", "description": "Override output directory"},
                },
                "required": ["spec_path"],
            },
        ),
        Tool(
            name="vectorize_image",
            description=(
                "Convert a raster image (PNG, JPG, BMP) to an editable SVG. "
                "Great for turning sketches, photos, or screenshots into vector art."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "Path to input image"},
                    "output_path": {"type": "string", "description": "Path for output SVG"},
                    "preset": {
                        "type": "string",
                        "enum": list(VECTORIZE_PRESETS),
                        "description": "Vectorization preset (detailed, simplified, sketch, logo)",
                    },
                    "color_mode": {
                        "type": "string",
                        "enum": ["color", "binary"],
                        "default": "color",
                    },
                    "color_precision": {
                        "type": "integer",
                        "default": 6,
                        "description": "Color precision 1-8 (fewer = simpler SVG)",
                    },
                },
                "required": ["input_path", "output_path"],
            },
        ),
    ]


# ---- Tool execution -----------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from the client."""
    logger.info("Received tool call: %s", name)

    try:
        if name == "create_chart":
            data = json.loads(arguments["data_json"])
            out = create_chart(
                data=data,
                chart_type=arguments["chart_type"],
                output_path=arguments["output_path"],
                title=arguments.get("title", ""),
                x_col=arguments.get("x_col"),
                y_col=arguments.get("y_col"),
                hue_col=arguments.get("hue_col"),
                xlabel=arguments.get("xlabel"),
                ylabel=arguments.get("ylabel"),
                style_name=arguments.get("style", "nature"),
            )
            return [TextContent(type="text", text=f"Chart saved to {out}")]

        elif name == "create_diagram":
            out = create_flowchart(
                nodes=arguments["nodes"],
                edges=arguments["edges"],
                output_path=arguments["output_path"],
            )
            return [TextContent(type="text", text=f"Diagram saved to {out}")]

        elif name == "create_slides":
            out = create_presentation(
                slides_data=arguments["slides"],
                output_path=arguments["output_path"],
                template_path=arguments.get("template_path"),
            )
            return [TextContent(type="text", text=f"Presentation saved to {out}")]

        elif name == "export_tikz":
            mode = arguments["mode"]
            if mode == "chart":
                data = json.loads(arguments.get("data_json", "[]"))
                out = chart_to_tikz(
                    data=data,
                    chart_type=arguments.get("chart_type", "bar"),
                    output_path=arguments["output_path"],
                    title=arguments.get("title", ""),
                    x_col=arguments.get("x_col"),
                    y_col=arguments.get("y_col"),
                )
            elif mode == "diagram":
                out = diagram_to_tikz(
                    nodes=arguments.get("nodes", []),
                    edges=arguments.get("edges", []),
                    output_path=arguments["output_path"],
                )
            else:
                raise ValueError(f"Invalid export_tikz mode: {mode}")
            return [TextContent(type="text", text=f"TikZ file saved to {out}")]

        elif name == "list_styles":
            styles = get_available_styles()
            return [TextContent(type="text", text=f"Available styles: {', '.join(styles)}")]

        elif name == "list_components":
            from techfig.components import get_registry, load_standard_components
            registry = get_registry()
            if not registry.list_all():
                load_standard_components(registry)
            
            comps = registry.list_all()
            result = ["Available components:"]
            for c in comps:
                result.append(f"- {c.name} [{c.category.value}] ({c.source})")
            return [TextContent(type="text", text="\n".join(result))]

        elif name == "export_figure":
            out = convert_format(
                input_path=arguments["input_path"],
                output_path=arguments["output_path"],
                dpi=arguments.get("dpi", 300),
            )
            return [TextContent(type="text", text=f"Converted file saved to {out}")]

        elif name == "vectorize_image":
            preset = arguments.get("preset")
            if preset:
                out = vectorize_with_preset(
                    arguments["input_path"], arguments["output_path"], preset=preset,
                )
            else:
                out = vectorize_image(
                    arguments["input_path"], arguments["output_path"],
                    color_mode=arguments.get("color_mode", "color"),
                    color_precision=arguments.get("color_precision", 6),
                )
            return [TextContent(type="text", text=f"Vectorized image saved to {out}")]

        elif name == "batch_generate":
            results = batch_generate(
                spec_path=arguments["spec_path"],
                output_dir=arguments.get("output_dir"),
            )
            return [TextContent(
                type="text",
                text=f"Batch complete. Generated {len(results)} files:\n" + "\n".join(results),
            )]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as exc:
        logger.error("Error executing %s: %s", name, exc, exc_info=True)
        return [TextContent(type="text", text=f"Error executing {name}: {exc}")]


# ---- Server lifecycle ---------------------------------------------------

async def _run_server():
    from mcp.server.stdio import stdio_server

    logger.info("Starting TechFig MCP server...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main():
    """Synchronous entry point for the ``techfig-mcp`` console script."""
    asyncio.run(_run_server())


if __name__ == "__main__":
    main()
