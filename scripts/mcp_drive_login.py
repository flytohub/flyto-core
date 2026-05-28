"""Drive flyto-core MCP to log in and screenshot key pages.

Reads credentials from env vars (FLYTO_TEST_EMAIL, FLYTO_TEST_PASSWORD)
so they never land in argv listings or files. Drops a screenshot per
URL in out/shots/ plus a JSON snapshot of the post-login DOM for each.

Pages to capture default to the war-room canonical surfaces; extend the
PAGES list to add more.
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
OUT = REPO_ROOT / "out" / "shots"


PAGES = [
    # (slug, path-or-url)
    ("after-login",    "/"),                # whatever lands after sign-in
    ("workspace",      "/flyto/workspace"),
    ("settings",       "/flyto/workspace/settings"),
]


def send(proc: subprocess.Popen, req: dict) -> dict:
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"server closed stdout. stderr=\n{stderr}")
        line = line.strip()
        if line:
            return json.loads(line)


_request_id = [10]


def call_tool(proc, name: str, arguments: dict) -> dict:
    _request_id[0] += 1
    resp = send(proc, {
        "jsonrpc": "2.0",
        "id": _request_id[0],
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    if "error" in resp:
        raise RuntimeError(f"{name} failed: {resp['error']}")
    content = resp.get("result", {}).get("content", [])
    if not content:
        return {}
    text = content[0].get("text", "{}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def ok(resp: dict) -> bool:
    return resp.get("status") == "success" or resp.get("ok") is True


def must_ok(label: str, resp: dict):
    if not ok(resp):
        print(f"[{label}] FAILED: {resp}", file=sys.stderr)
        raise SystemExit(2)


def execute(proc, session, module_id, **params):
    return call_tool(proc, "execute_module", {
        "module_id": module_id,
        "params": params,
        "context": {"browser_session": session} if session else {},
    })


def main(base_url: str) -> int:
    email = os.environ.get("FLYTO_TEST_EMAIL")
    password = os.environ.get("FLYTO_TEST_PASSWORD")
    if not email or not password:
        print("set FLYTO_TEST_EMAIL and FLYTO_TEST_PASSWORD env vars", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["FLYTO_MCP_ALLOW_LOCALHOST"] = "1"
    env["FLYTO_ALLOWED_HOSTS"] = "localhost,127.0.0.1"
    env["FLYTO_ALLOW_PRIVATE_NETWORK"] = "true"

    proc = subprocess.Popen(
        [sys.executable, "-m", "core.mcp_server"],
        cwd=str(SRC),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, env=env,
    )

    try:
        send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18",
                       "clientInfo": {"name": "mcp_drive_login", "version": "0.1"},
                       "capabilities": {}},
        })

        launch = call_tool(proc, "execute_module",
                           {"module_id": "browser.launch",
                            "params": {"headless": True, "viewport": {"width": 1440, "height": 900}}})
        must_ok("browser.launch", launch)
        session = launch.get("browser_session")
        print(f"[launch] session={session}", file=sys.stderr)

        # Step 1: load sign-in
        r = execute(proc, session, "browser.goto", url=f"{base_url}/sign-in")
        must_ok("goto /sign-in", r)
        time.sleep(1.5)

        # Step 2: type credentials.
        # `browser.type` typically takes selector + text. The DOM
        # snapshot from earlier shows inputs name=email, name=password.
        r = execute(proc, session, "browser.type",
                    selector="input[name='email']", text=email)
        must_ok("type email", r)
        r = execute(proc, session, "browser.type",
                    selector="input[name='password']", text=password)
        must_ok("type password", r)

        # Capture pre-submit state so we can see the now-enabled button
        r = execute(proc, session, "browser.screenshot",
                    path=str(OUT / "00-login-filled.png"), full_page=False)
        must_ok("screenshot login-filled", r)

        # Step 3: click Sign in. Try several selectors — the form's
        # submit button may be `button[type=submit]` or a Mantine button
        # with a specific data attribute. Be tolerant.
        clicked = False
        for sel in [
            "button[type='submit']",
            "button:has-text('Sign in')",
            "[data-flyto-hint='3']",  # from earlier DOM snapshot
        ]:
            r = execute(proc, session, "browser.click", selector=sel)
            if ok(r):
                clicked = True
                print(f"[click] matched selector {sel!r}", file=sys.stderr)
                break
        if not clicked:
            print("[click sign-in] all selectors failed; last response:", r, file=sys.stderr)
            return 3

        # Give the SPA time to navigate + render the post-login surface
        time.sleep(3.0)

        # Step 4: confirm we're past /sign-in
        r = execute(proc, session, "browser.evaluate",
                    script="JSON.stringify({url: location.href, title: document.title})")
        print(f"[post-login] {r.get('result') or r.get('data') or r}", file=sys.stderr)

        # Step 5: walk the key pages, screenshot each.
        for slug, path in PAGES:
            full = base_url.rstrip("/") + path if path.startswith("/") else path
            r = execute(proc, session, "browser.goto", url=full)
            if not ok(r):
                print(f"[goto {slug}] failed: {r}", file=sys.stderr)
                continue
            time.sleep(2.5)  # let dashboards/charts render
            png = OUT / f"{slug}.png"
            r = execute(proc, session, "browser.screenshot",
                        path=str(png), full_page=True)
            if ok(r):
                print(f"[shot] {slug} -> {png}", file=sys.stderr)
            else:
                print(f"[shot {slug}] error: {r}", file=sys.stderr)

            # Also dump DOM text so we can reason about structure
            r = execute(proc, session, "browser.snapshot", format="text")
            if ok(r):
                (OUT / f"{slug}.snapshot.txt").write_text(
                    json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

        execute(proc, session, "browser.close")
        return 0
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5181"
    sys.exit(main(base))
