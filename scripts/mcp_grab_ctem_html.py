"""Save the CTEM Actions page HTML to a file for inspection."""
import json, os, sys, subprocess, time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
OUT = Path(__file__).resolve().parent.parent / "out" / "ctem-error"


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
    resp = send(proc, {"jsonrpc": "2.0", "id": _id[0], "method": "tools/call",
                       "params": {"name": name, "arguments": args}})
    content = resp.get("result", {}).get("content", [])
    if not content: return {}
    text = content[0].get("text", "{}")
    try: return json.loads(text)
    except json.JSONDecodeError: return {"raw": text}


def exec_mod(proc, session, m, **p):
    return call(proc, "execute_module", module_id=m, params=p,
                context={"browser_session": session} if session else {})


def main(base, org):
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"FLYTO_MCP_ALLOW_LOCALHOST": "1",
                "FLYTO_ALLOWED_HOSTS": "localhost,127.0.0.1",
                "FLYTO_ALLOW_PRIVATE_NETWORK": "true"})
    proc = subprocess.Popen([sys.executable, "-m", "core.mcp_server"], cwd=str(SRC),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, env=env)
    try:
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18",
                               "clientInfo": {"name": "x", "version": "0.1"}, "capabilities": {}}})
        launch = call(proc, "execute_module", module_id="browser.launch",
                      params={"headless": True, "viewport": {"width": 1440, "height": 900}})
        session = launch["browser_session"]
        exec_mod(proc, session, "browser.goto", url=f"{base}/sign-in"); time.sleep(2)
        exec_mod(proc, session, "browser.type", selector="input[name='email']", text=os.environ['FLYTO_TEST_EMAIL'])
        exec_mod(proc, session, "browser.type", selector="input[name='password']", text=os.environ['FLYTO_TEST_PASSWORD'])
        exec_mod(proc, session, "browser.click", selector="button[type='submit']"); time.sleep(3.5)
        exec_mod(proc, session, "browser.goto", url=f"{base}/projects/{org}/warroom/exp-ctem"); time.sleep(4)

        # Big screenshot, just the page main area
        big = OUT / "ctem-error-big.png"
        exec_mod(proc, session, "browser.screenshot", path=str(big), full_page=True)
        print(f"saved {big}")

        # Snapshot DOM
        r = exec_mod(proc, session, "browser.snapshot", format="text")
        snap_path = OUT / "ctem-error-dom.txt"
        snap_path.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved {snap_path}")

        exec_mod(proc, session, "browser.close")
    finally:
        try: proc.stdin.close(); proc.wait(timeout=5)
        except Exception: proc.kill()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5181",
         sys.argv[2] if len(sys.argv) > 2 else "f3ecb96f19c3a9bcce5a32cbc9863d27")
