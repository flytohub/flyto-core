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
    r"(authorization|cookie|auth[_-]?token|access[_-]?token|refresh[_-]?token|password|secret|session|firebase|bearer|(^|[_-])(token|pat)([_-]|$))",
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


def _path_key(url: str) -> str:
    parsed = urlparse(str(url or ""))
    path = parsed.path or "/"
    return path.rstrip("/") or "/"


def _explicit_reachable_paths(page: Mapping[str, Any]) -> List[str]:
    paths: List[str] = []
    for key in ("reachable_paths", "router_paths", "sitemap_paths"):
        values = page.get(key) or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            if not value:
                continue
            paths.append(_path_key(str(value)))
    return sorted(set(paths))


def infer_intent(label: str, fallback: str = "inspect") -> Dict[str, Any]:
    """Infer a stable, human-readable intent from a label without using an LLM."""
    raw = str(label or "").strip()
    normalized = re.sub(r"\s+", " ", raw).lower()
    verb = fallback
    intent_object = normalized or "unknown"
    patterns = [
        ("create", ("create", "add", "new", "建立", "新增")),
        ("delete", ("delete", "remove", "刪除", "削除")),
        ("invite", ("invite", "邀請")),
        ("generate", ("generate", "export", "report", "產生", "匯出")),
        ("run", ("run", "scan", "start", "verify", "execute", "執行", "掃描", "驗證")),
        ("configure", ("setting", "configure", "connect", "設定", "連接")),
        ("view", ("view", "open", "details", "檢視", "查看")),
    ]
    for candidate, tokens in patterns:
        if any(token in normalized for token in tokens):
            verb = candidate
            break
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "unknown"
    return {
        "verb": verb,
        "object": intent_object[:80],
        "slug": f"{verb}_{slug}"[:96],
    }


def _append_finding(findings: List[WarroomFinding], code: str, severity: str, message: str, evidence: Dict[str, Any]) -> None:
    findings.append(WarroomFinding(code=code, severity=severity, message=message, evidence=evidence))


def build_site_graph(target: str, pages: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a deterministic graph from page snapshots or browser observations."""
    page_nodes: List[Dict[str, Any]] = []
    action_edges: List[Dict[str, Any]] = []
    api_edges: List[Dict[str, Any]] = []
    intent_nodes: Dict[str, Dict[str, Any]] = {}
    intent_edges: List[Dict[str, Any]] = []
    state_edges: List[Dict[str, Any]] = []
    reachable_paths: set[str] = set()
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
        reachable_paths.update(_explicit_reachable_paths(page))
        reachable_paths.add(_path_key(url))

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
            _append_finding(
                findings,
                "blank_screen",
                "P0",
                f"{url} has no visible text or controls.",
                {"page_id": page_id, "url": url},
            )
        if console_errors:
            _append_finding(
                findings,
                "console_error",
                "P0",
                f"{url} emitted console errors.",
                {"page_id": page_id, "count": len(console_errors)},
            )
        if page.get("horizontal_overflow"):
            _append_finding(
                findings,
                "horizontal_overflow",
                "P1",
                f"{url} has horizontal overflow.",
                {"page_id": page_id, "url": url},
            )

        for control_index, control in enumerate(controls):
            selector = stable_selector(control, control_index)
            disabled = bool(control.get("disabled") or control.get("aria_disabled"))
            action_id = f"{page_id}_action_{control_index + 1}"
            label = control_label(control)
            intent = infer_intent(str(control.get("intent") or label), fallback="click")
            intent_id = intent["slug"]
            intent_nodes.setdefault(intent_id, {
                "id": intent_id,
                "verb": intent["verb"],
                "object": intent["object"],
                "source": "control",
            })
            action_edges.append({
                "id": action_id,
                "page_id": page_id,
                "url": url,
                "label": label,
                "kind": str(control.get("kind") or control.get("tag") or "control"),
                "selector": selector,
                "disabled": disabled,
                "href": strip_query(str(control.get("href") or "")) if control.get("href") else "",
                "expected_state": infer_expected_state(control),
                "intent_id": intent_id,
            })
            intent_edges.append({
                "from": action_id,
                "to": intent_id,
                "kind": "action_realizes_intent",
            })
            if not disabled and not control.get("href") and label == "unnamed control":
                _append_finding(
                    findings,
                    "unlabeled_action",
                    "P1",
                    "A reachable control has no stable label.",
                    {"page_id": page_id, "selector": selector},
                )

        for request_index, request in enumerate(requests):
            api_id = f"{page_id}_api_{request_index + 1}"
            status = int(request.get("status") or 0)
            api_url = strip_query(str(request.get("url") or ""))
            trigger = str(request.get("trigger") or "")
            api_edges.append({
                "id": api_id,
                "page_id": page_id,
                "method": str(request.get("method") or "GET").upper(),
                "url": api_url,
                "status": status,
                "resource_type": request.get("resource_type", ""),
                "trigger": trigger,
                "ghost_api_type": classify_ghost_api(request, states),
            })
            if status >= 500:
                _append_finding(
                    findings,
                    "api_5xx",
                    "P0",
                    "A browser-observed API request returned 5xx.",
                    {"page_id": page_id, "api_id": api_id, "status": status},
                )
            elif status >= 400:
                _append_finding(
                    findings,
                    "api_4xx",
                    "P1",
                    "A browser-observed API request returned 4xx.",
                    {"page_id": page_id, "api_id": api_id, "status": status},
                )
            ghost_type = classify_ghost_api(request, states)
            if ghost_type == "type_a_ui_api_no_effect":
                _append_finding(
                    findings,
                    "ghost_api_type_a",
                    "P1",
                    "A UI-triggered API returned successfully but produced no observed UI effect.",
                    {"page_id": page_id, "api_id": api_id, "url": api_url, "trigger": trigger},
                )
            elif ghost_type == "type_b_api_without_ui_path":
                _append_finding(
                    findings,
                    "ghost_api_type_b",
                    "P1",
                    "An API endpoint was observed or cataloged without a reachable UI path.",
                    {"page_id": page_id, "api_id": api_id, "url": api_url},
                )
            elif ghost_type == "type_c_error_swallowed":
                _append_finding(
                    findings,
                    "ghost_api_type_c",
                    "P0",
                    "An API error was not reflected by an observable UI error state.",
                    {"page_id": page_id, "api_id": api_id, "status": status},
                )

        _append_state_assertion_findings(findings, page_id, page)
        _append_business_state_findings(findings, page_id, page, action_edges)

        for state_index, state in enumerate(states):
            state_edges.append({
                "id": f"{page_id}_state_{state_index + 1}",
                "page_id": page_id,
                "state": state,
                "source": "text_or_marker",
            })

    graph = {
        "schema_version": "warroom.site_graph.v1",
        "target": strip_query(target),
        "generated_at": now_iso(),
        "pages": page_nodes,
        "actions": action_edges,
        "apis": api_edges,
        "intents": sorted(intent_nodes.values(), key=lambda item: item["id"]),
        "intent_edges": intent_edges,
        "state_graph": {
            "states": state_edges,
            "allowed_states": [
                "idle",
                "loading",
                "error",
                "resolved_empty",
                "resolved_data",
                "disabled",
                "locked_preview",
                "hidden",
                "pending",
                "partial",
                "stale",
                "expired",
            ],
        },
        "reachable_paths": sorted(reachable_paths),
        "observed_paths": sorted({_path_key(page.get("url", "")) for page in page_nodes}),
        "findings": [finding.to_dict() for finding in findings],
    }
    graph["scores"] = score_graph(graph)
    return graph


def classify_ghost_api(request: Mapping[str, Any], page_states: Iterable[str]) -> str:
    status = int(request.get("status") or 0)
    has_ui_effect = request.get("has_ui_effect")
    ui_effect = str(request.get("ui_effect") or "").strip().lower()
    trigger = str(request.get("trigger") or "").strip()
    ui_path = request.get("ui_path")
    source = str(request.get("source") or "").strip().lower()
    if status >= 400 and "error" not in set(page_states):
        return "type_c_error_swallowed"
    if ui_path is False or request.get("orphan") is True or source in {"api_catalog", "openapi", "schema"}:
        return "type_b_api_without_ui_path"
    if trigger and status and status < 400 and (has_ui_effect is False or ui_effect in {"none", "no-op", "noop"}):
        return "type_a_ui_api_no_effect"
    return ""


def _append_state_assertion_findings(findings: List[WarroomFinding], page_id: str, page: Mapping[str, Any]) -> None:
    assertions = page.get("state_assertions") or []
    if not isinstance(assertions, list):
        return
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, Mapping):
            continue
        expected = assertion.get("expected")
        observed = assertion.get("observed")
        if expected == observed:
            continue
        severity = str(assertion.get("severity") or "P0")
        _append_finding(
            findings,
            "state_contradiction",
            severity,
            "Observed product state contradicted the declared invariant.",
            {
                "page_id": page_id,
                "assertion_id": assertion.get("id") or f"assertion_{index + 1}",
                "expected": expected,
                "observed": observed,
            },
        )


def _append_business_state_findings(
    findings: List[WarroomFinding],
    page_id: str,
    page: Mapping[str, Any],
    action_edges: List[Mapping[str, Any]],
) -> None:
    state = page.get("business_state") or page.get("api_state") or {}
    if not isinstance(state, Mapping):
        return
    success = state.get("success")
    states = set(infer_states(page))
    if success is True and "error" in states:
        _append_finding(
            findings,
            "state_contradiction",
            "P0",
            "API reported success while the UI rendered an error state.",
            {"page_id": page_id, "expected": "success_ui", "observed": "error_ui"},
        )
    credit_value = state.get("credits_remaining", state.get("credits"))
    try:
        credits_remaining = int(credit_value)
    except (TypeError, ValueError):
        return
    if credits_remaining > 0:
        return
    metered_tokens = ("generate", "run", "scan", "export", "verify", "red team", "pentest")
    page_actions = [action for action in action_edges if action.get("page_id") == page_id]
    for action in page_actions:
        label = str(action.get("label") or "").lower()
        if not action.get("disabled") and any(token in label for token in metered_tokens):
            _append_finding(
                findings,
                "state_contradiction",
                "P0",
                "Metered action is enabled while credits are exhausted.",
                {
                    "page_id": page_id,
                    "action_id": action.get("id"),
                    "credits_remaining": credits_remaining,
                    "label": action.get("label"),
                },
            )


def infer_states(page: Mapping[str, Any]) -> List[str]:
    text = str(page.get("text") or page.get("body_text") or "").lower()
    states: List[str] = []
    explicit = page.get("state") or page.get("states")
    if isinstance(explicit, str):
        states.append(explicit)
    elif isinstance(explicit, list):
        states.extend(str(item) for item in explicit if item)
    if not text and page.get("disabled"):
        states.append("disabled")
    if any(token in text for token in ("loading", "載入", "読み込み", "laden")):
        states.append("loading")
    if any(token in text for token in ("error", "failed", "失敗", "錯誤", "エラー")):
        states.append("error")
    if any(token in text for token in ("empty", "no data", "no results", "沒有資料")):
        states.append("resolved_empty")
    if any(token in text for token in ("locked", "upgrade", "權限", "permission", "paywall")):
        states.append("locked_preview")
    if any(token in text for token in ("pending", "generating", "queued", "處理中", "生成中")):
        states.append("pending")
    if any(token in text for token in ("partial", "partially", "部分")):
        states.append("partial")
    if any(token in text for token in ("stale", "cached", "outdated", "過期快取")):
        states.append("stale")
    if any(token in text for token in ("expired", "session expired", "重新登入", "期限切れ")):
        states.append("expired")
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
    observed_paths = set(graph.get("observed_paths") or [])
    reachable_paths = set(graph.get("reachable_paths") or observed_paths)
    reachable_weight = max(len(reachable_paths) * 3 + len(actions) + len(apis), 1)
    exploration_coverage = round(exercised_weight / discovered_weight, 3)
    observed_coverage = round(len(observed_paths) / max(len(observed_paths), 1), 3)
    reachable_coverage = round(min(1.0, len(observed_paths) / max(len(reachable_paths), 1)), 3)
    visual_integrity = round(max(0.0, 1.0 - (p0 * 0.25 + p1 * 0.08)), 3)
    api_ui_consistency = round(
        1.0 if not apis else max(0.0, 1.0 - sum(1 for api in apis if api.get("status", 0) >= 400) / len(apis)),
        3,
    )
    business_logic_confidence = round(max(0.0, min(1.0, exploration_coverage * visual_integrity)), 3)

    return {
        "exploration_coverage": exploration_coverage,
        "observed_coverage": observed_coverage,
        "reachable_coverage": reachable_coverage,
        "reachable_weight": reachable_weight,
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
        "observed_coverage",
        "reachable_coverage",
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
