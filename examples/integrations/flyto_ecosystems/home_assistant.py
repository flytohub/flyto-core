"""Home Assistant resource adapter: explicit effects, observed states, no blind replay.

Intended for an AI Space execution host on the owner's trusted network. Never
run this in a public Cloud worker against arbitrary customer-supplied URLs.
The existing Flyto2 host owns approvals and physical actuation policy.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import ssl
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

SUPPORTED_DOMAINS = frozenset({"light", "switch", "sensor", "binary_sensor"})
CONTROLLABLE = frozenset({"light", "switch"})
_ENTITY = re.compile(r"^(light|switch|sensor|binary_sensor)\.[a-z0-9_]+$")
_CAPABILITIES = frozenset({"vendor.homeassistant.observe", "vendor.homeassistant.turn_on", "vendor.homeassistant.turn_off"})
MAX_RESPONSE = 256 * 1024


def _url(url: str, *, allow_local_http: bool) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Home Assistant endpoint must not contain credentials, query or fragment")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Home Assistant requires an absolute HTTP(S) endpoint")
    if parsed.path.rstrip("/") not in ("",):
        raise ValueError("Home Assistant endpoint must be an origin, without path")
    if parsed.scheme == "http":
        host = parsed.hostname.lower()
        try:
            private = not ipaddress.ip_address(host).is_global
        except ValueError:
            private = host == "localhost" or host.endswith(".local")
        if not allow_local_http or not private:
            raise ValueError("Unencrypted HTTP requires explicit local-network permission")
    return url.rstrip("/")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class HomeAssistantREST:
    """Authenticated, response-bounded HTTP transport. Token stays in memory."""

    def __init__(self, url: str, token: str, *, allow_local_http: bool = False, timeout: float = 8.0):
        self.url = _url(url, allow_local_http=allow_local_http)
        if not token:
            raise ValueError("Home Assistant long-lived access token is required")
        self._token = token
        self._timeout = min(max(float(timeout), 0.5), 30.0)
        self._opener = build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def request(self, path: str, *, payload: dict[str, Any] | None = None) -> Any:
        if not path.startswith("/api/") or "?" in path or "#" in path or ".." in path:
            raise ValueError("request must use a fixed Home Assistant API path")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = Request(self.url + path, data=data, headers=headers, method="POST" if data else "GET")
        with self._opener.open(req, timeout=self._timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("Home Assistant response is too large")
        return json.loads(raw.decode("utf-8"))

    def state(self, entity_id: str) -> dict[str, Any]:
        result = self.request(f"/api/states/{entity_id}")
        if not isinstance(result, dict) or result.get("entity_id") != entity_id:
            raise ValueError("Home Assistant returned a mismatched entity")
        return result

    def service(self, domain: str, operation: str, entity_id: str) -> None:
        # An HTTP acknowledgement is NOT an execution or completion receipt.
        self.request(f"/api/services/{domain}/{operation}", payload={"entity_id": entity_id})

    def entities(self) -> list[dict[str, Any]]:
        answer = self.request("/api/states")
        if not isinstance(answer, list) or len(answer) > 10000:
            raise ValueError("Home Assistant state catalog is invalid")
        return answer


class IntentLedger:
    """Durable one-way idempotency barrier; unknown results are not replayed."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), isolation_level=None, timeout=8)
        conn.execute("PRAGMA busy_timeout=8000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS calls (call_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL)")
        os.chmod(self.path, 0o600)

    def claim(self, call_id: str, request_hash: str) -> tuple[bool, dict[str, str]]:
        if not isinstance(call_id, str) or not 1 <= len(call_id) <= 128:
            raise ValueError("call_id is required and bounded")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO calls VALUES (?, ?, ?, ?)", (call_id, request_hash, "unknown", "effect may have been sent"))
            row = conn.execute("SELECT request_hash, outcome, detail FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            fresh = conn.execute("SELECT changes()").fetchone()[0] == 1
            conn.commit()
        return bool(fresh), {"request_hash": row[0], "outcome": row[1], "detail": row[2]}

    def finish(self, call_id: str, outcome: str, detail: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE calls SET outcome = ?, detail = ? WHERE call_id = ? AND outcome = 'unknown'",
                (outcome, detail[:256], call_id),
            )


class HomeAssistantAdapter:
    """One HA entity bound to an exact Flyto2 resource and call ledger."""

    def __init__(
        self,
        entity_id: str,
        transport: Any,
        ledger: IntentLedger,
        *,
        sleep: Callable[[float], None] = time.sleep,
        observations: int = 3,
    ):
        if not _ENTITY.fullmatch(entity_id):
            raise ValueError("unsupported Home Assistant entity")
        self.entity_id = entity_id
        self.resource_id = f"homeassistant:{entity_id}"
        self._domain = entity_id.split(".", 1)[0]
        self._transport = transport
        self._ledger = ledger
        self._sleep = sleep
        self._observations = max(1, min(int(observations), 10))

    @property
    def deployment_mode(self) -> str:
        return "physical"

    def describe(self) -> tuple[dict[str, Any], ...]:
        operations = ["observe"] + (["turn_on", "turn_off"] if self._domain in CONTROLLABLE else [])
        return tuple({
            "resource_id": self.resource_id,
            "capability_id": f"vendor.homeassistant.{op}",
            "approval_status": "DISCOVERED",
            "requires_safe_stop": False,
            "actuates": op != "observe",
            "idempotent": op == "observe",
        } for op in operations)

    def observe(self, *, phase: str = "", execution_id: str = "") -> dict[str, Any]:
        state = self._transport.state(self.entity_id)
        value = state.get("state")
        if not isinstance(value, str) or value.lower() in {"", "unknown", "unavailable"}:
            raise ValueError("Home Assistant device state is not observable")
        return {"state": {"entity_id": self.entity_id, "value": value,
                          "phase": phase, "call_id": execution_id}}

    def invoke(self, request: Any) -> dict[str, Any]:
        call_id = str(getattr(request, "call_id", "") or "")
        capability_id = str(getattr(request, "capability_id", "") or "")
        arguments = getattr(request, "arguments", {})
        if capability_id not in _CAPABILITIES or not isinstance(arguments, dict) or arguments:
            return {"outcome": "refused", "detail": "undeclared capability or arguments", "evidence": {}}
        operation = capability_id.rsplit(".", 1)[1]
        if operation != "observe" and self._domain not in CONTROLLABLE:
            return {"outcome": "refused", "detail": "resource is read-only", "evidence": {}}
        if operation == "observe":
            try:
                return {"outcome": "completed", "detail": "observed state", "evidence": self.observe()}
            except Exception:
                return {"outcome": "failed", "detail": "state cannot be read", "evidence": {}}

        fingerprint = hashlib.sha256(json.dumps(
            [self.resource_id, capability_id, arguments], separators=(",", ":")
        ).encode()).hexdigest()
        try:
            # A state read must succeed before claiming intent to send.
            before = self.observe(phase="before", execution_id=call_id)
            fresh, prior = self._ledger.claim(call_id, fingerprint)
        except Exception:
            return {"outcome": "refused", "detail": "cannot durably admit this call", "evidence": {}}
        if prior["request_hash"] != fingerprint:
            return {"outcome": "refused", "detail": "call_id was bound to a different command", "evidence": {}}
        if not fresh:
            # A completed call has a durable result, but a crash after claim
            # and before/after HTTP leaves an unknown effect. Never replay it.
            if prior["outcome"] == "completed":
                return {"outcome": "completed", "detail": "previously verified result (not re-executed)",
                        "evidence": {"replay": False, "prior_verified": True}}
            return {"outcome": "refused", "detail": "call already admitted; reconcile before any retry",
                    "evidence": {"replay": False, "prior_outcome": prior["outcome"]}}

        wanted = "on" if operation == "turn_on" else "off"
        try:
            if before["state"]["value"] != wanted:
                self._transport.service(self._domain, operation, self.entity_id)
            for i in range(self._observations):
                after = self.observe(phase="after", execution_id=call_id)
                if after["state"]["value"] == wanted:
                    self._ledger.finish(call_id, "completed", "target state observed")
                    return {"outcome": "completed", "detail": "target state observed",
                            "evidence": {"before": before, "after": after}}
                if i + 1 < self._observations:
                    self._sleep(0.2)
        except Exception:
            # Service might have executed despite a lost HTTP ACK.
            self._ledger.finish(call_id, "uncertain", "submission or observation outcome unknown")
            return {"outcome": "failed", "detail": "outcome unknown; manual reconciliation required",
                    "evidence": {"before": before}}
        self._ledger.finish(call_id, "uncertain", "target state not observed")
        return {"outcome": "failed", "detail": "target state not observed; manual reconciliation required",
                "evidence": {"before": before, "after": after}}

    def cancel(self, call_id: str) -> dict[str, str]:
        return {"outcome": "refused", "detail": "HA service calls have no generic cancellation API"}

    def safe_stop(self) -> dict[str, str]:
        return {"outcome": "refused", "detail": "No generic safety stop for Home Assistant entities"}


def discover_entities(transport: HomeAssistantREST) -> tuple[dict[str, Any], ...]:
    """Passive discovery; entities are explicitly unapproved until bound."""
    result = []
    for item in transport.entities():
        if not isinstance(item, dict):
            continue
        entity_id = item.get("entity_id")
        if isinstance(entity_id, str) and _ENTITY.fullmatch(entity_id):
            domain = entity_id.partition(".")[0]
            result.append({"resource_id": f"homeassistant:{entity_id}", "entity_id": entity_id,
                           "domain": domain, "approval_status": "DISCOVERED"})
    return tuple(result)


def build_adapter(resource_id: str) -> HomeAssistantAdapter:
    """Core host entry point, configured only by the local execution host."""
    prefix = "homeassistant:"
    if not resource_id.startswith(prefix):
        raise ValueError("resource is not a Home Assistant entity")
    origin = os.environ.get("FLYTO_HA_URL", "")
    token = os.environ.get("FLYTO_HA_TOKEN", "")
    allow_local_http = os.environ.get("FLYTO_HA_ALLOW_LOCAL_HTTP") == "1"
    ledger_path = os.environ.get("FLYTO_HA_LEDGER") or str(
        Path.home() / ".local/state/flyto2/ha-calls.sqlite3"
    )
    return HomeAssistantAdapter(
        resource_id[len(prefix):],
        HomeAssistantREST(origin, token, allow_local_http=allow_local_http),
        IntentLedger(ledger_path),
    )
