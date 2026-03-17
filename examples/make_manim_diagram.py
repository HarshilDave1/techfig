import argparse
from techfig.engines.animations import create_animation

def main():
    parser = argparse.ArgumentParser(description="Create a simple diagram animated by Manim.")
    parser.add_argument("--output", default="output/manim_diagram", help="Output directory")
    args = parser.parse_args()
    
    spec = {
        "engine": "animations",
        "type": "manim_diagram",
        "elements": [
            {"id": "input", "type": "circle", "text": "Input", "x": 0, "y": 60, "color": "accent"},
            {"id": "process1", "type": "box", "text": "Filter", "x": 50, "y": 60},
            {"id": "process2", "type": "box", "text": "Transform", "x": 100, "y": 60},
            {"id": "output", "type": "circle", "text": "Result", "x": 150, "y": 60, "color": "accent"}
        ],
        "connections": [
            {"from": "input", "to": "process1"},
            {"from": "process1", "to": "process2"},
            {"from": "process2", "to": "output"}
        ]
    }
    
    # We will save it locally to a subfolder or to output directory
    import os
    os.makedirs(args.output, exist_ok=True)
    out_path = os.path.join(args.output, "diagram_animation.mp4")
    
    create_animation(spec, out_path)
    print(f"Manim diagram animation saved to {out_path}")

if __name__ == "__main__":
    main()
