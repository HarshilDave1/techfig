from typing import Any, Dict, List
import json
import os

try:
    from manim import (
        Scene, Rectangle, Circle, Text, Line, Arrow, VGroup, DOWN,
        config, FadeIn, Write, Create
    )
except ImportError:
    # Allow importing engine for CLI help even if manim is missing
    Scene = object

from techfig.utils.data_loader import load_data


class DiagramScene(Scene):
    def __init__(self, spec: Dict[str, Any], **kwargs):
        self.spec = spec
        super().__init__(**kwargs)

    def construct(self):
        elements = self.spec.get("elements", [])
        connections = self.spec.get("connections", [])
        
        mobjects = {}
        
        # 1. Create and position elements
        for el in elements:
            el_type = el.get("type", "box")
            el_id = el.get("id", f"el_{len(mobjects)}")
            text = el.get("text", "")
            
            # Note: manim origin is center of screen (0,0). Coordinate systems differ, 
            # so we translate from absolute SVG coordinates to roughly center-relative for simple cases,
            # but ideally manim expects relative positioning or explicit coordinates.
            # Here, we will map x,y somewhat directly but scaled down (SVG 800px -> Manim ~14 units)
            scale_factor = 0.05
            sc_x = float(el.get("x", 0)) * scale_factor - 7  # Shift origin roughly to center
            sc_y = -(float(el.get("y", 0)) * scale_factor - 4)
            
            fill_color = "BLUE"
            if el.get("color") == "accent":
                fill_color = "RED"
                
            mob = None
            if el_type == "box":
                w = float(el.get("w", 120)) * scale_factor
                h = float(el.get("h", 60)) * scale_factor
                mob = Rectangle(width=w, height=h, color=fill_color)
            elif el_type == "circle":
                r = float(el.get("r", 40)) * scale_factor
                mob = Circle(radius=r, color=fill_color)
            else:
                # Fallback for complex shapes not easily translated to simple manim equivalents yet
                w = float(el.get("w", 100)) * scale_factor
                h = float(el.get("h", 100)) * scale_factor
                mob = Rectangle(width=w, height=h, color=fill_color)
                
            mob.move_to([sc_x, sc_y, 0])
            
            if text:
                t = Text(text, font_size=24)
                t.move_to(mob.get_center())
                mobjects[el_id] = VGroup(mob, t)
            else:
                mobjects[el_id] = mob

        # 2. Animate elements appearing
        self.play(*[FadeIn(mob) for mob in mobjects.values()], run_time=1.5)
        self.wait(0.5)

        # 3. Create connections
        arrows = []
        for conn in connections:
            source_id = conn.get("from")
            target_id = conn.get("to")
            if source_id in mobjects and target_id in mobjects:
                src = mobjects[source_id]
                dst = mobjects[target_id]
                
                # Get the boundary point directed towards the other object
                src_point = src.get_boundary(dst.get_center() - src.get_center())
                dst_point = dst.get_boundary(src.get_center() - dst.get_center())
                
                arrow = Arrow(start=src_point, end=dst_point, buff=0.1)
                arrows.append(arrow)

        if arrows:
            self.play(*[Create(arr) for arr in arrows], run_time=1)
            self.wait(1)


def create_animation(spec_path: str, output_path: str, quality: str = "l", preview: bool = False):
    """
    Renders an animated version of a diagram specification using Manim.
    quality: 'l', 'm', 'h', 'p', 'k' (Manim defaults)
    """
    try:
        import manim
    except ImportError:
        raise ImportError("Manim is not installed. Please install it using `pip install manim` and ensure system dependencies (Cairo, FFMPEG) are met.")

    if not output_path.endswith(".mp4"):
         output_path += ".mp4"
         
    spec = load_data(spec_path)
    
    # Configure Manim
    config.media_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    config.quality = f"{quality}_quality"
    config.preview = preview
    config.output_file = os.path.basename(output_path)
    
    # We turn off console output to keep CLI clean, unless preview is True
    config.verbosity = "INFO" if preview else "WARNING"

    # Instantiate and render the scene
    scene = DiagramScene(spec)
    scene.render()
    
    # Move the file explicitly if manim output it in a nested subfolder
    # Manim usually puts it in media/videos/1080p60/DiagramScene.mp4 based on the script name
    # We'll try to find it and move it to the requested exact output path
    import shutil
    import glob
    videos_dir = os.path.join(config.media_dir, "videos", "1080p60") # Default for high quality
    if quality == "l":
        videos_dir = os.path.join(config.media_dir, "videos", "480p15")
    elif quality == "m":
        videos_dir = os.path.join(config.media_dir, "videos", "720p30")
        
    # Search for the generated file
    search_pattern = os.path.join(config.media_dir, "videos", "**", "*.mp4")
    generated_files = glob.glob(search_pattern, recursive=True)
    
    if generated_files:
        # Sort by latest modification
        latest_file = max(generated_files, key=os.path.getmtime)
        if os.path.abspath(latest_file) != os.path.abspath(output_path):
             shutil.move(latest_file, output_path)
             
    return output_path
