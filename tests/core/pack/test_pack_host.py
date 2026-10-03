"""Installing an out-of-process flyto.pack.v1 pack into the module registry.

The pack here is a stdlib-only Python subprocess speaking JSON-RPC, so the
whole path — manifest, digest, signature, registry transaction, policy gate,
PluginManager, RuntimeInvoker — runs without Node.
"""

import json

import pytest
from pack_helpers import module_row, write_pack

from core.modules.registry import ModuleRegistry
from core.pack import host
from core.pack.host import install_pack, installed_packs, uninstall_pack
from core.pack.manifest import PackManifestError

CONTRACT = {
    "actuates": False,
    "safety_class": "read_only",
    "requires_safe_stop": False,
    "cancellable": True,
    "idempotent": True,
}


def signed_pack(tmp_path, keypair, **kwargs):
    private, public = keypair
    pack, manifest = write_pack(tmp_path / "pack", sign_with=private, **kwargs)
    return pack, manifest, {"test-key": public}


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


async def run(module_id, params, context=None):
    module = ModuleRegistry.get(module_id)(params, context or {})
    return await module.run()


async def test_signed_pack_registers_like_a_python_module(tmp_path, keypair):
    modules = [
        module_row("fake.echo", provides_capability="fake.echo", contract=CONTRACT),
        module_row("fake.fail"),
    ]
    pack, _, keys = signed_pack(tmp_path, keypair, modules=modules, description="A fake pack")
    provenance = install_pack(pack, trusted_keys=keys)

    assert provenance.signature_verified is True
    assert provenance.signature["key_id"] == "test-key"
    assert provenance.module_ids == ("fake.echo", "fake.fail")

    meta = ModuleRegistry.get_metadata("fake.echo")
    # Ownership is stamped by the registry, never claimed by the pack.
    assert meta["plugin"] == "com.example.fake"
    assert meta["contract"]["schema"] == "flyto.capability-contract.v1"
    assert meta["params_schema"]["text"]["type"] == "string"
    assert ModuleRegistry.capabilities()["fake.echo"] == ["fake.echo"]

    info = ModuleRegistry.get_plugins()["com.example.fake"]
    assert info.version == "0.1.0"
    assert info.description == "A fake pack"
    assert info.module_count == 2


async def test_pack_appears_in_manifest_catalog_and_mcp(tmp_path, keypair):
    from core.capability_manifest import get_capability_manifest
    from core.catalog.module import get_module_detail, search_modules
    from core.mcp_handler import get_module_info

    modules = [module_row("fake.echo", provides_capability="fake.echo", contract=CONTRACT)]
    pack, _, keys = signed_pack(tmp_path, keypair, modules=modules)
    install_pack(pack, trusted_keys=keys)

    manifest = get_capability_manifest()
    assert "fake.echo" in manifest["modules"]
    assert manifest["contracts"]["fake.echo"]["module_id"] == "fake.echo"
    entry = next(p for p in manifest["plugins"] if p["id"] == "com.example.fake")
    assert entry["module_ids"] == ["fake.echo"]

    detail = get_module_detail("fake.echo")
    assert detail is not None and detail["params_schema"]["text"]["label"] == "Text"
    assert any(r.get("module_id") == "fake.echo" for r in search_modules("fake echo"))
    info = get_module_info("fake.echo")
    assert "error" not in info


async def test_module_runs_through_the_subprocess(tmp_path, keypair):
    pack, _, keys = signed_pack(tmp_path, keypair, modules=[module_row("fake.echo"), module_row("fake.fail")])
    install_pack(pack, trusted_keys=keys)

    result = await run("fake.echo", {"text": "hi"}, {"execution_id": "exec-1", "secrets": {"API": "s3cret"}})
    assert result["ok"] is True
    assert result["data"]["input"] == {"text": "hi"}
    # The foreign process sees identifiers only — never the execution context.
    assert result["data"]["context"] == {
        "pack_id": "com.example.fake",
        "module_id": "fake.echo",
        "execution_id": "exec-1",
    }

    failed = await run("fake.fail", {"text": "x"})
    assert failed == {"ok": False, "error": "refused by the pack", "error_code": "NOPE"}


async def test_reply_without_boolean_ok_is_a_failure(tmp_path, keypair):
    pack, _, keys = signed_pack(tmp_path, keypair, modules=[module_row("fake.noflag")])
    install_pack(pack, trusted_keys=keys)
    result = await run("fake.noflag", {"text": "x"})
    assert result["ok"] is False and result["error_code"] == "PACK_PROTOCOL_ERROR"


async def test_params_are_validated_before_leaving_the_process(tmp_path, keypair):
    row = module_row("fake.echo")
    row["params_schema"] = {"count": {"type": "integer", "label": "Count", "description": "n", "required": True}}
    pack, _, keys = signed_pack(tmp_path, keypair, modules=[row])
    install_pack(pack, trusted_keys=keys)
    with pytest.raises(ValueError):
        ModuleRegistry.get("fake.echo")({}, {})


async def test_policy_gate_applies_with_the_pack_as_owner(tmp_path, keypair, monkeypatch):
    from core.module_policy import ModulePolicyError

    row = module_row("fake.echo", required_permissions=["shell.execute"])
    pack, _, keys = signed_pack(tmp_path, keypair, modules=[row])
    install_pack(pack, trusted_keys=keys)

    # The process-global grant does not reach a plugin module.
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")
    with pytest.raises(ModulePolicyError):
        await run("fake.echo", {"text": "x"})

    monkeypatch.setenv("FLYTO_PLUGIN_GRANTS", "com.example.fake:shell.execute")
    assert (await run("fake.echo", {"text": "x"}))["ok"] is True

    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "com.example.fake")
    with pytest.raises(ModulePolicyError):
        await run("fake.echo", {"text": "x"})


async def test_unsigned_pack_is_refused_unless_allowed(tmp_path):
    pack, _ = write_pack(tmp_path / "pack")
    assert code_of(lambda: install_pack(pack)) == "UNSIGNED"
    assert ModuleRegistry.has("fake.echo") is False
    provenance = install_pack(pack, require_signature=False)
    assert provenance.signature is None and provenance.signature_verified is False
    assert ModuleRegistry.has("fake.echo")


async def test_a_present_signature_is_verified_even_when_not_required(tmp_path, keypair):
    pack, _, _ = signed_pack(tmp_path, keypair)
    assert code_of(lambda: install_pack(pack, require_signature=False)) == "UNTRUSTED_KEY"


async def test_pack_cannot_replace_another_owners_module(tmp_path, keypair):
    first, _ = write_pack(tmp_path / "a", pack_id="com.example.first")
    install_pack(first, require_signature=False)
    second, _ = write_pack(tmp_path / "b", pack_id="com.example.second")
    assert code_of(lambda: install_pack(second, require_signature=False)) == "REGISTRATION_FAILED"
    assert ModuleRegistry.get_metadata("fake.echo")["plugin"] == "com.example.first"
    assert "com.example.second" not in installed_packs()


async def test_pack_id_cannot_shadow_an_entry_point(tmp_path, monkeypatch):
    import core.modules.registry.core as registry_core

    class EP:
        name = "com.example.fake"
        value = "x:y"

        def load(self):
            return lambda: None

    original = registry_core._iter_entry_points
    monkeypatch.setattr(registry_core, "_iter_entry_points", lambda group="flyto.modules": original(group) + [EP()])
    pack, _ = write_pack(tmp_path / "p")
    assert code_of(lambda: install_pack(pack, require_signature=False)) == "REGISTRATION_FAILED"


async def test_inprocess_python_manifest_is_not_loadable(tmp_path):
    pack, _ = write_pack(
        tmp_path / "p", runtime={"binding": "inprocess-python", "entry_point": "pkg.mod:register_all"}
    )
    assert code_of(lambda: install_pack(pack, require_signature=False)) == "BINDING_NOT_LOADABLE"


async def test_min_host_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "_host_version", lambda: "2.36.0")
    pack, _ = write_pack(tmp_path / "p", min_host="2.37.0")
    assert code_of(lambda: install_pack(pack, require_signature=False)) == "HOST_TOO_OLD"
    monkeypatch.setattr(host, "_host_version", lambda: "2.37.0")
    assert install_pack(pack, require_signature=False).host_version == "2.37.0"


async def test_invoker_plugin_manager_is_wired(tmp_path, keypair):
    from core.runtime.invoke import get_invoker

    pack, _, keys = signed_pack(tmp_path, keypair)
    install_pack(pack, trusted_keys=keys)
    invoker = get_invoker()
    manager = host.get_pack_plugin_manager()
    assert invoker.plugin_manager is manager
    assert "com.example.fake" in invoker._router.config.available_plugins
    # The runtime policy gate reads the pack's declared steps from the manager.
    assert manager.get_manifest("com.example.fake").get_step("fake.echo") is not None
    result = await invoker.invoke_plugin_step("com.example.fake", "fake.echo", {"text": "direct"}, {})
    assert result["ok"] is True and result["data"]["input"] == {"text": "direct"}


async def test_rediscovery_keeps_the_pack(tmp_path, keypair):
    from core.capability_manifest import refresh_capability_manifest

    pack, _, keys = signed_pack(tmp_path, keypair)
    install_pack(pack, trusted_keys=keys)
    ModuleRegistry.discover_plugins(force=True)
    assert ModuleRegistry.get_metadata("fake.echo")["plugin"] == "com.example.fake"
    assert "fake.echo" in refresh_capability_manifest()["modules"]


async def test_uninstall_removes_modules_and_stops_the_process(tmp_path, keypair):
    pack, _, keys = signed_pack(tmp_path, keypair)
    install_pack(pack, trusted_keys=keys)
    await run("fake.echo", {"text": "start it"})
    manager = host.get_pack_plugin_manager()
    assert "com.example.fake" in manager._plugins

    assert await uninstall_pack("com.example.fake") == ["fake.echo"]
    assert ModuleRegistry.has("fake.echo") is False
    assert "com.example.fake" not in ModuleRegistry.get_plugins()
    assert "com.example.fake" not in manager._plugins
    assert manager.get_manifest("com.example.fake") is None


async def test_provenance_record_is_written(tmp_path, keypair):
    pack, manifest, keys = signed_pack(tmp_path, keypair)
    out = tmp_path / "provenance"
    provenance = install_pack(pack, trusted_keys=keys, provenance_dir=out)
    record = json.loads((out / "com.example.fake-0.1.0.json").read_text())
    assert record["schema"] == "flyto.pack-provenance.v1"
    assert record["artifact_digest"] == manifest["artifact"]["digest"]
    assert record["signature"]["key_id"] == "test-key"
    assert record["manifest_sha256"] == provenance.manifest_sha256
    assert installed_packs()["com.example.fake"] == provenance


async def test_reinstall_requires_uninstall(tmp_path, keypair):
    pack, _, keys = signed_pack(tmp_path, keypair)
    install_pack(pack, trusted_keys=keys)
    assert code_of(lambda: install_pack(pack, trusted_keys=keys)) == "ALREADY_INSTALLED"
    await uninstall_pack("com.example.fake")
    assert install_pack(pack, trusted_keys=keys).pack_id == "com.example.fake"
