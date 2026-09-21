import pytest

from core.modules.atomic.capability.invoke import (
    CapabilityInvokeModule,
    RUNTIME_DISPATCHER_CONTEXT_KEY,
)


class Dispatcher:
    _flyto_runtime_opaque = True

    def __init__(self, result=None):
        self.requests = []
        self.result = result or {"outcome": "completed", "evidence": {"ok": True}}

    async def invoke(self, request):
        self.requests.append(dict(request))
        return dict(self.result)


@pytest.mark.asyncio
async def test_capability_invoke_uses_only_opaque_runtime_dispatcher():
    dispatcher = Dispatcher()
    module = CapabilityInvokeModule(
        {
            "resource_id": "robot-1",
            "capability_id": "motion.advance",
            "arguments": {"distance_m": 0.05, "speed_mps": 0.02},
        },
        {RUNTIME_DISPATCHER_CONTEXT_KEY: dispatcher},
    )

    result = await module.execute()

    assert result["ok"] is True
    assert dispatcher.requests == [
        {
            "resource_id": "robot-1",
            "capability_id": "motion.advance",
            "arguments": {"distance_m": 0.05, "speed_mps": 0.02},
        }
    ]


@pytest.mark.asyncio
async def test_capability_invoke_refuses_without_host_authority():
    module = CapabilityInvokeModule(
        {
            "resource_id": "robot-1",
            "capability_id": "motion.advance",
            "arguments": {},
        },
        {},
    )

    result = await module.execute()

    assert result["ok"] is False
    assert result["error"]["code"] == "CAPABILITY_RUNTIME_UNAVAILABLE"


def test_capability_invoke_rejects_nested_or_unbounded_arguments():
    with pytest.raises(ValueError, match="bounded JSON scalar"):
        CapabilityInvokeModule(
            {
                "resource_id": "robot-1",
                "capability_id": "vendor.example.pick",
                "arguments": {"target": {"x": 1}},
            },
            {},
        )
