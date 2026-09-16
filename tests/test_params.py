"""Tests for the parametric expression evaluator and spec resolver."""
from pathlib import Path

import pytest

from techfig.engines.params import (
    UnsafeExpression,
    resolve_spec,
    safe_eval,
)
from techfig.engines.sketch_interpreter import render_from_spec


class TestSafeEvalWhitelist:
    """Reject anything outside the restricted expression subset."""

    def test_rejects_dunder_import(self):
        with pytest.raises(UnsafeExpression):
            safe_eval("__import__('os').system('rm -rf /')")

    def test_rejects_attribute_access(self):
        with pytest.raises(UnsafeExpression):
            safe_eval("x.__class__", env={"x": 1})

    def test_rejects_lambda(self):
        with pytest.raises(UnsafeExpression):
            safe_eval("(lambda: 1)()")

    def test_rejects_comprehension(self):
        with pytest.raises(UnsafeExpression):
            safe_eval("[i for i in range(3)]")

    def test_unknown_name_raises(self):
        with pytest.raises(UnsafeExpression):
            safe_eval("unknown + 1")


class TestSafeEvalExpressions:
    def test_whole_field_binding_float(self):
        assert safe_eval("2 * d", env={"d": 3.5}) == 7.0

    def test_math_functions_allowed(self):
        assert safe_eval("math.sqrt(16) + math.sin(0)") == 4.0

    def test_helpers_allowed(self):
        assert safe_eval("abs(-5) + max(1, 2) + min(3, 4)") == 10

    def test_ternary(self):
        assert safe_eval("a if a > b else b", env={"a": 1, "b": 2}) == 2

    def test_text_interpolation_fmt(self):
        assert safe_eval("fmt(x, '.3f')", env={"x": 1.23456}) == "1.235"

    def test_list_subscript(self):
        assert safe_eval("xs[1]", env={"xs": [10, 20, 30]}) == 20


class TestResolveSpec:
    def test_defaults_from_value(self):
        spec = {
            "params": [{"name": "d", "min": 0, "max": 10, "step": 1, "value": 5}],
            "elements": [{"type": "box", "id": "b", "x": 0, "y": 0, "h": "{{2*d}}"}],
        }
        concrete, bindings = resolve_spec(spec)
        assert concrete["elements"][0]["h"] == 10
        assert bindings == [{"path": ["elements", 0, "h"], "expr": "2*d", "kind": "value"}]

    def test_param_values_override_defaults(self):
        spec = {
            "params": [{"name": "d", "min": 0, "max": 10, "step": 1, "value": 5}],
            "elements": [{"type": "box", "id": "b", "x": 0, "y": 0, "h": "{{2*d}}"}],
        }
        concrete, _ = resolve_spec(spec, param_values={"d": 7})
        assert concrete["elements"][0]["h"] == 14

    def test_text_interpolation(self):
        spec = {
            "params": [{"name": "n", "min": 1, "max": 5, "step": 1, "value": 3}],
            "elements": [{"type": "text", "x": 0, "y": 0, "text": "n = {{n}}"}],
        }
        concrete, bindings = resolve_spec(spec)
        assert concrete["elements"][0]["text"] == "n = 3"
        assert bindings[0]["kind"] == "text"

    def test_params_and_model_removed_from_concrete(self):
        spec = {
            "params": [{"name": "d", "min": 0, "max": 10, "step": 1, "value": 5}],
            "model": {"source": "def f(x): return x"},
            "elements": [],
        }
        concrete, _ = resolve_spec(spec)
        assert "params" not in concrete
        assert "model" not in concrete


class TestRenderFromSpecBinding:
    """A spec with bindings should render identically to a hand-substituted spec."""

    def test_binding_render_byte_identical(self, tmp_path):
        base_spec = {
            "canvas": {"width": 400, "height": 300},
            "elements": [
                {"type": "box", "id": "b1", "x": 0, "y": 0, "w": 100, "h": 60, "text": "A"},
                {"type": "box", "id": "b2", "x": 200, "y": 0, "w": 100, "h": 60, "text": "B"},
            ],
            "connections": [{"from": "b1", "to": "b2"}],
        }
        bound_spec = {
            "canvas": {"width": 400, "height": 300},
            "params": [{"name": "d", "min": 0, "max": 200, "step": 1, "value": 100}],
            "elements": [
                {"type": "box", "id": "b1", "x": 0, "y": 0, "w": 100, "h": "{{d}}", "text": "A"},
                {"type": "box", "id": "b2", "x": 200, "y": 0, "w": 100, "h": 60, "text": "B"},
            ],
            "connections": [{"from": "b1", "to": "b2"}],
        }
        expected = dict(base_spec)
        expected["elements"][0]["h"] = 100

        out1 = render_from_spec(bound_spec, str(tmp_path / "bound.svg"))
        out2 = render_from_spec(expected, str(tmp_path / "expected.svg"))

        assert Path(out1).read_bytes() == Path(out2).read_bytes()

    def test_unknown_param_raises(self):
        spec = {
            "elements": [{"type": "box", "id": "b", "x": 0, "y": 0, "h": "{{2*d}}"}],
        }
        with pytest.raises(UnsafeExpression):
            resolve_spec(spec)


class TestResolveSpecValidation:
    def test_params_must_be_list(self):
        with pytest.raises(ValueError, match="'params' must be a list"):
            resolve_spec({"params": "bad", "elements": []})

    def test_param_must_have_name(self):
        with pytest.raises(ValueError, match="'name'"):
            resolve_spec({"params": [{"min": 0, "max": 1, "step": 0.1, "value": 0.5}], "elements": []})


class TestSafeEvalResourceLimits:
    """Explicit guards that raise UnsafeExpression rather than exhausting resources."""

    def test_exponent_magnitude_capped(self):
        with pytest.raises(UnsafeExpression, match=r"(?i)exponent"):
            safe_eval("9**9**9")
        with pytest.raises(UnsafeExpression, match=r"(?i)exponent"):
            safe_eval("2**100000")

    def test_math_factorial_capped(self):
        with pytest.raises(UnsafeExpression, match=r"(?i)factorial"):
            safe_eval("math.factorial(10**7)")
        with pytest.raises(UnsafeExpression, match=r"(?i)factorial"):
            safe_eval("math.factorial(1001)")

    def test_sequence_sizing_capped(self):
        with pytest.raises(UnsafeExpression, match=r"(?i)sequence"):
            safe_eval("'a'*10**10")
        with pytest.raises(UnsafeExpression, match=r"(?i)sequence"):
            safe_eval("10**10*'a'")
        with pytest.raises(UnsafeExpression, match=r"(?i)sequence"):
            safe_eval("[1]*10**10")

    def test_numeric_literal_magnitude_capped(self):
        huge_int_str = "9" * 400
        with pytest.raises(UnsafeExpression, match=r"(?i)magnitude|limit"):
            safe_eval(huge_int_str)

    def test_fmt_width_and_precision_capped(self):
        with pytest.raises(UnsafeExpression, match=r"(?i)format"):
            safe_eval("fmt(1, '>1000000000')")
        with pytest.raises(UnsafeExpression, match=r"(?i)format"):
            safe_eval("fmt(1.5, '.1000000f')")
