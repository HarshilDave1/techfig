"""Tests for T2: interactive SVG runtime (expr_to_js + create_interactive_svg)."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from techfig.engines.interactive_svg import create_interactive_svg
from techfig.engines.model_transpile import expr_to_js
from techfig.engines.params import safe_eval

NODE = shutil.which("node")


def make_spec():
    return {
        "canvas": {"width": 800, "height": 600},
        "style": {"name": "nature"},
        "params": [
            {
                "name": "d", "min": 0, "max": 10, "step": 0.5, "value": 1.5,
                "label": "Thickness", "unit": "nm",
            },
            {"name": "theta", "min": 0, "max": 90, "step": 1, "value": 30},
        ],
        "elements": [
            {
                "type": "box", "id": "slab", "x": 0, "y": 0, "w": 300,
                "h": "{{2*d}}", "text": "slab", "color": "primary",
            },
            {"type": "circle", "x": 200, "y": -100, "r": "{{20 + 4*theta}}"},
            {"type": "text", "x": -200, "y": -200, "text": "n = {{fmt(d, '.2f')}}"},
            {"type": "line", "x1": -300, "y1": 250, "x2": "{{300 - d*10}}", "y2": 250},
            {"type": "path", "points": "{{[[0, 0], [d, 100], [2*d, 0]]}}"},
        ],
        "connections": [],
    }


def build_widget(tmp_path, spec=None):
    spec = spec or make_spec()
    out = tmp_path / "widget.html"
    path = create_interactive_svg(spec, str(out), title="Demo")
    return Path(path).read_text()


def get_bindings(page):
    m = re.search(r"var __TF_BINDINGS = (\[.*?\]);\n", page, re.DOTALL)
    assert m, "bindings table not found"
    return json.loads(m.group(1))


class TestExprToJs:
    def test_pow(self):
        assert expr_to_js("a**2") == "Math.pow(a, 2)"

    def test_math_call(self):
        assert expr_to_js("math.sin(x)") == "Math.sin(x)"

    def test_math_const(self):
        assert expr_to_js("math.pi") == "Math.PI"

    def test_ternary(self):
        assert expr_to_js("1 if x > 0 else -1") == "((x > 0) ? 1 : (-1))"

    def test_fmt(self):
        assert expr_to_js("fmt(x, '.3f')") == '__fmt(x, ".3f")'

    def test_floor_div(self):
        assert expr_to_js("a // b") == "Math.floor(a / b)"

    def test_chained_compare(self):
        assert expr_to_js("0 < x < 10") == "(0 < x && x < 10)"

    def test_bool_ops(self):
        assert expr_to_js("a and not b") == "(a && (!b))"

    def test_len(self):
        assert expr_to_js("len(xs)") == "xs.length"

    def test_list_literal(self):
        assert expr_to_js("[1, 2, 3]") == "[1, 2, 3]"

    def test_subscript(self):
        assert expr_to_js("xs[0]") == "xs[0]"

    def test_arith(self):
        assert expr_to_js("2 * d") == "(2 * d)"

    def test_unsupported_raises(self):
        for bad in ("lambda: 1", "x.y", "{'a': 1}", "x[1:2]", "math.erf(x)"):
            with pytest.raises(ValueError):
                expr_to_js(bad)


class TestCreateInteractiveSvg:
    def test_creates_html(self, tmp_path):
        page = build_widget(tmp_path)
        assert page.startswith("<!DOCTYPE html>")
        assert "<svg" in page

    def test_one_range_input_per_param(self, tmp_path):
        page = build_widget(tmp_path)
        inputs = re.findall(r'<input type="range" class="tf-param"[^>]*>', page)
        assert len(inputs) == 2
        d_input = [s for s in inputs if 'data-name="d"' in s][0]
        for frag in ('min="0"', 'max="10"', 'step="0.5"', 'value="1.5"'):
            assert frag in d_input
        assert "Thickness" in page
        assert re.search(r'<output[^>]*class="tf-value"[^>]*>1\.5 nm</output>', page)

    def test_no_external_resources(self, tmp_path):
        page = build_widget(tmp_path)
        assert "<script src" not in page
        assert "<link" not in page
        for m in re.finditer(r"https?://[^\"'\s]+", page):
            assert "www.w3.org" in m.group(0), m.group(0)

    def test_auto_ids_assigned(self, tmp_path):
        page = build_widget(tmp_path)
        assert 'id="tf-el-1"' in page  # circle had no id

    def test_bindings_table_embedded(self, tmp_path):
        page = build_widget(tmp_path)
        bindings = get_bindings(page)
        # height binding for the {{2*d}} bound box
        assert any(b["attr"] == "height" and b["js"] == "(2 * d)" for b in bindings)
        # box y follows the bound height (center-origin convention)
        assert any(b["attr"] == "y" and b["sel"] == "rect" for b in bindings)
        assert any(b["attr"] == "r" and b["sel"] == "circle" for b in bindings)
        # text interpolation -> textContent
        assert any(
            b["attr"] == "textContent" and b["js"] == '"n = " + (__fmt(d, ".2f"))'
            for b in bindings
        )
        # line coordinate binding -> recomputed d attribute
        assert any(
            b["attr"] == "d" and b["js"].startswith("`M ${(-300)}") for b in bindings
        )
        # path points binding -> __tf_d(...) array-to-d helper
        assert any(b["attr"] == "d" and "__tf_d(" in b["js"] for b in bindings)

    def test_no_params_spec(self, tmp_path):
        spec = {
            "canvas": {"width": 400, "height": 300},
            "elements": [{"type": "box", "id": "b", "x": 0, "y": 0, "w": 100, "h": 50}],
        }
        page = build_widget(tmp_path, spec)
        assert '<input type="range"' not in page
        assert "<svg" in page

    def test_text_label_moved_by_resolver_keeps_id(self, tmp_path):
        # Two stacked text labels: the overlap resolver moves the second one,
        # so the SVG id (post-resolver) and the spec binding (pre-resolver)
        # disagree. The transform approach keeps the label connected via its
        # group id; assert the binding references the resolved id, not the
        # raw spec position.
        spec = {
            "canvas": {"width": 600, "height": 400},
            "params": [{"name": "d", "min": 0, "max": 10, "step": 0.5, "value": 1.5}],
            "elements": [
                {"type": "text", "x": 0, "y": 10, "text": "aaa"},
                {"type": "text", "x": 0, "y": "{{10}}", "text": "bbb"},
            ],
        }
        page = build_widget(tmp_path, spec)
        bindings = get_bindings(page)
        assert any(b["attr"] == "transform" for b in bindings)

    def test_unsupported_binding_target_raises(self, tmp_path):
        spec = {
            "canvas": {"width": 400, "height": 300},
            "params": [{"name": "d", "min": 0, "max": 10, "step": 0.5, "value": 1.5}],
            "elements": [
                {"type": "pen", "points": "{{[[0, 0], [d, 100]]}}"},
            ],
        }
        with pytest.raises(ValueError, match="pen"):
            create_interactive_svg(spec, str(tmp_path / "x.html"))


@pytest.mark.skipif(NODE is None, reason="node not available")
class TestNodeRuntime:
    def _extract_script(self, page):
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", page, re.DOTALL)
        assert scripts
        return scripts[-1]

    def test_node_check(self, tmp_path):
        page = build_widget(tmp_path)
        f = tmp_path / "runtime.js"
        f.write_text(self._extract_script(page))
        res = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr

    def test_smoke_and_parity(self, tmp_path):
        page = build_widget(tmp_path)
        harness = (
            "global.window = {__tf: null};\n"
            "global.document = {"
            "querySelectorAll: function () { return []; }, "
            "getElementById: function () { return null; }};\n"
            + self._extract_script(page)
            + "\nvar __out = {"
            "fmt_f: window.__tf.fmt(0.1234, '.3f'), "
            "fmt_pct: window.__tf.fmt(0.5, '.1%'), "
            "fmt_e: window.__tf.fmt(12345.678, '.2e'), "
            "fmt_d: window.__tf.fmt(3, 'd'), "
            "height: (function () {"
            " var b = window.__tf.bindings.filter("
            "function (x) { return x.attr === 'height'; })[0];"
            " return b ? new Function('d', 'return (' + b.js + ')')(1.5) : null; })(),"
            "d_default: window.__tf.params.d};\n"
            "console.log(JSON.stringify(__out));\n"
        )
        f = tmp_path / "harness.js"
        f.write_text(harness)
        res = subprocess.run([NODE, str(f)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        out = json.loads(res.stdout)
        # __fmt parity with Python format()
        assert out["fmt_f"] == format(0.1234, ".3f")
        assert out["fmt_pct"] == format(0.5, ".1%")
        assert out["fmt_e"] == format(12345.678, ".2e")
        assert out["fmt_d"] == format(3, "d")
        # binding-eval smoke: JS value == Python safe_eval value
        assert abs(out["height"] - safe_eval("2 * d", {"d": 1.5})) < 1e-9
        assert out["d_default"] == 1.5


class TestCli:
    def test_cli_interactive(self, tmp_path):
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(make_spec()))
        out = tmp_path / "widget.html"
        res = subprocess.run(
            [
                sys.executable, "-m", "techfig.cli", "interactive",
                str(spec_path), "-o", str(out), "--title", "Demo",
            ],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        assert out.exists()
        assert "Demo" in out.read_text()
