"""SVG Animation Engine.

Applies lightweight CSS/SMIL animations to existing static SVG files.
Allows animating scientific diagrams without needing a heavyweight
system like Manim or ffmpeg.
"""
import logging
import re
from pathlib import Path
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# Register standard SVG namespaces
ET.register_namespace('', "http://www.w3.org/2000/svg")
ET.register_namespace('xlink', "http://www.w3.org/1999/xlink")

def animate_svg(
    input_path: str,
    output_path: str,
    animation_type: str = "draw",
    duration: float = 2.0,
    stagger: float = 0.5
) -> str:
    """Animate an existing static SVG file.
    
    Args:
        input_path: Path to the static .svg file.
        output_path: Where to save the animated .svg file.
        animation_type: Type of animation:
            - 'draw': Sequentially draws line paths (line-drawing effect).
            - 'fade': Sequentially fades in elements.
            - 'pulse': Makes shapes gently pulse in size.
        duration: Base duration of the animation in seconds.
        stagger: Delay between animating sequential elements in seconds.
        
    Returns:
        The absolute path to the generated animated SVG file.
    """
    input_file = Path(input_path).resolve()
    if not input_file.exists():
        raise FileNotFoundError(f"Cannot find SVG file: {input_file}")
        
    # Read the SVG content
    with open(input_file, 'r', encoding='utf-8') as f:
        svg_content = f.read()
        
    # Remove XML declaration if present to prevent parsing issues
    svg_content = re.sub(r'<\?xml[^>]+\?>', '', svg_content).strip()
    
    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError as e:
        logger.error(f"Failed to parse SVG {input_file}: {e}")
        # If parsing fails, just return the original file or raise
        raise ValueError(f"Invalid SVG file: {e}")

    # Ensure SVG namespace is used
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    
    # Generate unique CSS class based on animation type
    anim_class = f"techfig-anim-{animation_type}"
    
    style_elem = ET.Element('{http://www.w3.org/2000/svg}style')
    
    if animation_type == "draw":
        # Find all paths
        paths = root.findall('.//svg:path', ns)
        
        css_rules = [
            f".{anim_class} {{",
            "  stroke-dasharray: 1000;",
            "  stroke-dashoffset: 1000;",
            f"  animation: techfig-draw {duration}s ease forwards;",
            "}",
            "@keyframes techfig-draw {",
            "  to { stroke-dashoffset: 0; }",
            "}"
        ]
        
        # Add class and stagger
        for i, path in enumerate(paths):
            path.set('class', f"{path.get('class', '')} {anim_class}".strip())
            delay = i * stagger
            if delay > 0:
                # Add inline style for delay
                current_style = path.get('style', '')
                path.set('style', f"{current_style} animation-delay: {delay}s;".strip())
                
    elif animation_type == "fade":
        # Find all group elements (g) that have children, or paths/shapes
        # A simple heuristic: apply to immediate children of root
        children = [c for c in root if c.tag != '{http://www.w3.org/2000/svg}defs' and c.tag != '{http://www.w3.org/2000/svg}style']
        
        css_rules = [
            f".{anim_class} {{",
            "  opacity: 0;",
            f"  animation: techfig-fade {duration}s ease forwards;",
            "}",
            "@keyframes techfig-fade {",
            "  to { opacity: 1; }",
            "}"
        ]
        
        for i, child in enumerate(children):
            child.set('class', f"{child.get('class', '')} {anim_class}".strip())
            delay = i * stagger
            if delay > 0:
                current_style = child.get('style', '')
                child.set('style', f"{current_style} animation-delay: {delay}s;".strip())
                
    elif animation_type == "pulse":
        # Apply pulse to circles or rects
        shapes = root.findall('.//svg:circle', ns) + root.findall('.//svg:rect', ns)
        
        css_rules = [
            f".{anim_class} {{",
            f"  animation: techfig-pulse {duration}s ease-in-out infinite alternate;",
            "  transform-origin: center;",
            "  transform-box: fill-box;",
            "}",
            "@keyframes techfig-pulse {",
            "  from { transform: scale(1); }",
            "  to { transform: scale(1.1); }",
            "}"
        ]
        
        for shape in shapes:
            shape.set('class', f"{shape.get('class', '')} {anim_class}".strip())
            
    else:
        raise ValueError(f"Unknown SVG animation type: {animation_type}")
        
    style_elem.text = "\n".join(css_rules)
    root.insert(0, style_elem)
    
    # Save the modified SVG
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write with XML declaration
    with open(out_file, 'wb') as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        ET.ElementTree(root).write(f, encoding='utf-8', xml_declaration=False)
        
    return str(out_file)
