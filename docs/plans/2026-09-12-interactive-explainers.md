# Plan: Parametric / interactive explainer support in techfig

Branch: `feat/interactive-explainers`. Orchestrated by scientist profile; implemented by coder profile via `hermes -p coder chat --oneshot`.

## Goal
One JSON spec → (a) static SVG at default params (existing pipeline, unchanged), (b) a self-contained HTML widget where sliders re-evaluate bound attributes live. Then a page assembler (`techfig explain`) that turns markdown + spec blocks into a single-file explainer, and an HTML critique gate.

## Architecture
- `techfig/engines/params.py` — parse `params`, evaluate `{{expr}}` bindings in Python (safe AST-restricted evaluator), resolve a spec to a concrete spec at a given param dict.
- `techfig/engines/model_transpile.py` — restricted Python → JS transpiler for model functions; `verify_model()` cross-checks numerics.
- `techfig/engines/interactive_svg.py` — emit SVG with `data-tf-bind` attributes + inline vanilla-JS runtime (no CDN) + slider UI.
- `techfig/engines/explain.py` — markdown + fenced ```techfig blocks → single HTML.
- `geo_linter` / `critique --html` — Playwright-based inert-control + readout checks.

## Tasks (each: TDD, pytest green, ruff clean, one commit)

### T1 params + expression evaluator
- `params` top-level list: `{name, min, max, step, value, label?, unit?}`.
- Any string field matching `^\{\{(.+)\}\}$` (whole-field) or containing `{{...}}` (text interpolation) is a binding.
- Safe evaluator: `ast` whitelist (numbers, names, BinOp, UnaryOp, Compare, IfExp, Call to `math.*` and a small helper set `abs,min,max,round,fmt(x, spec)`), no attribute access beyond `math.`, no subscripts of non-params.
- `resolve_spec(spec, param_values=None) -> concrete spec` (params default from `value`), returns also `bindings: list[(element_index_or_conn, field, expr)]`.
- Wire into `render_from_spec`: call `resolve_spec` before validation so existing pipeline is untouched. Add `params` to `DIAGRAM_SCHEMA` (both places — see pitfall #16 in skill).
- Tests: eval whitelist rejects `__import__`, attribute, lambda; text interpolation; static render of a spec with bindings equals render of hand-substituted spec.

### T2 interactive SVG runtime
- `create_interactive_svg(spec, output_path, title=None) -> path`: renders concrete SVG (defaults), then post-processes: each bound element gets `id` (auto if missing) and JS bindings table `[{id, attr, jsExpr}]`. Expressions transpiled Py→JS with `model_transpile.expr_to_js` (shared with T3; do the minimal expression subset here: arithmetic, `**`→`Math.pow`, `math.X`→`Math.X`, ternary IfExp, comparisons, `fmt(x,'.3f')`→helper).
- Output: single HTML file: `<style>` (CSS vars from style preset: `--tf-primary` etc.), controls `<div>` with one `<input type=range>` + label + value readout per param, inline `<svg>`, `<script>` runtime (≤200 lines, no deps). Text bindings set `textContent`; attr bindings `setAttribute`. Path/line coordinates: support `x1,y1,x2,y2,cx,cy,r,x,y,width,height,opacity,fill`, and for `path`/`polyline` elements support `points` binding (array expr → `d`).
- CLI: `techfig interactive spec.json -o out.html`.
- Tests: HTML contains one range input per param; `node --check` on extracted script passes (skip if node missing); binding table JSON parses; a snapshot-ish test that a `{{thickness}}`-bound `height` attr appears in bindings.

### T3 model functions + transpiler + verify
- Spec `model: {file: "model.py"}` or `model: {source: "..."}`. Functions defined in restricted Python (def, return, assignments, for-range loops, if/else, while, lists, math.*, arithmetic, comparisons, augmented assign, tuple unpack of 2). Expose to bindings by name.
- `expr_to_js`, `function_to_js`, `module_to_js`. `**`→`Math.pow`, `//`→`Math.floor(a/b)`, `range`→for-loop, list append→push, `len`→`.length`, `abs/min/max/sum` mapped.
- `verify_model(source, n_samples=50, seed=0, tol=1e-9) -> report`: evaluate each function at random params (within param ranges) in Python and Node (`node -e`), compare. CLI `techfig verify-model spec.json`. Skip cleanly if `node` absent.
- Tests: transpile a thin-film Airy reflectance function and verify agreement.

### T4 live `plot` element
- In interactive mode, a `plot` element with `series: [{x: "{{xs}}", y: "{{ys}}"}]` renders as native SVG axes (reuse tick/label text pipeline; linear scales only) + `<path>` per series, all bound. Static mode unchanged (matplotlib). Axis ranges: fixed from spec (`xlim`,`ylim`) or auto at defaults with 10% pad (frozen so lines move, not axes).
- Tests: path `d` has N points; ylim respected.

### T5 readout + state elements
- `readout`: `{type, x, y, expr, format, verdict:{expr,true,false}}` → text bound; verdict appended with class `tf-verdict-true/false`.
- `state` param kind: `{name, kind:"state", options:[...], value}` renders as `<select>` (or radio); elements gain optional `visible_when` expr → `display:none` when false. Static mode: honour `visible_when` at defaults.
- Register both in enum + engine.

### T6 `techfig explain` page assembler
- Input markdown with front-matter (`title`, `status`, `refs: [{n, doi|url, text}]`) and fenced blocks ` ```techfig {interactive} ` containing spec JSON or a path. Output single HTML: inlined figures (namespaced ids `fig1-…`), interactive figures embed runtime once, numbered references list with hrefs, an epistemic-status badge per section (`> status: Established|Active|Speculative`). Markdown via `markdown` lib if present else minimal fallback (headings, paragraphs, lists, links, inline code).
- CLI `techfig explain doc.md -o page.html`. No `<script src>`, no remote CSS.
- Tests: two figures → unique ids; refs render; interactive runtime present once.

### T7 `critique --html`
- `lint_html(path)`: with Playwright (optional dep, skip if absent): load page; assert every `.tf-readout` non-empty and not `–`; for each range input set to min then max, screenshot SVG bbox, pixel-diff → flag inert controls; at min/mid/max compute text bbox overlaps via `getBBox` → report collisions. JSON report `{score, issues, inert_controls, overlaps_at:{...}}`.
- CLI `techfig critique --html page.html`.
- Tests: unit test on a fabricated page with a dead slider (skipif no playwright).

### T8 docs + example
- `examples/arc_thin_film/`: spec + model.py (single-layer ARC reflectance vs wavelength, params n1, d, angle), `explainer.md`. Build script in README. Update README command table. Bump version 1.1.0 in both places.

## Gates
- Every task: `.venv/bin/python -m pytest tests -q` green, `.venv/bin/ruff check techfig tests` clean (scope to touched files if pre-existing failures), commit on branch.
- Orchestrator reviews diff per task before dispatching the next.
