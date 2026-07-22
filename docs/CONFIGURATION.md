# Configuration

Flyto2 Core reads configuration from CLI arguments, workflow parameters,
environment variables, package extras, module policy, and persisted local
state. The generated [configuration reference](reference/configuration.md)
links all 93 detected environment-variable names to their readers.

## Runtime Installation

| Extra | Adds |
|---|---|
| base | workflow engine, CLI, MCP stdio, schemas, HTTP/data utilities |
| `browser` | Playwright browser automation |
| `api` | FastAPI and Uvicorn Execution API |
| `vector` | Qdrant and sentence-transformer integrations |
| `image` | QR and image processing |
| `crypto` | AES encryption/decryption and JWT signing/verification |
| `dns` | DNS record types beyond the socket-based A/AAAA fallback |
| `ai` | OpenAI-backed agents, chat, embeddings, and provider adapters |
| `telegram` | Telegram bot integration |
| `cloud` | browser and image extras |
| `all` | every supported runtime extra |

Install only the capabilities a deployment uses, for example
`pip install 'flyto-core[api,crypto,dns]'`. Contributors should install
`pip install -e '.[dev]'`; the development extra includes every dependency
required by the non-browser test suite.

`pyproject.toml` is the canonical dependency contract. `requirements.txt` and
`requirements-integrations.txt` are compatibility installers that delegate to
named extras. `requirements.lock` pins only the base runtime and is regenerated
with `scripts/lock-deps.sh`; it does not claim to lock every optional provider.

## Security-Critical Environment

| Variable | Purpose |
|---|---|
| `FLYTO_API_TOKEN` | Fixed Execution API bearer token |
| `FLYTO_CORS_ORIGINS` | Explicit browser origins for the Execution API |
| `FLYTO_MODULE_ALLOWLIST` | Only modules matching these patterns may execute |
| `FLYTO_MODULE_DENYLIST` | Deny matching modules when no allowlist overrides it |
| `FLYTO_GRANTED_PERMISSIONS` | Runtime permission grants |
| `FLYTO_ENV_VAR_ALLOWLIST` | Environment names visible to modules |
| `FLYTO_ALLOWED_HOSTS` | Allowed private/localhost destinations |
| `FLYTO_HTTP_ALLOWED_PORTS` | Allowed destination ports |
| `FLYTO_ALLOW_PRIVATE_NETWORK` | Explicit private-network opt-in |
| `FLYTO_SANDBOX_DIR` | Filesystem sandbox root |
| `FLYTO_ALLOW_ABSOLUTE_PATHS` | Explicit absolute-path opt-in |
| `FLYTO_VERIFICATION_API_KEY` | Preferred verification `/run` key |
| `FLYTO_TRUSTED_CALLBACK_HOSTS` | Verification callback destination allowlist |

Do not disable SSRF or sandbox guards in a shared or production environment.
Test-only overrides belong in scoped fixtures and must not be set during test
collection.

## CLI And Template Environment

- `FLYTO_ENV` selects module filtering context.
- `FLYTO_API_URL` selects the remote template API.
- `FLYTO_TOKEN` authenticates template operations.
- `FLYTO_STORAGE_DIR` changes local key/value storage.
- `HEADLESS` influences browser launch defaults where supported.

## Provider Credentials

AI, cloud, messaging, database, and productivity modules read provider-specific
environment names. Install only the needed extra/integration, grant only the
required permissions, and inject credentials at runtime. Never place real
tokens in workflow YAML, recipe defaults, examples, or checked-in `.env` files.

## Local State

| Path | Purpose |
|---|---|
| `~/.flyto/.api-token-<port>` | Generated Execution API bearer token |
| `~/.flyto/token` | Optional remote template API token |
| `~/.flyto/storage` | Default local key/value storage |
| `.flyto-runs/` | Workflow run state used by replay |

Token and sensitive workflow files are written with owner-only permissions
where the platform supports POSIX modes.

## Module Policy

Policy is applied before module execution and again at execution boundaries.
Allowlist is authoritative when present; otherwise denylist patterns apply.
The default denylist blocks high-risk shell/process surfaces. A transport must
not bypass this shared policy by invoking a module registry directly.

## Recipes And Workflow Assets

The package includes 41 recipe YAML files and one recipe bundle. Repository
workflow fixtures cover security audit, pentest, implementation, and smoke
scenarios. Their exact names and step counts are generated in
[Configuration And Packaged Assets](reference/configuration.md).
