"""Non-executing W3C WoT Thing Description 1.1 translation.

The TD is untrusted discovery material, not an authority to call a URL or
approve a device. The host's existing registration lifecycle owns approval,
binding, cancellation and evidence. This module never makes a network request.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

TD_CONTEXT = "https://www.w3.org/2022/wot/td/v1.1"
MAX_AFFORDANCES = 128
_WOT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Offer:
    """A discovered capability proposal, never an approved declaration."""

    resource_id: str
    capability_id: str
    kind: str
    name: str
    idempotent: bool = False
    safe: bool = False
    observable: bool = False
    approval_status: str = "DISCOVERED"


def _names(td: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = td.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"TD {key} must be an object")
    if len(value) > MAX_AFFORDANCES:
        raise ValueError("TD has too many affordances")
    return value


def _forms(affordance: Mapping[str, Any]) -> None:
    forms = affordance.get("forms", [])
    if not isinstance(forms, list) or len(forms) > 16:
        raise ValueError("TD forms must be a bounded array")
    for form in forms:
        if not isinstance(form, Mapping):
            raise ValueError("TD form must be an object")
        href = form.get("href", "")
        if not isinstance(href, str) or len(href) > 2048:
            raise ValueError("TD form URL is invalid")
        parsed = urlsplit(href)
        if parsed.scheme not in {"http", "https", "coap", "coaps", "mqtt", "mqtts", ""}:
            raise ValueError("unsupported TD form transport")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("TD form cannot embed credentials or fragments")
        # Deliberately do not dereference or store the form URL in an Offer.


def import_thing_description(td: Mapping[str, Any], *, resource_id: str) -> tuple[Offer, ...]:
    """Turn externally claimed affordances into unapproved Flyto2 offers."""
    if not isinstance(td, Mapping):
        raise ValueError("Thing Description must be an object")
    if not isinstance(resource_id, str) or not resource_id or len(resource_id) > 192:
        raise ValueError("resource_id must identify a bounded resource")
    context = td.get("@context")
    contexts = [context] if isinstance(context, str) else context
    if not isinstance(contexts, list) or TD_CONTEXT not in contexts:
        raise ValueError("Thing Description 1.1 context required")
    if not isinstance(td.get("title"), str) or not td["title"].strip():
        raise ValueError("Thing Description title is required")
    defs = td.get("securityDefinitions")
    if not isinstance(defs, Mapping) or not defs:
        raise ValueError("securityDefinitions are required")
    selected = td.get("security")
    selected_names = [selected] if isinstance(selected, str) else selected
    if not isinstance(selected_names, list) or not selected_names:
        raise ValueError("security must name declared securityDefinitions")
    if any(not isinstance(name, str) or name not in defs for name in selected_names):
        raise ValueError("security references undefined securityDefinitions")

    result: list[Offer] = []
    used: set[str] = set()
    for kind, key in (("property", "properties"), ("action", "actions"), ("event", "events")):
        for name, spec in _names(td, key).items():
            if not isinstance(name, str) or not _WOT_NAME.fullmatch(name):
                raise ValueError(f"invalid TD {kind} name")
            if not isinstance(spec, Mapping):
                raise ValueError("TD affordance must be an object")
            _forms(spec)
            if kind == "action":
                for flag in ("safe", "idempotent"):
                    if flag in spec and type(spec[flag]) is not bool:
                        raise ValueError(f"{flag} must be a boolean")
            if kind == "property" and "readOnly" in spec and type(spec["readOnly"]) is not bool:
                raise ValueError("readOnly must be a boolean")
            canonical = name.replace("-", "_").lower()
            cap = f"vendor.wot.{kind}_{canonical}"
            if cap in used:
                raise ValueError("two TD affordances map to one capability identifier")
            used.add(cap)
            result.append(Offer(
                resource_id=resource_id,
                capability_id=cap,
                kind=kind,
                name=name,
                safe=bool(spec.get("safe", False)) if kind == "action" else kind != "action",
                idempotent=bool(spec.get("idempotent", False)) if kind == "action" else kind != "action",
                observable=kind in {"property", "event"},
            ))
    if len(result) > MAX_AFFORDANCES:
        raise ValueError("TD has too many total affordances")
    return tuple(result)


def export_thing_description(
    offers: tuple[Offer, ...], *,
    title: str,
    security_definitions: Mapping[str, Any],
    security: str,
    forms_by_capability: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Export approved affordances with real host-supplied forms and auth.

    Never fabricate anonymous access or endpoints. A host must explicitly
    provide real, independently authorized interaction forms.
    """
    if not title or len(title) > 128:
        raise ValueError("title must be non-empty and bounded")
    if (not isinstance(security_definitions, Mapping) or security not in security_definitions
            or not isinstance(security_definitions[security], Mapping)
            or security_definitions[security].get("scheme") in (None, "nosec")):
        raise ValueError("approved Thing Description requires explicit non-anonymous security")
    td: dict[str, Any] = {
        "@context": TD_CONTEXT, "title": title,
        "securityDefinitions": dict(security_definitions),
        "security": security,
        "properties": {}, "actions": {}, "events": {},
    }
    for offer in offers:
        if offer.approval_status != "APPROVED":
            # Avoid making discovered but unapproved affordances appear callable.
            continue
        collection = {"property": "properties", "action": "actions", "event": "events"}.get(offer.kind)
        if collection is None or not _WOT_NAME.fullmatch(offer.name):
            raise ValueError("invalid offer to export")
        forms = forms_by_capability.get(offer.capability_id)
        if not forms:
            raise ValueError("approved affordances require real interaction forms")
        _forms({"forms": forms})
        spec: dict[str, Any] = {}
        if offer.kind == "action":
            spec = {"safe": offer.safe, "idempotent": offer.idempotent}
        elif offer.kind == "property":
            spec = {"readOnly": True}
        spec["forms"] = forms
        td[collection][offer.name] = spec
    return td
