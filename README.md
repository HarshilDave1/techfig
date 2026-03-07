# TechFig — Technical Graphic Agent

> AI-assisted toolkit for scientists to create publication-quality figures, editable SVG diagrams, and PowerPoint presentations.

## What is this?

TechFig is a **code-first visualization toolkit** designed for researchers and scientists. Instead of generating pixel images, it generates **editable outputs**:

- **SVG diagrams** — open in Inkscape, tweak every node and label
- **matplotlib/seaborn figures** — export as SVG, PNG, or PDF with journal-ready styling
- **PowerPoint decks** — real `.pptx` files with proper slide layouts

## Architecture

```
Engine Layer (pure Python, no AI)  →  Agent Layer (LLM tools)  →  Adapters (MCP, CLI, API)
```

The core engines have zero AI dependency — they're just Python functions that take structured input and produce output files. The AI layer translates natural language into structured calls.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# CLI usage
techfig chart --data results.csv --type bar --style nature -o fig1.svg
techfig diagram --description "flowchart of PCR process" -o pcr_flow.svg
techfig slides --input outline.yaml -o presentation.pptx

# MCP server (for Claude Desktop, Cursor, etc.)
pip install -e ".[mcp]"
techfig-mcp  # starts MCP server
```

## Status

🚧 **Phase 1 — MVP in progress.** Starting with the diagram engine.

See [PLAN.md](PLAN.md) for the full roadmap.
