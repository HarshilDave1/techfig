"""Tests for T6: techfig explain page assembler."""
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from techfig.engines.explain import assemble_explainer_page, render_explainer
from techfig.engines.interactive_svg import render_interactive_fragment, runtime_js

NODE = shutil.which("node")


class FigureCounter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.figures = []

    def handle_starttag(self, tag, attrs):
        if tag == "figure":
            self.figures.append(dict(attrs))


class TestExplainAssembly:
    def test_fixture_all_spec_requirements(self, tmp_path):
        """Fixture md with two static figures and one interactive ->

        - ids unique across figures (regex all id= values)
        - <script> runtime appears exactly once
        - refs render with doi href
        - [^1] becomes a link
        - status badge present
        - no src= on any script tag
        - page validates enough that html.parser finds N <figure> tags
        """
        md_text = """---
title: Optical Metamaterials Explainer
subtitle: Principles and Resonance
status: Active
style: nature
refs: [{"n": 1, "doi": "10.1038/s41586-020-2649-2", "text": "Smith et al., Nature 2020"}, {"n": 2, "url": "https://example.com/optics", "text": "Optics Handbook"}]
---

## 1. Introduction
> status: Established

Electromagnetic metamaterials enable unprecedented control over wavefronts[^1].

```techfig
{
  "canvas": {"width": 400, "height": 300},
  "elements": [
    {"type": "box", "id": "substrate", "x": 200, "y": 150, "w": 120, "h": 50, "text": "Substrate"}
  ]
}
```
Caption: Figure 1: Substrate schematic.

## 2. Tunable Resonance
> status: Active

By adjusting layer thickness, resonance frequency shifts systematically[^2].

```techfig interactive
{
  "params": [
    {"name": "d", "min": 10, "max": 100, "step": 5, "value": 50, "label": "Thickness", "unit": "nm"}
  ],
  "canvas": {"width": 400, "height": 300},
  "elements": [
    {"type": "box", "id": "resonator", "x": 200, "y": 150, "w": "{{2*d}}", "h": 60, "text": "Resonator"}
  ]
}
```
Caption: Figure 2: Interactive resonance adjustment.

## 3. High-Q Regimes
> status: Speculative

Emergent topological states remain an active frontier.

```techfig
{
  "canvas": {"width": 400, "height": 300},
  "elements": [
    {"type": "box", "id": "cavity", "x": 200, "y": 150, "w": 100, "h": 70, "text": "Cavity"}
  ]
}
```
Caption: Figure 3: High-Q cavity geometry.
"""
        doc_file = tmp_path / "doc.md"
        doc_file.write_text(md_text, encoding="utf-8")
        out_html = tmp_path / "page.html"

        result_path = assemble_explainer_page(doc_file, out_html)
        assert Path(result_path).exists()
        html = out_html.read_text(encoding="utf-8")

        # 1. IDs unique across figures
        ids = re.findall(r'\bid=["\']([^"\']+)["\']', html)
        assert len(ids) > 0, "Expected id attributes in HTML"
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {[x for x in ids if ids.count(x) > 1]}"

        # 2. <script> runtime appears exactly once
        script_tags = re.findall(r"<script(?:\s+[^>]*)?>", html)
        assert len(script_tags) == 1, f"Expected 1 <script> tag, found {len(script_tags)}"
        assert "function __fmt" in html

        # 3. Refs render with DOI href and url
        assert 'href="https://doi.org/10.1038/s41586-020-2649-2"' in html
        assert 'href="https://example.com/optics"' in html

        # 4. [^1] and [^2] become links
        assert '<a href="#ref-1" class="tf-cite">[1]</a>' in html
        assert '<a href="#ref-2" class="tf-cite">[2]</a>' in html

        # 5. Status badges present
        assert '<span class="tf-status tf-status-active">Active</span>' in html
        assert '<span class="tf-status tf-status-established">Established</span>' in html
        assert '<span class="tf-status tf-status-speculative">Speculative</span>' in html

        # 6. No src= on any script tag
        assert not re.search(r"<script[^>]+src=", html)

        # 7. html.parser finds N <figure> tags
        parser = FigureCounter()
        parser.feed(html)
        assert len(parser.figures) == 3

    def test_static_only_page_has_no_script(self, tmp_path):
        md_text = """---
title: Static Explainer
---

# Introduction

```techfig
{
  "canvas": {"width": 300, "height": 200},
  "elements": [{"type": "box", "id": "b1", "x": 100, "y": 100, "w": 50, "h": 50}]
}
```
"""
        html = render_explainer(md_text)
        assert "<script" not in html
        assert "<figure" in html

    def test_fenced_refs_json_block(self, tmp_path):
        md_text = """---
title: Fenced Refs Test
---

See citation[^1].

```refs json
[
  {"n": 1, "doi": "10.1000/182", "text": "DOI Handbook"}
]
```
"""
        html = render_explainer(md_text)
        assert '<a href="#ref-1" class="tf-cite">[1]</a>' in html
        assert '<li id="ref-1">' in html
        assert 'href="https://doi.org/10.1000/182"' in html

    def test_file_spec_reference(self, tmp_path):
        spec = {
            "canvas": {"width": 300, "height": 200},
            "elements": [{"type": "circle", "id": "c1", "x": 100, "y": 100, "r": 40}],
        }
        spec_file = tmp_path / "diagram.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        md_text = """---
title: External Spec Test
---

```techfig
file: diagram.json
```
Caption: Circle from external file.
"""
        doc_file = tmp_path / "doc.md"
        doc_file.write_text(md_text, encoding="utf-8")
        out_html = tmp_path / "out.html"

        assemble_explainer_page(doc_file, out_html)
        html = out_html.read_text(encoding="utf-8")
        assert "<svg" in html
        assert "Circle from external file." in html


class TestInteractiveFragment:
    def test_render_interactive_fragment(self):
        spec = {
            "params": [{"name": "r", "min": 10, "max": 50, "step": 1, "value": 20}],
            "canvas": {"width": 400, "height": 300},
            "elements": [{"type": "circle", "id": "circ", "x": 200, "y": 150, "r": "{{r}}"}],
        }
        frag = render_interactive_fragment(spec, fig_id="fig1")
        assert "svg" in frag
        assert "<svg" in frag["svg"]
        assert "controls_html" in frag
        assert 'class="tf-param"' in frag["controls_html"]
        assert "bindings_js" in frag
        assert "model_js" in frag
        # Check that fig_id namespacing is applied
        assert "fig1" in frag["controls_html"]
        assert "fig1" in frag["bindings_js"]

    def test_runtime_js_export(self):
        rjs = runtime_js()
        assert isinstance(rjs, str)
        assert "function __fmt" in rjs
        assert "window.__tf" in rjs


class TestExplainCli:
    def test_cli_explain(self, tmp_path):
        md = """---
title: CLI Test
---

# Heading

```techfig
{
  "canvas": {"width": 200, "height": 100},
  "elements": [{"type": "box", "x": 50, "y": 50, "w": 40, "h": 20}]
}
```
"""
        in_md = tmp_path / "test.md"
        in_md.write_text(md, encoding="utf-8")
        out_html = tmp_path / "test.html"

        cmd = [sys.executable, "-m", "techfig.cli", "explain", str(in_md), "-o", str(out_html)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        assert out_html.exists()
        assert "<figure" in out_html.read_text(encoding="utf-8")


class TestMultiFigureModels:
    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_multi_interactive_figure_model_namespace_collision(self, tmp_path):
        md = """---
title: Multi-Model Explainer
---

```techfig interactive
{
  "model": {"source": "def f(a):\\n    return a * 10"},
  "params": [{"name": "a", "min": 1, "max": 10, "step": 1, "value": 2}],
  "canvas": {"width": 300, "height": 200},
  "elements": [{"type": "readout", "id": "r1", "x": 50, "y": 50, "expr": "{{f(a)}}"}]
}
```

```techfig interactive
{
  "model": {"source": "def f(a):\\n    return a * 1000"},
  "params": [{"name": "a", "min": 1, "max": 10, "step": 1, "value": 2}],
  "canvas": {"width": 300, "height": 200},
  "elements": [{"type": "readout", "id": "r2", "x": 50, "y": 50, "expr": "{{f(a)}}"}]
}
```
"""
        html = render_explainer(md)
        script_match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
        assert script_match is not None, "Script block not found in explainer"
        script_content = script_match.group(1)

        harness = f"""
function makeEl() {{
  var valNode = {{ textContent: "" }};
  return {{
    querySelector: function(sel) {{ return valNode; }},
    valNode: valNode
  }};
}}
var fig1_el = makeEl();
var fig2_el = makeEl();
global.window = {{ __tf: null }};
global.document = {{
  querySelectorAll: function (sel) {{ return []; }},
  getElementById: function (id) {{
    if (id === "fig1-r1" || id === "r1") return fig1_el;
    if (id === "fig2-r2" || id === "r2") return fig2_el;
    return null;
  }}
}};
{script_content}
console.log(JSON.stringify({{
  fig1: fig1_el.valNode.textContent,
  fig2: fig2_el.valNode.textContent
}}));
"""
        harness_file = tmp_path / "multi_model_harness.js"
        harness_file.write_text(harness, encoding="utf-8")
        res = subprocess.run([NODE, str(harness_file)], capture_output=True, text=True)
        assert res.returncode == 0, f"Node run failed: {res.stderr}"
        results = json.loads(res.stdout)
        assert float(results["fig1"]) == 20
        assert float(results["fig2"]) == 2000
        assert results["fig1"] != results["fig2"]

