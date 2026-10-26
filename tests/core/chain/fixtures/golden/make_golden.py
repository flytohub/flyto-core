"""Build the flyto-core chain golden fixtures with flyto-cloud's own record.py and signing.py.

Produced from flyto-cloud 7b1ad65079e6 (branch feat/unified-platform-integration-20261018):
``src/ui/web/backend/services/execution_chain/record.py`` (sha256 b9cb4df00576ea9a...) and
``signing.py`` (sha256 ffa1a96c485b40f5...), copied unchanged into a package named
``cloudchain`` in a scratch virtualenv that has only ``cryptography`` installed.
This file is not imported by the test suite; it records how the fixtures were made.

Usage: python -I make_golden.py <dir holding cloudchain/> <out dir>
Keys are derived from fixed seeds, and ed25519 signatures are deterministic,
so the output is byte-for-byte reproducible.
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])

from cloudchain import record as chain_record  # noqa: E402
from cloudchain import signing as chain_signing  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: E402


def key(seed: str) -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed.encode()).digest())


cloud_old = chain_signing.MemoryChainSigner("cloud-golden-1", key("flyto-core golden cloud 1"))
cloud = chain_signing.MemoryChainSigner("cloud-golden-2", key("flyto-core golden cloud 2"))
host = chain_signing.MemoryChainSigner("host-golden-1", key("flyto-core golden host 1"))
DEVICE = "dev-golden"
ROTATED = "2026-10-01T00:00:00+00:00"

old_entry = chain_signing.key_entry(cloud_old.key_id, cloud_old.public_key_raw(), not_after=ROTATED)
new_entry = chain_signing.key_entry(cloud.key_id, cloud.public_key_raw(), not_before=ROTATED)
cloud_keys = chain_signing.key_document("cloud", [old_entry, new_entry],
                            [chain_signing.rotation_statement(cloud_old, new_entry, at=ROTATED)])
host_keys = chain_signing.key_document(f"host:{DEVICE}", [chain_signing.key_entry(host.key_id, host.public_key_raw())])

CAPABILITY = "example.resource.move_to"
CONTRACT_DIGEST = chain_record.digest_of({"schema": "flyto.capability-contract.v1", "actuates": True,
                               "label": "Move to a position 位置"})

rec = chain_record.new_record(chain_record.call_id_for_job("job-golden-1"))


def add(stage, at, signer, body, key_signer):
    global rec
    section = chain_record.new_section(rec, section_stage=stage, at=at, signer=signer, body=body)
    rec = chain_record.append(rec, chain_signing.attest(section, key_signer))


add("admit", "2026-10-26T08:00:00+00:00", "cloud",
    {"entry_path": "W1", "principal": "user:golden", "params_digest": chain_record.digest_of({"x": 1.5, "y": -2})}, cloud)
add("contract", "2026-10-26T08:00:01+00:00", "cloud",
    {"contracts": {CAPABILITY: CONTRACT_DIGEST}, "max_level": 4}, cloud)
add("authority", "2026-10-26T08:00:02+00:00", "cloud", {"effective_max_level": 4, "grant_ids": ["g-1"]}, cloud)
add("approval", "2026-10-26T08:00:03+00:00", "cloud", {"kind": "operator_start", "approver": "user:golden"}, cloud)
add("lease", "2026-10-26T08:00:04+00:00", "cloud", {"resource_id": "res-1", "generation": 3}, cloud)
add("dispatch", "2026-10-26T08:00:05+00:00", "cloud",
    {"job_id": "job-golden-1", "target_host": DEVICE, "envelope_digest": chain_record.digest_of({"job": "golden"}),
     "expires_at": "2026-10-26T09:00:05+00:00"}, cloud)
head_at_dispatch = rec["head"]
add("host_claim", "2026-10-26T08:00:06+00:00", f"host:{DEVICE}",
    {"host_id": DEVICE, "device_key_id": host.key_id, "cloud_record_head": head_at_dispatch,
     "host_verified": True, "refusal": None, "stop_exempt": False, "host_seq": 1}, host)
add("host_execute", "2026-10-26T08:00:09+00:00", f"host:{DEVICE}",
    {"calls": [{"call_id": "cap-1", "capability_id": CAPABILITY, "local_contract_digest": CONTRACT_DIGEST,
                "effect_seq": 3, "outcome": "completed"}], "host_seq": 5}, host)
add("evidence", "2026-10-26T08:00:10+00:00", f"host:{DEVICE}",
    {"captures": [{"capture_seq": 2, "kind": "before", "call_id": "cap-1", "sha256": chain_record.digest_of({"p": 0})},
                  {"capture_seq": 4, "kind": "after", "call_id": "cap-1", "sha256": chain_record.digest_of({"p": 1})}],
     "ordering_proof": [{"call_id": "cap-1", "before": 2, "effect": 3, "after": 4, "ordered": True}],
     "host_seq": 6}, host)
add("verdict", "2026-10-26T08:00:11+00:00", "cloud",
    {"state": "done", "effect": "confirmed", "proof": "supported", "code": None}, cloud)

assert chain_record.link_problems(rec) == [], chain_record.link_problems(rec)
docs = {"cloud": chain_signing.load_key_document(cloud_keys), f"host:{DEVICE}": chain_signing.load_key_document(host_keys)}
trusted = {"cloud": chain_signing.endorsed_keys(docs["cloud"], [cloud_old.key_id]),
           f"host:{DEVICE}": chain_signing.endorsed_keys(docs[f"host:{DEVICE}"], [host.key_id])}
assert chain_signing.signature_problems(rec, docs, trusted=trusted) == [], chain_signing.signature_problems(rec, docs, trusted=trusted)

out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


def write(name, value):
    (out / name).write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


write("record.json", rec)
write("cloud-keys.json", cloud_keys)
write("host-keys.json", host_keys)
# The section digests and canonical bytes Cloud computed, so core is held to Cloud's bytes.
write("digests.json", {
    "head": rec["head"],
    "sections": [{"seq": s["seq"], "digest": chain_record.section_digest(s),
                  "signing_message_sha256": hashlib.sha256(chain_record.signing_message(s)).hexdigest()}
                 for s in rec["sections"]],
})
print(rec["head"])
