# Build a provider pack

This guide is for a provider that ships its own pack, such as a security-rating
vendor, an issue tracker or a robot vendor. The pack is the provider's API declared
as data (`flyto.pack.v1` with `runtime.binding: connector`). The same signed zip
runs on its own as an MCP server with the customer's own credential, and it loads
into a Flyto2 Space unchanged. You need flyto-core and nothing from Flyto2:
no account, no service, and no review.

`tests/core/pack/test_build_a_pack_guide.py` runs every command on this page, in
order, exactly as written. A trailing `# exit 1` is the exit code that command
promises. Nothing on the page reaches a real provider.

The formats are defined in [the pack manifest spec](../specs/PACK_MANIFEST_SPEC.md),
and every command is listed in [the CLI guide](../CLI.md).

## 1. Scaffold

```sh
flyto pack init items-pack --pack-id com.example.items
```

`init` writes three things:

- `flyto-pack.json`, with a `connector` (where the API is, how a call
  authenticates, each operation), `entitlements` (the probe operation that
  reads what the account holds), `scopes` and `standalone`;
- `fixtures/exchanges.json`, the recorded exchanges `flyto pack test` answers
  from;
- `tests/test_pack.py`, which runs that same test under pytest.

To start from your OpenAPI 3 document instead, pass `--openapi`. See
[step 7](#7-start-from-an-openapi-document).

## 2. Decide every consequence

A consequence says what a call does to the world: `observe`, `reversible`,
`external_write`, `real_world` or `irreversible`. Hosts grade every operation by
it, and a standalone server turns it into the MCP tool annotations. The scaffold
never sets one, and the HTTP method is not read as one, because a GET can start a
scan and a POST can be a search. Until you decide each operation, the pack does
not validate and does not build, and the refusal names every operation still
undecided.

```sh
flyto pack doctor items-pack  # exit 1
flyto pack consequence items-pack account.entitlements=observe item.get=observe
flyto pack doctor items-pack
```

`doctor` explains each refusal, giving the code, the cause and the fix. It also
checks each operation on its own, so you see every operation that needs work in
one pass.

## 3. Test against recorded exchanges

```sh
flyto pack test items-pack
```

`pack test` starts a loopback fake provider built from `fixtures/exchanges.json`
alone. It installs the pack against it and makes each recorded call through the
real connector runtime and pre-check gate: the credential resolved by name, the
entitlements probe, the scope grants and the result filter. The fake identifies
the customer by the credential the runtime actually sent. The report covers each
operation and lists typed failures:

- a `sensitive` path or `paginate.data_path` that names nothing in any recorded
  answer;
- a `result_scope` that never named an item;
- a probe answer outside the declared `entitlements` shape;
- a request nobody recorded;
- an operation no call exercises;
- a customer offered other operations than its fixture says.

Then it runs the offline conformance suite (`pack conform`). It exits 0 only when
everything passes.

The fixtures hold **test** credential values, never real ones. Record what the
provider answers, with values invented, and state what each call should come back
as: `{"ok": true}` by default, or `{"error_code": "OUT_OF_SCOPE"}` for a refusal
you expect.

## 4. Build and sign

```sh
flyto pack keygen --private publisher.pem --public publisher.pub
flyto pack build items-pack --lock requirements.lock --key publisher.pem --key-id publisher-1 -o items-0.1.0.zip
flyto pack verify items-0.1.0.zip --trusted-key publisher-1=publisher.pub
```

`--lock` is your hashed lockfile in pip `--require-hashes` format. It must pin
flyto-core at the pack's `min_host` or later. The build generates the entry points
for each platform, a README and the third-party notice. It sets
`artifact.digest`, signs the manifest and verifies the result before it writes the
zip. Keep `publisher.pem` private and give your customers `publisher.pub`.

## 5. Run it standalone

A customer runs the same zip with their own credential. The credential is named in
the pack (`items_api_token`), and its value comes from the environment (or the OS
keychain), never from the pack:

```sh
export FLYTO_CREDENTIAL_ITEMS_API_TOKEN=your-provider-token
flyto pack health items-0.1.0.zip --trusted-key publisher-1=publisher.pub
flyto pack run items-0.1.0.zip --trusted-key publisher-1=publisher.pub
```

`health` verifies the pack and reports each credential name and where its value
would come from, never the value itself. `run` serves the operations as MCP tools
over stdio; add `--transport streamable_http` for loopback HTTP.

## 6. Load it into a Space

A Space installs the same zip from a file, through the same `install_pack` call
the standalone server uses:

```python
from pathlib import Path

from core.pack.host import install_pack
from core.pack.portable import extract_pack_zip

Path("space-copy").mkdir()
extract_pack_zip("items-0.1.0.zip", "space-copy")
provenance = install_pack("space-copy", trusted_keys={"publisher-1": Path("publisher.pub").read_text()})
assert provenance.signature_verified
print(provenance.module_ids)
```

Each operation is a module with the same id (`items.item.get`), and the Space
supplies the credential under the same name.

## 7. Start from an OpenAPI document

<!-- file: openapi.yaml -->
```yaml
openapi: 3.0.3
info: {title: Example tracker API, version: "1.0"}
servers: [{url: "https://api.tracker.example"}]
components:
  securitySchemes:
    token: {type: http, scheme: bearer}
paths:
  /v1/account:
    get: {operationId: getAccount}
  /v1/issues/{issue}:
    get:
      operationId: getIssue
      parameters: [{name: issue, in: path, required: true, schema: {type: string}}]
  /v1/issues/{issue}/close:
    post:
      operationId: closeIssue
      parameters: [{name: issue, in: path, required: true, schema: {type: string}}]
```

```sh
flyto pack init tracker-pack --openapi openapi.yaml --pack-id com.example.tracker --probe get_account
flyto pack doctor tracker-pack  # exit 1
flyto pack consequence tracker-pack get_account=observe get_issue=observe close_issue=external_write
flyto pack test tracker-pack  # exit 1
```

The draft carries over what the document states: the server, the security
schemes (as credential names), each path, its parameters and its JSON body. It
writes one call per operation and records no response, because it did not see
one. So `pack test` fails with `UNRECORDED_REQUEST`, naming each request to
record, until you add the provider's answers to `exchanges`. Then name the
features each operation needs (step 8).

## 8. Product combinations

A provider whose customers hold different product combinations declares each
product as a feature. Each operation then lists the features it requires; all of
them are needed, or write `{"any": [...]}` when one is enough. The probe reads
which products the account holds from the provider itself, so the provider stays
the authority. The pre-check only hides operations the account does not hold, and
it stops those calls before they are sent.

`examples/packs/product-combinations` has three products and an operation that
needs two:

<!-- excerpt: examples/packs/product-combinations/flyto-pack.json -->
```json
{
  "connector": {
    "operations": [
      {"id": "record.get", "requires": {"features": ["records"]}},
      {"id": "plan.get", "requires": {"features": ["planning"]}},
      {"id": "trend.get", "requires": {"features": ["analytics"]}},
      {"id": "plan.forecast", "requires": {"features": ["planning", "analytics"]}}
    ]
  },
  "entitlements": {
    "probe": "account.entitlements",
    "features": {"keys": ["records", "planning", "analytics"], "path": "$.products[*]"}
  }
}
```

| The customer holds | Offered besides the probe |
|---|---|
| nothing | nothing |
| records | `record.get` |
| planning | `plan.get` |
| analytics | `trend.get` |
| records, planning | `plan.get`, `record.get` |
| records, analytics | `record.get`, `trend.get` |
| planning, analytics | `plan.forecast`, `plan.get`, `trend.get` |
| all three | `plan.forecast`, `plan.get`, `record.get`, `trend.get` |

The fixtures declare one customer per combination, each with the operations it
must be `offered`. `pack test` checks each listing through
`effective_module_ids`, the same listing a host shows. A customer holding only
`planning` who calls `plan.forecast` is refused with `FEATURE_NOT_ENTITLED` and
`missing_features: ["analytics"]`, and no request reaches the provider.

```sh
flyto pack test examples/packs/product-combinations
```

`tests/core/pack/test_product_combinations.py` checks all eight rows of the table
above, written out by hand.
