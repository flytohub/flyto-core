# Core Minimal Architecture

**Version:** 1.0.0
**Date:** 2026-01-30
**Status:** Implemented (Phase 4)

## Overview

The Flyto core has been restructured to follow a **Core Minimal** architecture where:

1. **Core** contains only essential components (runtime, engine, flow modules)
2. **Plugins** handle all other functionality (LLM, Browser, Database, etc.)

This separation provides:
- **Isolation**: Plugin crashes don't affect core
- **Flexibility**: Plugins can use different dependency versions
- **Scalability**: Plugins can be scaled independently
- **Maintainability**: Smaller core is easier to maintain

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         FLYTO CORE                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   Runtime   │  │   Engine    │  │    Builtin Modules      │ │
│  │             │  │             │  │                         │ │
│  │ - Invoker   │  │ - Executor  │  │  flow.branch            │ │
│  │ - Router    │  │ - Context   │  │  flow.switch            │ │
│  │ - Manager   │  │ - Trace     │  │  flow.loop              │ │
│  │ - Protocol  │  │             │  │  flow.fork/merge/join   │ │
│  │ - Process   │  │             │  │  flow.start/end         │ │
│  │ - Health    │  │             │  │  flow.trigger           │ │
│  └─────────────┘  └─────────────┘  │  flow.invoke/subflow    │ │
│                                     └─────────────────────────┘ │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  Secrets    │  │  Metering   │  │    Permissions          │ │
│  │   Proxy     │  │   Tracker   │  │                         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ JSON-RPC over stdio
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         PLUGINS                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ flyto-official_  │  │ flyto-official_  │                    │
│  │     database     │  │       llm        │                    │
│  │                  │  │                  │                    │
│  │  - query         │  │  - chat          │                    │
│  │  - insert        │  │  - embedding     │                    │
│  │  - update        │  │                  │                    │
│  │  - delete        │  │                  │                    │
│  └──────────────────┘  └──────────────────┘                    │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ flyto-official_  │  │   third-party    │                    │
│  │     browser      │  │    plugins...    │                    │
│  │                  │  │                  │                    │
│  │  - goto          │  │  - slack         │                    │
│  │  - click         │  │  - github        │                    │
│  │  - screenshot    │  │  - email         │                    │
│  └──────────────────┘  └──────────────────┘                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
src/core/
├── runtime/                 # Plugin runtime system
│   ├── __init__.py
│   ├── invoke.py           # RuntimeInvoker (dual-track routing)
│   ├── routing.py          # ModuleRouter (prefer plugin, fallback legacy)
│   ├── protocol.py         # JSON-RPC encoder/decoder
│   ├── process.py          # Subprocess management
│   ├── manager.py          # PluginManager
│   ├── health.py           # Health checker
│   ├── config.py           # Runtime configuration
│   ├── types.py            # Type definitions
│   └── exceptions.py       # Runtime exceptions
│
├── secrets/                 # Secret management
│   ├── __init__.py
│   └── proxy.py            # SecretsProxy (ref/resolve pattern)
│
├── metering/               # Usage tracking
│   ├── __init__.py
│   └── tracker.py          # MeteringTracker
│
├── modules/
│   ├── builtin/            # Flow modules (in-process)
│   │   └── __init__.py     # BUILTIN_MODULE_IDS, is_builtin_module()
│   │
│   ├── atomic/             # Legacy modules (deprecated)
│   │   ├── flow/           # Flow control (stays in core)
│   │   ├── browser/        # → flyto-official_browser plugin
│   │   ├── llm/            # → flyto-official_llm plugin
│   │   ├── database/       # → flyto-official_database plugin
│   │   └── ...
│   │
│   └── registry.py         # Module registry
│
└── engine/                 # Workflow engine
    └── step_executor/      # Step execution
```

## Builtin Modules (Flow Control)

These modules run in-process and are essential for workflow execution:

| Module | Description |
|--------|-------------|
| `flow.branch` | Conditional branching (if/then) |
| `flow.switch` | Multi-way branching (switch/case) |
| `flow.loop` | Iteration control (repeat N times) |
| `flow.foreach` | List iteration |
| `flow.goto` | Unconditional jump |
| `flow.fork` | Split into parallel branches |
| `flow.merge` | Combine multiple inputs |
| `flow.join` | Wait for parallel branches |
| `flow.start` | Workflow entry point |
| `flow.end` | Workflow exit point |
| `flow.trigger` | Event triggers |
| `flow.invoke` | Subflow execution |
| `flow.container` | Embedded subflow |
| `flow.subflow` | External workflow reference |
| `flow.breakpoint` | Human approval |

## Plugin System

Plugins are subprocess-based modules that communicate via JSON-RPC:

### Plugin Structure

```
plugins/
└── flyto-official_[category]/
    ├── plugin.manifest.json    # Plugin metadata + step definitions
    ├── main.py                 # JSON-RPC entry point
    ├── requirements.txt        # Python dependencies
    └── steps/
        ├── __init__.py
        └── [step].py           # Step implementations
```

### Available Plugins

| Plugin | Steps | Description |
|--------|-------|-------------|
| `flyto-official_database` | query, insert, update, delete | SQL database operations |
| `flyto-official_llm` | chat, embedding | LLM operations (OpenAI, Anthropic) |
| `flyto-official_browser` | goto, click, screenshot | Browser automation (Playwright) |

## Routing Logic

The RuntimeInvoker uses dual-track routing:

1. **Check** if module is builtin (flow.*) → run in-process
2. **Check** if plugin exists and is healthy → use plugin
3. **Fallback** to legacy module if plugin fails (configurable)
4. **Error** if no handler available

```python
# Routing configuration
routing:
  default_prefer: plugin       # Prefer plugin over legacy
  default_fallback: legacy     # Fallback to legacy if plugin fails
  force_plugin_default: false  # Don't force plugin (allow fallback)
```

## Migration Guide

### For Module Developers

**Before (Atomic Module):**
```python
@register_module("llm.chat")
class LlmChat(BaseModule):
    async def execute(self):
        # Implementation
```

**After (Plugin):**
```python
# In plugin's steps/chat.py
async def execute_chat(input_data, config, context):
    # Implementation
    return {"ok": True, "output": {...}}
```

### For Workflow Authors

No changes needed! The routing system automatically:
- Uses plugins when available
- Falls back to legacy modules when needed
- Maintains backward compatibility

## Performance Considerations

- **Subprocess overhead**: ~10-30ms per invocation
- **Process pooling**: Plugins stay running for reuse
- **Lazy loading**: Plugins start on first invoke
- **Health checks**: Unhealthy plugins are restarted

## Future Plans

1. **Phase M**: Multi-tenant isolation (dedicated plugin pools)
2. **Phase F**: Frontend integration (plugin marketplace UI)
3. Remove `atomic/` directory after full migration
