# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Safe expression evaluator — drop-in replacement for `eval()` in
guard/condition contexts.

The historical pattern of `eval(expr, {"__builtins__": {}, ...})` is NOT
safe. The classic break-out

    ().__class__.__mro__[-1].__subclasses__()

walks the type hierarchy via attribute access and finds e.g.
`subprocess.Popen` without touching builtins at all. Any expression
that reaches a single Python object (even a literal `()`) can pivot
to arbitrary execution.

`safe_eval()` instead parses the expression to AST, walks it with a
whitelist of allowed node types, and refuses anything that could
escape: no attribute access, no comprehensions, no lambdas, no
imports, no f-strings, no walrus.

Supported:
  - Literals (numbers, strings, None, True, False)
  - Names resolved from the caller-supplied context dict
  - Comparisons:    a == b, a != b, a < b, a <= b, etc.
  - Boolean logic:  a and b, a or b, not a
  - Membership:     a in b, a not in b
  - Identity:       a is None, a is not None
  - Arithmetic:     + - * / // % ** unary +-
  - Indexing:       d['k'], lst[0], obj[1:2]
  - Containers:     [...], (...,), {...}, {k: v}
  - Function calls limited to ALLOWED_BUILTINS (len, str, int, float,
    bool, abs, min, max, sum, sorted, any, all, round)

Refused (raises SafeEvalError):
  - Attribute access:   x.y  → would re-open the dunder escape vector
  - Lambda, comprehensions, generator expressions
  - Import, with, try, raise, assert, def, class
  - Subscript assignment, walrus :=
  - Any name not in the context dict or builtins whitelist
"""

import ast
from typing import Any, Mapping


class SafeEvalError(ValueError):
    """Raised when an expression cannot be safely evaluated."""


# Function whitelist. Keep this conservative — every entry here is a
# capability the guard expression author can use. Add new entries only
# after verifying the function has no attribute-walk escape vectors
# (e.g. `getattr` is NOT here, because `getattr(x, '__class__')` reopens
# the dunder pivot).
ALLOWED_BUILTINS: Mapping[str, Any] = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "any": any,
    "all": all,
    "round": round,
}


# AST nodes safe to walk into. Anything not here triggers a refusal.
_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name, ast.Load,
    ast.Compare,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd, ast.Invert,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Subscript, ast.Slice, ast.Index,  # Index is py<3.9, kept for safety
    ast.Tuple, ast.List, ast.Dict, ast.Set,
    ast.Call,
)


def safe_eval(expression: str, context: Mapping[str, Any]) -> Any:
    """Evaluate ``expression`` against ``context`` without giving the
    expression author the ability to execute arbitrary Python.

    Raises ``SafeEvalError`` if the expression contains any disallowed
    syntax — never silently downgrades.
    """
    if not isinstance(expression, str):
        raise SafeEvalError(f"expression must be str, got {type(expression).__name__}")
    if len(expression) > 4096:
        # Bound how much CPU the parser/walker can be made to spend on
        # one expression — guards in workflow YAML should be small.
        raise SafeEvalError("expression too long (limit 4096 chars)")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise SafeEvalError(f"syntax error: {e}") from e

    _validate(tree)
    return _eval_node(tree.body, context)


def _validate(tree: ast.AST) -> None:
    """Pre-walk that rejects any unsupported node BEFORE evaluation.
    Fail-closed: walking the tree to evaluate would risk subtle escape
    paths if a new ast node type appears; the explicit allow-list here
    is the gate."""
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise SafeEvalError(
                f"disallowed expression node: {type(node).__name__}"
            )
        # Reject attribute access flat-out — `x.__class__`, `x.y`, all
        # of it. This is what closes the classical sandbox escape.
        if isinstance(node, ast.Attribute):  # type: ignore[unreachable]
            raise SafeEvalError("attribute access is not allowed")
    # Calls: only allow Name nodes as callees, never expressions that
    # produce a callable. That blocks `(getattr)(obj, '__class__')`
    # style indirection.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise SafeEvalError("only direct named calls are allowed")
            if node.func.id not in ALLOWED_BUILTINS:
                raise SafeEvalError(f"call to {node.func.id!r} not allowed")
            for kw in node.keywords:
                if kw.arg is None:
                    raise SafeEvalError("**kwargs unpacking not allowed")


def _eval_node(node: ast.AST, context: Mapping[str, Any]) -> Any:
    # Constants
    if isinstance(node, ast.Constant):
        return node.value

    # Names: look up in caller context, then builtins whitelist.
    if isinstance(node, ast.Name):
        if node.id in context:
            return context[node.id]
        if node.id in ALLOWED_BUILTINS:
            return ALLOWED_BUILTINS[node.id]
        raise SafeEvalError(f"name {node.id!r} is not defined")

    # Boolean logic
    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, context) for v in node.values]
        if isinstance(node.op, ast.And):
            result: Any = True
            for v in values:
                result = result and v
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for v in values:
                result = result or v
            return result
        raise SafeEvalError(f"bool op {type(node.op).__name__} not allowed")

    # Unary
    if isinstance(node, ast.UnaryOp):
        v = _eval_node(node.operand, context)
        if isinstance(node.op, ast.Not):
            return not v
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.UAdd):
            return +v
        if isinstance(node.op, ast.Invert):
            return ~v
        raise SafeEvalError(f"unary op {type(node.op).__name__} not allowed")

    # Arithmetic
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, context)
        right = _eval_node(node.right, context)
        op = node.op
        if isinstance(op, ast.Add): return left + right
        if isinstance(op, ast.Sub): return left - right
        if isinstance(op, ast.Mult): return left * right
        if isinstance(op, ast.Div): return left / right
        if isinstance(op, ast.FloorDiv): return left // right
        if isinstance(op, ast.Mod): return left % right
        if isinstance(op, ast.Pow):
            # Bound exponent to keep this from being a CPU DoS via 2**huge.
            if isinstance(right, (int, float)) and right > 64:
                raise SafeEvalError("exponent too large")
            return left ** right
        raise SafeEvalError(f"bin op {type(op).__name__} not allowed")

    # Comparisons (chained: a < b < c)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, context)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval_node(comp, context)
            if isinstance(op, ast.Eq):    ok = left == right
            elif isinstance(op, ast.NotEq): ok = left != right
            elif isinstance(op, ast.Lt):   ok = left < right
            elif isinstance(op, ast.LtE):  ok = left <= right
            elif isinstance(op, ast.Gt):   ok = left > right
            elif isinstance(op, ast.GtE):  ok = left >= right
            elif isinstance(op, ast.In):   ok = left in right
            elif isinstance(op, ast.NotIn): ok = left not in right
            elif isinstance(op, ast.Is):   ok = left is right
            elif isinstance(op, ast.IsNot): ok = left is not right
            else: raise SafeEvalError(f"compare op {type(op).__name__} not allowed")
            if not ok:
                return False
            left = right
        return True

    # Subscript
    if isinstance(node, ast.Subscript):
        target = _eval_node(node.value, context)
        slc = node.slice
        if isinstance(slc, ast.Slice):
            lower = _eval_node(slc.lower, context) if slc.lower else None
            upper = _eval_node(slc.upper, context) if slc.upper else None
            step = _eval_node(slc.step, context) if slc.step else None
            return target[slice(lower, upper, step)]
        return target[_eval_node(slc, context)]

    # Containers
    if isinstance(node, ast.List):
        return [_eval_node(e, context) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(e, context) for e in node.elts)
    if isinstance(node, ast.Set):
        return {_eval_node(e, context) for e in node.elts}
    if isinstance(node, ast.Dict):
        return {
            _eval_node(k, context) if k is not None else None: _eval_node(v, context)
            for k, v in zip(node.keys, node.values)
        }

    # Whitelisted function calls
    if isinstance(node, ast.Call):
        # _validate already ensured node.func is a Name in ALLOWED_BUILTINS.
        fn = ALLOWED_BUILTINS[node.func.id]  # type: ignore[union-attr]
        args = [_eval_node(a, context) for a in node.args]
        kwargs = {kw.arg: _eval_node(kw.value, context) for kw in node.keywords}
        return fn(*args, **kwargs)

    raise SafeEvalError(f"unhandled node type: {type(node).__name__}")
