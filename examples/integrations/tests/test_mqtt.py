from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from flyto_ecosystems.mqtt import MqttTelemetryAdapter


@dataclass
class Request:
    call_id: str = "one"
    capability_id: str = "vendor.mqtt.observe"
    arguments: dict | None = None


def test_exact_topic_passive_telemetry_and_freshness():
    moment = [100.0]
    adapter = MqttTelemetryAdapter("lab/temperature", clock=lambda: moment[0], freshness_seconds=5)
    assert adapter.invoke(Request())["outcome"] == "refused"
    assert not adapter.accept("lab/other", b"20")
    assert adapter.accept("lab/temperature", b'{"value": 24.5}')
    assert adapter.invoke(Request())["evidence"]["telemetry"]["value"] == 24.5
    moment[0] = 105.1
    assert adapter.invoke(Request())["outcome"] == "refused"


@pytest.mark.parametrize("topic", [
    "lab/#", "lab/+", "lab/#/temperature", "../temperature", "",
    "/absolute", "lab//temperature", "lab/$SYS",
])
def test_topic_bindings_must_be_exact(topic):
    with pytest.raises(ValueError):
        MqttTelemetryAdapter(topic)


@pytest.mark.parametrize("payload", [
    b"{", b'{"value": []}', b'{"value": 2, "command":"turn_on"}',
    b"NaN", b'{"value": NaN}', b"null", b'"' + b"a" * 17000 + b'"',
])
def test_invalid_telemetry_never_becomes_evidence(payload):
    adapter = MqttTelemetryAdapter("lab/temperature")
    assert adapter.accept("lab/temperature", payload) is False
    assert adapter.invoke(Request())["outcome"] == "refused"


def test_mutation_never_publishes_and_is_not_a_capability():
    adapter = MqttTelemetryAdapter("lab/temperature")
    assert adapter.invoke(Request(capability_id="vendor.mqtt.publish"))["outcome"] == "refused"
    assert adapter.cancel("one")["outcome"] == "refused"
    assert adapter.safe_stop()["outcome"] == "refused"
    assert adapter.describe()[0]["approval_status"] == "DISCOVERED"


def test_transport_requires_tls_and_subscribes_to_one_exact_topic():
    adapter = MqttTelemetryAdapter("lab/temperature")
    class Client:
        def __init__(self):
            self.subscribed = []
            self.loop = False
            self.secured = False
            self.on_connect = None
            self.on_message = None

        def tls_set(self):
            self.secured = True

        def connect(self, *_args, **_kwargs):
            self.on_connect(self, None, {}, 0)

        def subscribe(self, topic, qos):
            self.subscribed.append((topic, qos))

        def loop_start(self):
            self.loop = True

        def loop_stop(self):
            self.loop = False

        def disconnect(self):
            return None

    c = Client()
    with pytest.raises(ValueError):
        adapter.connect("broker.local", tls=False, client_factory=lambda: c)
    adapter.connect("broker.local", client_factory=lambda: c)
    assert c.secured
    assert c.subscribed == [("lab/temperature", 1)]
    c.on_message(c, None, SimpleNamespace(topic="lab/temperature", payload=b"17"))
    assert adapter.observe()["telemetry"]["value"] == 17
    c.on_message(c, None, SimpleNamespace(topic="lab/temperature", payload=b"99", retain=True))
    assert adapter.observe()["telemetry"]["value"] == 17
    adapter.disconnect()
    assert not c.loop
