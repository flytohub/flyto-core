# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Shared deterministic receipt and validation helpers for baseline solvers."""

import hashlib
import json
import math
import re
from typing import Any, Dict

from .errors import ValidationError

RECEIPT_SCHEMA = "flyto.core.domain-solver-receipt.v1"
RECEIPT_VERSION = "flyto.execution-verification-receipt.v1"
MAX_SAFE_INTEGER = (1 << 53) - 1
_SAFE_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}\Z")


def finite_number(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be a finite number", field=field)
    if type(value) is int and not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
        raise ValidationError(f"{field} exceeds the safe numeric range", field=field)
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        raise ValidationError(f"{field} must be a finite number", field=field) from None
    if not math.isfinite(normalized):
        raise ValidationError(f"{field} must be a finite number", field=field)
    if positive and normalized <= 0:
        raise ValidationError(f"{field} must be positive", field=field)
    return normalized


def safe_text(value: Any, field: str) -> str:
    """Return one bounded identifier-like string suitable for evidence."""
    if type(value) is not str:
        raise ValidationError(f"{field} must be a safe bounded string", field=field)
    normalized = value.strip()
    if not _SAFE_TEXT.fullmatch(normalized) or ".." in normalized or "//" in normalized:
        raise ValidationError(f"{field} must be a safe bounded string", field=field)
    return normalized


def finite_result(value: float, field: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValidationError(f"{field} arithmetic result is not finite", field=field)
    return value


def exact_unit(params: Dict[str, Any], field: str, supported: str) -> str:
    value = params.get(field)
    if value != supported:
        raise ValidationError(f"{field} must be {supported!r}", field=field)
    return supported


def receipt(module_id: str, solver_version: str, equation: str,
            normalized_inputs: Dict[str, Any], units: Dict[str, str],
            result: Dict[str, Any], assumptions: list[str],
            validation_checks: Dict[str, bool]) -> Dict[str, Any]:
    evidence = {
        "solver_schema": RECEIPT_SCHEMA,
        "solver_schema_version": "1.0.0",
        "module_id": module_id,
        "solver_id": module_id,
        "solver_version": solver_version,
        "equation_model": equation,
        "normalized_inputs": normalized_inputs,
        "units": units,
        "result": result,
        "assumptions": assumptions,
        "checks": validation_checks,
    }
    try:
        encoded = json.dumps(
            evidence, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError("solver evidence must be finite JSON") from exc
    detached = json.loads(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    return {
        "receipt_version": RECEIPT_VERSION,
        "success": True,
        "status": "verified",
        "evidence_id": f"domain-solver:{module_id}:{digest[:24]}",
        "evidence_sha256": digest,
        "evidence": detached,
    }
