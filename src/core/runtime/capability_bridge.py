# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Optional client for a local Flyto2 Runtime capability bridge.

The client speaks only the provider-neutral ``flyto2.execution.v1`` HTTP/JSON
contract. Importing or using flyto-core never requires Flyto2 Runtime; callers
must explicitly construct this client and provide the same-user bridge token.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import aiohttp
from pydantic import BaseModel, ConfigDict, Field

EXECUTION_SCHEMA = "flyto2.execution.v1"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:7676/flyto2/capabilities/v1"
BRIDGE_TOKEN_HEADER = "x-flyto2-capability-token"
MAX_ACCEPTED_WAIT_CYCLES = 10_000


class FlytoRuntimeBridgeError(RuntimeError):
    """Raised for transport, authentication, or malformed bridge behavior."""


class RuntimeCapabilityDescriptor(BaseModel):
    """One capability advertised by a live Flyto2 Runtime manifest."""

    model_config = ConfigDict(extra="allow")

    id: str
    revision: int = Field(ge=1)
    risk_level: str
    approval: str
    evidence: List[str] = Field(default_factory=list)


class FlytoRuntimeManifest(BaseModel):
    """Provider-neutral live Runtime capability manifest."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_: Literal[EXECUTION_SCHEMA] = Field(alias="schema", serialization_alias="schema")
    product: str
    runtime: str
    runtime_version: str
    runtime_id: str
    display_name: str
    platform: str
    roles: List[str] = Field(default_factory=list)
    capabilities: List[RuntimeCapabilityDescriptor] = Field(default_factory=list)

    def supports(self, capability: str, revision: int = 1) -> bool:
        """Return whether the live Runtime advertises a capability revision."""

        return any(
            entry.id == capability and entry.revision == revision
            for entry in self.capabilities
        )


class CapabilityFollowUp(BaseModel):
    """Contract-defined next observation for an accepted operation."""

    model_config = ConfigDict(extra="forbid")

    capability: str
    input: Dict[str, Any] = Field(default_factory=dict)


class CapabilityOperation(BaseModel):
    """Opaque durable operation handle returned by Runtime."""

    model_config = ConfigDict(extra="allow")

    kind: str
    ref: str
    state: Literal["pending", "running"]
    wait: Optional[CapabilityFollowUp] = None
    inspect: Optional[CapabilityFollowUp] = None


class CapabilityFailure(BaseModel):
    """Stable provider-neutral capability failure metadata."""

    model_config = ConfigDict(extra="allow")

    code: str
    retryable: bool = False
    detail: Optional[str] = None


class CapabilityInvocation(BaseModel):
    """A validated ``flyto2.execution.v1`` capability invocation envelope."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal[EXECUTION_SCHEMA] = Field(
        default=EXECUTION_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    invocation_id: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=1, max_length=128)
    revision: int = Field(default=1, ge=1)
    operation_id: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    trace_id: Optional[str] = Field(default=None, max_length=128)
    requested_at: str
    input: Dict[str, Any] = Field(default_factory=dict)


class CapabilityResult(BaseModel):
    """A validated terminal or accepted Runtime capability result."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal[EXECUTION_SCHEMA] = Field(alias="schema", serialization_alias="schema")
    invocation_id: str
    capability: str
    revision: int
    status: Literal["accepted", "success", "failed"]
    started_at: str
    completed_at: Optional[str] = None
    output: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    operation: Optional[CapabilityOperation] = None
    failure: Optional[CapabilityFailure] = None


class FlytoRuntimeCapabilityClient:
    """Explicit same-machine client for Flyto2 Runtime capabilities.

    The client accepts only a loopback HTTP endpoint and never discovers or
    reads Runtime credentials implicitly. Callers may pass a token directly or
    use :meth:`from_token_file` with a path supplied at runtime.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BRIDGE_URL,
        timeout_seconds: float = 30.0,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        normalized_token = token.strip()
        if len(normalized_token) < 32:
            raise ValueError("Flyto2 Runtime bridge token is invalid or too short")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._token = normalized_token
        self._base_url = _normalize_bridge_url(base_url)
        self._timeout_seconds = float(timeout_seconds)
        self._session = session
        self._owns_session = session is None

    @classmethod
    def from_token_file(
        cls,
        token_file: str | Path,
        *,
        base_url: str = DEFAULT_BRIDGE_URL,
        timeout_seconds: float = 30.0,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> "FlytoRuntimeCapabilityClient":
        """Create a client from an explicitly supplied Runtime token file."""

        token = Path(token_file).read_text(encoding="utf-8").strip()
        return cls(
            token,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            session=session,
        )

    async def __aenter__(self) -> "FlytoRuntimeCapabilityClient":
        await self._ensure_session()
        return self

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the internally owned HTTP session, if any."""

        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def manifest(self) -> FlytoRuntimeManifest:
        """Fetch and validate the live Runtime capability manifest."""

        payload = await self._request_json("GET", "/manifest")
        return FlytoRuntimeManifest.model_validate(payload)

    async def invoke(
        self,
        capability: str,
        input_data: Mapping[str, Any],
        *,
        revision: int = 1,
        operation_id: Optional[str] = None,
        invocation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> CapabilityResult:
        """Invoke one Runtime capability without automatically waiting."""

        invocation = CapabilityInvocation(
            invocation_id=invocation_id or f"core-{uuid4().hex}",
            capability=capability,
            revision=revision,
            operation_id=operation_id or f"core-op-{uuid4().hex}",
            trace_id=trace_id,
            requested_at=_utc_now(),
            input=dict(input_data),
        )
        return await self.invoke_envelope(invocation)

    async def invoke_envelope(
        self,
        invocation: CapabilityInvocation | Mapping[str, Any],
    ) -> CapabilityResult:
        """Send an already constructed invocation envelope."""

        envelope = (
            invocation
            if isinstance(invocation, CapabilityInvocation)
            else CapabilityInvocation.model_validate(invocation)
        )
        payload = await self._request_json(
            "POST",
            "/invoke",
            json_body=envelope.model_dump(exclude_none=True, by_alias=True),
        )
        return CapabilityResult.model_validate(payload)

    async def invoke_until_terminal(
        self,
        capability: str,
        input_data: Mapping[str, Any],
        *,
        revision: int = 1,
        operation_id: Optional[str] = None,
        invocation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        max_wait_cycles: int = MAX_ACCEPTED_WAIT_CYCLES,
    ) -> CapabilityResult:
        """Invoke and follow bounded contract handles until terminal."""

        if max_wait_cycles <= 0:
            raise ValueError("max_wait_cycles must be positive")
        original = CapabilityInvocation(
            invocation_id=invocation_id or f"core-{uuid4().hex}",
            capability=capability,
            revision=revision,
            operation_id=operation_id or f"core-op-{uuid4().hex}",
            trace_id=trace_id,
            requested_at=_utc_now(),
            input=dict(input_data),
        )
        result = await self.invoke_envelope(original)
        cycle = 0
        while result.status == "accepted":
            if cycle >= max_wait_cycles:
                raise FlytoRuntimeBridgeError(
                    "Capability operation exceeded the bounded follow-up limit"
                )
            follow_up = result.operation.wait if result.operation else None
            if follow_up is None:
                raise FlytoRuntimeBridgeError(
                    "Accepted capability result did not provide a wait follow-up"
                )
            waited = await self.invoke_envelope(
                _follow_up_invocation(original, follow_up, cycle)
            )
            cycle += 1
            if waited.status == "failed":
                return waited
            if waited.status == "accepted":
                result = waited
                continue
            if waited.output.get("matched") is False:
                continue
            # Preserve exactly-once admission: reconcile by replaying the
            # original operation_id instead of starting a replacement action.
            result = await self.invoke_envelope(original)
        return result

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        session = await self._ensure_session()
        try:
            async with session.request(
                method,
                f"{self._base_url}{path}",
                headers={BRIDGE_TOKEN_HEADER: self._token},
                json=dict(json_body) if json_body is not None else None,
                # A redirect could forward the bridge token to a different
                # origin, even though the initial URL is loopback-only.
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise FlytoRuntimeBridgeError(
                        f"Flyto2 Runtime bridge request failed with HTTP {response.status}"
                    )
                payload = await response.json()
        except FlytoRuntimeBridgeError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise FlytoRuntimeBridgeError(
                "Flyto2 Runtime bridge request failed"
            ) from exc
        if not isinstance(payload, dict):
            raise FlytoRuntimeBridgeError("Flyto2 Runtime bridge returned non-object JSON")
        return payload

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout_seconds)
            )
        return self._session


def _follow_up_invocation(
    original: CapabilityInvocation,
    follow_up: CapabilityFollowUp,
    cycle: int,
) -> CapabilityInvocation:
    digest = hashlib.sha256(
        (
            f"{original.invocation_id}\0{original.operation_id}\0"
            f"{follow_up.capability}\0{cycle}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    return CapabilityInvocation(
        invocation_id=f"followup-{digest}",
        capability=follow_up.capability,
        revision=1,
        operation_id=f"followup-{digest}",
        trace_id=original.trace_id,
        requested_at=_utc_now(),
        input=dict(follow_up.input),
    )


def _normalize_bridge_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "http":
        raise ValueError("Flyto2 Runtime capability bridge must use local HTTP")
    if parsed.username or parsed.password:
        raise ValueError("Flyto2 Runtime bridge URL must not contain credentials")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Flyto2 Runtime capability bridge must use a loopback host")
    if parsed.query or parsed.fragment:
        raise ValueError("Flyto2 Runtime bridge URL must not contain query or fragment")
    path = parsed.path.rstrip("/")
    if path in {"", "/"}:
        path = "/flyto2/capabilities/v1"
    elif path != "/flyto2/capabilities/v1":
        raise ValueError("Flyto2 Runtime bridge URL has an unsupported path")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
