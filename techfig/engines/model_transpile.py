"""Restricted Python -> JavaScript transpiler for TechFig models.

Two layers share one AST whitelist:

1. *Binding expressions* — ``expr_to_js`` (T2 behaviour, unchanged): the small
   expression subset accepted by ``techfig.engines.params.safe_eval``.  An
   optional ``extra_funcs`` set (T3) whitelists calls to model functions.
2. *Model functions* (T3) — ``module_to_js`` / ``function_to_js`` transpile a
   restricted Python module (top-level ``def`` blocks only) so the same
   numerical model can run inside the interactive SVG runtime.  The Python
   side executes the identical source via ``exec_model_source`` after the
   same ``validate_model_source`` pass, so ``verify_model`` can cross-check
   both implementations numerically with Node.

Supported statement subset (anything else raises :class:`TranspileError`,
a ``ValueError`` subclass, with the source line number): ``return``,
assignment / augmented assignment, 2-name tuple unpacking,
``for i in range(...)`` (1-3 args), ``while``, ``if/elif/else``, ``pass``,
``break``/``continue``, bare call statements, a leading docstring, and
``<list>.append(x)`` statements.  Expressions add (on top of the binding
subset): calls to other model functions.

Mappings: ``**`` -> ``Math.pow(a, b)``; ``//`` -> ``Math.floor(a / b)``;
``range`` -> JS for-loop; ``.append`` -> ``.push``; ``len(x)`` -> ``x.length``;
``sum(xs)`` -> ``xs.reduce((a, b) => a + b, 0)`` inside model functions
(binding expressions keep the T2 ``__tf_sum`` runtime helper);
``abs/min/max/round`` -> ``Math.*``; ``math.X`` -> ``Math.X``.

Known parity notes — surfaced by ``verify_model`` rather than silently
ignored: ``%`` follows the dividend's sign in JS but the divisor's in Python
(negative operands disagree); a JS for-loop leaves its induction variable one
increment past the final Python iteration value if read after the loop;
Python raises ``ZeroDivisionError`` where JS yields ``Infinity``.
"""
import ast
import json
import math
import random
import shutil
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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

# Names a model source may not define or assign (they shadow the helper
# namespace shared by the Python and JS sides).
_RESERVED_NAMES = {"math", "abs", "min", "max", "round", "len", "sum", "range", "fmt"}

# Python identifiers that would break the emitted JavaScript.
_JS_RESERVED = {
    "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "export", "extends", "finally",
    "for", "function", "if", "import", "in", "instanceof", "let", "new",
    "return", "super", "switch", "this", "throw", "try", "typeof", "var",
    "void", "while", "with", "yield", "enum", "await", "null", "true",
    "false", "undefined", "NaN", "Infinity", "arguments", "eval",
    "Math", "__fmt", "__tf_sum", "__tf_d",
}

# Helper calls and math members allowed inside model functions (must have
# mappings in BOTH the Python exec namespace and the JS emitter).
_MODEL_HELPERS = {"len", "sum", "abs", "min", "max", "round"}
_MODEL_MATH = _MATH_FUNCS | set(_MATH_CONST)


class TranspileError(ValueError):
    """Raised when a node has no JavaScript mapping or fails the whitelist."""


class _Ctx:
    """Transpile context.

    ``extra_funcs``: names allowed as plain call targets (model functions).
    ``module_mode``: True while transpiling a model function body — enables
    the ``sum`` -> ``reduce`` and ``<list>.append`` -> ``push`` mappings and
    rejects ``fmt``.  Binding expressions (ctx=None) behave exactly as T2.
    """

    __slots__ = ("extra_funcs", "module_mode")

    def __init__(self, extra_funcs: Iterable[str] = (), module_mode: bool = False):
        self.extra_funcs = frozenset(extra_funcs)
        self.module_mode = module_mode


def expr_to_js(expr: str, extra_funcs: Optional[Iterable[str]] = None) -> str:
    """Transpile a restricted Python expression to JavaScript source.

    Args:
        expr: Python expression string.
        extra_funcs: Optional names (e.g. model functions) allowed as call
            targets.  Without it the T2 binding-subset behaviour is exact.

    Raises:
        TranspileError: On syntax errors or unsupported AST nodes (also a
            ValueError, matching the T2 contract).
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise TranspileError(f"Invalid expression syntax: {expr!r}") from exc
    ctx = _Ctx(extra_funcs=extra_funcs) if extra_funcs else None
    return _trans(tree.body, ctx)


def _trans(node: ast.AST, ctx: Optional[_Ctx] = None) -> str:
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
        return "[" + ", ".join(_trans(e, ctx) for e in node.elts) + "]"
    if isinstance(node, ast.Subscript):
        sl = node.slice
        if isinstance(sl, ast.Slice):
            raise TranspileError("Slices are not supported in JS transpile")
        return f"{_trans(node.value, ctx)}[{_trans(sl, ctx)}]"
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            return f"Math.pow({_trans(node.left, ctx)}, {_trans(node.right, ctx)})"
        if isinstance(node.op, ast.FloorDiv):
            return f"Math.floor({_trans(node.left, ctx)} / {_trans(node.right, ctx)})"
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise TranspileError(f"Unsupported binary operator: {type(node.op).__name__}")
        return f"({_trans(node.left, ctx)} {op} {_trans(node.right, ctx)})"
    if isinstance(node, ast.UnaryOp):
        o = _trans(node.operand, ctx)
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
            parts.append(f"{_trans(left, ctx)} {js_op} {_trans(comp, ctx)}")
            left = comp
        return "(" + " && ".join(parts) + ")"
    if isinstance(node, ast.BoolOp):
        js_op = "&&" if isinstance(node.op, ast.And) else "||"
        return "(" + f" {js_op} ".join(_trans(v, ctx) for v in node.values) + ")"
    if isinstance(node, ast.IfExp):
        return (f"({_trans(node.test, ctx)} ? {_trans(node.body, ctx)}"
                f" : {_trans(node.orelse, ctx)})")
    if isinstance(node, ast.Attribute):
        if not (isinstance(node.value, ast.Name) and node.value.id == "math"):
            raise TranspileError("Only 'math.<name>' attribute access is supported")
        if node.attr in _MATH_CONST:
            return f"Math.{_MATH_CONST[node.attr]}"
        raise TranspileError(f"math.{node.attr} has no JS mapping")
    if isinstance(node, ast.Call):
        return _trans_call(node, ctx)
    raise TranspileError(f"Unsupported node: {type(node).__name__}")


def _trans_call(node: ast.Call, ctx: Optional[_Ctx]) -> str:
    if node.keywords:
        raise TranspileError("Keyword arguments are not supported")
    args = [_trans(a, ctx) for a in node.args]
    func = node.func

    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name) and func.value.id == "math":
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
        if (
            ctx is not None and ctx.module_mode
            and func.attr == "append" and isinstance(func.value, ast.Name)
        ):
            if len(args) != 1:
                raise TranspileError(".append takes exactly 1 argument")
            return f"{func.value.id}.push({args[0]})"
        raise TranspileError("Only 'math.<fn>(...)' calls are supported")

    if isinstance(func, ast.Name):
        name = func.id
        if name in _HELPER_FUNCS:
            if name == "len":
                if len(args) != 1:
                    raise TranspileError("len() takes exactly 1 argument")
                return f"{args[0]}.length"
            if name == "fmt":
                if ctx is not None and ctx.module_mode:
                    raise TranspileError("fmt() is not allowed in model functions")
                if len(args) != 2:
                    raise TranspileError("fmt() takes exactly 2 arguments")
                return f"__fmt({', '.join(args)})"
            if name == "sum":
                if len(args) != 1:
                    raise TranspileError("sum() takes exactly 1 argument")
                if ctx is not None and ctx.module_mode:
                    return f"{args[0]}.reduce((a, b) => a + b, 0)"
                return f"__tf_sum({args[0]})"
            return f"Math.{name}({', '.join(args)})"
        if ctx is not None and name in ctx.extra_funcs:
            return f"{name}({', '.join(args)})"
        if ctx is not None and ctx.module_mode and name == "range":
            raise TranspileError("range() is only allowed in for-loop headers")
        raise TranspileError(f"Function '{name}' has no JS mapping")

    raise TranspileError("Unsupported call form")


# ---- model-source validation (shared by transpiler and Python exec) --------


def _verr(node: ast.AST, msg: str) -> TranspileError:
    lineno = getattr(node, "lineno", 0)
    return TranspileError(f"line {lineno}: {msg}")


def _check_ident(name: str, lineno: int, kind: str) -> None:
    if name.startswith("__") and name.endswith("__"):
        raise TranspileError(f"line {lineno}: dunder name '{name}' is not allowed")
    if name in _RESERVED_NAMES:
        raise TranspileError(f"line {lineno}: '{name}' is not allowed as a {kind}")
    if name in _JS_RESERVED:
        raise TranspileError(f"line {lineno}: '{name}' is a reserved JavaScript word")


def _is_docstring_stmt(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _skip_docstring(body: List[ast.stmt]) -> List[ast.stmt]:
    if body and _is_docstring_stmt(body[0]):
        return body[1:]
    return body


def _collect_locals(body: List[ast.stmt]) -> Set[str]:
    """Names assigned anywhere in the function (Python scoping: local everywhere)."""
    out: Set[str] = set()

    def add(target: ast.expr) -> None:
        if isinstance(target, ast.Name):
            out.add(target.id)
        elif isinstance(target, ast.Tuple):
            for e in target.elts:
                if isinstance(e, ast.Name):
                    out.add(e.id)

    def walk(stmts: List[ast.stmt]) -> None:
        for s in stmts:
            if isinstance(s, ast.Assign):
                for t in s.targets:
                    add(t)
            elif isinstance(s, ast.AugAssign):
                add(s.target)
            elif isinstance(s, ast.For):
                add(s.target)
                walk(s.body)
            elif isinstance(s, (ast.While, ast.If)):
                walk(s.body)
                walk(s.orelse)

    walk(_skip_docstring(body))
    return out


class _FnCheck:
    """Whitelist validator for one model function body."""

    def __init__(self, fn: ast.FunctionDef, known: Set[str]):
        self.fn = fn
        self.known = known
        self.params = {a.arg for a in fn.args.args}
        self.locals = _collect_locals(fn.body)

    def _known_name(self, name: str) -> bool:
        return name in self.params or name in self.locals or name in self.known

    def _check_target_name(self, node: ast.Name) -> None:
        _check_ident(node.id, node.lineno, "variable name")
        if node.id in self.known:
            raise _verr(node, f"variable '{node.id}' collides with a model function name")

    def check_stmt(self, node: ast.stmt) -> None:
        # An Expr whose value is a bare tuple/name/list attribute access
        # (e.g. an unused docstring) is handled via _check_call below.
        if isinstance(node, ast.Return):
            if node.value is not None:
                self.check_expr(node.value)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self._check_target_name(t)
                elif isinstance(t, ast.Tuple):
                    if len(t.elts) != 2 or not all(isinstance(e, ast.Name) for e in t.elts):
                        raise _verr(node, "only 2-name tuple unpacking is supported")
                    for e in t.elts:
                        self._check_target_name(e)
                else:
                    raise _verr(
                        node, f"assignment target '{type(t).__name__}' is not supported"
                    )
            self.check_expr(node.value)
        elif isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                raise _verr(node, "augmented assignment target must be a plain name")
            self._check_target_name(node.target)
            if not isinstance(
                node.op,
                (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.Pow),
            ):
                raise _verr(node, "augmented assignment operator is not supported")
            self.check_expr(node.value)
        elif isinstance(node, ast.For):
            if not isinstance(node.target, ast.Name):
                raise _verr(node, "for-loop target must be a plain name")
            self._check_target_name(node.target)
            it = node.iter
            if not (
                isinstance(it, ast.Call)
                and isinstance(it.func, ast.Name)
                and it.func.id == "range"
            ):
                raise _verr(node, "for loops must iterate over range(...)")
            if not 1 <= len(it.args) <= 3:
                raise _verr(node, "range() takes 1 to 3 arguments")
            if it.keywords:
                raise _verr(node, "range() does not accept keyword arguments")
            for a in it.args:
                self.check_expr(a)
            if node.orelse:
                raise _verr(node, "for/else is not supported")
            for s in node.body:
                self.check_stmt(s)
        elif isinstance(node, ast.While):
            self.check_expr(node.test)
            if node.orelse:
                raise _verr(node, "while/else is not supported")
            for s in node.body:
                self.check_stmt(s)
        elif isinstance(node, ast.If):
            self.check_expr(node.test)
            for s in node.body:
                self.check_stmt(s)
            for s in node.orelse:
                self.check_stmt(s)
        elif isinstance(node, (ast.Pass, ast.Break, ast.Continue)):
            pass
        elif isinstance(node, ast.Expr):
            if _is_docstring_stmt(node):
                raise _verr(node, "string statements are only allowed as the docstring")
            self.check_expr(node.value, allow_append=True)
        else:
            raise _verr(
                node, f"statement '{type(node).__name__}' is not allowed in model functions"
            )

    def check_expr(self, node: ast.expr, allow_append: bool = False) -> None:
        if isinstance(node, ast.Constant):
            return
        if isinstance(node, ast.Name):
            _check_ident(node.id, node.lineno, "name")
            if not (node.id == "math" or self._known_name(node.id)):
                raise _verr(node, f"name '{node.id}' is not defined in the model")
            return
        if isinstance(node, (ast.List, ast.Tuple)):
            for e in node.elts:
                self.check_expr(e)
            return
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                raise _verr(node, "slices are not supported")
            self.check_expr(node.value)
            self.check_expr(node.slice)
            return
        if isinstance(node, ast.BinOp):
            if not isinstance(
                node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
            ):
                raise _verr(node, f"operator '{type(node.op).__name__}' is not supported")
            self.check_expr(node.left)
            self.check_expr(node.right)
            return
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
                raise _verr(node, f"operator '{type(node.op).__name__}' is not supported")
            self.check_expr(node.operand)
            return
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if not isinstance(
                    op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
                ):
                    raise _verr(node, f"comparison '{type(op).__name__}' is not supported")
            self.check_expr(node.left)
            for c in node.comparators:
                self.check_expr(c)
            return
        if isinstance(node, ast.BoolOp):
            for v in node.values:
                self.check_expr(v)
            return
        if isinstance(node, ast.IfExp):
            self.check_expr(node.test)
            self.check_expr(node.body)
            self.check_expr(node.orelse)
            return
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "math":
                if node.attr not in _MODEL_MATH:
                    raise _verr(node, f"math.{node.attr} is not supported in models")
                return
            raise _verr(node, "only 'math.<name>' attribute access is allowed")
        if isinstance(node, ast.Call):
            self._check_call(node, allow_append)
            return
        raise _verr(
            node, f"expression '{type(node).__name__}' is not allowed in model functions"
        )

    def _check_call(self, node: ast.Call, allow_append: bool) -> None:
        if node.keywords:
            raise _verr(node, "keyword arguments are not supported")
        func = node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id == "math":
                if func.attr not in _MODEL_MATH:
                    raise _verr(node, f"math.{func.attr} is not supported in models")
            elif (
                allow_append
                and isinstance(func.value, ast.Name)
                and func.attr == "append"
                and len(node.args) == 1
            ):
                if not self._known_name(func.value.id):
                    raise _verr(node, f"name '{func.value.id}' is not defined in the model")
            else:
                raise _verr(
                    node, "only 'math.<fn>' calls (or '<list>.append' statements) are allowed"
                )
        elif isinstance(func, ast.Name):
            if func.id == "range":
                raise _verr(node, "range() is only allowed in for-loop headers")
            if func.id not in _MODEL_HELPERS and func.id not in self.known:
                raise _verr(node, f"call to '{func.id}' is not defined in the model")
        else:
            raise _verr(node, "unsupported call form")
        for a in node.args:
            self.check_expr(a)


def _validate_function(fn: ast.FunctionDef, known: Set[str]) -> List[str]:
    args = fn.args
    if (
        args.vararg or args.kwarg or args.kwonlyargs
        or args.defaults or any(d is not None for d in args.kw_defaults)
    ):
        raise _verr(fn, "only plain positional parameters are allowed")
    params = [a.arg for a in args.args]
    for p in args.args:
        _check_ident(p.arg, fn.lineno, "parameter name")
    if fn.decorator_list:
        raise _verr(fn, "decorators are not allowed")
    checker = _FnCheck(fn, known)
    for stmt in _skip_docstring(fn.body):
        checker.check_stmt(stmt)
    return params


def validate_model_source(source: str) -> List[ast.FunctionDef]:
    """Validate a restricted model source; return its FunctionDef nodes.

    Raises TranspileError (a ValueError) with the offending line number for
    anything outside the whitelist (non-``def`` module statements, forbidden
    constructs, unknown names, reserved/dunder identifiers).
    """
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise TranspileError(
            f"Invalid model source syntax: {exc.msg} (line {exc.lineno})"
        ) from exc

    funcs: List[ast.FunctionDef] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.append(node)
        else:
            raise _verr(node, "only function definitions are allowed at module level")

    names: Set[str] = set()
    for fn in funcs:
        _check_ident(fn.name, fn.lineno, "function name")
        if fn.name in names:
            raise _verr(fn, f"duplicate function '{fn.name}'")
        names.add(fn.name)
    for fn in funcs:
        _validate_function(fn, names)
    return funcs


# ---- Python-side execution of the same restricted source --------------------


def exec_model_source(source: str) -> Dict[str, Any]:
    """Execute a validated model source; return ``{function name: callable}``.

    The namespace contains only ``math`` and the helper builtins, so even a
    validation bug cannot reach the real builtins.
    """
    funcs = validate_model_source(source)
    ns: Dict[str, Any] = {
        "__builtins__": {},
        "math": math,
        "range": range, "len": len, "abs": abs,
        "min": min, "max": max, "sum": sum, "round": round,
    }
    code = compile(source, "<techfig-model>", "exec")
    exec(code, ns)
    return {fn.name: ns[fn.name] for fn in funcs}


# ---- statement-level JS emitter ----------------------------------------------


def _emit_stmt(node: ast.stmt, ctx: _Ctx, depth: int) -> List[str]:
    ind = "  " * depth
    if isinstance(node, ast.Return):
        if node.value is None:
            return [ind + "return;"]
        return [f"{ind}return {_trans(node.value, ctx)};"]
    if isinstance(node, ast.Assign):
        out: List[str] = []
        for t in node.targets:
            if isinstance(t, ast.Name):
                out.append(f"{ind}{t.id} = {_trans(node.value, ctx)};")
            else:  # 2-name tuple target (validated)
                a, b = t.elts
                out.append(f"{ind}[{a.id}, {b.id}] = {_trans(node.value, ctx)};")
        return out
    if isinstance(node, ast.AugAssign):
        t = node.target.id
        if isinstance(node.op, ast.FloorDiv):
            return [f"{ind}{t} = Math.floor({t} / {_trans(node.value, ctx)});"]
        if isinstance(node.op, ast.Pow):
            return [f"{ind}{t} = Math.pow({t}, {_trans(node.value, ctx)});"]
        op = _BIN_OPS.get(type(node.op))
        return [f"{ind}{t} {op}= {_trans(node.value, ctx)};"]
    if isinstance(node, ast.For):
        t = node.target.id
        rargs = node.iter.args
        if len(rargs) == 1:
            start, stop, step_node = "0", _trans(rargs[0], ctx), None
        elif len(rargs) == 2:
            start, stop, step_node = _trans(rargs[0], ctx), _trans(rargs[1], ctx), None
        else:
            start = _trans(rargs[0], ctx)
            stop = _trans(rargs[1], ctx)
            step_node = rargs[2]
        if step_node is None:
            cond = f"{t} < {stop}"
            incr = f"{t} += 1"
        else:
            step_js = _trans(step_node, ctx)
            try:
                sv = ast.literal_eval(step_node)
                is_const = isinstance(sv, (int, float)) and not isinstance(sv, bool)
            except (ValueError, TypeError, SyntaxError):
                is_const = False
            if is_const:
                if sv == 0:
                    raise _verr(node, "range() step cannot be zero")
                cond = f"{t} < {stop}" if sv > 0 else f"{t} > {stop}"
                incr = f"{t} += {step_js}"
            else:
                cond = f"(({step_js}) > 0) ? ({t} < {stop}) : ({t} > {stop})"
                incr = f"{t} += ({step_js})"
        out = [f"{ind}for ({t} = {start}; {cond}; {incr}) {{"]
        for s in node.body:
            out.extend(_emit_stmt(s, ctx, depth + 1))
        out.append(ind + "}")
        return out
    if isinstance(node, ast.While):
        out = [f"{ind}while ({_trans(node.test, ctx)}) {{"]
        for s in node.body:
            out.extend(_emit_stmt(s, ctx, depth + 1))
        out.append(ind + "}")
        return out
    if isinstance(node, ast.If):
        return _emit_if(node, ctx, depth)
    if isinstance(node, ast.Expr):
        return [f"{ind}{_trans(node.value, ctx)};"]
    if isinstance(node, ast.Pass):
        return []
    if isinstance(node, ast.Break):
        return [ind + "break;"]
    if isinstance(node, ast.Continue):
        return [ind + "continue;"]
    raise _verr(node, f"cannot emit statement '{type(node).__name__}'")


def _emit_if(node: ast.If, ctx: _Ctx, depth: int) -> List[str]:
    ind = "  " * depth
    out = [f"{ind}if ({_trans(node.test, ctx)}) {{"]
    for s in node.body:
        out.extend(_emit_stmt(s, ctx, depth + 1))
    if node.orelse:
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            sub = _emit_if(node.orelse[0], ctx, depth)
            out.append(ind + "} else " + sub[0][len(ind):])
            out.extend(sub[1:])
            return out
        out.append(ind + "} else {")
        for s in node.orelse:
            out.extend(_emit_stmt(s, ctx, depth + 1))
    out.append(ind + "}")
    return out


def function_to_js(fn: ast.FunctionDef, known_funcs: Optional[Set[str]] = None) -> str:
    """Transpile one validated model function to a JS function declaration."""
    if not isinstance(fn, ast.FunctionDef):
        raise TranspileError("function_to_js expects a FunctionDef node")
    known = set(known_funcs) if known_funcs is not None else {fn.name}
    _validate_function(fn, known)
    ctx = _Ctx(extra_funcs=known, module_mode=True)
    params = [a.arg for a in fn.args.args]
    locals_ = _collect_locals(fn.body)
    lines = [f"function {fn.name}({', '.join(params)}) {{"]
    if locals_:
        lines.append(f"  let {', '.join(sorted(locals_))};")
    for stmt in _skip_docstring(fn.body):
        lines.extend(_emit_stmt(stmt, ctx, 1))
    lines.append("}")
    return "\n".join(lines)


def module_to_js(source: str) -> str:
    """Transpile a restricted model source (all top-level defs) to JavaScript."""
    funcs = validate_model_source(source)
    names = {fn.name for fn in funcs}
    return "\n\n".join(function_to_js(fn, known_funcs=names) for fn in funcs)


# ---- numeric verification against Node --------------------------------------


def verify_model(
    source: str,
    param_ranges: Dict[str, Tuple[float, float]],
    n_samples: int = 50,
    seed: int = 0,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> Dict[str, Any]:
    """Cross-check a model source between Python and Node.

    Every function whose parameters all appear in ``param_ranges`` is sampled
    at ``n_samples`` random argument tuples (seeded), evaluated in Python and
    in Node (``node -e`` harness reading the sample points from stdin), and
    compared with ``atol + rtol * |python|``.

    Returns ``{ok, n_checked, max_abs_err, mismatches}``; ``ok`` is ``None``
    with ``skipped: "node not found"`` when Node is not installed.
    """
    funcs = validate_model_source(source)
    node = shutil.which("node")
    if node is None:
        return {"ok": None, "skipped": "node not found"}

    rng = random.Random(seed)
    points: List[Dict[str, Any]] = []
    for fn in funcs:
        args = [a.arg for a in fn.args.args]
        if not args or not all(a in param_ranges for a in args):
            continue
        for _ in range(n_samples):
            points.append({
                "fn": fn.name,
                "args": [rng.uniform(*param_ranges[a]) for a in args],
            })
    if not points:
        return {"ok": True, "n_checked": 0, "max_abs_err": 0.0, "mismatches": []}

    names = sorted({p["fn"] for p in points})
    harness = (
        module_to_js(source)
        + "\nvar __REF = {" + ", ".join(f"{n}: {n}" for n in names) + "};\n"
        + "var __pts = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
        + "var __out = [];\n"
        + "for (var __i = 0; __i < __pts.length; __i++) {\n"
        + "  var __p = __pts[__i];\n"
        + "  try {\n"
        + "    __out.push(__REF[__p.fn].apply(null, __p.args));\n"
        + "  } catch (e) {\n"
        + "    __out.push({__err: String(e)});\n"
        + "  }\n"
        + "}\n"
        + "console.log(JSON.stringify(__out));\n"
    )
    res = subprocess.run(
        [node, "-e", harness],
        input=json.dumps(points), capture_output=True, text=True, timeout=120,
    )
    if res.returncode != 0:
        raise RuntimeError(f"node verification harness failed:\n{res.stderr}")
    js_out = json.loads(res.stdout)

    py_fns = exec_model_source(source)
    mismatches: List[Dict[str, Any]] = []
    n_checked = 0
    max_abs_err = 0.0
    for point, js_val in zip(points, js_out):
        n_checked += 1
        try:
            py_val = py_fns[point["fn"]](*point["args"])
        except Exception as exc:
            mismatches.append({
                "fn": point["fn"], "args": point["args"],
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        if isinstance(js_val, dict) and "__err" in js_val:
            mismatches.append({
                "fn": point["fn"], "args": point["args"],
                "py": py_val, "error": f"js: {js_val['__err']}",
            })
            continue
        if not (
            isinstance(py_val, (int, float)) and isinstance(js_val, (int, float))
        ):
            mismatches.append({
                "fn": point["fn"], "args": point["args"],
                "error": f"non-numeric comparison: py={py_val!r} js={js_val!r}",
            })
            continue
        err = abs(float(py_val) - float(js_val))
        max_abs_err = max(max_abs_err, err)
        if err > atol + rtol * abs(float(py_val)):
            mismatches.append({
                "fn": point["fn"], "args": point["args"],
                "py": py_val, "js": js_val, "abs_err": err,
            })
    return {
        "ok": not mismatches,
        "n_checked": n_checked,
        "max_abs_err": max_abs_err,
        "mismatches": mismatches,
    }
