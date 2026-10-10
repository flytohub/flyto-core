"""Helpers for flyto.pack.v1 tests: write a pack directory, optionally signed."""

import json
from pathlib import Path

from core.pack.manifest import (
    MANIFEST_FILENAME,
    SIGNATURE_FILENAME,
    pack_tree_digest,
    validate_pack_manifest,
)
from core.pack.signature import sign_manifest

# A stdlib-only JSON-RPC plugin, so the subprocess path is tested without Node.
FAKE_PLUGIN = r'''
import json, sys
for line in sys.stdin:
    if not line.strip():
        continue
    req = json.loads(line)
    method, rid, params = req.get("method"), req.get("id"), req.get("params") or {}
    if method == "handshake":
        res = {"pluginVersion": "0.1.0"}
    elif method == "ping":
        res = {}
    elif method == "shutdown":
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {}}), flush=True)
        break
    elif method == "invoke":
        step, inp = params.get("step"), params.get("input") or {}
        if step.endswith(".fail"):
            res = {"ok": False, "error": {"code": "NOPE", "message": "refused by the pack"}}
        elif step.endswith(".noflag"):
            res = {"ok": "yes", "data": 1}
        else:
            res = {"ok": True, "data": {"input": inp, "context": params.get("context")}}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "no"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}), flush=True)
'''


def module_row(module_id, **extra):
    row = {
        "module_id": module_id,
        "label": module_id.split(".")[-1].title(),
        "description": f"Test module {module_id}",
        "params_schema": {
            "text": {"type": "string", "label": "Text", "description": "Some text", "placeholder": "x"}
        },
        "output_schema": {"input": {"type": "object", "description": "Echoed input"}},
        "timeout_ms": 10000,
    }
    row.update(extra)
    return row


def write_pack(
    root: Path,
    pack_id="com.example.fake",
    namespaces=("fake",),
    modules=None,
    runtime=None,
    sign_with=None,
    key_id="test-key",
    with_digest=True,
    **pack_extra,
):
    """Write a pack directory; returns ``(path, normalized manifest)``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(FAKE_PLUGIN, encoding="utf-8")
    manifest = {
        "schema": "flyto.pack.v1",
        "pack": {"id": pack_id, "version": "0.1.0", "namespaces": list(namespaces), **pack_extra},
        "runtime": runtime or {"binding": "subprocess-jsonrpc", "language": "python", "entry": "main.py"},
        "modules": modules or [module_row(f"{namespaces[0]}.echo")],
    }
    if with_digest:
        manifest["artifact"] = {"digest": pack_tree_digest(root)}
    (root / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    normalized = validate_pack_manifest(manifest)
    if sign_with is not None:
        signature = sign_manifest(normalized, sign_with, key_id)
        (root / SIGNATURE_FILENAME).write_text(json.dumps(signature), encoding="utf-8")
    return root, normalized
