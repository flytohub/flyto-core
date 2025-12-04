# Module Quick Reference

Quick guide for creating compliant Flyto Core modules.

---

## Module ID Formula

```
category.subcategory.action
```

**Examples:**
- `data.json.parse`
- `notification.slack.send_message`
- `browser.page.screenshot`
- `ai.openai.chat`

---

## Allowed Categories

### Atomic (No External Dependencies)
- `browser` - Browser automation
- `data` - Data transformation
- `utility` - Helper functions
- `file` - File operations
- `string` - String processing
- `array` - Array manipulation
- `math` - Mathematical operations

### Third-party (External Services)
- `ai` - AI services (OpenAI, Claude, etc.)
- `notification` - Messaging (Slack, Email, etc.)
- `database` - Databases (PostgreSQL, MySQL, etc.)
- `cloud` - Cloud storage (S3, GCS, etc.)
- `productivity` - Productivity tools (Notion, Sheets, etc.)
- `api` - Generic API calls
- `developer` - Developer tools (GitHub, etc.)

---

## Label Format

**Rule**: Title Case, 2-5 words, human-readable

**Examples:**
- ✅ "Parse JSON"
- ✅ "Send Slack Message"
- ✅ "Take Screenshot"
- ❌ "parse json" (not title case)
- ❌ "PARSE JSON" (all caps)
- ❌ "Parse" (too short, needs context)

---

## Color Palette

**Atomic Modules:**
- Browser: `#8B5CF6` (purple)
- Data: `#F59E0B` (amber)
- Utility: `#6B7280` (gray)
- File: `#6B7280` (gray)
- String: `#8B5CF6` (purple)
- Array: `#10B981` (green)
- Math: `#F59E0B` (amber)

**Third-party:**
- AI: `#EC4899` (pink)
- Notifications: Various (match service brand)
- Database: `#3B82F6` (blue)
- Cloud: `#06B6D4` (cyan)

---

## Input/Output Types

**Common Types:**
- `text` - Plain text string
- `json` - JSON object
- `html` - HTML content
- `file_path` - File system path
- `browser_instance` - Playwright browser
- `image` - Image file
- `any` - Accepts anything

**Example:**
```python
input_types=['text', 'json'],      # Can accept text or JSON
output_types=['json', 'object'],   # Produces JSON/object
```

---

## Required Fields Checklist

```python
@register_module(
    ✓ module_id='category.subcategory.action',
    ✓ version='1.0.0',
    ✓ category='category',
    ✓ subcategory='subcategory',
    ✓ tags=['tag1', 'tag2', ...],  # 2-5 tags
    ✓ label='Title Case Label',
    ✓ label_key='modules.category.subcategory.action.label',
    ✓ description='Clear description',
    ✓ description_key='modules.category.subcategory.action.description',
    ✓ icon='IconName',  # Valid Lucide icon
    ✓ color='#HEXCOL',  # Valid hex color
    ✓ input_types=[...],  # Optional but recommended
    ✓ output_types=[...], # Optional but recommended
    ✓ params_schema={...},
    ✓ output_schema={...},
    ✓ examples=[{...}],  # At least 1
    ✓ author='Your Name',
    ✓ license='MIT',
)
```

---

## Params Schema Structure

```python
params_schema={
    'param_name': {
        'type': 'string',  # string, number, boolean, array, object, select
        'label': 'Human Label',
        'label_key': 'modules.category.subcategory.action.params.param_name.label',
        'description': 'What this parameter does',
        'description_key': 'modules.category.subcategory.action.params.param_name.description',
        'required': True,  # or False
        'default': 'value',  # Optional
        'placeholder': 'hint',  # Optional
        'multiline': False,  # For text inputs
    }
}
```

---

## i18n Key Format

**Pattern:**
```
modules.{category}.{subcategory}.{action}.{field}
```

**Examples:**
```
modules.data.json.parse.label
modules.data.json.parse.description
modules.data.json.parse.params.text.label
modules.data.json.parse.examples.basic.title
```

---

## Common Icons

| Use Case | Icon Name |
|----------|-----------|
| Data/JSON | `Braces` |
| File | `FileText` |
| Database | `Database` |
| Cloud | `Cloud` |
| Email | `Mail` |
| Message | `MessageSquare` |
| Notification | `Bell` |
| Search | `Search` |
| Filter | `Filter` |
| Calculator | `Calculator` |
| API | `Globe`, `Link` |
| Image | `Image` |
| Code | `Code` |
| List | `List` |
| Package | `Package` |

[Full icon list](https://lucide.dev/)

---

## Quick Commands

```bash
# Create new module from template
python scripts/create_module.py \\
    --category data \\
    --subcategory xml \\
    --action parse \\
    --label "Parse XML"

# Lint a module
python scripts/lint_modules.py path/to/module.py

# Lint all modules
python scripts/lint_modules.py

# Test module registration
python -c "from core.modules import atomic; print('OK')"
```

---

## Validation Checklist

Before submitting a PR, verify:

- [ ] Module ID matches `category.subcategory.action`
- [ ] Category is in allowed list
- [ ] Label is Title Case, 2-5 words
- [ ] Color is valid hex (#RRGGBB)
- [ ] All required fields present
- [ ] i18n keys follow pattern
- [ ] At least 1 example included
- [ ] input_types/output_types declared
- [ ] Runs `python scripts/lint_modules.py` with no errors
- [ ] Module imports successfully
- [ ] i18n translations added to i18n/en.json

---

## Example: Perfect Module

```python
@register_module(
    module_id='data.json.parse',
    version='1.0.0',
    category='data',
    subcategory='json',
    tags=['data', 'json', 'parse', 'atomic'],
    label='Parse JSON',
    label_key='modules.data.json.parse.label',
    description='Parse JSON string into object',
    description_key='modules.data.json.parse.description',
    icon='Braces',
    color='#F59E0B',
    input_types=['text', 'string'],
    output_types=['json', 'object'],
    params_schema={
        'json_string': {
            'type': 'string',
            'label': 'JSON String',
            'label_key': 'modules.data.json.parse.params.json_string.label',
            'description': 'JSON string to parse',
            'required': True,
            'multiline': True,
        }
    },
    output_schema={
        'data': {'type': 'object', 'description': 'Parsed object'}
    },
    examples=[{
        'title': 'Parse API response',
        'params': {'json_string': '{"key": "value"}'}
    }],
    author='Flyto Core Team',
    license='MIT',
)
async def json_parse(context):
    import json
    return {'data': json.loads(context['params']['json_string'])}
```

---

**See also:**
- [Complete Specification](MODULE_SPECIFICATION.md)
- [Writing Modules Guide](WRITING_MODULES.md)
- [Contributing Guidelines](../CONTRIBUTING.md)
