# Plugin SDK Development Guide

This guide explains how to create flyto plugins in any programming language.

## Supported Languages

| Language | Status | Entry Point | Package Manager |
|----------|--------|-------------|-----------------|
| Python | ✅ Full Support | `main.py` | pip |
| Node.js | ✅ Full Support | `index.js` | npm |
| TypeScript | ✅ Full Support | `index.ts` | npm |
| Go | ✅ Full Support | `plugin` (binary) | go |
| Rust | ✅ Full Support | `plugin` (binary) | cargo |
| Java | ✅ Full Support | `plugin.jar` | maven |
| Kotlin | ✅ Full Support | `plugin.jar` | gradle |
| C# | ✅ Full Support | `Plugin.dll` | nuget |
| Ruby | ✅ Full Support | `main.rb` | gem |
| PHP | ✅ Full Support | `main.php` | composer |
| Deno | ✅ Full Support | `main.ts` | deno |
| Bun | ✅ Full Support | `index.ts` | bun |
| Binary | ✅ Full Support | `plugin` | N/A |

## Plugin Structure

```
my-plugin/
├── plugin.yaml          # Manifest (required)
├── main.py / index.js / plugin  # Entry point
├── README.md            # Documentation
├── icon.png             # 256x256 icon
└── examples/            # Usage examples
```

## Manifest Format (plugin.yaml)

```yaml
name: my-awesome-scraper
version: 1.0.0
author: developer@example.com
license: MIT

runtime:
  language: go           # python | node | typescript | go | rust | java | csharp | binary
  entry: scraper         # entry point (relative to plugin dir)
  min_flyto_version: 2.0.0

modules:
  - id: mycompany.scraper
    label: Web Scraper
    description: Scrape any website
    category: browser
    icon: Globe
    color: "#6366F1"
    params_schema:
      url:
        type: string
        required: true
        description: URL to scrape
    output_schema:
      title:
        type: string
      content:
        type: string

permissions:
  - browser.read
  - browser.write
  - network.outbound
```

## JSON-RPC Protocol

Plugins communicate with Core via JSON-RPC 2.0 over stdio.

### Handshake (Core → Plugin)

```json
{
  "jsonrpc": "2.0",
  "method": "handshake",
  "params": {
    "protocolVersion": "0.1.0",
    "pluginId": "my-plugin",
    "executionId": "exec-123"
  },
  "id": 1
}
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "pluginVersion": "1.0.0",
    "supportedMethods": ["invoke", "ping", "shutdown"]
  },
  "id": 1
}
```

### Invoke (Core → Plugin)

```json
{
  "jsonrpc": "2.0",
  "method": "invoke",
  "params": {
    "step": "scrape",
    "input": {"url": "https://example.com"},
    "config": {},
    "context": {
      "browser_ws_endpoint": "ws://127.0.0.1:9222/devtools/browser/xxx"
    },
    "timeoutMs": 30000
  },
  "id": 2
}
```

**Success Response:**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "ok": true,
    "data": {
      "title": "Example Domain",
      "content": "..."
    }
  },
  "id": 2
}
```

**Error Response:**

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32001,
    "message": "Page not found",
    "data": {"url": "https://example.com/404"}
  },
  "id": 2
}
```

### Ping (Core → Plugin)

```json
{"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 3}
```

**Response:**

```json
{"jsonrpc": "2.0", "result": {"pong": true}, "id": 3}
```

### Shutdown (Core → Plugin)

```json
{
  "jsonrpc": "2.0",
  "method": "shutdown",
  "params": {"reason": "idle", "gracePeriodMs": 5000},
  "id": 4
}
```

## Browser Session Sharing

Plugins can connect to a shared browser instance using the CDP WebSocket endpoint.

The `context.browser_ws_endpoint` contains a WebSocket URL like:
```
ws://127.0.0.1:9222/devtools/browser/abc123
```

### Python (Playwright)

```python
from playwright.sync_api import sync_playwright

def execute(params, context):
    ws_endpoint = context.get("browser_ws_endpoint")

    with sync_playwright() as p:
        browser = p.chromium.connect(ws_endpoint)
        page = browser.new_page()
        page.goto(params["url"])
        title = page.title()
        browser.close()

    return {"ok": True, "data": {"title": title}}
```

### Node.js (Playwright)

```javascript
const { chromium } = require('playwright');

async function execute(params, context) {
    const browser = await chromium.connect(context.browser_ws_endpoint);
    const page = await browser.newPage();
    await page.goto(params.url);
    const title = await page.title();
    await browser.close();

    return { ok: true, data: { title } };
}
```

### Go (chromedp)

```go
package main

import (
    "context"
    "github.com/chromedp/chromedp"
)

func execute(params, ctx map[string]interface{}) map[string]interface{} {
    wsEndpoint := ctx["browser_ws_endpoint"].(string)

    allocCtx, cancel := chromedp.NewRemoteAllocator(context.Background(), wsEndpoint)
    defer cancel()

    taskCtx, cancel := chromedp.NewContext(allocCtx)
    defer cancel()

    var title string
    chromedp.Run(taskCtx,
        chromedp.Navigate(params["url"].(string)),
        chromedp.Title(&title),
    )

    return map[string]interface{}{
        "ok": true,
        "data": map[string]interface{}{"title": title},
    }
}
```

## Example: Python Plugin

### Directory Structure

```
my-python-plugin/
├── plugin.yaml
├── main.py
└── requirements.txt
```

### plugin.yaml

```yaml
name: my-python-plugin
version: 1.0.0
runtime:
  language: python
  entry: main.py
modules:
  - id: myplugin.hello
    label: Hello World
    params_schema:
      name: {type: string, required: true}
    output_schema:
      message: {type: string}
```

### main.py

```python
#!/usr/bin/env python3
import json
import sys

def handle_request(request):
    method = request["method"]
    params = request.get("params", {})
    request_id = request["id"]

    if method == "handshake":
        return {"pluginVersion": "1.0.0"}

    elif method == "invoke":
        step = params["step"]
        input_data = params["input"]

        if step == "hello":
            name = input_data.get("name", "World")
            return {"ok": True, "data": {"message": f"Hello, {name}!"}}

        return {"ok": False, "error": f"Unknown step: {step}"}

    elif method == "ping":
        return {"pong": True}

    elif method == "shutdown":
        sys.exit(0)

def main():
    for line in sys.stdin:
        request = json.loads(line.strip())
        result = handle_request(request)
        response = {
            "jsonrpc": "2.0",
            "result": result,
            "id": request["id"]
        }
        print(json.dumps(response), flush=True)

if __name__ == "__main__":
    main()
```

## Example: Node.js Plugin

### Directory Structure

```
my-node-plugin/
├── plugin.yaml
├── index.js
└── package.json
```

### plugin.yaml

```yaml
name: my-node-plugin
version: 1.0.0
runtime:
  language: node
  entry: index.js
modules:
  - id: myplugin.greet
    label: Greeting
    params_schema:
      name: {type: string}
```

### index.js

```javascript
const readline = require('readline');

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

function handleRequest(request) {
    const { method, params, id } = request;

    switch (method) {
        case 'handshake':
            return { pluginVersion: '1.0.0' };

        case 'invoke':
            const { step, input } = params;
            if (step === 'greet') {
                return { ok: true, data: { message: `Hello, ${input.name || 'World'}!` } };
            }
            return { ok: false, error: `Unknown step: ${step}` };

        case 'ping':
            return { pong: true };

        case 'shutdown':
            process.exit(0);
    }
}

rl.on('line', (line) => {
    const request = JSON.parse(line);
    const result = handleRequest(request);
    const response = { jsonrpc: '2.0', result, id: request.id };
    console.log(JSON.stringify(response));
});
```

## Example: Go Plugin

### Directory Structure

```
my-go-plugin/
├── plugin.yaml
├── main.go
└── go.mod
```

### plugin.yaml

```yaml
name: my-go-plugin
version: 1.0.0
runtime:
  language: go
  entry: plugin  # compiled binary name
modules:
  - id: myplugin.process
    label: Data Processor
```

### main.go

```go
package main

import (
    "bufio"
    "encoding/json"
    "fmt"
    "os"
)

type Request struct {
    JSONRPC string                 `json:"jsonrpc"`
    Method  string                 `json:"method"`
    Params  map[string]interface{} `json:"params"`
    ID      int                    `json:"id"`
}

type Response struct {
    JSONRPC string      `json:"jsonrpc"`
    Result  interface{} `json:"result"`
    ID      int         `json:"id"`
}

func handleRequest(req Request) interface{} {
    switch req.Method {
    case "handshake":
        return map[string]string{"pluginVersion": "1.0.0"}

    case "invoke":
        params := req.Params
        step := params["step"].(string)
        input := params["input"].(map[string]interface{})

        if step == "process" {
            return map[string]interface{}{
                "ok":   true,
                "data": map[string]interface{}{"processed": true, "input": input},
            }
        }
        return map[string]interface{}{"ok": false, "error": "Unknown step"}

    case "ping":
        return map[string]bool{"pong": true}

    case "shutdown":
        os.Exit(0)
    }
    return nil
}

func main() {
    scanner := bufio.NewScanner(os.Stdin)
    for scanner.Scan() {
        var req Request
        json.Unmarshal(scanner.Bytes(), &req)

        result := handleRequest(req)
        resp := Response{JSONRPC: "2.0", Result: result, ID: req.ID}

        output, _ := json.Marshal(resp)
        fmt.Println(string(output))
    }
}
```

Build with: `go build -o plugin main.go`

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| -32700 | Parse Error | Invalid JSON |
| -32600 | Invalid Request | Invalid request object |
| -32601 | Method Not Found | Method doesn't exist |
| -32602 | Invalid Params | Invalid parameters |
| -32603 | Internal Error | Internal JSON-RPC error |
| -32001 | Step Not Found | Plugin step doesn't exist |
| -32002 | Validation Error | Input validation failed |
| -32003 | Permission Denied | Missing permission |
| -32004 | Secret Not Provided | Required secret missing |
| -32005 | Timeout | Operation timed out |
| -32006 | Resource Exhausted | Resource limit exceeded |
| -32007 | Browser Not Available | Browser session unavailable |
| -32008 | Browser Connection Failed | CDP connection failed |
| -32009 | Language Not Supported | Language runtime not available |

## Best Practices

1. **Always validate input** - Check required fields before processing
2. **Handle timeouts** - Respect `timeoutMs` in invoke requests
3. **Clean shutdown** - Release resources on shutdown signal
4. **Use structured logging** - Write logs to stderr, JSON-RPC to stdout
5. **Return proper errors** - Use error codes from the table above
6. **Test locally** - Use `flyto run` command to test plugins locally

## Publishing to Marketplace

1. Package your plugin as a directory or tarball
2. Ensure `plugin.yaml` is valid and complete
3. Include an icon (256x256 PNG)
4. Write clear documentation in README.md
5. Submit to the Flyto marketplace (coming soon)
