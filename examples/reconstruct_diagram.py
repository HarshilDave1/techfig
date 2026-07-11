"""Example: Reconstruct a diagram from a JSON spec.

This demonstrates Step 2 of the sketch-to-diagram workflow.
Step 1 would be sending an image to an LLM with the sketch prompt.
"""
from techfig.engines.sketch_interpreter import render_from_spec

# The spec would come from an LLM vision analysis in practice.
# Here we define it directly to show the format.
spec = {
    "canvas": {"width": 800, "height": 400},
    "elements": [
        {"type": "circle", "id": "c1", "x": -200, "y": 0, "r": 60, "text": "Input", "color": "#0072B2"},
        {"type": "box", "id": "b1", "x": 0, "y": 0, "w": 140, "h": 70, "text": "Process", "color": "#D55E00"},
        {"type": "circle", "id": "c2", "x": 200, "y": 0, "r": 60, "text": "Output", "color": "#009E73"},
        {"type": "ellipse", "id": "e1", "x": 0, "y": 130, "rx": 80, "ry": 35,
         "text": "Feedback", "color": "#CC79A7", "stroke_dash": "5,3"},
    ],
    "connections": [
        {"from": "c1", "to": "b1", "style": "arrow"},
        {"from": "b1", "to": "c2", "style": "arrow"},
        {"from": "c2", "to": "e1", "style": "line", "stroke_dash": "5,3"},
        {"from": "e1", "to": "c1", "style": "arrow", "label": "loop"},
    ],
}

if __name__ == "__main__":
    # Step 2: Render the spec
    output = render_from_spec(spec, "output/reconstructed_diagram.svg")
    print(f"Diagram saved to {output}")

    # To see the LLM prompt for Step 1:
    # print(get_sketch_prompt())
