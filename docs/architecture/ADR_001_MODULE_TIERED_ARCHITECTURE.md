# ADR-001: Module Tiered Architecture

**Status:** Implemented
**Date:** 2025-12-06 (Updated: 2025-01-24)
**Author:** Flyto Core Team

## Context

The current module system exposes all atomic modules (300+) directly to users, making it difficult for non-technical users to build workflows. Additionally, there is no validation to prevent invalid module combinations (e.g., connecting `api.chat` directly to `page.click` without a browser context).

## Decision

Implement a tiered module architecture with context-based connection validation.

### Module Tier System (Implemented)

| Tier | Enum Value | Display | Auto-Detection |
|------|------------|---------|----------------|
| FEATURED | `featured` | Prominent cards at top | `level=TEMPLATE` |
| STANDARD | `standard` | Normal category list | browser, api, ai, file, etc. |
| TOOLKIT | `toolkit` | Collapsed "Toolkit" section | string, array, math, etc. |
| INTERNAL | `internal` | Hidden from UI | meta, testing, debug |

```python
from core.modules.types import ModuleTier, TIER_DISPLAY_ORDER

class ModuleTier(str, Enum):
    FEATURED = "featured"    # Prominent display
    STANDARD = "standard"    # Normal display
    TOOLKIT = "toolkit"      # Collapsed section
    INTERNAL = "internal"    # Hidden from UI

TIER_DISPLAY_ORDER = {
    ModuleTier.FEATURED: 1,
    ModuleTier.STANDARD: 2,
    ModuleTier.TOOLKIT: 3,
    ModuleTier.INTERNAL: 99,
}
```

### Tier Auto-Detection Logic

Tiers are automatically assigned at registration time:

```python
def _resolve_tier(tier, level, tags, category, subcategory, module_id):
    # 1. Explicit tier parameter
    if tier is not None:
        return tier

    # 2. Internal categories
    if category in {'meta', 'testing', 'debug', 'training'}:
        return ModuleTier.INTERNAL

    # 3. Toolkit categories (low-level utilities)
    toolkit_categories = {
        'string', 'array', 'object', 'math', 'datetime',
        'validate', 'encode', 'convert', 'check', 'logic',
        'text', 'regex', 'format', 'hash', 'set', 'stats',
        'utility', 'random', 'crypto', 'path', 'vector',
        'shell', 'process', 'port',
    }
    if category in toolkit_categories:
        return ModuleTier.TOOLKIT
    if subcategory in toolkit_categories:
        return ModuleTier.TOOLKIT
    if module_id and module_id.split('.')[0] in toolkit_categories:
        return ModuleTier.TOOLKIT

    # 4. Advanced tag
    if tags and 'advanced' in tags:
        return ModuleTier.TOOLKIT

    # 5. Template level
    if level == ModuleLevel.TEMPLATE:
        return ModuleTier.FEATURED

    # 6. Default to standard
    return ModuleTier.STANDARD
```

### Current Distribution

| Tier | Count | Categories |
|------|-------|------------|
| STANDARD | 149 | ai, analysis, api, browser, cloud, communication, compare, data, database, document, element, file, flow, huggingface, image, notification, productivity, storage |
| TOOLKIT | 116 | array, check, convert, crypto, encode, format, hash, logic, math, object, path, random, regex, set, stats, string, text, utility, validate |
| INTERNAL | 8 | meta, testing, training |
| FEATURED | 0 | (awaiting template modules) |

### Category → Tier Mapping

**STANDARD Categories** (user-facing, visible by default):
```
ai, analysis, api, browser, cloud, communication, compare,
data, database, document, element, file, flow, http,
huggingface, image, llm, notification, productivity,
storage, ui, vision, webhook
```

**TOOLKIT Categories** (low-level utilities, collapsed):
```
array, check, convert, crypto, datetime, encode, format,
hash, logic, math, object, path, port, process, random,
regex, set, shell, stats, string, text, utility, validate, vector
```

**INTERNAL Categories** (hidden from UI):
```
debug, meta, testing, training
```

### Module Levels (Existing)

| Level | Name | Purpose |
|-------|------|---------|
| ATOMIC | Atomic Modules | Single-purpose building blocks |
| COMPOSITE | Composite Modules | High-level workflow combinations |
| TEMPLATE | Workflow Templates | One-click solutions |
| PATTERN | Advanced Patterns | System internal patterns |

### Context System

Modules declare their context requirements and provisions:

```python
@register_module(
    module_id="page.click",
    requires_context=["browser"],  # Must have browser context
    provides_context=["browser"],  # Still provides browser after execution
)
```

**Context Types:**
- `browser` - Browser instance available
- `page` - Page loaded in browser
- `file` - File handle or path available
- `data` - Structured data available
- `api_response` - API response available

### UI Visibility (Existing)

```python
class UIVisibility(str, Enum):
    DEFAULT = "default"  # Show in normal mode
    EXPERT = "expert"    # Show only in expert collapsed section
    HIDDEN = "hidden"    # Never show in UI
```

### Catalog API (Implemented)

```python
from core.modules.registry import get_catalog_manager, ModuleRegistry

# Method 1: Via catalog manager
cm = get_catalog_manager()
catalog = cm.get_tiered_catalog(lang='en')
start_catalog = cm.get_start_module_catalog(lang='en')
stats = cm.get_tier_statistics()

# Method 2: Via registry directly
catalog = ModuleRegistry.get_catalog(lang='en')
start_modules = ModuleRegistry.get_start_modules(lang='en')
```

### Catalog Response Format

```json
{
  "tiers": [
    {
      "id": "standard",
      "label": "Standard",
      "display_order": 2,
      "categories": [
        {
          "id": "browser",
          "label": "Browser",
          "modules": [
            {
              "module_id": "browser.launch",
              "tier": "standard",
              "category": "browser",
              "ui_label": "Launch Browser",
              "ui_description": "Launch a new browser instance",
              "ui_icon": "Globe",
              "ui_color": "#8B5CF6",
              "can_be_start": true,
              "requires_context": [],
              "provides_context": ["browser"]
            }
          ]
        }
      ]
    },
    {
      "id": "toolkit",
      "label": "Toolkit",
      "display_order": 3,
      "categories": [
        {
          "id": "string",
          "label": "String",
          "modules": [...]
        }
      ]
    }
  ],
  "total_count": 265,
  "tier_counts": {
    "standard": 149,
    "toolkit": 116
  }
}
```

### @register_module Parameters

```python
@register_module(
    module_id="browser.goto",
    level=ModuleLevel.ATOMIC,
    category="browser",

    # Tier (optional - auto-detected from category)
    tier=ModuleTier.STANDARD,

    # Context (optional, only needed for modules with dependencies)
    requires_context=None,
    provides_context=["browser", "page"],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label="Open URL",
    ui_description="Navigate browser to a URL",
    ui_group="Browser / Navigation",
    ui_icon="Globe",
    ui_color="#8B5CF6",

    # Schema
    params_schema={...},
    output_schema={...},

    # Connection rules
    can_receive_from=['*'],
    can_connect_to=['*'],
)
```

## UI Behavior

### Add Node Dialog

Frontend displays modules grouped by tier:

1. **FEATURED** (if any) - Large cards at top
2. **STANDARD** - Main category list, expanded by default
3. **TOOLKIT** - Collapsed section labeled "Toolkit" or "Developer Tools"

### Select Start Module Dialog

Same structure, but filtered to `can_be_start=True` modules only.

### Expert Mode (Optional)

Expandable section containing:
- Flow diagram of internal steps
- Read-only YAML view
- Execution logs
- Evolution history

## Consequences

### Benefits

1. **Simpler UX** - Normal users only see high-level actions
2. **Automatic Classification** - Tiers derived from category/level
3. **Extensible** - New modules automatically inherit tier based on category
4. **Clean API** - Frontend receives pre-grouped catalog

### Trade-offs

1. **Category Discipline** - Module authors must use correct categories
2. **Override Available** - Explicit `tier` parameter for edge cases

## Implementation Status

| Feature | Status |
|---------|--------|
| ModuleTier enum | Implemented |
| TIER_DISPLAY_ORDER | Implemented |
| _resolve_tier() auto-detection | Implemented |
| tier in @register_module | Implemented |
| tier in module metadata | Implemented |
| ModuleRegistry.get_catalog() | Implemented |
| ModuleRegistry.get_start_modules() | Implemented |
| ModuleCatalogManager.get_tiered_catalog() | Implemented |
| ModuleCatalogManager.get_start_module_catalog() | Implemented |
| ModuleCatalogManager.get_tier_statistics() | Implemented |
| @register_composite decorator | Planned |
| Composite modules | Planned |

## API Endpoints

The flyto-cloud backend exposes these endpoints for the tiered system:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v2/modules/catalog` | Tiered catalog (standard + toolkit) |
| `GET /api/v2/modules/starters` | Start-capable modules only |
| `GET /api/v2/modules/validate-connection` | Check if two modules can connect |
| `GET /api/v2/modules/compatible` | Get modules that can follow a given module |

## Related Documents

- [Composite README](../../src/core/modules/composite/README.md)
- [MODULE_SPECIFICATION.md](../MODULE_SPECIFICATION.md)
- [WRITING_MODULES.md](../WRITING_MODULES.md)
- [ADR-002: Module Hot Reload](./ADR_002_MODULE_HOT_RELOAD.md)
