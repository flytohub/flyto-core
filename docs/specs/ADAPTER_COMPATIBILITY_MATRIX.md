# Adapter compatibility matrix

Status: **implemented** (`core.pack.compatibility`, read by
`flyto pack conform`). Matrix version: **1**. Conformance suite:
`flyto.pack-conformance.v1`.

A pack's `pack.min_host` promises every host that loads it. Contracts are
closed schemas, so a pack that uses a newer key is refused by every older
host. `flyto pack conform` computes the oldest flyto-core that accepts
everything the pack uses and fails a pack whose `min_host` is older, or
missing.

## Feature → first flyto-core that accepts it

| Feature | Since | What the pack uses |
| --- | --- | --- |
| `capability_contract.v1` | 2.35.0 | `contract` on a module row (`flyto.capability-contract.v1`) |
| `contract.optional_fields` | 2.36.0 | `role`, `artifacts`, `recovery`, `expected_duration_ms` |
| `pack.v1` | 2.37.0 | `flyto.pack.v1` manifest, `subprocess-jsonrpc` and `http` bindings |
| `evidence.absolute_targets` | 2.38.0 | `distance_to` / `angle_to` measure ops, `measure.frame` |
| `recovery.semantics` | 2.39.0 | `recovery.on` / `alternatives` / `preserves` / `resource_scope` / `fills` |
| `evidence.display_keys` | 2.40.0 | evidence `label`, `unit`, `channel` |

Rows are only ever added; a released version never changes what it
accepts. `tests/core/pack/test_pack_conformance.py` keeps this table equal
to `core.pack.compatibility.FEATURES`. A new contract or pack feature adds
its row in the same change that adds the feature.

## What the conformance suite checks

| Check | Reads | Fails when |
| --- | --- | --- |
| `manifest` | files | the manifest does not validate (stable error code) |
| `tree_digest` | files | `artifact.digest` is declared and the files differ |
| `signature` | files + keys | a signature does not verify against a given trusted key |
| `safe_stop_declared` | files | something requires a stop and no row has `role: safe_stop` |
| `evidence_declared` | files | an actuating capability declares no evidence |
| `compatibility` | files + matrix | `min_host` is missing, older than the matrix requires, or newer than this host |
| `installs` | runner | `install_pack` refuses the pack |
| `safe_stop_answers` | runner | a stop answers anything but `ok: true` |
| `completes_in_bounds` | runner | an actuation inside the published bounds is refused |
| `refuses_out_of_bounds` | runner | a value past a published maximum is accepted (clamped or ignored) |
| `answers` | runner | a call gets no answer: the runner crashed, timed out or replied unreadably |

`not_applicable` is never a pass; a report where nothing ran is not
conformant. `--static-only` runs the file checks and never starts the runner.

## Evidence level of a result

A conformant report is **D2**: a local run of an exact command against
whatever the runner drove, which should be the vendor's simulator. It is not
hardware certification. A pack and device combination enters the table
below only with a D4 record: the same pack digest on the real device, the
device's own receipts, a measured stop and an independent observation.

## Verified pack × device × host combinations

None recorded. No third-party adapter has been accepted on real equipment
under this suite, and none may be listed until it has (J17 is a hypothesis,
not a result; 2026-10-16 gap audit in flyto-cloud).

| Pack id | Pack version / digest | Device (vendor, model, firmware) | Host (flyto-core) | Record | Level |
| --- | --- | --- | --- | --- | --- |
