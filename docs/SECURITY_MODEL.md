# Security Model

## Assets

Core may handle API keys, browser sessions, cookies, workflow parameters,
database credentials, filesystem data, screenshots, execution evidence,
callbacks, and plugin packages. These assets cross different trust boundaries
and must not share one implicit trust decision.

## Threat Boundaries

| Input | Primary controls |
|---|---|
| HTTP/MCP caller | Bearer or internal-key authentication before dispatch |
| Module ID | Shared allowlist/denylist and permission checks |
| URL/callback | SSRF guard, scheme/host/port validation, trusted-host policy |
| Filesystem path | Sandbox root, traversal checks, explicit absolute-path opt-in |
| Workflow YAML | Parser, schema, module and connection validation |
| Stored evidence | Redaction, owner-only files, authenticated reads |
| Browser content | Treat DOM, downloads, scripts, and redirects as untrusted |
| Plugin package | Operator review, manifest permissions, process isolation |
| Provider response | Validate type, size, status, and expected schema |

## Authentication

Execution API mutating operations and all workflow/evidence reads require the
active bearer token. MCP POST and DELETE are protected before JSON-RPC/session
dispatch. Verification `/run` uses `X-Internal-Key` and fails closed when no key
is configured. Health and module metadata endpoints intentionally remain public
for local discovery.

## Network Policy

Outbound HTTP and browser navigation reject unsafe destinations by default.
Private networks, localhost, trusted LLM hosts, callback hosts, and nonstandard
ports require explicit configuration. DNS and redirect behavior must be checked
at the final request boundary, not only when parsing the initial URL.

See [SSRF Security](SECURITY_SSRF.md) for module-specific rules.

## Filesystem Policy

File modules resolve paths through the sandbox guard. Absolute paths and paths
outside the configured root require explicit policy. Archive extraction must
also validate each member path. Sensitive local state uses owner-only modes
where available.

## Secrets And Persistence

Secrets enter through runtime parameters, environment variables, or external
secret systems. Redaction runs before workflow definitions and evidence are
persisted. Public examples use only registered `@flyto2.com` aliases and fake
values. Secret scanning is necessary but does not replace source review.

## Plugin Trust

Installing a plugin is code installation. The plugin protocol and manifest do
not make an unreviewed package safe. Operators should pin versions, inspect
publisher/repository/signatures, review requested permissions, and run unknown
plugins in an isolated environment with minimal network and filesystem access.

## Security Verification

Regression tests cover fail-closed auth initialization, wildcard bind posture,
MCP complete mediation, module policy, SSRF, callback restrictions, path guards,
redaction, and evidence access. Reports go to
[security@flyto2.com](mailto:security@flyto2.com); see the root
[Security Policy](../SECURITY.md) for disclosure handling.

## Non-Claims

- Public module metadata is not authorization to execute the module.
- A successful schema check does not prove an external provider is trustworthy.
- A local default does not make a non-loopback deployment secure by itself.
- Optional LLM review is not a security control or release authority.
- Defined plugin HTTP handlers are not active unless an application mounts and
  protects their router.
