from dataclasses import dataclass
from threading import Thread

import pytest
from flyto_ecosystems.home_assistant import (
    HomeAssistantAdapter,
    HomeAssistantREST,
    IntentLedger,
    _url,
    discover_entities,
)


@dataclass
class Request:
    call_id: str
    capability_id: str
    arguments: dict


class Transport:
    def __init__(self, *, value="off", fail_service=False, fail_observe=False, auto_change=True):
        self.value = value
        self.service_calls = 0
        self.fail_service = fail_service
        self.fail_observe = fail_observe
        self.auto_change = auto_change

    def state(self, entity_id):
        if self.fail_observe:
            raise ConnectionError("network failed")
        return {"entity_id": entity_id, "state": self.value}

    def service(self, domain, operation, entity_id):
        self.service_calls += 1
        if self.fail_service:
            raise ConnectionError("response lost: side effect may have occurred")
        if self.auto_change:
            self.value = "on" if operation == "turn_on" else "off"

    def entities(self):
        return [
            {"entity_id": "light.lobby"},
            {"entity_id": "sensor.temperature"},
            {"entity_id": "script.unsafe"},
        ]


def adapter(tmp_path, transport=None, resource="light.lobby"):
    transport = transport or Transport()
    return HomeAssistantAdapter(resource, transport, IntentLedger(tmp_path / "ledger.sqlite3"), sleep=lambda _: None), transport


def test_can_read_and_discover_but_not_auto_approve(tmp_path):
    a, t = adapter(tmp_path)
    assert a.observe()["state"]["value"] == "off"
    assert all(x["approval_status"] == "DISCOVERED" for x in a.describe())
    assert [x["entity_id"] for x in discover_entities(t)] == ["light.lobby", "sensor.temperature"]
    assert a.invoke(Request("o1", "vendor.homeassistant.observe", {}))["outcome"] == "completed"
    assert t.service_calls == 0


def test_actuation_requires_durable_unique_id_and_state_evidence(tmp_path):
    a, t = adapter(tmp_path)
    call = Request("call-1", "vendor.homeassistant.turn_on", {})
    answer = a.invoke(call)
    assert answer["outcome"] == "completed"
    assert answer["evidence"]["before"]["state"]["value"] == "off"
    assert answer["evidence"]["after"]["state"]["value"] == "on"
    assert t.service_calls == 1
    again = adapter(tmp_path, t)[0].invoke(call)
    assert again["outcome"] == "completed"
    assert again["evidence"]["replay"] is False
    assert t.service_calls == 1
    forbidden = a.invoke(Request("call-1", "vendor.homeassistant.turn_off", {}))
    assert forbidden["outcome"] == "refused"
    assert t.service_calls == 1


def test_unknown_service_outcome_is_never_resubmitted(tmp_path):
    t = Transport(fail_service=True)
    a, _ = adapter(tmp_path, t)
    call = Request("c2", "vendor.homeassistant.turn_on", {})
    assert a.invoke(call)["outcome"] == "failed"
    assert adapter(tmp_path, t)[0].invoke(call)["outcome"] == "refused"
    assert t.service_calls == 1


def test_missing_observation_does_not_mean_completed(tmp_path):
    t = Transport(auto_change=False)
    a, _ = adapter(tmp_path, t)
    call = Request("c3", "vendor.homeassistant.turn_on", {})
    assert a.invoke(call)["outcome"] == "failed"
    assert t.service_calls == 1
    assert a.invoke(call)["outcome"] == "refused"
    assert t.service_calls == 1


def test_unreadable_state_fails_before_intent_or_actuation(tmp_path):
    t = Transport(fail_observe=True)
    a, _ = adapter(tmp_path, t)
    assert a.invoke(Request("c4", "vendor.homeassistant.turn_on", {}))["outcome"] == "refused"
    assert t.service_calls == 0
    t.fail_observe = False
    assert a.invoke(Request("c4", "vendor.homeassistant.turn_on", {}))["outcome"] == "completed"
    assert t.service_calls == 1


@pytest.mark.parametrize("state", ["unknown", "unavailable", ""])
def test_ha_unreported_state_never_authorizes_actuation(tmp_path, state):
    a, t = adapter(tmp_path, Transport(value=state))
    assert a.invoke(Request("unavailable", "vendor.homeassistant.observe", {}))["outcome"] == "failed"
    assert a.invoke(Request("unavailable-control", "vendor.homeassistant.turn_on", {}))["outcome"] == "refused"
    assert t.service_calls == 0


def test_sensor_never_accepts_mutating_call(tmp_path):
    a, t = adapter(tmp_path, resource="sensor.temperature")
    assert a.invoke(Request("c5", "vendor.homeassistant.turn_on", {}))["outcome"] == "refused"
    assert t.service_calls == 0


def test_no_cancellation_or_emergency_stop_is_fabricated(tmp_path):
    a, _ = adapter(tmp_path)
    assert a.cancel("c")["outcome"] == "refused"
    assert a.safe_stop()["outcome"] == "refused"


def test_duplicate_call_id_writes_one_intent_even_in_parallel(tmp_path):
    ledger = IntentLedger(tmp_path / "ledger.sqlite3")
    results = []

    def run():
        results.append(ledger.claim("same", "hash")[0])

    threads = [Thread(target=run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [False] * 7 + [True]


@pytest.mark.parametrize("url,local,valid", [
    ("https://ha.example.com", False, True),
    ("http://192.168.1.5:8123", True, True),
    ("http://127.0.0.1:8123", False, False),
    ("http://remote.example.com:8123", True, False),
    ("http://ha.local:8123", True, True),
    ("https://user:fake@localhost", False, False),
    ("file:///tmp/ha", True, False),
    ("https://ha.example.com/base", False, False),
])
def test_endpoint_requires_explicit_secure_configuration(url, local, valid):
    if valid:
        assert _url(url, allow_local_http=local) == url
    else:
        with pytest.raises(ValueError):
            _url(url, allow_local_http=local)


def test_http_transport_never_follows_redirects_or_leaks_secrets():
    t = HomeAssistantREST("https://ha.example.com", "runtime-token")
    assert t._opener.handlers
    assert "runtime-token" not in repr(t)
    with pytest.raises(ValueError):
        t.request("/api/../secrets")
