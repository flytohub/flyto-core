# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Install out-of-process ``flyto.pack.v1`` packs into the module registry.

A pack written in any language arrives as a directory holding
``flyto-pack.json`` (and, normally, ``flyto-pack.sig.json``). Installing it:

1. validates and normalizes the manifest (``core.pack.manifest``);
2. recomputes the tree digest of the directory and compares it with
   ``artifact.digest``;
3. verifies the ed25519 publisher signature against the host's trusted key
   set — refusing an unsigned pack unless the host explicitly allows one;
4. registers one module per manifest row through ``@register_module`` itself,
   inside a ``ModuleRegistry`` load transaction whose owner is the pack id —
   so the rows are validated, contract-checked, ownership-stamped and policy
   gated exactly like a Python module's, and they appear in the catalog,
   the capability manifest and MCP search with no special case;
5. makes the pack invocable: a ``subprocess-jsonrpc`` pack is registered with
   a ``PluginManager`` that is wired into the ``RuntimeInvoker``; an ``http``
   pack is reached at the endpoint the host configures for its namespace;
6. records an install provenance record (``flyto.pack-provenance.v1``).

Nothing here downloads anything or contacts a key server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..modules.base import BaseModule
from ..plugin.manifest import (
    PluginManifestError,
    plugin_environment_names,
    validate_plugin_endpoint,
)
from .manifest import (
    LOADABLE_BINDINGS,
    PACK_SCHEMA,
    PackManifestError,
    manifest_sha256,
    pack_tree_digest,
    read_pack_manifest,
    stage_pack_tree,
)
from .signature import read_signature, verify_manifest_signature

logger = logging.getLogger(__name__)

__all__ = [
    "PROVENANCE_SCHEMA",
    "PackProvenance",
    "install_pack",
    "uninstall_pack",
    "installed_packs",
    "get_pack_plugin_manager",
]

PROVENANCE_SCHEMA = "flyto.pack-provenance.v1"
ALLOWED_HOSTS_ENV = "FLYTO_PLUGIN_ENDPOINT_ALLOWED_HOSTS"


@dataclass(frozen=True)
class PackProvenance:
    """What was installed, from where, and on whose signature."""

    pack_id: str
    version: str
    binding: str
    manifest_sha256: str
    artifact_digest: Optional[str]
    signature: Optional[Dict[str, str]]
    signature_verified: bool
    module_ids: Tuple[str, ...]
    source: str
    installed_at: str
    host_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": PROVENANCE_SCHEMA,
            "pack_id": self.pack_id,
            "version": self.version,
            "binding": self.binding,
            "manifest_sha256": self.manifest_sha256,
            "artifact_digest": self.artifact_digest,
            "signature": dict(self.signature) if self.signature else None,
            "signature_verified": self.signature_verified,
            "module_ids": list(self.module_ids),
            "source": self.source,
            "installed_at": self.installed_at,
            "host_version": self.host_version,
        }


@dataclass
class _InstalledPack:
    provenance: PackProvenance
    transport: Any
    manifest: Dict[str, Any] = field(repr=False, default_factory=dict)
    # The host-private copy a subprocess pack runs from (None for http).
    staged_dir: Optional[Path] = None


_LOCK = threading.Lock()
# Serializes install_pack end to end, so two installs of one id cannot both
# pass the "already installed" check and leave one transport orphaned.
_INSTALL_LOCK = threading.RLock()
_INSTALLED: Dict[str, _InstalledPack] = {}
_MANAGER: Any = None


def get_pack_plugin_manager():
    """The ``PluginManager`` that owns every subprocess pack's process."""
    global _MANAGER
    with _LOCK:
        if _MANAGER is None:
            from ..runtime.manager import PluginManager

            # A private, empty directory: packs are registered explicitly by
            # id, so the manager's own directory discovery must find nothing.
            _MANAGER = PluginManager(
                plugin_dir=Path(tempfile.mkdtemp(prefix="flyto-packs-")),
                pool_id="flyto-packs",
            )
        return _MANAGER


def _wire_invoker(manager: Any) -> None:
    """Wire the pack manager into the global ``RuntimeInvoker``.

    ``set_plugin_manager`` used to have no caller, so the invoker's plugin
    route was dead. It is set here when the invoker has no manager yet (or
    already has this one, which refreshes the router's plugin ids). A host
    that wired its own manager keeps it; pack modules pass their manager
    explicitly, so they work either way.
    """
    from ..runtime.invoke import get_invoker

    invoker = get_invoker()
    if invoker.plugin_manager is None or invoker.plugin_manager is manager:
        invoker.set_plugin_manager(manager)


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------


class _SubprocessTransport:
    """JSON-RPC over stdio, through the shared ``PluginManager``."""

    def __init__(self, pack_id: str, manager: Any, timeout_ms: int):
        self.pack_id = pack_id
        self.manager = manager
        self.timeout_ms = timeout_ms

    async def invoke(self, module_id: str, params: Dict[str, Any], context: Dict[str, Any], timeout_ms: Optional[int]) -> Any:
        from ..runtime.invoke import get_invoker

        return await get_invoker().invoke_plugin_step(
            plugin_id=self.pack_id,
            step_id=module_id,
            input_data=params,
            context=context,
            timeout_ms=min(timeout_ms or self.timeout_ms, self.timeout_ms),
            manager=self.manager,
        )

    async def close(self) -> None:
        await self.manager.unregister_pack(self.pack_id)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 - urllib hook
        """Refuse every redirect: the endpoint is configuration, not a hint."""
        return None


class _HttpTransport:
    """``POST <endpoint>/v1/invoke`` to the endpoint the host configured.

    The address is derived from the pack's first namespace —
    ``FLYTO_PLUGIN_ENDPOINT__<NAMESPACE>`` and ``FLYTO_PLUGIN_TOKEN__<NAMESPACE>``
    — and never read from the manifest, then checked against the declared
    locality (loopback for ``same_host``; an explicit
    ``FLYTO_PLUGIN_ENDPOINT_ALLOWED_HOSTS`` entry for ``same_network``) on
    every call, with no DNS lookup and no redirects.
    """

    def __init__(self, namespace: str, locality: str, timeout_ms: int, max_bytes: int):
        self.endpoint_env, self.token_env = plugin_environment_names(namespace)
        self.locality = locality
        self.timeout_ms = timeout_ms
        self.max_bytes = max_bytes

    def _endpoint(self) -> str:
        endpoint = os.environ.get(self.endpoint_env, "")
        if not endpoint:
            raise PackManifestError("ENDPOINT_MISSING", f"{self.endpoint_env} is not configured")
        allowed = tuple(h.strip() for h in os.environ.get(ALLOWED_HOSTS_ENV, "").split(",") if h.strip())
        try:
            validate_plugin_endpoint(endpoint, self.locality, allowed)
        except PluginManifestError as exc:
            raise PackManifestError(exc.code, str(exc)) from None
        return endpoint.rstrip("/") + "/v1/invoke"

    def _post(self, url: str, body: bytes, timeout_s: float) -> Any:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = os.environ.get(self.token_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=timeout_s) as response:  # nosec B310 - scheme checked
                raw = response.read(self.max_bytes + 1)
        except urllib.error.HTTPError as exc:
            raw = exc.read(self.max_bytes + 1)
        if len(raw) > self.max_bytes:
            raise PackManifestError("RESPONSE_TOO_LARGE", "pack response exceeds max_response_bytes")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise PackManifestError("PROTOCOL_ERROR", "pack response is not JSON") from None
        if type(data) is not dict or data.get("contract_version") != PACK_SCHEMA:
            raise PackManifestError("PROTOCOL_ERROR", "pack response lacks contract_version flyto.pack.v1")
        return data

    async def invoke(self, module_id: str, params: Dict[str, Any], context: Dict[str, Any], timeout_ms: Optional[int]) -> Any:
        url = self._endpoint()
        body = json.dumps(
            {"contract_version": PACK_SCHEMA, "module_id": module_id, "params": params, "context": context},
            allow_nan=False,
        ).encode("utf-8")
        budget = min(timeout_ms or self.timeout_ms, self.timeout_ms) / 1000.0
        return await asyncio.to_thread(self._post, url, body, budget)

    async def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# The registry row's implementation
# ---------------------------------------------------------------------------


class PackModule(BaseModule):
    """A module whose implementation lives in an out-of-process pack.

    One subclass per manifest row is registered through ``@register_module``.
    ``BaseModule.run`` has already applied the policy gate (with the pack as
    owner) and the module's timeout by the time ``execute`` runs, and the
    parameters were validated against the row's ``params_schema``.
    """

    auto_validate_schema = True
    pack_id: str = ""
    _row_timeout_ms: Optional[int] = None

    def validate_params(self) -> None:
        """Parameters are validated against the registry schema before this."""
        return None

    def _wire_context(self) -> Dict[str, Any]:
        """The context a foreign process receives: identifiers only.

        Never the execution context itself — it holds secrets, credentials,
        browser handles and host authority, none of which a third-party
        process is entitled to.
        """
        wire = {"pack_id": self.pack_id, "module_id": self.module_id}
        execution_id = self.context.get("execution_id") if isinstance(self.context, dict) else None
        if isinstance(execution_id, str):
            wire["execution_id"] = execution_id
        return wire

    async def execute(self) -> Dict[str, Any]:
        """Send the call to the pack and normalize its envelope."""
        installed = _INSTALLED.get(self.pack_id)
        if installed is None:
            return _failure("PACK_NOT_INSTALLED", f"pack '{self.pack_id}' is not installed")
        try:
            envelope = await installed.transport.invoke(
                self.module_id, dict(self.params), self._wire_context(), self._row_timeout_ms
            )
        except PackManifestError as exc:
            return _failure(exc.code, str(exc))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport failures become module failures
            return _failure("PACK_TRANSPORT_ERROR", f"{type(exc).__name__}: {str(exc)[:500]}")
        return self._normalize(envelope)

    def _normalize(self, envelope: Any) -> Dict[str, Any]:
        if type(envelope) is not dict or type(envelope.get("ok")) is not bool:
            # No absent-means-true across a language boundary.
            return _failure("PACK_PROTOCOL_ERROR", "pack reply has no boolean 'ok'")
        if envelope["ok"]:
            return {"ok": True, "data": envelope.get("data")}
        error = envelope.get("error") if type(envelope.get("error")) is dict else {}
        code = str(error.get("code") or "PACK_MODULE_FAILED")[:64]
        message = str(error.get("message") or "pack module failed")[:2000]
        return _failure(code, message)


def _failure(code: str, message: str) -> Dict[str, Any]:
    """The failure shape atomic modules return: ``ok`` false, message and code."""
    return {"ok": False, "error": message, "error_code": code}


def _proxy_class(pack_id: str, row: Mapping[str, Any]) -> type:
    name = "Pack_" + "".join(ch if ch.isalnum() else "_" for ch in row["module_id"])
    return type(
        name,
        (PackModule,),
        {
            "__doc__": f"{row['module_id']} from pack {pack_id}.",
            "__module__": __name__,
            "module_id": row["module_id"],
            "pack_id": pack_id,
            "_row_timeout_ms": row["timeout_ms"],
        },
    )


def _decorator_kwargs(row: Mapping[str, Any]) -> Dict[str, Any]:
    from ..modules.types import StabilityLevel

    return {
        "module_id": row["module_id"],
        "version": row["version"],
        "stability": StabilityLevel(row["stability"]),
        "category": row["category"],
        "subcategory": row["subcategory"],
        "tags": list(row["tags"]),
        "label": row["label"],
        "label_key": row["label_key"],
        "description": row["description"],
        "description_key": row["description_key"],
        "icon": row["icon"],
        "color": row["color"],
        "params_schema": row["params_schema"],
        "output_schema": row["output_schema"],
        "input_types": list(row["input_types"]),
        "output_types": list(row["output_types"]),
        "can_receive_from": list(row["can_receive_from"]),
        "can_connect_to": list(row["can_connect_to"]),
        "provides_capability": row["provides_capability"] or None,
        "contract": row["contract"],
        "required_permissions": list(row["required_permissions"]),
        "timeout_ms": row["timeout_ms"],
        "retryable": row["retryable"],
        "max_retries": row["max_retries"] if row["retryable"] else 3,
        "concurrent_safe": row["concurrent_safe"],
        "requires_credentials": row["requires_credentials"],
        "handles_sensitive_data": row["handles_sensitive_data"],
    }


class _PackEntryPoint:
    """Entry-point shaped handle ``ModuleRegistry.install_external_pack`` loads."""

    def __init__(self, manifest: Mapping[str, Any]):
        self.name = manifest["pack"]["id"]
        self.value = f"{PACK_SCHEMA}:{self.name}"
        self.pack_version = manifest["pack"]["version"]
        self.pack_description = manifest["pack"].get("description", "")
        self.pack_namespaces = tuple(manifest["pack"]["namespaces"])
        self._rows = [dict(row) for row in manifest["modules"]]

    def load(self):
        rows = self._rows
        pack_id = self.name
        namespaces = self.pack_namespaces

        def register_all() -> None:
            from ..modules.registry import ModuleRegistry, register_module

            _check_namespaces(ModuleRegistry, pack_id, namespaces)
            for row in rows:
                module_id = row["module_id"]
                if ModuleRegistry.has(module_id):
                    owner = (ModuleRegistry.get_metadata(module_id) or {}).get("plugin", "")
                    if owner != pack_id:
                        # Raising rolls the whole pack back: a pack does not
                        # get to replace flyto-core's module or another pack's.
                        raise ValueError(f"module id '{module_id}' is already registered by another owner")
                register_module(**_decorator_kwargs(row))(_proxy_class(pack_id, row))
            _check_capability_contracts(ModuleRegistry, pack_id, rows)

        return register_all


def _owner(metadata: Optional[Mapping[str, Any]]) -> str:
    return str((metadata or {}).get("plugin") or "")


def _check_namespaces(registry: Any, pack_id: str, namespaces: Tuple[str, ...]) -> None:
    """Refuse a namespace another owner already holds.

    The static deny list cannot name every namespace flyto-core ships
    (``capability`` is where ``capability.invoke`` lives) and cannot know the
    namespaces of installed Python packs at all. A namespace is held by
    whoever has a module in it, and by any other external pack that declared
    it — even one with no module there yet — so a third-party pack can neither
    publish ``capability.*`` beside the capability host nor add look-alike
    steps to another vendor's namespace.
    """
    wanted = set(namespaces)
    for module_id, metadata in list(registry._metadata.items()):
        if module_id.split(".", 1)[0] in wanted and _owner(metadata) != pack_id:
            raise ValueError("pack namespace is already held by another owner")
    for name, other in list(registry._external_packs.items()):
        if name != pack_id and wanted & set(getattr(other, "pack_namespaces", ())):
            raise ValueError("pack namespace is already declared by another pack")


def _check_capability_contracts(registry: Any, pack_id: str, rows: List[Dict[str, Any]]) -> None:
    """Refuse a capability whose meaning another owner already declared.

    The capability host resolves a capability's contract from every provider
    and fails closed when they disagree. A pack that declared an existing
    capability with a different contract — or with none — would therefore
    turn another vendor's ``role: safe_stop`` into an ambiguous, refused call:
    a stop that no longer stops. A second provider of the same capability is
    normal (two fleets can both stop a base), so it is allowed when its
    contract is exactly the one already declared.
    """
    for row in rows:
        capability = row.get("provides_capability") or ""
        if not capability:
            continue
        mine = (registry._metadata.get(row["module_id"]) or {}).get("contract")
        for metadata in list(registry._metadata.values()):
            declared = str((metadata or {}).get("provides_capability") or "").strip()
            if declared != capability or _owner(metadata) == pack_id:
                continue
            if metadata.get("contract") != mine:
                raise ValueError("capability is already declared by another owner with a different contract")


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------


def _host_version() -> str:
    try:
        from .. import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001
        return "unknown"


def _check_min_host(manifest: Mapping[str, Any]) -> None:
    wanted = manifest["pack"].get("min_host")
    if not wanted:
        return
    have = _host_version()

    def key(text: str) -> Tuple[int, ...]:
        core = text.split("+", 1)[0].split("-", 1)[0]
        try:
            return tuple(int(part) for part in core.split("."))
        except ValueError:
            return (0,)

    if have != "unknown" and key(have) < key(wanted):
        raise PackManifestError("HOST_TOO_OLD", "this flyto-core is older than the pack's min_host")


def install_pack(
    pack_dir: os.PathLike[str] | str,
    *,
    trusted_keys: Optional[Mapping[str, Any]] = None,
    require_signature: bool = True,
    provenance_dir: Optional[os.PathLike[str] | str] = None,
) -> PackProvenance:
    """Verify and install one pack directory. Returns its provenance record.

    ``require_signature`` defaults to True: an unsigned pack is refused unless
    the host opts out, and a signed one must verify against ``trusted_keys``.
    A signature that is present is always verified, even when not required.

    A subprocess pack runs from a host-private copy of its attested files,
    made in the same pass that computes the digest, so changing the source
    directory after install cannot change the code that is spawned later.

    Raises ``PackManifestError`` on any refusal; the registry, the plugin
    manager and the installed set are then unchanged.
    """
    with _INSTALL_LOCK:
        return _install_pack(
            pack_dir,
            trusted_keys=trusted_keys,
            require_signature=require_signature,
            provenance_dir=provenance_dir,
        )


def _install_pack(
    pack_dir: os.PathLike[str] | str,
    *,
    trusted_keys: Optional[Mapping[str, Any]],
    require_signature: bool,
    provenance_dir: Optional[os.PathLike[str] | str],
) -> PackProvenance:
    try:
        root = Path(pack_dir).resolve(strict=True)
    except OSError:
        raise PackManifestError("PACK_UNREADABLE", "pack directory is missing") from None
    manifest = read_pack_manifest(root)
    runtime = manifest["runtime"]
    if runtime["binding"] not in LOADABLE_BINDINGS:
        raise PackManifestError(
            "BINDING_NOT_LOADABLE",
            "inprocess-python packs load through their flyto.modules entry point",
        )
    _check_min_host(manifest)

    signature_doc = read_signature(root)
    signature: Optional[Dict[str, str]] = None
    if signature_doc is not None:
        signature = verify_manifest_signature(manifest, signature_doc, trusted_keys or {})
    elif require_signature:
        raise PackManifestError("UNSIGNED", "pack is not signed and the host requires a signature")

    pack_id = manifest["pack"]["id"]
    if pack_id in _INSTALLED:
        # Replacing a running pack in place would leave its old process
        # serving the old code under the new manifest; upgrade is explicit.
        raise PackManifestError("ALREADY_INSTALLED", "pack is already installed; uninstall it first")

    artifact_digest = manifest.get("artifact", {}).get("digest")
    staged: Optional[Path] = None
    try:
        if runtime["binding"] == "subprocess-jsonrpc":
            staged = Path(tempfile.mkdtemp(prefix="flyto-pack-")).resolve(strict=True)
            actual = stage_pack_tree(root, staged)
        else:
            actual = pack_tree_digest(root)
        if artifact_digest is not None and actual != artifact_digest:
            raise PackManifestError("DIGEST_MISMATCH", "pack files do not match artifact.digest")
        return _register_pack(manifest, root, staged, artifact_digest, signature, provenance_dir)
    except BaseException:
        installed = _INSTALLED.get(pack_id)
        # A failure after the pack went live (writing provenance) leaves it
        # installed, so its copy stays; any earlier refusal removes the copy.
        if staged is not None and (installed is None or installed.staged_dir != staged):
            shutil.rmtree(staged, ignore_errors=True)
        raise


def _register_pack(
    manifest: Dict[str, Any],
    root: Path,
    staged: Optional[Path],
    artifact_digest: Optional[str],
    signature: Optional[Dict[str, str]],
    provenance_dir: Optional[os.PathLike[str] | str],
) -> PackProvenance:
    runtime = manifest["runtime"]
    pack_id = manifest["pack"]["id"]
    timeout_ms = runtime["request_timeout_ms"]
    manager = None
    if runtime["binding"] == "subprocess-jsonrpc":
        manager = get_pack_plugin_manager()
        try:
            manager.register_pack(
                pack_id,
                staged,
                version=manifest["pack"]["version"],
                language=runtime["language"],
                entry=runtime["entry"],
                steps=[
                    {"id": row["module_id"], "required_permissions": list(row["required_permissions"])}
                    for row in manifest["modules"]
                ],
                env={"PYTHONDONTWRITEBYTECODE": "1"},
            )
        except Exception as exc:  # noqa: BLE001 - runtime validation errors carry no stable code
            raise PackManifestError("INVALID_RUNTIME", f"pack runtime is not usable: {type(exc).__name__}") from None
        transport: Any = _SubprocessTransport(pack_id, manager, timeout_ms)
    else:
        transport = _HttpTransport(
            manifest["pack"]["namespaces"][0], runtime["locality"], timeout_ms, runtime["max_response_bytes"]
        )

    from ..modules.registry import ModuleRegistry

    _INSTALLED[pack_id] = _InstalledPack(
        provenance=None, transport=transport, manifest=manifest, staged_dir=staged  # type: ignore[arg-type]
    )
    try:
        ModuleRegistry.install_external_pack(_PackEntryPoint(manifest))
    except ValueError:
        _INSTALLED.pop(pack_id, None)
        if manager is not None:
            manager._manifests.pop(pack_id, None)
            manager._manifest_paths.pop(pack_id, None)
        raise PackManifestError("REGISTRATION_FAILED", f"pack '{pack_id}' could not be registered") from None

    if manager is not None:
        _wire_invoker(manager)

    provenance = PackProvenance(
        pack_id=pack_id,
        version=manifest["pack"]["version"],
        binding=runtime["binding"],
        manifest_sha256=manifest_sha256(manifest),
        artifact_digest=artifact_digest,
        signature=signature,
        signature_verified=signature is not None,
        module_ids=tuple(row["module_id"] for row in manifest["modules"]),
        source=str(root),
        installed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        host_version=_host_version(),
    )
    _INSTALLED[pack_id].provenance = provenance
    if provenance_dir is not None:
        out = Path(provenance_dir)
        out.mkdir(parents=True, exist_ok=True)
        target = out / f"{pack_id}-{provenance.version}.json"
        target.write_text(json.dumps(provenance.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info(
        "Installed pack %s %s (%s, %d modules, signature %s)",
        pack_id,
        provenance.version,
        provenance.binding,
        len(provenance.module_ids),
        signature["key_id"] if signature else "none",
    )
    return provenance


async def uninstall_pack(pack_id: str) -> List[str]:
    """Remove a pack's modules from the registry and stop its process."""
    from ..modules.registry import ModuleRegistry

    removed = ModuleRegistry.uninstall_external_pack(pack_id)
    installed = _INSTALLED.pop(pack_id, None)
    if installed is not None:
        try:
            await installed.transport.close()
        finally:
            if installed.staged_dir is not None:
                shutil.rmtree(installed.staged_dir, ignore_errors=True)
    return removed


def installed_packs() -> Dict[str, PackProvenance]:
    """Provenance of every installed pack, by pack id."""
    return {pack_id: item.provenance for pack_id, item in _INSTALLED.items() if item.provenance is not None}
