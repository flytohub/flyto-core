"""External device ecosystems; never part of flyto-core's execution engine."""

from .wot import export_thing_description, import_thing_description

__all__ = ["import_thing_description", "export_thing_description"]
