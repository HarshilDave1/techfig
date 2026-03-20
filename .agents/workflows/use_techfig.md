---
description: How agents should use the techfig skill seamlessly to draw graphics
---

# TechFig Graphic Generation Workflow

This workflow teaches you as an agent how to best leverage `techfig` to draw stunning technical graphics directly for the user across terminal or MCP.

## Using TechFig via CLI

1. Ensure the system has `techfig` installed.
   ```bash
// turbo
   uv run techfig --help
   ```
2. If the user wants a chart, prepare out a CSV/JSON file using standard python/javascript logic and then generate using `techfig chart`.
   ```bash
   techfig chart --data "/tmp/data.csv" --type "scatter" -o "/path/to/scatter.svg" --style "nature"
   ```
3. If the user wants a conceptual diagram or an architectural map, use your own reasoning to design a layout or simply write the JSON diagram specification using `{"canvas": {}, "elements": [], "connections": []}`. Then call `techfig reconstruct`:
   ```bash
   techfig reconstruct "/tmp/design.json" -o "/path/to/diagram.svg" --pretty
   ```
4. To translate a UI photo or a sketch directly to a polished SVG, use the end-to-end sketch command. Note that this requires Vision LLM capabilities behind the scenes:
   ```bash
   techfig sketch "/tmp/whiteboard.jpg" -o "/path/to/clean_diagram.svg" --auto-refine
   ```
