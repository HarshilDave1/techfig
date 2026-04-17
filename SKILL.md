---
name: techfig
description: Create publication-quality figures, editable SVG diagrams, PowerPoint presentations, and LaTeX/TikZ exports from data and structured descriptions. Converts raster images to vector SVGs.
---

# TechFig — Technical Graphic Agent Skill

You are a technical visualization assistant. You generate **code that generates graphics** — not pixels. All outputs are editable (SVG, .pptx, .tex).

## What You Can Do

| Capability | Tool | Output |
|-----------|------|--------|
| Statistical charts | `create_chart` | SVG/PNG (bar, line, scatter, box, histogram, heatmap) |
| Structural diagrams | `create_diagram` | SVG (flowcharts, schematics with boxes/circles/diamonds) |
| Diagram Reconstruction | `reconstruct_diagram` | SVG (from LLM vision specs), supports `pretty` 3D rendering |
| Presentations | `create_slides` | .pptx with speaker notes and embedded figures |
| LaTeX export | `export_tikz` | .tex files using pgfplots/TikZ |
| Image → Vector | `vectorize_image` | Editable SVG from any raster image (PNG/JPG/BMP) |
| Format conversion | `export_figure` | SVG → PNG, SVG → PDF |
| Batch generation | `batch_generate` | Process a YAML manifest to generate all figures at once |

## How to Use

### MCP Server (recommended for LLM assistants)

Add to your MCP config:
```json
{
  "mcpServers": {
    "techfig": {
      "command": "techfig-mcp"
    }
  }
}
```

### CLI Usage

```bash
# Chart from CSV data
techfig chart --data results.csv --type bar --style nature -o fig1.svg

# Diagram from JSON spec
techfig diagram --input nodes_edges.json -o flow.svg

# Slides from JSON
techfig slides --input outline.json -o talk.pptx

# Convert raster image to editable SVG
techfig vectorize photo.png -o vector.svg --preset sketch

# LaTeX/TikZ export for papers
techfig tikz --mode chart --data results.csv --chart-type line -o fig.tex

# Batch: generate everything from a manifest
techfig batch --input manifest.yaml

# List available styles
techfig styles
```

## Style Presets

- **nature** — Nature journal style (serif, 300 DPI, muted colors)
- **science** — Science journal style (sans-serif, compact)
- **dark** — Dark background for presentations
- **presentation** — Large fonts, low DPI, clean
- **minimal** — No grid, light aesthetic
- Custom `.yaml` files are also supported

## Vectorization Presets

- **detailed** — High-fidelity color tracing with smooth curves
- **simplified** — Fewer colors, cleaner shapes
- **sketch** — Black & white (for hand-drawn sketches)
- **logo** — Very few colors, bold shapes (icons/logos)

## Data Input Formats

Charts accept data as:
- CSV file path (`results.csv`)
- Excel file path (`data.xlsx`)
- JSON file path or inline JSON string
- pandas DataFrame (when using Python API directly)

## Examples

See the `examples/` directory for working samples:
- `examples/sample_data.csv` — sample tabular data
- `examples/make_chart.py` — generate a chart from CSV
- `examples/make_diagram.py` — generate a flowchart SVG
- `examples/make_slides.py` — generate a presentation
- `examples/vectorize_image.py` — convert a PNG to vector SVG
- `examples/batch_manifest.yaml` — batch generation manifest

## Key Design Decisions

1. **Editable outputs** — SVGs with element IDs for Inkscape; .pptx for PowerPoint; .tex for LaTeX
2. **No AI dependency in engines** — All engines are pure Python; the AI layer is optional
3. **Colorblind-safe palettes** — All built-in styles use accessible color schemes
4. **Fallback backends** — SVG conversion tries cairosvg → rsvg-convert → inkscape

## Self-Improvement Loop (Agent-Driven)

The self-improvement loop is **agent-driven**, not hardcoded. The agent (not techfig)
is the critic and orchestrator. Techfig provides only deterministic tools:

1. **Generate initial figure:** `techfig reconstruct --input spec.json -o v1.svg`
2. **Get deterministic critique:** `techfig critique --input spec.json --svg-output v1.svg`
3. **Agent reviews the SVG visually** (using vision tools) **and reads the critique report**
4. **Agent modifies the spec.json** based on the feedback
5. **Re-generate:** `techfig reconstruct --input spec.json -o v2.svg`
6. **Repeat** until satisfied

### Programmatic API

```python
from techfig.engines.autoresearch import critique_report
import json

spec = json.load(open("spec.json"))
report = critique_report(spec, "output.svg")
print(f"Score: {report['score']}")
print(f"Issues: {report['issues']}")
print(f"Suggestions: {report['suggestions']}")
```

### Optional: Vision-Based Aesthetic Scoring

If an API key is available (e.g. `ANTHROPIC_API_KEY`), the aesthetic critic
remains available for optional visual quality scoring:

```python
from techfig.engines.aesthetic_critic import score_aesthetic, render_to_png

# Convert SVG to PNG for visual review
render_to_png("diagram.svg", "diagram.png")

# Score with a vision model (requires API key)
score, feedback = score_aesthetic("diagram.svg")
```
