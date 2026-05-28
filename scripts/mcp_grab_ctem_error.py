"""Grab the actual error text shown on the CTEM Actions page."""

import json, os, sys, subprocess, time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def send(proc, req):
    proc.stdin.write(json.dumps(req) + "\n"); proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError(proc.stderr.read() if proc.stderr else "EOF")
        if line.strip():
            return json.loads(line)


_id = [10]


def call(proc, name, **args):
    _id[0] += 1
    resp = send(proc, {
        "jsonrpc": "2.0", "id": _id[0], "method": "tools/call",
        "params": {"name": name, "arguments": args},
    })
    content = resp.get("result", {}).get("content", [])
    if not content: return {}
    text = content[0].get("text", "{}")
    try: return json.loads(text)
    except json.JSONDecodeError: return {"raw": text}


def exec_mod(proc, session, m, **p):
    return call(proc, "execute_module", module_id=m, params=p,
                context={"browser_session": session} if session else {})


def main(base, org):
    email = os.environ["FLYTO_TEST_EMAIL"]
    password = os.environ["FLYTO_TEST_PASSWORD"]

    env = os.environ.copy()
    env.update({
        "FLYTO_MCP_ALLOW_LOCALHOST": "1",
        "FLYTO_ALLOWED_HOSTS": "localhost,127.0.0.1",
        "FLYTO_ALLOW_PRIVATE_NETWORK": "true",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "core.mcp_server"], cwd=str(SRC),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, env=env)
    try:
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18",
                               "clientInfo": {"name": "x", "version": "0.1"}, "capabilities": {}}})
        launch = call(proc, "execute_module", module_id="browser.launch",
                      params={"headless": True, "viewport": {"width": 1440, "height": 900}})
        session = launch["browser_session"]
        exec_mod(proc, session, "browser.goto", url=f"{base}/sign-in")
        time.sleep(2)
        exec_mod(proc, session, "browser.type", selector="input[name='email']", text=email)
        exec_mod(proc, session, "browser.type", selector="input[name='password']", text=password)
        exec_mod(proc, session, "browser.click", selector="button[type='submit']")
        time.sleep(3.5)

        exec_mod(proc, session, "browser.goto",
                 url=f"{base}/projects/{org}/warroom/exp-ctem")
        time.sleep(4)

        # Grab the page body text in full
        r = exec_mod(proc, session, "browser.evaluate", script="document.body.innerText")
        text = r.get("result") if isinstance(r, dict) else r
        print("=== PAGE TEXT ===")
        print(text)

        # Also grab console errors
        r = exec_mod(proc, session, "browser.evaluate", script="""
            (() => {
                const errors = window.__capturedErrors || [];
                return errors.map(e => String(e)).join('\\n---\\n');
            })()
        """)
        ce = r.get("result") if isinstance(r, dict) else r
        if ce:
            print("\n=== CAPTURED ERRORS ===")
            print(ce)

        exec_mod(proc, session, "browser.close")
    finally:
        try: proc.stdin.close(); proc.wait(timeout=5)
        except Exception: proc.kill()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5181",
         sys.argv[2] if len(sys.argv) > 2 else "f3ecb96f19c3a9bcce5a32cbc9863d27")
