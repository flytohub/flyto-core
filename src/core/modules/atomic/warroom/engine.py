# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Deterministic verification helpers.

This module intentionally avoids LLM calls. It turns observable website facts
into a graph and evidence scores that can be replayed by recipes or CI.
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping
from urllib.parse import urlparse, urlunparse

import yaml

SECRETISH_KEYS = re.compile(
    r"(authorization|cookie|auth[_-]?token|access[_-]?token|refresh[_-]?token|password|secret|session|firebase|bearer|(^|[_-])(token|pat)([_-]|$))",
    re.IGNORECASE,
)
SAFE_EVIDENCE_METADATA_KEYS = {"authorization_gate"}

CORE_DETERMINISTIC_VERIFICATION_SCHEMA = "flyto.core.deterministic_verification.v1"
LEGACY_AUTOMATION_TEST_MODEL_SCHEMA = "warroom.automation_test_model.v1"

DETERMINISTIC_ENGINE_MODE = {
    "name": "Deterministic Verification Runtime",
    "execution_mode": "deterministic_evidence_first",
    "llm_required": False,
    "llm_role": "optional_evidence_reviewer",
    "fact_source": "browser_dom_network_screenshot_sse",
    "gate_authority": "deterministic_evidence_gate",
    "human_editable_yaml": True,
}

DETERMINISTIC_TESTING_CONTRACT = {
    "inputs": [
        "site_graph",
        "intent_graph",
        "state_graph",
        "api_graph",
        "yaml_replay",
        "browser_artifacts",
        "event_stream",
    ],
    "outputs": [
        "evidence_pack",
        "gate_verdict",
        "readiness_score",
        "false_empty",
        "false_locked",
        "hidden_error",
        "state_contradictions",
        "ghost_api_findings",
        "rbac_fail_open",
        "replay_evidence",
    ],
    "llm_can_create_facts": False,
    "llm_can_gate": False,
}

DETERMINISTIC_RULE_CODES = [
    "false_empty",
    "false_locked",
    "hidden_error",
    "ghost_api_type_a",
    "ghost_api_type_b",
    "ghost_api_type_c",
    "state_contradiction",
    "rbac_fail_open",
]


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
            key_str = str(key)
            if key_str in SAFE_EVIDENCE_METADATA_KEYS:
                redacted[key_str] = redact(inner)
            elif SECRETISH_KEYS.search(key_str):
                redacted[key_str] = "[REDACTED]"
            else:
                redacted[key_str] = redact(inner)
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
    return f'[data-flyto-verification-control="{index + 1}"]'


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
    rbac_matrices: List[Mapping[str, Any]] = []

    for page_index, raw_page in enumerate(pages):
        page = redact(dict(raw_page))
        url = strip_query(str(page.get("url") or target))
        page_id = f"page_{page_index + 1}"
        text = str(page.get("text") or page.get("body_text") or "")
        console_errors = page.get("console_errors") or []
        controls = list(page.get("controls") or [])
        requests = list(page.get("requests") or page.get("network") or [])
        states = infer_states(page)
        rbac_matrix = _normalize_rbac_matrix(page.get("rbac_matrix") or page.get("authz_matrix"))
        if rbac_matrix:
            rbac_matrices.append(rbac_matrix)
            _append_rbac_findings(findings, page_id, rbac_matrix)
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

        _append_product_state_rule_findings(findings, page_id, page, states, requests)
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
    if rbac_matrices:
        graph["rbac_matrix"] = _aggregate_rbac_matrices(rbac_matrices)
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


def _append_product_state_rule_findings(
    findings: List[WarroomFinding],
    page_id: str,
    page: Mapping[str, Any],
    states: Iterable[str],
    requests: Iterable[Mapping[str, Any]],
) -> None:
    state_set = set(states)
    if "resolved_empty" in state_set:
        count_key, count_value = _positive_data_count(page, requests)
        if count_value > 0:
            _append_finding(
                findings,
                "false_empty",
                "P0",
                "UI rendered an empty state while deterministic data evidence reported rows.",
                {"page_id": page_id, "data_key": count_key, "data_count": count_value},
            )

    if "locked_preview" in state_set and _has_positive_access(page):
        _append_finding(
            findings,
            "false_locked",
            "P0",
            "UI rendered a locked preview while entitlement or authorization evidence allowed access.",
            {"page_id": page_id, "states": sorted(state_set)},
        )

    for index, request in enumerate(requests):
        try:
            status = int(request.get("status") or 0)
        except (TypeError, ValueError):
            status = 0
        error_hidden = (
            request.get("error_hidden") is True
            or request.get("ui_error_visible") is False
            or ("hidden" in state_set and "error" not in state_set)
            or (status >= 400 and "error" not in state_set)
        )
        if status >= 400 and error_hidden:
            _append_finding(
                findings,
                "hidden_error",
                "P0",
                "API or workflow error was not rendered as an observable UI error state.",
                {
                    "page_id": page_id,
                    "api_index": index + 1,
                    "status": status,
                    "url": strip_query(str(request.get("url") or "")),
                },
            )


def _positive_data_count(page: Mapping[str, Any], requests: Iterable[Mapping[str, Any]]) -> tuple[str, int]:
    containers: List[tuple[str, Any]] = [
        ("business_state", page.get("business_state")),
        ("api_state", page.get("api_state")),
        ("data_state", page.get("data_state")),
    ]
    for index, request in enumerate(requests):
        containers.extend([
            (f"request_{index + 1}", request),
            (f"request_{index + 1}.response", request.get("response")),
            (f"request_{index + 1}.json", request.get("json")),
        ])

    for prefix, value in containers:
        if not isinstance(value, Mapping):
            continue
        for key in ("data_count", "items_count", "results_count", "row_count", "total", "count", "records"):
            try:
                count = int(value.get(key))
            except (TypeError, ValueError):
                continue
            if count > 0:
                return f"{prefix}.{key}", count
        for key in ("items", "results", "rows", "data"):
            items = value.get(key)
            if isinstance(items, list) and len(items) > 0:
                return f"{prefix}.{key}", len(items)
    return "", 0


def _has_positive_access(page: Mapping[str, Any]) -> bool:
    state = page.get("business_state") or page.get("api_state") or page.get("authz_state") or {}
    if not isinstance(state, Mapping):
        return False
    for key in ("has_access", "authorized", "entitled", "capability_enabled", "can_run", "allowed"):
        if state.get(key) is True:
            return True
    return state.get("locked") is False or state.get("paywalled") is False


def _normalize_rbac_matrix(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {}
    return dict(value)


def _append_rbac_findings(findings: List[WarroomFinding], page_id: str, matrix: Mapping[str, Any]) -> None:
    violations = matrix.get("violations") or []
    if not isinstance(violations, list):
        violations = [str(violations)]
    fail_closed = bool(matrix.get("fail_closed", not violations))
    fail_open = matrix.get("fail_open") is True or not fail_closed or len(violations) > 0
    if not fail_open:
        return
    _append_finding(
        findings,
        "rbac_fail_open",
        "P0",
        "Authorization matrix allowed a role, tenant, or action that should fail closed.",
        {
            "page_id": page_id,
            "roles_tested": matrix.get("roles_tested") or matrix.get("roles") or [],
            "tenant_pairs_tested": matrix.get("tenant_pairs_tested") or matrix.get("tenant_pairs") or 0,
            "violations": violations[:20],
        },
    )


def _aggregate_rbac_matrices(matrices: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    roles: List[str] = []
    tenant_pair_count = 0
    violations: List[Any] = []
    fail_closed = True
    for matrix in matrices:
        matrix_roles = matrix.get("roles_tested") or matrix.get("roles") or []
        if isinstance(matrix_roles, list):
            roles.extend(str(role) for role in matrix_roles if role)
        elif matrix_roles:
            roles.append(str(matrix_roles))

        tenant_pairs = matrix.get("tenant_pairs_tested") or matrix.get("tenant_pairs") or 0
        if isinstance(tenant_pairs, list):
            tenant_pair_count += len(tenant_pairs)
        else:
            with suppress(TypeError, ValueError):
                tenant_pair_count += int(tenant_pairs or 0)

        matrix_violations = matrix.get("violations") or []
        if isinstance(matrix_violations, list):
            violations.extend(matrix_violations)
        elif matrix_violations:
            violations.append(str(matrix_violations))
        fail_closed = fail_closed and bool(matrix.get("fail_closed", not matrix_violations))

    return {
        "roles_tested": sorted(set(roles)),
        "tenant_pairs_tested": tenant_pair_count,
        "fail_closed": fail_closed and not violations,
        "violations": violations[:50],
    }


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


def generate_scenarios(graph: Mapping[str, Any], *, name: str = "Deterministic Verification Regression") -> Dict[str, Any]:
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
                    "(async () => {"
                    "const deadline = Date.now() + 5000;"
                    "while (Date.now() < deadline) {"
                    "const text = (document.body?.innerText || '').trim();"
                    "if (text.length > 0) break;"
                    "await new Promise((resolve) => setTimeout(resolve, 100));"
                    "}"
                    "const text = (document.body?.innerText || '').trim();"
                    "return {"
                    "text_chars: text.length,"
                    "horizontal_overflow: document.documentElement.scrollWidth > innerWidth + 2,"
                    "title: document.title"
                    "};"
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
    safe_artifacts = redact(dict(artifacts or {}))
    gate = evaluate_product_verification_gate(
        graph=graph,
        run_evaluation=run_eval,
        artifacts=safe_artifacts,
        p0=p0,
        p1=p1,
    )
    automation_model = automation_test_model(
        graph=graph,
        scenarios=scenarios or {},
        run_result=unwrapped_run,
        run_evaluation=run_eval,
        artifacts=safe_artifacts,
        gate=gate,
        p0=p0,
        p1=p1,
    )
    return {
        "schema_version": "warroom.evidence_pack.v1",
        "generated_at": now_iso(),
        "verdict": verdict,
        "automation_test_model": automation_model,
        "gate_verdict": gate["gate_verdict"],
        "gate_score": gate["score"],
        "score_breakdown": gate["score_breakdown"],
        "artifact_completeness": gate["artifact_completeness"],
        "gate_blockers": gate["blockers"],
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
        "artifacts": safe_artifacts,
    }


def automation_test_model(
    *,
    graph: Mapping[str, Any],
    scenarios: Mapping[str, Any],
    run_result: Mapping[str, Any],
    run_evaluation: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    gate: Mapping[str, Any],
    p0: int,
    p1: int,
) -> Dict[str, Any]:
    """Summarize the deterministic automation-test model for UI/CI consumers."""
    observed_paths = sorted({str(path) for path in (graph.get("observed_paths") or [])})
    reachable_paths = sorted({str(path) for path in (graph.get("reachable_paths") or observed_paths)})
    expected_paths = sorted({str(path) for path in (graph.get("expected_paths") or reachable_paths)})
    blocked_paths = sorted(set(expected_paths) - set(observed_paths))
    graph_scores = graph.get("scores") if isinstance(graph.get("scores"), Mapping) else {}
    run_summary = run_evaluation.get("summary") if isinstance(run_evaluation.get("summary"), Mapping) else {}
    artifact_status = artifact_completeness(artifacts)
    api_edges = list(graph.get("apis") or [])
    findings = list(graph.get("findings") or [])
    state_findings = [item for item in findings if item.get("code") == "state_contradiction"]
    scenario_steps = list(scenarios.get("steps") or [])
    run_results = list(run_result.get("results") or [])
    ghost_summary = _ghost_api_summary(api_edges, findings)
    rbac_matrix = _rbac_matrix_summary(graph, artifacts)
    rule_summary = _deterministic_rule_summary(findings, rbac_matrix)
    authorization_gate = _authorization_gate_summary(artifacts)
    event_stream = _event_stream_summary(graph, artifacts)
    scheduler_loop = _scheduler_loop_summary(graph, artifacts)
    verification_contract = str(artifacts.get("verification_contract") or CORE_DETERMINISTIC_VERIFICATION_SCHEMA)
    if verification_contract != CORE_DETERMINISTIC_VERIFICATION_SCHEMA:
        verification_contract = CORE_DETERMINISTIC_VERIFICATION_SCHEMA
    product_contract = str(artifacts.get("product_contract") or artifacts.get("automation_test_contract") or "")
    product_surface = str(artifacts.get("product_surface") or "")
    capability = str(artifacts.get("capability") or "deterministic_verification")
    replay_reliability = _score_value(run_summary.get("replay_reliability"))
    readiness_score = _automation_readiness_score(
        reachable=_score_value(graph_scores.get("reachable_coverage")),
        replay=replay_reliability,
        artifact_score=_score_value(artifact_status["score"]),
        p0=p0,
        p1=p1,
        ghost_p0=ghost_summary["type_c_count"],
        rbac_matrix=rbac_matrix,
    )

    return {
        "schema_version": verification_contract,
        "legacy_schema_version": LEGACY_AUTOMATION_TEST_MODEL_SCHEMA,
        "product_contract": product_contract,
        "product_surface": product_surface,
        "capability": capability,
        "engine_mode": dict(DETERMINISTIC_ENGINE_MODE),
        "deterministic_contract": dict(DETERMINISTIC_TESTING_CONTRACT),
        "readiness_score": readiness_score,
        "coverage": {
            "observed_paths": observed_paths,
            "reachable_paths": reachable_paths,
            "expected_paths": expected_paths,
            "blocked_paths": blocked_paths,
            "observed_coverage": graph_scores.get("observed_coverage", 0),
            "reachable_coverage": graph_scores.get("reachable_coverage", 0),
            "expected_coverage": round(len(observed_paths) / max(len(expected_paths), 1), 3),
        },
        "intent_graph": {
            "count": len(graph.get("intents") or []),
            "intents": list(graph.get("intents") or [])[:20],
        },
        "scenario_synthesis": {
            "schema_version": scenarios.get("schema_version", ""),
            "name": scenarios.get("name", ""),
            "step_count": len(scenario_steps),
            "replayable_steps": sum(1 for step in scenario_steps if step.get("module")),
            "generated_from": scenarios.get("generated_from", ""),
        },
        "replay": {
            "ok": bool(run_result.get("replay_ok", run_result.get("ok", False))),
            "total": run_summary.get("total", len(run_results)),
            "passed": run_summary.get("passed", 0),
            "failed": run_summary.get("failed", 0),
            "reliability": replay_reliability,
            "steps": run_results[:30],
        },
        "ghost_api": ghost_summary,
        "deterministic_rules": rule_summary,
        "business_invariants": {
            "state_contradictions": len(state_findings),
            "p0": p0,
            "p1": p1,
            "findings": state_findings[:20],
        },
        "rbac_matrix": rbac_matrix,
        "authorization_gate": authorization_gate,
        "event_stream": event_stream,
        "scheduler_loop": scheduler_loop,
        "evidence_chain": {
            "artifact_completeness": artifact_status,
            "has_screenshot": "screenshot" in artifact_status["present"],
            "has_dom_snapshot": "dom_snapshot" in artifact_status["present"],
            "has_network_log": "network_log" in artifact_status["present"],
            "evidence_signature_expected": bool(artifacts.get("target_url")),
        },
        "gate": {
            "verdict": gate.get("gate_verdict"),
            "score": gate.get("score"),
            "blockers": list(gate.get("blockers") or []),
        },
    }


def _ghost_api_summary(api_edges: Iterable[Mapping[str, Any]], findings: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    by_type: Dict[str, List[Dict[str, Any]]] = {
        "type_a_ui_api_no_effect": [],
        "type_b_api_without_ui_path": [],
        "type_c_error_swallowed": [],
    }
    for api in api_edges:
        ghost_type = str(api.get("ghost_api_type") or "")
        if ghost_type in by_type:
            by_type[ghost_type].append({
                "id": api.get("id"),
                "method": api.get("method"),
                "url": api.get("url"),
                "status": api.get("status"),
                "trigger": api.get("trigger"),
            })
    finding_codes = {str(item.get("code") or "") for item in findings}
    return {
        "type_a_count": len(by_type["type_a_ui_api_no_effect"]),
        "type_b_count": len(by_type["type_b_api_without_ui_path"]),
        "type_c_count": len(by_type["type_c_error_swallowed"]),
        "type_a": by_type["type_a_ui_api_no_effect"][:20],
        "type_b": by_type["type_b_api_without_ui_path"][:20],
        "type_c": by_type["type_c_error_swallowed"][:20],
        "has_findings": any(code.startswith("ghost_api") for code in finding_codes),
    }


def _deterministic_rule_summary(findings: Iterable[Mapping[str, Any]], rbac_matrix: Mapping[str, Any]) -> Dict[str, Any]:
    counts = dict.fromkeys(DETERMINISTIC_RULE_CODES, 0)
    samples: Dict[str, List[Dict[str, Any]]] = {code: [] for code in DETERMINISTIC_RULE_CODES}
    for finding in findings:
        code = str(finding.get("code") or finding.get("type") or "")
        if code not in counts:
            continue
        counts[code] += 1
        if len(samples[code]) < 8:
            samples[code].append(dict(finding))
    if rbac_matrix.get("status") != "not_provided" and not rbac_matrix.get("fail_closed"):
        counts["rbac_fail_open"] = max(1, counts["rbac_fail_open"])
    return {
        "required": list(DETERMINISTIC_RULE_CODES),
        "counts": counts,
        "samples": samples,
        "has_blockers": any(counts.get(code, 0) > 0 for code in DETERMINISTIC_RULE_CODES),
    }


def _rbac_matrix_summary(graph: Mapping[str, Any], artifacts: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    artifact_matrix = (artifacts or {}).get("rbac_matrix") if isinstance(artifacts, Mapping) else None
    matrix = graph.get("rbac_matrix") or graph.get("authz_matrix") or artifact_matrix or {}
    if not isinstance(matrix, Mapping) or not matrix:
        return {
            "status": "not_provided",
            "roles_tested": [],
            "tenant_pairs_tested": 0,
            "fail_closed": False,
            "violations": [],
        }
    summary = dict(matrix)
    roles = matrix.get("roles_tested") or matrix.get("roles") or []
    tenant_pairs = matrix.get("tenant_pairs_tested") or matrix.get("tenant_pairs") or 0
    if isinstance(tenant_pairs, list):
        tenant_pair_count = len(tenant_pairs)
    else:
        try:
            tenant_pair_count = int(tenant_pairs or 0)
        except (TypeError, ValueError):
            tenant_pair_count = 0
    violations = matrix.get("violations") or []
    summary["status"] = str(matrix.get("status") or "provided")
    summary["roles_tested"] = list(roles) if isinstance(roles, list) else [str(roles)]
    if "roles_required" in matrix:
        summary["roles_required"] = _string_list(matrix.get("roles_required"))
    role_expectations = matrix.get("role_expectations") or matrix.get("expectations")
    if isinstance(role_expectations, Mapping):
        summary["role_expectations"] = {str(role): str(expectation) for role, expectation in role_expectations.items()}
    summary["tenant_pairs_tested"] = tenant_pair_count
    summary["fail_closed"] = bool(matrix.get("fail_closed", not violations))
    if "fail_open_disallowed" in matrix:
        summary["fail_open_disallowed"] = bool(matrix.get("fail_open_disallowed"))
    if "frontend_authority" in matrix:
        summary["frontend_authority"] = bool(matrix.get("frontend_authority"))
    summary["violations"] = list(violations)[:20] if isinstance(violations, list) else [str(violations)]
    return summary


def _authorization_gate_summary(artifacts: Mapping[str, Any]) -> Dict[str, Any]:
    gate = artifacts.get("authorization_gate") or {}
    if not isinstance(gate, Mapping) or not gate:
        return {
            "status": "not_provided",
            "authority": "",
            "org_gate": "",
            "commercial_gate": "",
            "scope_gate": "",
            "capability_gate": "",
            "frontend_authority": False,
            "fail_closed": False,
        }
    return {
        "status": str(gate.get("status") or "provided"),
        "authority": str(gate.get("authority") or ""),
        "org_gate": str(gate.get("org_gate") or ""),
        "commercial_gate": str(gate.get("commercial_gate") or ""),
        "scope_gate": str(gate.get("scope_gate") or ""),
        "capability_gate": str(gate.get("capability_gate") or ""),
        "frontend_authority": bool(gate.get("frontend_authority")),
        "fail_closed": bool(gate.get("fail_closed")),
    }


def _string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _event_stream_summary(graph: Mapping[str, Any], artifacts: Mapping[str, Any]) -> Dict[str, Any]:
    stream = artifacts.get("event_stream") or graph.get("event_stream") or {}
    if not isinstance(stream, Mapping) or not stream:
        return {
            "status": "not_provided",
            "transport": "",
            "endpoint": "",
            "expected_events": [],
            "observed_events": [],
            "observed_count": 0,
            "fail_closed": False,
            "source": "",
            "expected_payload_fields": [],
        }

    observed = stream.get("observed_events") or stream.get("published_events") or []
    observed_events = list(observed) if isinstance(observed, list) else _string_list(observed)
    expected_events = _string_list(stream.get("expected_events") or stream.get("events"))
    expected_payload_fields = _string_list(stream.get("expected_payload_fields") or stream.get("payload_fields"))
    status = str(stream.get("status") or ("observed" if observed_events else "contract"))
    return {
        "status": status,
        "transport": str(stream.get("transport") or stream.get("protocol") or "text/event-stream"),
        "endpoint": str(stream.get("endpoint") or stream.get("sse_endpoint") or ""),
        "expected_events": expected_events,
        "expected_payload_fields": expected_payload_fields,
        "observed_events": observed_events[:20],
        "observed_count": len(observed_events),
        "fail_closed": bool(stream.get("fail_closed", bool(expected_events))),
        "source": str(stream.get("source") or stream.get("producer") or ""),
    }


def _scheduler_loop_summary(graph: Mapping[str, Any], artifacts: Mapping[str, Any]) -> Dict[str, Any]:
    loop = artifacts.get("scheduler_loop") or graph.get("scheduler_loop") or {}
    if not isinstance(loop, Mapping) or not loop:
        return {
            "status": "not_provided",
            "scanner_id": "",
            "authority": "",
            "enabled": None,
            "dispatch_source": "",
            "manual_run_endpoint": "",
            "scheduler_control_endpoint": "",
            "durable_job": False,
            "last_run_status": "",
            "run_count": 0,
            "fail_count": 0,
        }

    return {
        "status": str(loop.get("status") or "contract"),
        "scanner_id": str(loop.get("scanner_id") or loop.get("job_id") or ""),
        "authority": str(loop.get("authority") or "flyto-engine"),
        "enabled": loop.get("enabled") if isinstance(loop.get("enabled"), bool) else None,
        "dispatch_source": str(loop.get("dispatch_source") or loop.get("source") or ""),
        "manual_run_endpoint": str(loop.get("manual_run_endpoint") or ""),
        "scheduler_control_endpoint": str(loop.get("scheduler_control_endpoint") or ""),
        "durable_job": bool(loop.get("durable_job") or loop.get("durable")),
        "last_run_status": str(loop.get("last_run_status") or ""),
        "run_count": int(loop.get("run_count") or 0),
        "fail_count": int(loop.get("fail_count") or 0),
    }


def _automation_readiness_score(
    *,
    reachable: float,
    replay: float,
    artifact_score: float,
    p0: int,
    p1: int,
    ghost_p0: int,
    rbac_matrix: Mapping[str, Any],
) -> float:
    base = (reachable * 25) + (replay * 25) + (artifact_score * 20)
    rbac_status = str(rbac_matrix.get("status") or "not_provided")
    rbac_points = 15 if rbac_status != "not_provided" and rbac_matrix.get("fail_closed") else 5
    invariant_points = max(0, 15 - (p0 * 6) - (p1 * 2) - (ghost_p0 * 4))
    return round(max(0.0, min(100.0, base + rbac_points + invariant_points)), 1)


def evaluate_product_verification_gate(
    *,
    graph: Mapping[str, Any],
    run_evaluation: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    p0: int,
    p1: int,
) -> Dict[str, Any]:
    """Score the 90-point Flyto2 Product Verification evidence gate.

    The score is a release summary, not the authority. `gate_verdict` remains
    fail-closed on P0/P1 findings, weak replay, poor reachable coverage, dry-run
    evidence, or missing core artifacts.
    """
    scores = graph.get("scores") if isinstance(graph.get("scores"), Mapping) else {}
    run_summary = run_evaluation.get("summary") if isinstance(run_evaluation.get("summary"), Mapping) else {}
    reachable = _score_value(scores.get("reachable_coverage"))
    replay = _score_value(run_summary.get("replay_reliability"))
    artifact_status = artifact_completeness(artifacts)
    rbac_matrix = _rbac_matrix_summary(graph, artifacts)

    intents = graph.get("intents") if isinstance(graph.get("intents"), list) else []
    state_graph = graph.get("state_graph") if isinstance(graph.get("state_graph"), Mapping) else {}
    state_nodes = state_graph.get("states") if isinstance(state_graph.get("states"), list) else []
    api_edges = graph.get("apis") if isinstance(graph.get("apis"), list) else []
    has_network_artifact = "network_log" in artifact_status["present"]
    graph_checks = {
        "intent_graph": bool(intents),
        "state_graph": bool(state_nodes or state_graph.get("allowed_states")),
        "api_graph_or_network": bool(api_edges or has_network_artifact),
    }
    graph_points = round(20 * sum(1 for ok in graph_checks.values() if ok) / len(graph_checks), 1)

    graph_contract = str(artifacts.get("graph_contract") or "")
    verification_contract = str(artifacts.get("verification_contract") or "")
    product_contract = str(artifacts.get("product_contract") or artifacts.get("automation_test_contract") or "")
    target_url = str(artifacts.get("target_url") or "")
    dry_run = bool(artifacts.get("dry_run"))
    scope_checks = {
        "graph_contract": graph_contract == "warroom.product_verification.v1",
        "verification_contract": verification_contract in {"", CORE_DETERMINISTIC_VERIFICATION_SCHEMA},
        "product_contract": not product_contract or _valid_contract_name(product_contract),
        "target_url": bool(target_url),
    }
    scope_points = round(15 * sum(1 for ok in scope_checks.values() if ok) / len(scope_checks), 1)

    live_checks = {
        "artifact_completeness": bool(artifact_status["complete"]),
        "non_dry_run": not dry_run,
    }
    live_points = round(15 * sum(1 for ok in live_checks.values() if ok) / len(live_checks), 1)

    breakdown = {
        "route_reachable_coverage": {
            "points": round(20 * reachable, 1),
            "max": 20,
            "value": reachable,
            "threshold": 0.85,
        },
        "intent_state_api_graph": {
            "points": graph_points,
            "max": 20,
            "checks": graph_checks,
        },
        "replay_reliability": {
            "points": round(20 * replay, 1),
            "max": 20,
            "value": replay,
            "threshold": 0.95,
        },
        "scope_authz_safety": {
            "points": scope_points,
            "max": 15,
            "checks": scope_checks,
        },
        "live_operation_loop": {
            "points": live_points,
            "max": 15,
            "checks": live_checks,
        },
        "public_geo_ai_crawler": {
            "points": 10,
            "max": 10,
            "status": "external_release_gate",
        },
    }
    total = round(sum(float(item["points"]) for item in breakdown.values()), 1)

    blockers: List[str] = []
    if p0 > 0:
        blockers.append(f"p0_findings:{p0}")
    if p1 > 0:
        blockers.append(f"p1_findings:{p1}")
    if reachable < 0.85:
        blockers.append(f"reachable_coverage_below_0.85:{reachable}")
    if replay < 0.95:
        blockers.append(f"replay_reliability_below_0.95:{replay}")
    if not artifact_status["complete"]:
        blockers.append("missing_artifacts:" + ",".join(artifact_status["missing"]))
    if dry_run:
        blockers.append("dry_run_not_live_evidence")
    if not scope_checks["graph_contract"]:
        blockers.append("invalid_or_missing_graph_contract")
    if not scope_checks["verification_contract"]:
        blockers.append("invalid_verification_contract")
    if not scope_checks["product_contract"]:
        blockers.append("invalid_product_contract")
    if not scope_checks["target_url"]:
        blockers.append("missing_target_url")
    if rbac_matrix.get("status") != "not_provided" and not rbac_matrix.get("fail_closed"):
        blockers.append("rbac_fail_open")

    gate_verdict = "pass" if total >= 90 and not blockers else "blocked"
    return {
        "gate_verdict": gate_verdict,
        "score": total,
        "score_breakdown": breakdown,
        "artifact_completeness": artifact_status,
        "blockers": blockers,
    }


def artifact_completeness(artifacts: Mapping[str, Any]) -> Dict[str, Any]:
    required = ["screenshot", "dom_snapshot", "network_log"]
    present = [key for key in required if _artifact_present(artifacts.get(key))]
    missing = [key for key in required if key not in present]
    return {
        "required": required,
        "present": present,
        "missing": missing,
        "complete": not missing,
        "score": round(len(present) / len(required), 3),
    }


def _artifact_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, Mapping):
        if value.get("status") == "error":
            return False
        return bool(value)
    if isinstance(value, (list, str)):
        return bool(value)
    return True


def _score_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def _valid_contract_name(value: str) -> bool:
    return bool(re.match(r"^[a-z0-9][a-z0-9_.-]*\.v[0-9]+$", str(value or "")))


def evidence_to_markdown(pack: Mapping[str, Any]) -> str:
    scores = pack.get("scores") or {}
    lines = [
        "# Deterministic Verification Evidence Pack",
        "",
        f"Verdict: {pack.get('verdict', 'unknown')}",
        f"Gate verdict: {pack.get('gate_verdict', 'unknown')}",
        f"Gate score: {pack.get('gate_score', 'n/a')}",
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
    lines.extend(["", "## 90-Point Gate"])
    for key, value in (pack.get("score_breakdown") or {}).items():
        if isinstance(value, Mapping):
            lines.append(f"- {key}: {value.get('points', 'n/a')}/{value.get('max', 'n/a')}")
    completeness = pack.get("artifact_completeness") or {}
    if isinstance(completeness, Mapping):
        lines.append(f"- artifact_completeness: {completeness.get('score', 'n/a')} missing={completeness.get('missing', [])}")
    blockers = pack.get("gate_blockers") or []
    if blockers:
        lines.append(f"- blockers: {', '.join(str(item) for item in blockers)}")
    automation = pack.get("automation_test_model") or {}
    if isinstance(automation, Mapping):
        lines.extend(["", "## Automation Test Model"])
        lines.append(f"- schema_version: {automation.get('schema_version', 'n/a')}")
        mode = automation.get("engine_mode") if isinstance(automation.get("engine_mode"), Mapping) else {}
        lines.append(
            "- deterministic_mode: "
            f"{mode.get('execution_mode', 'n/a')} "
            f"llm_required={mode.get('llm_required', False)} "
            f"llm_role={mode.get('llm_role', 'n/a')}"
        )
        lines.append(f"- readiness_score: {automation.get('readiness_score', 'n/a')}")
        replay = automation.get("replay") if isinstance(automation.get("replay"), Mapping) else {}
        ghost = automation.get("ghost_api") if isinstance(automation.get("ghost_api"), Mapping) else {}
        rules = automation.get("deterministic_rules") if isinstance(automation.get("deterministic_rules"), Mapping) else {}
        rbac = automation.get("rbac_matrix") if isinstance(automation.get("rbac_matrix"), Mapping) else {}
        events = automation.get("event_stream") if isinstance(automation.get("event_stream"), Mapping) else {}
        scheduler = automation.get("scheduler_loop") if isinstance(automation.get("scheduler_loop"), Mapping) else {}
        lines.append(f"- replay: {replay.get('passed', 'n/a')}/{replay.get('total', 'n/a')} reliability={replay.get('reliability', 'n/a')}")
        lines.append(
            "- ghost_api: "
            f"type_a={ghost.get('type_a_count', 0)} "
            f"type_b={ghost.get('type_b_count', 0)} "
            f"type_c={ghost.get('type_c_count', 0)}"
        )
        if isinstance(rules.get("counts"), Mapping):
            rule_counts = rules["counts"]
            lines.append(
                "- deterministic_rules: "
                f"false_empty={rule_counts.get('false_empty', 0)} "
                f"false_locked={rule_counts.get('false_locked', 0)} "
                f"hidden_error={rule_counts.get('hidden_error', 0)} "
                f"rbac_fail_open={rule_counts.get('rbac_fail_open', 0)}"
            )
        lines.append(f"- rbac_matrix: {rbac.get('status', 'not_provided')} fail_closed={rbac.get('fail_closed', False)}")
        lines.append(f"- event_stream: {events.get('status', 'not_provided')} expected={events.get('expected_events', [])}")
        lines.append(f"- scheduler_loop: {scheduler.get('status', 'not_provided')} scanner={scheduler.get('scanner_id', '')}")
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
