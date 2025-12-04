# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability within Flyto Core, please report it responsibly.

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:

**security@flyto.dev**

Or, if you prefer, you can use GitHub's private vulnerability reporting feature:

1. Go to the [Security tab](../../security) of this repository
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

When using Flyto Core, please follow these security best practices:

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

```python
def validate_params(self):
    url = self.params.get('url', '')

    # Validate URL format
    if not url.startswith(('http://', 'https://')):
        raise ValueError("URL must start with http:// or https://")

    # Prevent SSRF attacks
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname in ['localhost', '127.0.0.1', '0.0.0.0']:
        raise ValueError("Local URLs are not allowed")
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

Flyto Core automatically redacts sensitive values in logs. However, be careful when:

- Writing custom modules that log parameter values
- Using the `utility.log` module with sensitive data
- Enabling debug mode in production

## Known Security Considerations

### Code Execution

Flyto Core executes workflow definitions. Be aware that:

- Workflow files should be treated as code
- Only run workflows from trusted sources
- Review third-party modules before using them

### Network Access

Some modules make network requests. Consider:

- Using firewall rules to restrict outbound connections
- Monitoring network traffic from workflow executions
- Using allowlists for permitted domains

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
3. **Monitor** the [security advisories](../../security/advisories)

## Responsible Disclosure

We follow responsible disclosure practices:

- We will not take legal action against security researchers acting in good faith
- We will work with you to understand and resolve the issue
- We will publicly acknowledge your contribution (with your permission)

## Contact

For security concerns:
- Email: security@flyto.dev
- GitHub Security Advisories: [Report a vulnerability](../../security/advisories/new)

For general questions:
- GitHub Issues: For non-security bugs and feature requests
- GitHub Discussions: For questions and community support

---

Thank you for helping keep Flyto Core and its users safe.
