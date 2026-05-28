"""Probe: log in, click first project card, print resulting orgId.

Used as a one-shot helper so mcp_tour.py can take orgId as argv
instead of discovering it inside its own subprocess (which kept
hanging on the embedded eval).
"""
import json, os, sys, subprocess, time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def main():
    env = os.environ.copy()
    env.update({"FLYTO_MCP_ALLOW_LOCALHOST": "1", "FLYTO_ALLOWED_HOSTS": "localhost,127.0.0.1", "FLYTO_ALLOW_PRIVATE_NETWORK": "true"})
    p = subprocess.Popen([sys.executable, "-m", "core.mcp_server"], cwd=str(SRC),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1, env=env)

    def send(req):
        p.stdin.write(json.dumps(req) + "\n"); p.stdin.flush()
        while True:
            line = p.stdout.readline()
            if not line: raise RuntimeError("EOF: " + (p.stderr.read() or ""))
            if line.strip(): return json.loads(line)

    counter = [10]
    def call(name, **a):
        counter[0] += 1
        r = send({"jsonrpc": "2.0", "id": counter[0], "method": "tools/call",
                  "params": {"name": name, "arguments": a}})
        c = r.get("result", {}).get("content", [])
        return json.loads(c[0]["text"]) if c else {}

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18",
                         "clientInfo": {"name": "find-orgid", "version": "0.1"},
                         "capabilities": {}}})
        L = call("execute_module", module_id="browser.launch",
                 params={"headless": True, "viewport": {"width": 1440, "height": 900}})
        s = L.get("browser_session")

        # Log in
        call("execute_module", module_id="browser.goto",
             params={"url": "http://localhost:5181/sign-in"},
             context={"browser_session": s})
        time.sleep(1.5)
        call("execute_module", module_id="browser.type",
             params={"selector": "input[name='email']", "text": os.environ["FLYTO_TEST_EMAIL"]},
             context={"browser_session": s})
        call("execute_module", module_id="browser.type",
             params={"selector": "input[name='password']", "text": os.environ["FLYTO_TEST_PASSWORD"]},
             context={"browser_session": s})
        call("execute_module", module_id="browser.click",
             params={"selector": "button[type='submit']"},
             context={"browser_session": s})
        time.sleep(3.5)

        # Navigate to /projects to ensure the card is on screen, then click it
        call("execute_module", module_id="browser.goto",
             params={"url": "http://localhost:5181/projects"},
             context={"browser_session": s})
        time.sleep(2.5)

        # Click the project card via its visible content
        r = call("execute_module", module_id="browser.evaluate",
                 params={"script": "const el = [...document.querySelectorAll('*')].find(n => n.textContent && n.textContent.trim().startsWith('Flyto2') && n.offsetWidth > 200 && getComputedStyle(n).cursor === 'pointer'); if (el) el.click(); 'clicked'"},
                 context={"browser_session": s})
        time.sleep(2.0)

        # Read resulting path. Some browser.evaluate transports drop
        # bare-string returns — wrap so we always come back with an
        # object that survives serialisation.
        r = call("execute_module", module_id="browser.evaluate",
                 params={"script": "JSON.stringify({path: location.pathname, href: location.href})"},
                 context={"browser_session": s})
        print(json.dumps({"raw": r}))

        call("execute_module", module_id="browser.close",
             params={}, context={"browser_session": s})
    finally:
        try: p.stdin.close(); p.wait(timeout=5)
        except Exception: p.kill()


if __name__ == "__main__":
    main()
