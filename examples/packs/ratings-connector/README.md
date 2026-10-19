# Example connector pack: ratings

A provider pack that has no code. `flyto-pack.json` declares a `connector`
section, and flyto-core turns each declared operation into a module when the
pack is installed:

| Operation | Module | Consequence |
| --- | --- | --- |
| `company.get` | `ratings.company.get` | observe |
| `findings.list` | `ratings.findings.list` (offset pagination) | observe |
| `portfolio.list` | `ratings.portfolio.list` | observe |

The token is never in the pack. `auth[0].credential` names a credential,
`ratings_api_token`, and the host supplies its value at call time through the
execution context's `secrets` layer. `scheme: Basic` sends the token as the
user name with an empty password.

`findings.list` marks `$.items[*].assets` sensitive. Those leaves are redacted
in step logs and the trace. The workflow still gets them in the step result.

```bash
flyto pack verify examples/packs/ratings-connector --allow-unsigned
flyto pack conform examples/packs/ratings-connector --static-only
```

`api.ratings.example` is a placeholder. The tests run this pack against a
local fake server (`tests/core/pack/test_connector_runtime.py`). To start a
connector from a provider's OpenAPI document, run
`flyto pack import-openapi openapi.json`. Every imported operation comes out
with no `consequence`, so the pack does not validate until a person has set
each one.
