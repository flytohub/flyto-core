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

The matrix is generated, never written by hand:
[`../reference/pack-compatibility-matrix.md`](../reference/pack-compatibility-matrix.md)
for people and
[`../reference/pack-compatibility-matrix.json`](../reference/pack-compatibility-matrix.json)
(`flyto.pack-compatibility-matrix.v1`) for tools. Both are outputs of
`scripts/generate_reference.py`, read from `core.pack.compatibility.FEATURES`;
`tests/core/pack/test_compatibility_matrix.py` fails when either is stale.
`flyto pack matrix` prints the same matrix, and with `--certification FILE
--certifier-key ID=FILE` it adds the packs those verified records certify.

Rows are only ever added; a released version never changes what it
accepts. A new contract or pack feature adds its row to `FEATURES` in the
same change that adds the feature, then regenerates.

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
| `operations_called` | — | never: a connector's operations reach the provider, so this offline suite does not call them (`not_applicable`) |
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

## Certification (`flyto.pack-certification.v1`)

`flyto pack certify PACK --key CERT.pem --key-id ID` runs, in this order
(`core.pack.certification.CHECKS`):

| Check | Fails when | Not applicable when |
| --- | --- | --- |
| `verify` | the digest, files, signature (through rotation statements) or revocation list refuse the pack; or it is not built (`PACK_NOT_BUILT`) | never |
| `compatibility` | `min_host` is missing, older than the matrix requires, or newer than this host | never |
| `conform` | the conformance suite above is not conformant | never |
| `pack_test` | `flyto pack test` fails against the pack's recorded fixtures | the pack is not a connector (its runner is what `conform` runs) |
| `standalone_health` | standalone health, pointed at the recorded fixtures with a fixture customer's test credential, is unhealthy | the pack has no `standalone` section |

A pack that fails `verify` is never run: every later check is `not_run`.
Only when every check passes, or is not applicable where the table allows
it, is a record signed. It names the pack digest, the flyto-core range it
passed on (`core.min` = `min_host`, `core.max` = the flyto-core that ran the
checks), the matrix version, the features used, each check's result and the
certifier key id, signed with the one ed25519 step under its own domain
(`flyto.pack-certification.v1`). A record is evidence level **D2**, and it
says `hardware_acceptance: NOT_VERIFIED`.

A host may require certification through a policy table
(`flyto.pack-certification-policy.v1`). The first rule whose `packs` pattern
matches the pack id decides:

```json
{"schema": "flyto.pack-certification-policy.v1",
 "rules": [{"packs": "com.example.*", "require": true, "certifiers": ["certifier-1"], "max_age_days": 365}]}
```

When the rule requires it, `install_pack` and `verify_pack` refuse a pack
without a record that verifies against a key the rule names and that names
this exact pack digest (`PACK_UNCERTIFIED`). A record that names the pack but
no longer applies is `CERTIFICATION_STALE`
(`core.pack.certification.STALENESS`: this host is newer than `core.max` or
older than `core.min`, the matrix version changed, or the record is older
than `max_age_days`). No matching rule, or `require: false`, requires
nothing.

## Upgrade compatibility (`upgrade`)

A pack declares which earlier versions it upgrades from (`supersedes`),
which it may be replaced by again (`rollback`, a subset of `supersedes`),
and the stored state that changes (`migrations`: `from`, `state`,
`reversible`). A rollback across an irreversible migration cannot be
declared (`ROLLBACK_IRREVERSIBLE`). A host replacing a running version
passes it as `install_pack(..., upgrade_from=...)`;
`core.pack.upgrade.check_transition` refuses an upgrade the new version does
not declare (`UPGRADE_UNDECLARED`), a downgrade the running version does not
declare (`ROLLBACK_UNDECLARED`) and the same version with other content
(`VERSION_REBUILT`). It names the migrations the switch crosses; flyto-core
runs none of them.

## Publisher keys over time

A publisher rotates its key with a statement signed by the old key
(`flyto.publisher-key-rotation.v1`, `flyto pack rotate-key`). A host that
trusts the old key follows at most 8 statements to the key a pack is signed
with (`--key-rotation FILE`, `install_pack(..., key_rotations=...)`); a chain
that does not connect is `KEY_ROTATION_BROKEN`, a longer one
`KEY_ROTATION_TOO_LONG`.

The revocation list `flyto.pack-revocations.v2` adds `revoked_keys`:
revoking a key revokes every pack it signed after the revocation point. A
signature carries no time a compromised key could not forge, so the point is
stated by what the key signed before it, the `retained` digests (packs, and
rotation statements). Any other pack signed by that key is `PACK_REVOKED`,
and any other rotation statement it signed is `PUBLISHER_KEY_REVOKED`. A v1
list still loads.

## Verified pack × device × host combinations

None recorded. No third-party adapter has been accepted on real equipment
under this suite, and none may be listed until it has (J17 is a hypothesis,
not a result; 2026-10-16 gap audit in flyto-cloud).

| Pack id | Pack version / digest | Device (vendor, model, firmware) | Host (flyto-core) | Record | Level |
| --- | --- | --- | --- | --- | --- |
