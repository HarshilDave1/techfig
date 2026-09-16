"""Tests for T3: restricted-Python model functions, Py->JS transpiler, verify_model."""
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from techfig.engines.interactive_svg import create_interactive_svg
from techfig.engines.model_transpile import (
    expr_to_js,
    exec_model_source,
    function_to_js,
    module_to_js,
    validate_model_source,
    verify_model,
)
from techfig.engines.params import load_model, load_model_source, safe_eval
from techfig.engines.sketch_interpreter import render_from_json, render_from_spec

NODE = shutil.which("node")

AIRY = '''def R(n0, n1, n2, d, lam):
    r01 = (n0 - n1) / (n0 + n1)
    r12 = (n1 - n2) / (n1 + n2)
    delta = 2 * math.pi * n1 * d / lam
    cosc = math.cos(2 * delta)
    num = r01**2 + r12**2 + 2 * r01 * r12 * cosc
    den = 1 + r01**2 * r12**2 + 2 * r01 * r12 * cosc
    return num / den
'''

R3 = '''def R(n1, d, lam):
    n0 = 1.0
    n2 = 1.5
    r01 = (n0 - n1) / (n0 + n1)
    r12 = (n1 - n2) / (n1 + n2)
    delta = 2 * math.pi * n1 * d / lam
    cosc = math.cos(2 * delta)
    num = r01**2 + r12**2 + 2 * r01 * r12 * cosc
    den = 1 + r01**2 * r12**2 + 2 * r01 * r12 * cosc
    return num / den
'''

SERIES = '''def series_sum(a0, r, n):
    s = 0
    for k in range(n):
        s = s + a0 * r**k
    return s
'''

HARMONIC = '''def harmonic_sum(n):
    s = 0.0
    k = 1.0
    while k <= n:
        s = s + 1.0 / k
        k += 1.0
    return s
'''

FORBIDDEN = [
    ("import", "def f():\n    import os\n    return 1\n"),
    ("attr_non_math", "def f(x):\n    return x.real\n"),
    ("lambda", "def f(x):\n    g = lambda a: a\n    return g(x)\n"),
    ("comprehension", "def f(n):\n    return [i for i in range(n)]\n"),
    ("with", "def f():\n    with open('x') as fh:\n        return 1\n"),
    ("try", "def f():\n    try:\n        return 1\n    except Exception:\n        return 2\n"),
    ("class", "class A:\n    pass\n"),
    ("arg_annotation", "def f(x: int):\n    return x\n"),
    ("return_annotation", "def f(x) -> int:\n    return x\n"),
    ("posonly_param", "def f(a, /, b):\n    return a + b\n"),
]


def airy_python(n0, n1, n2, d, lam):
    import math as m
    r01 = (n0 - n1) / (n0 + n1)
    r12 = (n1 - n2) / (n1 + n2)
    delta = 2 * m.pi * n1 * d / lam
    cosc = m.cos(2 * delta)
    num = r01 ** 2 + r12 ** 2 + 2 * r01 * r12 * cosc
    den = 1 + r01 ** 2 * r12 ** 2 + 2 * r01 * r12 * cosc
    return num / den


def r3_python(n1, d, lam):
    return airy_python(1.0, n1, 1.5, d, lam)


def make_model_spec(model=None):
    return {
        "canvas": {"width": 600, "height": 400},
        "params": [
            {"name": "n1", "min": 1.0, "max": 3.0, "step": 0.01, "value": 1.5},
            {"name": "d", "min": 0, "max": 500, "step": 1, "value": 100},
            {"name": "lam", "min": 400, "max": 900, "step": 1, "value": 550},
        ],
        "model": model if model is not None else {"source": R3},
        "elements": [
            {
                "type": "text", "id": "t", "x": 0, "y": 0,
                "text": "R = {{fmt(R(n1, d, lam), '.4f')}}",
            },
        ],
        "connections": [],
    }


def get_bindings(page):
    import re
    m = re.search(r"var __TF_BINDINGS = (\[.*?\]);\n", page, re.DOTALL)
    assert m, "bindings table not found"
    return json.loads(m.group(1))


class TestModuleToJs:
    def test_airy_function(self):
        js = module_to_js(AIRY)
        assert "function R(n0, n1, n2, d, lam) {" in js
        assert "let cosc, delta, den, num, r01, r12;" in js
        assert "Math.pow(r01, 2)" in js
        assert "Math.PI" in js
        assert "Math.cos((2 * delta))" in js
        assert "return (num / den);" in js

    def test_range_one_arg(self):
        js = module_to_js(SERIES)
        assert "for (k = 0; k < n; k += 1) {" in js
        assert "s = (s + (a0 * Math.pow(r, k)));" in js

    def test_range_const_negative_step(self):
        src = "def f():\n    for i in range(10, 0, -1):\n        pass\n    return i\n"
        js = module_to_js(src)
        assert "for (i = 10; i > 0; i += (-1)) {" in js

    def test_range_dynamic_step(self):
        src = "def f(a, b, s):\n    for i in range(a, b, s):\n        pass\n    return i\n"
        js = module_to_js(src)
        assert "((s) > 0) ? (i < b) : (i > b)" in js

    def test_range_zero_step_rejected(self):
        src = "def f():\n    for i in range(10, 0, 0):\n        pass\n"
        with pytest.raises(ValueError, match="step"):
            module_to_js(src)

    def test_append_and_len(self):
        src = (
            "def build(n):\n"
            "    xs = []\n"
            "    for i in range(n):\n"
            "        xs.append(i * i)\n"
            "    return len(xs)\n"
        )
        js = module_to_js(src)
        assert "xs.push((i * i));" in js
        assert "return xs.length;" in js

    def test_sum_reduce_in_function_body(self):
        src = "def total(xs):\n    return sum(xs)\n"
        js = module_to_js(src)
        assert "return xs.reduce((a, b) => a + b, 0);" in js

    def test_sum_binding_mode_unchanged(self):
        # T2 contract: binding expressions map sum -> __tf_sum (runtime helper).
        assert expr_to_js("sum(xs)") == "__tf_sum(xs)"

    def test_tuple_unpack(self):
        src = "def f(a, b):\n    a, b = b, a\n    return a\n"
        js = module_to_js(src)
        assert "[a, b] = [b, a];" in js

    def test_augassign(self):
        src = (
            "def f(x):\n"
            "    x += 2\n"
            "    x //= 3\n"
            "    x **= 2\n"
            "    x %= 5\n"
            "    return x\n"
        )
        js = module_to_js(src)
        assert "x += 2;" in js
        assert "x = Math.floor(x / 3);" in js
        assert "x = Math.pow(x, 2);" in js
        assert "x %= 5;" in js

    def test_if_elif_else_chain(self):
        src = (
            "def grade(x):\n"
            "    if x > 90:\n"
            "        return 4\n"
            "    elif x > 50:\n"
            "        return 2\n"
            "    else:\n"
            "        return 0\n"
        )
        js = module_to_js(src)
        assert "if ((x > 90)) {" in js
        assert "else if ((x > 50)) {" in js
        assert "else {" in js

    def test_while(self):
        js = module_to_js(HARMONIC)
        assert "while ((k <= n)) {" in js
        assert "k += 1.0;" in js

    def test_calls_between_functions(self):
        src = (
            "def sq(x):\n"
            "    return x * x\n"
            "\n"
            "def norm(a, b):\n"
            "    return math.sqrt(sq(a) + sq(b))\n"
        )
        js = module_to_js(src)
        assert "Math.sqrt((sq(a) + sq(b)));" in js

    def test_function_to_js_matches_module(self):
        fn = ast.parse(AIRY).body[0]
        assert function_to_js(fn) == module_to_js(AIRY)

    def test_bare_module_statement_rejected(self):
        with pytest.raises(ValueError, match="module level"):
            module_to_js("x = 1")

    def test_locals_not_redeclared_for_params(self):
        js = module_to_js(SERIES)
        assert "let a0" not in js
        assert "let n" not in js.replace("function series_sum(a0, r, n)", "")


class TestValidateModel:
    @pytest.mark.parametrize("name,src", FORBIDDEN, ids=[n for n, _ in FORBIDDEN])
    def test_forbidden_raises(self, name, src):
        with pytest.raises(ValueError):
            load_model({"model": {"source": src}})
        with pytest.raises(ValueError):
            module_to_js(src)

    def test_error_includes_line_number(self):
        with pytest.raises(ValueError, match=r"line 2"):
            load_model({"model": {"source": FORBIDDEN[0][1]}})

    def test_validate_model_source_ok(self):
        validate_model_source(AIRY)  # no raise

    def test_function_name_collision_with_helper_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            load_model({"model": {"source": "def sum(x):\n    return x\n"}})

    def test_call_to_unknown_name_rejected(self):
        with pytest.raises(ValueError, match="call to 'g'"):
            load_model({"model": {"source": "def f(x):\n    return g(x)\n"}})

    def test_kwarg_rejected(self):
        with pytest.raises(ValueError):
            load_model({"model": {"source": "def f(x):\n    return math.cos(x=x)\n"}})

    def test_catch_warnings_rce_payload_rejected(self, tmp_path):
        marker = tmp_path / "marker"
        src = (
            'def f(x: [c for c in ().__class__.__base__.__subclasses__()'
            f' if c.__name__ == "catch_warnings"][0]()._module.__builtins__["__import__"]("os").system("echo PWNED > {marker}")):\n'
            '    return x\n'
        )
        with pytest.raises(ValueError):
            validate_model_source(src)
        with pytest.raises(ValueError):
            exec_model_source(src)
        assert not marker.exists()


class TestLoadModel:
    def test_load_source_returns_callables(self):
        fns = load_model({"model": {"source": AIRY}})
        assert set(fns) == {"R"}
        got = fns["R"](1.0, 1.5, 2.0, 100.0, 550.0)
        assert got == pytest.approx(airy_python(1.0, 1.5, 2.0, 100.0, 550.0))

    def test_load_file(self, tmp_path):
        (tmp_path / "model.py").write_text(AIRY)
        fns = load_model({"model": {"file": "model.py"}}, base_dir=str(tmp_path))
        assert "R" in fns

    def test_load_file_absolute(self, tmp_path):
        mp = tmp_path / "model.py"
        mp.write_text(AIRY)
        fns = load_model({"model": {"file": str(mp)}})
        assert "R" in fns

    def test_load_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_model({"model": {"file": "nope.py"}}, base_dir=str(tmp_path))
        with pytest.raises(FileNotFoundError, match="nope.py"):
            load_model_source({"file": "nope.py"}, base_dir=str(tmp_path))

    def test_no_model_returns_empty(self):
        assert load_model({}) == {}

    def test_both_source_and_file_rejected(self):
        with pytest.raises(ValueError, match="either"):
            load_model({"model": {"source": AIRY, "file": "m.py"}})

    def test_helper_builtins_available(self):
        src = (
            "def stats(xs):\n"
            "    total = sum(xs)\n"
            "    m = abs(min(xs)) + abs(max(xs))\n"
            "    return total / len(xs)\n"
        )
        fns = load_model({"model": {"source": src}})
        assert fns["stats"]([1, 2, 3]) == 2.0

    def test_functions_can_call_each_other(self):
        src = (
            "def sq(x):\n"
            "    return x * x\n"
            "\n"
            "def norm(a, b):\n"
            "    return math.sqrt(sq(a) + sq(b))\n"
        )
        fns = load_model({"model": {"source": src}})
        assert fns["norm"](3.0, 4.0) == pytest.approx(5.0)

    def test_exec_model_source(self):
        fns = exec_model_source(R3)
        assert fns["R"](1.5, 100.0, 550.0) == pytest.approx(r3_python(1.5, 100.0, 550.0))

    def test_dunder_name_rejected(self):
        with pytest.raises(ValueError):
            load_model({"model": {"source": "def f():\n    x = __builtins__\n    return 1\n"}})


class TestSafeEvalModelCalls:
    def test_binding_calls_model_fn(self):
        fns = load_model({"model": {"source": AIRY}})
        env = {"n1": 1.5, "d": 100.0, "lam": 550.0, **fns}
        got = safe_eval("R(1.0, n1, 2.0, d, lam)", env)
        assert got == pytest.approx(fns["R"](1.0, 1.5, 2.0, 100.0, 550.0))

    def test_unknown_call_still_rejected(self):
        with pytest.raises(ValueError):
            safe_eval("g(1)", env={})

    def test_expr_to_js_extra_funcs(self):
        assert expr_to_js("R(n1, d, lam)", extra_funcs=frozenset({"R"})) == "R(n1, d, lam)"
        with pytest.raises(ValueError):
            expr_to_js("R(n1, d, lam)")


class TestResolveSpecWithModel:
    def test_model_binding_resolved(self):
        from techfig.engines.params import resolve_spec

        spec = make_model_spec()
        concrete, bindings = resolve_spec(spec)
        expected = format(r3_python(1.5, 100, 550), ".4f")
        assert concrete["elements"][0]["text"] == f"R = {expected}"
        assert bindings[0]["kind"] == "text"
        assert "R(n1, d, lam)" in bindings[0]["expr"]

    def test_param_model_name_collision_rejected(self):
        from techfig.engines.params import resolve_spec

        spec = {
            "params": [{"name": "n1", "min": 0, "max": 1, "step": 0.1, "value": 0.5}],
            "model": {"source": "def n1(x):\n    return x\n"},
            "elements": [],
        }
        with pytest.raises(ValueError, match="collides"):
            resolve_spec(spec)


class TestStaticRenderWithModel:
    def test_render_model_binding(self, tmp_path):
        spec = make_model_spec()
        out = render_from_spec(spec, str(tmp_path / "m.svg"))
        svg = Path(out).read_text()
        expected = "R = " + format(r3_python(1.5, 100, 550), ".4f")
        assert expected in svg

    def test_render_from_json_model_file(self, tmp_path):
        (tmp_path / "model.py").write_text(R3)
        spec = make_model_spec(model={"file": "model.py"})
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec))
        out = render_from_json(str(spec_file), str(tmp_path / "o.svg"))
        svg = Path(out).read_text()
        expected = "R = " + format(r3_python(1.5, 100, 550), ".4f")
        assert expected in svg


class TestInteractiveWithModel:
    def test_module_js_embedded(self, tmp_path):
        spec = make_model_spec()
        out = create_interactive_svg(spec, str(tmp_path / "w.html"))
        page = Path(out).read_text()
        assert "function R(n1, d, lam) {" in page
        bindings = get_bindings(page)
        assert any("R(n1, d, lam)" in b["js"] for b in bindings)
        assert any(b["attr"] == "textContent" for b in bindings)

    def test_unknown_model_fn_in_binding_raises(self, tmp_path):
        spec = make_model_spec()
        spec["elements"][0]["text"] = "{{g(n1, d, lam)}}"
        with pytest.raises(ValueError):
            create_interactive_svg(spec, str(tmp_path / "w.html"))
    def test_model_file_with_base_dir(self, tmp_path):
        (tmp_path / "model.py").write_text(R3)
        spec = make_model_spec(model={"file": "model.py"})
        out = create_interactive_svg(spec, str(tmp_path / "w.html"), base_dir=str(tmp_path))
        assert "function R(n1, d, lam) {" in Path(out).read_text()

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_node_end_to_end_binding_calls_model(self, tmp_path):
        import re

        spec = make_model_spec()
        out = create_interactive_svg(spec, str(tmp_path / "w.html"))
        page = Path(out).read_text()
        script = re.findall(r"<script[^>]*>(.*?)</script>", page, re.DOTALL)[-1]
        harness = (
            "global.window = {__tf: null};\n"
            "global.document = {"
            "querySelectorAll: function () { return []; }, "
            "getElementById: function () { return null; }};\n"
            + script
            # In a browser the top-level `function R()` of a classic <script>
            # is global, so `new Function` binding bodies can call it. Node
            # modules are scoped, so mirror that here explicitly.
            + "\nglobal.R = R;\n"
            + "\nvar __b = window.__tf.bindings.filter("
            "function (x) { return x.attr === 'textContent'; })[0];\n"
            "var __fn = new Function('n1', 'd', 'lam', '__fmt', '__tf_sum', '__tf_d', "
            "'return (' + __b.js + ')');\n"
            "console.log(JSON.stringify({"
            "text: __fn(1.5, 100, 550, window.__tf.fmt, null, null)}));\n"
        )
        f = tmp_path / "harness.js"
        f.write_text(harness)
        res = subprocess.run([NODE, str(f)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        out = json.loads(res.stdout)
        assert out["text"] == "R = " + format(r3_python(1.5, 100, 550), ".4f")


class TestVerifyModel:
    def test_node_absent_skip(self, monkeypatch):
        from techfig.engines import model_transpile

        monkeypatch.setattr(model_transpile.shutil, "which", lambda name: None)
        report = verify_model(AIRY, {})
        assert report == {"ok": None, "skipped": "node not found"}

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_airy_ok(self):
        ranges = {
            "n0": (1.0, 1.2), "n1": (1.3, 2.5), "n2": (1.0, 3.0),
            "d": (10.0, 500.0), "lam": (400.0, 900.0),
        }
        report = verify_model(AIRY, ranges, n_samples=50)
        assert report["ok"] is True
        assert report["n_checked"] == 50
        assert report["max_abs_err"] < 1e-9
        assert report["mismatches"] == []

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_harmonic_while_loop_ok(self):
        report = verify_model(HARMONIC, {"n": (1.0, 60.0)}, n_samples=20)
        assert report["ok"] is True
        assert report["n_checked"] == 20
        assert report["max_abs_err"] < 1e-9

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_mismatch_mod_semantics(self):
        # Python % follows the divisor sign; JS % the dividend sign. For
        # negative operands the two disagree — verify_model must catch it.
        src = "def f(x):\n    return x % 7\n"
        report = verify_model(src, {"x": (-20.0, -10.0)}, n_samples=25)
        assert report["ok"] is False
        assert report["mismatches"]
        assert report["n_checked"] > 0

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_python_error_recorded(self):
        src = "def f(x):\n    return 1 / x\n"
        report = verify_model(src, {"x": (0.0, 0.0)}, n_samples=5)
        assert report["ok"] is False
        assert len(report["mismatches"]) == 5
        assert "ZeroDivisionError" in report["mismatches"][0]["error"]

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_no_checkable_functions(self):
        src = "def f(a):\n    return a\n"
        report = verify_model(src, {"x": (0.0, 1.0)}, n_samples=5)
        assert report["ok"] is True
        assert report["n_checked"] == 0


@pytest.mark.skipif(NODE is None, reason="node not available")
class TestRangeLoopNodeParity:
    def test_series_sum_exact(self):
        js = module_to_js(SERIES)
        res = subprocess.run(
            [NODE, "-e", js + "\nconsole.log(JSON.stringify([series_sum(2.0, 0.5, 10)]))"],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        js_val = json.loads(res.stdout)[0]
        py_val = exec_model_source(SERIES)["series_sum"](2.0, 0.5, 10)
        assert js_val == py_val

    def test_airy_node_parity(self):
        js = module_to_js(AIRY)
        args = (1.0, 1.5, 2.0, 100.0, 550.0)
        res = subprocess.run(
            [NODE, "-e", js + f"\nconsole.log(JSON.stringify([R{args}]))"],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        js_val = json.loads(res.stdout)[0]
        fns = exec_model_source(AIRY)
        assert abs(js_val - fns["R"](*args)) < 1e-12


class TestVerifyModelCli:
    def _run(self, *cli_args):
        return subprocess.run(
            [sys.executable, "-m", "techfig.cli", "verify-model", *cli_args],
            capture_output=True, text=True,
        )

    def test_no_model_exits_nonzero(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps({"elements": []}))
        res = self._run(str(spec_file))
        assert res.returncode == 1
        assert "model" in (res.stderr + res.stdout).lower()

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_ok_exits_zero(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(make_model_spec()))
        res = self._run(str(spec_file), "--samples", "10")
        assert res.returncode == 0, res.stderr
        report = json.loads(res.stdout[res.stdout.index("{"):])
        assert report["ok"] is True
        assert report["n_checked"] == 10

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_mismatch_exits_nonzero(self, tmp_path):
        spec = {
            "params": [{"name": "x", "min": -20, "max": -10, "step": 0.1, "value": -15}],
            "model": {"source": "def f(x):\n    return x % 7\n"},
            "elements": [],
        }
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec))
        res = self._run(str(spec_file), "--samples", "10")
        assert res.returncode == 1
        report = json.loads(res.stdout[res.stdout.index("{"):])
        assert report["ok"] is False

    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_model_file_resolved_relative_to_spec(self, tmp_path):
        (tmp_path / "model.py").write_text(R3)
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(make_model_spec(model={"file": "model.py"})))
        res = self._run(str(spec_file), "--samples", "5")
        assert res.returncode == 0, res.stderr
        report = json.loads(res.stdout[res.stdout.index("{"):])
        assert report["ok"] is True


class TestInteractiveCliWithModel:
    @pytest.mark.skipif(NODE is None, reason="node not available")
    def test_interactive_model_file(self, tmp_path):
        (tmp_path / "model.py").write_text(R3)
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(make_model_spec(model={"file": "model.py"})))
        out = tmp_path / "w.html"
        res = subprocess.run(
            [sys.executable, "-m", "techfig.cli", "interactive", str(spec_file), "-o", str(out)],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        assert "function R(n1, d, lam) {" in out.read_text()


class TestModelResourceLimits:
    def test_while_infinite_loop_capped(self):
        src = "def f():\n    while True:\n        pass\n"
        fns = exec_model_source(src)
        with pytest.raises(ValueError, match=r"(?i)loop exceeded maximum iterations"):
            fns["f"]()

    def test_for_infinite_range_capped(self):
        src = "def f():\n    for i in range(10**12):\n        pass\n"
        fns = exec_model_source(src)
        with pytest.raises(ValueError, match=r"(?i)maximum.*iteration|exceeds"):
            fns["f"]()
