# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Deterministic Warroom discovery, scenario generation, and scoring helpers.

This module intentionally avoids LLM calls. It turns observable website facts
into a graph and evidence scores that can be replayed by recipes or CI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping
from urllib.parse import urlparse, urlunparse

import yaml

SECRETISH_KEYS = re.compile(
    r"(authorization|cookie|token|password|secret|session|firebase|pat|bearer)",
    re.IGNORECASE,
)


@dataclass
class WarroomFinding:
    code: str
    severity: str
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def strip_query(url: str) -> str:
    parsed = urlparse(str(url or ""))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def redact(value: Any) -> Any:
    """Redact secret-looking keys and strip URL query strings."""
    if isinstance(value, Mapping):
        redacted: Dict[str, Any] = {}
        for key, inner in value.items():
            if SECRETISH_KEYS.search(str(key)):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact(inner)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and re.match(r"^https?://", value):
        return strip_query(value)
    return value


def stable_selector(control: Mapping[str, Any], index: int = 0) -> str:
    for key in ("testid", "data-testid", "aria_label", "aria-label", "name", "id"):
        value = str(control.get(key) or "").strip()
        if value:
            if key in {"testid", "data-testid"}:
                return f'[data-testid="{_escape_selector(value)}"]'
            if key in {"aria_label", "aria-label"}:
                return f'[aria-label="{_escape_selector(value)}"]'
            if key == "name":
                tag = str(control.get("tag") or "input").lower()
                return f'{tag}[name="{_escape_selector(value)}"]'
            return f"#{_escape_selector(value)}"
    selector = str(control.get("selector") or "").strip()
    if selector:
        return selector
    return f'[data-warroom-control="{index + 1}"]'


def _escape_selector(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def control_label(control: Mapping[str, Any]) -> str:
    for key in ("text", "label", "aria_label", "aria-label", "title", "placeholder", "href"):
        value = str(control.get(key) or "").strip()
        if value:
            return value[:120]
    return "unnamed control"


def build_site_graph(target: str, pages: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a deterministic graph from page snapshots or browser observations."""
    page_nodes: List[Dict[str, Any]] = []
    action_edges: List[Dict[str, Any]] = []
    api_edges: List[Dict[str, Any]] = []
    findings: List[WarroomFinding] = []

    for page_index, raw_page in enumerate(pages):
        page = redact(dict(raw_page))
        url = strip_query(str(page.get("url") or target))
        page_id = f"page_{page_index + 1}"
        text = str(page.get("text") or page.get("body_text") or "")
        console_errors = page.get("console_errors") or []
        controls = list(page.get("controls") or [])
        requests = list(page.get("requests") or page.get("network") or [])
        states = infer_states(page)

        page_nodes.append({
            "id": page_id,
            "url": url,
            "title": page.get("title", ""),
            "body_chars": len(text),
            "states": states,
            "control_count": len(controls),
            "api_count": len(requests),
            "screenshot": page.get("screenshot", ""),
        })

        if not text and not controls:
            findings.append(WarroomFinding(
                code="blank_screen",
                severity="P0",
                message=f"{url} has no visible text or controls.",
                evidence={"page_id": page_id, "url": url},
            ))
        if console_errors:
            findings.append(WarroomFinding(
                code="console_error",
                severity="P0",
                message=f"{url} emitted console errors.",
                evidence={"page_id": page_id, "count": len(console_errors)},
            ))
        if page.get("horizontal_overflow"):
            findings.append(WarroomFinding(
                code="horizontal_overflow",
                severity="P1",
                message=f"{url} has horizontal overflow.",
                evidence={"page_id": page_id, "url": url},
            ))

        for control_index, control in enumerate(controls):
            selector = stable_selector(control, control_index)
            disabled = bool(control.get("disabled") or control.get("aria_disabled"))
            action_id = f"{page_id}_action_{control_index + 1}"
            action_edges.append({
                "id": action_id,
                "page_id": page_id,
                "url": url,
                "label": control_label(control),
                "kind": str(control.get("kind") or control.get("tag") or "control"),
                "selector": selector,
                "disabled": disabled,
                "href": strip_query(str(control.get("href") or "")) if control.get("href") else "",
                "expected_state": infer_expected_state(control),
            })
            if not disabled and not control.get("href") and not control_label(control):
                findings.append(WarroomFinding(
                    code="unlabeled_action",
                    severity="P1",
                    message="A reachable control has no stable label.",
                    evidence={"page_id": page_id, "selector": selector},
                ))

        for request_index, request in enumerate(requests):
            api_id = f"{page_id}_api_{request_index + 1}"
            status = int(request.get("status") or 0)
            api_edges.append({
                "id": api_id,
                "page_id": page_id,
                "method": str(request.get("method") or "GET").upper(),
                "url": strip_query(str(request.get("url") or "")),
                "status": status,
                "resource_type": request.get("resource_type", ""),
                "trigger": request.get("trigger", ""),
            })
            if status >= 500:
                findings.append(WarroomFinding(
                    code="api_5xx",
                    severity="P0",
                    message="A browser-observed API request returned 5xx.",
                    evidence={"page_id": page_id, "api_id": api_id, "status": status},
                ))
            elif status >= 400:
                findings.append(WarroomFinding(
                    code="api_4xx",
                    severity="P1",
                    message="A browser-observed API request returned 4xx.",
                    evidence={"page_id": page_id, "api_id": api_id, "status": status},
                ))

    graph = {
        "schema_version": "warroom.site_graph.v1",
        "target": strip_query(target),
        "generated_at": now_iso(),
        "pages": page_nodes,
        "actions": action_edges,
        "apis": api_edges,
        "findings": [finding.to_dict() for finding in findings],
    }
    graph["scores"] = score_graph(graph)
    return graph


def infer_states(page: Mapping[str, Any]) -> List[str]:
    text = str(page.get("text") or page.get("body_text") or "").lower()
    states: List[str] = []
    if any(token in text for token in ("loading", "載入", "読み込み", "laden")):
        states.append("loading")
    if any(token in text for token in ("error", "failed", "失敗", "錯誤", "エラー")):
        states.append("error")
    if any(token in text for token in ("empty", "no data", "no results", "沒有資料")):
        states.append("resolved_empty")
    if any(token in text for token in ("locked", "upgrade", "權限", "permission", "paywall")):
        states.append("locked_preview")
    if page.get("hidden"):
        states.append("hidden")
    if text and not states:
        states.append("resolved_data")
    return sorted(set(states))


def infer_expected_state(control: Mapping[str, Any]) -> str:
    if control.get("disabled") or control.get("aria_disabled"):
        return "disabled"
    label = control_label(control).lower()
    if any(token in label for token in ("upgrade", "locked", "premium", "pro")):
        return "locked_preview"
    return "actionable"


def score_graph(graph: Mapping[str, Any]) -> Dict[str, Any]:
    pages = list(graph.get("pages") or [])
    actions = list(graph.get("actions") or [])
    apis = list(graph.get("apis") or [])
    findings = list(graph.get("findings") or [])

    p0 = sum(1 for item in findings if item.get("severity") == "P0")
    p1 = sum(1 for item in findings if item.get("severity") == "P1")
    exercised_weight = len(pages) * 3 + len(actions) + len(apis)
    discovered_weight = max(exercised_weight + p0 * 8 + p1 * 3, 1)
    exploration_coverage = round(exercised_weight / discovered_weight, 3)
    visual_integrity = round(max(0.0, 1.0 - (p0 * 0.25 + p1 * 0.08)), 3)
    api_ui_consistency = round(
        1.0 if not apis else max(0.0, 1.0 - sum(1 for api in apis if api.get("status", 0) >= 400) / len(apis)),
        3,
    )
    business_logic_confidence = round(max(0.0, min(1.0, exploration_coverage * visual_integrity)), 3)

    return {
        "exploration_coverage": exploration_coverage,
        "replay_reliability": 1.0,
        "state_model_confidence": 1.0 if pages else 0.0,
        "api_ui_consistency": api_ui_consistency,
        "business_logic_confidence": business_logic_confidence,
        "visual_integrity": visual_integrity,
        "p0": p0,
        "p1": p1,
    }


def generate_scenarios(graph: Mapping[str, Any], *, name: str = "Warroom Generated Regression") -> Dict[str, Any]:
    """Generate deterministic YAML-compatible scenarios from a site graph."""
    steps: List[Dict[str, Any]] = []
    for page in graph.get("pages", []):
        page_id = str(page.get("id"))
        steps.append({
            "id": f"{page_id}_goto",
            "module": "browser.goto",
            "params": {"url": page.get("url", graph.get("target", ""))},
        })
        steps.append({
            "id": f"{page_id}_dom_assert",
            "module": "browser.evaluate",
            "params": {
                "script": (
                    "() => ({"
                    "text_chars: (document.body?.innerText || '').length,"
                    "horizontal_overflow: document.documentElement.scrollWidth > innerWidth + 2,"
                    "title: document.title"
                    "})"
                )
            },
            "assertions": [
                {"path": "result.text_chars", "operator": ">", "expected": 0, "severity": "P0"},
                {"path": "result.horizontal_overflow", "operator": "==", "expected": False, "severity": "P1"},
            ],
        })

    return {
        "name": name,
        "schema_version": "warroom.scenarios.v1",
        "generated_from": graph.get("schema_version", ""),
        "target": graph.get("target", ""),
        "steps": steps,
    }


def scenarios_to_yaml(scenarios: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(scenarios), sort_keys=False, allow_unicode=True)


def evaluate_run(run_result: Mapping[str, Any]) -> Dict[str, Any]:
    unwrapped = unwrap_run_result(run_result)
    results = list(unwrapped.get("results") or unwrapped.get("steps") or [])
    failed = [item for item in results if item.get("status") == "failed"]
    p0 = sum(1 for item in failed if item.get("severity") == "P0")
    p1 = sum(1 for item in failed if item.get("severity") == "P1")
    total = max(len(results), 1)
    stable = sum(1 for item in results if item.get("status") == "passed")
    return {
        "passed": not failed,
        "summary": {
            "total": len(results),
            "passed": stable,
            "failed": len(failed),
            "p0": p0,
            "p1": p1,
            "replay_reliability": round(stable / total, 3),
        },
        "findings": failed,
    }


def unwrap_run_result(run_result: Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(run_result.get("data"), Mapping):
        data = run_result["data"]
        if "results" in data or "steps" in data:
            return data
    return run_result


def evidence_pack(
    *,
    site_graph: Mapping[str, Any] | None = None,
    scenarios: Mapping[str, Any] | None = None,
    run_result: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    graph = dict(site_graph or {})
    unwrapped_run = unwrap_run_result(run_result or {"results": []})
    run_eval = evaluate_run(unwrapped_run)
    graph_scores = dict(graph.get("scores") or {})
    p0 = int(graph_scores.get("p0", 0)) + int(run_eval["summary"]["p0"])
    p1 = int(graph_scores.get("p1", 0)) + int(run_eval["summary"]["p1"])
    verdict = "pass" if p0 == 0 and p1 == 0 and run_eval["passed"] else "fail"
    return {
        "schema_version": "warroom.evidence_pack.v1",
        "generated_at": now_iso(),
        "verdict": verdict,
        "scores": {
            **graph_scores,
            "replay_reliability": run_eval["summary"]["replay_reliability"],
            "p0": p0,
            "p1": p1,
        },
        "site_graph": graph,
        "scenarios": dict(scenarios or {}),
        "run": dict(unwrapped_run or {}),
        "run_evaluation": run_eval,
        "artifacts": redact(dict(artifacts or {})),
    }


def evidence_to_markdown(pack: Mapping[str, Any]) -> str:
    scores = pack.get("scores") or {}
    lines = [
        "# Warroom Evidence Pack",
        "",
        f"Verdict: {pack.get('verdict', 'unknown')}",
        f"Generated: {pack.get('generated_at', '')}",
        "",
        "## Scores",
    ]
    for key in (
        "exploration_coverage",
        "replay_reliability",
        "state_model_confidence",
        "api_ui_consistency",
        "business_logic_confidence",
        "visual_integrity",
        "p0",
        "p1",
    ):
        lines.append(f"- {key}: {scores.get(key, 'n/a')}")
    lines.extend(["", "## Findings"])
    findings = (pack.get("site_graph") or {}).get("findings") or []
    findings.extend((pack.get("run_evaluation") or {}).get("findings") or [])
    if findings:
        for finding in findings:
            lines.append(f"- {finding.get('severity', 'P?')} {finding.get('code', 'finding')}: {finding.get('message', '')}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def to_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)
