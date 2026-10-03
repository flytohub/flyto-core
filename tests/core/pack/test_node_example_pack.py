"""End to end: the Node.js example pack, signed, installed and executed.

Skipped when ``node`` is not on PATH. Proves three things:

* the checked-in ``flyto-pack.json`` is exactly what ``registerModule`` produces;
* the same two modules written with Python's ``@register_module`` export the
  same normalized rows — one contract, two authoring languages;
* a signed Node pack installs into the registry and runs over JSON-RPC.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core.capability_manifest import get_capability_manifest
from core.modules.registry import ModuleRegistry
from core.pack.export import export_python_pack
from core.pack.host import install_pack
from core.pack.manifest import (
    MANIFEST_FILENAME,
    SIGNATURE_FILENAME,
    pack_tree_digest,
    validate_pack_manifest,
)
from core.pack.signature import sign_manifest

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "packs" / "node-greeter"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def node_manifest():
    out = subprocess.run([NODE, "index.js", "--manifest"], cwd=EXAMPLE, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_checked_in_manifest_is_what_the_helper_produces():
    checked_in = json.loads((EXAMPLE / MANIFEST_FILENAME).read_text())
    assert validate_pack_manifest(node_manifest()) == validate_pack_manifest(checked_in)


def test_node_and_python_produce_the_same_rows(python_greeter_path):
    node = validate_pack_manifest(node_manifest())
    python = export_python_pack("_python_greeter_pack:register_all", pack_id="com.example.greeter", version="0.1.0")
    assert node["modules"] == python["modules"]
    assert node["pack"]["namespaces"] == python["pack"]["namespaces"]


async def test_signed_node_pack_installs_and_runs(tmp_path, keypair, host_version):
    private, public = keypair
    pack = tmp_path / "node-greeter"
    shutil.copytree(EXAMPLE, pack)
    raw = json.loads((pack / MANIFEST_FILENAME).read_text())
    raw["artifact"] = {"digest": pack_tree_digest(pack)}
    (pack / MANIFEST_FILENAME).write_text(json.dumps(raw), encoding="utf-8")
    signature = sign_manifest(validate_pack_manifest(raw), private, "example-publisher")
    (pack / SIGNATURE_FILENAME).write_text(json.dumps(signature), encoding="utf-8")

    provenance = install_pack(pack, trusted_keys={"example-publisher": public})
    assert provenance.signature_verified
    assert ModuleRegistry.get_metadata("greeter.greet")["plugin"] == "com.example.greeter"
    assert get_capability_manifest()["contracts"]["greeter.greet"]["contract"]["safety_class"] == "read_only"

    greet = await ModuleRegistry.get("greeter.greet")({"name": "Ada"}, {}).run()
    assert greet == {"ok": True, "data": {"greeting": "Hello, Ada!"}}
    repeated = await ModuleRegistry.get("greeter.repeat")({"text": "hi", "times": 3}, {}).run()
    assert repeated == {"ok": True, "data": {"text": "hi hi hi"}}
    blank = await ModuleRegistry.get("greeter.repeat")({"text": " "}, {}).run()
    assert blank == {"ok": False, "error": "text is blank", "error_code": "BLANK_TEXT"}
