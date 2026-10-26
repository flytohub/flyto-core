# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""A resource fault in the adapter contract (``core.adapter_status``).

The rule is the one flyto-cloud reads (``services/device/equipment_fault.py``):
``fault: {reason, since}`` is a fault, ``fault: null`` is "checked, none", and
no ``fault`` key is "unknown" -- what every adapter written before this field
reports, so it stays valid. An exception that carries ``fault_code`` is a
fault, not only a failed call.
"""

import asyncio

import pytest

from core.adapter_status import (
    CONNECTION_STATES,
    FAULT_KEY,
    NOT_REPORTED,
    RAISED_CODE_ATTRIBUTE,
    REASON_FAULT_RAISED,
    REASON_FAULT_UNREADABLE,
    REPORTED_CLEAR,
    AdapterFaultError,
    ResourceFault,
    fault_code,
    fault_payload,
    raised_fault,
    read_fault,
    status_payload,
)
from core.capability_contract import validate_contract
from core.capability_host import CapabilityHost

SINCE = "2026-10-26T08:00:00+00:00"
RESOURCE = "resource-01"
READ = validate_contract({"actuates": False, "safety_class": "read_only", "requires_safe_stop": False,
                          "cancellable": False, "idempotent": True})


# -- the field --------------------------------------------------------------


def test_the_names_are_the_ones_cloud_reads():
    assert (FAULT_KEY, RAISED_CODE_ATTRIBUTE) == ("fault", "fault_code")
    assert (REASON_FAULT_UNREADABLE, REASON_FAULT_RAISED) == ("fault_report_unreadable", "adapter_fault")
    assert CONNECTION_STATES == ("connected", "reconnecting", "failed", "stopped")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({}, NOT_REPORTED),
        ({"state": "connected"}, NOT_REPORTED),
        (None, NOT_REPORTED),
        ({"fault": None}, REPORTED_CLEAR),
    ],
)
def test_absent_is_unknown_and_null_is_clear(payload, expected):
    assert read_fault(payload) == expected


def test_a_fault_is_its_reason_and_its_instant():
    reading = read_fault({"fault": {"reason": "limit.tripped", "since": "2026-10-26T08:00:00Z"}})
    assert reading.reported and reading.faulted
    assert reading.fault == ResourceFault("limit.tripped", SINCE)


@pytest.mark.parametrize(
    "raw",
    [
        "tripped",
        {"reason": "Not A Code", "since": SINCE},
        {"reason": "limit.tripped"},
        {"reason": "limit.tripped", "since": "2026-10-26T08:00:00"},
        {"reason": "limit.tripped", "since": "yesterday"},
        [],
    ],
)
def test_a_fault_nobody_can_read_is_a_fault_never_silence(raw):
    reading = read_fault({"fault": raw})
    assert reading.faulted
    assert reading.fault.reason == REASON_FAULT_UNREADABLE


def test_the_payload_written_is_the_payload_read():
    assert fault_payload(None) is None
    assert fault_payload(ResourceFault("drive.latched", SINCE)) == {"reason": "drive.latched", "since": SINCE}
    assert read_fault({"fault": fault_payload(ResourceFault("drive.latched", SINCE))}).fault.reason == "drive.latched"


def test_fault_code_grammar():
    assert fault_code(" drive.latched ") == "drive.latched"
    assert fault_code("Drive") == fault_code("") == fault_code(7) == ""


# -- the exception convention ---------------------------------------------------


def test_an_exception_with_fault_code_is_a_fault():
    class VendorError(Exception):
        fault_code = "controller.error_42"

    assert raised_fault(VendorError(), at=SINCE) == ResourceFault("controller.error_42", SINCE)


def test_an_unreadable_fault_code_is_still_a_fault():
    error = RuntimeError("x")
    error.fault_code = "Not A Code"
    assert raised_fault(error, at=SINCE) == ResourceFault(REASON_FAULT_RAISED, SINCE)


def test_any_other_exception_is_not_a_fault():
    assert raised_fault(RuntimeError("timeout"), at=SINCE) is None


def test_adapter_fault_is_the_ready_made_exception():
    error = AdapterFaultError("limit.tripped", "joint limit")
    assert isinstance(error, Exception) and error.fault_code == "limit.tripped"
    assert raised_fault(error, at=SINCE).reason == "limit.tripped"


# -- the status shape ----------------------------------------------------------


def test_a_status_without_fault_keeps_its_old_shape():
    raw = {"state": "connected", "since": SINCE, "attempts": 2, "last_error": "", "vendor_extra": object()}
    assert status_payload(raw) == {"state": "connected", "since": SINCE, "attempts": 2, "last_error": ""}


def test_a_status_carries_the_fault_normalized():
    found = status_payload({"state": "connected", "fault": {"reason": "limit.tripped", "since": "2026-10-26T08:00:00Z"}})
    assert found == {"state": "connected", "fault": {"reason": "limit.tripped", "since": SINCE}}
    assert status_payload({"state": "connected", "fault": None}) == {"state": "connected", "fault": None}
    assert status_payload({"fault": "garbled"})["fault"]["reason"] == REASON_FAULT_UNREADABLE


def test_a_status_field_of_the_wrong_type_is_dropped_not_coerced():
    assert status_payload({"state": "sleeping", "attempts": "3", "accepting_calls": 1}) == {}


# -- the host ------------------------------------------------------------------


class Adapter:
    deployment_mode = "simulation"

    def __init__(self, *, raise_fault=None, status=None, transport=None):
        self.raise_fault = raise_fault
        self.status = status
        if transport is not None:
            self.transport_status = lambda: transport

    def invoke(self, request):
        if self.raise_fault is not None:
            raise self.raise_fault
        return {"outcome": "completed"}

    def cancel(self, call_id):
        return {"outcome": "cancelled"}

    def safe_stop(self):
        return {"outcome": "completed"}


class StatusAdapter(Adapter):
    def connection_status(self):
        return self.status


def make_host(adapter):
    return CapabilityHost(
        adapter_id="fake.adapter", resource_id=RESOURCE, adapter_factory=lambda resource_id: adapter,
        contract_lookup=lambda capability_id: (READ, 5_000, "declared"), run_id="run-fault",
        sleep=lambda seconds: None,
    )


def call(host):
    return asyncio.run(host.invoke({"resource_id": RESOURCE, "capability_id": "thing.read", "arguments": {}}))


def test_an_adapter_that_reports_nothing_reports_no_fault_key():
    host = make_host(Adapter())
    record = call(host)
    assert record["outcome"] == "completed" and FAULT_KEY not in record
    assert host.connection_status() is None


def test_a_raised_fault_fails_the_call_and_is_latched_on_the_status():
    host = make_host(StatusAdapter(raise_fault=AdapterFaultError("limit.tripped"), status={"state": "connected"}))
    record = call(host)
    assert record["outcome"] == "failed"
    assert record[FAULT_KEY]["reason"] == "limit.tripped"
    assert host.connection_status() == {"state": "connected", "fault": record[FAULT_KEY]}


def test_the_adapter_saying_no_fault_clears_the_latch():
    adapter = StatusAdapter(raise_fault=AdapterFaultError("limit.tripped"), status={"state": "connected"})
    host = make_host(adapter)
    call(host)
    adapter.status = {"state": "connected", "fault": None}
    assert host.connection_status() == {"state": "connected", "fault": None}
    adapter.status = {"state": "connected"}
    assert host.connection_status() == {"state": "connected"}


def test_the_adapters_own_fault_answer_wins():
    fault = {"reason": "drive.latched", "since": SINCE}
    host = make_host(StatusAdapter(status={"state": "connected", "fault": fault}))
    assert host.connection_status() == {"state": "connected", "fault": fault}


def test_a_transport_status_is_read_when_there_is_no_connection_status():
    host = make_host(Adapter(transport={"state": "stopped", "fault": None}))
    assert host.connection_status() == {"state": "stopped", "fault": None}


def test_a_status_surface_that_raises_says_so():
    class Broken(Adapter):
        def connection_status(self):
            raise OSError("gone")

    assert make_host(Broken()).connection_status() == {"status_error": "OSError"}


def test_an_ordinary_adapter_error_is_not_a_fault():
    host = make_host(StatusAdapter(raise_fault=RuntimeError("boom"), status={"state": "connected"}))
    record = call(host)
    assert record["outcome"] == "failed" and FAULT_KEY not in record
    assert host.connection_status() == {"state": "connected"}
