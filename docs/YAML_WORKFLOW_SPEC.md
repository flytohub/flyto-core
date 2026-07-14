# YAML Workflow Specification v1.0

This document defines the complete specification for Flyto2 YAML workflows.

**Audience**: Users, Developers, Frontend Engineers

---

## Table of Contents

1. [Basic Structure](#1-basic-structure)
2. [Variable Syntax](#2-variable-syntax)
3. [Data Types](#3-data-types)
4. [Step Configuration](#4-step-configuration)
5. [Control Flow](#5-control-flow)
6. [Error Handling](#6-error-handling)
7. [Output Definition](#7-output-definition)
8. [Frontend UI Guidelines](#8-frontend-ui-guidelines)
9. [Common Pitfalls](#9-common-pitfalls)
10. [Complete Examples](#10-complete-examples)

---

## 1. Basic Structure

### 1.1 Minimal Workflow

```yaml
id: my_workflow
name: My First Workflow
version: "1.0.0"

steps:
  - id: step1
    module: file.read
    params:
      path: "/tmp/input.txt"
```

### 1.2 Full Workflow Structure

```yaml
# ============================================
# METADATA (Required)
# ============================================
id: complete_example              # Unique identifier (snake_case)
name: Complete Example Workflow   # Human-readable name
version: "1.0.0"                  # Semantic versioning
description: |                    # Multi-line description
  This workflow demonstrates all features.
  Use this as a reference.

# ============================================
# WORKFLOW INPUT PARAMETERS (Optional)
# ============================================
params:
  - name: input_url               # Parameter name
    type: string                  # Data type
    required: true                # Is required?
    description: "The URL to process"
    default: null                 # Default value (if not required)

  - name: output_format
    type: enum
    required: false
    default: "json"
    options: ["json", "csv", "xml"]  # Enum options

  - name: max_items
    type: number
    required: false
    default: 10
    min: 1                        # Validation: minimum
    max: 100                      # Validation: maximum

# ============================================
# EXECUTION STEPS (Required)
# ============================================
steps:
  - id: step1
    module: module.name
    params: {}
    # ... (see Section 4)

# ============================================
# WORKFLOW OUTPUT (Optional)
# ============================================
output:
  status: success
  data: ${final_step.result}
  processed_at: ${timestamp}
```

---

## 2. Variable Syntax

### 2.1 Basic Syntax

All variables use `${...}` syntax.

| Pattern | Description | Example |
|---------|-------------|---------|
| `${step_id}` | Entire step output | `${download.result}` |
| `${step_id.field}` | Specific field | `${api_call.status_code}` |
| `${step_id.field.subfield}` | Nested field | `${ai.result.data.summary}` |
| `${step_id.array.0}` | Array index (0-based) | `${search.items.0}` |
| `${params.name}` | Workflow input parameter | `${params.input_url}` |
| `${env.VAR_NAME}` | Environment variable | `${env.API_KEY}` |
| `${timestamp}` | Current ISO timestamp | `2024-01-15T10:30:00` |
| `${workflow.id}` | Workflow metadata | `my_workflow` |
| `${workflow.name}` | Workflow name | `My Workflow` |

### 2.2 Nested Path Access

```yaml
# AI returns complex response:
# {
#   "result": {
#     "analysis": {
#       "summary": "...",
#       "keywords": ["ai", "automation"],
#       "entities": [
#         {"name": "Claude", "type": "AI", "confidence": 0.95},
#         {"name": "GPT", "type": "AI", "confidence": 0.90}
#       ]
#     },
#     "metadata": {
#       "model": "gpt-4",
#       "tokens": 150
#     }
#   }
# }

steps:
  - id: ai_analyze
    module: ai.chat
    params:
      prompt: "Analyze this text..."

  # Access nested fields
  - id: use_summary
    module: notification.send
    params:
      message: ${ai_analyze.result.analysis.summary}

  # Access array
  - id: use_keywords
    module: array.join
    params:
      array: ${ai_analyze.result.analysis.keywords}
      separator: ", "

  # Access array element
  - id: first_entity
    module: log.info
    params:
      message: "First entity: ${ai_analyze.result.analysis.entities.0.name}"

  # Access nested in array element
  - id: entity_confidence
    module: condition.check
    params:
      value: ${ai_analyze.result.analysis.entities.0.confidence}
```

### 2.3 String Interpolation vs Direct Reference

```yaml
# IMPORTANT: These behave differently!

# Direct reference - preserves original type (object, array, number, etc.)
- id: pass_object
  module: object.pick
  params:
    object: ${previous.result}        # ← Gets the actual object/array

# String interpolation - converts to string
- id: build_message
  module: notification.send
  params:
    message: "Result: ${previous.result}"  # ← Converted to string

# Mixed interpolation - all become strings
- id: build_url
  module: api.get
  params:
    url: "https://api.example.com/${params.endpoint}?id=${data.id}"
```

**Rule**:
- `${var}` alone → preserves type
- `"text ${var} text"` → becomes string

### 2.4 Variable Resolution Order

Variables are resolved in this order:

1. `params.*` - Workflow input parameters
2. `env.*` - Environment variables
3. `step_id.*` - Previous step outputs (must be executed before)
4. Built-ins (`timestamp`, `workflow.*`)

```yaml
# CORRECT: step1 runs before step2
steps:
  - id: step1
    module: api.get
    params:
      url: ${params.api_url}

  - id: step2
    module: file.write
    params:
      content: ${step1.result}   # ✓ step1 already executed

# WRONG: Cannot reference future steps
steps:
  - id: step1
    module: file.write
    params:
      content: ${step2.result}   # ✗ step2 not yet executed!

  - id: step2
    module: api.get
    params:
      url: ${params.api_url}
```

---

## 3. Data Types

### 3.1 Supported Types in params_schema

| Type | YAML Example | JSON Schema | UI Component |
|------|--------------|-------------|--------------|
| `string` | `"hello"` | `{"type": "string"}` | Text input |
| `number` | `42` or `3.14` | `{"type": "number"}` | Number input |
| `integer` | `42` | `{"type": "integer"}` | Number input (no decimals) |
| `boolean` | `true` / `false` | `{"type": "boolean"}` | Toggle/Checkbox |
| `array` | `[1, 2, 3]` | `{"type": "array"}` | List editor |
| `object` / `json` | `{key: value}` | `{"type": "object"}` | JSON editor |
| `enum` | `"option1"` | `{"enum": [...]}` | Dropdown/Select |
| `file` | `"/path/to/file"` | `{"type": "string", "format": "file"}` | File picker |
| `url` | `"https://..."` | `{"type": "string", "format": "uri"}` | URL input |
| `email` | `"a@b.com"` | `{"type": "string", "format": "email"}` | Email input |
| `password` | `"***"` | `{"type": "string", "format": "password"}` | Password input |
| `textarea` | `"long text..."` | `{"type": "string", "format": "textarea"}` | Textarea |
| `code` | `"console.log()"` | `{"type": "string", "format": "code"}` | Code editor |
| `datetime` | `"2024-01-15T10:30"` | `{"type": "string", "format": "date-time"}` | DateTime picker |
| `date` | `"2024-01-15"` | `{"type": "string", "format": "date"}` | Date picker |
| `time` | `"10:30:00"` | `{"type": "string", "format": "time"}` | Time picker |
| `color` | `"#FF5733"` | `{"type": "string", "format": "color"}` | Color picker |
| `range` | `50` | `{"type": "number", "format": "range"}` | Slider |
| `selector` | `"#element"` | `{"type": "string", "format": "selector"}` | CSS selector input |

### 3.2 Type Coercion Rules

```yaml
# Numbers in strings are NOT auto-converted
params:
  count: "10"        # String "10", not number 10
  count: 10          # Number 10

# Booleans must be explicit
params:
  enabled: true      # Boolean true
  enabled: "true"    # String "true" - NOT boolean!
  enabled: yes       # YAML converts to boolean true
  enabled: "yes"     # String "yes"

# Arrays must use YAML array syntax
params:
  items: [1, 2, 3]           # Array
  items: "[1, 2, 3]"         # String "[1, 2, 3]" - NOT array!
  items:                     # Array (block style)
    - 1
    - 2
    - 3

# Objects must use YAML object syntax
params:
  config: {key: value}       # Object
  config: "{key: value}"     # String - NOT object!
  config:                    # Object (block style)
    key: value
```

### 3.3 Null and Empty Values

```yaml
# Null values
params:
  optional_field: null       # Explicit null
  optional_field: ~          # YAML null shorthand
  optional_field:            # Implicit null (empty value)

# Empty values
params:
  empty_string: ""           # Empty string (not null)
  empty_array: []            # Empty array (not null)
  empty_object: {}           # Empty object (not null)

# IMPORTANT: These are different!
params:
  field: null                # null - field exists but has no value
  field: ""                  # empty string - field has empty string value
  # (field omitted)          # undefined - field does not exist
```

---

## 4. Step Configuration

### 4.1 Step Properties

```yaml
steps:
  - id: step_id                    # Required: Unique step identifier
    module: category.action        # Required: Module to execute

    # Parameters passed to module
    params:
      param1: value1
      param2: ${previous.result}

    # Human-readable description (for UI/logs)
    description: "What this step does"

    # Store result in custom variable name
    output: custom_var_name        # Access via ${custom_var_name}

    # Conditional execution
    when: ${params.should_run}     # Only run if truthy

    # Error handling
    on_error: stop                 # stop | continue | retry

    # Retry configuration
    retry:
      count: 3                     # Max retry attempts
      delay_ms: 1000               # Delay between retries
      backoff: exponential         # none | linear | exponential

    # Timeout in seconds
    timeout: 30

    # Parallel execution marker
    parallel: true                 # Run with other parallel steps

    # Loop over array
    foreach: ${data.items}         # Iterate over array
    as: item                       # Variable name for current item
```

### 4.2 Step ID Rules

```yaml
# VALID step IDs
- id: step1
- id: fetch_data
- id: processItems
- id: step_2_validate

# INVALID step IDs
- id: 1step              # Cannot start with number
- id: step-one           # No hyphens (use underscore)
- id: step.one           # No dots (reserved for path access)
- id: my step            # No spaces
- id: step1              # Duplicate! Each ID must be unique
```

### 4.3 Module ID Format

```yaml
# Standard format: category.action
module: file.read
module: api.get
module: browser.click
module: array.map

# With namespace: namespace.category.action
module: core.file.read
module: pro.ai.analyze

# Module categories:
# - file.*       File operations
# - api.*        HTTP/API calls
# - browser.*    Browser automation
# - data.*       Data transformation
# - array.*      Array operations
# - object.*     Object operations
# - string.*     String operations
# - ai.*         AI/LLM operations
# - notification.* Notifications
# - condition.*  Conditionals
# - loop.*       Loops
```

---

## 5. Control Flow

### 5.1 Conditional Execution (when)

```yaml
steps:
  # Simple truthy check
  - id: optional_step
    module: notification.send
    when: ${params.send_notification}    # Runs if truthy
    params:
      message: "Done!"

  # Comparison operators
  - id: check_count
    module: log.info
    when: "${data.count} > 10"           # Comparison
    params:
      message: "Count exceeds 10"

  # Supported operators:
  # ==  Equal
  # !=  Not equal
  # >   Greater than
  # <   Less than
  # >=  Greater than or equal
  # <=  Less than or equal
  # contains      String/array contains
  # !contains     Does not contain

  # String contains
  - id: check_error
    module: alert.send
    when: "${response.message} contains error"
    params:
      message: "Error detected"

  # Negation
  - id: not_empty
    module: process.data
    when: "${data.items} != null"
    params:
      items: ${data.items}
```

### 5.2 Loops (foreach)

```yaml
steps:
  - id: get_items
    module: api.get
    params:
      url: "https://api.example.com/items"

  # Loop over array
  - id: process_each
    module: file.download
    foreach: ${get_items.result.items}    # Array to iterate
    as: item                               # Current item variable
    params:
      url: ${item.download_url}            # Access current item
      path: "/downloads/${item.filename}"

  # Loop with index (use array.enumerate first)
  - id: enumerate_items
    module: array.enumerate
    params:
      array: ${get_items.result.items}

  - id: process_with_index
    module: log.info
    foreach: ${enumerate_items.result}
    as: entry
    params:
      message: "Item ${entry.index}: ${entry.value.name}"
```

### 5.3 Parallel Execution

```yaml
steps:
  # Sequential step first
  - id: get_urls
    module: api.get
    params:
      url: "https://api.example.com/urls"

  # Parallel steps - run simultaneously
  - id: download_images
    module: file.download
    parallel: true
    params:
      url: ${get_urls.result.image_url}

  - id: download_videos
    module: file.download
    parallel: true
    params:
      url: ${get_urls.result.video_url}

  - id: download_docs
    module: file.download
    parallel: true
    params:
      url: ${get_urls.result.doc_url}

  # This step waits for all parallel steps to complete
  - id: merge_results
    module: object.merge
    params:
      objects:
        - ${download_images.result}
        - ${download_videos.result}
        - ${download_docs.result}
```

---

## 6. Error Handling

### 6.1 on_error Options

```yaml
steps:
  - id: risky_step
    module: api.get
    params:
      url: ${params.url}

    # Error handling strategies:
    on_error: stop        # DEFAULT: Stop workflow, mark as failed
    on_error: continue    # Log error, continue to next step
    on_error: retry       # Retry based on retry config
```

### 6.2 Retry Configuration

```yaml
steps:
  - id: flaky_api
    module: api.get
    params:
      url: "https://unreliable-api.com/data"
    on_error: retry
    retry:
      count: 3              # Try up to 3 times
      delay_ms: 1000        # Wait 1 second between retries
      backoff: exponential  # 1s, 2s, 4s delays

# Backoff strategies:
# - none: Fixed delay (delay_ms)
# - linear: delay_ms * attempt (1000, 2000, 3000)
# - exponential: delay_ms * 2^attempt (1000, 2000, 4000)
```

### 6.3 Error Information Access

```yaml
steps:
  - id: may_fail
    module: api.get
    params:
      url: ${params.url}
    on_error: continue

  # Check if previous step failed
  - id: handle_result
    module: condition.switch
    params:
      value: ${may_fail.ok}
      cases:
        true:
          - id: success_path
            module: log.info
            params:
              message: "Success: ${may_fail.result}"
        false:
          - id: error_path
            module: notification.send
            params:
              message: "Failed: ${may_fail.error}"
```

---

## 7. Output Definition

### 7.1 Workflow Output

```yaml
# Define what the workflow returns
output:
  # Static values
  workflow_id: ${workflow.id}
  executed_at: ${timestamp}

  # Step results
  final_data: ${last_step.result}

  # Nested structure
  summary:
    total_items: ${count_step.result}
    processed: ${process_step.result.count}

  # Conditional output
  status: ${final_step.ok}
  error: ${final_step.error}
```

### 7.2 Default Output (if not specified)

```yaml
# If no output section, workflow returns:
{
  "status": "completed",  # or "failed"
  "steps": {
    "step1": { ... },     # Each step's output
    "step2": { ... },
    ...
  },
  "execution_time": 1234  # milliseconds
}
```

---

## 8. Frontend UI Guidelines

### 8.1 Parameter Input Components

Based on `params_schema`, render appropriate UI components:

```yaml
# Module definition (for frontend reference)
params_schema:
  # Text input
  name:
    type: string
    label: "Name"
    placeholder: "Enter name..."
    required: true

  # Number with constraints
  count:
    type: number
    label: "Count"
    min: 1
    max: 100
    default: 10

  # Dropdown/Select
  format:
    type: enum
    label: "Output Format"
    options: ["json", "csv", "xml"]
    default: "json"

  # Textarea for long text
  content:
    type: string
    format: textarea
    label: "Content"
    rows: 5

  # Code editor
  script:
    type: string
    format: code
    label: "Script"
    language: "javascript"

  # File picker
  file_path:
    type: string
    format: file
    label: "Select File"
    accept: [".json", ".yaml"]

  # Toggle
  enabled:
    type: boolean
    label: "Enable Feature"
    default: true

  # Array input
  tags:
    type: array
    items:
      type: string
    label: "Tags"

  # Nested object
  config:
    type: object
    label: "Configuration"
    properties:
      timeout:
        type: number
      retries:
        type: number
```

### 8.2 Variable Picker UI

Frontend should provide variable picker for `${...}` syntax:

```
┌─────────────────────────────────────────┐
│ Select Variable                     [x] │
├─────────────────────────────────────────┤
│ ▼ Previous Steps                        │
│   ├── step1                             │
│   │   ├── result                        │
│   │   ├── result.data                   │
│   │   └── result.data.items             │
│   └── step2                             │
│       ├── result                        │
│       └── result.url                    │
│                                         │
│ ▼ Workflow Parameters                   │
│   ├── params.input_url                  │
│   └── params.max_items                  │
│                                         │
│ ▼ Environment                           │
│   ├── env.API_KEY                       │
│   └── env.DATABASE_URL                  │
│                                         │
│ ▼ Built-in                              │
│   ├── timestamp                         │
│   ├── workflow.id                       │
│   └── workflow.name                     │
└─────────────────────────────────────────┘
```

### 8.3 Step Output Preview

Show expected output structure for each module:

```yaml
# Module: api.get
output_schema:
  result:
    type: object
    properties:
      status_code:
        type: number
        description: "HTTP status code"
      headers:
        type: object
      body:
        type: any
        description: "Response body (parsed if JSON)"
      elapsed_ms:
        type: number

# UI should show:
# ${step_id.result.status_code} → number
# ${step_id.result.headers} → object
# ${step_id.result.body} → any
# ${step_id.result.elapsed_ms} → number
```

### 8.4 Connection Type Validation

Modules define input/output types for visual connection validation:

```yaml
# Module definition
input_types: ['string', 'url']    # What this module accepts
output_types: ['json']             # What this module outputs

# UI should:
# 1. Show compatible connections (green)
# 2. Warn on type mismatch (yellow)
# 3. Block invalid connections (red)
```

### 8.5 Validation Indicators

```yaml
# Required field missing
params:
  url:          # ← Show red border, "Required field"

# Type mismatch
params:
  count: "abc"  # ← Show warning, "Expected number"

# Invalid variable reference
params:
  data: ${nonexistent.step}  # ← Show error, "Step not found"

# Future step reference
params:
  data: ${step3.result}  # ← Show error, "Cannot reference future step"
  # (when current step is step2)
```

---

## 9. Common Pitfalls

### 9.1 Variable Syntax Errors

```yaml
# WRONG: Missing $
params:
  url: {params.url}          # ✗ Just a string "{params.url}"

# CORRECT
params:
  url: ${params.url}         # ✓ Variable reference

# WRONG: Spaces inside ${}
params:
  url: ${ params.url }       # ✗ Won't resolve

# CORRECT
params:
  url: ${params.url}         # ✓ No spaces

# WRONG: Wrong bracket type
params:
  url: $(params.url)         # ✗ Wrong syntax
  url: #{params.url}         # ✗ Wrong syntax

# CORRECT
params:
  url: ${params.url}         # ✓ Dollar sign + curly braces
```

### 9.2 Type Preservation Issues

```yaml
# PROBLEM: Type lost in string interpolation
- id: get_data
  module: api.get
  params:
    url: "https://api.example.com/items"
    # Returns: {"items": [1, 2, 3]}

- id: wrong_usage
  module: array.length
  params:
    array: "Items: ${get_data.result.items}"  # ✗ String, not array!

- id: correct_usage
  module: array.length
  params:
    array: ${get_data.result.items}           # ✓ Actual array
```

### 9.3 Null Reference Errors

```yaml
# PROBLEM: Accessing field that might not exist
- id: risky
  module: notification.send
  params:
    message: ${api_call.result.data.deep.field}
    # If any part is null → entire value is null

# SOLUTION 1: Check before access
- id: check_first
  module: condition.check
  when: ${api_call.result.data} != null
  params:
    value: ${api_call.result.data.deep.field}

# SOLUTION 2: Use default value (if module supports it)
- id: with_default
  module: string.coalesce
  params:
    values:
      - ${api_call.result.data.deep.field}
      - "default value"
```

### 9.4 Step Order Dependencies

```yaml
# WRONG: Referencing step that hasn't run yet
steps:
  - id: step2
    module: process.data
    params:
      input: ${step1.result}    # ✗ step1 not defined yet!

  - id: step1
    module: api.get
    params:
      url: "https://api.example.com"

# CORRECT: Define dependencies in order
steps:
  - id: step1
    module: api.get
    params:
      url: "https://api.example.com"

  - id: step2
    module: process.data
    params:
      input: ${step1.result}    # ✓ step1 already executed
```

### 9.5 YAML Formatting Issues

```yaml
# WRONG: Unquoted special characters
params:
  message: Hello: World        # ✗ Colon causes parsing error
  query: SELECT * FROM users   # ✗ May cause issues

# CORRECT: Quote strings with special characters
params:
  message: "Hello: World"      # ✓ Quoted
  query: "SELECT * FROM users" # ✓ Quoted

# WRONG: Indentation error
steps:
- id: step1                    # ✗ Wrong indentation
module: api.get
  params:
    url: "..."

# CORRECT: Consistent indentation (2 spaces)
steps:
  - id: step1                  # ✓ Correct indentation
    module: api.get
    params:
      url: "..."

# WRONG: Tab characters (YAML doesn't allow tabs)
steps:
	- id: step1                # ✗ Tab character!

# CORRECT: Use spaces only
steps:
  - id: step1                  # ✓ Spaces
```

### 9.6 Boolean and Null Confusion

```yaml
# YAML auto-converts these to boolean:
params:
  value: yes      # → true
  value: no       # → false
  value: on       # → true
  value: off      # → false
  value: true     # → true
  value: false    # → false

# If you want the string "yes", quote it:
params:
  value: "yes"    # → string "yes"

# YAML null values:
params:
  value: null     # → null
  value: ~        # → null
  value:          # → null (empty)
  value: "null"   # → string "null" (not null!)
```

### 9.7 Array Index Out of Bounds

```yaml
# PROBLEM: Array might be empty or shorter than expected
params:
  first: ${items.0}           # Might be null if empty
  tenth: ${items.9}           # Might be null if < 10 items

# SOLUTION: Check length first
- id: check_length
  module: array.length
  params:
    array: ${data.items}

- id: safe_access
  when: "${check_length.result} > 0"
  module: process.item
  params:
    item: ${data.items.0}
```

### 9.8 Circular Reference

```yaml
# WRONG: Self-reference
- id: loop
  module: data.transform
  params:
    input: ${loop.result}     # ✗ Cannot reference itself!

# WRONG: Circular dependency
- id: step_a
  module: process
  params:
    input: ${step_b.result}   # ✗ step_b references step_a!

- id: step_b
  module: process
  params:
    input: ${step_a.result}   # ✗ Circular!
```

### 9.9 Environment Variable Not Set

```yaml
# PROBLEM: Env var might not exist
params:
  api_key: ${env.API_KEY}     # null if not set

# SOLUTION: Validate in workflow params
params:
  - name: api_key
    type: string
    required: true
    default: ${env.API_KEY}   # Use env var as default
```

### 9.10 Special Characters in Paths

```yaml
# PROBLEM: Dots in key names conflict with path syntax
# Data: {"user.name": "John", "user": {"name": "Jane"}}

params:
  value: ${data.user.name}    # Gets "Jane" (nested path)
  # Cannot access "user.name" key directly!

# SOLUTION: Restructure data or use object.get with key parameter
- id: get_special_key
  module: object.get
  params:
    object: ${data}
    key: "user.name"          # Gets "John"
```

---

## 10. Complete Examples

### 10.1 Web Scraping Workflow

```yaml
id: web_scraper
name: Web Scraper
version: "1.0.0"
description: Scrape a webpage and save results

params:
  - name: url
    type: url
    required: true
    description: "URL to scrape"
  - name: selectors
    type: object
    required: true
    description: "CSS selectors for data extraction"
  - name: output_file
    type: string
    required: true
    default: "/tmp/scraped_data.json"

steps:
  - id: open_browser
    module: browser.open
    params:
      headless: true

  - id: navigate
    module: browser.goto
    params:
      url: ${params.url}
      wait_until: networkidle

  - id: extract_title
    module: browser.extract
    params:
      selector: ${params.selectors.title}
      attribute: textContent

  - id: extract_links
    module: browser.extract_all
    params:
      selector: ${params.selectors.links}
      attribute: href

  - id: extract_content
    module: browser.extract
    params:
      selector: ${params.selectors.content}
      attribute: innerHTML

  - id: close_browser
    module: browser.close

  - id: format_output
    module: object.create
    params:
      properties:
        url: ${params.url}
        title: ${extract_title.result}
        links: ${extract_links.result}
        content: ${extract_content.result}
        scraped_at: ${timestamp}

  - id: save_file
    module: file.write
    params:
      path: ${params.output_file}
      content: ${format_output.result}
      format: json

output:
  success: true
  file: ${params.output_file}
  data: ${format_output.result}
```

### 10.2 AI Analysis Pipeline

```yaml
id: ai_analysis_pipeline
name: AI Content Analysis
version: "1.0.0"
description: Analyze content using AI and route based on results

params:
  - name: content
    type: string
    format: textarea
    required: true
  - name: analysis_type
    type: enum
    options: ["sentiment", "summary", "keywords", "all"]
    default: "all"

steps:
  - id: analyze
    module: ai.chat
    params:
      model: gpt-4
      system: |
        You are a content analyst. Analyze the given content and return JSON with:
        - sentiment: positive/negative/neutral
        - summary: 2-3 sentence summary
        - keywords: array of 5-10 keywords
        - confidence: 0-1 score
      prompt: |
        Analyze this content:

        ${params.content}
      response_format: json
    timeout: 60
    retry:
      count: 2
      delay_ms: 2000

  - id: parse_response
    module: data.json_parse
    params:
      text: ${analyze.result.content}

  # Route based on sentiment
  - id: handle_positive
    module: notification.send
    when: "${parse_response.result.sentiment} == positive"
    params:
      channel: "#wins"
      message: |
        Positive content detected!
        Summary: ${parse_response.result.summary}

  - id: handle_negative
    module: notification.send
    when: "${parse_response.result.sentiment} == negative"
    params:
      channel: "#alerts"
      message: |
        Negative content needs attention!
        Summary: ${parse_response.result.summary}

  - id: save_keywords
    module: array.join
    params:
      array: ${parse_response.result.keywords}
      separator: ", "

  - id: store_result
    module: database.insert
    params:
      collection: "analyses"
      document:
        content_hash: ${hash.result}
        sentiment: ${parse_response.result.sentiment}
        summary: ${parse_response.result.summary}
        keywords: ${parse_response.result.keywords}
        confidence: ${parse_response.result.confidence}
        analyzed_at: ${timestamp}

output:
  sentiment: ${parse_response.result.sentiment}
  summary: ${parse_response.result.summary}
  keywords: ${save_keywords.result}
  confidence: ${parse_response.result.confidence}
```

### 10.3 Multi-Step Data Processing

```yaml
id: data_pipeline
name: Data Processing Pipeline
version: "1.0.0"
description: Fetch, transform, and export data

params:
  - name: api_url
    type: url
    required: true
  - name: filters
    type: object
    default: {}
  - name: export_format
    type: enum
    options: ["json", "csv", "excel"]
    default: "json"

steps:
  # Fetch data
  - id: fetch_data
    module: api.get
    params:
      url: ${params.api_url}
      headers:
        Authorization: "Bearer ${env.API_TOKEN}"
    retry:
      count: 3
      delay_ms: 1000
      backoff: exponential

  # Validate response
  - id: validate
    module: condition.assert
    params:
      condition: "${fetch_data.result.status_code} == 200"
      message: "API returned non-200 status"

  # Extract items
  - id: extract_items
    module: object.get
    params:
      object: ${fetch_data.result.body}
      path: "data.items"
      default: []

  # Filter items
  - id: filter_items
    module: array.filter
    params:
      array: ${extract_items.result}
      condition: ${params.filters}

  # Transform each item
  - id: transform_items
    module: array.map
    params:
      array: ${filter_items.result}
      transform:
        id: "$.id"
        name: "$.attributes.name"
        value: "$.attributes.value"
        processed_at: ${timestamp}

  # Count results
  - id: count_results
    module: array.length
    params:
      array: ${transform_items.result}

  # Export based on format
  - id: export_json
    module: file.write
    when: "${params.export_format} == json"
    params:
      path: "/output/data.json"
      content: ${transform_items.result}
      format: json

  - id: export_csv
    module: data.csv_write
    when: "${params.export_format} == csv"
    params:
      path: "/output/data.csv"
      data: ${transform_items.result}

  - id: export_excel
    module: data.excel_write
    when: "${params.export_format} == excel"
    params:
      path: "/output/data.xlsx"
      data: ${transform_items.result}

  # Notification
  - id: notify
    module: notification.send
    params:
      message: |
        Data pipeline completed!
        - Total items: ${count_results.result}
        - Format: ${params.export_format}
        - Time: ${timestamp}

output:
  success: true
  total_items: ${count_results.result}
  export_format: ${params.export_format}
  executed_at: ${timestamp}
```

---

## 11. Execution Semantics

This section defines the precise behavior of the workflow engine for edge cases.

### 11.1 Variable Resolution Behavior

```yaml
# Rule: Non-existent paths return null, do not throw exceptions
${step.nonexistent.path}  # Returns null

# Exception: Comparisons in 'when' conditions treat null as falsy
when: ${data.value}       # False if data.value is null/undefined

# Rule: Type coercion in string interpolation
message: "Value: ${data.number}"  # Number converted to string
```

### 11.2 Foreach Aggregation Behavior

```yaml
# Rule: foreach step result is always an array of iteration results
- id: process_items
  module: data.transform
  foreach: ${input.items}      # Array of 3 items
  as: item
  params:
    data: ${item}

# Result: process_items.result = [result1, result2, result3]
# Order matches original array order

# Rule: If iteration fails with on_error: continue
# Failed iteration produces: { ok: false, error: "..." }
# process_items.result = [result1, { ok: false, error: "..." }, result3]

# Rule: If iteration fails with on_error: stop
# Entire foreach step fails immediately
```

### 11.3 Parallel Execution Semantics

```yaml
# Rule: Consecutive parallel: true steps form a parallel group
steps:
  - id: step1
    parallel: true  # Group A start

  - id: step2
    parallel: true  # Group A

  - id: step3       # Group A ends, step3 waits for A to complete

  - id: step4
    parallel: true  # Group B start

# Rule: Error propagation in parallel groups
# If any step in group has on_error: stop and fails:
#   - Cancel other running steps in same group
#   - Steps after group do not execute
#   - Workflow fails

# Rule: Data dependencies in parallel groups
# Steps in same parallel group should NOT reference each other
# Bad: step2 cannot use ${step1.result} if both are parallel: true
```

### 11.4 Timeout Behavior

```yaml
# Rule: Step timeout applies to single execution, not retries
- id: slow_api
  module: api.get
  timeout: 30          # Each attempt has 30s timeout
  retry:
    count: 3
    delay_ms: 1000

# If timeout occurs:
#   step.ok = false
#   step.error = "Step timed out after 30 seconds"
#   Follows on_error handling (stop/continue/retry)

# Rule: No timeout means system default (typically 300s)
# Rule: timeout: 0 means no timeout limit
```

### 11.5 Retry Behavior

```yaml
# Rule: Retry count is additional attempts after first failure
retry:
  count: 3  # Total 4 attempts: 1 initial + 3 retries

# Rule: Backoff calculation
# none:        delay_ms (constant)
# linear:      delay_ms * attempt (1000, 2000, 3000, ...)
# exponential: delay_ms * 2^attempt (1000, 2000, 4000, ...)

# Rule: on_error: retry without retry config uses defaults
# Default: count=3, delay_ms=1000, backoff=linear
```

### 11.6 Conditional Execution (when)

```yaml
# Truthy values: non-empty string, non-zero number, non-empty array/object, true
# Falsy values:  empty string, 0, empty array/object, null, false

# Comparison operators
when: "${value} == 10"        # Equality (type-coerced)
when: "${value} === 10"       # Strict equality
when: "${value} != null"      # Not null
when: "${value} > 5"          # Greater than
when: "${value} >= 5"         # Greater than or equal
when: "${value} < 10"         # Less than
when: "${value} <= 10"        # Less than or equal

# String operators
when: "${text} contains error"      # Substring match
when: "${text} !contains error"     # No substring match
when: "${text} startsWith http"     # Prefix match
when: "${text} endsWith .json"      # Suffix match
when: "${text} matches ^[a-z]+$"    # Regex match

# Array operators
when: "${array} contains value"     # Array includes value
when: "${array}.length > 0"         # Array not empty

# Logical operators (evaluated left to right)
when: "${a} && ${b}"                # AND
when: "${a} || ${b}"                # OR
when: "!${a}"                       # NOT
```

### 11.7 Output Variable Naming

```yaml
# Rule: Step output is stored in context with step ID as key
- id: fetch_data
  module: api.get
  # Result accessible as ${fetch_data.result}

# Rule: Custom output variable name
- id: fetch_data
  module: api.get
  output: api_response
  # Result accessible as both:
  #   ${fetch_data.result}
  #   ${api_response.result}
```

### 11.8 Workflow Output Resolution

```yaml
# Rule: If output section exists, only return resolved output
output:
  data: ${final_step.result}
  count: ${count_step.result}
# Returns: { data: ..., count: ..., __metadata__: { ... } }

# Rule: If no output section, return default structure
# Returns: {
#   status: "completed",
#   steps: { step1: {...}, step2: {...} },
#   execution_time: 1234
# }
```

---

## 12. Workflow Metadata (Optional)

Optional fields for marketplace, search, and organization:

```yaml
id: my_workflow
name: My Workflow
version: "1.0.0"
description: "Workflow description"

# Optional metadata
tags: ["browser", "scraping", "demo"]
category: "browser_automation"
author: "flyto"
visibility: "public"    # public | private | unlisted
icon: "robot"           # Icon identifier for UI
color: "#3B82F6"        # Theme color for UI
```

These fields are for UI/marketplace use; the engine ignores them.

---

## Appendix A: Reserved Keywords

These words cannot be used as step IDs:

- `params`
- `env`
- `timestamp`
- `workflow`
- `output`
- `steps`
- `null`
- `true`
- `false`

---

## Appendix B: Module Categories Quick Reference

| Category | Description | Example Modules |
|----------|-------------|-----------------|
| `file.*` | File operations | `file.read`, `file.write`, `file.copy` |
| `api.*` | HTTP requests | `api.get`, `api.post`, `api.graphql` |
| `browser.*` | Browser automation | `browser.goto`, `browser.click`, `browser.extract` |
| `data.*` | Data conversion | `data.json_parse`, `data.csv_read` |
| `array.*` | Array operations | `array.map`, `array.filter`, `array.reduce` |
| `object.*` | Object operations | `object.pick`, `object.merge`, `object.get` |
| `string.*` | String operations | `string.replace`, `string.split`, `string.template` |
| `ai.*` | AI/LLM calls | `ai.chat`, `ai.embed`, `ai.analyze` |
| `notification.*` | Notifications | `notification.send`, `notification.email` |
| `condition.*` | Conditionals | `condition.check`, `condition.switch` |
| `loop.*` | Loop control | `loop.while`, `loop.times` |
| `image.*` | Image processing | `image.resize`, `image.convert` |
| `database.*` | Database operations | `database.query`, `database.insert` |

---

## Version History

| Version | Date       | Changes                                            |
|---------|------------|----------------------------------------------------|
| 1.0.0   | 2025-12-05 | Initial specification                              |
| 1.1.0   | 2025-12-06 | Added execution semantics, metadata fields         |

---

*This document is the single source of truth for YAML workflow syntax.*
