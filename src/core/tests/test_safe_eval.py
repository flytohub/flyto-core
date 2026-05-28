# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Tests for the safe expression evaluator.

The most important assertions are the *negative* ones — the sandbox
escapes we explicitly want to refuse. Adding a new test here when a new
escape vector is discovered is the cheapest way to keep this honest.
"""

import pytest

from core.safe_eval import safe_eval, SafeEvalError, ALLOWED_BUILTINS


# ─── allowed expressions ──────────────────────────────────────────

@pytest.mark.parametrize("expr,context,expected", [
    ("1 + 1", {}, 2),
    ("True and False", {}, False),
    ("not None", {}, True),
    ("x == 5", {"x": 5}, True),
    ("x in [1, 2, 3]", {"x": 2}, True),
    ("x in [1, 2, 3]", {"x": 99}, False),
    ("len(items) > 0", {"items": [1, 2]}, True),
    ("status == 'open'", {"status": "open"}, True),
    ("a and b or c", {"a": 0, "b": 1, "c": 9}, 9),
    ("user['role'] == 'admin'", {"user": {"role": "admin"}}, True),
    ("count >= 1 and count <= 10", {"count": 5}, True),  # chained
    ("sum([1, 2, 3])", {}, 6),
    ("max(values)", {"values": [3, 7, 2]}, 7),
    ("abs(-5)", {}, 5),
    ("'hello'[1:4]", {}, "ell"),
])
def test_allowed(expr, context, expected):
    assert safe_eval(expr, context) == expected


# ─── refused: attribute access (the classic escape) ──────────────

def test_refuses_attribute_access():
    # Attribute is not in the allowed-node list, so _validate refuses it
    # at the AST-walk stage before reaching the dedicated Attribute branch.
    with pytest.raises(SafeEvalError, match="disallowed expression node: Attribute"):
        safe_eval("x.__class__", {"x": 1})

def test_refuses_dunder_walk():
    # The textbook eval escape — walk type hierarchy to subprocess.Popen
    with pytest.raises(SafeEvalError):
        safe_eval(
            "().__class__.__mro__[1].__subclasses__()",
            {},
        )

def test_refuses_method_call():
    with pytest.raises(SafeEvalError):
        safe_eval("'abc'.upper()", {})


# ─── refused: indirect callable / getattr trick ──────────────────

def test_refuses_call_of_expression():
    # If the caller smuggled a callable into context, we still
    # only allow Call.func == ast.Name. Subscript-then-call is the
    # most realistic indirection path — refused.
    with pytest.raises(SafeEvalError, match="direct named calls"):
        safe_eval("funcs[0](items)", {"funcs": [len], "items": [1]})

def test_refuses_unknown_builtin():
    with pytest.raises(SafeEvalError, match="not allowed"):
        safe_eval("eval('1+1')", {})

def test_refuses_getattr():
    with pytest.raises(SafeEvalError):
        safe_eval("getattr(x, '__class__')", {"x": 1})


# ─── refused: control flow / definitions ──────────────────────────

@pytest.mark.parametrize("expr", [
    "lambda x: x",
    "[x for x in range(10)]",
    "(x for x in items)",
    "{x: x for x in items}",
])
def test_refuses_advanced_syntax(expr):
    with pytest.raises(SafeEvalError):
        safe_eval(expr, {"items": [1]})


# ─── refused: CPU DoS ────────────────────────────────────────────

def test_refuses_huge_exponent():
    with pytest.raises(SafeEvalError, match="exponent too large"):
        safe_eval("2 ** 1000000", {})

def test_refuses_long_expression():
    expr = "1+" * 3000 + "1"
    with pytest.raises(SafeEvalError, match="too long"):
        safe_eval(expr, {})


# ─── name resolution ─────────────────────────────────────────────

def test_undefined_name():
    with pytest.raises(SafeEvalError, match="not defined"):
        safe_eval("undefined_var", {})

def test_builtin_shadowed_by_context():
    # Context wins over builtin — callers can override len() if they
    # really want. (Reasonable for guard DSL flexibility.)
    assert safe_eval("len", {"len": 42}) == 42


# ─── type contract ───────────────────────────────────────────────

def test_rejects_non_string_expression():
    with pytest.raises(SafeEvalError, match="must be str"):
        safe_eval(b"1+1", {})  # type: ignore[arg-type]
