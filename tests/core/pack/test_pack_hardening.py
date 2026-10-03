"""Adversarial install cases for flyto.pack.v1 packs.

Each test is a way a third-party pack could take something it does not own:
code swapped in after the signature was checked, a namespace another owner
already ships, a capability whose meaning another provider already declared,
or a racing second install of the same id.
"""

import threading

import pytest
from pack_helpers import FAKE_PLUGIN, module_row, write_pack

from core.capability_host.host import registry_contract_lookup
from core.modules.registry import ModuleRegistry
from core.pack import host
from core.pack.host import install_pack, installed_packs
from core.pack.manifest import PackManifestError

STOP = {
    "actuates": True,
    "safety_class": "movement",
    "requires_safe_stop": False,
    "cancellable": False,
    "idempotent": True,
    "role": "safe_stop",
}
READ = {
    "actuates": False,
    "safety_class": "read_only",
    "requires_safe_stop": False,
    "cancellable": True,
    "idempotent": True,
}


def code_of(call):
    with pytest.raises(PackManifestError) as info:
        call()
    return info.value.code


async def run(module_id, params):
    return await ModuleRegistry.get(module_id)(params, {}).run()


# -- code swapped after verification ----------------------------------------


async def test_code_changed_after_install_does_not_run(tmp_path, keypair):
    private, public = keypair
    pack, _ = write_pack(tmp_path / "pack", sign_with=private)
    install_pack(pack, trusted_keys={"test-key": public})
    # The process starts lazily. Swapping the entry after the digest and
    # signature were checked must not change what runs.
    evil = FAKE_PLUGIN.replace('"input": inp', '"input": {"swapped": True}')
    (pack / "main.py").write_text(evil, encoding="utf-8")
    result = await run("fake.echo", {"text": "hi"})
    assert result["ok"] is True
    assert result["data"]["input"] == {"text": "hi"}


async def test_staged_copy_is_removed_on_uninstall(tmp_path, keypair):
    private, public = keypair
    pack, _ = write_pack(tmp_path / "pack", sign_with=private)
    install_pack(pack, trusted_keys={"test-key": public})
    staged = host._INSTALLED["com.example.fake"].staged_dir
    assert staged is not None and staged.is_dir() and staged != pack.resolve()
    await host.uninstall_pack("com.example.fake")
    assert not staged.exists()


async def test_refused_install_leaves_no_staged_copy(tmp_path, monkeypatch):
    import tempfile

    made = []
    original = tempfile.mkdtemp

    def tracking(*args, **kwargs):
        path = original(*args, **kwargs)
        made.append(path)
        return path

    monkeypatch.setattr(host.tempfile, "mkdtemp", tracking)
    pack, _ = write_pack(tmp_path / "pack")
    (pack / "extra.txt").write_text("not attested", encoding="utf-8")
    assert code_of(lambda: install_pack(pack, require_signature=False)) == "DIGEST_MISMATCH"
    assert all(not __import__("os").path.exists(p) for p in made if "flyto-pack-" in p)


# -- namespace squatting ----------------------------------------------------


async def test_pack_cannot_add_modules_to_a_core_namespace(tmp_path):
    # "capability" is flyto-core's (capability.invoke) but not on the static
    # deny list; a pack must not publish capability.* beside it.
    pack, _ = write_pack(
        tmp_path / "pack", namespaces=("capability",), modules=[module_row("capability.invoke_fast")]
    )
    assert code_of(lambda: install_pack(pack, require_signature=False)) == "REGISTRATION_FAILED"
    assert not ModuleRegistry.has("capability.invoke_fast")


async def test_pack_cannot_join_another_packs_namespace(tmp_path):
    first, _ = write_pack(tmp_path / "a", pack_id="com.example.first")
    install_pack(first, require_signature=False)
    second, _ = write_pack(
        tmp_path / "b", pack_id="com.example.second", modules=[module_row("fake.other")]
    )
    assert code_of(lambda: install_pack(second, require_signature=False)) == "REGISTRATION_FAILED"
    assert not ModuleRegistry.has("fake.other")


async def test_declared_but_empty_namespace_is_still_held(tmp_path):
    first, _ = write_pack(tmp_path / "a", pack_id="com.example.first", namespaces=("fake", "spare"))
    install_pack(first, require_signature=False)
    second, _ = write_pack(
        tmp_path / "b", pack_id="com.example.second", namespaces=("spare",), modules=[module_row("spare.x")]
    )
    assert code_of(lambda: install_pack(second, require_signature=False)) == "REGISTRATION_FAILED"


# -- capability meaning -----------------------------------------------------


def _cap_pack(tmp_path, name, ns, contract):
    row = module_row(f"{ns}.stop", provides_capability="robot.base.stop", contract=contract)
    return write_pack(tmp_path / name, pack_id=f"com.example.{name}", namespaces=(ns,), modules=[row])[0]


async def test_pack_cannot_change_an_existing_capability_contract(tmp_path):
    install_pack(_cap_pack(tmp_path, "real", "realbot", STOP), require_signature=False)
    assert registry_contract_lookup("robot.base.stop")[2] == "declared"
    hostile = _cap_pack(tmp_path, "hostile", "hostile", READ)
    assert code_of(lambda: install_pack(hostile, require_signature=False)) == "REGISTRATION_FAILED"
    # The safe stop still resolves; it did not become "ambiguous".
    contract, _, status = registry_contract_lookup("robot.base.stop")
    assert status == "declared" and contract["role"] == "safe_stop"


async def test_pack_cannot_drop_the_contract_of_an_existing_capability(tmp_path):
    install_pack(_cap_pack(tmp_path, "real", "realbot", STOP), require_signature=False)
    row = module_row("hostile.stop", provides_capability="robot.base.stop")
    hostile, _ = write_pack(
        tmp_path / "hostile", pack_id="com.example.hostile", namespaces=("hostile",), modules=[row]
    )
    assert code_of(lambda: install_pack(hostile, require_signature=False)) == "REGISTRATION_FAILED"
    assert registry_contract_lookup("robot.base.stop")[2] == "declared"


async def test_second_provider_with_the_same_contract_is_allowed(tmp_path):
    install_pack(_cap_pack(tmp_path, "real", "realbot", STOP), require_signature=False)
    install_pack(_cap_pack(tmp_path, "fleet", "fleet", STOP), require_signature=False)
    assert ModuleRegistry.capabilities()["robot.base.stop"] == ["fleet.stop", "realbot.stop"]
    assert registry_contract_lookup("robot.base.stop")[2] == "declared"


# -- concurrent install -----------------------------------------------------


async def test_concurrent_installs_of_one_id_install_once(tmp_path):
    pack, _ = write_pack(tmp_path / "pack")
    results = []

    def attempt():
        try:
            results.append(install_pack(pack, require_signature=False).pack_id)
        except PackManifestError as exc:
            results.append(exc.code)

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("com.example.fake") == 1
    assert results.count("ALREADY_INSTALLED") == 5
    assert list(installed_packs()) == ["com.example.fake"]
