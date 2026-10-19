# Flyto2 Bundle — `flyto.bundle.v1`

Status: **implemented in flyto-core 2.41.0, unreleased** (`core.pack.bundle`,
`flyto bundle build|verify`). Installation is private, from a file or a
folder; nothing is published to a marketplace.

## What it is

A bundle is what a solution ships as one unit: the [packs](PACK_MANIFEST_SPEC.md)
it needs, the Space workflow documents that use them, and the report
templates those workflows fill. It **references** each pack by id, exact
version and pack digest. It never carries a copy, so a pack has exactly one
artifact however many bundles use it, and a bundle cannot quietly ship a
different build of a pack under the same name.

## The document

`flyto-bundle.json`, at the root of the bundle directory or zip:

```json
{
  "schema": "flyto.bundle.v1",
  "bundle": {
    "id": "com.example.rating-review",
    "version": "0.1.0",
    "title": "optional",
    "description": "optional"
  },
  "packs": [
    {"id": "com.example.ratings", "version": "0.1.0", "digest": "sha256:<pack digest>"}
  ],
  "workflows": [
    {"name": "rating-review", "path": "workflows/rating-review.json", "digest": "sha256:<file sha256>"}
  ],
  "templates": [
    {"name": "rating-summary", "path": "templates/rating-summary.md",
     "media_type": "text/markdown", "digest": "sha256:<file sha256>"}
  ]
}
```

| Key | Rule |
| --- | --- |
| `schema` | Exactly `flyto.bundle.v1`. |
| `bundle.id` | Lowercase identifier, as a pack id. |
| `bundle.version`, `packs[].version` | One exact semver release. A range, a prefix or `latest` is refused (`VERSION_NOT_PINNED`). |
| `packs[]` | 1–64 references `{id, version, digest}`. `digest` is the [pack digest](PACK_MANIFEST_SPEC.md#supply-chain-2410): SHA-256 of the normalized manifest, which carries `artifact.digest`. |
| `workflows[]`, `templates[]` | Up to 256 each, `{name, path, digest}`; a template may add `media_type`. `path` is relative, inside the bundle. `digest` is `sha256:` of the file's bytes. |

A pack id, an item name (workflows and templates share one namespace) or an
item path appearing twice is refused (`DUPLICATE_NAME`). Unknown keys are
refused. The bundle directory holds the manifest, the declared files and an
optional `flyto-bundle.sig.json`, and nothing else (`UNDECLARED_FILE`): a
pack copied in is refused like any other undeclared file.

A workflow document is JSON (`.json`) or YAML (`.yaml`, `.yml`). Its module
references are every `module` key, including those inside an inline
sub-workflow (`workflow_source`, `template`), collected by the same function
the module policy uses (`core.module_policy._collect_module_ids`).

## Verifying

`flyto bundle verify BUNDLE --pack PACK.zip … [trust options]`
(`verify_bundle`) refuses, with a typed reason:

| Code | When |
| --- | --- |
| `UNSIGNED` / `UNTRUSTED_KEY` / `SIGNATURE_MISMATCH` | the bundle signature is required and absent, from an unknown key, or over a different manifest |
| `UNDECLARED_FILE` | the bundle holds a file the manifest does not declare |
| `WORKFLOW_DIGEST_MISMATCH` / `TEMPLATE_DIGEST_MISMATCH` | a file's bytes differ from its digest |
| `PACK_NOT_FOUND` | no supplied pack has the referenced id and version |
| `PACK_REVOKED` | the revocation list names a referenced pack |
| `PACK_DIGEST_MISMATCH` | the supplied pack is not the one the bundle pins |
| `MODULE_NOT_PROVIDED` | a workflow uses a module that no referenced pack and no core module provides |

Each supplied pack is itself verified as `flyto pack verify` would (tree
digest, signature, revocation, portable tree). The core module set is every
registered module with no plugin owner (`core_module_ids`).

## Building

`flyto bundle build DIR --pack PACK.zip … [-o ZIP] [--key PEM --key-id ID]`
(`build_bundle`) reads a source manifest whose pins and digests may be
omitted, verifies each supplied pack, pins its digest (a digest the source
already states must match: `PACK_DIGEST_MISMATCH`), digests each file,
validates the result exactly as `verify` does, and writes one deterministic
zip (sorted entries, fixed timestamps). With a key it writes
`flyto-bundle.sig.json`:

```json
{"schema": "flyto.bundle-signature.v1", "algorithm": "ed25519",
 "key_id": "…", "signature": "<base64>"}
```

signed over `b"flyto.bundle-signature.v1\n" + canonical(normalized
manifest)` with the pack signing step (`core.pack.signature.sign_detached`).
The output file must not exist: a new bundle version is a new file.

## Example

`examples/bundles/rating-review/` pins `examples/packs/ratings-connector`
and carries one workflow (two pack operations and the core module
`string.uppercase`) and one Markdown report template.
`tests/core/pack/test_bundle.py` builds and verifies it, and checks every
refusal above.

## Not covered

- No resolver or download: the host supplies the pack files with `--pack`.
- Templates are attested bytes; their syntax is not checked.
- A workflow's parameters are not checked against the modules' schemas
  here; `flyto run` and the Space do that when it runs.
