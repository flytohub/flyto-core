"""Integration: exact Core host policy must gate the real HA adapter."""

import os
import subprocess
import sys


def test_actual_core_host_requires_physical_approval_then_verifies_state():
    script = """
import asyncio
import tempfile
from pathlib import Path
from flyto_ecosystems.pack import register_all
from flyto_ecosystems.home_assistant import HomeAssistantAdapter, IntentLedger
from core.capability_host import CapabilityHost

register_all()

class HA:
    def __init__(self):
        self.value = "off"
        self.sends = 0
    def state(self, entity_id):
        return {"entity_id": entity_id, "state": self.value}
    def service(self, domain, action, entity_id):
        self.sends += 1
        self.value = "on"

with tempfile.TemporaryDirectory() as tmp:
    ha = HA()
    adapter = HomeAssistantAdapter("light.lobby", ha, IntentLedger(Path(tmp)/"ledger.db"), sleep=lambda _: None)
    options = dict(
        adapter_id="homeassistant.entity",
        resource_id="homeassistant:light.lobby",
        adapter_factory=lambda resource: adapter,
        sleep=lambda _: None,
    )
    request = {
        "resource_id": "homeassistant:light.lobby",
        "capability_id": "vendor.homeassistant.turn_on",
        "arguments": {},
    }
    denied = CapabilityHost(**options)
    first = asyncio.run(denied.invoke(request))
    assert first["outcome"] == "refused", first
    assert ha.sends == 0, denied.records()
    allowed = CapabilityHost(**options, allow=["vendor.homeassistant.turn_on"], yes_physical=True)
    second = asyncio.run(allowed.invoke(request))
    assert second["outcome"] == "completed", second
    assert ha.sends == 1, allowed.records()
    assert allowed.records()[0]["contract_status"] == "declared"
    assert ha.value == "on"
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
