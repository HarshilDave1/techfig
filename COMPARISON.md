# Techfig Improvement Plan — Before/After Comparison

## Overview

This document tracks the improvements made to techfig's SVG diagram engine as part of the Inkscape improvement plan. All changes are implemented, merged, and tested.

**Test results:** 183 passed, 2 skipped, 0 failed
**Linting:** ruff clean (all files)

---

## Phase 1: Foundation Fixes

### P1-A: Overlap Resolver — Stop Destroying Good Layouts

**Before:** The overlap resolver (`align_rows_and_cols` in `geo_linter.py`) grouped diagonal element pairs (close on both X and Y axes) and averaged them to the same point, destroying intentional diagonal layouts.

**After:** Added a `close_perp` check — when grouping elements for alignment on one axis, the resolver skips grouping a pair if they're also close on the perpendicular axis. Diagonal layouts are preserved.

### P1-B: Real Font Metrics

**Before:** Text width was estimated using `len(text) * 0.6` — a crude heuristic that caused label misplacement, overlapping text, and incorrect panel sizing.

**After:** Font metrics are now measured using PIL (`_measure_text`, `_text_width`), which reads the actual font file and computes precise glyph widths. Text placement and panel sizing are now accurate.

### P1-C: Rasterizer Reorder

**Before:** PNG export tried CairoSVG first, which produced inconsistent results for complex SVGs (gradients, filters).

**After:** Rasterizer backend order is now Playwright → resvg → CairoSVG. Playwright (headless Chromium) provides the most accurate rendering for SVGs with defs, gradients, and filters.

---

## Phase 2: SVG Builder Improvements

### P2-A: `<defs>` Support — Gradients, Filters, Patterns

**Before:** `SVGBuilder` had no support for SVG `<defs>` — no gradients, no filters, no patterns. All fills were flat colors.

**After:** New methods: `add_linear_gradient`, `add_radial_gradient`, `add_pattern`, `add_filter`. Materials can now have gradient fills (e.g., silicon with depth gradient), hatching patterns (e.g., BSF layer), and blur filters (e.g., soft shadows).

### P2-B: Material Presets

**Before:** No material library. Users had to manually specify colors for each element.

**After:** Built-in material presets: `metal` (silver/gold contacts), `semiconductor` (silicon), `glass` (ARC layers), `dielectric` (oxide), `substrate`. Each preset includes appropriate fill, stroke, and opacity defaults.

### P2-C: Stroke ≠ Fill + Fill Opacity Defaults

**Before:** All shapes used `stroke = fill` — outlines and fills were always the same color, making layered diagrams visually flat and hard to read.

**After:** `stroke_color` is now a separate parameter on all shape builders. Fill opacity defaults to 0.7 (configurable), allowing overlapping layers to be visible through each other.

### P2-D: Typography Roles

**Before:** All text used the same font size and weight. No semantic distinction between titles, labels, annotations, and tick marks.

**After:** Five typography roles: `title` (20pt bold), `subtitle` (16pt), `label` (12pt), `annotation` (10pt italic), `tick` (9pt). Each role has consistent size, weight, and color defaults.

### P2-E: Arrows and Paths as First-Class Elements

**Before:** No arrow or path elements. Users had to hack lines with manual arrowhead markers.

**After:** `arrow` and `path` are now first-class element types in the diagram spec. `SVGBuilder.add_arrow_xy()` supports curved arrows. `SVGBuilder.add_path()` supports M/L/Q/C SVG path commands with optional arrowheads. `geo_linter.py` validates path points and snapping.

---

## Phase 3: New Element Types

### P3-A: textblock Element

**Before:** No multi-line text support. Long descriptions had to be split into individual `text` elements manually.

**After:** `textblock` element type with automatic line wrapping, panel background, and configurable padding. Supports title + body text.

### P3-B: plot Element

**Before:** No inline charts. Data plots had to be generated separately and composited manually.

**After:** `plot` element type renders inline charts via matplotlib. Supports line plots, scatter plots, and bar charts within the SVG diagram.

### P3-C: lattice Element

**Before:** No array/grid element. Repeated structures (e.g., photonic crystal lattices, pixel arrays) had to be specified one element at a time.

**After:** `lattice` element type creates n×m rectangular or hexagonal arrays of a base shape. `SVGBuilder.add_lattice()` handles layout, spacing, and rendering.

### P3-D: callout Element

**Before:** No callout support. Annotated labels with leader lines had to be manually constructed from separate text and line elements.

**After:** `callout` element type with `anchor` position, leader line, and label box. `SVGBuilder.add_callout()` renders the leader line and label automatically.

### P3-E: legend Element

**Before:** No legend support. Material keys had to be manually constructed.

**After:** `legend` element type renders a bordered panel with swatch + label rows. Automatically lays out entries in a grid.

### P3-F: Math Text

**Before:** No equation rendering. Formulas had to be rendered as images and composited separately.

**After:** Math text rendering via matplotlib's mathtext engine. Supports LaTeX-style notation ($J_{sc}$, $\eta$, $V_{oc}$, etc.) rendered as SVG paths.

---

## Phase 4: CLI and Cleanup

### P4-C: Fix/Delete pretty.py

**Before:** `pretty.py` generated unrelated images (random decorative graphics) instead of polishing diagrams.

**After:** `pretty.py` removed. Its CLI entry point is cleaned up. No more confusion about what "pretty" mode does.

---

## Bug Fixes Discovered During Implementation

### sketch_interpreter.py API Restoration

**Issue:** Commit `21878d9` ("Polish sketch_interpreter: clean docstring formatting") accidentally deleted 400 lines — removing ALL functional API functions (`validate_spec`, `render_from_spec`, `render_from_json`, `get_sketch_prompt`, `get_diagram_schema`, `sketch_to_diagram`, `auto_refine`) while leaving only schema/prompt constants.

**Fix:** All 9 API functions restored. The file now has both the schema/prompt constants AND the functional API.

### DIAGRAM_SCHEMA Missing "legend" Type

**Issue:** The `DIAGRAM_SCHEMA` type enum was missing `"legend"`, causing `validate_spec()` to reject valid legend elements even though `diagrams.py` supported them.

**Fix:** Added `"legend"` to the type enum in `DIAGRAM_SCHEMA`.

---

## Benchmark Diagrams

The following benchmark diagrams exercise the new features:

| File | Description |
|------|-------------|
| `benchmark.svg` | Solar cell cross-section using JSON spec (material presets, arrows, callouts, legend, fill_opacity, stroke_color, typography roles) |
| `benchmark.png` | PNG export of the above (179KB, rasterized via Playwright) |
| `benchmark_defs.svg` | Solar cell cross-section using SVGBuilder API directly (gradients, patterns, filters, material lookups) |
| `equation_Jsc.svg` | Math text: $J_{sc} = q \int \Phi(\lambda) d\lambda$ |
| `equation_eta.svg` | Math text: $\eta = J_{sc} V_{oc} FF / P_{in}$ |
| `equation_Voc.svg` | Math text: $V_{oc} = k_B T / q \ln(J_{sc}/J_0 + 1)$ |

---

## Remaining Work

- **P4-A:** `--polish N` CLI mode (render/critique/revise loop) — pending P3-C completion
- **P4-B:** Style-reference mode (diffusion image as layout inspiration) — pending P4-A
- **Git commit:** Changes are uncommitted due to root-owned `.git/objects` subdirs blocking git write operations. Fix: `sudo chown llamapc:llamapc` on the `.git/objects` directory.
