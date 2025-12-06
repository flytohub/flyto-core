# ADR-001: Module Tiered Architecture

**Status:** Accepted
**Date:** 2025-12-06
**Author:** Flyto Core Team

## Context

The current module system exposes all atomic modules (127+) directly to users, making it difficult for non-technical users to build workflows. Additionally, there is no validation to prevent invalid module combinations (e.g., connecting `api.chat` directly to `page.click` without a browser context).

## Decision

Implement a tiered module architecture with context-based connection validation.

### Module Levels

| Level | Name | Target User | UI Visibility |
|-------|------|-------------|---------------|
| 1 | Workflow Templates | End users who want one-click solutions | Default visible (card + form) |
| 2 | Atomic Modules | System internal / Evolution / Planner | Hidden (expert collapsed section) |
| 3 | Composite Modules | Normal and advanced users | Default visible (main interaction) |
| 4 | Advanced Patterns | System internal / Composite internals | Hidden |

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

### UI Visibility

```python
class UIVisibility(str, Enum):
    DEFAULT = "default"  # Show in normal mode
    EXPERT = "expert"    # Show only in expert collapsed section
    HIDDEN = "hidden"    # Never show in UI
```

### Connection Validation

```python
def can_connect(source_module: str, target_module: str, context_chain: List[str]) -> ValidationResult:
    target_meta = get_module_metadata(target_module)

    if target_meta.requires_context:
        for ctx in target_meta.requires_context:
            if ctx not in context_chain:
                return ValidationResult(
                    valid=False,
                    reason=f"{target_module} requires {ctx} context"
                )

    return ValidationResult(valid=True)
```

### Metadata Schema

#### For Atomic Modules (@register_module)

```python
@register_module(
    module_id="browser.goto",
    level=ModuleLevel.ATOMIC,
    category="browser",

    # Context (optional, only needed for modules with dependencies)
    requires_context=None,
    provides_context=["browser", "page"],

    # UI metadata
    ui_visibility=UIVisibility.EXPERT,
    ui_label="Open URL",
    ui_description="Navigate browser to a URL",
    ui_group="Browser / Navigation",

    # Schema
    params_schema={...},
    output_schema={...},
)
```

#### For Composite Modules (@register_composite)

```python
@register_composite(
    composite_id="composite.browser.search_and_screenshot",
    category="browser",
    tags=["search", "screenshot"],

    # Context
    requires_context=None,
    provides_context=["file"],

    # UI metadata (default visible)
    ui_visibility=UIVisibility.DEFAULT,
    ui_label="Search and Screenshot",
    ui_description="Search the web and capture screenshot",
    ui_group="Browser / Common Tasks",
    ui_icon="Search",
    ui_color="#4285F4",

    # Form generation
    ui_params_schema={
        "query": {
            "type": "string",
            "label": "Search Query",
            "required": True,
            "ui_component": "input",
        },
        "engine": {
            "type": "string",
            "label": "Search Engine",
            "options": ["google", "bing", "duckduckgo"],
            "default": "google",
            "ui_component": "select",
        }
    },

    # Internal steps (not shown to normal users)
    steps=[...],
)
```

## UI Behavior

### Normal Mode (Default)

Users see:
- Level 1 Template cards
- Level 3 Composite cards
- Simple parameter forms
- Execution results

Users do NOT see:
- Atomic module list
- YAML workflow definition
- Internal step details

### Expert Mode (Collapsed Section)

Expandable section at bottom containing:
- Flow diagram of internal steps
- Read-only YAML view
- Execution logs
- Evolution history

YAML is NEVER directly editable in the UI. To customize:
1. Click "Copy to My Workflows"
2. Edit in new draft workspace
3. Save as custom composite

## Consequences

### Benefits

1. **Simpler UX** - Normal users only see high-level actions
2. **Automatic Validation** - Invalid connections prevented at design time
3. **Extensible** - New modules automatically inherit rules based on category
4. **No Manual JSON** - Connection rules derived from module metadata

### Trade-offs

1. **Migration** - Existing modules need `requires_context` / `provides_context` added
2. **Convention** - Module authors must follow context naming conventions

## Implementation Plan

1. Update `ModuleLevel` enum to include visibility
2. Add `UIVisibility` enum
3. Add `requires_context` and `provides_context` to `@register_module`
4. Add `ui_visibility` and `ui_params_schema` to `@register_composite`
5. Update existing composite modules with new metadata
6. Implement connection validation in UI layer

## API Endpoints

The flyto-cloud backend exposes these endpoints for the tiered system:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v2/modules/tiered` | Combined catalog (composite=default, atomic=expert) |
| `GET /api/v2/modules/composite` | Level 3 composite modules only |
| `GET /api/v2/modules/catalog` | Level 2 atomic modules only |
| `GET /api/v2/modules/validate-connection` | Check if two modules can connect |
| `GET /api/v2/modules/compatible` | Get modules that can follow a given module |
| `GET /api/v2/modules/starters` | Get modules that can start a workflow |

### Response Format (Tiered Endpoint)

```json
{
  "version": "2.0.0",
  "architecture": "ADR-001",
  "default": {
    "total": 9,
    "modules": [...],
    "groups": [
      {"id": "Browser / Search", "label": "Browser / Search", "count": 2}
    ]
  },
  "expert": {
    "total": 127,
    "modules": [...],
    "label": "Expert Mode",
    "description": "Advanced atomic modules for power users"
  }
}
```

### Module Format

```json
{
  "module_id": "composite.browser.search_and_notify",
  "level": "composite",
  "visibility": "default",
  "group": "Browser / Search",
  "label": "Web Search and Notify",
  "description": "Search the web and send results to Slack",
  "icon": "Search",
  "color": "#4285F4",
  "requires_context": [],
  "provides_context": ["data", "api_response"],
  "params_schema": {
    "query": {
      "type": "string",
      "label": "Search Query",
      "required": true,
      "ui_component": "input"
    }
  }
}
```

## Sync Architecture

### Current: Backend Restart Sync

```
flyto-core (GitHub)
     |
     v (git pull)
flyto-core (local sibling)
     |
     v (dynamic import on startup)
Backend Registry
     |
     v (HTTP API)
Frontend (5-min cache)
```

### Future: Hot Reload Sync

For production environments requiring zero-downtime updates:

1. **Webhook Trigger**: GitHub push triggers webhook to backend
2. **Hot Reload**: Backend reloads module registry without restart
3. **Cache Invalidation**: Frontend cache cleared via WebSocket
4. **Version Check**: Frontend polls version endpoint

See: [ADR-002: Module Hot Reload](./ADR_002_MODULE_HOT_RELOAD.md) (planned)

## Related Documents

- [MODULE_SPECIFICATION.md](../MODULE_SPECIFICATION.md)
- [WRITING_MODULES.md](../WRITING_MODULES.md)
- [CHANGELOG.md](../../CHANGELOG.md)
