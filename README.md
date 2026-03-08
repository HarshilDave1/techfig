# TechFig — Technical Graphic Agent

> AI-assisted toolkit for scientists to create publication-quality figures, editable SVG diagrams, and PowerPoint presentations.

## What is this?

TechFig is a **code-first visualization toolkit** designed for researchers and scientists. Instead of generating pixel images, it generates **editable outputs**:

- **SVG diagrams** — open in Inkscape, tweak every node and label
- **matplotlib/seaborn figures** — export as SVG, PNG, or PDF with journal-ready styling
- **PowerPoint decks** — real `.pptx` files with proper slide layouts and speaker notes
- **LaTeX/TikZ** — `.tex` files for direct inclusion in papers
- **Image → Vector** — convert any raster image (PNG/JPG) to an editable SVG

## Architecture

```
Engine Layer (pure Python, no AI)  →  Agent Layer (LLM tools)  →  Adapters (MCP, CLI)
```

The core engines have zero AI dependency — they're just Python functions that take structured input and produce output files. The AI layer translates natural language into structured calls.

## Quick Start

```bash
# Install
pip install -e ".[all]"

# Chart from CSV
techfig chart --data results.csv --type bar --style nature -o fig1.svg

# Diagram from JSON
techfig diagram --input nodes.json -o flow.svg

# Slides from JSON
techfig slides --input outline.json -o talk.pptx

# Vectorize a raster image → editable SVG
techfig vectorize photo.png -o vector.svg --preset sketch

# LaTeX/TikZ export
techfig tikz --mode chart --data results.csv --chart-type bar -o fig.tex

# Batch generation from manifest
techfig batch --input manifest.yaml

# List style presets
techfig styles

# MCP server (for Claude Desktop, Cursor, Antigravity, etc.)
techfig-mcp
```

## MCP Server

Add to your assistant's MCP config:

```json
{
  "mcpServers": {
    "techfig": {
      "command": "techfig-mcp"
    }
  }
}
```

**Available tools:** `create_chart`, `create_diagram`, `create_slides`, `export_tikz`, `vectorize_image`, `export_figure`, `list_styles`, `batch_generate`

## Styles

Built-in presets: `nature`, `science`, `dark`, `presentation`, `minimal`

Custom styles via YAML files — see `templates/styles/example_custom.yaml`.

## Examples

See the `examples/` directory for working scripts and sample data.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

See [PLAN.md](PLAN.md) for the full roadmap.
