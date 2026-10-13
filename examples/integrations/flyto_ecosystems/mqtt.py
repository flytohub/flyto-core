"""Read-only MQTT telemetry for approved exact topics.

No publish / command support: MQTT QoS (even QoS 2) cannot establish exactly
once physical effects. Mutating MQTT adapters must supply a durable device-side
call-id receipt and independently observed completion before being enabled.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Any, Callable

MAX_PAYLOAD_BYTES = 16 * 1024
TOPIC_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]{0,127}$")
CAPABILITY_ID = "vendor.mqtt.observe"


def _nonfinite_json(value: str) -> None:
    """Invalid JSON non-finite constants cannot become sensor evidence."""
    raise ValueError(f"non-finite MQTT sample: {value}")


class MqttTelemetryAdapter:
    """One topic per resource, bounded freshness, no inferred actuation."""

    def __init__(self, topic: str, *, clock: Callable[[], float] = time.monotonic,
                 freshness_seconds: float = 30.0):
        if not isinstance(topic, str) or not TOPIC_PATTERN.fullmatch(topic) or "//" in topic:
            raise ValueError("MQTT resource must bind one exact topic, no wildcard")
        self.topic = topic
        self.resource_id = f"mqtt:{topic}"
        self._clock = clock
        self.freshness_seconds = max(1.0, min(float(freshness_seconds), 3600.0))
        self._sample: dict[str, Any] | None = None
        self._received_at = float("-inf")
        self._client: Any = None

    @property
    def deployment_mode(self) -> str:
        return "physical"

    def describe(self) -> tuple[dict[str, Any], ...]:
        return ({
            "resource_id": self.resource_id,
            "capability_id": CAPABILITY_ID,
            "approval_status": "DISCOVERED",
            "actuates": False,
            "idempotent": True,
        },)

    def accept(self, topic: str, payload: bytes) -> bool:
        """Receive an MQTT message; wrong topic / malformed sample is ignored."""
        if topic != self.topic or not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD_BYTES:
            return False
        try:
            parsed = json.loads(
                payload.decode("utf-8"),
                parse_constant=_nonfinite_json,
            )
        except (ValueError, UnicodeError):
            return False
        # Flat scalar JSON is a deliberately bounded sensor contract.
        if type(parsed) in (bool, str, int, float):
            if type(parsed) is float and not math.isfinite(parsed):
                return False
            if isinstance(parsed, str) and len(parsed) > 512:
                return False
            self._sample = {"value": parsed, "topic": topic}
        elif (isinstance(parsed, dict) and set(parsed) == {"value"}
              and (type(parsed["value"]) in (str, int, float, bool))
              and len(str(parsed["value"])) <= 512):
            if type(parsed["value"]) is float and not math.isfinite(parsed["value"]):
                return False
            self._sample = {"value": parsed["value"], "topic": topic}
        else:
            return False
        self._received_at = self._clock()
        return True

    def observe(self, *, phase: str = "", execution_id: str = "") -> dict[str, Any]:
        if self._sample is None or self._clock() - self._received_at > self.freshness_seconds:
            raise RuntimeError("MQTT sample missing or stale")
        return {"telemetry": dict(self._sample), "phase": phase, "call_id": execution_id}

    def invoke(self, request: Any) -> dict[str, Any]:
        capability_id = getattr(request, "capability_id", "")
        arguments = getattr(request, "arguments", {})
        if capability_id != CAPABILITY_ID or arguments not in ({}, None):
            return {"outcome": "refused", "detail": "read-only MQTT adapter", "evidence": {}}
        try:
            evidence = self.observe(execution_id=str(getattr(request, "call_id", "") or ""))
        except RuntimeError:
            return {"outcome": "refused", "detail": "telemetry not observed or stale", "evidence": {}}
        return {"outcome": "completed", "detail": "fresh MQTT telemetry observed", "evidence": evidence}

    def connect(self, host: str, *, port: int = 8883, tls: bool = True,
                username: str = "", password: str = "", client_factory: Callable[..., Any] | None = None) -> None:
        """Begin exact-topic subscription. No connect on discovery/import."""
        if not host or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.:-]{0,253}", host):
            raise ValueError("MQTT broker hostname is invalid")
        if not tls:
            raise ValueError("MQTT telemetry transport requires TLS")
        if not 1 <= port <= 65535:
            raise ValueError("invalid MQTT port")
        if client_factory is None:
            try:
                import paho.mqtt.client as mqtt
            except ImportError as error:
                raise RuntimeError("Install flyto-ecosystems[mqtt] on the execution host") from error
            client_factory = mqtt.Client
        client = client_factory()
        if username:
            client.username_pw_set(username, password or None)
        client.tls_set()

        def message(_client: Any, _userdata: Any, packet: Any) -> None:
            # A retained value might have been published days ago. Receiving
            # it now is not independent evidence of a *fresh* sensor reading.
            if getattr(packet, "retain", False):
                return
            self.accept(packet.topic, packet.payload)

        def connected(_client: Any, _userdata: Any, _flags: Any, reason_code: Any, *_extra: Any) -> None:
            if int(reason_code) == 0:
                _client.subscribe(self.topic, qos=1)

        client.on_connect = connected
        client.on_message = message
        client.connect(host, port=port, keepalive=30)
        client.loop_start()
        self._client = client

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def cancel(self, call_id: str) -> dict[str, str]:
        return {"outcome": "refused", "detail": "read-only telemetry has no effect to cancel"}

    def safe_stop(self) -> dict[str, str]:
        return {"outcome": "refused", "detail": "no physical actuation in this MQTT adapter"}


def build_adapter(resource_id: str) -> MqttTelemetryAdapter:
    if not resource_id.startswith("mqtt:"):
        raise ValueError("not an MQTT resource")
    adapter = MqttTelemetryAdapter(resource_id[5:])
    # MQTT credentials stay in the local host environment, never manifests.
    host = os.environ.get("FLYTO_MQTT_HOST")
    if not host:
        raise ValueError("FLYTO_MQTT_HOST must be configured on the execution host")
    adapter.connect(
        host,
        port=int(os.environ.get("FLYTO_MQTT_PORT", "8883")),
        tls=True,
        username=os.environ.get("FLYTO_MQTT_USER", ""),
        password=os.environ.get("FLYTO_MQTT_PASSWORD", ""),
    )
    return adapter
