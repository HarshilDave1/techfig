# Technical Graphic Agent — Implementation Plan

> A portable Python toolkit + MCP server that helps scientists create publication-quality figures, editable SVG diagrams, and PowerPoint presentations from data and natural language descriptions.

## Vision

Scientists spend too much time fighting with visualization tools. This project provides a **code-first, AI-assisted** workflow where:

1. You describe what you want (optionally with a rough sketch)
2. The agent writes deterministic code (matplotlib, SVG builders, python-pptx)
3. You get **editable outputs** — SVGs you can tweak in Inkscape, `.pptx` files you can polish in PowerPoint, LaTeX/TikZ you can paste into papers

The AI doesn't generate pixels. It generates **code that generates graphics**.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│              Adapter Layer (outermost)                │
│   MCP Server  │  OpenClaw Skill  │  CLI  │  REST API │
├──────────────────────────────────────────────────────┤
│              Agent Layer (middle)                     │
│   Tool definitions, prompt templates,                │
│   sketch interpretation, conversation state          │
├──────────────────────────────────────────────────────┤
│              Engine Layer (core, no AI dependency)    │
│   Figures  │  Diagrams  │  Slides  │  Animations     │
│   matplotlib   drawsvg    python-pptx   manim        │
│   plotly       SVG gen    slide layouts  motion       │
│   seaborn                                            │
└──────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | AI Required? | Purpose |
|-------|-------------|---------|
| **Engine** | No | Pure Python functions that take structured input → produce output files |
| **Agent** | Yes | Translates natural language → structured calls to the engine layer |
| **Adapter** | No | Thin wrappers that expose the agent layer to different platforms |

---

## Phase 1: MVP (Build This First)

**Goal:** A working MCP server with 3 tools that you can use immediately from Claude Desktop, Cursor, or Antigravity.

### 1.1 — Figure Engine (`techfig/engines/figures.py`)

Core functions for data visualization:

- `create_chart(data, chart_type, title, labels, style, output_path)` → generates matplotlib/seaborn chart
  - Supports: bar, line, scatter, histogram, box, heatmap
  - Outputs: `.svg` (editable in Inkscape), `.png`, `.pdf`
- `apply_style(style_name)` → applies a named preset
  - Built-in styles: `"nature"`, `"science"`, `"presentation"`, `"dark"`, `"minimal"`
  - Each style defines: font family, font sizes, line widths, color palette, figure dimensions
- Data input: accepts file paths (`.csv`, `.xlsx`, `.json`) or inline data (lists/dicts)

### 1.2 — Diagram Engine (`techfig/engines/diagrams.py`)

Core functions for schematic/conceptual diagrams:

- `create_diagram(description, elements, connections, output_path)` → generates SVG
  - Uses `drawsvg` or raw SVG string building
  - Supports: boxes, circles, arrows, labels, grouping
  - All elements have `id` attributes for easy Inkscape editing
- `create_flowchart(steps, connections, output_path)` → generates SVG flowchart
- Future: `sketch_to_diagram(image_path, description)` → interprets a photo of a hand-drawn sketch

### 1.3 — Slide Engine (`techfig/engines/slides.py`)

Core functions for PowerPoint generation:

- `create_deck(title, slides, output_path)` → generates `.pptx`
  - Each slide is a dict: `{layout, title, content, figures, notes}`
  - Layouts: `"title"`, `"title_content"`, `"two_column"`, `"figure"`, `"blank"`
- `add_figure_slide(deck, figure_path, title, notes)` → inserts a figure into an existing deck
- `apply_theme(deck, theme_name)` → applies color/font theme to entire deck

### 1.4 — MCP Server (`techfig/mcp_server.py`)

Exposes the engines as MCP tools:

| Tool | Input | Output |
|------|-------|--------|
| `create_figure` | data (file path or inline), chart_type, title, style | SVG/PNG file path |
| `create_diagram` | description, elements, connections, style | SVG file path |
| `create_slides` | title, slide definitions (with optional figure paths) | .pptx file path |
| `list_styles` | — | available style presets |
| `export_figure` | input_path, output_format | converted file path |

### 1.5 — CLI (`techfig/cli.py`)

Simple CLI for standalone use:

```bash
techfig chart --data results.csv --type bar --style nature -o fig1.svg
techfig slides --input outline.yaml -o presentation.pptx
techfig export fig1.svg --format png --dpi 300
```

---

## Phase 2: Enhanced Features (After MVP Works)

- **Sketch-to-diagram:** Pass a photo of a hand-drawn sketch + description → structured SVG
- **LaTeX/TikZ export:** `export_figure --format tikz` for paper integration
- **Manim animations:** `create_animation` tool for generating explanation videos
- **Batch mode:** "Take figures 1–6 and create a 10-slide deck with speaker notes"
- **Style customization:** User-defined `.yaml` style files in project directory
- **Template gallery:** Pre-built templates for common scientific diagrams (experimental setups, circuit diagrams, molecular structures, etc.)

---

## Phase 3: Productization

- **Web UI:** Chat + code editor + live preview (three-panel layout)
- **OpenClaw subagent adapter:** Follow OpenClaw agent spec for plug-and-play
- **Cloud rendering:** Server-side Manim rendering for animations
- **Marketplace listing:** Package for HACS-style distribution

---

## Project Structure

```
Technical Graphic Agent/
├── pyproject.toml              # Package metadata, dependencies, entry points
├── README.md                   # Usage docs
├── PLAN.md                     # This file
│
├── techfig/                    # Main package
│   ├── __init__.py
│   ├── cli.py                  # CLI entry point
│   ├── mcp_server.py           # MCP server entry point
│   │
│   ├── engines/                # Core engines (no AI dependency)
│   │   ├── __init__.py
│   │   ├── figures.py          # matplotlib/seaborn chart generation
│   │   ├── diagrams.py         # SVG diagram generation
│   │   └── slides.py           # python-pptx slide generation
│   │
│   ├── styles/                 # Style presets
│   │   ├── __init__.py
│   │   ├── nature.yaml         # Nature journal style
│   │   ├── science.yaml        # Science journal style
│   │   ├── presentation.yaml   # Clean presentation style
│   │   └── dark.yaml           # Dark mode style
│   │
│   └── utils/                  # Shared utilities
│       ├── __init__.py
│       ├── data_loader.py      # CSV/Excel/JSON loading
│       ├── svg_builder.py      # SVG construction helpers
│       └── export.py           # Format conversion
│
├── templates/                  # Diagram/slide templates
│   ├── experimental_setup.svg
│   └── basic_deck.pptx
│
└── tests/
    ├── test_figures.py
    ├── test_diagrams.py
    ├── test_slides.py
    └── fixtures/               # Test data files
        ├── sample_data.csv
        └── sample_sketch.png
```

---

## Dependencies

```
# Core (Phase 1)
matplotlib >= 3.8
seaborn >= 0.13
python-pptx >= 0.6.23
drawsvg >= 2.3
pandas >= 2.0
openpyxl >= 3.1        # Excel support
pyyaml >= 6.0          # Style config files
cairosvg >= 2.7        # SVG → PNG/PDF conversion
mcp >= 1.0             # MCP server SDK

# Phase 2
manim >= 0.18          # Animation engine
Pillow >= 10.0         # Sketch image processing
```

---

## Verification Plan

### Automated Tests
- **Unit tests** for each engine function using `pytest`:
  - `test_figures.py`: generate each chart type, verify SVG output is valid XML, verify PNG is non-empty
  - `test_diagrams.py`: generate diagrams with various elements, verify SVG structure
  - `test_slides.py`: generate decks, verify `.pptx` is valid (openable by python-pptx)
- Run: `pytest tests/ -v`

### Manual Verification
1. **Figure test:** Run `techfig chart --data tests/fixtures/sample_data.csv --type bar --style nature -o /tmp/test_fig.svg`, open the resulting SVG in Inkscape, confirm all elements are editable vector objects
2. **Slide test:** Run `techfig slides` with a sample outline, open the `.pptx` in PowerPoint/LibreOffice Impress, confirm slides are properly formatted
3. **MCP test:** Start the MCP server, connect from Claude Desktop or Cursor, ask it to create a figure from a CSV file, confirm the output is correct

---

## Open Questions for You

1. **Default output directory** — should generated files go into a `./output/` folder in your project, or next to the source data?
2. **Color palettes** — do you have preferred palettes, or should I curate a set of colorblind-safe scientific palettes?
ANSWER: Use the popular color palettes for scientific figures
3. **PowerPoint base template** — do you have an existing `.pptx` template (with your institution's branding) you'd like to use as a base?
Answer: Good idea on template: I dont have one now but we will keep a templates/ folder to let users use if needed
4. **Priority order** — which engine should I build first: figures (charts from data), diagrams (SVG schematics), or slides (.pptx)?
Answer: Lets start with the diagrams 
