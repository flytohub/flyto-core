"""flow.trigger declares the settings a host's trigger editor writes onto it.

A host refuses to save a parameter the module contract does not declare. The
trigger editor writes the schedule's ``timezone``, a webhook's
``webhook_provider`` and ``require_signature``, and the ``triggers`` list; each
is declared, holds no secret, is never drawn as a generic field, and gets
no default: a new trigger node's params stay what they were, so an empty
``triggers`` list never turns a single trigger into a list of none.
"""

import pytest

from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry

HOST_SETTINGS = ("timezone", "webhook_provider", "require_signature", "triggers")


@pytest.mark.parametrize("key", HOST_SETTINGS)
def test_the_trigger_declares_each_host_setting_hidden(key):
    schema = ModuleRegistry.get_metadata("flow.trigger")["params_schema"]

    assert key in schema
    assert schema[key].get("visibility") == "hidden"
    assert schema[key].get("skipDefault") is True
    assert "default" not in schema[key]
    assert not schema[key].get("secret") and schema[key].get("format") != "password"
