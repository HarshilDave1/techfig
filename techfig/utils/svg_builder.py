"""Utilities for building and manipulating SVGs.

This module provides a wrapper around drawsvg to make creating
scientific diagrams easier, with built-in styling and layout helpers.
"""
from typing import Dict, Any, Optional, Tuple, List
import drawsvg as draw

class SVGBuilder:
    """Helper class for building styled SVGs."""
    
    def __init__(self, width: int = 800, height: int = 600, style_config: Optional[Dict[str, Any]] = None):
        """Initialize the SVG canvas."""
        self.width = width
        self.height = height
        self.drawing = draw.Drawing(width, height, origin='center')
        
        # Default styling if none provided
        self.style = style_config or {
            "font_family": "Arial, Helvetica, sans-serif",
            "font_size": 14,
            "stroke": "#333333",
            "stroke_width": 2,
            "fill": "none",
            "colors": {
                "primary": "#0072B2",   # Colorblind-safe blue
                "secondary": "#D55E00", # Colorblind-safe orange
                "accent": "#009E73",    # Colorblind-safe green
                "background": "#FFFFFF",
                "text": "#000000"
            }
        }
        
        # Add white background by default for better PNG export later
        self.drawing.append(draw.Rectangle(
            -width/2, -height/2, width, height, 
            fill=str(self.style.get("colors", {}).get("background", "#FFFFFF"))
        ))
        
        # Store elements by ID for easy connection (arrows) later
        self._elements: Dict[str, Tuple[float, float, float, float]] = {} # id -> (x, y, w, h)

    def add_box(self, x: float, y: float, w: float, h: float, 
                text: str = "", element_id: str = "", 
                color: str = "primary", **kwargs) -> None:
        """Add a labeled rectangular node to the diagram."""
        fill_color = str(self.style.get("colors", {}).get(color, color))
        
        # Create a group for the box and text
        group = draw.Group(id=element_id) if element_id else draw.Group()
        
        # Draw the rectangle
        rect = draw.Rectangle(
            x - w/2, y - h/2, w, h,
            fill=fill_color + "33", # Add some transparency to fill
            stroke=fill_color,
            stroke_width=float(str(self.style.get("stroke_width", 2))),
            rx=5, ry=5, # Slightly rounded corners look more modern
            **kwargs
        )
        group.append(rect)
        
        # Add centered text if provided
        if text:
            # Simple text wrapping could be added here later
            t = draw.Text(
                text,
                font_size=float(str(self.style.get("font_size", 14))),
                x=x, y=y,
                center=True,
                font_family=str(self.style.get("font_family", "Arial")),
                fill=str(self.style.get("colors", {}).get("text", "#000000"))
            )
            group.append(t)
            
        self.drawing.append(group)
        
        if element_id:
            self._elements[element_id] = (x, y, w, h)

    def add_circle(self, x: float, y: float, r: float, 
                   text: str = "", element_id: str = "", 
                   color: str = "secondary", **kwargs) -> None:
        """Add a labeled circular node to the diagram."""
        fill_color = str(self.style.get("colors", {}).get(color, color))
        
        group = draw.Group(id=element_id) if element_id else draw.Group()
        
        circle = draw.Circle(
            x, y, r,
            fill=fill_color + "33",
            stroke=fill_color,
            stroke_width=float(str(self.style.get("stroke_width", 2))),
            **kwargs
        )
        group.append(circle)
        
        if text:
            t = draw.Text(
                text,
                font_size=float(str(self.style.get("font_size", 14))),
                x=x, y=y,
                center=True,
                font_family=str(self.style.get("font_family", "Arial")),
                fill=str(self.style.get("colors", {}).get("text", "#000000"))
            )
            group.append(t)
            
        self.drawing.append(group)
        
        if element_id:
            # For connection points, treat circle as a bounding box
            self._elements[element_id] = (x, y, r*2, r*2)

    def add_arrow(self, from_id: str, to_id: str, 
                  text: str = "", stroke_color: str = "stroke", 
                  route: str = "straight", **kwargs) -> None:
        """Draw a connecting arrow between two named elements."""
        if from_id not in self._elements or to_id not in self._elements:
            raise ValueError(f"Cannot connect {from_id} to {to_id}: elements not found")
            
        fx, fy, fw, fh = self._elements[from_id]
        tx, ty, tw, th = self._elements[to_id]
        
        # Create an arrow marker
        color_val = str(self.style.get("colors", {}).get(stroke_color) or self.style.get(stroke_color, stroke_color))
        arrow = draw.Marker(-0.1, -0.5, 0.9, 0.5, scale=8, orient='auto')
        arrow.append(draw.Lines(-0.1, -0.5, -0.1, 0.5, 0.9, 0, fill=color_val, close=True))  # type: ignore
        
        # Calculate intersection points on boundaries (simplified - connects from centers for now)
        # TODO: Implement proper boundary intersection logic
        
        path = draw.Path(
            stroke=color_val,
            stroke_width=float(str(self.style.get("stroke_width", 2))),
            fill='none',
            marker_end=arrow,
            **kwargs
        )
        
        if route == "straight":
            # Just draw a line between centers for now
            # A more advanced version would calculate the boundary intersections
            # based on shapes and relative positions
            path.M(fx, fy).L(tx, ty)
        elif route == "orthogonal":
            # For flowcharts: go horizontal then vertical
            mid_x = (fx + tx) / 2
            path.M(fx, fy).L(mid_x, fy).L(mid_x, ty).L(tx, ty)
            
        self.drawing.append(path)
        
        if text:
            # Place text at the midpoint
            mid_p_x = (fx + tx) / 2
            mid_p_y = (fy + ty) / 2
            t = draw.Text(
                text,
                font_size=float(str(self.style.get("font_size", 14))) * 0.8, # slightly smaller
                x=mid_p_x, y=mid_p_y - 10, # slightly above the line
                center=True,
                font_family=str(self.style.get("font_family", "Arial")),
                fill=str(self.style.get("colors", {}).get("text", "#000000"))
            )
            self.drawing.append(t)

    def save(self, output_path: str) -> None:
        """Save the diagram to a file."""
        if output_path.endswith('.svg'):
            self.drawing.save_svg(output_path)
        elif output_path.endswith('.png'):
            self.drawing.save_png(output_path)
        else:
            raise ValueError(f"Unsupported output format for {output_path}. Use .svg or .png")

    def get_svg_string(self) -> str:
        """Return the raw SVG string."""
        return self.drawing.as_svg()
