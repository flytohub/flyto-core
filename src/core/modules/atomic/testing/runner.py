# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Shared deterministic step runner for testing and Warroom modules."""

from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping

from ...registry import get_module


def get_path(data: Any, path: str) -> Any:
    current = data
    for part in str(path or "").split("."):
        if part == "":
            continue
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def resolve_refs(value: Any, step_results: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        ref = value[2:-1].strip()
        if ref.startswith("context."):
            return get_path(context, ref.removeprefix("context."))
        step_id, _, path = ref.partition(".")
        return get_path(step_results.get(step_id), path)
    if isinstance(value, list):
        return [resolve_refs(item, step_results, context) for item in value]
    if isinstance(value, dict):
        return {key: resolve_refs(inner, step_results, context) for key, inner in value.items()}
    return value


def evaluate_assertion(result: Any, assertion: Mapping[str, Any]) -> Dict[str, Any]:
    path = str(assertion.get("path") or "")
    operator = str(assertion.get("operator") or "truthy")
    expected = assertion.get("expected")
    actual = get_path(result, path) if path else result

    if operator == "==":
        passed = actual == expected
    elif operator == "!=":
        passed = actual != expected
    elif operator == ">":
        passed = actual > expected
    elif operator == ">=":
        passed = actual >= expected
    elif operator == "<":
        passed = actual < expected
    elif operator == "<=":
        passed = actual <= expected
    elif operator == "contains":
        passed = expected in actual if actual is not None else False
    elif operator == "not_contains":
        passed = expected not in actual if actual is not None else True
    elif operator == "exists":
        passed = actual is not None
    elif operator == "truthy":
        passed = bool(actual)
    elif operator == "falsy":
        passed = not bool(actual)
    else:
        raise ValueError(f"Unsupported assertion operator: {operator}")

    return {
        "path": path,
        "operator": operator,
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "severity": assertion.get("severity", "P1"),
        "message": assertion.get("message", ""),
    }


async def execute_test_steps(
    steps: Iterable[Mapping[str, Any]],
    *,
    context: Dict[str, Any] | None = None,
    stop_on_failure: bool = True,
    timeout_per_step: float | int = 30000,
) -> Dict[str, Any]:
    base_context = context or {}
    step_results: Dict[str, Any] = {}
    results: List[Dict[str, Any]] = []
    passed = 0
    failed = 0

    for index, step in enumerate(steps):
        step_id = str(step.get("id") or f"step_{index + 1}")
        module_id = str(step.get("module") or "")
        started = time.monotonic()
        result: Dict[str, Any] = {
            "step": index + 1,
            "id": step_id,
            "name": step.get("name") or step.get("label") or step_id,
            "module": module_id,
            "status": "passed",
            "severity": step.get("severity", "P1"),
            "duration_ms": 0,
        }

        if not module_id:
            result.update({"status": "failed", "error": "step.module is required"})
        else:
            try:
                module_class = get_module(module_id)
                params = resolve_refs(deepcopy(step.get("params") or {}), step_results, base_context)
                module_context = dict(base_context)
                module_context["step_results"] = step_results
                instance = module_class(params, module_context)
                output = await asyncio.wait_for(
                    instance.execute(),
                    timeout=float(timeout_per_step) / 1000,
                )
                result["output"] = output
                if isinstance(output, dict) and output.get("ok") is False:
                    result["status"] = "failed"
                    result["error"] = output.get("error") or "module returned ok=false"
                if isinstance(output, dict) and output.get("passed") is False:
                    result["status"] = "failed"
                    result["error"] = output.get("message") or "module returned passed=false"

                assertion_results = [
                    evaluate_assertion(output, assertion)
                    for assertion in step.get("assertions", []) or []
                ]
                if assertion_results:
                    result["assertions"] = assertion_results
                failed_assertions = [item for item in assertion_results if not item["passed"]]
                if failed_assertions:
                    result["status"] = "failed"
                    result["error"] = failed_assertions[0].get("message") or "assertion failed"
                    if any(item.get("severity") == "P0" for item in failed_assertions):
                        result["severity"] = "P0"
            except Exception as exc:  # noqa: BLE001 - test runner records failures
                result.update({"status": "failed", "error": str(exc)})

        result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        step_results[step_id] = result.get("output", result)
        results.append(result)
        if result["status"] == "passed":
            passed += 1
        else:
            failed += 1
            if stop_on_failure:
                break

    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "results": results,
    }
