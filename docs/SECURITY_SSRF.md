# SSRF Protection

flyto-core includes built-in Server-Side Request Forgery (SSRF) protection for all modules that make outbound HTTP requests or navigate browsers to URLs.

## Protected Modules

| Module | Tag | Entry Point |
|--------|-----|-------------|
| `http.request` | `ssrf_protected` | `validate_url_with_env_config()` before request |
| `http.get` | `ssrf_protected` | `validate_url_with_env_config()` before GET |
| `browser.goto` | `ssrf_protected` | `validate_url_ssrf()` in `validate_params()` |
| `image.download` | `ssrf_protected`, `path_restricted` | `validate_url_with_env_config()` before download |

## What Gets Blocked

### Private IP Ranges

| Range | Description |
|-------|-------------|
| `10.0.0.0/8` | RFC 1918 Class A |
| `172.16.0.0/12` | RFC 1918 Class B |
| `192.168.0.0/16` | RFC 1918 Class C |
| `127.0.0.0/8` | Loopback |
| `169.254.0.0/16` | Link-local |
| `0.0.0.0/8` | Current network |
| `100.64.0.0/10` | Shared address space (CGN) |
| `224.0.0.0/4` | Multicast |
| `240.0.0.0/4` | Reserved |
| `::1/128` | IPv6 loopback |
| `fc00::/7` | IPv6 unique local |
| `fe80::/10` | IPv6 link-local |
| `ff00::/8` | IPv6 multicast |

### Blocked Hostnames

- `localhost`, `localhost.localdomain`
- `127.0.0.1`, `::1`, `0.0.0.0`
- `metadata.google.internal` (GCP metadata)
- `169.254.169.254` (AWS/Azure/GCP metadata)
- `metadata.internal`

### Scheme Restrictions

Only `http` and `https` are allowed. `file://`, `ftp://`, `gopher://`, etc. are rejected.

## How It Works

```
URL input
  |
  v
1. Strip whitespace
2. Check scheme (http/https only)
3. Check hostname against BLOCKED_HOSTNAMES
4. If allowed_hosts is set, check allowlist
5. DNS resolve hostname
6. Check resolved IP against PRIVATE_IP_RANGES
  |
  v
Allow or raise SSRFError
```

DNS resolution (step 5-6) prevents DNS rebinding attacks where a hostname initially resolves to a public IP but later resolves to a private IP.

## Configuration

Three environment variables control SSRF behavior:

### `FLYTO_ALLOW_PRIVATE_NETWORK`

Set to `true` to disable all SSRF checks. Use only in development or fully trusted environments.

```bash
FLYTO_ALLOW_PRIVATE_NETWORK=true
```

### `FLYTO_ALLOWED_HOSTS`

Comma-separated list of specific hosts to allow through SSRF protection. Supports wildcards.

```bash
# Allow specific internal hosts
FLYTO_ALLOWED_HOSTS=internal.corp.com,api.staging.local

# Wildcard support
FLYTO_ALLOWED_HOSTS=*.dev.local,monitoring.internal
```

### `FLYTO_VSCODE_LOCAL_MODE`

Designed for VS Code extension local development. Allows `localhost`, `127.0.0.1`, and `::1` while keeping all other private IPs blocked.

```bash
FLYTO_VSCODE_LOCAL_MODE=true
```

## Usage in Custom Modules

```python
from core.utils import validate_url_with_env_config, SSRFError

class MyHttpModule(BaseModule):
    async def execute(self):
        url = self.params["url"]
        try:
            validated_url = validate_url_with_env_config(url)
        except SSRFError as e:
            return {"ok": False, "error": str(e), "error_code": "SSRF_BLOCKED"}

        # Safe to make request
        ...
```

For controlled private access (e.g., a module that must reach an internal API):

```python
from core.utils import validate_url_ssrf

validate_url_ssrf(url, allowed_hosts=["api.internal.corp.com", "*.staging.local"])
```

## Implementation

Core functions in `src/core/utils.py`:

| Function | Purpose |
|----------|---------|
| `is_private_ip(ip_str)` | Check if IP is in any private range |
| `validate_url_ssrf(url, allow_private, allowed_hosts)` | Full SSRF validation with options |
| `get_ssrf_config()` | Read config from environment variables |
| `validate_url_with_env_config(url)` | Convenience wrapper using env config |
