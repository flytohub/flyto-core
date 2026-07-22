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
