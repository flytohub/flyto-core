# Module Specification

**Version**: 1.0.0
**Status**: Official Standard
**Purpose**: Strict guidelines for creating Flyto2 modules to ensure consistency, UI compatibility, and maintainability

---

## Table of Contents

- [Why We Need This](#why-we-need-this)
- [Module Naming Conventions](#module-naming-conventions)
- [Required Fields](#required-fields)
- [Optional Fields](#optional-fields)
- [Input/Output Types](#inputoutput-types)
- [Connection Compatibility](#connection-compatibility)
- [Validation Rules](#validation-rules)
- [UI Mapping Guidelines](#ui-mapping-guidelines)
- [Examples](#examples)
- [Enforcement](#enforcement)

---

## Why We Need This

### The Problem
Without strict guidelines, open source contributors might:
- Use inconsistent naming (`elementQuery` vs `element.query` vs `element_query`)
- Create incompatible input/output schemas
- Make modules that can't connect properly in UI
- Use unclear labels that confuse users
- Break UI generation logic

### The Solution
A strict specification that:
- ✅ Enforces naming conventions
- ✅ Validates metadata structure
- ✅ Ensures module compatibility
- ✅ Makes UI generation predictable
- ✅ Maintains professional quality

---

## Module Naming Conventions

### 1. Module ID Format

**MUST follow**: `category.subcategory.action`

```python
# ✅ CORRECT
module_id='browser.page.screenshot'
module_id='data.json.parse'
module_id='notification.slack.send_message'
module_id='ai.openai.chat'

# ❌ WRONG
module_id='browserScreenshot'           # No dots, camelCase
module_id='screenshot'                  # Missing category
module_id='browser.screenshot'          # Missing subcategory
module_id='BROWSER.PAGE.SCREENSHOT'     # Wrong case
```

### 2. Naming Rules

| Component | Rule | Example |
|-----------|------|---------|
| **category** | lowercase, single word | `browser`, `data`, `notification` |
| **subcategory** | lowercase, single word or service name | `page`, `json`, `slack`, `openai` |
| **action** | lowercase, underscore_case for multi-word | `screenshot`, `send_message`, `parse` |

### 3. Label Format

**MUST be**: Title Case, 2-5 words max, human-readable

```python
# ✅ CORRECT
label='Take Screenshot'
label='Send Slack Message'
label='Parse JSON'
label='OpenAI Chat'

# ❌ WRONG
label='screenshot'              # Not title case
label='TAKE SCREENSHOT'         # All caps
label='Take A Really Long Screenshot Of The Entire Page'  # Too long
label='Scrnsht'                 # Abbreviations
```

### 4. Category Standards

**Use these predefined categories ONLY:**

```python
ALLOWED_CATEGORIES = [
    # Atomic modules
    'browser',      # Browser automation
    'data',         # Data transformation
    'utility',      # Helper functions
    'file',         # File operations
    'string',       # String processing
    'array',        # Array manipulation
    'math',         # Mathematical operations

    # Third-party integrations
    'ai',           # AI services
    'notification', # Messaging/notifications
    'database',     # Database operations
    'cloud',        # Cloud storage
    'productivity', # Productivity tools (Notion, Sheets)
    'api',          # Generic API calls
    'developer',    # Developer tools (GitHub, etc.)

    # Future
    'workflow',     # Composite workflows (v1.1)
]
```

**Adding new categories requires maintainer approval.**

---

## Required Fields

Every module **MUST** include these fields:

```python
@register_module(
    # Identity (REQUIRED)
    module_id='category.subcategory.action',  # MUST match naming convention
    version='1.0.0',                          # MUST be semantic version

    # Classification (REQUIRED)
    category='category',                      # MUST be from ALLOWED_CATEGORIES
    subcategory='subcategory',                # MUST be lowercase
    tags=['tag1', 'tag2'],                    # MUST be list, 2-5 tags

    # Display (REQUIRED)
    label='Human Label',                      # MUST be Title Case, 2-5 words
    label_key='i18n.key.label',              # MUST follow i18n key format
    description='Clear description',          # MUST be 10-100 characters
    description_key='i18n.key.description',  # MUST follow i18n key format

    # Visual (REQUIRED)
    icon='IconName',                          # MUST be valid Lucide icon name
    color='#HEXCOLOR',                        # MUST be valid hex color

    # Schema (REQUIRED)
    params_schema={...},                      # MUST be valid JSON schema
    output_schema={...},                      # MUST be valid JSON schema

    # Documentation (REQUIRED)
    examples=[...],                           # MUST have at least 1 example
    author='Name or Team',                    # MUST be string
    license='MIT'                             # MUST be valid SPDX license
)
```

---

## Input/Output Types

### Type System for UI Connections

Each module MUST declare what types it accepts and produces:

```python
@register_module(
    # ... other fields ...

    # NEW: Connection compatibility
    input_types=['text', 'json'],        # What this module can accept
    output_types=['html', 'screenshot'], # What this module produces

    # NEW: Connection rules
    can_connect_to=['browser.*', 'data.json.*'],  # Which modules can receive output
    can_receive_from=['api.*', 'file.read'],      # Which modules can send input
)
```

### Standard Type List

```python
STANDARD_TYPES = {
    # Data types
    'text': 'Plain text string',
    'json': 'JSON object',
    'html': 'HTML content',
    'xml': 'XML content',
    'csv': 'CSV data',
    'binary': 'Binary data',

    # Resource types
    'url': 'Web URL',
    'file_path': 'File system path',
    'image': 'Image file',
    'screenshot': 'Screenshot image',

    # Browser types
    'browser_instance': 'Playwright browser',
    'page_instance': 'Playwright page',
    'element': 'Browser element',

    # API types
    'api_response': 'API response object',
    'webhook': 'Webhook payload',

    # Any
    'any': 'Accepts any type',
}
```

### Example: Module with Type Declarations

```python
@register_module(
    module_id='browser.page.screenshot',
    # ... other fields ...

    input_types=['browser_instance'],     # Needs a browser
    output_types=['screenshot', 'image'], # Produces screenshot

    can_receive_from=[
        'browser.instance.launch',        # Can connect from launch
        'browser.page.navigate',          # Can connect from navigate
    ],

    can_connect_to=[
        'file.write',                     # Can send to file write
        'cloud.s3.upload',                # Can send to S3
        'ai.vision.*',                    # Can send to vision AI
    ],
)
async def browser_screenshot(context):
    # ...
```

---

## Connection Compatibility

### How UI Uses This

When user drags a module in the visual editor:

```javascript
// UI checks compatibility
function canConnect(sourceModule, targetModule) {
    // Check if source output types match target input types
    const hasMatchingType = sourceModule.output_types.some(outType =>
        targetModule.input_types.includes(outType) ||
        targetModule.input_types.includes('any')
    );

    // Check if explicitly allowed
    const isExplicitlyAllowed = sourceModule.can_connect_to.some(pattern =>
        matchesPattern(targetModule.module_id, pattern)
    );

    return hasMatchingType || isExplicitlyAllowed;
}
```

### Pattern Matching

```python
# Exact match
can_connect_to=['file.read']

# Wildcard subcategory
can_connect_to=['browser.*']  # Matches browser.page.click, browser.instance.launch, etc.

# Wildcard action
can_connect_to=['*.json.*']   # Matches data.json.parse, api.json.stringify, etc.
```

---

## Validation Rules

### Automatic Validation

Every module is validated on registration:

```python
class ModuleValidator:
    def validate(self, metadata):
        errors = []

        # 1. Check module_id format
        if not re.match(r'^[a-z]+\.[a-z_]+\.[a-z_]+$', metadata['module_id']):
            errors.append('Invalid module_id format')

        # 2. Check category is allowed
        if metadata['category'] not in ALLOWED_CATEGORIES:
            errors.append(f'Category {metadata["category"]} not allowed')

        # 3. Check label format (Title Case, 2-5 words)
        if not self._is_title_case(metadata['label']):
            errors.append('Label must be Title Case')

        # 4. Check color is valid hex
        if not re.match(r'^#[0-9A-F]{6}$', metadata['color']):
            errors.append('Color must be valid hex (#RRGGBB)')

        # 5. Check i18n keys exist
        if not self._i18n_key_exists(metadata['label_key']):
            errors.append(f'i18n key {metadata["label_key"]} not found')

        # 6. Validate input/output types
        for t in metadata.get('input_types', []):
            if t not in STANDARD_TYPES and t != 'any':
                errors.append(f'Unknown input type: {t}')

        # 7. Check params_schema structure
        if not self._valid_json_schema(metadata['params_schema']):
            errors.append('Invalid params_schema')

        # 8. Ensure at least 1 example
        if len(metadata.get('examples', [])) < 1:
            errors.append('Must have at least 1 example')

        if errors:
            raise ValidationError(f'Module validation failed: {errors}')
```

### Validation Levels

```python
# STRICT mode (default) - Reject invalid modules
@register_module(..., validation='strict')

# WARN mode - Log warnings but allow registration
@register_module(..., validation='warn')

# PERMISSIVE mode - No validation (not recommended)
@register_module(..., validation='permissive')
```

---

## UI Mapping Guidelines

### How Metadata Maps to UI

```python
@register_module(
    module_id='notification.slack.send_message',

    # UI Block Title
    label='Send Slack Message',

    # UI Block Color & Icon
    color='#4A154B',  # Slack purple
    icon='MessageSquare',  # Lucide icon

    # UI Block Description (tooltip)
    description='Send a message to a Slack channel',

    # UI Form Fields (from params_schema)
    params_schema={
        'channel': {
            'type': 'string',
            'label': 'Channel',              # Field label
            'placeholder': '#general',       # Field placeholder
            'required': True,                # Field validation
        },
        'text': {
            'type': 'string',
            'label': 'Message',
            'multiline': True,               # Use textarea
            'required': True,
        },
        'icon_emoji': {
            'type': 'string',
            'label': 'Icon Emoji',
            'default': ':robot_face:',       # Field default
            'required': False,
        }
    },

    # UI Output Connectors (from output_schema)
    output_schema={
        'message_ts': {
            'type': 'string',
            'description': 'Message timestamp',
        },
        'ok': {
            'type': 'boolean',
            'description': 'Success status',
        }
    },
)
```

### UI Block Rendering

```
┌─────────────────────────────────────┐
│ 🟣 Send Slack Message              │  ← label + icon + color
├─────────────────────────────────────┤
│ ◉ Input: webhook_url               │  ← input_types
├─────────────────────────────────────┤
│ Channel: [#general      ]          │  ← params_schema
│ Message: [Hello!        ]          │
│ Icon:    [:robot_face:  ]          │
├─────────────────────────────────────┤
│ ○ Output: message_ts, ok           │  ← output_schema
└─────────────────────────────────────┘
```

---

## Examples

### ✅ PERFECT Module

```python
@register_module(
    # Identity
    module_id='data.json.parse',
    version='1.0.0',

    # Classification
    category='data',
    subcategory='json',
    tags=['data', 'json', 'parse', 'atomic'],

    # Display
    label='Parse JSON',
    label_key='modules.data.json.parse.label',
    description='Parse JSON string into object',
    description_key='modules.data.json.parse.description',

    # Visual
    icon='Braces',
    color='#F59E0B',

    # Connection types
    input_types=['text', 'string'],
    output_types=['json', 'object'],
    can_receive_from=['file.read', 'api.http.*'],
    can_connect_to=['data.*', 'notification.*'],

    # Schema
    params_schema={
        'json_string': {
            'type': 'string',
            'label': 'JSON String',
            'label_key': 'modules.data.json.parse.params.json_string.label',
            'description': 'JSON string to parse',
            'description_key': 'modules.data.json.parse.params.json_string.description',
            'required': True,
            'multiline': True,
        }
    },
    output_schema={
        'data': {
            'type': 'object',
            'description': 'Parsed JSON object',
        }
    },

    # Documentation
    examples=[{
        'title': 'Parse API response',
        'title_key': 'modules.data.json.parse.examples.api.title',
        'params': {
            'json_string': '{"name": "John", "age": 30}',
        }
    }],
    author='Flyto2 Team',
    license='MIT',
)
async def json_parse(context):
    import json
    params = context['params']
    data = json.loads(params['json_string'])
    return {'data': data}
```

### ❌ BAD Module (Don't Do This)

```python
@register_module(
    # ❌ Wrong: camelCase, no category structure
    module_id='parseJson',

    # ❌ Wrong: Invalid version
    version='1',

    # ❌ Wrong: Category not in allowed list
    category='utils',

    # ❌ Wrong: Not lowercase
    subcategory='JSON',

    # ❌ Wrong: Not enough tags
    tags=['json'],

    # ❌ Wrong: Not title case
    label='parse json string',

    # ❌ Wrong: No i18n key
    # label_key is missing!

    # ❌ Wrong: Too short
    description='Parse JSON',

    # ❌ Wrong: Invalid icon name
    icon='json-icon',

    # ❌ Wrong: Invalid color format
    color='orange',

    # ❌ Wrong: Missing required fields
    # input_types, output_types missing!

    # ❌ Wrong: Missing labels and descriptions
    params_schema={
        'data': {'type': 'string'}
    },

    # ❌ Wrong: No examples
    examples=[],

    # ❌ Wrong: No author
    # author is missing!
)
```

---

## Enforcement

### 1. Registration-time Validation

```python
# In registry.py
def register_module(**metadata):
    validator = ModuleValidator()

    try:
        validator.validate(metadata)
    except ValidationError as e:
        if STRICT_MODE:
            raise  # Reject module
        else:
            logger.warning(f'Module validation failed: {e}')

    # ... register module
```

### 2. CLI Linting Tool

```bash
# Validate a module file
flyto2 lint src/core/modules/my_module.py

# Output:
✓ Module ID format correct
✓ Category 'data' allowed
✗ Label 'parse json' must be Title Case
✗ Missing i18n key for label
✓ Color '#F59E0B' is valid hex
✗ Must have at least 1 example

Score: 3/6 checks passed
```

### 3. CI/CD Checks

```yaml
# .github/workflows/validate-modules.yml
- name: Validate Modules
  run: |
    python scripts/validate_modules.py
    # Fails PR if modules don't pass validation
```

### 4. Module Template Generator

```bash
# Generate a new module from template
flyto2 create-module --category data --subcategory xml --action parse

# Creates:
# src/core/modules/data/xml/parse.py
# With all required fields pre-filled
```

---

## Summary

### The Golden Rules

1. **Naming**: Always `category.subcategory.action`
2. **Categories**: Use predefined categories only
3. **Labels**: Title Case, 2-5 words, human-readable
4. **Types**: Declare input/output types for UI compatibility
5. **i18n**: Always include label_key and description_key
6. **Validation**: Must pass validation to be accepted
7. **Examples**: At least 1 working example required

### Benefits

✅ **Consistent** - All modules follow same structure
✅ **Predictable** - UI can reliably generate interfaces
✅ **Compatible** - Modules declare what they connect to
✅ **Professional** - High quality standard
✅ **Maintainable** - Easy to understand and modify
✅ **Scalable** - Clear rules for growth

### Next Steps

1. Read this specification thoroughly
2. Use `flyto2 create-module` to generate new modules
3. Run `flyto2 lint` before submitting
4. All PRs must pass validation checks

---

**Questions?** See [CONTRIBUTING.md](../CONTRIBUTING.md) or open a GitHub Discussion.
