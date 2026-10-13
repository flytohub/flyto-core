"""The optional pack uses Flyto2's actual registry, not an invented catalog."""

import os
import subprocess
import sys


def test_core_registry_accepts_external_adapters_as_modules():
    # Keep the Core global singleton untouched for the other integration tests.
    script = """
from flyto_ecosystems.pack import register_all
from core.capability_manifest import get_capability_manifest
register_all()
manifest = get_capability_manifest()
capabilities = {row["capability"] for row in manifest["capabilities"]}
expected = {
    "vendor.homeassistant.observe",
    "vendor.homeassistant.turn_on",
    "vendor.homeassistant.turn_off",
    "vendor.mqtt.observe",
}
assert expected <= capabilities, expected - capabilities
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-3500:]
