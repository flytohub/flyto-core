# HTTP And MCP API

## Runtime Separation

Flyto2 Core exposes two HTTP applications:

- `flyto serve` starts the local Execution API, normally on `127.0.0.1:8333`.
- `flyto-verification` starts the deterministic verification runner, normally
  on `127.0.0.1:8344`.

They have separate authentication contracts and should not share assumptions.
The generated [HTTP route reference](reference/http-api.md) is the complete
decorator-level inventory.

## Execution API Authentication

At startup, `create_app` initializes a bearer token. `FLYTO_API_TOKEN` supplies
the token; otherwise Core generates one and writes
`~/.flyto/.api-token-<port>` with owner-only permissions.

```http
Authorization: Bearer <token>
```

Non-loopback binding fails closed when authentication is not active.

## Active Execution API Routes

| Method and path | Auth | Behavior |
|---|---|---|
| `GET /health` | Public | Liveness and server version |
| `GET /v1/info` | Public | Runtime capability and catalog counts |
| `GET /v1/modules` | Public | Categories or category-filtered modules |
| `GET /v1/modules/{module_id}` | Public | Module schema and examples |
| `POST /v1/execute` | Bearer | Execute one policy-allowed module |
| `POST /v1/workflow/run` | Bearer | Execute a workflow with trace/evidence options |
| `GET /v1/workflow/{execution_id}` | Bearer | Read execution status and step summary |
| `GET /v1/workflow/{execution_id}/evidence` | Bearer | Read step evidence and outputs |
| `POST /v1/workflow/{execution_id}/replay/{step_id}` | Bearer | Replay a persisted workflow boundary |
| `GET /v1/extensions` | Bearer | Installed extensions of both supported kinds |
| `GET /v1/extensions/kinds` | Bearer | The supported prefixes and entry-point groups |
| `POST /v1/extensions/install` | Bearer + opt-in | Install or upgrade one extension |
| `POST /v1/extensions/uninstall` | Bearer + opt-in | Uninstall one extension |
| `POST /mcp` | Bearer | MCP JSON-RPC and session initialization |
| `GET /mcp` | Public, always 405 | Documents that server-initiated SSE is unsupported |
| `DELETE /mcp` | Bearer | Delete an MCP session |

Module discovery is public metadata. Execution, replay, session mutation, and
evidence-bearing reads require a token. Evidence can contain workflow outputs,
so it is not a public discovery surface.

## Module Execution

`POST /v1/execute` accepts a `module_id`, `params`, and optional context. The
module allow/deny filter applies before lookup. Browser modules use server-side
browser sessions and require a resolvable session except for `browser.launch`.
Responses use the typed `ExecuteModuleResponse` envelope.

## Workflow Execution

`POST /v1/workflow/run` accepts a workflow object, optional parameters, and
trace/evidence switches. The route validates every module against policy before
creating the engine. Evidence-enabled runs persist a redacted workflow copy for
later inspection and replay.

## MCP HTTP

The MCP route supports JSON-RPC requests and batches over POST. Successful
initialization returns an `Mcp-Session-Id`; subsequent calls may present that
session. Authentication is checked before JSON-RPC dispatch, so an invalid
caller cannot reach module execution.

For a process-local transport without an HTTP bind, run:

```bash
python -m core.mcp_server
```

## Extension Management

Core manages exactly two extension shapes, and the pair is the whole contract:

| Kind | Name prefix | Entry-point group |
|---|---|---|
| `modules` | `flyto-modules-` | `flyto.modules` |
| `plugins` | `flyto-plugin-` | `flyto.plugins` |

Nothing is special-cased per extension. A module pack such as
`flyto-modules-robotics` is admitted on its prefix and served by the same code
path as every other pack; no Core source names it.

`GET /v1/extensions/kinds` serves that table from the same object the installer
enforces, so a client's idea of what is installable cannot drift from Core's.

Install requests take the full prefixed distribution name. A bare name is
rejected rather than completed: `robotics` is ambiguous between the two kinds,
and guessing would install a package the caller did not ask for.

An install proceeds as: classify → validate name/version → record the prior
version → run pip → **prove** the installed distribution declares at least one
entry point in its kind's group → refresh the loader manifests and, for the
`modules` kind, the module registry. A package that installs but declares no
entry point is not an extension:

- on a **first** install it is uninstalled again (`rolled_back: true`), because
  the only thing on disk is a package Core cannot use and did not have before;
- on an **upgrade** it is left in place, because uninstalling would remove the
  working version the operator already had.

Successful responses report `restart_required`. An upgrade sets it: the
extension's code is already imported into the running interpreter and Python
does not un-import, so a refresh updates what Core *reports* while only a
restart changes what it *runs*. A first install does not set it. Uninstall
always sets it.

Both mutating routes require the bearer token **and** an explicit operator
opt-in, `FLYTO_EXTENSIONS_INSTALL_ENABLED=1`. Installing a package runs its
build hooks as host code, and the auto-minted local token authorises module
execution, not arbitrary code installation. Read routes need only the token;
`GET /v1/extensions` reports whether the opt-in is active.

Failures return a fixed envelope with a stable code:

```json
{"ok": false, "error": {"code": "entrypoint_missing", "message": "...", "name": "flyto-modules-x", "rolled_back": true}}
```

| Code | Status | Meaning |
|---|---|---|
| `unsupported_extension` | 400 | Name matches no supported prefix |
| `invalid_name` | 400 | Not a valid package name |
| `invalid_version` | 400 | Not a valid version string |
| `not_installed` | 404 | Nothing to uninstall |
| `entrypoint_missing` | 409 | Installed, but declares no Flyto2 entry point |
| `rollback_failed` | 409 | Not an extension, and the undo also failed |
| `install_failed` | 502 | Package manager reported failure |
| `uninstall_failed` | 502 | Package manager reported failure |
| `timeout` | 504 | Package manager exceeded its bound |
| `extension_management_disabled` | 403 | Operator opt-in not set |

Package-manager stdout and stderr are logged locally and never returned: they
carry interpreter paths, index URLs, and sometimes credentials embedded in an
index URL. `see server logs` in a message is literal, not a hedge.

## Verification Service

| Method and path | Auth | Behavior |
|---|---|---|
| `GET /health` | Public | Liveness and graph contract |
| `POST /run` | `X-Internal-Key` | Queue deterministic verification and callback |

`/run` reads its expected key from `FLYTO_VERIFICATION_API_KEY`,
`FLYTO_RUNNER_SECRET`, or `FLYTO_VERIFICATION_SECRET` and returns 503 when no
key is configured. Callback targets are independently restricted by trusted
host policy.

## Defined But Not Mounted

`src/core/api/plugins/routes.py` defines eight plugin-management routes under
`/api/v1/plugins`. The current Execution API `create_app` does not include that
router. Consumers must use the CLI/plugin runtime or explicitly mount and secure
the factory; these paths must not be advertised as active server endpoints.

## Errors

- 401/403: missing or invalid caller credentials.
- 404: unknown module, execution, evidence set, or session.
- 405: unsupported MCP GET/SSE behavior.
- 422: request-model validation failure.
- 503: protected service started without required authentication state.
- Structured module/workflow responses may also report policy or execution
  errors with HTTP 200 when the response model represents operation outcome.
