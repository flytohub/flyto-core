# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Flyto2 deterministic verification runner service.

This service is intentionally small: engine remains the authority for org
membership, entitlement, verified target scope, and campaign state. The runner
only validates the supplied execution scope again, executes a server-owned
flyto-core workflow, and returns/callbacks deterministic evidence.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import aiohttp
import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

GRAPH_CONTRACT = "warroom.product_verification.v1"
INTERNAL_KEY_HEADER = "X-Internal-Key"
DEFAULT_CALLBACK_PATH = "/api/v1/code/runner/executions/callback"


class VerificationRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workflow_yaml: str = Field(..., alias="workflowYaml", min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    allowed_targets: list[str] = Field(default_factory=list)
    org_id: str = ""
    campaign_id: str = ""
    dry_run: bool = False
    callback_url: str | None = None


@dataclass
class VerificationExecution:
    execution_id: str
    dry_run: bool
    status: str = "queued"
    verdict: str = "unknown"
    findings_count: int = 0
    critical_count: int = 0
    error_message: str = ""
    evidence_pack: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0

    def callback_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "runner_execution_id": self.execution_id,
            "status": self.status,
            "verdict": self.verdict,
            "findings_count": self.findings_count,
            "critical_count": self.critical_count,
            "dry_run": self.dry_run,
        }
        if self.error_message:
            payload["error_message"] = self.error_message
        if self.evidence_pack is not None:
            payload["evidence_pack"] = self.evidence_pack
        if self.artifacts:
            payload["artifacts"] = self.artifacts
        payload["evidence_sig"] = evidence_signature(payload)
        return payload


def evidence_signature(payload: Mapping[str, Any]) -> str:
    body = json.dumps(
        {
            "evidence_pack": payload.get("evidence_pack"),
            "artifacts": payload.get("artifacts", []),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def extract_host(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return (parsed.hostname or "").lower().rstrip(".")


def target_allowed(target_url: str, allowed_targets: list[str]) -> bool:
    target_host = extract_host(target_url)
    if not target_host:
        return False
    for allowed in allowed_targets:
        allowed_host = extract_host(allowed)
        if allowed_host and allowed_host == target_host:
            return True
    return False


def parse_workflow_yaml(workflow_yaml: str) -> dict[str, Any]:
    try:
        workflow = yaml.safe_load(workflow_yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid workflowYaml: {exc}") from exc
    if not isinstance(workflow, dict):
        raise ValueError("workflowYaml must parse to an object")
    if not isinstance(workflow.get("steps"), list):
        raise ValueError("workflowYaml.steps must be an array")
    return workflow


def render_params(value: Any, params: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        rendered = value
        for key, replacement in params.items():
            if isinstance(replacement, (str, int, float, bool)):
                rendered = rendered.replace(f"{{{{{key}}}}}", str(replacement))
        return rendered
    if isinstance(value, list):
        return [render_params(item, params) for item in value]
    if isinstance(value, dict):
        return {key: render_params(inner, params) for key, inner in value.items()}
    return value


def _normalise_pack(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, Mapping):
        return None
    if isinstance(candidate.get("evidence_pack"), Mapping):
        return dict(candidate["evidence_pack"])
    if isinstance(candidate.get("pack"), Mapping):
        return dict(candidate["pack"])
    if candidate.get("schema_version") == "warroom.evidence_pack.v1":
        return dict(candidate)
    if isinstance(candidate.get("data"), Mapping):
        return _normalise_pack(candidate["data"])
    return None


def extract_evidence_pack(result: Mapping[str, Any]) -> dict[str, Any] | None:
    steps = result.get("steps")
    if isinstance(steps, Mapping):
        for key in ("evidence_pack", "report_json", "report", "warroom_report"):
            pack = _normalise_pack(steps.get(key))
            if pack is not None:
                return pack
        for output in reversed(list(steps.values())):
            pack = _normalise_pack(output)
            if pack is not None:
                return pack
    return _normalise_pack(result)


def _finding_list(pack: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not pack:
        return []
    findings: list[Mapping[str, Any]] = []
    raw_findings = pack.get("findings")
    if isinstance(raw_findings, list):
        findings.extend(item for item in raw_findings if isinstance(item, Mapping))
    site_graph = pack.get("site_graph")
    if isinstance(site_graph, Mapping):
        raw_site_findings = site_graph.get("findings")
        if isinstance(raw_site_findings, list):
            findings.extend(item for item in raw_site_findings if isinstance(item, Mapping))
    run_eval = pack.get("run_evaluation")
    if isinstance(run_eval, Mapping):
        raw_run_findings = run_eval.get("findings")
        if isinstance(raw_run_findings, list):
            findings.extend(item for item in raw_run_findings if isinstance(item, Mapping))
    return findings


def count_findings(pack: Mapping[str, Any] | None) -> tuple[int, int]:
    findings = _finding_list(pack)
    critical = 0
    for finding in findings:
        severity = str(finding.get("severity") or "").lower()
        if severity in {"p0", "critical", "blocker"}:
            critical += 1
    return len(findings), critical


def _artifact_from_path(kind: str, name: str, path_value: Any) -> dict[str, Any] | None:
    if not isinstance(path_value, (str, Path)):
        return None
    path = Path(path_value)
    if not path.exists() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        return None
    content = path.read_bytes()
    mime = "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
    return {
        "kind": kind,
        "name": name or path.name,
        "mime_type": mime,
        "content_base64": base64.b64encode(content).decode("ascii"),
        "size_bytes": len(content),
    }


def build_artifacts(pack: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    raw_artifacts = pack.get("artifacts") if isinstance(pack, Mapping) else None
    if not isinstance(raw_artifacts, Mapping):
        return artifacts

    screenshot = _artifact_from_path("screenshot", "warroom-product-verification.png", raw_artifacts.get("screenshot"))
    if screenshot:
        artifacts.append(screenshot)

    for key, kind, name in (
        ("dom_snapshot", "dom_snapshot", "dom-snapshot.json"),
        ("network_log", "network_log", "network-log.json"),
    ):
        value = raw_artifacts.get(key)
        if value is None:
            continue
        artifacts.append({
            "kind": kind,
            "name": name,
            "mime_type": "application/json",
            "json": value,
            "size_bytes": len(json.dumps(value, default=str)),
        })
    return artifacts


async def execute_verification(body: VerificationRunRequest) -> VerificationExecution:
    execution = VerificationExecution(
        execution_id=f"verification-{uuid.uuid4().hex[:12]}",
        dry_run=body.dry_run,
        status="running",
    )
    started = time.monotonic()
    target_url = str(body.params.get("target_url") or "").strip()
    if target_url and body.allowed_targets and not target_allowed(target_url, body.allowed_targets):
        execution.status = "failed"
        execution.verdict = "blocked"
        execution.error_message = "target_url is outside the engine-computed verification scope"
        return execution

    try:
        workflow = render_params(parse_workflow_yaml(body.workflow_yaml), body.params)
        if body.dry_run:
            execution.status = "complete"
            execution.verdict = "planned"
            execution.evidence_pack = {
                "schema_version": "warroom.evidence_pack.v1",
                "verdict": "planned",
                "scores": {"p0": 0, "p1": 0, "replay_reliability": 1.0},
                "artifacts": {
                    "target_url": target_url,
                    "graph_contract": GRAPH_CONTRACT,
                    "verification_service": "flyto-verification",
                    "dry_run": True,
                },
            }
            return execution

        from core.engine import WorkflowEngine
        from core.modules import atomic  # noqa: F401

        engine = WorkflowEngine(workflow=workflow, params=body.params or {}, enable_trace=True)
        result = await engine.execute()
        pack = extract_evidence_pack(result)
        execution.evidence_pack = pack or {
            "schema_version": "warroom.evidence_pack.v1",
            "verdict": "pass" if result.get("status") == "completed" else "fail",
            "scores": {"p0": 0, "p1": 0, "replay_reliability": 1.0},
            "run": result,
            "artifacts": {
                "target_url": target_url,
                "graph_contract": GRAPH_CONTRACT,
                "verification_service": "flyto-verification",
            },
        }
        execution.artifacts = build_artifacts(execution.evidence_pack)
        execution.findings_count, execution.critical_count = count_findings(execution.evidence_pack)
        execution.verdict = str(execution.evidence_pack.get("verdict") or "pass")
        execution.status = "complete"
    except Exception as exc:  # pragma: no cover - defensive service boundary
        logger.exception("verification execution failed")
        execution.status = "failed"
        execution.verdict = "failed"
        execution.error_message = str(exc)
    finally:
        execution.duration_ms = int((time.monotonic() - started) * 1000)
    return execution


def resolve_callback_url(body: VerificationRunRequest) -> str:
    if body.callback_url:
        return body.callback_url
    engine_url = os.environ.get("FLYTO_ENGINE_CALLBACK_URL") or os.environ.get("FLYTO_ENGINE_URL")
    if not engine_url:
        return ""
    return engine_url.rstrip("/") + DEFAULT_CALLBACK_PATH


async def post_callback(callback_url: str, payload: Mapping[str, Any]) -> None:
    if not callback_url:
        return
    headers = {"Content-Type": "application/json"}
    internal_key = os.environ.get("FLYTO_RUNNER_SECRET") or os.environ.get("FLYTO_VERIFICATION_SECRET")
    if internal_key:
        headers[INTERNAL_KEY_HEADER] = internal_key
    async with aiohttp.ClientSession() as session, session.post(
        callback_url,
        json=payload,
        headers=headers,
        timeout=30,
    ) as response:
        if response.status >= 300:
            text = await response.text()
            raise RuntimeError(f"engine callback failed: {response.status} {text[:500]}")


async def run_and_callback(body: VerificationRunRequest) -> VerificationExecution:
    execution = await execute_verification(body)
    await post_callback(resolve_callback_url(body), execution.callback_payload())
    return execution


def create_app():
    try:
        from fastapi import BackgroundTasks, FastAPI
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("flyto-core[api] is required to run flyto-verification") from exc

    app = FastAPI(
        title="flyto-verification",
        description="Deterministic Flyto2 product verification runner backed by flyto-core.",
        version="0.1.0",
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "flyto-verification", "graph_contract": GRAPH_CONTRACT}

    @app.post("/run")
    async def run(body: VerificationRunRequest, background_tasks: BackgroundTasks):
        execution_id = f"verification-{uuid.uuid4().hex[:12]}"
        queued = VerificationRunRequest(**body.model_dump())

        async def _execute_with_fixed_id() -> None:
            execution = await execute_verification(queued)
            execution.execution_id = execution_id
            await post_callback(resolve_callback_url(queued), execution.callback_payload())

        background_tasks.add_task(_execute_with_fixed_id)
        return {
            "ok": True,
            "execution_id": execution_id,
            "dry_run": body.dry_run,
            "service": "flyto-verification",
            "graph_contract": GRAPH_CONTRACT,
        }

    return app


def main(host: str = "127.0.0.1", port: int = 8344) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
