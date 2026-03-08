"""Example: Generate a flowchart diagram."""
from techfig.engines.diagrams import create_flowchart

nodes = [
    {"id": "data",    "text": "Raw Data",    "x": 0,   "y": 0, "shape": "box", "color": "secondary"},
    {"id": "clean",   "text": "Clean",       "x": 200, "y": 0, "shape": "box"},
    {"id": "valid",   "text": "Valid?",      "x": 400, "y": 0, "shape": "diamond"},
    {"id": "analyze", "text": "Analyze",     "x": 600, "y": -80, "shape": "box"},
    {"id": "reject",  "text": "Reject",      "x": 600, "y": 80, "shape": "circle"},
    {"id": "result",  "text": "Results",     "x": 800, "y": -80, "shape": "box", "color": "accent"},
]

edges = [
    {"from": "data",  "to": "clean",   "label": "load"},
    {"from": "clean", "to": "valid",   "label": "check"},
    {"from": "valid", "to": "analyze", "label": "yes"},
    {"from": "valid", "to": "reject",  "label": "no"},
    {"from": "analyze", "to": "result", "label": "output"},
]

output = create_flowchart(nodes, edges, "output/example_flowchart.svg")
print(f"Diagram saved to {output}")
