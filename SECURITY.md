# Security Policy

## Supported Versions

Security fixes land on the latest 2.28.x release. Older lines do not receive
backports — upgrading is the supported path.

| Version  | Supported          |
| -------- | ------------------ |
| 2.28.x   | :white_check_mark: |
| < 2.28   | :x:                |

The current secure release is **2.28.0**. Every advisory published against
this project is patched at or below that version, and every one has a named
regression test that runs in CI.

[**SECURITY_STATUS.md**](SECURITY_STATUS.md) lists all of them —
advisory, severity, affected range, fixed-in version, and the regression test
that covers it. That page is generated from `security/advisories.json` and
verified in CI: every test it names must resolve to a collectable test node, so
the coverage column cannot drift into fiction.

### Filesystem and network boundaries

Every advisory published against this project concerns one of two boundaries:
which files a caller-supplied path may reach, and which hosts a caller-supplied
target may reach. Both are configured by environment, and both should be set
explicitly in production.

**Filesystem**

| Variable | Effect |
| -------- | ------ |
| `FLYTO_SANDBOX_DIR` | Confines every caller-supplied path to this directory. **Defaults to the process working directory**, which is rarely what you want for a server. |
| `FLYTO_ALLOW_ABSOLUTE_PATHS` | Whether absolute paths may be supplied at all (they are still confined by `FLYTO_SANDBOX_DIR`). |

**Outbound network**

| Variable | Effect |
| -------- | ------ |
| `FLYTO_ALLOW_PRIVATE_NETWORK` | Allow targets that resolve into private/link-local ranges. Default `false`. |
| `FLYTO_ALLOWED_HOSTS` | Comma-separated hosts (wildcards allowed) permitted regardless of the range check. |
| `FLYTO_HTTP_ALLOWED_PORTS` | Extra ports the HTTP guard accepts. |
| `FLYTO_ALLOW_PORT_SCAN` | Allow `port.check` to probe non-loopback hosts. |

Loopback is always permitted for infrastructure connections (Redis, MySQL,
SMTP, SSH), because self-hosted deployments legitimately connect there and
blocking it closes no path a workflow does not already have.

### Coverage is enforced, not assumed

Centralizing a guard only moves the failure mode from "the guard is wrong" to
"the guard was not called" — which is harder to see and just as exploitable.
Both boundaries therefore have a registry-wide coverage test that fails the
build rather than a convention that relies on reviewers:

| Test | Enforces |
| ---- | -------- |
| `tests/core/test_write_sink_coverage.py` | Every module declaring a path-shaped parameter reaches `validate_path_with_env_config`. |
| `tests/core/test_outbound_guard_coverage.py` | Every module declaring a URL/host-shaped parameter reaches an SSRF guard (`enforce_outbound_url`, `enforce_outbound_service_url`, `enforce_outbound_host`, or a guarded session). |

Exemptions must state what the parameter really addresses, and they are
re-verified on every run: a module excused as "makes no request" fails the
moment it opens a connection, and a module excused for validating locally fails
the moment that validation is removed.

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability within Flyto2 Core, please report it responsibly.

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:

**security@flyto2.com**

Or, if you prefer, you can use GitHub's private vulnerability reporting feature:

1. Go to the [Security tab](https://github.com/flytohub/flyto-core/security) of this repository
2. Click "Report a vulnerability"
3. Fill out the form with details about the vulnerability

### What to Include

Please include the following information in your report:

- **Type of vulnerability** (e.g., SQL injection, XSS, authentication bypass)
- **Location** of the affected source code (file path and line numbers if possible)
- **Step-by-step instructions** to reproduce the issue
- **Proof-of-concept** or exploit code (if possible)
- **Impact assessment** - what an attacker could achieve
- **Suggested fix** (if you have one)

### Response Timeline

- **Initial Response**: Within 48 hours of your report
- **Status Update**: Within 7 days with an assessment
- **Resolution Target**: Within 90 days for most issues

### What to Expect

1. **Acknowledgment**: We will acknowledge receipt of your report within 48 hours
2. **Assessment**: We will assess the vulnerability and determine its severity
3. **Updates**: We will keep you informed of our progress
4. **Fix**: We will develop and test a fix
5. **Disclosure**: We will coordinate public disclosure with you
6. **Credit**: We will credit you in our security advisories (unless you prefer anonymity)

## Security Best Practices

When using Flyto2 Core, please follow these security best practices:

### Environment Variables

**Never hardcode sensitive credentials in workflow files.**

```yaml
# BAD - Don't do this
steps:
  - id: api_call
    module: api.http_post
    params:
      headers:
        Authorization: "Bearer sk-1234567890abcdef"  # Never hardcode!

# GOOD - Use environment variables
steps:
  - id: api_call
    module: api.http_post
    params:
      headers:
        Authorization: "Bearer ${env.API_KEY}"
```

### Recommended Environment Variables

Store sensitive values in environment variables:

```bash
# API Keys
export OPENAI_API_KEY="your-key-here"
export ANTHROPIC_API_KEY="your-key-here"
export GITHUB_TOKEN="your-token-here"

# Database Credentials
export DATABASE_URL="postgresql://user:pass@host:5432/db"

# Third-party Services
export SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
export STRIPE_API_KEY="sk_live_..."
```

### File Permissions

Workflow files may contain sensitive logic. Protect them appropriately:

```bash
# Restrict workflow file permissions
chmod 600 sensitive-workflow.yaml

# Restrict .env files
chmod 600 .env
```

### Input Validation

When creating custom modules, always validate and sanitize inputs:

Network modules validate the initial destination and use the shared guarded
session/request helpers from `src/core/utils.py`. The guarded connector checks
the address used for the actual connection, and the request helper revalidates
every redirect target before following it.

```python
from core.utils import (
    guarded_aiohttp_request,
    guarded_client_session,
    validate_url_with_env_config,
    SSRFError,
)

try:
    validate_url_with_env_config(url)
    async with guarded_client_session() as session:
        response = await guarded_aiohttp_request(session, "GET", url)
except SSRFError as e:
    return {'ok': False, 'error': str(e), 'error_code': 'SSRF_BLOCKED'}
```

#### Blocked IP Ranges (Default)

| Range | Reason |
|-------|--------|
| `10.0.0.0/8` | RFC 1918 private |
| `172.16.0.0/12` | RFC 1918 private |
| `192.168.0.0/16` | RFC 1918 private |
| `127.0.0.0/8`, `::1/128` | Loopback |
| `169.254.0.0/16`, `fe80::/10` | Link-local |
| `0.0.0.0/8` | Reserved |
| `100.64.0.0/10` | Shared address (CGN) |
| `192.0.0.0/24`, `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` | Documentation/test |
| `224.0.0.0/4`, `240.0.0.0/4` | Multicast/reserved |

#### Blocked Hostnames

`localhost`, `localhost.localdomain`, `127.0.0.1`, `::1`, `0.0.0.0`, `metadata.google.internal`, `169.254.169.254` (cloud metadata), `metadata.internal`

#### DNS Resolution Check

The guarded connector checks the resolved IP at connection time and connects
through that validated resolver. Redirects are followed only after each new
target passes the same policy. This closes resolve-then-connect DNS rebinding
and public-to-private redirect gaps.

#### Representative Protected Modules

| Module | Protection |
|--------|-----------|
| `http.request` | `validate_url_with_env_config()` |
| `api.http_get` | `validate_url_with_env_config()` |
| `browser.goto` | `validate_url_with_env_config()` |
| `browser.tab` | `validate_url_with_env_config()` |
| `image.download` | `validate_url_with_env_config()` |
| `notification.send` | `validate_url_with_env_config()` |
| `communication.webhook_trigger` | `validate_url_with_env_config()` |
| `llm.chat` | `validate_url_with_env_config()` (custom base URL) |
| `vector.connector` | `validate_url_with_env_config()` |
| `port.check` | `is_private_ip()` direct check |
| `ai.local_ollama` | localhost-only enforcement |
| `agent.chain`, `agent.autonomous` | localhost-only by default; exact host/port scope for loopback and full guarded requests for operator-enabled remote Ollama |

#### Validator Enforcement

The module validator (`validator.py`) requires all network modules to declare SSRF protection via the `ssrf_protected` tag (rule `SEC001` / `CORE-SEC-003`).

#### Configuration

```bash
# Allow private networks (development only)
FLYTO_ALLOW_PRIVATE_NETWORK=true

# Allowlist specific hosts (comma-separated, supports wildcards)
FLYTO_ALLOWED_HOSTS=localhost,127.0.0.1,*.internal.corp.com

# VS Code local mode (allow localhost only)
FLYTO_VSCODE_LOCAL_MODE=true

# Allow remote Ollama server (default: localhost only)
FLYTO_ALLOW_REMOTE_OLLAMA=true
```

### Filesystem Sandbox Protection

Modules that accept file paths canonicalize them with
`validate_path_with_env_config()` before reading, creating directories, or
writing. The canonical path must remain within `FLYTO_SANDBOX_DIR`; symlink and
`..` escapes are rejected. This applies to general file modules as well as
document/image readers, browser snapshots/traces/cookie persistence, generated
PDFs, extracted Word images, and cloud-download destinations.

```bash
# Set an explicit production sandbox root.
FLYTO_SANDBOX_DIR=/srv/flyto/workspace

# Absolute paths are accepted only when they still resolve inside the sandbox.
FLYTO_ALLOW_ABSOLUTE_PATHS=true
```

### Browser Automation Security

When using browser modules:

```yaml
# Run in headless mode for server environments
- id: browser
  module: browser.launch
  params:
    headless: true

# Be cautious with file downloads
- id: download
  module: browser.download
  params:
    path: "/safe/download/directory/"  # Use restricted directory
```

### Logging and Secrets

Flyto2 Core automatically redacts sensitive values in logs. However, be careful when:

- Writing custom modules that log parameter values
- Using the `utility.log` module with sensitive data
- Enabling debug mode in production

## Known Security Considerations

### Code Execution

Flyto2 Core executes workflow definitions. Be aware that:

- Workflow files should be treated as code
- Only run workflows from trusted sources
- Review third-party modules before using them

### Network Access

Some modules make network requests. Consider:

- Using firewall rules to restrict outbound connections
- Monitoring network traffic from workflow executions
- Using allowlists for permitted domains (see SSRF configuration above)

### Browser Automation

The browser modules can:

- Execute JavaScript on web pages
- Access cookies and local storage
- Download files

Always run browser automation in isolated environments when processing untrusted content.

## Security Updates

Security updates are released as patch versions (e.g., 1.0.1, 1.0.2). We recommend:

1. **Subscribe** to this repository's releases
2. **Update** promptly when security patches are released
3. **Monitor** the [security advisories](https://github.com/flytohub/flyto-core/security/advisories)

## Responsible Disclosure

We follow responsible disclosure practices:

- We will not take legal action against security researchers acting in good faith
- We will work with you to understand and resolve the issue
- We will publicly acknowledge your contribution (with your permission)

## Contact

For security concerns:
- Email: security@flyto2.com
- GitHub Security Advisories: [Report a vulnerability](https://github.com/flytohub/flyto-core/security/advisories/new)

For general questions:
- GitHub Issues: For non-security bugs and feature requests
- GitHub Discussions: For questions and community support

---

Thank you for helping keep Flyto2 Core and its users safe.
