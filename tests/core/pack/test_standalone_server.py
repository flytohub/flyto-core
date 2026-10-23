"""A connector pack served on its own as an MCP server, by core's one generic runtime.

Nothing here is written per provider: the tools, their annotations and their
calls come from the manifest. The end-to-end test runs the generated entry
point of a built zip as a subprocess and drives it as an MCP client over
stdio, against a loopback fake provider; the credential comes from the
environment by the name the pack declares.
"""

import json
import os
import subprocess
import sys
import threading

import aiohttp
import pytest
from portable_helpers import (
    IRREVERSIBLE_OP,
    LOCK,
    RECORDED,
    ROOT,
    TOKEN,
    Provider,
    declared_ids,
    entitled_ids,
    example_doc,
    example_source,
    start_provider,
)

from core.mcp_protocol import MODERN_PROTOCOL_VERSION
from core.pack.manifest import PackManifestError, validate_pack_manifest
from core.pack.portable import build_portable_pack, extract_pack_zip
from core.pack.standalone import health, load_standalone, start_http, tools_for
from core.pack.standalone_auth import KEYCHAIN_READERS, CredentialResolver

PYTHON = sys.executable


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


@pytest.fixture
def provider(monkeypatch):
    base_url, port, stop = start_provider()
    # The SSRF guard admits this loopback server only because the test says so.
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FLYTO_HTTP_ALLOWED_PORTS", str(port))
    yield base_url, port
    stop()


def build(tmp_path, base_url=None, mutate=None, name="ratings", **kwargs):
    out = tmp_path / f"{name}.zip"
    build_portable_pack(example_source(tmp_path, base_url=base_url, mutate=mutate, name=f"{name}-src"), out,
                        lockfile=LOCK, **kwargs)
    return out


def env_resolver(standalone, value=TOKEN):
    return CredentialResolver(standalone, env={"FLYTO_CREDENTIAL_RATINGS_API_TOKEN": value} if value else {},
                              keychain=lambda service, account: None)


# -- tools from the manifest ---------------------------------------------------------------


def test_each_operation_is_a_tool_annotated_from_its_consequence():
    def mutate(doc):
        doc["connector"]["operations"].append(IRREVERSIBLE_OP)
    tools = {tool["name"]: tool for tool in tools_for(validate_pack_manifest(example_doc(mutate)))}
    assert sorted(tools) == declared_ids(example_doc(mutate))
    assert "ratings.finding.dismiss" in tools
    observe = tools["ratings.company.get"]
    assert observe["annotations"]["readOnlyHint"] is True
    assert observe["annotations"]["destructiveHint"] is False
    assert observe["annotations"]["idempotentHint"] is True
    assert observe["annotations"]["openWorldHint"] is True
    assert observe["inputSchema"] == {
        "type": "object",
        "properties": {"company": {"type": "string", "description": "Company identifier"}},
        "required": ["company"],
        "additionalProperties": False,
    }
    irreversible = tools["ratings.finding.dismiss"]
    assert irreversible["annotations"]["readOnlyHint"] is False
    assert irreversible["annotations"]["destructiveHint"] is True
    assert irreversible["annotations"]["idempotentHint"] is False
    assert tools["ratings.findings.list"]["inputSchema"]["required"] == ["company"]


def test_the_annotation_table_covers_every_consequence():
    from core.pack.connector import CONSEQUENCE_ANNOTATIONS, CONSEQUENCES

    assert set(CONSEQUENCE_ANNOTATIONS) == set(CONSEQUENCES)
    assert CONSEQUENCE_ANNOTATIONS["observe"]["readOnlyHint"] is True
    assert all(not row["readOnlyHint"] for level, row in CONSEQUENCE_ANNOTATIONS.items() if level != "observe")
    assert CONSEQUENCE_ANNOTATIONS["irreversible"]["destructiveHint"] is True


# -- in process ------------------------------------------------------------------------------


async def test_tools_list_and_call_in_process(tmp_path, provider, host_version_241):
    base_url, _ = provider
    out = build(tmp_path, base_url)
    pack = load_standalone(out, transport="stdio", require_signature=False,
                           resolver_factory=env_resolver)
    try:
        listed = await pack.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert [tool["name"] for tool in listed["result"]["tools"]] == entitled_ids(example_doc(),
                                                                                   Provider.customer)
        called = await pack.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": "ratings.company.get", "arguments": {"company": "c-1"}}})
        body = called["result"]
        assert body["isError"] is False
        content = body["structuredContent"]
        assert (content["ok"], content["data"]) == (True, RECORDED["company"])
        # Listed first, so the call is admitted on the cached probe answer, under the standalone "*" grant.
        assert content["metadata"]["precheck"]["entitlements"] == "cache"
        assert content["metadata"]["precheck"]["scope"] == {"dimension": "company", "kept": 1, "dropped": 0}
        assert Provider.seen[-1]["auth"].startswith("Basic ")
    finally:
        await pack.close()


async def test_a_credential_entitled_to_fewer_features_lists_fewer_tools(tmp_path, provider, host_version_241):
    base_url, _ = provider
    Provider.customer = "ratings_only"
    expected = entitled_ids(example_doc(), "ratings_only")
    assert expected != declared_ids(example_doc())  # the example has a tool this customer does not hold
    pack = load_standalone(build(tmp_path, base_url), transport="stdio", require_signature=False,
                           resolver_factory=env_resolver)
    try:
        listed = await pack.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert [tool["name"] for tool in listed["result"]["tools"]] == expected
        hidden = sorted(set(declared_ids(example_doc())) - set(expected))
        # Hidden is not unreachable: a call still goes through the gate, which refuses it typed.
        called = await pack.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": hidden[0], "arguments": {"company": "c-1"}}})
        assert called["result"]["isError"] is True
        assert called["result"]["structuredContent"]["error_code"] == "FEATURE_NOT_ENTITLED"
    finally:
        await pack.close()


async def test_an_unreadable_probe_lists_only_the_ungated_tools(tmp_path, provider, host_version_241):
    base_url, _ = provider
    Provider.customer = None
    pack = load_standalone(build(tmp_path, base_url), transport="stdio", require_signature=False,
                           resolver_factory=env_resolver)
    try:
        listed = await pack.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [tool["name"] for tool in listed["result"]["tools"]]
        assert names == entitled_ids(example_doc(), None)
        probe = "ratings." + example_doc()["entitlements"]["probe"]
        assert probe in names  # the probe is an ungated observe operation, so it stays a tool
        called = await pack.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": "ratings.company.get", "arguments": {"company": "c-1"}}})
        assert called["result"]["isError"] is True
        assert called["result"]["structuredContent"]["error_code"] == "PROVIDER_ENTITLEMENT_UNREADABLE"
        assert all(seen["path"] != "/v1/companies/c-1" for seen in Provider.seen)
    finally:
        await pack.close()


async def test_a_call_without_the_credential_fails_typed_and_sends_nothing(tmp_path, provider, host_version_241):
    base_url, _ = provider
    out = build(tmp_path, base_url)
    pack = load_standalone(out, transport="stdio", require_signature=False,
                           resolver_factory=lambda standalone: env_resolver(standalone, value=None))
    try:
        called = await pack.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": "ratings.company.get", "arguments": {"company": "c-1"}}})
        assert called["result"]["isError"] is True
        assert called["result"]["structuredContent"]["error_code"] == "CREDENTIAL_MISSING"
        assert Provider.seen == []
    finally:
        await pack.close()


async def test_an_unknown_tool_is_a_protocol_error(tmp_path, host_version_241):
    pack = load_standalone(build(tmp_path), transport="stdio", require_signature=False,
                           resolver_factory=env_resolver)
    try:
        answer = await pack.dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                      "params": {"name": "execute_module", "arguments": {}}})
        assert answer["error"]["code"] == -32601
    finally:
        await pack.close()


async def test_modern_protocol_requests_are_served(tmp_path, provider, host_version_241):
    base_url, _ = provider
    pack = load_standalone(build(tmp_path, base_url), transport="stdio", require_signature=False,
                           resolver_factory=env_resolver)
    try:
        meta = {"io.modelcontextprotocol/protocolVersion": MODERN_PROTOCOL_VERSION,
                "io.modelcontextprotocol/clientCapabilities": {}}
        answer = await pack.dispatch({"jsonrpc": "2.0", "id": 1, "method": "server/discover",
                                      "params": {"_meta": meta}})
        assert answer["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "com.example.ratings"
        listed = await pack.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                                      "params": {"_meta": meta}})
        # The list depends on the credential, so it carries no public cache hint.
        assert "cacheScope" not in listed["result"] and "ttlMs" not in listed["result"]
    finally:
        await pack.close()


def test_a_transport_the_pack_does_not_declare_is_refused(tmp_path, host_version_241):
    def mutate(doc):
        doc["standalone"]["transports"] = ["stdio"]
    out = build(tmp_path, mutate=mutate)
    assert code_of(lambda: load_standalone(out, transport="streamable_http", require_signature=False)) \
        == "TRANSPORT_NOT_DECLARED"


def test_an_unsigned_pack_needs_an_explicit_allow(tmp_path, host_version_241):
    assert code_of(lambda: load_standalone(build(tmp_path), transport="stdio")) == "UNSIGNED"


def test_a_pack_without_a_standalone_section_does_not_run_standalone(tmp_path, host_version_241):
    from pack_helpers import write_pack

    pack_dir, _ = write_pack(tmp_path / "proc")
    assert code_of(lambda: load_standalone(pack_dir, transport="stdio", require_signature=False)) \
        == "STANDALONE_MISSING"


# -- credentials -------------------------------------------------------------------------------


def test_credentials_come_from_env_then_the_os_keychain_by_name():
    standalone = validate_pack_manifest(example_doc())["standalone"]
    asked = []

    def keychain(service, account):
        asked.append((service, account))
        return "from-keychain"

    resolver = CredentialResolver(standalone, env={}, keychain=keychain)
    assert resolver.resolve() == {"ratings_api_token": "from-keychain"}
    assert asked == [("flyto.pack.com.example.ratings", "ratings_api_token")]
    assert resolver.status() == [{"name": "ratings_api_token", "source": "keychain"}]
    env_first = CredentialResolver(standalone, env={"FLYTO_CREDENTIAL_RATINGS_API_TOKEN": "from-env"},
                                   keychain=keychain)
    assert env_first.resolve() == {"ratings_api_token": "from-env"}
    nothing = CredentialResolver(standalone, env={}, keychain=lambda service, account: None)
    assert nothing.resolve() == {} and nothing.status() == [{"name": "ratings_api_token", "source": "missing"}]
    env_only = CredentialResolver(standalone, env={"FLYTO_PACK_NO_KEYCHAIN": "1"}, keychain=keychain)
    asked.clear()
    assert env_only.resolve() == {} and asked == []


def test_the_keychain_readers_are_a_table_of_os_commands(monkeypatch):
    from core.pack import standalone_auth as credentials

    assert KEYCHAIN_READERS["darwin"][:2] == ("security", "find-generic-password")
    assert KEYCHAIN_READERS["linux"][:2] == ("secret-tool", "lookup")
    calls = []

    class Done:
        returncode = 0
        stdout = "secret-from-os\n"

    def fake_run(argv, **kwargs):
        calls.append(argv)
        assert kwargs.get("shell") is not True
        return Done()

    value = credentials.read_keychain("flyto.pack.x", "name", platform="darwin", run=fake_run)
    assert value == "secret-from-os"
    assert calls == [["security", "find-generic-password", "-s", "flyto.pack.x", "-a", "name", "-w"]]

    class Missing:
        returncode = 44
        stdout = ""

    assert credentials.read_keychain("flyto.pack.x", "name", platform="linux", run=lambda argv, **k: Missing()) is None
    assert credentials.read_keychain("flyto.pack.x", "name", platform="plan9", run=fake_run) is None


def test_health_reports_names_never_values(tmp_path, provider, host_version_241):
    base_url, _ = provider
    out = build(tmp_path, base_url)
    report = health(out, require_signature=False, resolver_factory=lambda s: env_resolver(s, value="s3cr3t-value"))
    assert report["healthy"] is True
    assert report["credentials"] == [{"name": "ratings_api_token", "source": "env"}]
    assert report["tools"] == len(declared_ids(example_doc()))
    assert report["runtime"]["satisfied"] is True
    assert "s3cr3t-value" not in json.dumps(report)
    missing = health(out, require_signature=False, resolver_factory=lambda s: env_resolver(s, value=None))
    assert missing["healthy"] is False
    assert missing["problems"] == ["CREDENTIAL_MISSING"]
    assert missing["entitled_tools"] == len(entitled_ids(example_doc(), None))
    assert missing["entitlements"] == {"source": "unreadable", "error_code": "CREDENTIAL_MISSING"}


@pytest.mark.parametrize("customer", ["ratings_only", "ratings_and_monitoring", None])
def test_health_reports_the_entitled_count(tmp_path, provider, host_version_241, customer):
    base_url, _ = provider
    Provider.customer = customer
    report = health(build(tmp_path, base_url), require_signature=False, resolver_factory=env_resolver)
    assert report["tools"] == len(declared_ids(example_doc()))
    assert report["entitled_tools"] == len(entitled_ids(example_doc(), customer))
    if customer is None:
        assert report["entitlements"] == {"source": "unreadable", "error_code": "PROVIDER_ENTITLEMENT_UNREADABLE"}
        assert report["problems"] == ["PROVIDER_ENTITLEMENT_UNREADABLE"]
    else:
        assert report["entitlements"] == {"source": "provider"}
        assert report["healthy"] is True


# -- over Streamable HTTP ------------------------------------------------------------------------


async def test_streamable_http_needs_the_token_and_serves_the_tools(tmp_path, provider, host_version_241):
    base_url, _ = provider
    out = build(tmp_path, base_url)
    pack = load_standalone(out, transport="streamable_http", require_signature=False,
                           resolver_factory=env_resolver)
    runner, port = await start_http(pack, host="127.0.0.1", port=0, token="t" * 40)
    url = f"http://127.0.0.1:{port}/mcp"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                    headers=headers) as response:
                assert response.status == 401
            authorized = {**headers, "Authorization": "Bearer " + "t" * 40}
            async with session.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                    headers={**authorized, "Origin": "https://evil.example"}) as response:
                assert response.status == 403
            async with session.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                               "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                                    headers=authorized) as response:
                assert response.status == 200
                assert response.headers.get("Mcp-Session-Id")
            async with session.post(url, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                               "params": {"name": "ratings.portfolio.list", "arguments": {}}},
                                    headers=authorized) as response:
                body = await response.json()
                content = body["result"]["structuredContent"]
                assert (content["ok"], content["data"]) == (True, RECORDED["portfolio"])
                assert content["metadata"]["precheck"]["entitlements"] == "provider"
            async with session.get(url, headers=authorized) as response:
                assert response.status == 405
    finally:
        await runner.cleanup()
        await pack.close()


async def test_http_refuses_to_bind_beyond_loopback(tmp_path, host_version_241):
    pack = load_standalone(build(tmp_path), transport="streamable_http", require_signature=False,
                           resolver_factory=env_resolver)
    try:
        with pytest.raises(PackManifestError) as info:
            await start_http(pack, host="0.0.0.0", port=0, token="t" * 40)
        assert info.value.code == "HTTP_BIND_REFUSED"
        with pytest.raises(PackManifestError) as info:
            await start_http(pack, host="127.0.0.1", port=0, token="short")
        assert info.value.code == "HTTP_TOKEN_WEAK"
    finally:
        await pack.close()


# -- the proof: the generated entry point, as a subprocess, over stdio --------------------------------


def _platform():
    return {"darwin": "macos", "linux": "linux"}.get(sys.platform)


class StdioClient:
    def __init__(self, process):
        self.process = process
        self.lines = []
        self._ready = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.process.stdout:
            with self._ready:
                self.lines.append(line)
                self._ready.notify_all()

    def request(self, message, timeout=60):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        if "id" not in message:
            return None
        with self._ready:
            ok = self._ready.wait_for(lambda: self.lines, timeout=timeout)
            assert ok, "the server did not answer"
            return json.loads(self.lines.pop(0))


@pytest.mark.skipif(_platform() is None, reason="the posix entry points run on macOS and Linux")
def test_the_built_zip_runs_standalone_over_stdio_through_its_generated_entry_point(tmp_path, provider):
    base_url, port = provider
    out = build(tmp_path, base_url)
    pack_dir = tmp_path / "installed-pack"
    pack_dir.mkdir()
    extract_pack_zip(out, pack_dir)

    # What the generated install step would leave: a venv whose `flyto` is
    # this checkout's CLI (the install step itself needs the network).
    home = tmp_path / "pack-home"
    venv_bin = home / "com.example.ratings" / "0.1.0" / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    shim = venv_bin / "flyto"
    shim.write_text(f'#!/bin/sh\nexec "{PYTHON}" -m cli.main "$@"\n', encoding="utf-8")
    shim.chmod(0o755)

    entry = json.loads((pack_dir / "flyto-pack.json").read_text())  # raw; the normalized one is derived
    standalone = validate_pack_manifest(entry)["standalone"]
    command = standalone["entry_points"][_platform()]["serve"]["stdio"] + ["--allow-unsigned"]
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "PYTHONPATH": str(ROOT / "src"),
        "FLYTO_PACK_HOME": str(home),
        "FLYTO_CREDENTIAL_RATINGS_API_TOKEN": TOKEN,
        "FLYTO_PACK_NO_KEYCHAIN": "1",
        "FLYTO_ALLOWED_HOSTS": "127.0.0.1",
        "FLYTO_HTTP_ALLOWED_PORTS": str(port),
    }
    process = subprocess.Popen(command, cwd=pack_dir, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        client = StdioClient(process)
        init = client.request({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                          "clientInfo": {"name": "test", "version": "1"}}})
        assert init["result"]["serverInfo"]["name"] == "com.example.ratings", process.stderr
        client.request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        listed = client.request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        assert sorted(tools) == entitled_ids(entry, Provider.customer)
        from core.pack.connector import CONSEQUENCE_ANNOTATIONS

        consequence = {f"ratings.{op['id']}": op["consequence"] for op in entry["connector"]["operations"]}
        for name, tool in tools.items():
            assert tool["annotations"]["readOnlyHint"] is CONSEQUENCE_ANNOTATIONS[consequence[name]]["readOnlyHint"]
        called = client.request({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                 "params": {"name": "ratings.company.get", "arguments": {"company": "c-1"}}})
        assert called["result"]["isError"] is False
        content = called["result"]["structuredContent"]
        assert (content["ok"], content["data"]) == (True, RECORDED["company"])
        assert Provider.seen[-1]["path"] == "/v1/companies/c-1"
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
        stderr = process.stderr.read()
        process.stderr.close()
        process.stdout.close()
    assert TOKEN not in stderr
    assert process.returncode == 0, stderr

