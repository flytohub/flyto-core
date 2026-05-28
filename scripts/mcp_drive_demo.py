"""Drive flyto-core's MCP server over stdio to capture a screenshot.

Demonstrates the actual MCP path an LLM client (Claude Code, Claude
Desktop, etc.) would take. Spawns `python -m core.mcp_server`, sends
JSON-RPC initialize + a browser sequence, prints the screenshot path.

Run from the repo root::

    python scripts/mcp_drive_demo.py http://localhost:5181/ out/site-shot.png

Argv 1 is the URL to load, argv 2 is where to write the PNG. The
screenshot path is also printed on stdout so calling shells can pick
it up.
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"


def send(proc: subprocess.Popen, req: dict) -> dict:
    """Send one JSON-RPC request and read the matching response."""
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    # The server replies with exactly one line per request (notifications
    # excluded). Read until we get a non-empty line.
    while True:
        line = proc.stdout.readline()
        if not line:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"server closed stdout. stderr=\n{stderr}")
        line = line.strip()
        if not line:
            continue
        return json.loads(line)


def call_tool(proc, request_id: int, name: str, arguments: dict) -> dict:
    """Call a tool via tools/call and unwrap the structured content."""
    resp = send(proc, {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    if "error" in resp:
        raise RuntimeError(f"{name} failed: {resp['error']}")
    # MCP tools/call result.content is a list of TextContent blocks;
    # we expect a single JSON-encoded one.
    content = resp.get("result", {}).get("content", [])
    if not content:
        return {}
    text = content[0].get("text", "{}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def main(url: str, out_png: Path) -> int:
    out_png.parent.mkdir(parents=True, exist_ok=True)

    # Whitelist localhost for this run — flyto-core's MCP server refuses
    # private addresses unless the operator opts in. This is exactly the
    # "verify my own dev site" path we hardened FC3 for.
    env = os.environ.copy()
    env["FLYTO_MCP_ALLOW_LOCALHOST"] = "1"
    env["FLYTO_ALLOWED_HOSTS"] = "localhost,127.0.0.1"
    # SSRF guard's hardcoded port allowlist is {80, 443, 8080, 8443}.
    # Vite dev runs on :5181, which is otherwise refused. The intended
    # escape hatch for self-testing is FLYTO_ALLOW_PRIVATE_NETWORK=true,
    # which short-circuits the whole validator (incl. port check) once
    # the caller has accepted responsibility for what gets dialled. We
    # do that here, scoped to this child process only.
    env["FLYTO_ALLOW_PRIVATE_NETWORK"] = "true"

    proc = subprocess.Popen(
        [sys.executable, "-m", "core.mcp_server"],
        cwd=str(SRC),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    try:
        # 1. MCP handshake
        init = send(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "mcp_drive_demo", "version": "0.1"},
                "capabilities": {},
            },
        })
        print(f"[init] protocolVersion={init.get('result', {}).get('protocolVersion')}", file=sys.stderr)

        def assert_ok(label: str, resp: dict, code: int) -> None:
            # flyto-core modules return either {"status": "success", ...}
            # or {"status": "error", "error": "..."}; older paths use
            # {"ok": true/false}. Accept either shape.
            ok = resp.get("status") == "success" or resp.get("ok") is True
            if not ok:
                print(f"[{label}] error: {resp}", file=sys.stderr)
                raise SystemExit(code)

        # 2. Launch browser (force headless — we're driving from a
        # script, no human needs to see a window pop up).
        launch = call_tool(proc, 2, "execute_module", {
            "module_id": "browser.launch",
            "params": {"headless": True},
        })
        assert_ok("browser.launch", launch, 2)
        session = launch.get("browser_session") or launch.get("session_id")
        print(f"[browser.launch] session={session}", file=sys.stderr)

        # 3. Goto the dev site
        goto = call_tool(proc, 3, "execute_module", {
            "module_id": "browser.goto",
            "params": {"url": url},
            "context": {"browser_session": session} if session else {},
        })
        assert_ok("browser.goto", goto, 3)
        print(f"[browser.goto {url}] http_status={goto.get('status_code') or goto.get('http_status')}", file=sys.stderr)

        # Give the SPA a moment to hydrate before we grab pixels.
        time.sleep(2.0)

        # 4. Screenshot
        shot = call_tool(proc, 4, "execute_module", {
            "module_id": "browser.screenshot",
            "params": {"path": str(out_png), "full_page": True},
            "context": {"browser_session": session} if session else {},
        })
        assert_ok("browser.screenshot", shot, 4)
        print(f"[browser.screenshot] saved -> {out_png}", file=sys.stderr)

        # 5. Snapshot DOM so we can also reason about structure
        snap = call_tool(proc, 5, "execute_module", {
            "module_id": "browser.snapshot",
            "params": {"format": "text"},
            "context": {"browser_session": session} if session else {},
        })
        snap_path = out_png.with_suffix(".snapshot.txt")
        with open(snap_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(snap, ensure_ascii=False, indent=2))
        print(f"[browser.snapshot] saved -> {snap_path}", file=sys.stderr)

        # 6. Clean up — never leave a Chromium zombie running
        call_tool(proc, 6, "execute_module", {
            "module_id": "browser.close",
            "params": {},
            "context": {"browser_session": session} if session else {},
        })

        # The driver's only required stdout line so a calling shell can
        # grep just the artefact path.
        print(str(out_png))
        return 0
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    url_arg = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5181/"
    out_arg = Path(sys.argv[2] if len(sys.argv) > 2 else "out/site-shot.png")
    sys.exit(main(url_arg, out_arg))
