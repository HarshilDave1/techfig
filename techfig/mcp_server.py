"""Model Context Protocol (MCP) Server for TechFig.

This exposes the visualization engines as callable tools to LLM assistants
like Claude Desktop, Cursor, windsurf, or custom agents.
"""
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional
import json
import logging

# We use the official anthropic mcp SDK
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent
from pydantic import BaseModel, Field

from techfig.engines.figures import create_chart
from techfig.engines.diagrams import create_flowchart
from techfig.engines.slides import create_presentation

# Set up logging to go to stderr so it doesn't corrupt MCP's stdout jsonrpc
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("techfig_mcp")

app = Server("techfig")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available visualization tools."""
    return [
        Tool(
            name="create_chart",
            description="Generate a statistical chart (bar, line, scatter, box, histogram) using seaborn/matplotlib and save as SVG/PNG.",
            inputSchema={
                "type": "object",
                "properties": {
                    "data_json": {
                        "type": "string", 
                        "description": "JSON string containing an array of objects or dict of lists representing the dataset."
                    },
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "scatter", "box", "histogram"]
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Absolute path where to save the chart (.svg or .png)"
                    },
                    "title": {"type": "string"},
                    "x_col": {"type": "string"},
                    "y_col": {"type": "string"},
                    "hue_col": {"type": "string"},
                    "style": {
                        "type": "string", 
                        "enum": ["nature", "science", "dark"],
                        "default": "nature"
                    }
                },
                "required": ["data_json", "chart_type", "output_path"]
            }
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
                                "shape": {"type": "string", "enum": ["box", "circle"]},
                                "color": {"type": "string"}
                            },
                            "required": ["id", "text", "x", "y"]
                        }
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "label": {"type": "string"}
                            },
                            "required": ["from", "to"]
                        }
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Absolute path where to save the diagram (.svg or .png)"
                    }
                },
                "required": ["nodes", "edges", "output_path"]
            }
        ),
        Tool(
            name="create_slides",
            description="Generate a PowerPoint (.pptx) presentation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "slides": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string", "description": "Bullet points separated by newlines"},
                                "image": {"type": "string", "description": "Absolute path to an image to embed on this slide"}
                            },
                            "required": ["title"]
                        }
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Absolute path where to save the .pptx file"
                    }
                },
                "required": ["slides", "output_path"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from the client."""
    logger.info(f"Received tool call: {name}")
    
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
                style_name=arguments.get("style", "nature")
            )
            return [TextContent(type="text", text=f"Chart successfully saved to {out}")]
            
        elif name == "create_diagram":
            out = create_flowchart(
                nodes=arguments["nodes"],
                edges=arguments["edges"],
                output_path=arguments["output_path"]
            )
            return [TextContent(type="text", text=f"Diagram successfully saved to {out}")]
            
        elif name == "create_slides":
            out = create_presentation(
                slides_data=arguments["slides"],
                output_path=arguments["output_path"]
            )
            return [TextContent(type="text", text=f"Presentation successfully saved to {out}")]
            
        else:
            raise ValueError(f"Unknown tool: {name}")
            
    except Exception as e:
        logger.error(f"Error executing {name}: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]

async def main():
    """Run the server using stdin/stdout transport."""
    from mcp.server.stdio import stdio_server
    
    logger.info("Starting TechFig MCP server...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
