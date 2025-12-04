# Hello World Example

A minimal example to get started with Flyto Core.

## Prerequisites

```bash
cd flyto-core
pip install -r requirements.txt
```

## Run

### Option 1: YAML Workflow

```bash
python run.py examples/hello_world/workflow.yaml
```

**workflow.yaml:**
```yaml
name: Hello World
steps:
  - id: reverse
    module: string.reverse
    params:
      text: "Hello Flyto"

  - id: shout
    module: string.uppercase
    params:
      text: "${reverse.result}"
```

**Output:** `OTYFL OLLEH`

### Option 2: Python Script

```bash
python examples/hello_world/run_python.py
```

## What This Shows

1. **YAML Workflow**: Define workflows declaratively
2. **Variable Reference**: Use `${step_id.field}` to chain outputs
3. **Python API**: Use `ModuleRegistry.execute()` directly
4. **Module Discovery**: List available modules programmatically

## Next Steps

- Browse available modules: `python -m src.core.modules.registry stats`
- Try browser automation: `workflows/templates/webpage_screenshot.yaml`
- Create your own module: [docs/REGISTER_MODULE_GUIDE.md](../../docs/REGISTER_MODULE_GUIDE.md)
