"""Parametric expression evaluator for interactive TechFig specs.

A spec may declare a top-level ``params`` list and use ``{{expr}}`` bindings
anywhere inside element/connection string fields.  This module resolves those
bindings into a concrete spec at a given parameter dict, using a small,
AST-restricted Python evaluator.
"""
import ast
import builtins
import copy
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_BINDING_RE = re.compile(r"\{\{(.+?)\}\}")


class UnsafeExpression(ValueError):
    """Raised when an expression attempts something outside the whitelist."""


def _check_node(node: ast.AST, env_callables: Tuple[str, ...] = ()) -> None:
    """Validate that ``node`` is within the allowed AST subset.

    Allowed nodes:
    - literals: Constant (numbers, strings, None)
    - collections: List, Tuple, Dict (only for constants/params)
    - names and indexing: Name, Subscript
    - arithmetic/logic: BinOp, UnaryOp, Compare, BoolOp, IfExp
    - operators: Add, Sub, Mult, Div, FloorDiv, Mod, Pow, USub, UAdd, Not,
      Eq, NotEq, Lt, LtE, Gt, GtE, And, Or
    - function calls: Call (limited to ``math.<fn>``, helpers, and model
      functions from ``env_callables``)

    Everything else is rejected with a clear message.
    """
    allowed = {
        ast.Expression,
        ast.Constant,
        ast.Name,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.Subscript,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.BoolOp,
        ast.IfExp,
        ast.Call,
        ast.Attribute,
        ast.Load,
        # Binary operators
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        # Unary operators
        ast.UAdd,
        ast.USub,
        ast.Not,
        # Comparison operators
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        # Boolean operators
        ast.And,
        ast.Or,
        # Subscript contexts
        ast.Index,
    }
    if type(node) not in allowed:
        raise UnsafeExpression(f"Expression contains disallowed syntax: {type(node).__name__}")

    if isinstance(node, ast.Attribute):
        # Only ``math.<name>`` attribute access is permitted anywhere.
        if not (isinstance(node.value, ast.Name) and node.value.id == "math"):
            raise UnsafeExpression("Only 'math.<name>' attribute access is allowed")
        if node.attr not in _ALLOWED_MATH:
            raise UnsafeExpression(f"math.{node.attr} is not allowed")

    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            if not (isinstance(func.value, ast.Name) and func.value.id == "math"):
                raise UnsafeExpression("Only 'math.<function>' attribute access is allowed")
        elif isinstance(func, ast.Name):
            if func.id in _HELPER_FUNCS:
                pass  # built-in helper handled at eval time
            elif func.id in env_callables:
                pass  # model function exposed to bindings (T3)
            else:
                raise UnsafeExpression(f"Function '{func.id}' is not allowed")
        else:
            raise UnsafeExpression("Only direct calls or 'math.<function>' calls are allowed")

    for child in ast.iter_child_nodes(node):
        _check_node(child, env_callables)


_ALLOWED_MATH = {
    "acos", "acosh", "asin", "asinh", "atan", "atan2", "atanh", "cbrt", "ceil", "comb",
    "copysign", "cos", "cosh", "degrees", "dist", "e", "erf", "erfc", "exp", "exp2",
    "expm1", "fabs", "factorial", "floor", "fmod", "frexp", "fsum", "gamma", "gcd",
    "hypot", "inf", "isclose", "isfinite", "isinf", "isnan", "isqrt", "lcm", "ldexp",
    "lgamma", "log", "log10", "log1p", "log2", "modf", "nan", "nextafter", "pi", "pow",
    "radians", "remainder", "sin", "sinh", "sqrt", "tan", "tanh", "tau", "trunc",
    "ulp",
}

_HELPER_FUNCS = {"abs", "min", "max", "round", "len", "fmt", "sum"}


def _fmt(value: Any, spec: str) -> str:
    """Format helper exposed to bindings as ``fmt(x, '.3f')``."""
    return format(value, spec)


def _resolve_name(name: str, env: Dict[str, Any]) -> Any:
    """Look up a name in the evaluation environment.

    ``math`` is the only module exposed; all other names must come from ``env``.
    """
    if name == "math":
        return math
    if name in env:
        return env[name]
    raise UnsafeExpression(f"Unknown parameter or name: '{name}'")


def safe_eval(expr: str, env: Dict[str, Any] | None = None) -> Any:
    """Evaluate ``expr`` in a restricted Python subset.

    Args:
        expr: Python expression string.
        env: Mapping of parameter names to values.

    Returns:
        The evaluated result.

    Raises:
        UnsafeExpression: If the expression uses disallowed syntax or names.
    """
    env = env or {}
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpression(f"Invalid expression syntax: {expr}") from exc

    env_callables = tuple(sorted(
        k for k, v in env.items() if callable(v)
    ))
    _check_node(tree, env_callables)

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return _resolve_name(node.id, env)
        if isinstance(node, ast.List):
            return [_eval(elt) for elt in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(_eval(elt) for elt in node.elts)
        if isinstance(node, ast.Dict):
            keys = []
            values = []
            for k, v in zip(node.keys, node.values):
                if k is None:
                    raise UnsafeExpression("Keyword unpacking is not allowed")
                keys.append(_eval(k))
                values.append(_eval(v))
            return dict(zip(keys, values))
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left ** right
            raise UnsafeExpression(f"Unsupported binary operator: {type(node.op).__name__}")
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.Not):
                return not operand
            raise UnsafeExpression(f"Unsupported unary operator: {type(node.op).__name__}")
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = _eval(comparator)
                if isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                else:
                    raise UnsafeExpression(f"Unsupported comparison: {type(op).__name__}")
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.BoolOp):
            values = [_eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise UnsafeExpression(f"Unsupported boolean operator: {type(node.op).__name__}")
        if isinstance(node, ast.IfExp):
            return _eval(node.body) if _eval(node.test) else _eval(node.orelse)
        if isinstance(node, ast.Subscript):
            value = _eval(node.value)
            index = _eval(node.slice)
            return value[index]
        if isinstance(node, ast.Attribute):
            # Only ``math.<name>`` survives _check_node.
            return getattr(math, node.attr)
        if isinstance(node, ast.Call):
            func_node = node.func
            args = [_eval(a) for a in node.args]
            kwargs = {kw.arg: _eval(kw.value) for kw in node.keywords if kw.arg is not None}
            if isinstance(func_node, ast.Attribute):
                # math.<fn>
                if func_node.attr not in _ALLOWED_MATH:
                    raise UnsafeExpression(f"math.{func_node.attr} is not allowed")
                return getattr(math, func_node.attr)(*args, **kwargs)
            if isinstance(func_node, ast.Name):
                fn = func_node.id
                if fn == "fmt":
                    if len(args) != 2:
                        raise UnsafeExpression("fmt() takes exactly 2 arguments")
                    return _fmt(args[0], args[1])
                if fn == "sum":
                    if len(args) != 1:
                        raise UnsafeExpression("sum() takes exactly 1 argument")
                    return sum(args[0])
                if fn in env and callable(env[fn]):
                    return env[fn](*args, **kwargs)
                # abs, min, max, round, len
                try:
                    builtin = getattr(builtins, fn)
                except AttributeError as exc:
                    raise UnsafeExpression(f"Unknown helper function: '{fn}'") from exc
                return builtin(*args, **kwargs)
            raise UnsafeExpression("Unsupported call form")
        raise UnsafeExpression(f"Unsupported expression node: {type(node).__name__}")

    return _eval(tree.body)


def _is_value_binding(value: Any) -> bool:
    """Return True if ``value`` is a string that is exactly ``{{...}}``."""
    if not isinstance(value, str):
        return False
    m = _BINDING_RE.fullmatch(value.strip())
    return m is not None


def _has_bindings(value: Any) -> bool:
    """Return True if ``value`` is a string containing at least one ``{{...}}``."""
    if not isinstance(value, str):
        return False
    return _BINDING_RE.search(value) is not None


def _evaluate_binding(value: str, env: Dict[str, Any]) -> Tuple[Any, str]:
    """Evaluate a whole-field or text-interpolation binding.

    Returns ``(result, kind)`` where kind is ``'value'`` for whole-field
    bindings and ``'text'`` for interpolated text.
    """
    stripped = value.strip()
    m = _BINDING_RE.fullmatch(stripped)
    if m:
        return safe_eval(m.group(1).strip(), env), "value"

    def replacer(match: re.Match) -> str:
        result = safe_eval(match.group(1).strip(), env)
        return str(result)

    return _BINDING_RE.sub(replacer, value), "text"


def _resolve_value(value: Any, env: Dict[str, Any], path: List[str | int], bindings: List[Dict[str, Any]]) -> Any:
    """Recursively resolve bindings inside a value, tracking locations.

    ``path`` locates the field in the original spec; ``bindings`` collects
    metadata for downstream interactive renderers.
    """
    if isinstance(value, dict):
        resolved: Dict[str, Any] = {}
        for k, v in value.items():
            resolved[k] = _resolve_value(v, env, path + [k], bindings)
        if resolved.get("type") == "readout":
            expr_val = resolved.get("expr")
            if expr_val is not None:
                if isinstance(expr_val, str):
                    s = expr_val.strip()
                    if s.startswith("{{") and s.endswith("}}"):
                        s = s[2:-2].strip()
                    try:
                        resolved["value"] = safe_eval(s, env)
                    except Exception:
                        resolved["value"] = expr_val
                else:
                    resolved["value"] = expr_val
            verdict = resolved.get("verdict")
            if isinstance(verdict, dict):
                v_expr = verdict.get("expr")
                if isinstance(v_expr, str):
                    s = v_expr.strip()
                    if s.startswith("{{") and s.endswith("}}"):
                        s = s[2:-2].strip()
                    try:
                        v_bool = bool(safe_eval(s, env))
                    except Exception:
                        v_bool = False
                    verdict["value"] = v_bool
        if "visible_when" in resolved:
            vw = resolved["visible_when"]
            if isinstance(vw, str):
                s = vw.strip()
                if s.startswith("{{") and s.endswith("}}"):
                    s = s[2:-2].strip()
                try:
                    resolved["visible_when"] = bool(safe_eval(s, env))
                except Exception:
                    pass
        return resolved

    if isinstance(value, list):
        resolved_list: List[Any] = []
        for i, item in enumerate(value):
            resolved_list.append(_resolve_value(item, env, path + [i], bindings))
        return resolved_list

    if _is_value_binding(value):
        expr = _BINDING_RE.fullmatch(value.strip()).group(1).strip()  # type: ignore[union-per]
        result, kind = _evaluate_binding(value, env)
        bindings.append({"path": list(path), "expr": expr, "kind": kind})
        return result

    if _has_bindings(value):
        result, kind = _evaluate_binding(value, env)
        bindings.append({"path": list(path), "expr": value, "kind": kind})
        return result

    return value


def load_model_source(model: Dict[str, Any], base_dir: str | None = None) -> str:
    """Return the restricted model source declared by a spec's ``model`` block.

    The block is ``{"source": "..."}`` or ``{"file": "model.py"}`` — a relative
    ``file`` path is resolved against ``base_dir`` (the spec file's directory).
    """
    if not isinstance(model, dict):
        raise ValueError("'model' must be an object with 'source' or 'file'")
    has_source, has_file = "source" in model, "file" in model
    if has_source and has_file:
        raise ValueError("'model' must have either 'source' or 'file', not both")
    if has_source:
        if not isinstance(model["source"], str) or not model["source"].strip():
            raise ValueError("'model.source' must be a non-empty string")
        return model["source"]
    if has_file:
        path = Path(model["file"])
        if not path.is_absolute() and base_dir:
            path = Path(base_dir) / path
        if not path.is_file():
            raise FileNotFoundError(f"Model file not found: {path}")
        return path.read_text(encoding="utf-8")
    raise ValueError("'model' must have a 'source' or 'file' key")


def load_model(
    spec: Dict[str, Any],
    base_dir: str | None = None,
) -> Dict[str, Any]:
    """Load a spec's model functions.

    Returns ``{function name: callable}`` for the spec's ``model`` block
    (validated restricted Python — see ``techfig.engines.model_transpile``),
    or ``{}`` when the spec declares no model.
    """
    model = spec.get("model")
    if model is None:
        return {}
    from techfig.engines.model_transpile import exec_model_source

    return exec_model_source(load_model_source(model, base_dir))


def resolve_spec(
    spec: Dict[str, Any],
    param_values: Dict[str, Any] | None = None,
    base_dir: str | None = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Resolve a parametric spec to a concrete spec at the given parameters.

    The top-level ``params`` key declares parameters with ``name``, ``min``,
    ``max``, ``step``, and ``value`` (plus optional ``label`` and ``unit``).
    When ``param_values`` is omitted, defaults are taken from each parameter's
    ``value`` field.

    The top-level ``model`` block (``{"source": ...}`` or ``{"file": ...}``,
    file paths relative to ``base_dir``) defines restricted-Python model
    functions; they are exposed to bindings by name, so ``{{R(n1, d, lam)}}``
    calls the model function ``R``.

    Any string field that is exactly ``{{expr}}`` is replaced by the evaluated
    result (which may be a number, list, or string).  Strings that contain
    ``{{expr}}`` inside other text are replaced by interpolated text.

    Args:
        spec: Diagram specification dict, possibly containing parametric bindings.
        param_values: Optional mapping of parameter names to values.  Missing
            names use the declared default ``value``.
        base_dir: Base directory for resolving a relative ``model.file``
            (typically the directory of the JSON spec file).

    Returns:
        ``(concrete_spec, bindings)`` where ``bindings`` is a list of dicts
        describing each bound field in the original spec:
        ``{path: [...keys/indices...], expr: str, kind: 'value'|'text'}``.

    Raises:
        UnsafeExpression: If a binding uses disallowed syntax or an unknown name.
        ValueError: On invalid ``params``/``model`` declarations.
    """
    spec = copy.deepcopy(spec)
    params = spec.get("params", [])
    if not isinstance(params, list):
        raise ValueError("'params' must be a list")

    env: Dict[str, Any] = {}
    for p in params:
        if not isinstance(p, dict):
            raise ValueError("Each param must be a dict")
        name = p.get("name")
        if not name:
            raise ValueError("Each param must have a 'name'")
        kind = p.get("kind", "range")
        if kind not in ("range", "state"):
            raise ValueError(f"Unknown param kind: '{kind}'")
        if kind == "state":
            options = p.get("options")
            if not options or not isinstance(options, list):
                raise ValueError(f"State param '{name}' requires non-empty 'options' list")
            default_val = p.get("value", options[0])
            env[name] = param_values.get(name, default_val) if param_values else default_val
        else:
            env[name] = param_values.get(name, p.get("value")) if param_values else p.get("value")

    model_fns = load_model(spec, base_dir)
    collisions = sorted(set(env) & set(model_fns))
    if collisions:
        raise ValueError(
            f"model function name '{collisions[0]}' collides with a param name"
        )
    env.update(model_fns)

    bindings: List[Dict[str, Any]] = []
    concrete: Dict[str, Any] = {}
    for key, value in spec.items():
        if key in ("params", "model"):
            continue
        concrete[key] = _resolve_value(value, env, [key], bindings)

    return concrete, bindings
