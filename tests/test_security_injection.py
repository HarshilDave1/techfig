"""Security tests for HTML/JS injection prevention (t_69d4945a)."""
import re

from techfig.engines.explain import render_explainer
from techfig.engines.interactive_svg import create_interactive_svg


HOSTILE_PAYLOAD = "</script><script>window.PWNED=1</script>"
HOSTILE_XML = "</text><script>window.PWN_XL=1</script><text>"


def test_param_label_and_unit_injection(tmp_path):
    spec = {
        "canvas": {"width": 400, "height": 300},
        "params": [
            {
                "name": "slider1",
                "min": 0,
                "max": 10,
                "step": 1,
                "value": 5,
                "label": f"Length {HOSTILE_PAYLOAD}",
                "unit": f"cm {HOSTILE_PAYLOAD}",
            }
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 50, "y": 50, "w": "{{slider1 * 10}}", "h": 20}
        ],
    }
    out_file = tmp_path / "widget.html"
    create_interactive_svg(spec, str(out_file), title="Safe Title")
    html = out_file.read_text(encoding="utf-8")

    assert "<script>window.PWNED=1</script>" not in html
    assert html.count("</script>") == 1
    assert "&lt;/script&gt;&lt;script&gt;window.PWNED=1&lt;/script&gt;" in html


def test_state_param_options_injection(tmp_path):
    spec = {
        "canvas": {"width": 400, "height": 300},
        "params": [
            {
                "name": "mode",
                "kind": "state",
                "options": [HOSTILE_PAYLOAD, "normal"],
                "value": HOSTILE_PAYLOAD,
                "label": "Mode Selection",
            }
        ],
        "elements": [
            {"type": "box", "id": "b1", "x": 50, "y": 50, "w": 50, "h": 20}
        ],
    }
    out_file = tmp_path / "widget.html"
    create_interactive_svg(spec, str(out_file))
    html = out_file.read_text(encoding="utf-8")

    assert "<script>window.PWNED=1</script>" not in html
    assert html.count("</script>") == 1
    # Check that in the script tag, the JSON uses \\u003c
    script_part = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script_part is not None
    assert "<script>" not in script_part.group(1)
    assert "</script>" not in script_part.group(1)
    assert "\\u003c" in script_part.group(1)


def test_page_title_injection(tmp_path):
    spec = {
        "canvas": {"width": 400, "height": 300},
        "elements": [{"type": "box", "x": 10, "y": 10, "w": 20, "h": 20}],
    }
    out_file = tmp_path / "widget.html"
    hostile_title = f"Figure {HOSTILE_PAYLOAD}"
    create_interactive_svg(spec, str(out_file), title=hostile_title)
    html = out_file.read_text(encoding="utf-8")

    assert "<script>window.PWNED=1</script>" not in html
    assert html.count("</script>") == 1
    assert "&lt;/script&gt;&lt;script&gt;window.PWNED=1&lt;/script&gt;" in html


def test_native_plot_labels_and_series_injection(tmp_path):
    hostile_xl = "</text><script>window.PWN_XL=1</script><text>"
    hostile_yl = "</text><script>window.PWN_YL=1</script><text>"
    hostile_title = "</text><script>window.PWN_TITLE=1</script><text>"
    hostile_cap = "</text><script>window.PWN_CAP=1</script><text>"
    hostile_color = 'red"><script>window.PWN_COL=1</script><path x="'
    hostile_dash = '5,5"><script>window.PWN_DASH=1</script><path x="'

    spec = {
        "canvas": {"width": 600, "height": 400},
        "params": [{"name": "k", "min": 1, "max": 5, "step": 1, "value": 2}],
        "elements": [
            {
                "type": "plot",
                "id": "myplot",
                "x": 0,
                "y": 0,
                "w": 400,
                "h": 300,
                "xlabel": hostile_xl,
                "ylabel": hostile_yl,
                "title": hostile_title,
                "text": hostile_cap,
                "series": [
                    {
                        "id": 's0"><script>window.PWN_ID=1</script><path x="',
                        "x": [0, 1, 2],
                        "y": "{{[0, k, 2*k]}}",
                        "color": hostile_color,
                        "stroke_dash": hostile_dash,
                    }
                ],
            }
        ],
    }
    out_file = tmp_path / "widget.html"
    create_interactive_svg(spec, str(out_file))
    html = out_file.read_text(encoding="utf-8")

    assert "<script>window.PWN_XL=1</script>" not in html
    assert "<script>window.PWN_YL=1</script>" not in html
    assert "<script>window.PWN_TITLE=1</script>" not in html
    assert "<script>window.PWN_CAP=1</script>" not in html
    assert "<script>window.PWN_COL=1</script>" not in html
    assert "<script>window.PWN_DASH=1</script>" not in html
    assert "<script>window.PWN_ID=1</script>" not in html
    assert html.count("</script>") == 1


def test_explain_frontmatter_and_captions_injection():
    md = f"""---
title: Explainer {HOSTILE_PAYLOAD}
subtitle: Subtitle {HOSTILE_PAYLOAD}
status: established {HOSTILE_PAYLOAD}
---

# Introduction

```techfig interactive caption="{HOSTILE_PAYLOAD}"
{{
  "canvas": {{"width": 400, "height": 300}},
  "params": [{{"name": "p", "min": 0, "max": 10, "step": 1, "value": 2}}],
  "elements": [{{"type": "circle", "x": 100, "y": 100, "r": "{{{{p * 5}}}}"}}]
}}
```

```techfig caption="{HOSTILE_PAYLOAD}"
{{
  "canvas": {{"width": 200, "height": 100}},
  "elements": [{{"type": "box", "x": 20, "y": 20, "w": 30, "h": 20}}]
}}
```
"""
    html = render_explainer(md)

    assert "<script>window.PWNED=1</script>" not in html
    # Only the runtime script tag
    assert html.count("</script>") == 1


def test_explain_ref_injection_and_javascript_protocol():
    md = f"""---
title: Ref Test
refs:
  - n: 1
    doi: "10.1038/s41586-020-2649-2"
    text: "Valid Ref {HOSTILE_PAYLOAD}"
  - n: 2
    url: "javascript:window.PWNED_JS=1"
    text: "Hostile JS URL"
  - n: 3
    url: "https://example.com/paper"
    text: "Hostile Tag in Text {HOSTILE_PAYLOAD}"
  - n: 4
    url: "http://example.com/test?a=1&b=2{HOSTILE_PAYLOAD}"
    text: "Hostile URL {HOSTILE_PAYLOAD}"
---

Citation [^1] and [^2] and [^3] and [^4].
"""
    html = render_explainer(md)

    assert "<script>window.PWNED=1</script>" not in html
    assert "href=\"javascript:" not in html
    assert "href='javascript:" not in html
    assert "javascript:window.PWNED_JS=1" not in html
    assert html.count("</script>") == 0
