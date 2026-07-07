---
name: techfig
description: Create publication-quality figures, editable SVG diagrams, PowerPoint presentations, and LaTeX/TikZ exports from data and structured descriptions.
---

# TechFig — Technical Graphic Agent Skill

You are a technical visualization assistant. You generate **code that generates graphics** — not pixels. All outputs are editable (SVG, .pptx, .tex).

## Quick Reference

| Task | Command | Key Flags |
|------|---------|----------|
| Bar/line/scatter chart | `techfig chart` | `--data`, `--type`, `--style`, `-o` |
| Flowchart/diagram | `techfig diagram` | `--input`, `-o` |
| Reconstruct from vision spec | `techfig reconstruct` | input file, `-o` |
| LaTeX/TikZ export | `techfig tikz` | `--mode`, `--data`, `--chart-type`, `-o` |
| PowerPoint slides | `techfig slides` | `--input`, `-o` |
| Batch generate | `techfig batch` | `--input` |
| Critique & score | `techfig critique` | `--input`, `--svg-output` |
| List styles | `techfig styles` | — |

**Always use `-o <output_file>` to specify the output path.**

## What You Can Do

| Capability | Tool | Output |
|-----------|------|--------|
| Statistical charts | `create_chart` | SVG/PNG (bar, line, scatter, box, histogram, heatmap) |
| Structural diagrams | `create_diagram` | SVG (flowcharts, schematics with boxes/circles/diamonds) |
| Diagram Reconstruction | `reconstruct_diagram` | SVG (from LLM vision specs) |
| Presentations | `create_slides` | .pptx with speaker notes and embedded figures |
| LaTeX export | `export_tikz` | .tex files using pgfplots/TikZ |
| Format conversion | `export_figure` | SVG → PNG, SVG → PDF |
| Batch generation | `batch_generate` | Process a YAML manifest to generate all figures at once |

## CLI Usage

**Every command uses `-o <output>` to set the output file path.**

```bash
# Chart from CSV data — always specify -o
techfig chart --data results.csv --type bar --style nature -o fig1.svg

# Diagram from JSON spec
techfig diagram --input nodes_edges.json -o flow.svg

# Reconstruct diagram from vision spec
techfig reconstruct spec.json -o diagram.svg

# Slides from JSON
techfig slides --input outline.json -o talk.pptx

# LaTeX/TikZ export for papers
techfig tikz --mode chart --data results.csv --chart-type line -o fig.tex

# Batch: generate everything from a manifest
techfig batch --input manifest.yaml

# Critique a generated figure (agent-driven self-improvement)
techfig critique --input spec.json --svg-output diagram.svg

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

## Data Input Formats

Charts accept data as:
- CSV file path (`results.csv`)
- Excel file path (`data.xlsx`)
- JSON file path or inline JSON string
- pandas DataFrame (when using Python API directly)

## Error Handling & Troubleshooting

**If a command fails:**

1. **Check the error message** — techfig returns clear error text
2. **Verify file paths exist** — `--data` and `--input` files must be present
3. **Check chart type** — valid types: `bar`, `line`, `scatter`, `box`, `histogram`, `heatmap`
4. **Check style name** — run `techfig styles` to see available presets
5. **Try minimal style first** — `--style minimal` has fewer dependencies
6. **SVG conversion fallback** — tries cairosvg → rsvg-convert → inkscape automatically

**Common issues:**
- `FileNotFoundError` → check that input file exists at the given path
- `ValueError: invalid chart type` → use one of the 6 valid types above
- `cairosvg not found` → install with `pip install cairosvg` or use `--format png`
- Grid alignment warnings → use `techfig critique` to get a score and fix suggestions

## Examples

See the `examples/` directory for working samples:
- `examples/sample_data.csv` — sample tabular data
- `examples/make_chart.py` — generate a chart from CSV
- `examples/make_diagram.py` — generate a flowchart SVG
- `examples/make_slides.py` — generate a presentation
- `examples/batch_manifest.yaml` — batch generation manifest

## Key Design Decisions

1. **Editable outputs** — SVGs with element IDs for Inkscape; .pptx for PowerPoint; .tex for LaTeX
2. **No AI dependency in engines** — All engines are pure Python; the AI layer is optional
3. **Colorblind-safe palettes** — All built-in styles use accessible color schemes
4. **Fallback backends** — SVG conversion tries cairosvg → rsvg-convert → inkscape

## Self-Improvement Loop (Agent-Driven)

The self-improvement loop is **agent-driven**, not hardcoded. The agent (not techfig)
is the critic and orchestrator. Techfig provides only deterministic tools:

1. **Generate initial figure:** `techfig reconstruct spec.json -o v1.svg`
2. **Get deterministic critique:** `techfig critique --input spec.json --svg-output v1.svg`
3. **Agent reviews the SVG visually** (using vision tools) **and reads the critique report**
4. **Agent modifies the spec.json** based on the feedback
5. **Re-generate:** `techfig reconstruct spec.json -o v2.svg`
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
