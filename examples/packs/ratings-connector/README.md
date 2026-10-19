# Example connector pack: ratings

A provider pack that has no code. `flyto-pack.json` declares a `connector`
section, and flyto-core turns each declared operation into a module when the
pack is installed:

| Operation | Module | Consequence | Requires |
| --- | --- | --- | --- |
| `account.entitlements` | `ratings.account.entitlements` (the probe) | observe | nothing |
| `company.get` | `ratings.company.get` | observe | `ratings` |
| `findings.list` | `ratings.findings.list` (offset pagination) | observe | `ratings` |
| `portfolio.list` | `ratings.portfolio.list` | observe | `ratings` |
| `portfolio.add` | `ratings.portfolio.add` (uses one `monitoring_slots`) | external_write | `monitoring` |

The token is never in the pack. `auth[0].credential` names a credential,
`ratings_api_token`, and the host supplies its value at call time through the
execution context's `secrets` layer. `scheme: Basic` sends the token as the
user name with an empty password.

`findings.list` marks `$.items[*].assets` sensitive. Those leaves are redacted
in step logs and the trace. The workflow still gets them in the step result.

The provider decides what the account holds. `entitlements` names the probe
operation and where its answer lists features and the meter's remaining
amount. An account without `monitoring` is never offered `portfolio.add`,
and calling it anyway is refused before any request. `scopes` declares the
`company` dimension. A member's `scope_grants` in the execution context say
which companies Flyto2 may work on for them: an input outside the grant is
refused, and portfolio rows outside it are dropped and counted. The
provider's own access control still applies underneath; the grant only
narrows.

```bash
flyto pack verify examples/packs/ratings-connector --allow-unsigned
flyto pack conform examples/packs/ratings-connector --static-only
```

The `standalone` section makes it a portable pack: the same zip runs on its
own as an MCP server and loads into a Space. Building it needs a lockfile
that pins and hashes flyto-core (`--lock`); the tests use a fixture lock
whose hash is not of a real wheel.

```bash
flyto pack build examples/packs/ratings-connector --lock requirements.lock -o ratings.zip
flyto pack run ratings.zip --allow-unsigned            # MCP over stdio
```

`api.ratings.example` is a placeholder. The tests run this pack against a
local fake server (`tests/core/pack/test_connector_runtime.py`). To start a
connector from a provider's OpenAPI document, run
`flyto pack import-openapi openapi.json`. Every imported operation comes out
with no `consequence`, so the pack does not validate until a person has set
each one.
