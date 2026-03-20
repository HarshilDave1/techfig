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
