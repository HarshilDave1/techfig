# TechFig — Technical Graphic Agent

> AI-assisted toolkit for scientists to create publication-quality figures, editable SVG diagrams, and PowerPoint presentations.

## What is this?

TechFig is a **code-first visualization toolkit** designed for researchers and scientists. Instead of generating pixel images, it generates **editable outputs**:

- **SVG diagrams** — open in Inkscape, tweak every node and label
- **matplotlib/seaborn figures** — export as SVG, PNG, or PDF with journal-ready styling
- **PowerPoint decks** — real `.pptx` files with proper slide layouts and speaker notes
- **LaTeX/TikZ** — `.tex` files for direct inclusion in papers
- **Sketch → Diagram** — reconstruct a clean editable SVG from an image using LLM vision + geometric primitives

## Architecture

```
Engine Layer (pure Python, no AI)  →  Agent Layer (LLM workflow)  →  CLI
```

The core engines have zero AI dependency — they're just Python functions that take structured input and produce output files. The AI layer translates natural language into structured calls.

### Sketch-to-Diagram Workflow

```
Image → LLM Vision (with sketch prompt) → JSON spec → Diagram Engine → editable SVG
```

1. **Step 1:** Send the image + `get_sketch_prompt` output to a vision LLM (Claude, GPT-4V)
2. **Step 2:** Pass the JSON output to `reconstruct_diagram` to get a clean SVG

## Installation

```bash
pip install techfig              # base (charts, diagrams, slides, TikZ)
pip install "techfig[interactive]" # + Plotly interactive charts
pip install "techfig[animation]" # + Matplotlib physics animations

# For Manim diagram animations, system dependencies (Cairo, FFMPEG) are required.
```

*For developers, you can also clone and use `uv`:*
```bash
git clone https://github.com/harshil/techfig.git
cd techfig
uv sync
```

## Quick Start

```bash
techfig chart --data results.csv --type bar --style nature -o fig1.svg

# Diagram from JSON
techfig diagram --input nodes.json -o flow.svg

# End-to-end: take a sketch photo and instantly convert to diagram SVG
techfig sketch whiteboard_sketch.jpg -o diagram.svg

# Reconstruct diagram from JSON spec (output from LLM vision)
techfig reconstruct spec.json -o diagram.svg

# Start from built-in templates for inspiration!
techfig reconstruct techfig/templates/optical_bench.json -o optical_bench.svg --pretty
# Reconstruct a diagram and generate a "pretty" 3D image using an AI model
techfig reconstruct spec.json -o diagram.svg --pretty --pretty-model openai/dall-e-3

# Print the LLM system prompt for sketch interpretation
techfig prompt

# Slides from JSON
techfig slides --input outline.json -o talk.pptx

# LaTeX/TikZ export
techfig tikz --mode chart --data results.csv --chart-type bar -o fig.tex

# Batch generation from manifest
techfig batch --input manifest.yaml

# List style presets
techfig styles
```

## Styles

Built-in presets: `nature`, `science`, `dark`, `presentation`, `minimal`

Custom styles via YAML files — see `templates/styles/example_custom.yaml`.

## Examples

See the `examples/` directory for working scripts, sample data, and the `optical_diagram_spec.json` demo.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
