# Data Flow Architecture

**Version**: 1.0.0
**Status**: RFC
**Last Updated**: 2025-01-06

## Core Principle: Single Source of Truth

All execution logic, data flow, and variable resolution MUST be in `flyto-core`.
`flyto-cloud` only handles UI rendering and thin adaptation layer.

```
┌─────────────────────────────────────────────────────────────────┐
│  flyto-core (All Logic - Single Source of Truth)               │
│                                                                 │
│  ├── WorkflowEngine        - Execution, scheduling, routing    │
│  ├── ExecutionContext      - State management, data tracking   │
│  ├── VariableResolver      - {{}} syntax, path resolution      │
│  ├── EventRouter           - Edge-based control flow           │
│  ├── ResourceInjector      - Resource edge data injection      │
│  ├── VarCatalog (NEW)      - Introspection API for UI          │
│  └── Module Metadata       - Ports, types, connection rules    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓ SDK API
┌─────────────────────────────────────────────────────────────────┐
│  flyto-cloud (UI + Thin Adapter)                                │
│                                                                 │
│  ├── Render workflow graph                                      │
│  ├── Display parameter forms                                    │
│  ├── Show available variables (from core VarCatalog)            │
│  ├── Stream execution progress                                  │
│  ├── Handle auth/session/multi-tenant                           │
│  └── NO execution logic, NO validation logic                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Engine SDK Interface

### Required API Endpoints

```python
# flyto-core/src/core/engine/sdk.py

class EngineSDK:
    """Stable interface for flyto-cloud to consume"""

    # Version for compatibility checking
    api_version: str = "1.0"

    def validate(self, workflow: dict) -> ValidationResult:
        """Validate workflow structure and connections"""

    def execute(self, workflow: dict, inputs: dict, options: dict) -> ExecutionResult:
        """Execute workflow and return result (blocking)"""

    async def execute_stream(
        self, workflow: dict, inputs: dict, options: dict
    ) -> AsyncIterator[EngineEvent]:
        """Execute workflow with streaming events"""

    def introspect(
        self, workflow: dict, node_id: str,
        mode: Literal["edit", "runtime"] = "edit",
        context_snapshot: dict = None
    ) -> VarCatalog:
        """Get available variables for a node (for UI sidebar)"""

    def get_execution_trace(self, execution_id: str) -> ExecutionTrace:
        """Get detailed execution trace for debugging"""

    # Control plane
    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution"""

    def pause(self, execution_id: str) -> bool:
        """Pause a running execution"""

    def resume(self, execution_id: str) -> bool:
        """Resume a paused execution"""
```

### Engine Events (Streaming)

```python
@dataclass
class EngineEvent:
    """Event emitted during workflow execution"""
    type: Literal[
        "engine_start",
        "node_start",
        "node_end",
        "log",
        "partial_output",  # For LLM streaming, progress, etc.
        "error",
        "engine_end"
    ]
    ts: float                    # Unix timestamp
    execution_id: str
    node_id: Optional[str]
    payload: Dict[str, Any]      # Type-specific data
```

### VarCatalog (Introspection API)

This is the key API for UI to show "available variables" without implementing logic.

**Two modes**:
- `edit`: Based on graph structure only (schema-inferred types, no examples)
- `runtime`: With execution context (real types, actual examples from trace)

```python
@dataclass
class VarCatalog:
    """Available variables for a node at edit/runtime"""

    schema_version: str = "1.0"
    mode: Literal["edit", "runtime"]

    # Input ports for this node
    # {{input}} = {{inputs.main}} (shorthand for main port)
    # {{inputs.<port>}} for specific port
    inputs: Dict[str, PortVarInfo]

    # All upstream node outputs, structured by node -> port -> fields
    # {{node_id}} = full output
    # {{node_id.<port>}} = specific port
    # {{node_id.<port>.field}} = nested field
    nodes: Dict[str, NodeVarInfo]

    # Global/workflow variables
    # {{global.var}}
    globals: Dict[str, VarInfo]

    # Workflow parameters
    # {{params.name}}
    params: Dict[str, VarInfo]

    # Environment variables (only safe ones, never secrets)
    # {{env.VAR}} - filtered by allowlist
    env: Dict[str, VarInfo]


@dataclass
class NodeVarInfo:
    """Variable info for a specific node"""
    node_id: str
    node_type: str  # module_id
    ports: Dict[str, PortVarInfo]  # port_id -> info
    is_reachable: bool  # Whether this node is upstream of current


@dataclass
class PortVarInfo:
    """Variable info for a specific port"""
    port_id: str
    fields: Dict[str, VarInfo]  # Nested field structure
    type: str  # Overall port type
    example: Any  # Example value (runtime only)


@dataclass
class VarInfo:
    """Single variable/field info"""
    path: str               # Full path, e.g., "node1.output.data.items[0]"
    type: str               # "string", "number", "boolean", "object", "array", "any"
    description: str        # Human-readable description
    example: Any            # Example value (None if edit-mode and no schema default)
    origin_node: str        # Which node produced this
    is_available: bool      # Whether reachable from current node

    # Edit vs Runtime metadata
    source: Literal["schema", "trace"]  # Where type/example came from
    confidence: float       # 0.0-1.0, type inference confidence (edit-mode)
    availability: Literal["edit", "runtime", "both"]
```

---

## Cloud Adapter Pattern

### What Cloud Adapter Should Do

```python
# flyto-cloud/src/ui/web/backend/services/engine_adapter.py

class EngineAdapter:
    """Thin adapter between HTTP/WebSocket and core engine"""

    def __init__(self):
        from core.engine import EngineSDK
        self.engine = EngineSDK()

    async def execute_workflow(self, request: ExecuteRequest) -> AsyncGenerator:
        """
        1. Extract auth/user context
        2. Call core engine
        3. Stream results via WebSocket
        4. Handle cancellation/pause
        """
        # Prepare inputs with user context
        inputs = {
            **request.inputs,
            "__user_id": request.user_id,
            "__tenant_id": request.tenant_id,
        }

        # Call core - NO logic here, just pass-through
        result = await self.engine.execute(
            workflow=request.workflow,
            inputs=inputs,
            options=request.options,
        )

        # Stream to frontend
        yield result

    async def get_available_variables(self, workflow: dict, node_id: str) -> VarCatalog:
        """Get available variables for UI sidebar - just call core"""
        return self.engine.introspect(workflow, node_id)
```

### What Cloud Adapter Should NOT Do

- NO validation logic (call `engine.validate()`)
- NO variable resolution (core does it)
- NO connection rule checking (core does it)
- NO execution routing decisions (core does it)

---

## Implementation Phases

### Phase 1: Minimum Viable (Core API + Cloud Sidebar)

**Goal**: Users can see and use available variables without guessing syntax.

#### Core Tasks:
1. [ ] Create `VarCatalog` data structure
2. [ ] Implement `engine.introspect()` API
3. [ ] Add `prompt_source` to llm.agent (auto/manual)
4. [ ] Ensure `{{input}}` auto-binding works

#### Cloud Tasks:
1. [ ] Add API endpoint: `GET /api/variables/{workflow_id}/{node_id}`
2. [ ] Add sidebar component showing available variables
3. [ ] Click to insert `{{variable}}` into current field

### Phase 2: n8n-level UX

**Goal**: Expression editor with autocomplete and drag-drop.

#### Core Tasks:
1. [ ] `engine.parse_expression(expr)` - Parse and validate
2. [ ] `engine.autocomplete(prefix, ctx)` - Suggest completions
3. [ ] `engine.validate_expression(expr, expected_type)` - Type check

#### Cloud Tasks:
1. [ ] Expression editor popup with syntax highlighting
2. [ ] Autocomplete dropdown as user types
3. [ ] Drag-drop from sidebar to parameter fields
4. [ ] Type mismatch warnings

### Phase 3: Debug & Lineage

**Goal**: Visual debugging with data flow inspection.

#### Core Tasks:
1. [ ] Standardize `ExecutionTrace` format
2. [ ] Per-node `input_snapshot` and `output_snapshot`
3. [ ] Edge data flow summary

#### Cloud Tasks:
1. [ ] Debug panel showing node I/O
2. [ ] Click node to see input/output values
3. [ ] Lineage visualization (data flow paths)

---

## Migration Plan: Cloud Executor Slim-Down

### Current State (Problem)
```
flyto-cloud/
├── services/workflow_executor.py    # Duplicates core logic
├── services/execution_context.py    # Duplicates core logic
├── services/event_router.py         # Duplicates core logic
├── services/context/                 # Duplicates core logic
```

### Target State (Solution)
```
flyto-cloud/
├── services/engine_adapter.py       # Thin adapter only
├── services/stream_handler.py       # WebSocket streaming
├── services/auth_context.py         # User/tenant context
```

### Migration Steps

1. **Create core SDK interface** (`core/engine/sdk.py`)
2. **Create cloud adapter** (`cloud/services/engine_adapter.py`)
3. **Migrate one endpoint at a time**:
   - Start with `/api/workflows/validate` → uses `engine.validate()`
   - Then `/api/workflows/execute` → uses `engine.execute()`
   - Then `/api/variables/{node_id}` → uses `engine.introspect()`
4. **Shadow run before cutover** (for /execute):
   - Run both old cloud executor AND new core engine
   - Compare outputs (diff trace, diff result)
   - Log discrepancies without affecting user
   - Only cutover when diff rate < 1%
5. **Delete old cloud executor code** once all endpoints migrated and stable

### Shadow Run Implementation

```python
# cloud/services/engine_adapter.py

async def execute_with_shadow(self, request: ExecuteRequest):
    """Run both engines, compare, return old result"""

    # Run new core engine (shadow)
    try:
        new_result = await self.engine.execute(request.workflow, request.inputs)
    except Exception as e:
        logger.warning(f"Shadow run failed: {e}")
        new_result = {"error": str(e)}

    # Run old cloud executor (primary)
    old_result = await self.old_executor.execute(request.workflow, request.inputs)

    # Compare and log differences
    diff = self._compare_results(old_result, new_result)
    if diff:
        logger.info(f"Shadow diff: {diff}")
        metrics.increment("shadow_run.diff_count")
    else:
        metrics.increment("shadow_run.match_count")

    # Return old result (safe)
    return old_result
```

---

## Context Layers (Security)

Context is separated into layers to prevent accidental exposure of sensitive data.

```python
@dataclass
class ExecutionContext:
    """Layered context for security isolation"""

    # PUBLIC: Exposed to VariableResolver, included in VarCatalog
    # User can reference these in {{}} expressions
    public: Dict[str, Any]

    # PRIVATE: Only accessible by specific modules (explicit allowlist)
    # NOT included in VarCatalog, NOT resolvable via {{}}
    # Examples: __user_id, __tenant_id, internal flags
    private: Dict[str, Any]

    # SECRETS: Never returned to cloud/UI, never logged
    # Only passed to modules that declare `requires_credentials=True`
    # Examples: API keys, tokens, passwords
    secrets: Dict[str, Any]
```

### Rules

| Layer | VarCatalog | VariableResolver | Module Access | Logging |
|-------|------------|------------------|---------------|---------|
| public | Yes | Yes | All | Yes |
| private | No | No | Allowlist only | Masked |
| secrets | No | No | requires_credentials only | Never |

### Cloud Adapter Responsibility

```python
# Cloud injects user context into PRIVATE layer
context.private["__user_id"] = request.user_id
context.private["__tenant_id"] = request.tenant_id

# Cloud injects credentials into SECRETS layer
context.secrets["OPENAI_API_KEY"] = get_user_api_key(request.user_id)

# PUBLIC layer comes from workflow inputs
context.public.update(request.inputs)
```

---

## Variable Syntax Specification

**Version**: 1.0

### Grammar

```
expression     := "{{" path "}}"
path           := segment ("." segment)*
segment        := identifier | array_access
identifier     := [a-zA-Z_][a-zA-Z0-9_]*
array_access   := identifier "[" index "]"
index          := integer | quoted_string
integer        := [0-9]+
quoted_string  := '"' [^"]* '"' | "'" [^']* "'"
```

### Supported Patterns

| Pattern | Description | Example |
|---------|-------------|---------|
| `{{input}}` | Main input port (alias for `{{inputs.main}}`) | `{{input}}` |
| `{{input.field}}` | Field from main input | `{{input.data.title}}` |
| `{{inputs.<port>}}` | Specific input port | `{{inputs.resource}}` |
| `{{<node_id>}}` | Full output of a node | `{{http_request_1}}` |
| `{{<node_id>.<port>}}` | Specific port of a node | `{{http_request_1.output}}` |
| `{{<node_id>.<port>.field}}` | Nested field | `{{http_request_1.output.body.items}}` |
| `{{<node_id>.<port>.arr[0]}}` | Array index | `{{parser.output.items[0]}}` |
| `{{<node_id>.<port>.obj["key"]}}` | Quoted key (for special chars) | `{{api.output.data["my-key"]}}` |
| `{{params.<name>}}` | Workflow parameter | `{{params.api_key}}` |
| `{{global.<var>}}` | Global workflow variable | `{{global.counter}}` |
| `{{env.<VAR>}}` | Environment variable (allowlist only) | `{{env.NODE_ENV}}` |

### Resolution Modes

```python
class VariableResolver:
    def resolve(
        self,
        value: Any,
        context: ExecutionContext,
        mode: Literal["string", "raw"] = "raw"
    ) -> Any:
        """
        mode="raw": Return original type (object, array, etc.)
        mode="string": Stringify for template insertion
                       - object/array → JSON string
                       - None → empty string
                       - other → str()
        """
```

### Missing Field Behavior

```python
# Default: Return None for missing fields
resolver.resolve("{{node1.missing}}", ctx)  # → None

# Strict mode: Raise error
resolver.resolve("{{node1.missing}}", ctx, strict=True)  # → VariableNotFoundError

# With default
resolver.resolve("{{node1.missing | default('fallback')}}", ctx)  # → "fallback"
```

### NOT Supported (By Design)

- Function calls: `{{upper(input.name)}}` ❌
- Filters/pipes: `{{input.name | upper}}` ❌ (except `default`)
- Arithmetic: `{{input.count + 1}}` ❌
- Conditionals: `{{input.x if input.y else input.z}}` ❌

> Reason: Keep the resolver simple and predictable. Complex transformations should be done in modules.

---

## Variable Syntax Reference (Quick Reference)

| Pattern | Description | Example |
|---------|-------------|---------|
| `{{input}}` | Output from immediate upstream node | `{{input}}` |
| `{{input.field}}` | Specific field from upstream | `{{input.data.title}}` |
| `{{node_id}}` | Full output of a node | `{{http_request_1}}` |
| `{{node_id.field}}` | Specific field from a node | `{{http_request_1.body.items}}` |
| `{{params.name}}` | Workflow parameter | `{{params.api_key}}` |
| `{{env.VAR}}` | Environment variable | `{{env.OPENAI_API_KEY}}` |
| `{{global.var}}` | Global workflow variable | `{{global.counter}}` |

### Auto-bind Input (llm.agent)

Enhanced configuration for flexible input handling:

```python
# llm.agent params_schema additions
field('prompt_source', type='select', options=[
    {'label': 'From previous node', 'value': 'auto'},
    {'label': 'Define below', 'value': 'manual'}
], default='manual'),

field('prompt_path', type='string',
    description='Path to extract prompt from input (when auto)',
    default='{{input}}',  # Uses VariableResolver
    ui={'visibility': 'advanced'}
),

field('join_strategy', type='select', options=[
    {'label': 'First item only', 'value': 'first'},
    {'label': 'Join with newlines', 'value': 'newline'},
    {'label': 'Join with separator', 'value': 'separator'},
    {'label': 'As JSON array', 'value': 'json'}
], default='first',
    description='How to handle array inputs',
    ui={'visibility': 'advanced'}
),

field('join_separator', type='string',
    default='\n\n---\n\n',
    ui={'visibility': 'advanced', 'depends_on': {'join_strategy': 'separator'}}
),
```

**Example: Auto mode**

```yaml
- id: agent_1
  module: llm.agent
  params:
    prompt_source: auto
    prompt_path: "{{input.message}}"  # Extract specific field
    join_strategy: newline            # If input is array, join with \n
```

**Example: Manual mode (default)**

```yaml
- id: agent_1
  module: llm.agent
  params:
    prompt_source: manual
    task: "Analyze this data: {{input.data}}"
```

**Runtime behavior**:

```python
if prompt_source == "auto":
    # Resolve prompt_path using VariableResolver
    raw_input = resolver.resolve(prompt_path, context, mode="raw")

    # Handle array inputs
    if isinstance(raw_input, list):
        if join_strategy == "first":
            task = str(raw_input[0]) if raw_input else ""
        elif join_strategy == "newline":
            task = "\n".join(str(item) for item in raw_input)
        elif join_strategy == "separator":
            task = join_separator.join(str(item) for item in raw_input)
        elif join_strategy == "json":
            task = json.dumps(raw_input, ensure_ascii=False)
    else:
        task = str(raw_input) if raw_input else ""

    if not task.strip():
        raise NoPromptSpecifiedError(
            "prompt_source=auto but input is empty. "
            f"prompt_path={prompt_path}, resolved={raw_input}"
        )
else:
    task = params.get("task", "")
    if not task.strip():
        raise NoPromptSpecifiedError("prompt_source=manual but task is empty")
```

---

## Success Criteria

### Phase 1 Complete When:
- [ ] User can see available variables in UI sidebar
- [ ] User can click to insert `{{variable}}`
- [ ] llm.agent supports `prompt_source: auto`
- [ ] Cloud has no validation/execution logic (uses core API)

### Phase 2 Complete When:
- [ ] Expression editor with autocomplete works
- [ ] Drag-drop variables works
- [ ] Type checking shows warnings

### Phase 3 Complete When:
- [ ] Debug panel shows per-node I/O
- [ ] Lineage graph visualizes data flow
- [ ] Execution trace is fully captured
