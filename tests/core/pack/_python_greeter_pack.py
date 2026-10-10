"""The Node.js example pack's two modules, written with ``@register_module``.

Used to prove that the decorator and the Node helper produce the same
``flyto.pack.v1`` rows. Registration happens inside ``register_all`` — as an
entry-point pack does it — so the rows are owned by the pack that registers
them.
"""

from typing import Any, Dict

PACK_DESCRIPTION = "Example pack written in Node.js: greetings and repetition."


def register_all() -> None:
    """Register the greeter modules."""
    from core.modules.base import BaseModule
    from core.modules.registry import register_module

    @register_module(
        module_id="greeter.greet",
        version="1.0.0",
        category="greeter",
        label="Greet",
        description="Return a greeting for a name",
        icon="Hand",
        tags=["example", "greeting"],
        params_schema={
            "name": {
                "type": "string",
                "label": "Name",
                "description": "Who to greet",
                "placeholder": "Ada",
                "required": True,
                "maxLength": 64,
            },
        },
        output_schema={"greeting": {"type": "string", "description": "The greeting"}},
        provides_capability="greeter.greet",
        contract={
            "actuates": False,
            "safety_class": "read_only",
            "requires_safe_stop": False,
            "cancellable": True,
            "idempotent": True,
        },
        timeout_ms=5000,
        can_receive_from=["*"],
        can_connect_to=["*"],
    )
    class GreetModule(BaseModule):
        """Return a greeting."""

        def validate_params(self) -> None:
            """Nothing beyond the schema."""
            return None

        async def execute(self) -> Dict[str, Any]:
            """Greet."""
            return {"ok": True, "data": {"greeting": f"Hello, {self.params['name']}!"}}

    @register_module(
        module_id="greeter.repeat",
        version="1.0.0",
        category="greeter",
        label="Repeat",
        description="Repeat a text a bounded number of times",
        icon="Repeat",
        tags=["example"],
        params_schema={
            "text": {
                "type": "string",
                "label": "Text",
                "description": "Text to repeat",
                "placeholder": "hi",
                "required": True,
            },
            "times": {
                "type": "integer",
                "label": "Times",
                "description": "How many times",
                "default": 2,
                "min": 1,
                "max": 5,
            },
        },
        output_schema={"text": {"type": "string", "description": "The repeated text"}},
        timeout_ms=5000,
        can_receive_from=["*"],
        can_connect_to=["*"],
    )
    class RepeatModule(BaseModule):
        """Repeat a text."""

        def validate_params(self) -> None:
            """Nothing beyond the schema."""
            return None

        async def execute(self) -> Dict[str, Any]:
            """Repeat."""
            times = int(self.params.get("times", 2))
            return {"ok": True, "data": {"text": " ".join([self.params["text"]] * times)}}
