# Module Phase 2 Features

Enhanced execution control and security features for Flyto Core modules.

---

## Overview

Phase 2 introduces production-ready features for robust workflow execution:

### Execution Control
- ⏱️ **Timeout** - Prevent modules from running too long
- 🔄 **Retry Logic** - Automatically retry failed operations
- 🔒 **Concurrent Safety** - Control parallel execution

### Security
- 🔑 **Credential Requirements** - Mark modules that need API keys
- 🛡️ **Sensitive Data Handling** - Flag modules processing sensitive info
- 🚫 **Permission System** - Declare required permissions

---

## Execution Settings

### Timeout

Prevent modules from hanging indefinitely.

```python
@register_module(
    module_id='api.external_service',

    # Timeout after 30 seconds
    timeout=30,

    # ... other fields
)
```

**Use cases:**
- API calls to external services
- Browser operations that might hang
- Network-dependent operations

**Behavior:**
- Raises `TimeoutError` if execution exceeds timeout
- Works with retry logic (each retry gets full timeout)
- `None` = no timeout (default)

**Example:**
```python
# API call with 30s timeout
@register_module(
    module_id='api.weather.fetch',
    timeout=30,  # Fail if API takes >30s
)

# Browser screenshot with 10s timeout
@register_module(
    module_id='browser.screenshot',
    timeout=10,  # Browser should respond quickly
)
```

---

### Retryable

Automatically retry failed operations.

```python
@register_module(
    module_id='api.http_get',

    # Enable retries
    retryable=True,
    max_retries=3,

    # ... other fields
)
```

**Use cases:**
- Network requests (temporary failures)
- External API calls (rate limits, timeouts)
- Browser automation (element not ready)

**Behavior:**
- Retries on **any exception** (except `KeyboardInterrupt`)
- Exponential backoff: 1s, 2s, 4s, 8s...
- Fails after `max_retries` attempts

**Example:**
```python
# HTTP request with retries
@register_module(
    module_id='api.http_get',
    retryable=True,
    max_retries=3,  # Try up to 3 times
    timeout=30,     # Each attempt gets 30s
)
# Total max time: 30s * 3 = 90s + backoff time
```

**Retry Timeline:**
```
Attempt 1: Execute → Fail
           ↓ Wait 1s
Attempt 2: Execute → Fail
           ↓ Wait 2s
Attempt 3: Execute → Success ✓
```

---

### Concurrent Safety

Control whether module can run in parallel.

```python
@register_module(
    module_id='browser.launch',

    # Only one instance at a time
    concurrent_safe=False,

    # ... other fields
)
```

**Use cases:**
- `concurrent_safe=False`:
  - Browser operations (resource conflicts)
  - File writes to same file
  - Database migrations

- `concurrent_safe=True` (default):
  - API calls (independent requests)
  - Data transformations (stateless)
  - Read-only operations

**Example:**
```python
# Browser - NOT safe for concurrent execution
@register_module(
    module_id='browser.launch',
    concurrent_safe=False,  # Don't launch multiple browsers
)

# API call - safe for concurrent execution
@register_module(
    module_id='api.search',
    concurrent_safe=True,  # Can make multiple searches in parallel
)
```

---

## Security Settings

### Requires Credentials

Mark modules that need API keys or authentication.

```python
@register_module(
    module_id='api.openai.chat',

    # This module needs API key
    requires_credentials=True,

    # ... other fields
)
```

**UI Behavior:**
- Shows 🔑 icon in module palette
- Warns user if credentials not configured
- Can prompt for API key before execution

**Example:**
```python
# OpenAI module
@register_module(
    module_id='api.openai.chat',
    requires_credentials=True,  # Needs OPENAI_API_KEY
)

# Local file read
@register_module(
    module_id='file.read',
    requires_credentials=False,  # No API key needed
)
```

---

### Handles Sensitive Data

Flag modules that process sensitive information.

```python
@register_module(
    module_id='database.query',

    # This module accesses sensitive data
    handles_sensitive_data=True,

    # ... other fields
)
```

**Use cases:**
- Database queries (user data, passwords)
- AI chat (user messages, PII)
- Payment processing
- Authentication systems

**UI Behavior:**
- Shows 🛡️ icon in module palette
- Warning when logging workflow output
- Compliance mode: mask sensitive data in logs

**Example:**
```python
# AI chat - handles user messages
@register_module(
    module_id='ai.claude.chat',
    handles_sensitive_data=True,  # User messages may contain PII
    requires_credentials=True,     # Also needs API key
)

# Public data search
@register_module(
    module_id='api.google_search',
    handles_sensitive_data=False,  # Search results are public
    requires_credentials=True,      # But still needs API key
)
```

---

### Required Permissions

Declare what permissions the module needs.

```python
@register_module(
    module_id='file.write',

    # Needs file system write permission
    required_permissions=['file.write'],

    # ... other fields
)
```

**Permission Format:**
```
resource.action

Examples:
- file.read
- file.write
- network.access
- browser.launch
- database.read
- database.write
- system.process
- ai.api
```

**Use cases:**
- Enterprise deployments (permission control)
- Sandboxed environments (security restrictions)
- Audit logging (track what modules do)

**Example:**
```python
# Browser module
@register_module(
    module_id='browser.launch',
    required_permissions=[
        'browser.launch',   # Permission to launch browser
        'system.process',   # Permission to create process
    ],
)

# API module
@register_module(
    module_id='api.http_get',
    required_permissions=['network.access'],  # Internet access
)

# File + Network module
@register_module(
    module_id='file.upload_s3',
    required_permissions=[
        'file.read',       # Read local file
        'network.access',  # Upload to internet
    ],
)
```

---

## Complete Examples

### API Module with Full Phase 2

```python
@register_module(
    module_id='api.openai.chat',
    version='1.0.0',
    category='ai',
    subcategory='ai',
    label='OpenAI Chat',
    icon='Brain',
    color='#10A37F',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    can_connect_to=['data.*', 'notification.*'],

    # Phase 2: Execution settings
    timeout=60,              # AI can take up to 60s
    retryable=True,          # Retry on network errors
    max_retries=3,           # Up to 3 attempts
    concurrent_safe=True,    # Can make multiple AI calls in parallel

    # Phase 2: Security settings
    requires_credentials=True,        # Needs OPENAI_API_KEY
    handles_sensitive_data=True,      # User prompts may contain PII
    required_permissions=[
        'network.access',
        'ai.api',
    ],

    params_schema={...},
    output_schema={...},
    examples=[...],
)
```

### Browser Module with Full Phase 2

```python
@register_module(
    module_id='browser.screenshot',
    version='1.0.0',
    category='browser',
    subcategory='browser',
    label='Take Screenshot',
    icon='Camera',
    color='#8B5CF6',

    # Connection types
    input_types=['browser_instance'],
    output_types=['image', 'screenshot'],
    can_receive_from=['browser.launch', 'browser.goto'],
    can_connect_to=['file.write', 'cloud.s3.*'],

    # Phase 2: Execution settings
    timeout=10,              # Screenshot should be quick
    retryable=True,          # Retry if element not ready
    max_retries=2,           # Don't retry too many times
    concurrent_safe=False,   # Browser operations are not thread-safe

    # Phase 2: Security settings
    requires_credentials=False,       # No API key needed
    handles_sensitive_data=False,     # Screenshots are user-initiated
    required_permissions=[
        'browser.launch',
        'file.write',
    ],

    params_schema={...},
    output_schema={...},
    examples=[...],
)
```

### Simple Data Module

```python
@register_module(
    module_id='data.json.parse',
    version='1.0.0',
    category='data',
    subcategory='json',
    label='Parse JSON',
    icon='Braces',
    color='#F59E0B',

    # Connection types
    input_types=['text', 'string'],
    output_types=['json', 'object'],

    # Phase 2: Execution settings
    # No timeout - should complete instantly
    # No retry - parsing either works or doesn't
    concurrent_safe=True,    # JSON parsing is stateless

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,  # Unless JSON contains sensitive data
    required_permissions=[],       # No special permissions needed

    params_schema={...},
    output_schema={...},
    examples=[...],
)
```

---

## Best Practices

### When to Use Timeout

✅ **Use timeout for:**
- External API calls
- Network requests
- Browser operations
- Long-running computations

❌ **Don't use timeout for:**
- Instant operations (JSON parse, string manipulation)
- Internal calculations
- Data transformations

**Example:**
```python
# ✅ Good - API calls need timeout
@register_module(
    module_id='api.weather',
    timeout=30,
)

# ❌ Bad - JSON parsing is instant
@register_module(
    module_id='data.json.parse',
    timeout=1,  # Unnecessary!
)
```

---

### When to Use Retryable

✅ **Use retryable for:**
- Network requests (temporary failures)
- External services (rate limits)
- Browser automation (element loading)

❌ **Don't use retryable for:**
- Validation errors (won't fix on retry)
- Permission errors (won't fix on retry)
- Logic errors (won't fix on retry)

**Example:**
```python
# ✅ Good - Network can have temporary issues
@register_module(
    module_id='api.http_get',
    retryable=True,
)

# ❌ Bad - Parameter validation won't fix itself
@register_module(
    module_id='string.split',
    retryable=True,  # Unnecessary!
)
```

---

### Concurrent Safety Guidelines

**Set `concurrent_safe=False` if:**
- Module uses shared resources (files, browser)
- Module modifies global state
- Module has race conditions

**Keep `concurrent_safe=True` if:**
- Module is stateless
- Module only reads data
- Module uses independent resources

**Example:**
```python
# ❌ NOT concurrent safe
@register_module(
    module_id='browser.launch',
    concurrent_safe=False,  # Browser instances conflict
)

# ✅ Concurrent safe
@register_module(
    module_id='math.calculate',
    concurrent_safe=True,  # Pure calculation, no side effects
)
```

---

### Security Settings Matrix

| Module Type | requires_credentials | handles_sensitive_data | required_permissions |
|-------------|---------------------|------------------------|---------------------|
| API (public data) | ✅ Yes | ❌ No | `network.access` |
| API (user data) | ✅ Yes | ✅ Yes | `network.access` |
| File read | ❌ No | ⚠️ Maybe | `file.read` |
| File write | ❌ No | ⚠️ Maybe | `file.write` |
| Browser | ❌ No | ❌ No | `browser.launch` |
| Database | ✅ Yes | ✅ Yes | `database.read/write` |
| Math/String | ❌ No | ❌ No | None |

---

## Migration Guide

### Updating Existing Modules

1. **Identify module characteristics:**
   ```python
   # Questions to ask:
   # - Can it timeout? → Add timeout
   # - Can it fail temporarily? → Add retryable
   # - Does it use shared resources? → Set concurrent_safe=False
   # - Does it need API keys? → Set requires_credentials=True
   # - Does it handle user data? → Set handles_sensitive_data=True
   ```

2. **Add Phase 2 fields:**
   ```python
   @register_module(
       # ... existing fields ...

       # Add these
       timeout=30,
       retryable=True,
       max_retries=3,
       concurrent_safe=True,
       requires_credentials=True,
       handles_sensitive_data=False,
       required_permissions=['network.access'],
   )
   ```

3. **Test with validator:**
   ```bash
   python scripts/validate_all_modules.py
   ```

---

## Validation

The validator automatically checks Phase 2 fields:

```bash
$ python scripts/validate_all_modules.py

✓ api.openai.chat
  ✓ timeout: 60s
  ✓ retryable: True (max 3 retries)
  ✓ concurrent_safe: True
  ✓ requires_credentials: True
  ✓ handles_sensitive_data: True

⚠ browser.launch
  WARNING: Module is not concurrent_safe but is retryable.
           Consider if retries might cause resource conflicts.
```

---

## Summary

Phase 2 adds production-ready features:

✅ **Execution Control:**
- Timeout prevents hanging
- Retry handles temporary failures
- Concurrent safety prevents conflicts

✅ **Security:**
- Credential requirements prevent misconfiguration
- Sensitive data flags enable compliance
- Permission system enables enterprise control

✅ **Developer Experience:**
- Clear error messages
- Automatic validation
- Best practices enforcement

**Next Steps:**
1. Update your modules with Phase 2 fields
2. Run validation: `python scripts/validate_all_modules.py`
3. Test timeout/retry behavior
4. Deploy with confidence! 🚀
