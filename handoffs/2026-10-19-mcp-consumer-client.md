# MCP consumer: the client and OAuth runtime

Owner: claude
Branch: lane/mcp-consumer (local, from origin/feat/unified-platform-integration-20261018 c7c60b6)
Date: 2026-10-19

## What changed

- `src/core/pack/mcp_client.py` (new): `McpClient(url, *, credential, credential_required, timeout_ms, send)`
  with `list_tools()` and `call_tool(name, arguments)`. Streamable HTTP: `initialize`, then
  `notifications/initialized`, then the call, carrying `Mcp-Session-Id` and the negotiated
  `MCP-Protocol-Version`. Answers in JSON or as an event stream (the response is picked by id).
  `normalize_tools` keeps name, title, description, input schema and the four behaviour hints
  (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) plus a digest. A
  malformed tool is named (`refused: MCP_TOOL_MALFORMED`), never dropped.
- Typed failures reuse `connector_runtime` (`ConnectorCallError`, `STATUS_FAILURES` via the
  now-public `status_failure`, `PROVIDER_TIMEOUT`, `PROVIDER_UNREACHABLE`, `SSRF_BLOCKED`,
  `PROVIDER_INVALID_RESPONSE`, `PROVIDER_REDIRECT_REFUSED`...) and add `MCP_FAILURES`.
  `FINAL_FAILURES` (401/403/4xx, `isError`, invalid params) are returned with `final: true`
  and never retried. A credential echoed back by a server is scrubbed from the error text.
- `src/core/pack/mcp_oauth.py` (new): `discover`, `pkce_pair`, `authorization_request`,
  `exchange_code`, `refresh`, `OAuthError` with `OAUTH_FAILURES`. Every request names the MCP
  server as `resource`; the token exchange carries no bearer.
- No `mcp` SDK dependency: three exchanges do not justify a second HTTP stack outside the SSRF
  guard.

## Why

Flyto2 Spaces consume external MCP servers (provider packs §0, DECISIONS 2026-10-19). The
runtime belongs with the connector runtime it reuses; Cloud's Space computer drives it
(`flyto-cloud` `local/mcp_consumer`).

## Verified

- Failing first: `tests/core/pack/test_mcp_client.py` and `test_mcp_oauth.py` failed at
  collection (`ModuleNotFoundError: No module named 'core.pack.mcp_client'` / `mcp_oauth`).
- After: `tests/core/pack` + outbound guard + import boundary + documentation generator tests:
  260 passed. The client suite runs against an in-process `ThreadingHTTPServer` fake MCP server
  (JSON and SSE modes, pagination, 401/503/307/rpc error/not JSON/slow/unreachable/SSRF).
- Ruff on `src/core/pack/` and `tests/core/pack/`: all checks passed.
- Docs regenerated (`scripts/generate_reference.py`), inventory tokens updated;
  `check_documentation.py` passed; `check_brand_identity.py` passed; `lint-project-memory.sh` PASS.
- `flyto-index verify --strict`: 21 pass, 0 warn, 0 fail.
- Cross-repo: flyto-cloud's `tests/unit/local/test_mcp_consumer_real_client.py` passed with this
  worktree's `src` on `PYTHONPATH` (host dispatcher -> adapter -> this client -> loopback fake).

## Not verified

- Any real MCP server or authorization server; no release or Cloud pin bump. Cloud's pinned
  flyto-core has no `core.pack.mcp_client`, so a host refuses MCP calls typed
  (`mcp_client_unavailable`) until it is released and pinned.
- Full core suite, CI.

## Follow-ups

- Release with the next core version and bump flyto-cloud's pin.
- Sensitive-result redaction: MCP tools declare no sensitive paths, so results are kept whole;
  a declared-paths mechanism would mirror `connector_runtime.sensitive_result_paths`.
