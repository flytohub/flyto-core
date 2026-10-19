# Flyto2 Module Pack Manifest — `flyto.pack.v1`

Status: **implemented in flyto-core 2.37.0** (`core.pack`). Validation,
normalization, tree digest, ed25519 signature verification, out-of-process
installation (`subprocess-jsonrpc`, `http`) and Python export are implemented
and tested. Installation is explicit: nothing scans a directory or downloads a
pack.

**2.41.0 (unreleased)** adds [portable packs](#portable-packs-standalone-2410):
one artifact that runs on its own as an MCP server and loads into a Flyto2
Space unchanged (`standalone` section, `flyto pack build|run|health`), the
[supply chain](#supply-chain-2410) around it (pack digest, hashed lockfile,
signed revocation list), and [bundles](BUNDLE_SPEC.md).

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
| `standalone` | Optional (2.41.0). How the pack runs on its own. See [Portable packs](#portable-packs-standalone-2410). |

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

### `connector` (2.41.0)

A provider pack with no code. `runtime` is `{"binding": "connector"}` with the
optional `request_timeout_ms` and `max_response_bytes`. The pack declares a
`connector` section instead of `modules`, and has exactly one namespace.
Each operation becomes one module, `<namespace>.<operation id>`, registered
through `@register_module` like any other row. One generic runtime
(`core.pack.connector_runtime`) runs every operation. No code is generated
per provider or per operation.

```json
"connector": {
  "base_url": "https://api.provider.example",
  "auth": [{"kind": "api_token", "header": "Authorization", "scheme": "Basic",
            "credential": "provider_api_token"}],
  "rate_limit": {"requests": 100, "per_seconds": 60},
  "operations": [{
    "id": "findings.list", "method": "GET", "path": "/v1/companies/{company}/findings",
    "consequence": "observe",
    "inputs": {"company": {"type": "string", "scope": "company"},
               "severity": {"type": "string"}},
    "result_scope": {"dimension": "company", "path": "$.items[*].guid"},
    "sensitive": ["$.items[*].assets"],
    "requires": {"features": ["ratings"]},
    "consumes": {"meter": "lookups", "amount": 1},
    "paginate": {"strategy": "offset", "data_path": "results", "page_size": 100}
  }]
}
```

- **`base_url`**: `https`, or `http` to a loopback host for local development.
  It may not carry userinfo.
- **`auth`**: up to four entries. `api_token` has `header` and an optional
  `scheme`. `oauth2_client_credentials` has `token_url` and optional `scopes`.
  `oauth2_authorization_code` has `authorize_url`, `token_url` and optional
  `scopes`. Each entry names its `credential`; none holds a value. At call
  time the runtime uses the first entry whose credential the host supplies in
  the execution context's `secrets` layer, by that name. If the host supplies
  none, the call fails with `CREDENTIAL_MISSING` before any request is sent.
  `scheme: Basic` sends a bare token as the user name with an empty password,
  and sends a `{username, password}` credential as that pair.
  `oauth2_client_credentials` exchanges `client_id`/`client_secret` at
  `token_url` and reuses the token until it expires.
  `oauth2_authorization_code` sends the access token the host keeps fresh.
- **`rate_limit`**: one token bucket shared by all of the pack's operations.
- **`operations[]`**:
  - `consequence` is one of the platform's levels: `observe`, `reversible`,
    `external_write`, `real_world`, `irreversible`. The row's
    `flyto.capability-contract.v1` contract states it as a safety class and an
    effect class (`core.pack.connector.CONSEQUENCE_CONTRACTS`), so a host
    grades the operation from the contract alone.
  - `inputs` are JSON-schema typed parameters and become the row's
    `params_schema`. An input goes `in` the path, the query or the body. By
    default a `{name}` in the path goes in the path, GET and DELETE send the
    rest in the query, and POST, PUT and PATCH send it in a JSON body. Path
    inputs are always required, and each one is encoded as a single segment.
    `secret: true` redacts the input in step logs.
  - `sensitive` and `result_scope` are JSONPaths (`$`, `.name`, `['name']`,
    `[n]`, `[*]`) into the operation's data: the body, or
    `{"items", "pages_fetched"}` for a paginated operation. Sensitive leaves
    are redacted in the step log and the trace
    (`BaseModule.sensitive_result_paths`), and the workflow still receives
    them.
  - `paginate` uses the `http.paginate` shapes (`offset`, `page`, `cursor`,
    `link_header`) with the same keys. A Link-header page must stay on the
    pack's origin.
  - `requires.features` is a list (all needed), or `{"any": [...]}`.
    `consumes` is `{meter, amount}`. An input's `scope` and the operation's
    `result_scope` name a data-scope dimension. The pre-check below enforces
    all four.
- **Refusals** are typed, and their `operation` attribute names the
  operation: `CONSEQUENCE_MISSING`, `CONSEQUENCE_UNKNOWN`,
  `PATH_PARAM_UNDECLARED`, `INLINE_SECRET` (a value-bearing auth key, a
  credential that is not a name, a secret-looking default, userinfo in a URL),
  `UNKNOWN_AUTH_KIND`, `INVALID_JSONPATH`, `INVALID_PAGINATION`,
  `CONNECTOR_REQUIRED`, `CONNECTOR_BINDING`, `MODULES_DERIVED`, and for the
  pre-check sections `ENTITLEMENTS_REQUIRED`, `FEATURE_UNDECLARED`,
  `METER_UNDECLARED`, `SCOPE_UNDECLARED`, `RESULT_SCOPE_DIMENSION_REQUIRED`,
  `PROBE_UNKNOWN`, `PROBE_NOT_OBSERVE`, `RESOLVE_UNKNOWN`,
  `INVALID_ENTITLEMENTS`, `INVALID_SCOPES`.
- **Calls** go through the platform SSRF guard and follow no redirects. They
  return `{"ok": true, "data": <body>}` or a typed failure carrying
  `error_code` and `http_status`: `PROVIDER_UNAUTHORIZED` (401),
  `PROVIDER_QUOTA_REFUSED` (402), `PROVIDER_FORBIDDEN` (403), `PROVIDER_NOT_FOUND` (404),
  `PROVIDER_RATE_LIMITED` (429, with `retry_after_s`), `PROVIDER_REJECTED`
  (other 4xx), `PROVIDER_ERROR` (5xx), `PROVIDER_INVALID_RESPONSE`,
  `PROVIDER_TIMEOUT`, `PROVIDER_UNREACHABLE`, `SSRF_BLOCKED`. A failure on any
  page fails the whole call.

### The pre-check: `entitlements` and `scopes` (2.41.0)

The provider is the source of truth for its own product, and a customer can
use it directly without Flyto2. The provider's own access control always
applies underneath. Flyto2 adds collaboration policy on top: a pre-check that
hides operations the account does not hold and stops a call early. It never
authorizes provider access. Whatever a cached answer said, a provider refusal
of an admitted call is final and comes back as its own typed failure
(`PROVIDER_FORBIDDEN`, `PROVIDER_QUOTA_REFUSED`, ...), and a refused call is
never retried.

```json
"entitlements": {
  "probe": "account.entitlements",
  "max_age_s": 900,
  "features": {"keys": ["ratings", "monitoring"], "path": "$.features[*]"},
  "meters": {"monitoring_slots": "$.meters.monitoring_slots.remaining"}
},
"scopes": [{"key": "company", "resolve": "portfolio.list"}]
```

- **`entitlements.probe`** names an ungated `observe` operation of the same
  connector. Its answer is mapped through the declared JSONPaths: `features`
  to the set of declared keys it lists (a listed key the pack does not
  declare is ignored), and each meter to its remaining amount, a non-negative
  integer. Any other shape is unreadable.
- The answer is read **per credential** and cached for `max_age_s` (default
  900, at most 86,400). A read may use the cache. A write, a quota-consuming
  call, and any call after a provider error read the probe again. A probe
  that fails or answers outside its shape drops the cached answer and refuses
  every feature-gated operation with `PROVIDER_ENTITLEMENT_UNREADABLE`.
- **`scopes`** declares the dimensions the provider's data is split by. A
  text `result_scope` names the one declared dimension; with two or more it
  must be `{"dimension", "path"}`.
- Every feature, meter and dimension an operation names must be declared, or
  the pack is refused.

`core.pack.connector_gate.admit` is the one gate, run for every operation
before the request, in this order:

1. `requires.features` must be held, else `FEATURE_NOT_ENTITLED` with
   `missing_features`.
2. The execution context's `scope_grants` must grant every dimension the
   operation uses, else `SCOPE_GRANT_MISSING`; an absent grant is never read
   as `"*"`. The grant is a `core.pack.connector_gate.ScopeGrants` the host
   makes from `{dimension: [values] | "*"}`. A plain mapping under the key
   is no grant, because step results (by step id) and a caller's variables
   land in the same context. Each scoped
   input must be inside its grant, else `OUT_OF_SCOPE`. Grants only narrow
   what Flyto2 runs for a member; they never widen what the provider
   credential can see.
3. A `consumes` meter must have `remaining >= amount`, else `QUOTA_EXHAUSTED`.

After the call, the result is filtered by `result_scope`: the items are the
elements under its last `[*]`, and items outside the grant are dropped and
counted. An item that does not name exactly one scalar scope value refuses
the whole result (`RESULT_SCOPE_UNREADABLE`); a result without `[*]` that is
outside the grant is refused (`OUT_OF_SCOPE`), never shown as empty. A
pre-checked result carries `metadata.precheck`: where the answer came from
(`provider` or `cache`), the features required, the scope counts, and for a
quota-consuming call `{meter, amount, before, after, matches}`, with the
meter read again after the call.

`core.pack.host.effective_module_ids(pack_id, secrets)` lists the operations
a credential is entitled to, through the same probe and cache. An operation
whose features the answer does not hold is omitted, not marked.

Only the credential the pack names, resolved from `secrets`, is sent to the
provider. Nothing else in the execution context, such as an inbound client's
bearer token or request headers, reaches it.

`flyto pack import-openapi DOC` drafts a `connector` section from an OpenAPI 3
document and lists what it could not map. It never sets `consequence`, so the
draft is refused until a person has decided each one.

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
`min_host` → verify the signature → refuse an id already installed → copy the
attested files into a host-private directory (`subprocess-jsonrpc` only) and
compare the digest of that copy with `artifact.digest` (`http` packs digest
the source in place) → register the runtime against the copy → register the
modules in one `ModuleRegistry` transaction owned by `pack.id` → wire the
invoker → record provenance. Every refusal raises `PackManifestError` and
leaves the registry, the plugin manager, the installed set and the staging
area unchanged. Installs are serialized; two concurrent installs of one id
install it once.

A subprocess pack's process is spawned lazily, on its first call, and is
respawned after a crash. It always runs from the private copy, whose bytes are
the bytes the digest was computed over, so editing or replacing the source
directory after install cannot change the code that runs. `uninstall_pack`
removes the copy.

The registry transaction refuses, and rolls the whole pack back, when:

- a module id is already held by another owner (flyto-core, a Python pack, or
  another external pack);
- a declared namespace is already held by another owner — any registered
  module in it whose owner is not this pack, or another installed external
  pack that declared it. The static reserved list cannot name every namespace
  flyto-core ships (`capability`, `vision`, ...) nor any Python pack's, so this
  is checked against the live registry;
- a module declares a `provides_capability` that another owner already
  provides with a different contract, or with none. The capability host fails
  closed when providers disagree, so a differing declaration would turn an
  existing `role: safe_stop` capability into a refused call. A second provider
  whose contract is identical is allowed.

The provenance record (`flyto.pack-provenance.v1`) holds the pack id and
version, binding, normalized-manifest SHA-256, artifact digest, signature key
id and algorithm (or `null`), whether a signature was verified, module ids,
source path, install time and host version. It is returned, listed by
`installed_packs()`, and written to `provenance_dir` when given.

A forced rediscovery (`discover_plugins(force=True)`,
`refresh_capability_manifest()`) keeps installed packs.

## Portable packs: `standalone` (2.41.0)

Flyto2 is not a gateway. A pack must run on its own, as a standalone MCP
server with the user's own credentials and no Flyto2 service involved, and
the same pack must load into a Flyto2 Space. One artifact, two ways to run,
no second version to maintain. Nothing is published to a marketplace:
installation is private, from a file or a folder.

### The section

The author writes three keys (`core.pack.portable`):

```json
"standalone": {
  "transports": ["stdio", "streamable_http"],
  "runtime": {"language": "python", "version": ">=3.10"},
  "lockfile": "requirements.lock"
}
```

| Key | Rule |
| --- | --- |
| `transports` | Each of `stdio`, `streamable_http` at most once, at least one. |
| `runtime` | `{language, version}`. The language is the one the binding's runtime is written in (`STANDALONE_RUNTIMES`: a `connector` pack runs on flyto-core, so `python`); `version` is a floor, `>=X.Y`, because that is what an install script can check. |
| `lockfile` | A relative path inside the pack, not under `bin/` and not a file the build writes. |

Only the `connector` binding can be standalone today: it is the binding whose
runtime is core's own. Any other binding is refused with
`STANDALONE_BINDING_UNSUPPORTED`.

Normalization derives the rest, so the signed manifest carries it and no
second hand-written copy can disagree (`credentials`, `credentials_needed` or
`entry_points` in the source are refused with `STANDALONE_DERIVED`):

```json
"standalone": {
  "transports": ["stdio", "streamable_http"],
  "runtime": {"language": "python", "version": ">=3.10", "package": "flyto-core"},
  "lockfile": {"path": "requirements.lock", "format": "pip-require-hashes"},
  "credentials": [{"name": "ratings_api_token",
                   "env": "FLYTO_CREDENTIAL_RATINGS_API_TOKEN",
                   "keychain": {"service": "flyto.pack.com.example.ratings",
                                "account": "ratings_api_token"}}],
  "credentials_needed": "one_of",
  "entry_points": {
    "macos": {"install": ["sh", "bin/macos/install.sh"],
              "healthcheck": ["sh", "bin/macos/healthcheck.sh"],
              "serve": {"stdio": ["sh", "bin/macos/serve.sh", "--transport", "stdio"],
                        "streamable_http": ["sh", "bin/macos/serve.sh", "--transport", "streamable_http"]}},
    "linux": {"...": "the same, under bin/linux/"},
    "windows": {"install": ["cmd.exe", "/d", "/c", "bin\\windows\\install.cmd"], "...": "..."}
  }
}
```

- **Credentials** are the names in `connector.auth`, in order, never a value.
  Run standalone, each value is read at call time from
  `FLYTO_CREDENTIAL_<NAME>`, then from the OS keychain (service
  `flyto.pack.<pack id>`, account `<name>`; macOS `security`, Linux
  `secret-tool`, Windows through the optional `keyring` package;
  `FLYTO_PACK_NO_KEYCHAIN=1` reads the environment only). In a Space the same
  names come from the Space's `secrets` layer. `credentials_needed` is
  `one_of` when the connector declares auth (it uses the first entry whose
  credential resolves) and `none` otherwise.
- **Entry points** are commands relative to the unpacked pack directory, one
  set per row of `PLATFORMS` (`macos`, `linux`, `windows`). They are
  generated by core from the manifest, never written per pack.

### Building

`flyto pack build DIR --lock FILE [-o ZIP] [--key PEM --key-id ID]`
(`build_portable_pack`):

1. validates the manifest; a pack with no `standalone` section is refused
   (`STANDALONE_MISSING`), and so is a source that holds a path the build
   writes (`bin/…`, `THIRD_PARTY_NOTICES.md`: `RESERVED_PATH`);
2. places the lockfile at `standalone.lockfile` and checks it (below);
3. writes, from the manifest and the platform table alone:
   `bin/<platform>/{install,healthcheck,serve}.{sh|cmd}`, a `README.md` (how
   to run it, the credential names and where they are read from, the tools
   and their consequences, how to load it into a Space; an author's
   `README.md` is kept under "About this pack"), and
   `THIRD_PARTY_NOTICES.md` (every distribution the lockfile installs, with
   its hashes);
4. sets `artifact.digest` over the result, signs the manifest when a key is
   given, verifies what it built as a host would, and writes one zip.

The zip holds the pack directory at its root. Entries are sorted, timestamped
1980-01-01, mode 0644 (0755 for the POSIX scripts) and deflated, so two builds
of one source are byte-identical. The output file must not exist
(`OUTPUT_EXISTS`).

The scripts contain no server code. `install` checks the Python floor,
creates the pack's environment outside the pack directory
(`$FLYTO_PACK_HOME/<pack id>/<version>/venv`, defaulting per platform), and
runs `pip install --require-hashes --only-binary=:all: -r <lockfile>`.
`serve` runs `flyto pack run <pack dir> "$@"`, and `healthcheck` runs
`flyto pack health <pack dir> "$@"`, from that environment.
`tests/core/pack/test_portable_pack.py` scans every file of a built zip and
fails if it imports, runs or names anything but that flyto-core runtime (no
Flyto2 Cloud or Desktop internal).

Reading a zip (`extract_pack_zip`) checks every entry before writing any:
an absolute path, `..`, a drive, a backslash (`ZIP_UNSAFE_PATH`), a symlink
(`ZIP_SYMLINK`), two names that collide case-insensitively or a file that is
also a directory (`ZIP_DUPLICATE`), an encrypted entry or a non-zip
(`ZIP_INVALID`), a tree beyond the pack bounds (`PACK_TOO_LARGE`), and a zip
with no `flyto-pack.json` at its root (`ZIP_NO_MANIFEST`).

### Running standalone

`flyto pack run ZIP|DIR [--transport stdio|streamable_http] [--port N]`
(`core.pack.standalone`) is one generic runtime for every connector pack:

1. the transport must be one the pack declares (`TRANSPORT_NOT_DECLARED`);
2. the pack is verified: the revocation list first (`PACK_REVOKED`), then
   `artifact.digest`, the portable tree (`PACK_NOT_BUILT`,
   `ENTRY_POINT_MISSING`, `LOCKFILE_MISSING`, the lockfile rules) and the
   signature (`UNSIGNED` unless `--allow-unsigned`, `UNTRUSTED_KEY` without
   `--trusted-key`);
3. it is installed with `install_pack`, the call a Space makes, so each tool
   is the same registered module behind the same policy gate;
4. it is served with `core.mcp_protocol`, the protocol code core's own MCP
   server uses (STDIO and Streamable HTTP, MCP 2024-11-05 through
   2026-07-28).

`tools/list` lists one tool per operation, named by its module id, with an
`inputSchema` from the operation's inputs and annotations from its
consequence (`connector.CONSEQUENCE_ANNOTATIONS`):

| Consequence | `readOnlyHint` | `destructiveHint` | `idempotentHint` |
| --- | --- | --- | --- |
| `observe` | true | false | true |
| `reversible` | false | false | false |
| `external_write` | false | false | false |
| `real_world` | false | true | false |
| `irreversible` | false | true | false |

`openWorldHint` is always true: every call reaches an outside system.
`tools/call` resolves the credentials by name for that call and runs the
module. The result is the connector runtime's own: `{"ok": true, "data": …}`
or its typed failure (`CREDENTIAL_MISSING` before any request,
`PROVIDER_UNAUTHORIZED`, `PROVIDER_RATE_LIMITED`, …), with `isError` set.

Over stdio only JSON-RPC reaches stdout. Over Streamable HTTP the server
binds a loopback address only (`HTTP_BIND_REFUSED` otherwise), serves `/mcp`,
and needs `Authorization: Bearer <token>` on every request; the token is
`FLYTO_PACK_HTTP_TOKEN` (at least 32 characters, `HTTP_TOKEN_WEAK`
otherwise) or one generated and printed to stderr. A request whose `Origin`
is not loopback is refused with 403, so a web page cannot reach the user's
credentials through it.

`flyto pack health ZIP|DIR` makes the same checks without serving or calling
the provider, and reports the runtime it runs on, each credential's name and
source (`env`, `keychain`, `missing`; never a value) and the tool count. It
exits 1 when a needed credential is missing (`CREDENTIAL_MISSING`) or the
runtime is older than the floor.

## Supply chain (2.41.0)

`core.pack.supply_chain`.

- **Pack digest.** `sha256:` + the hex `manifest_sha256` of the normalized
  manifest. The manifest carries `artifact.digest`, so this one value names
  what the pack says and every file it ships. `flyto pack verify` and
  `flyto pack build` print it; bundles pin it; revocation lists name it.
- **Signing** is the existing ed25519 step, unchanged for packs. The signing
  primitive is now `sign_detached(domain, document, key, key_id)` /
  `verify_detached`, with one domain per document type
  (`flyto.pack-signature.v1`, `flyto.bundle-signature.v1`,
  `flyto.pack-revocations.v1`), so a signature over one can never be replayed
  as another.
- **Lockfile** (`pip-require-hashes`): pip's hash-checking requirements
  format. Every line is `name==version` with at least one
  `--hash=sha256:<hex>`; an option (`-e`, `-r`, `--index-url`), a URL, a range
  or an unhashed line is refused (`LOCKFILE_INVALID`), and so is a package
  pinned twice. The runtime package must be pinned (`LOCKFILE_RUNTIME_MISSING`)
  at the pack's `min_host` or later (`LOCKFILE_RUNTIME_TOO_OLD`).
- **Revocation list** (`flyto.pack-revocations.v1`):

  ```json
  {"schema": "flyto.pack-revocations.v1",
   "list": {"sequence": 3, "issued_at": "2026-10-19T00:00:00Z",
            "revoked": [{"digest": "sha256:<pack digest>", "reason": "key_compromise"}]},
   "signature": {"algorithm": "ed25519", "key_id": "…", "signature": "<base64>"}}
  ```

  Reasons are `key_compromise`, `malicious`, `vulnerable`, `withdrawn`,
  `superseded`. A list is verified against the keys the loader trusts to sign
  it (`--revocation-key ID=FILE`); one that does not verify refuses the start
  (`REVOCATION_UNTRUSTED_KEY`, `REVOCATION_SIGNATURE_MISMATCH`,
  `REVOCATION_INVALID`), because it can no longer say the pack is not
  revoked. `install_pack(..., revocations=…)`, `flyto pack run`,
  `flyto pack health`, `flyto pack verify` and `flyto bundle verify` check it
  before anything of the pack is read beyond its manifest. A revoked pack
  refuses to start, standalone or in a Space (`PACK_REVOKED`).
- **Updates** are a new pinned version: a new manifest, a new digest, a new
  zip. A build never writes over an existing file, and installing an id that
  is already installed is refused (`ALREADY_INSTALLED`).

## CLI

```
flyto pack manifest <entry-point|module:callable> [--pack-id ID] [--version V] [-o FILE]
flyto pack digest <dir>
flyto pack keygen --private FILE --public FILE
flyto pack sign <dir> --key PRIVATE_PEM --key-id ID
flyto pack verify <dir> [--trusted-key ID=FILE ...] [--allow-unsigned]
flyto pack conform <dir> [--trusted-key ID=FILE ...] [--static-only] [--json]
flyto pack import-openapi <openapi.json|yaml> [-o FILE]
flyto pack build <dir> --lock FILE [-o ZIP] [--key PRIVATE_PEM --key-id ID]
flyto pack verify <dir|zip> [--trusted-key ID=FILE ...] [--allow-unsigned] [--revocations FILE --revocation-key ID=FILE ...]
flyto pack run <dir|zip> [--transport stdio|streamable_http] [--host 127.0.0.1] [--port N] [trust options]
flyto pack health <dir|zip> [trust options]
flyto bundle build <dir> --pack ZIP ... [-o ZIP] [--key PRIVATE_PEM --key-id ID]
flyto bundle verify <dir|zip> --pack ZIP ... [trust options]
```

Trust options are `--trusted-key`, `--allow-unsigned`, `--revocations` and
`--revocation-key`. Every refusal prints `error [CODE]: …` and exits 1.

## Example

`examples/packs/node-greeter/` is a Node.js pack with a 120-line,
dependency-free helper (`flyto.js`): `registerModule({...})` takes the
`@register_module` field names plus a `handler`; `node index.js --manifest`
prints the manifest; `node index.js` serves JSON-RPC.

`examples/packs/ratings-connector/` is a read-only connector pack with no
code: one company's rating, its findings (offset pagination, a sensitive
path), and a portfolio. The tests run it against a local fake server. It
declares a `standalone` section, so `flyto pack build` turns it into a
portable zip; `tests/core/pack/test_standalone_server.py` runs that zip's
generated `serve` entry point as a subprocess and drives it over stdio as an
MCP client. `examples/bundles/rating-review/` is a bundle that pins it.

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
- Standalone runs only the `connector` binding. The Windows entry points are
  generated and their content is tested, but they have not been run on
  Windows; the install step (which needs a package index) has not been run
  anywhere. No revocation list is distributed: a host supplies one.
