"""Restricted Python expression -> JavaScript transpiler.

Maps the same AST subset accepted by ``techfig.engines.params.safe_eval`` onto
equivalent JavaScript source for the interactive SVG runtime (T2 minimal
subset).  Anything outside the subset raises :class:`TranspileError` (a
``ValueError`` subclass).

Supported mappings:
- ``**``      -> ``Math.pow(a, b)``
- ``//``      -> ``Math.floor(a / b)``
- ``math.X``  -> ``Math.X`` (constants pi/e/tau/inf/nan and a safe function list)
- ``abs/min/max/round`` -> ``Math.*``
- ``len(x)``  -> ``x.length``
- ``fmt(x, '.3f')``      -> ``__fmt(x, ".3f")`` (runtime helper)
- ``sum(xs)`` -> ``__tf_sum(xs)`` (runtime helper)
- ``IfExp``   -> JS ternary, ``and/or/not`` -> ``&&/||/!``
- chained comparisons -> ``&&``-joined pairwise comparisons
- List/Tuple -> array literal, Subscript -> index
"""
import ast
import json
from typing import List

_MATH_CONST = {"pi": "PI", "e": "E", "tau": "TAU", "inf": "Infinity", "nan": "NaN"}
_MATH_FUNCS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sqrt", "exp",
    "log", "log10", "log2", "fabs", "floor", "ceil", "hypot", "pow",
    "cbrt", "trunc",
}
_MATH_ARITY = {"pow": (2, 2), "atan2": (2, 2), "hypot": (1, None)}
_HELPER_FUNCS = {"abs", "min", "max", "round", "len", "fmt", "sum"}
_BIN_OPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}
_CMP_OPS = {
    ast.Eq: "===", ast.NotEq: "!==", ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=",
}


class TranspileError(ValueError):
    """Raised when an expression node has no JavaScript mapping."""


def expr_to_js(expr: str) -> str:
    """Transpile a restricted Python expression to JavaScript source.

    Raises:
        TranspileError: On syntax errors or unsupported AST nodes (also a
            ValueError, matching the T2 contract).
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise TranspileError(f"Invalid expression syntax: {expr!r}") from exc
    return _trans(tree.body)


def _trans(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return "true" if v else "false"
        if v is None:
            return "null"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return json.dumps(v)
        raise TranspileError(f"Unsupported constant: {v!r}")
    if isinstance(node, ast.Name):
        return "Math" if node.id == "math" else node.id
    if isinstance(node, (ast.List, ast.Tuple)):
        return "[" + ", ".join(_trans(e) for e in node.elts) + "]"
    if isinstance(node, ast.Subscript):
        sl = node.slice
        if isinstance(sl, ast.Slice):
            raise TranspileError("Slices are not supported in JS transpile")
        return f"{_trans(node.value)}[{_trans(sl)}]"
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            return f"Math.pow({_trans(node.left)}, {_trans(node.right)})"
        if isinstance(node.op, ast.FloorDiv):
            return f"Math.floor({_trans(node.left)} / {_trans(node.right)})"
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise TranspileError(f"Unsupported binary operator: {type(node.op).__name__}")
        return f"({_trans(node.left)} {op} {_trans(node.right)})"
    if isinstance(node, ast.UnaryOp):
        o = _trans(node.operand)
        if isinstance(node.op, ast.USub):
            return f"(-{o})"
        if isinstance(node.op, ast.UAdd):
            return f"(+{o})"
        if isinstance(node.op, ast.Not):
            return f"(!{o})"
        raise TranspileError(f"Unsupported unary operator: {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        parts: List[str] = []
        left = node.left
        for op, comp in zip(node.ops, node.comparators):
            js_op = _CMP_OPS.get(type(op))
            if js_op is None:
                raise TranspileError(f"Unsupported comparison: {type(op).__name__}")
            parts.append(f"{_trans(left)} {js_op} {_trans(comp)}")
            left = comp
        return "(" + " && ".join(parts) + ")"
    if isinstance(node, ast.BoolOp):
        js_op = "&&" if isinstance(node.op, ast.And) else "||"
        return "(" + f" {js_op} ".join(_trans(v) for v in node.values) + ")"
    if isinstance(node, ast.IfExp):
        return f"({_trans(node.test)} ? {_trans(node.body)} : {_trans(node.orelse)})"
    if isinstance(node, ast.Attribute):
        if not (isinstance(node.value, ast.Name) and node.value.id == "math"):
            raise TranspileError("Only 'math.<name>' attribute access is supported")
        if node.attr in _MATH_CONST:
            return f"Math.{_MATH_CONST[node.attr]}"
        raise TranspileError(f"math.{node.attr} has no JS mapping")
    if isinstance(node, ast.Call):
        return _trans_call(node)
    raise TranspileError(f"Unsupported node: {type(node).__name__}")


def _trans_call(node: ast.Call) -> str:
    if node.keywords:
        raise TranspileError("Keyword arguments are not supported")
    args = [_trans(a) for a in node.args]
    func = node.func

    if isinstance(func, ast.Attribute):
        if not (isinstance(func.value, ast.Name) and func.value.id == "math"):
            raise TranspileError("Only 'math.<fn>(...)' calls are supported")
        name = func.attr
        if name in _MATH_CONST:
            raise TranspileError(f"math.{name} is a constant, not a function")
        if name not in _MATH_FUNCS:
            raise TranspileError(f"math.{name} has no JS mapping")
        lo, hi = _MATH_ARITY.get(name, (1, 1))
        if len(args) < lo or (hi is not None and len(args) > hi):
            hi_repr = "n" if hi is None else hi
            raise TranspileError(
                f"math.{name}: expected {lo}..{hi_repr} args, got {len(args)}"
            )
        return f"Math.{name}({', '.join(args)})"

    if isinstance(func, ast.Name):
        name = func.id
        if name not in _HELPER_FUNCS:
            raise TranspileError(f"Function '{name}' has no JS mapping")
        if name == "len":
            if len(args) != 1:
                raise TranspileError("len() takes exactly 1 argument")
            return f"{args[0]}.length"
        if name == "fmt":
            if len(args) != 2:
                raise TranspileError("fmt() takes exactly 2 arguments")
            return f"__fmt({', '.join(args)})"
        if name == "sum":
            if len(args) != 1:
                raise TranspileError("sum() takes exactly 1 argument")
            return f"__tf_sum({args[0]})"
        return f"Math.{name}({', '.join(args)})"

    raise TranspileError("Unsupported call form")
