# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""One generic runtime that serves any portable connector pack as an MCP server.

Nothing is generated or written per provider. Given a pack (a built zip or
its directory), this module:

1. checks the pack declares the requested transport, then verifies it the
   way a host does — revocation list first, then ``artifact.digest``, the
   portable tree (lockfile, entry points) and the publisher signature;
2. installs it with ``core.pack.host.install_pack`` — the very call a Flyto2
   Space makes — so each operation is the same registered module, under the
   same policy gate, in both places;
3. serves the pack's operations as MCP tools over stdio or Streamable HTTP
   with ``core.mcp_protocol``, the protocol code core's own MCP server uses.
   ``tools/list`` comes from the manifest: each tool's annotations from its
   operation's consequence (``connector.CONSEQUENCE_ANNOTATIONS``). It lists
   exactly the operations the running credential is entitled to, by
   ``core.pack.host.entitled_listing`` — the listing a Space uses, through
   the same probe and cache as every call. An unreadable probe lists only the
   ungated operations.
   ``tools/call`` runs the module through ``core.mcp_handler.execute_module``
   with the credentials resolved by name for that call
   (``core.pack.standalone_auth``), and returns the connector runtime's result
   or its typed failure (``CREDENTIAL_MISSING``, ``FEATURE_NOT_ENTITLED``,
   ``PROVIDER_*``) unchanged. Every declared operation stays callable: a
   hidden one is refused by the gate, typed, not by the listing.

Standalone, the person running the server holds the provider credential and
there is no Flyto2 member to narrow for, so each call carries an explicit
``ScopeGrants`` of ``"*"`` for every scope dimension the pack declares
(``standalone_scope_grants``). The provider's own access control decides
what that credential sees.

The HTTP transport binds a loopback address only and needs a bearer token on
every request; a browser ``Origin`` other than loopback is refused, so a web
page cannot reach the user's credentials through it.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .. import mcp_protocol
from .manifest import PackManifestError, read_pack_manifest

logger = logging.getLogger(__name__)

__all__ = ["StandalonePack", "tools_for", "standalone_scope_grants", "load_standalone", "serve_stdio", "start_http", "serve_http", "health"]

#: Keys of a registry parameter definition -> their JSON Schema names.
_SCHEMA_KEYS: Mapping[str, str] = {
    "type": "type", "description": "description", "label": "title", "enum": "enum", "default": "default",
    "min": "minimum", "max": "maximum", "minLength": "minLength", "maxLength": "maxLength",
    "pattern": "pattern", "items": "items", "format": "format",
}
_LOOPBACK_NAMES = frozenset({"localhost"})
_MIN_TOKEN_LENGTH = 32
_MAX_HTTP_BODY = 1024 * 1024


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


def _input_schema(params_schema: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    properties = {
        name: {_SCHEMA_KEYS[key]: value for key, value in spec.items() if key in _SCHEMA_KEYS}
        for name, spec in params_schema.items()
    }
    required = sorted(name for name, spec in params_schema.items() if spec.get("required") is True)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def tools_for(manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The MCP tools a connector pack's manifest declares, in module-id order."""
    from .connector import CONSEQUENCE_ANNOTATIONS, module_id_for

    namespace = manifest["pack"]["namespaces"][0]
    operations = {module_id_for(namespace, op["id"]): op for op in manifest["connector"]["operations"]}
    tools = []
    for row in manifest["modules"]:
        op = operations[row["module_id"]]
        label = row["label"] if isinstance(row["label"], str) else row["module_id"]
        description = row["description"] if isinstance(row["description"], str) else label
        tools.append({
            "name": row["module_id"],
            "title": label,
            "description": description,
            "inputSchema": _input_schema(row["params_schema"]),
            "annotations": {"title": label, **CONSEQUENCE_ANNOTATIONS[op["consequence"]]},
        })
    return tools


def standalone_scope_grants(manifest: Mapping[str, Any]) -> Any:
    """Every declared scope dimension granted ``"*"``: standalone, the credential holder is the caller."""
    from .connector_gate import ALL_VALUES, ScopeGrants

    return ScopeGrants({scope["key"]: ALL_VALUES for scope in manifest.get("scopes") or []})


@dataclass
class StandalonePack:
    """One verified, installed pack and the MCP server that serves it."""

    manifest: Dict[str, Any]
    root: Path
    transport: str
    verification: Dict[str, Any]
    resolver: Any
    _scratch: Optional[Path] = None
    _tools: List[Dict[str, Any]] = field(default_factory=list)
    _closed: bool = False

    def __post_init__(self) -> None:
        self._tools = tools_for(self.manifest)
        self._names = frozenset(tool["name"] for tool in self._tools)
        self._grants = standalone_scope_grants(self.manifest)
        pack = self.manifest["pack"]
        self.server = mcp_protocol.McpServer(
            server_info=lambda: {
                "name": pack["id"],
                "title": pack.get("title", pack["id"]),
                "version": pack["version"],
                "description": pack.get("description", ""),
            },
            instructions=pack.get("description") or f"The operations of {pack['id']} as tools.",
            list_tools=self.list_tools,
            call_tool=self._call_tool,
            tools_list_public=False,
        )

    async def listing(self) -> Any:
        """What the running credential is entitled to (``connector_gate.EntitledListing``)."""
        from .host import entitled_listing

        return await entitled_listing(self.manifest["pack"]["id"], self.resolver.resolve())

    async def list_tools(self) -> List[Dict[str, Any]]:
        """The declared tools the running credential is entitled to, in declared order."""
        offered = frozenset((await self.listing()).module_ids)
        return [tool for tool in self._tools if tool["name"] in offered]

    async def _call_tool(self, request_id: Any, params: Any, modern: bool) -> Dict[str, Any]:
        from ..mcp_handler import execute_module

        def result(body: Dict[str, Any]) -> Dict[str, Any]:
            return mcp_protocol.jsonrpc_result(request_id, body, modern=modern, server_info=self.server.server_info)

        if not isinstance(params, dict):
            return mcp_protocol.jsonrpc_error(request_id, -32602, "Request params must be an object")
        name, arguments = params.get("name"), params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return mcp_protocol.jsonrpc_error(
                request_id, -32602, "Tool name must be a string and arguments must be an object"
            )
        if name not in self._names:
            return mcp_protocol.jsonrpc_error(request_id, -32601, f"Unknown tool: {name}")
        try:
            # Resolved per call, by name: a keychain change applies to the next
            # call, and no value outlives the call that needed it.
            outcome = await execute_module(name, dict(arguments), context={"secrets": self.resolver.resolve(), "scope_grants": self._grants})
        except Exception as exc:  # noqa: BLE001 - a failed call is a tool error, not a dead server
            return result({"content": [{"type": "text", "text": f"{type(exc).__name__}"}], "isError": True})
        return result(mcp_protocol.tool_call_body(outcome))

    async def dispatch(self, request: dict) -> Optional[dict]:
        return await mcp_protocol.dispatch_jsonrpc(self.server, request)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        from .host import uninstall_pack

        try:
            await uninstall_pack(self.manifest["pack"]["id"])
        finally:
            if self._scratch is not None:
                shutil.rmtree(self._scratch, ignore_errors=True)


def _unpack(source: Path) -> Tuple[Path, Optional[Path]]:
    from .portable import extract_pack_zip

    if source.is_dir():
        return source, None
    if not source.is_file():
        _fail("PACK_UNREADABLE", "the pack is neither a directory nor a file")
    scratch = Path(tempfile.mkdtemp(prefix="flyto-pack-run-"))
    try:
        extract_pack_zip(source, scratch)
    except BaseException:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    return scratch, scratch


def load_standalone(
    source: os.PathLike[str] | str,
    *,
    transport: Optional[str],
    trusted_keys: Optional[Mapping[str, Any]] = None,
    require_signature: bool = True,
    revocations: Any = None,
    resolver_factory: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> StandalonePack:
    """Verify and install a portable pack for standalone serving; refuses with a typed reason.

    ``transport`` ``None`` takes the first one the pack declares.
    """
    from .host import install_pack
    from .portable import STANDALONE_TRANSPORTS, verify_pack_dir
    from .standalone_auth import CredentialResolver

    if transport is not None and transport not in STANDALONE_TRANSPORTS:
        _fail("TRANSPORT_UNKNOWN", f"transport is one of {', '.join(STANDALONE_TRANSPORTS)}")
    root, scratch = _unpack(Path(source))
    try:
        manifest = read_pack_manifest(root)
        if "standalone" not in manifest:
            _fail("STANDALONE_MISSING", "this pack has no standalone section; it runs only inside a host")
        transport = transport or manifest["standalone"]["transports"][0]
        if transport not in manifest["standalone"]["transports"]:
            _fail("TRANSPORT_NOT_DECLARED", f"the pack does not declare the {transport} transport")
        verification = verify_pack_dir(root, trusted_keys=trusted_keys, require_signature=require_signature,
                                       revocations=revocations)
        install_pack(root, trusted_keys=trusted_keys, require_signature=require_signature, revocations=revocations)
        factory = resolver_factory or (lambda standalone: CredentialResolver(standalone))
        return StandalonePack(manifest=manifest, root=root, transport=transport, verification=verification,
                              resolver=factory(manifest["standalone"]), _scratch=scratch)
    except BaseException:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------


async def serve_stdio(pack: StandalonePack) -> None:
    """Serve over stdio until EOF. Only JSON-RPC reaches stdout; anything else printed goes to stderr."""
    out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    real_stdout, sys.stdout = sys.stdout, sys.stderr

    def write_line(text: str) -> None:
        out.write(text + "\n")
        out.flush()

    try:
        await mcp_protocol.serve_stdio(pack.dispatch, read_line=sys.stdin.readline, write_line=write_line)
    finally:
        sys.stdout = real_stdout
        out.close()


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _origin_allowed(origin: Optional[str]) -> bool:
    if origin is None:
        return True
    return _is_loopback(urlsplit(origin).hostname or "")


async def start_http(pack: StandalonePack, *, host: str, port: int, token: str) -> Tuple[Any, int]:
    """Start Streamable HTTP at ``http://host:port/mcp``; returns ``(runner, bound port)``."""
    from aiohttp import web

    if not _is_loopback(host):
        _fail("HTTP_BIND_REFUSED", "the standalone server listens on a loopback address only")
    if type(token) is not str or len(token) < _MIN_TOKEN_LENGTH:
        _fail("HTTP_TOKEN_WEAK", f"the bearer token must be at least {_MIN_TOKEN_LENGTH} characters")
    expected = f"Bearer {token}".encode("utf-8")
    sessions: Dict[str, dict] = {}

    def refused(request: Any) -> Optional[Any]:
        supplied = request.headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(supplied, expected):
            return web.json_response({"error": "unauthorized"}, status=401)
        if not _origin_allowed(request.headers.get("Origin")):
            return web.json_response({"error": "origin not allowed"}, status=403)
        return None

    async def post(request: Any) -> Any:
        denial = refused(request)
        if denial is not None:
            return denial
        raw = await request.read()
        try:
            body: Any = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            body = mcp_protocol.PARSE_ERROR
        status, content, headers = await mcp_protocol.handle_http_post(request.headers, body, pack.dispatch,
                                                                       sessions)
        if content is None:
            return web.Response(status=status)
        return web.json_response(content, status=status, headers=headers)

    async def get(request: Any) -> Any:
        return web.json_response({"error": "Server-initiated SSE not supported. Use POST for JSON-RPC requests."},
                                 status=405)

    async def delete(request: Any) -> Any:
        denial = refused(request)
        if denial is not None:
            return denial
        if sessions.pop(request.headers.get("Mcp-Session-Id", ""), None) is None:
            return web.json_response({"error": "Session not found"}, status=404)
        return web.Response(status=200)

    app = web.Application(client_max_size=_MAX_HTTP_BODY)
    app.router.add_post("/mcp", post)
    app.router.add_get("/mcp", get)
    app.router.add_delete("/mcp", delete)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    bound = runner.addresses[0][1]
    return runner, bound


async def serve_http(pack: StandalonePack, *, host: str, port: int, token: str) -> None:
    """Serve Streamable HTTP until cancelled."""
    import asyncio

    runner, bound = await start_http(pack, host=host, port=port, token=token)
    print(f"{pack.manifest['pack']['id']} serving MCP at http://{host}:{bound}/mcp", file=sys.stderr, flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------


async def _health(pack: StandalonePack) -> Dict[str, Any]:
    from .portable import _python_floor

    standalone = pack.manifest["standalone"]
    floor = _python_floor(standalone["runtime"]["version"])
    tools = len(pack._tools)
    listing = await pack.listing()
    credentials = pack.resolver.status()
    problems = []
    if sys.version_info[:2] < floor:
        problems.append("RUNTIME_TOO_OLD")
    if standalone["credentials_needed"] == "one_of" and all(item["source"] == "missing" for item in credentials):
        problems.append("CREDENTIAL_MISSING")
    if tools != len(pack.manifest["connector"]["operations"]):
        problems.append("TOOLS_INCOMPLETE")
    if listing.error_code == "PROVIDER_ENTITLEMENT_UNREADABLE":
        problems.append("PROVIDER_ENTITLEMENT_UNREADABLE")
    return {
        "healthy": not problems,
        "problems": problems,
        "pack_id": pack.manifest["pack"]["id"],
        "version": pack.manifest["pack"]["version"],
        "verification": pack.verification,
        "runtime": {"language": "python", "required": standalone["runtime"]["version"],
                    "running": ".".join(map(str, sys.version_info[:3])), "satisfied": sys.version_info[:2] >= floor},
        "credentials": credentials,
        "transports": standalone["transports"],
        "tools": tools,
        "entitled_tools": len(listing.module_ids),
        "entitlements": listing.status(),
    }


def health(
    source: os.PathLike[str] | str,
    *,
    trusted_keys: Optional[Mapping[str, Any]] = None,
    require_signature: bool = True,
    revocations: Any = None,
    resolver_factory: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    """Verify, install and list a pack without serving it.

    The only provider request is the entitlements probe (an observe
    operation), so the report can count the tools the credential is entitled
    to. The report names each credential and where it would come from, never
    its value.
    """
    import asyncio

    pack = load_standalone(source, transport=None, trusted_keys=trusted_keys,
                           require_signature=require_signature, revocations=revocations,
                           resolver_factory=resolver_factory)

    async def run() -> Dict[str, Any]:
        try:
            return await _health(pack)
        finally:
            await pack.close()

    return asyncio.run(run())
