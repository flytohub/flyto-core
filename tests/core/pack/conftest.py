"""Fixtures for flyto.pack.v1 tests: keys, host version, and cleanup."""

import sys
from pathlib import Path

import pytest


@pytest.fixture
def keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    return private, private.public_key()


@pytest.fixture
def host_version(monkeypatch):
    """Pin the host version the min_host check reads (local venvs lag pyproject)."""
    import core.pack.host as host

    monkeypatch.setattr(host, "_host_version", lambda: "2.37.0")
    return "2.37.0"


@pytest.fixture(autouse=True)
async def _uninstall_packs():
    yield
    from core.pack import host

    for pack_id in list(host._INSTALLED):
        await host.uninstall_pack(pack_id)


@pytest.fixture
def python_greeter_path():
    path = str(Path(__file__).parent)
    sys.path.insert(0, path)
    yield path
    sys.path.remove(path)
    sys.modules.pop("_python_greeter_pack", None)
