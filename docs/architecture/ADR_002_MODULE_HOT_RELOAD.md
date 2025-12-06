# ADR-002: Module Hot Reload

**Status:** Accepted
**Date:** 2025-12-06
**Author:** Flyto Core Team

## Context

When flyto-core is updated on GitHub, the changes should propagate to flyto-cloud backend and frontend without requiring a full restart. This enables:

1. Zero-downtime module updates
2. Faster development iteration
3. Automatic sync between core and cloud

## Decision

Implement a hot reload system with three components:

1. **GitHub Webhook**: Triggers reload on push to flyto-core
2. **Backend Hot Reload**: Reloads module registries without restart
3. **Frontend Cache Invalidation**: Clears cache and fetches new modules

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub (flyto-core)                                            │
│  └── Push to main branch                                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ Webhook POST /api/v2/modules/reload
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  flyto-cloud Backend                                            │
│  ├── 1. Verify webhook signature                                │
│  ├── 2. Git pull flyto-core                                     │
│  ├── 3. Clear Python module cache                               │
│  ├── 4. Re-import module registries                             │
│  ├── 5. Increment version counter                               │
│  └── 6. Broadcast via WebSocket                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ WebSocket: { type: "modules_updated", version: "1.2.3" }
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│  flyto-cloud Frontend                                           │
│  ├── 1. Receive WebSocket message                               │
│  ├── 2. Clear localStorage cache                                │
│  ├── 3. Fetch new module catalog                                │
│  └── 4. Update UI reactively                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation

### 1. Backend: Reload Endpoint

```python
# flyto-cloud/src/ui/web/backend/api/v2/modules/routes.py

import hashlib
import hmac
import subprocess
from fastapi import Header, BackgroundTasks

# Module version tracking
_module_version = {"version": "1.0.0", "updated_at": None}

@router.post("/reload")
async def reload_modules(
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    """
    Hot reload modules from flyto-core.
    Called by GitHub webhook on push.
    """
    # Verify webhook signature (production)
    if not _verify_webhook_signature(x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Only handle push events
    if x_github_event != "push":
        return {"status": "ignored", "reason": f"Event type: {x_github_event}"}

    # Perform reload in background
    background_tasks.add_task(_perform_hot_reload)

    return {"status": "reload_initiated"}


async def _perform_hot_reload():
    """Background task to reload modules."""
    import sys
    import importlib

    core_path = _get_flyto_core_path()

    # 1. Git pull
    result = subprocess.run(
        ["git", "pull", "origin", "main"],
        cwd=core_path,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logger.error(f"Git pull failed: {result.stderr}")
        return

    # 2. Clear cached modules
    modules_to_reload = [
        key for key in sys.modules.keys()
        if key.startswith("src.core.modules")
    ]

    for module_name in modules_to_reload:
        del sys.modules[module_name]

    # 3. Clear registries
    from src.core.modules.registry import ModuleRegistry
    ModuleRegistry._modules.clear()
    ModuleRegistry._metadata.clear()

    # 4. Re-import
    from src.core.modules import atomic
    importlib.reload(atomic)

    try:
        from src.core.modules import composite
        importlib.reload(composite)
    except ImportError:
        pass

    # 5. Update version
    import datetime
    _module_version["version"] = f"1.0.{len(ModuleRegistry._modules)}"
    _module_version["updated_at"] = datetime.datetime.utcnow().isoformat()

    # 6. Broadcast to connected clients
    await _broadcast_module_update()

    logger.info(f"Hot reload complete. {len(ModuleRegistry._modules)} modules loaded.")


@router.get("/version")
async def get_module_version():
    """Get current module version for cache validation."""
    return _module_version
```

### 2. Backend: WebSocket Broadcast

```python
# flyto-cloud/src/ui/web/backend/websocket/manager.py

from typing import Set
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

async def _broadcast_module_update():
    await manager.broadcast({
        "type": "modules_updated",
        "version": _module_version["version"],
        "updated_at": _module_version["updated_at"]
    })
```

### 3. Frontend: WebSocket Listener

```javascript
// flyto-cloud/src/ui/web/frontend/src/composables/useModuleSync.js

import { ref, onMounted, onUnmounted } from 'vue'
import { useModuleCatalog } from './useModuleCatalog'

export function useModuleSync() {
  const { refreshCatalog, clearCache } = useModuleCatalog()
  const isConnected = ref(false)
  const lastUpdate = ref(null)
  let ws = null

  const connect = () => {
    const wsUrl = `ws://${window.location.host}/ws/modules`
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      isConnected.value = true
      console.log('Module sync connected')
    }

    ws.onmessage = async (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'modules_updated') {
        console.log('Modules updated, refreshing...')
        lastUpdate.value = data.updated_at

        // Clear cache and refresh
        clearCache()
        await refreshCatalog()

        // Notify user (optional)
        // toast.info('Modules updated')
      }
    }

    ws.onclose = () => {
      isConnected.value = false
      // Reconnect after 5 seconds
      setTimeout(connect, 5000)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }

  onMounted(() => {
    connect()
  })

  onUnmounted(() => {
    if (ws) {
      ws.close()
    }
  })

  return {
    isConnected,
    lastUpdate
  }
}
```

### 4. Frontend: Version Polling (Fallback)

For environments where WebSocket is not available:

```javascript
// flyto-cloud/src/ui/web/frontend/src/composables/useModuleCatalog.js

const MODULE_VERSION_KEY = 'flyto_module_version'

async function checkForUpdates() {
  try {
    const response = await fetch('/api/v2/modules/version')
    const { version } = await response.json()

    const cachedVersion = localStorage.getItem(MODULE_VERSION_KEY)

    if (cachedVersion !== version) {
      console.log(`Module update detected: ${cachedVersion} -> ${version}`)
      clearCache()
      await refreshCatalog()
      localStorage.setItem(MODULE_VERSION_KEY, version)
    }
  } catch (error) {
    console.error('Version check failed:', error)
  }
}

// Poll every 30 seconds
setInterval(checkForUpdates, 30000)
```

### 5. GitHub Webhook Setup

Configure in GitHub repository settings:

1. Go to flyto-core > Settings > Webhooks > Add webhook
2. Payload URL: `https://your-domain.com/api/v2/modules/reload`
3. Content type: `application/json`
4. Secret: Generate a secure secret
5. Events: Just the push event

### 6. Environment Variables

```bash
# .env
GITHUB_WEBHOOK_SECRET=your-secure-secret-here
FLYTO_CORE_PATH=/path/to/flyto-core  # Optional override
```

## Security Considerations

1. **Webhook Signature**: Always verify GitHub signature in production
2. **Rate Limiting**: Limit reload frequency (max once per minute)
3. **Rollback**: Keep previous module versions for quick rollback
4. **Validation**: Validate new modules before activating

## Development Mode

For local development, use file watcher instead of webhook:

```python
# development only
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ModuleChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            asyncio.create_task(_perform_hot_reload())

observer = Observer()
observer.schedule(ModuleChangeHandler(), core_path, recursive=True)
observer.start()
```

## Consequences

### Benefits

1. **Zero Downtime**: Users never experience interruption
2. **Instant Updates**: Changes propagate within seconds
3. **Simplified Deployment**: No manual restart needed
4. **Better DX**: Developers see changes immediately

### Trade-offs

1. **Complexity**: More moving parts to maintain
2. **Memory**: Brief spike during reload
3. **Edge Cases**: Some state may need manual handling

## Related Documents

- [ADR-001: Module Tiered Architecture](./ADR_001_MODULE_TIERED_ARCHITECTURE.md)
- [flyto-core CHANGELOG](../../CHANGELOG.md)
