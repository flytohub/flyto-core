# Composite Modules

High-level workflow templates combining multiple atomic and third-party modules.

## Module Tier System (v1.1)

The module system uses a tiered architecture for UI display:

| Tier | Display | Target User | Count |
|------|---------|-------------|-------|
| FEATURED | Prominent cards | End users | 0 |
| STANDARD | Normal list | All users | 149 |
| TOOLKIT | Collapsed section | Power users | 116 |
| INTERNAL | Hidden | System only | 8 |

### Category → Tier Mapping

**STANDARD** (user-facing):
```
ai, analysis, api, browser, cloud, communication, compare,
data, database, document, element, file, flow, http,
huggingface, image, llm, notification, productivity,
storage, ui, vision, webhook
```

**TOOLKIT** (low-level utilities):
```
array, check, convert, crypto, datetime, encode, format,
hash, logic, math, object, path, port, process, random,
regex, set, shell, stats, string, text, utility, validate, vector
```

**INTERNAL** (system only):
```
debug, meta, testing, training
```

### Tier Auto-Detection

Tiers are automatically assigned based on:
1. Explicit `tier` parameter (highest priority)
2. Category: `browser`, `api`, `ai` → STANDARD
3. Category: `string`, `array`, `math` → TOOLKIT
4. Subcategory or module_id prefix
5. Tag: `advanced` → TOOLKIT
6. Level: `TEMPLATE` → FEATURED

### Frontend Catalog API

```python
from core.modules.registry import get_catalog_manager

cm = get_catalog_manager()

# For "Add Node" dialog - all modules grouped by tier
catalog = cm.get_tiered_catalog(lang='en')
# Returns: { tiers: [...], total_count: 273, tier_counts: {...} }

# For "Select Start Module" dialog - only start-capable modules
start_catalog = cm.get_start_module_catalog(lang='en')

# Statistics
stats = cm.get_tier_statistics()
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
              "ui_label": "Launch Browser",
              "ui_icon": "Globe",
              ...
            }
          ]
        }
      ]
    },
    {
      "id": "toolkit",
      "label": "Toolkit",
      "display_order": 3,
      "categories": [...]
    }
  ],
  "total_count": 273,
  "tier_counts": {"standard": 149, "toolkit": 116, "internal": 8}
}
```

## Composite Module Architecture

Composite modules:
- Combine multiple atomic modules into high-level workflows
- Use `@register_composite` decorator
- Provide simplified parameter forms
- Include built-in error handling
- Automatically assigned to STANDARD or FEATURED tier

### Example Composite Module

```python
@register_composite(
    composite_id="composite.browser.search_and_screenshot",
    category="browser",
    tier=ModuleTier.STANDARD,  # Or auto-detected

    ui_label="Search and Screenshot",
    ui_description="Search the web and capture screenshot",
    ui_icon="Search",

    # Simplified parameters (hides internal complexity)
    ui_params_schema={
        "query": {"type": "string", "label": "Search Query", "required": True},
        "engine": {"type": "string", "options": ["google", "bing"], "default": "google"},
    },

    # Internal workflow steps (hidden from normal users)
    steps=[
        {"module": "browser.launch", "params": {}},
        {"module": "browser.goto", "params": {"url": "{{engine_url}}"}},
        {"module": "browser.screenshot", "params": {}},
    ],
)
```

## Planned Composite Modules

### Web Scraping Pipeline
- Combine browser automation + data extraction + CSV export
- Module ID: `composite.scraping.web_to_csv`

### Multi-Channel Notification
- Broadcast same message to Slack + Discord + Telegram + Email
- Module ID: `composite.notification.broadcast`

### API Data Pipeline
- Fetch API data + Transform + Store in database
- Module ID: `composite.pipeline.api_to_db`

### Scheduled Report Generation
- Collect data + Generate report + Email distribution
- Module ID: `composite.reporting.scheduled`

## Current Status

- Tier system: Implemented (v1.1)
- Catalog API: Implemented
- Composite decorator: Planned
- Composite modules: Planned

## Related Documents

- [ADR-001: Module Tiered Architecture](../../../docs/architecture/ADR_001_MODULE_TIERED_ARCHITECTURE.md)
- [MODULE_SPECIFICATION.md](../../../docs/MODULE_SPECIFICATION.md)
