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

# Generate interactive HTML widget from parametric diagram spec
techfig interactive spec.json -o widget.html

# Cross-check a spec's model functions between Python and Node
techfig verify-model spec.json

# Assemble single-file explainer page from markdown and diagram specs
techfig explain explainer.md -o page.html

# Validate interactive HTML for inert controls, overlaps, and runtime errors
techfig critique --html widget.html
```

## Command Reference

| Command | Usage | Description |
| --- | --- | --- |
| `chart` | `techfig chart --data <file> --type <type> -o <out>` | Generate statistical charts (SVG, PNG, or interactive Plotly) |
| `diagram` | `techfig diagram --input <nodes.json> -o <out>` | Generate structural node-and-edge diagrams |
| `reconstruct` | `techfig reconstruct <spec.json> -o <out.svg>` | Render clean SVG from diagram spec JSON |
| `interactive` | `techfig interactive <spec.json> -o <out.html> [--title <t>]` | Generate self-contained interactive HTML widget with live slider bindings |
| `verify-model` | `techfig verify-model <spec.json> [--samples <N>]` | Cross-check spec model functions between Python and Node |
| `explain` | `techfig explain <doc.md> -o <out.html>` | Assemble a standalone interactive explainer page from markdown |
| `critique` | `techfig critique --input <spec.json> --svg-output <out.svg> [--fix]` | Deterministic SVG geometric critique (alignment, overlaps, layout) |
| `critique --html` | `techfig critique --html <widget.html> [--json]` | Playwright-based inert-control, readout, and text-collision validation |
| `slides` | `techfig slides --input <slides.json> -o <out.pptx>` | Generate PowerPoint presentations |
| `tikz` | `techfig tikz --mode [chart\|diagram] ... -o <out.tex>` | Export charts or diagrams to LaTeX/TikZ |
| `sketch` | `techfig sketch <image> -o <out.svg>` | Convert whiteboard/paper sketch to clean SVG |
| `animate` | `techfig animate <spec.json> -o <out.mp4>` | Render diagram animation via Manim |
| `animate-svg` | `techfig animate-svg <input.svg> -o <out.svg>` | Apply CSS/SMIL animations to existing SVG |
| `panel` | `techfig panel <spec.json> -o <out>` | Multi-panel figure generation |
| `equation` | `techfig equation "<latex>" -o <out>` | Render LaTeX math equations |
| `math-widget` | `techfig math-widget <spec.json> -o <out.html>` | Generate interactive math formula widget |
| `components` | `techfig components [list\|search\|index\|render\|stats\|show]` | Manage standard and lab-folder component libraries |
| `styles` | `techfig styles` | List available style presets |
| `prompt` | `techfig prompt` | Print vision system prompt for sketch interpretation |
| `config` | `techfig config [list\|set] ...` | Manage configuration settings |
| `export` | `techfig export <in> -o <out> [--dpi <N>]` | Convert between figure formats |
| `batch` | `techfig batch --input <manifest> [-o <dir>]` | Batch render from manifest |

## Parametric Specs and Interactive Explainers

TechFig diagram specs support parametric reactive bindings, restricted-Python mathematical models, and interactive HTML explainer generation:

- **`params`**: Top-level parameter list with continuous ranges (`min`, `max`, `step`, `value`, `label`, `unit`) or discrete state toggles (`kind: "state"`, `options: [...]`).
- **`{{expr}}`**: Expressions bound to SVG geometry, text, or styling, evaluated in both Python and client-side JavaScript.
- **`model`**: Python model module (`{"file": "model.py"}` or `{"source": "..."}`) exposing functions by name to `{{expr}}` bindings and transpiled to vanilla JS. Cross-checked numerically with Node via `techfig verify-model`.
- **`readout`**: Element displaying live formatted numeric values with optional boolean verdict labels and styling (`tf-verdict-true` / `tf-verdict-false`).
- **`state` & `visible_when`**: Discrete state parameters rendered as `<select>` controls. Any element or connection can specify `"visible_when": "{{expr}}"` to conditionally toggle visibility.
- **Static outputs unchanged**: Specs with parametric bindings continue to render statically to SVG via `techfig reconstruct` evaluated at declared default parameter values.

### Execution Model and Security

- **Restricted AST Subset**: Expressions and model code are checked against a strict AST node allow-list. Only basic arithmetic, whitelisted `math` functions, assignments, bounded loops (`MAX_LOOP_ITERATIONS = 100,000`), and conditionals are allowed. Dunders (`__...`), arbitrary attribute access, imports, annotations, and unsupported builtins are rejected. Sequence allocations and power operations are size-bounded.
- **Path Confinement**: Referenced model and figure files (`model.file`, explain `file:`) are strictly confined to the spec directory (`resolved.is_relative_to(base)`); directory traversal (`..`) and absolute path escapes outside the spec directory are rejected.
- **Residual Risks**: Execution does not enforce hard wall-clock process timeouts or OS-level container isolation. Author-supplied model code runs in-process in the Python interpreter. Consequently, diagram specs and models should be treated as executable code and loaded only from trusted sources.
- **Math Rendering Note**: The HTML explainer generator uses a built-in lightweight markdown formatter when the optional `markdown` package is not installed and does not bundle a client-side math renderer (such as KaTeX or MathJax). LaTeX expressions (`$...$` and `$$...$$`) in explainer markdown are currently rendered as raw text.

See `examples/arc_thin_film/` for a complete working example of a single-layer anti-reflective coating model, parametric cross-section, live reflectance plot, and explainer page.

## Styles

Built-in presets: `nature`, `science`, `dark`, `presentation`, `minimal`, `metal`, `semiconductor`, `glass`, `dielectric`, `substrate`

Custom styles via YAML files — see `templates/styles/example_custom.yaml`.

## Examples

See the `examples/` directory for working scripts, sample data, and demos:

- `examples/arc_thin_film/` — Interactive anti-reflective coating explainer with restricted-Python model, live spectral plot, cross-section diagram, and build script.
- `examples/optical_diagram_spec.json` — Optical bench setup and ray diagram demo.
- `examples/organic_figures/` — Freehand drawing tools (`polygon`, `pen`, `compound` union/cut) for clouds, trees, and bacteria.
- `examples/hybrid_figures/` — Vector labels with generated 3D/photoreal insets using `type: image`.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

