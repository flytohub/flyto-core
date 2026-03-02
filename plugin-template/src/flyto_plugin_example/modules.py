"""
Plugin modules registration.

This file is the entry point referenced in pyproject.toml:
    [project.entry-points."flyto.modules"]
    example = "flyto_plugin_example.modules:register_all"

When flyto-core discovers this plugin, it calls register_all()
to register all modules with the ModuleRegistry.
"""

from core.modules.base import BaseModule
from core.modules.registry import register_module
from core.modules.schema import compose, field
from core.modules.schema.constants import FieldGroup
from core.modules.types import EdgeType


@register_module(
    module_id="example.hello",
    version="0.1.0",
    category="example",
    tags=["example", "demo", "plugin"],
    label="Hello World",
    label_key="modules.example.hello.label",
    description="A simple hello world module that greets the user",
    description_key="modules.example.hello.description",
    icon="Hand",
    color="#8B5CF6",
    input_types=["string", "object"],
    output_types=["string"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    input_ports=[
        {
            "id": "input",
            "label": "Input",
            "edge_type": EdgeType.DATA.value,
        }
    ],
    output_ports=[
        {
            "id": "output",
            "label": "Output",
            "event": "success",
            "color": "#10B981",
            "edge_type": EdgeType.DATA.value,
        },
        {
            "id": "error",
            "label": "Error",
            "event": "error",
            "color": "#EF4444",
            "edge_type": EdgeType.CONTROL.value,
        },
    ],
    params_schema=compose(
        field(
            "name",
            type="string",
            label="Name",
            default="World",
            description="Name to greet",
            group=FieldGroup.BASIC,
        ),
        field(
            "greeting",
            type="string",
            label="Greeting",
            default="Hello",
            description="Greeting prefix",
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        "message": {
            "type": "string",
            "description": "The greeting message",
        },
    },
    examples=[
        {
            "name": "Basic greeting",
            "params": {"name": "World", "greeting": "Hello"},
        },
    ],
    author="Your Name",
    license="MIT",
)
class HelloWorldModule(BaseModule):
    """A simple hello world module."""

    module_name = "Hello World"
    module_description = "Greets the user"

    def validate_params(self):
        self.name = self.params.get("name", "World")
        self.greeting = self.params.get("greeting", "Hello")

    async def execute(self):
        message = f"{self.greeting}, {self.name}!"
        return {
            "__event__": "success",
            "message": message,
            "outputs": {"output": {"message": message}},
        }


def register_all():
    """
    Register all modules in this plugin.

    This function is called automatically by flyto-core when the plugin
    is discovered via entry_points. The @register_module decorator on
    each module class handles the actual registration, so this function
    just needs to ensure the module classes are imported.
    """
    # Module classes are registered via @register_module decorator above.
    # Simply importing this file is enough.
    pass
