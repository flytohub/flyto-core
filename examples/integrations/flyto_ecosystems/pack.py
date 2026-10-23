"""Home Assistant capability declarations, registered through Flyto2 Core.

These modules intentionally reuse capability.invoke's existing opaque
dispatcher: registration is not another execution engine.
"""

from __future__ import annotations


def _register_one(action: str, actuates: bool) -> None:
    """Bind the capability id to this module, never to a loop's late value."""
    from core.modules.atomic.capability.invoke import CapabilityInvokeModule
    from core.modules.registry import register_module

    capability_id = f"vendor.homeassistant.{action}"
    contract = {
            "actuates": actuates,
            "safety_class": "controlled" if actuates else "read_only",
            "requires_safe_stop": False,
            "cancellable": False,
            "idempotent": not actuates,
            "effects": [],
            "evidence": [],
    }

    @register_module(
            module_id=f"ha.{action}",
            category="ha",
            version="1.0.0",
            label=f"Home Assistant {action}",
            description="Invoke a declared Home Assistant entity under the selected execution host",
            provides_capability=capability_id,
            contract=contract,
            params_schema={
                "resource_id": {
                    "type": "string", "required": True,
                    "description": "Approved homeassistant:<entity_id> resource",
                },
            },
            retryable=False,
            concurrent_safe=False,
            can_receive_from=["*"],
            can_connect_to=["*"],
    )
    class HomeAssistantCapability(CapabilityInvokeModule):
        """Bridge through Core's one authoritative opaque dispatcher."""

        def validate_params(self) -> None:
            self.params["capability_id"] = capability_id
            self.params["arguments"] = {}
            super().validate_params()

    HomeAssistantCapability.__name__ = f"HomeAssistant_{action}"


def register_all() -> None:
    """Register the external read-only and controlled capabilities."""
    for action, actuates in (
        ("observe", False),
        ("turn_on", True),
        ("turn_off", True),
    ):
        _register_one(action, actuates)
    from core.modules.atomic.capability.invoke import CapabilityInvokeModule
    from core.modules.registry import register_module

    @register_module(
        module_id="mqtt.observe",
        category="mqtt",
        version="1.0.0",
        label="MQTT Sensor Observation",
        description="Read the most recent fresh sample for an approved MQTT topic",
        provides_capability="vendor.mqtt.observe",
        contract={
            "actuates": False,
            "safety_class": "read_only",
            "requires_safe_stop": False,
            "cancellable": False,
            "idempotent": True,
            "evidence": [],
        },
        params_schema={
            "resource_id": {
                "type": "string", "required": True,
                "description": "Approved mqtt:<exact-topic> resource",
            },
        },
        retryable=False,
        can_receive_from=["*"],
        can_connect_to=["*"],
    )
    class MqttObserveCapability(CapabilityInvokeModule):
        """Passively read a host-bound MQTT sensor through capability.invoke."""

        def validate_params(self) -> None:
            self.params["capability_id"] = "vendor.mqtt.observe"
            self.params["arguments"] = {}
            super().validate_params()
