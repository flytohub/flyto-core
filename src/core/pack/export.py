# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Export a Python pack's ``@register_module`` rows as a ``flyto.pack.v1`` manifest.

``@register_module`` is authoring syntax. This prints what it produced — the
language-neutral contract — so anyone can read, diff, sign or reimplement a
Python pack's surface without running Python, and so a pack in another
language can be checked against it row for row.

``target`` is either the name of an installed ``flyto.modules`` entry point
(``robotics``) or a ``package.module:register_all`` path. A path is loaded in
a registry transaction under the pack id, exactly as discovery loads an entry
point, and removed again afterwards.
"""

from __future__ import annotations

import copy
import importlib
from typing import Any, Dict, List, Optional

from .manifest import _SEMVER, PACK_SCHEMA, PackManifestError, validate_pack_manifest

__all__ = ["export_python_pack", "module_row_from_metadata"]


def module_row_from_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """The ``flyto.pack.v1`` module row for one registry metadata row."""
    m = copy.deepcopy(metadata)
    row = {
        "module_id": m["module_id"],
        "version": m.get("version", "1.0.0"),
        "stability": m.get("stability", "stable"),
        "label": m.get("ui_label") or m["module_id"],
        "label_key": m.get("ui_label_key"),
        "description": m.get("ui_description") or "",
        "description_key": m.get("ui_description_key"),
        "category": m.get("category") or m["module_id"].split(".", 1)[0],
        "subcategory": m.get("subcategory"),
        "tags": list(m.get("tags") or []),
        "icon": m.get("ui_icon"),
        "color": m.get("ui_color"),
        "params_schema": m.get("params_schema") or {},
        "output_schema": m.get("output_schema") or {},
        "input_types": list(m.get("input_types") or []),
        "output_types": list(m.get("output_types") or []),
        "can_receive_from": list(m.get("can_receive_from") or ["*"]),
        "can_connect_to": list(m.get("can_connect_to") or ["*"]),
        "provides_capability": m.get("provides_capability") or "",
        "contract": m.get("contract"),
        "required_permissions": list(m.get("required_permissions") or []),
        "timeout_ms": m.get("timeout_ms"),
        "retryable": bool(m.get("retryable", False)),
        "max_retries": m.get("max_retries", 0),
        "concurrent_safe": bool(m.get("concurrent_safe", True)),
        "requires_credentials": bool(m.get("requires_credentials", False)),
        "handles_sensitive_data": bool(m.get("handles_sensitive_data", False)),
    }
    if row["label_key"] is None:
        row.pop("label_key")
    return row


class _CallableEntryPoint:
    def __init__(self, name: str, value: str, func: Any, version: Optional[str], description: Optional[str]):
        self.name = name
        self.value = value
        self._func = func
        self.pack_version = version or ""
        self.pack_description = description

    def load(self) -> Any:
        return self._func


def _load_callable(path: str) -> Any:
    module_name, _, attr = path.partition(":")
    if not module_name or not attr:
        raise PackManifestError("INVALID_TARGET", "target must be an entry point name or module:callable")
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        raise PackManifestError("INVALID_TARGET", "target module cannot be imported") from None
    func = getattr(module, attr, None)
    if not callable(func):
        raise PackManifestError("INVALID_TARGET", "target attribute is not callable")
    return func


def _raw_rows(owner: str) -> List[Dict[str, Any]]:
    from ..modules.registry import ModuleRegistry

    ids = ModuleRegistry.get_plugin_modules(owner)
    with ModuleRegistry._discovery_lock:
        # The raw rows, not get_metadata's localized copies: a label declared
        # as {language: text} is exported as declared.
        return [copy.deepcopy(ModuleRegistry._metadata[module_id]) for module_id in sorted(ids)]


def export_python_pack(
    target: str,
    *,
    pack_id: Optional[str] = None,
    version: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the normalized ``flyto.pack.v1`` manifest of a Python pack."""
    from ..modules.registry import ModuleRegistry
    from ..modules.registry.core import _iter_entry_points

    plugins = ModuleRegistry.discover_plugins()
    entry_points = {getattr(ep, "name", ""): ep for ep in _iter_entry_points()}
    temporary = None
    if target in entry_points:
        owner = target
        entry_value = getattr(entry_points[target], "value", "") or target
        info = plugins.get(owner)
        version = version or (info.version if info else None)
        description = description or (info.description if info else None)
    elif ":" in target:
        func = _load_callable(target)
        owner = pack_id or target.split(":", 1)[0].split(".", 1)[0].replace("-", "_").lower()
        entry_value = target
        try:
            ModuleRegistry.install_external_pack(
                _CallableEntryPoint(owner, target, func, version, description)
            )
        except ValueError:
            raise PackManifestError("EXPORT_FAILED", "the pack failed to register its modules") from None
        temporary = owner
        info = ModuleRegistry.get_plugins().get(owner)
        description = description or (info.description if info else None)
        if not version and info and _SEMVER.fullmatch(info.version or ""):
            version = info.version
    else:
        raise PackManifestError("INVALID_TARGET", "no installed flyto.modules entry point has that name")

    try:
        rows = _raw_rows(owner)
    finally:
        if temporary is not None:
            ModuleRegistry.uninstall_external_pack(temporary)
    if not rows:
        raise PackManifestError(
            "EXPORT_EMPTY",
            "the pack registered no modules under its own name (were they registered at import time?)",
        )
    if not version or not _SEMVER.fullmatch(version):
        raise PackManifestError("INVALID_SEMVER", "pack version is unknown or not semver; pass version=")

    pack: Dict[str, Any] = {
        "id": pack_id or owner,
        "version": version,
        "namespaces": sorted({row["module_id"].split(".", 1)[0] for row in rows}),
    }
    if description:
        pack["description"] = description
    return validate_pack_manifest(
        {
            "schema": PACK_SCHEMA,
            "pack": pack,
            "runtime": {"binding": "inprocess-python", "entry_point": entry_value},
            "modules": [module_row_from_metadata(row) for row in rows],
        }
    )
