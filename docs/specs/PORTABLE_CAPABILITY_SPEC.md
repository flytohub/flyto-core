# Portable Capabilities — shipping a capability with the thing that performs it

Status: **guidance over implemented formats**. Everything this page asks a
publisher to write is validated by flyto-core 2.40.0 today. It adds no new
format. The rules live in two normative documents, and this page does not
restate them:

- [`flyto.capability-contract.v1`](../CAPABILITY_CONTRACT.md): what a
  capability does to the world, how risky it is and what evidence proves it
  worked.
- [`flyto.pack.v1`](PACK_MANIFEST_SPEC.md): the language-neutral container
  that carries contracts, its tree digest, its publisher signature and how a
  host calls it.

## The idea

A capability's contract belongs to the thing that performs it, not to a
platform that uses it. A robot vendor's adapter, a lift controller's driver or
a policy trained by demonstration ships its own contracts, the way a library
ships its own type declarations. Any host can read them. Flyto2 is one such
host, and nothing in the contract names it.

The publisher states what the capability is, what it accepts, how risky it
is, how to stop it and what proves it worked. A host decides whether to allow
it, and judges the evidence itself.

## What to ship

Put a `flyto.pack.v1` manifest beside the implementation:

```
tabletop-arm/
├── flyto-pack.json        # the manifest: one row per capability, each with its contract
├── flyto-pack.sig.json    # optional ed25519 publisher signature over manifest and tree digest
├── runner/
│   └── main.py            # serves the capabilities: JSON-RPC on stdio, or HTTP
├── policy.json            # what the runner loads: model repository and pinned revision
└── README.md              # model or device card: data, environment, known limits
```

- **The runner can be written in any language** listed in
  `core/runtime/languages.py`, using either binding in
  [Bindings](PACK_MANIFEST_SPEC.md#bindings). It receives parameters and
  identifiers only, never the host's credentials or execution context.
- **Pinning the implementation.** The tree digest covers every file in the
  pack. Weights that fit within the digest's 512 MiB bound can sit in the pack
  directly. Larger ones stay where they are published, and a file in the pack
  (`policy.json` above) names the exact revision to load, so the digest pins
  the revision.
- **A new model is a new pack version.** The contract's key set is closed and
  has no model field. Training a new policy changes `pack.version`, and the
  tree digest changes with it. If the new policy accepts different inputs or
  proves success differently, the contract changes too, and a host treats
  that as a different capability to review.

## Writing the contract for a learned policy

A learned policy is one more implementation behind a contract. Answer each
question with the field that already exists:

| Question | Field |
| --- | --- |
| What does it do? | `provides_capability`, `label`, `description` |
| What does it accept, within what bounds? | `params_schema`. Every number an actuating contract takes declares finite `min` and `max`. A host refuses, and never clamps, a value outside them. |
| What does it do to the world? | `actuates`, `safety_class`, `effects`. A policy that moves things is `actuates: true`, `safety_class: movement`. |
| What must hold before it runs? | `requires` |
| Can it be stopped and cancelled? Is a retry safe? | `requires_safe_stop`, `cancellable`, `idempotent`. Most learned policies are not idempotent. A retry may move the object again, so declare `false`. |
| How is it stopped? | A separate capability in the same pack whose contract has `role: safe_stop`. The stop is never only an internal step of the policy. |
| What proves it worked? | `evidence`: a measurement of the world taken from an observation the adapter reports, judged against the call's own arguments. The policy's own success flag is not evidence. |
| How long may it run? | `expected_duration_ms` |
| What files does it return? | `artifacts`, for example a photo of the result |
| What may be tried after it fails? | `recovery` |

Example: [`examples/packs/tabletop-arm/flyto-pack.json`](../../examples/packs/tabletop-arm/flyto-pack.json).
The test `tests/core/pack/test_portable_capability_example.py` validates it and
checks that the excerpt below matches the file.

```json
{
  "module_id": "tabletop.pick_place",
  "provides_capability": "tabletop.pick_place",
  "params_schema": {
    "object_id": {"type": "string", "required": true},
    "target_x": {"type": "number", "required": true, "min": -0.30, "max": 0.30, "unit": "m"},
    "target_y": {"type": "number", "required": true, "min": 0.10, "max": 0.45, "unit": "m"}
  },
  "contract": {
    "actuates": true,
    "safety_class": "movement",
    "requires_safe_stop": true,
    "cancellable": true,
    "idempotent": false,
    "effects": ["object.relocated"],
    "requires": ["tabletop.calibrated"],
    "expected_duration_ms": 60000,
    "evidence": [{
      "kind": "placement",
      "observe": "object_pose",
      "phases": ["after", "settled"],
      "measure": {"op": "distance_to", "fields": ["x", "y"], "frame": "table"},
      "expect": {"arguments": {"x": "target_x", "y": "target_y"}},
      "tolerance": {"absolute": 0.02}
    }]
  }
}
```

The evidence says that the call succeeded only if the object's observed
position on the table, after the arm let go and again once settled, is within
2 cm of the point the call asked for. `core.capability_contract.judge` applied
to this spec gives:

| Observation | Verdict |
| --- | --- |
| Object 1 cm from the target, in frame `table` | usable |
| Object 5 cm from the target | not usable: error 0.05 exceeds 0.02 |
| Position reported in frame `camera` | not usable: phase `after` is not in frame `table` |
| No position reported | not usable: phase `after` was not observed |

The observation should come from a source independent of the policy, such as
a fixed camera or the gripper's own sensing. A host may require that.

## What a host does with it

Declaring a capability does not get it trusted. A conforming host:

1. **Verifies the publisher.** With `flyto pack verify` or `install_pack`, the
   signature and tree digest are checked offline against keys the host
   chose. An unknown key is refused.
2. **Validates the contract.** It applies `validate_contract`. The schema is
   closed, so an unknown key is an error and is never ignored.
3. **Admits the capability by its own policy.** Approval is the host's
   decision, per installation, and never part of the manifest.
4. **Refuses out-of-bounds arguments** before calling.
5. **Judges the evidence itself** from the observations the adapter reports.
   It does not take the runner's word that the call succeeded.

## Reporting a fault

An adapter may offer `connection_status()` (or `transport_status()` on the
transport that discovered the resource). Both are optional, and an adapter
without them stays valid. `core.adapter_status.status_payload` reads the
answer field by field. Its optional `fault` field says whether the resource
can work now:

| `fault` | Meaning |
| --- | --- |
| `{"reason": "<code>", "since": "<ISO 8601 with offset>"}` | faulted since then, for the adapter's own reason code |
| `null` | the adapter checked, and there is no fault |
| absent | unknown, which is what every adapter written before this field reports |
| present but unreadable | a fault, with reason `fault_report_unreadable` |

A call may also raise an exception that has a `fault_code` attribute.
`core.adapter_status.AdapterFaultError` is a ready-made one. The host records the
call as failed and records the fault, and `CapabilityHost.connection_status()`
keeps reporting it until the adapter answers `fault: null`.

## Relation to W3C WoT Thing Description 1.1

A Thing Description describes how to interact with a thing: its properties,
actions, events and protocol forms. It has no standard way to state
consequence, a safe stop, idempotency or the evidence that proves an action
worked, which is what a capability contract adds. The two complement each
other: a TD can describe an action, and the contract says when a host may run
it and how it decides the action worked.

Not defined yet: a TD vocabulary extension that carries contract fields inside
a TD. Until one is published, the pack manifest is the portable artifact.
Flyto2 Cloud reads a TD as untrusted description only, never as approval or
as an executable form.

## Checking a pack

```bash
flyto pack verify tabletop-arm --trusted-key acme=acme.pub   # signature and tree digest
flyto pack digest tabletop-arm                                # print the tree digest
```

```python
import json
from core.pack.manifest import validate_pack_manifest
manifest = validate_pack_manifest(json.load(open("tabletop-arm/flyto-pack.json")))
```

A host written in another language reimplements the same validation. The
admit and refuse vectors in `tests/core/vectors/` are its conformance set.

## Not covered yet

- A standalone JSON Schema for `flyto.capability-contract.v1`. The
  reference is `core.capability_contract.validate_contract` together with the
  vectors.
- A pack registry or download. A host is given directories and keys.
- The TD extension described above.
- Optional contract keys under review are not part of this page until they
  are released (for example `establishes` and `occupies`, flyto-core PR #139).
