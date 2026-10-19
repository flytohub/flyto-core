"""A webhook trigger runs when its deployment calls it; the path is its deployment's to give.

``flow.trigger`` refused to run a webhook trigger without ``webhook_path``
("webhook_path required for webhook trigger"), although its schema marks the
path optional. A deployment that addresses its webhooks itself (Flyto2 Cloud
gives each registered webhook its own address) never sets it, so every
workflow such a call started failed at its first step. The path stays a
setting for a server that mounts webhooks by path, and is reported when set.
"""

import pytest

from core.modules import atomic  # noqa: F401
from core.modules.registry import ModuleRegistry


async def _run(params):
    module = ModuleRegistry.get("flow.trigger")(params, {})
    return await module.run() if hasattr(module, "run") else await module.execute()


@pytest.mark.asyncio
async def test_a_webhook_trigger_runs_without_a_path():
    result = await _run({"trigger_type": "webhook"})

    assert result.get("__event__") == "triggered"


@pytest.mark.asyncio
async def test_a_path_that_is_set_is_still_reported():
    result = await _run({"trigger_type": "webhook", "webhook_path": "/hooks/orders"})

    assert result["trigger_data"]["webhook_path"] == "/hooks/orders"
