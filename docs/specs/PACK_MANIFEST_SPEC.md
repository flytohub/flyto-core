# Flyto2 Module Pack Manifest — `flyto.pack.v1`

Status: **implemented in flyto-core 2.37.0** (`core.pack`). Validation,
normalization, tree digest, ed25519 signature verification, out-of-process
installation (`subprocess-jsonrpc`, `http`) and Python export are implemented
and tested. Installation is explicit: nothing scans a directory or downloads a
pack.

## What it is

`@register_module` is the Python *authoring syntax*. What the platform consumes
is the registry row the decorator produces — id, display fields,
`params_schema`, connection rules and, for a capability, a
[`flyto.capability-contract.v1`](../CAPABILITY_CONTRACT.md) contract. A
`flyto.pack.v1` manifest is that row written as JSON, so:

- a pack in **any language** that emits the same rows is loaded into the same
  `ModuleRegistry`, with the same validation, ownership stamping and policy
  gate, and appears in the catalog, the capability manifest and MCP
  `search_modules` / `get_module_info` exactly as a Python module does;
- a **Python** pack can print the rows its decorators produced:
  `flyto pack manifest <entry-point | module:register_all>`.

Cloud and every other host only need to know: *this resource installed a pack
that provides these capabilities, under these contracts*.

## The document

```json
{
  "schema": "flyto.pack.v1",
  "pack": {
    "id": "com.example.greeter",
    "version": "0.1.0",
    "namespaces": ["greeter"],
    "description": "optional",
    "title": "optional",
    "license": "optional",
    "min_host": "2.37.0",
    "publisher_key_id": "optional; must equal the signing key id"
  },
  "runtime": {
    "binding": "subprocess-jsonrpc",
    "language": "node",
    "entry": "index.js",
    "request_timeout_ms": 30000
  },
  "artifact": {"digest": "sha256:<tree digest>"},
  "modules": [ { "module_id": "greeter.greet", "...": "..." } ]
}
```

| Key | Rule |
| --- | --- |
| `schema` | Exactly `flyto.pack.v1`, compared before anything else. |
| `pack.id` | Lowercase identifier (`a-z0-9` with `.`, `_`, `-` separators), ≤128. It is the **owner** stamped on every module and the key for `FLYTO_PLUGIN_GRANTS` / allow / deny lists. It may not equal an installed `flyto.modules` entry point name. |
| `pack.namespaces` | 1–8 namespaces; every `module_id` starts with one. Namespaces flyto-core ships or denies (`shell`, `file`, `browser`, `http`, …, the `DENIED_NAMESPACES` list in `core/plugin/manifest.py`) are refused, so a pack cannot shadow a core module. |
| `runtime.binding` | `subprocess-jsonrpc`, `http`, or `inprocess-python`. Only the first two are installed from a manifest; `inprocess-python` packs load through their `flyto.modules` entry point and the manifest is an export. |
| `artifact.digest` | Optional unless the pack is signed. See [Tree digest](#tree-digest). |
| `modules` | 1–256 rows, unique ids. |

Unknown keys are refused everywhere except inside a parameter definition.
Text is bounded UTF-8 with control, bidi-override, zero-width, private-use and
unassigned characters refused. Errors carry a stable `code` and never echo the
rejected value.

### Module rows

A row uses the `@register_module` keyword names. Every key except `module_id`
is optional; the validator fills in the decorator's defaults, so the
**normalized** row always carries every key:

| Key | Default |
| --- | --- |
| `version` | `1.0.0` |
| `stability` | `stable` (`beta`, `alpha`, `deprecated`) |
| `label` | the module id (text, or `{language: text}`) |
| `label_key` | `modules.<module_id>.label` |
| `description`, `description_key` | `""`, `null` |
| `category`, `subcategory` | first id segment, `null` |
| `tags`, `input_types`, `output_types`, `required_permissions` | `[]` |
| `icon`, `color` | `null` |
| `params_schema`, `output_schema` | `{}` — the registry's parameter mapping `{name: {"type": ..., ...}}` |
| `can_receive_from`, `can_connect_to` | `["*"]` |
| `provides_capability` | `""` |
| `contract` | `null`; when present, validated and normalized by `validate_contract` |
| `timeout_ms` | `null` |
| `retryable`, `max_retries` | `false`, `0` (3 when retryable) |
| `concurrent_safe` | `true` |
| `requires_credentials`, `handles_sensitive_data` | `false` |

Booleans must be JSON booleans; nothing is coerced and absent never means
true. An actuating contract's numeric parameters must declare finite `min` and
`max`, exactly as at `@register_module`.

Two packs that declare the same module — in Python and in Node — normalize to
**identical rows**. `tests/core/pack/test_node_example_pack.py` asserts it.

## Bindings

### `subprocess-jsonrpc`

`runtime.language` names an entry in `core/runtime/languages.py` (`python`,
`node`, `typescript`, `deno`, `bun`, `go`, `rust`, `java`, …) and
`runtime.entry` a relative path inside the pack (no `..`, no absolute path,
resolved inside the directory). The pack is registered with a
`PluginManager`, which is wired into the `RuntimeInvoker`
(`set_plugin_manager` previously had no caller). The process starts lazily on
the first call with the whitelisted environment of `core/runtime/process.py`
plus `PYTHONDONTWRITEBYTECODE=1`.

Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout, as for every
flyto-core plugin — `handshake` → `{"pluginVersion"}`, `invoke`
`{"step": <module_id>, "input": <params>, "context": {...}, "timeoutMs"}` →
`{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message"}}`,
`ping`, `shutdown`.

### `http`

`POST <endpoint>/v1/invoke` with
`{"contract_version": "flyto.pack.v1", "module_id", "params", "context"}`; the
reply must carry `"contract_version": "flyto.pack.v1"` and a boolean `ok`.
The endpoint and bearer token come from host configuration derived from the
pack's first namespace — `FLYTO_PLUGIN_ENDPOINT__<NAMESPACE>`,
`FLYTO_PLUGIN_TOKEN__<NAMESPACE>` — never from the manifest. `runtime.locality`
is enforced on every call without DNS: `same_host` requires a loopback
literal; `same_network` requires an exact entry in
`FLYTO_PLUGIN_ENDPOINT_ALLOWED_HOSTS` (comma-separated). Redirects are not
followed. Optional `max_response_bytes` (default 1 MiB, max 16 MiB).

### What a pack process receives

Parameters (validated against `params_schema` first) and a context of
identifiers only: `pack_id`, `module_id`, and `execution_id` when it is a
string. Never the execution context — secrets, credentials, browser handles
and host authority do not cross the boundary.

## Tree digest

`sha256:` + SHA-256 over the sorted lines
`<posix relative path> NUL <file sha256 hex> NUL <size> LF`, for every regular
file in the pack except `flyto-pack.json` and `flyto-pack.sig.json`. A symbolic
link or special file anywhere in the tree fails closed. Bounded at 10,000 files
and 512 MiB. `flyto pack digest DIR` prints it.

## Publisher signature

`flyto-pack.sig.json`, beside the manifest:

```json
{"schema": "flyto.pack-signature.v1", "algorithm": "ed25519",
 "key_id": "example-publisher", "manifest_sha256": "<hex>", "signature": "<base64>"}
```

The signed message is `b"flyto.pack-signature.v1\n" + canonical(normalized
manifest)`, where canonical is sorted keys, no whitespace, UTF-8. Because the
manifest carries `artifact.digest`, one signature covers the declared surface
and the code that runs; a signature over a manifest without a digest is
refused. Formatting changes to the file do not invalidate it; any change in
meaning does.

Verification is offline against a host-supplied trusted key set
(`{key_id: public key}` — raw 32 bytes, base64, PEM, or a key object). An
unknown key id is a refusal. `install_pack` requires a signature by default
(`require_signature=False` opts out); a signature that is present is always
verified. ed25519 needs the `cryptography` package (`flyto-core[crypto]`).

## Installing

```python
from core.pack.host import install_pack, uninstall_pack, installed_packs

provenance = install_pack(
    "/opt/packs/greeter",
    trusted_keys={"example-publisher": open("publisher.pub").read()},
    provenance_dir="/var/lib/flyto/provenance",   # optional
)
```

Order: read and normalize the manifest → refuse a non-loadable binding →
`min_host` → recompute and compare the tree digest → verify the signature →
register the runtime → register the modules in one `ModuleRegistry`
transaction owned by `pack.id` (any failure, including a module id another
owner already holds, rolls the whole pack back) → wire the invoker → record
provenance. Every refusal raises `PackManifestError` and leaves the registry,
the plugin manager and the installed set unchanged.

The provenance record (`flyto.pack-provenance.v1`) holds the pack id and
version, binding, normalized-manifest SHA-256, artifact digest, signature key
id and algorithm (or `null`), whether a signature was verified, module ids,
source path, install time and host version. It is returned, listed by
`installed_packs()`, and written to `provenance_dir` when given.

A forced rediscovery (`discover_plugins(force=True)`,
`refresh_capability_manifest()`) keeps installed packs.

## CLI

```
flyto pack manifest <entry-point|module:callable> [--pack-id ID] [--version V] [-o FILE]
flyto pack digest <dir>
flyto pack keygen --private FILE --public FILE
flyto pack sign <dir> --key PRIVATE_PEM --key-id ID
flyto pack verify <dir> [--trusted-key ID=FILE ...] [--allow-unsigned]
```

## Example

`examples/packs/node-greeter/` is a Node.js pack with a 120-line,
dependency-free helper (`flyto.js`): `registerModule({...})` takes the
`@register_module` field names plus a `handler`; `node index.js --manifest`
prints the manifest; `node index.js` serves JSON-RPC.

## Relation to `flyto.plugin.v1`

`flyto.plugin.v1` ([spec](PLUGIN_MANIFEST_SPEC.md)) remains the inert adoption
contract for `http`/`inprocess-python` plugins with a JSON-Schema parameter
subset and evidence declarations. `flyto.pack.v1` is the registry row itself,
so a decorator export round-trips without translation. See `DECISIONS.md`,
2026-10-04 "A module pack is the registry row as JSON".

## Not covered

- No operating-system sandbox: a subprocess pack runs with the rights of the
  user running flyto-core, as every out-of-process plugin does.
- No registry, download or key distribution: the host supplies directories and
  keys.
- The digest is checked at install time and the process starts lazily from the
  same directory, so the directory must be owned by the host and not writable
  by the pack's publisher or by the pack process itself.
- Upgrading is explicit: installing an id that is already installed is refused
  (`ALREADY_INSTALLED`); uninstall first.
- flyto-cloud does not yet call `install_pack`; its worker still discovers
  `plugin.yaml` plugins only.
