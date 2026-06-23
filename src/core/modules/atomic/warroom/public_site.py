# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Deterministic public-site verification module for SEO/AEO/GEO release gates."""

from __future__ import annotations

from typing import Any, Dict, Iterable
from urllib.parse import urlparse

from ...base import BaseModule
from ...registry import register_module
from .engine import now_iso, strip_query

CONTRACT = "flyto2.public_site_verification.v1"

CRITICAL_PATHS = {
    "/",
    "/robots.txt",
    "/sitemap.xml",
    "/llms.txt",
    "/llms-full.txt",
}

REQUIRED_ROUTES = [
    "/",
    "/robots.txt",
    "/sitemap.xml",
    "/llms.txt",
    "/llms-full.txt",
    "/pricing/",
    "/security/",
    "/enterprise/",
    "/airgap/",
    "/open-source/",
    "/compare/",
    "/api-docs/",
    "/trust/",
    "/docs/",
    "/blog/",
    "/changelog/",
]

REQUIRED_SEO_GEO_SIGNALS = [
    "title",
    "meta_description",
    "canonical",
    "open_graph",
    "structured_data",
    "llms_txt",
    "sitemap",
    "robots",
    "server_rendered_content",
]

AI_CRAWLER_UAS = {
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "Claude-SearchBot",
    "Claude-User",
    "anthropic-ai",
    "Claude-Web",
    "PerplexityBot",
    "Perplexity-User",
    "Google-Extended",
    "Googlebot",
    "Bingbot",
}


def _path_from_observation(observation: dict[str, Any]) -> str:
    value = observation.get("path")
    if isinstance(value, str) and value:
        return value if value.startswith("/") else f"/{value}"
    url = observation.get("url")
    if isinstance(url, str) and url:
        parsed = urlparse(url)
        path = parsed.path or "/"
        return path
    return "/"


def _status_value(observation: dict[str, Any]) -> int | None:
    for key in ("final_status", "status"):
        value = observation.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return None


def _is_unavailable(observation: dict[str, Any]) -> bool:
    if observation.get("timed_out") or observation.get("timeout"):
        return True
    if observation.get("ok") is False:
        return True
    if observation.get("error"):
        return True
    status = _status_value(observation)
    return status is None or status >= 400


def _finding(
    severity: str,
    code: str,
    message: str,
    *,
    path: str = "",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "path": path,
        "evidence": evidence or {},
    }


def _normalise_matrix(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalise_seo_geo(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _missing_routes(route_matrix: Iterable[dict[str, Any]], required_routes: Iterable[str]) -> list[str]:
    observed = {_path_from_observation(item).rstrip("/") or "/" for item in route_matrix}
    missing = []
    for route in required_routes:
        normalized = route.rstrip("/") or "/"
        if normalized not in observed:
            missing.append(route)
    return missing


def build_public_site_verification(
    *,
    base_url: str,
    observations: dict[str, Any],
    required_routes: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic release-gate contract from collected public-site evidence."""

    routes = required_routes or REQUIRED_ROUTES
    dns_matrix = _normalise_matrix(observations.get("dns_matrix") or observations.get("dns"))
    tls_matrix = _normalise_matrix(observations.get("tls_matrix") or observations.get("tls"))
    route_matrix = _normalise_matrix(observations.get("route_matrix") or observations.get("routes"))
    browser_matrix = _normalise_matrix(observations.get("browser_matrix") or observations.get("browser"))
    seo_geo_matrix = _normalise_seo_geo(observations.get("seo_geo_matrix") or observations.get("seo_geo"))

    findings: list[dict[str, Any]] = []

    for item in dns_matrix:
        host = str(item.get("host") or "")
        if item.get("ok") is False:
            findings.append(_finding("P0", "dns_unresolved", f"DNS lookup failed for {host}", evidence=item))

    for item in tls_matrix:
        host = str(item.get("host") or "")
        if item.get("ok") is False:
            findings.append(_finding("P0", "tls_unavailable", f"TLS/SNI probe failed for {host}", evidence=item))

    for item in route_matrix:
        path = _path_from_observation(item)
        status = _status_value(item)
        user_agent = str(item.get("user_agent") or item.get("ua") or "")
        if _is_unavailable(item):
            if user_agent in AI_CRAWLER_UAS:
                severity = "P1"
                code = "ai_crawler_blocked"
            else:
                severity = "P0" if path in CRITICAL_PATHS else "P1"
                code = "critical_route_unavailable" if severity == "P0" else "public_route_unavailable"
            findings.append(_finding(severity, code, f"Public route is unavailable: {path}", path=path, evidence=item))
            continue
        if status in {301, 302, 303, 307, 308} and item.get("final_status") != 200:
            severity = "P0" if path in CRITICAL_PATHS else "P1"
            findings.append(
                _finding(
                    severity,
                    "unresolved_redirect",
                    f"Route redirect did not resolve to HTTP 200: {path}",
                    path=path,
                    evidence=item,
                )
            )

        if user_agent in AI_CRAWLER_UAS and status in {401, 403, 429}:
            findings.append(
                _finding(
                    "P1",
                    "ai_crawler_blocked",
                    f"AI/search crawler received blocking status {status}: {user_agent}",
                    path=path,
                    evidence=item,
                )
            )

    for missing in _missing_routes(route_matrix, routes):
        severity = "P0" if missing in CRITICAL_PATHS else "P1"
        findings.append(
            _finding(
                severity,
                "missing_route_observation",
                f"Required public route was not observed: {missing}",
                path=missing,
            )
        )

    for item in browser_matrix:
        path = _path_from_observation(item)
        status = str(item.get("status") or "")
        if item.get("ok") is False or status in {"timeout", "error", "not_run"} or item.get("error"):
            findings.append(
                _finding(
                    "P0",
                    "browser_render_unverified",
                    f"Browser render proof is missing or failed for {path}",
                    path=path,
                    evidence=item,
                )
            )

    for key in REQUIRED_SEO_GEO_SIGNALS:
        if seo_geo_matrix.get(key) is False:
            findings.append(
                _finding(
                    "P1",
                    "seo_geo_signal_missing",
                    f"SEO/AEO/GEO signal is missing: {key}",
                    evidence={"signal": key},
                )
            )

    p0 = sum(1 for item in findings if item["severity"] == "P0")
    p1 = sum(1 for item in findings if item["severity"] == "P1")
    total_routes = max(len(routes), 1)
    observed_routes = total_routes - len(_missing_routes(route_matrix, routes))
    passing_routes = sum(
        1
        for item in route_matrix
        if not _is_unavailable(item) and (_status_value(item) == 200 or item.get("final_status") == 200)
    )
    route_score = round(min(passing_routes, observed_routes) / total_routes, 3)
    seo_score = round(
        sum(1 for key in REQUIRED_SEO_GEO_SIGNALS if seo_geo_matrix.get(key) is True)
        / len(REQUIRED_SEO_GEO_SIGNALS),
        3,
    )

    return {
        "contract": CONTRACT,
        "generated_at": generated_at or now_iso(),
        "target": strip_query(base_url),
        "ok": p0 == 0,
        "p0_findings": p0,
        "p1_findings": p1,
        "findings": findings,
        "dns_matrix": dns_matrix,
        "tls_matrix": tls_matrix,
        "route_matrix": route_matrix,
        "browser_matrix": browser_matrix,
        "seo_geo_matrix": seo_geo_matrix,
        "scores": {
            "public_route_readiness": route_score,
            "seo_geo_readiness": seo_score,
            "browser_render_readiness": 1.0 if browser_matrix and p0 == 0 else 0.0,
        },
    }


@register_module(
    module_id="warroom.public_site_verify",
    version="1.0.0",
    category="warroom",
    tags=["warroom", "public-site", "seo", "geo", "deterministic", "release-gate"],
    label="Warroom Public Site Verify",
    description="Evaluate DNS, TLS, route, browser, and SEO/GEO evidence for a public site",
    icon="Globe2",
    color="#10B981",
    input_types=["object"],
    output_types=["object"],
    can_receive_from=["browser.*", "api.*", "data.*", "flow.*", "start"],
    can_connect_to=["warroom.*", "verify.*", "file.*", "report.*"],
    params_schema={
        "base_url": {"type": "string", "required": True, "description": "Public site base URL"},
        "observations": {
            "type": "object",
            "required": True,
            "description": "Collected DNS/TLS/route/browser/SEO evidence",
        },
        "required_routes": {
            "type": "array",
            "required": False,
            "description": "Expected public routes; defaults to Flyto2 public SEO/GEO routes",
        },
        "generated_at": {"type": "string", "required": False, "description": "Evidence timestamp override"},
    },
    output_schema={
        "ok": {"type": "boolean"},
        "contract": {"type": "string"},
        "p0_findings": {"type": "number"},
        "p1_findings": {"type": "number"},
        "route_matrix": {"type": "array"},
        "browser_matrix": {"type": "array"},
    },
    timeout_ms=30000,
)
class WarroomPublicSiteVerifyModule(BaseModule):
    """Evaluate public-site evidence without relying on LLM judgment."""

    module_name = "Warroom Public Site Verify"
    module_description = "Evaluate public-site evidence for release readiness"

    def validate_params(self) -> None:
        if not self.params.get("base_url"):
            raise ValueError("base_url is required")
        if not isinstance(self.params.get("observations"), dict):
            raise ValueError("observations object is required")

    async def execute(self) -> Dict[str, Any]:
        return build_public_site_verification(
            base_url=self.params["base_url"],
            observations=self.params["observations"],
            required_routes=self.params.get("required_routes"),
            generated_at=self.params.get("generated_at"),
        )
