# Flyto2 Workflow DSL Specification

**Version:** 1.0.0-alpha
**Last Updated:** 2025-11-29

This document is the complete specification for Flyto2 workflow YAML files.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Workflow File Structure](#workflow-file-structure)
- [Top-Level Fields](#top-level-fields)
- [Parameters (params)](#parameters-params)
- [Steps](#steps)
- [Variable Syntax](#variable-syntax)
- [Output](#output)
- [Control Flow](#control-flow)
- [Error Handling](#error-handling)
- [Complete Examples](#complete-examples)

---

## Quick Start

**Minimal workflow:**

```yaml
name: "Hello World"
description: "My first workflow"

steps:
  - id: greet
    module: utility.delay
    params:
      duration_seconds: 1

output:
  message: "Workflow completed!"
```

**Run it:**
```bash
python -m cli.main my_workflow.yaml
```

---

## Workflow File Structure

Every workflow is a YAML file with this structure:

```yaml
# === Metadata ===
id: unique-workflow-id               # Optional: Unique identifier
name: "Workflow Name"                # Required: Human-readable name
version: "1.0.0"                     # Optional: Semantic version
description: "What this workflow does"  # Recommended: Description
author: "Your Name"                  # Optional: Author
tags: ["tag1", "tag2"]              # Optional: For categorization

# === Configuration ===
config:                              # Optional: Workflow-level config
  browser:
    headless: true
  timeout_ms: 300000

# === User Inputs ===
params:                              # Optional: User input definitions
  - name: keyword
    type: string
    required: true

# === Workflow Logic ===
steps:                               # Required: Ordered steps
  - id: step1
    module: core.browser.launch
    params:
      headless: true

# === Output ===
output:                              # Optional: Final output structure
  result: "${step1.status}"
```

---

## Top-Level Fields

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `name` | string | Workflow name | `"Google Search Automation"` |
| `steps` | array | Ordered list of steps to execute | See [Steps](#steps) |

### Recommended Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `description` | string | What the workflow does | `"Extract data from websites"` |
| `id` | string | Unique workflow identifier | `"google-search-v1"` |
| `version` | string | Semantic version | `"1.0.0"` |

### Optional Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `author` | string | Workflow author | `"Flyto2 Team"` |
| `tags` | array | Categorization tags | `["scraping", "api"]` |
| `params` | array | User input definitions | See [Parameters](#parameters-params) |
| `config` | object | Workflow-level configuration | See below |
| `output` | object | Output structure | See [Output](#output) |

### config (Workflow Configuration)

Override engine defaults:

```yaml
config:
  browser:
    headless: true              # Run browser without UI
    viewport:
      width: 1920
      height: 1080

  timeout_ms: 300000            # Default timeout (5 minutes)

  retries:
    default_max_attempts: 3
    default_delay_ms: 1000
```

---

## Parameters (params)

Define user inputs that can be provided when running the workflow.

### Basic Structure

```yaml
params:
  - name: keyword              # Required: Parameter name
    type: string               # Required: Data type
    label: "Search Keyword"    # Optional: UI display label
    description: "What to search for"  # Optional: Help text
    required: true             # Optional: Is this required?
    default: "python"          # Optional: Default value
```

### Supported Types

| Type | Description | Example Value |
|------|-------------|---------------|
| `string` | Text value | `"hello world"` |
| `number` | Numeric value | `42` or `3.14` |
| `boolean` | True/false | `true` or `false` |
| `array` | List of values | `["a", "b", "c"]` |
| `object` | Key-value pairs | `{key: "value"}` |
| `select` | Predefined options | See below |

### select Type (Dropdown)

```yaml
params:
  - name: browser_type
    type: select
    label: "Browser"
    options:
      - chromium
      - firefox
      - webkit
    default: chromium
```

### Validation Rules

```yaml
params:
  - name: count
    type: number
    min: 1                     # Minimum value
    max: 100                   # Maximum value
    default: 10

  - name: email
    type: string
    pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"  # Regex validation

  - name: keyword
    type: string
    minLength: 1               # Minimum string length
    maxLength: 100             # Maximum string length
```

### Complete Example

```yaml
params:
  - name: url
    type: string
    label: "Target URL"
    description: "The website to scrape"
    placeholder: "https://example.com"
    required: true

  - name: max_results
    type: number
    label: "Max Results"
    description: "Maximum number of items to extract"
    default: 10
    min: 1
    max: 100

  - name: headless
    type: boolean
    label: "Headless Mode"
    description: "Run browser without UI"
    default: true

  - name: output_format
    type: select
    label: "Output Format"
    options: ["json", "csv", "yaml"]
    default: "json"
```

---

## Steps

Steps are executed **sequentially** from top to bottom.

### Basic Step Structure

```yaml
steps:
  - id: step_name              # Recommended: Unique step identifier
    module: core.browser.launch  # Required: Module to execute
    description: "Launch browser"  # Optional: Human-readable description
    params:                    # Optional: Parameters passed to module
      headless: true
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `module` | string | Module identifier (e.g., `core.browser.goto`) |

### Recommended Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique step identifier (used to reference output) |
| `description` | string | What this step does |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `params` | object | Parameters passed to the module |
| `if` or `when` | string | Conditional execution (expression) |
| `timeout_ms` | number | Step-specific timeout |
| `retry` | object | Retry configuration |
| `on_error` | string | Error handling strategy |
| `on_error_goto` | string | Jump to step on error |

### Step Examples

#### Basic Step

```yaml
steps:
  - id: navigate
    module: core.browser.goto
    params:
      url: "https://example.com"
```

#### Step with Conditional Execution

```yaml
steps:
  - id: send_alert
    module: notification.slack.send_message
    if: "${extract_data.count > 100}"  # Only run if condition is true
    params:
      text: "Warning: Too many results!"
```

#### Step with Retry

```yaml
steps:
  - id: fetch_api
    module: api.http.get
    params:
      url: "https://api.example.com/data"
    timeout_ms: 10000
    retry:
      max_attempts: 3          # Retry up to 3 times
      delay_ms: 1000           # Wait 1 second between retries
      backoff: "exponential"   # Exponential backoff (1s, 2s, 4s...)
      retry_on:                # Only retry on these errors
        - "TimeoutError"
        - "ConnectionError"
```

#### Step with Error Handling

```yaml
steps:
  - id: risky_operation
    module: some.module
    on_error: "continue"       # Options: fail, continue, skip, goto
    on_error_goto: "cleanup"   # When on_error=goto, jump here
```

**Error handling options:**

- `fail` - Stop workflow immediately (default)
- `continue` - Continue to next step, log error
- `skip` - Skip this step silently
- `goto` - Jump to specified step ID

---

## Variable Syntax

Use `${...}` to reference values from parameters, environment, previous steps, and runtime.

### Available Namespaces

| Namespace | Description | Example |
|-----------|-------------|---------|
| `params` | User-provided parameters | `${params.keyword}` |
| `env` | Environment variables | `${env.API_KEY}` |
| `steps` | Output from previous steps | `${steps.fetch.output.data}` |
| `timestamp` | Current ISO timestamp | `${timestamp}` |

### Accessing Parameters

```yaml
params:
  - name: url
    type: string

steps:
  - id: navigate
    module: core.browser.goto
    params:
      url: "${params.url}"     # Access parameter value
```

### Accessing Environment Variables

```yaml
steps:
  - id: api_call
    module: api.http.get
    params:
      url: "https://api.example.com"
      headers:
        Authorization: "Bearer ${env.API_TOKEN}"  # From environment
```

**Set environment variables:**
```bash
export API_TOKEN=your_token_here
python -m cli.main workflow.yaml
```

### Accessing Step Outputs

Each step with an `id` stores its output, accessible as `${stepId.field}`.

**Shorthand syntax:**
```yaml
# These are equivalent:
browser: "${launch.browser}"
browser: "${steps.launch.output.browser}"
```

**Example:**
```yaml
steps:
  - id: fetch_data
    module: api.http.get
    params:
      url: "https://api.example.com"
    # Returns: { status_code: 200, body: "...", json: {...} }

  - id: process
    module: data.json.parse
    params:
      json_string: "${fetch_data.body}"  # Access 'body' from previous step

  - id: send_notification
    module: notification.slack.send_message
    params:
      text: "API returned status ${fetch_data.status_code}"
```

### Nested Access

Access nested object properties:

```yaml
# If step returns: { user: { name: "John", email: "john@example.com" } }
email: "${fetch_user.user.email}"
name: "${fetch_user.user.name}"

# Array access:
# If step returns: { items: ["a", "b", "c"] }
first: "${fetch_items.items[0]}"
```

### System Variables

| Variable | Type | Description |
|----------|------|-------------|
| `${timestamp}` | string | Current ISO 8601 timestamp |

---

## Output

Define the structure of data returned after workflow execution.

### Basic Output

```yaml
output:
  url: "${params.url}"
  results: "${extract_data.data}"
  count: "${extract_data.count}"
```

### Nested Output

```yaml
output:
  metadata:
    workflow: "google-search"
    version: "1.0.0"
    executed_at: "${timestamp}"

  input:
    keyword: "${params.keyword}"
    max_results: "${params.max_results}"

  results:
    count: "${extract_results.count}"
    data: "${extract_results.data}"

  performance:
    duration_ms: 5432
```

### Output Access

When workflow completes:
```bash
# CLI prints JSON output
python -m cli.main workflow.yaml
# Output:
# {
#   "url": "https://example.com",
#   "results": [...],
#   "count": 10
# }
```

---

## Control Flow

### Conditional Execution (if/when)

Execute step only if condition is true:

```yaml
steps:
  - id: check_results
    module: core.browser.extract
    params:
      selector: ".result"

  - id: send_alert
    if: "${check_results.count > 100}"  # Only run if > 100 results
    module: notification.slack.send_message
    params:
      text: "Warning: ${check_results.count} results found!"
```

**Supported operators:**
- Comparison: `>`, `<`, `>=`, `<=`, `==`, `!=`
- Logic: `and`, `or`, `not`
- Contains: `contains`, `startsWith`, `endsWith`

### Loops (Planned)

Process array items:

```yaml
steps:
  - id: fetch_users
    module: api.http.get
    params:
      url: "https://api.example.com/users"

  - id: process_each_user
    module: core.flow.loop
    params:
      items: "${fetch_users.json.users}"
      as: "user"
      steps:
        - id: send_email
          module: notification.email.send
          params:
            to_email: "${user.email}"
            subject: "Hello ${user.name}"
```

### Parallel Execution (Planned)

Run multiple branches concurrently:

```yaml
steps:
  - id: parallel_fetch
    module: core.flow.parallel
    params:
      branches:
        - steps:
            - module: api.http.get
              params:
                url: "https://api1.example.com"

        - steps:
            - module: api.http.get
              params:
                url: "https://api2.example.com"
```

---

## Error Handling

### Retry Configuration

```yaml
steps:
  - id: unreliable_api
    module: api.http.get
    params:
      url: "https://flaky-api.example.com"
    retry:
      max_attempts: 3
      delay_ms: 1000
      backoff: "exponential"  # Options: fixed, exponential, none
      retry_on:
        - "TimeoutError"
        - "ConnectionError"
```

**Backoff strategies:**
- `fixed` - Same delay every time (e.g., 1s, 1s, 1s)
- `exponential` - Doubling delay (e.g., 1s, 2s, 4s)
- `none` - No delay between retries

### Error Actions

```yaml
steps:
  - id: optional_step
    module: some.module
    on_error: "continue"  # Don't stop workflow if this fails

  - id: critical_step
    module: some.module
    on_error: "fail"      # Stop workflow if this fails (default)

  - id: with_cleanup
    module: some.module
    on_error: "goto"      # Jump to cleanup step
    on_error_goto: "cleanup_resources"

  # ... more steps ...

  - id: cleanup_resources
    module: core.browser.close
```

---

## Complete Examples

### Example 1: Web Scraping with Error Handling

```yaml
name: "Product Price Scraper"
description: "Scrape product prices with retry and error handling"
version: "1.0.0"

params:
  - name: product_url
    type: string
    label: "Product URL"
    required: true

config:
  browser:
    headless: true

steps:
  - id: launch_browser
    module: core.browser.launch
    params:
      headless: true

  - id: navigate
    module: core.browser.goto
    params:
      browser: "${launch_browser.browser}"
      url: "${params.product_url}"
    retry:
      max_attempts: 3
      delay_ms: 2000
      backoff: "exponential"
      retry_on: ["TimeoutError"]

  - id: wait_for_price
    module: core.browser.wait
    params:
      browser: "${launch_browser.browser}"
      selector: ".price"
      timeout_ms: 10000

  - id: extract_price
    module: core.browser.extract
    params:
      browser: "${launch_browser.browser}"
      selector: ".price"
      fields:
        amount:
          selector: ".price"
          type: "text"

  - id: close_browser
    module: core.browser.close
    params:
      browser: "${launch_browser.browser}"
    on_error: "continue"  # Always try to close browser

output:
  url: "${params.product_url}"
  price: "${extract_price.data[0].amount}"
  scraped_at: "${timestamp}"
```

### Example 2: API Integration with Notifications

```yaml
name: "GitHub Issues Monitor"
description: "Monitor GitHub issues and send Slack alerts"
version: "1.0.0"

params:
  - name: repo_owner
    type: string
    required: true

  - name: repo_name
    type: string
    required: true

steps:
  - id: fetch_issues
    module: api.github.list_issues
    params:
      owner: "${params.repo_owner}"
      repo: "${params.repo_name}"
      state: "open"
      labels: "bug"
      token: "${env.GITHUB_TOKEN}"

  - id: check_critical
    module: data.json.parse
    if: "${fetch_issues.count > 10}"
    params:
      json_string: "${fetch_issues.issues}"

  - id: send_alert
    module: notification.slack.send_message
    if: "${fetch_issues.count > 10}"
    params:
      webhook_url: "${env.SLACK_WEBHOOK_URL}"
      text: "⚠️ ${fetch_issues.count} open bugs in ${params.repo_owner}/${params.repo_name}"

output:
  repository: "${params.repo_owner}/${params.repo_name}"
  open_bugs: "${fetch_issues.count}"
  alert_sent: "${send_alert.sent}"
```

---

## Module Reference

For a complete list of available modules and their parameters, see:
- [MODULES.md](MODULES.md) - Complete module registry
- [NAMESPACES.yaml](../NAMESPACES.yaml) - Module taxonomy

---

## Best Practices

1. **Always use `id` for steps** - Makes output referencing easier
2. **Use descriptive names** - `extract_product_price` not `step3`
3. **Add `description`** - Helps others understand your workflow
4. **Use `${env.VAR}` for secrets** - Never hardcode API keys
5. **Add retry for network operations** - APIs and web pages can be flaky
6. **Close resources** - Always close browsers with `on_error: continue`
7. **Version your workflows** - Track changes with semantic versioning
8. **Test with small datasets first** - Use `limit` parameters during development

---

## DSL Schema Validation (Future)

Future versions will support JSON Schema validation for workflows.

---

## Changelog

**1.0.0-alpha (2025-11-29)**
- Initial DSL specification
- Support for params, steps, output, variables
- Basic control flow (if, retry, error handling)
- Environment variable support

---

**Questions or suggestions?** [Open an issue](https://github.com/flytohub/flyto2/issues)
