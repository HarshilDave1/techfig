"""Diagram engine to generate scientific schematics and flowcharts.

This engine processes high-level diagram descriptions (lists of nodes and edges)
and uses the SVGBuilder to generate the final graphic.
"""
from typing import Dict, List, Any, Optional
from pathlib import Path

from techfig.utils.svg_builder import SVGBuilder

def create_flowchart(
    nodes: List[Dict[str, Any]], 
    edges: List[Dict[str, Any]], 
    output_path: str,
    width: int = 800, 
    height: int = 600,
    style_config: Optional[Dict[str, Any]] = None
) -> str:
    """Generate a flowchart style diagram from node and edge definitions."""
    builder = SVGBuilder(width=width, height=height, style_config=style_config)
    
    # 1. Register all nodes first
    for node in nodes:
        node_id = node.get("id")
        shape = node.get("shape", "box")
        x, y = node.get("x", 0), node.get("y", 0)
        text = node.get("text", "")
        color = node.get("color", "primary")
        
        if shape == "box":
            w = node.get("w", 120)
            h = node.get("h", 60)
            builder.add_box(x, y, w, h, text=text, element_id=node_id, color=color)
        elif shape == "circle":
            r = node.get("r", 40)
            builder.add_circle(x, y, r, text=text, element_id=node_id, color=color)
        else:
            raise ValueError(f"Unknown shape type: {shape}")
            
    # 2. Draw all edges
    for edge in edges:
        from_id = edge.get("from")
        to_id = edge.get("to")
        label = edge.get("label", "")
        route = edge.get("route", "straight")
        color = edge.get("color", "stroke")
        
        if not from_id or not to_id:
            continue
            
        builder.add_arrow(from_id, to_id, text=label, route=route, stroke_color=color)

    # 3. Save output
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    builder.save(str(out_file))
    return str(out_file)

def generate_from_description(
    description: str,
    output_path: str,
    style_config: Optional[Dict[str, Any]] = None
) -> str:
    """Generate a diagram based purely on a natural language abstract representation.
    
    This is a stub for the AI Agent layer to implement. The engine layer expects
    structured data (nodes/edges). The agent will translate `description` into
    `nodes` and `edges` and call `create_flowchart`.
    """
    raise NotImplementedError(
        "Engine layer requires structured nodes/edges. "
        "Use the Agent layer to translate descriptions to structures."
    )
