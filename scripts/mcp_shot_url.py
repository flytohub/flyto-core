"""Tiny utility: launch a fresh browser session and screenshot exactly
one URL. Useful when you want a clean shot of a public page without
inheriting auth state from earlier runs.
"""
import json, os, sys, subprocess, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

def send(proc, req):
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line: raise RuntimeError(proc.stderr.read() if proc.stderr else "EOF")
        if line.strip(): return json.loads(line)

_id = [10]
def call(proc, name, **args):
    _id[0] += 1
    resp = send(proc, {"jsonrpc":"2.0","id":_id[0],"method":"tools/call",
                       "params":{"name":name,"arguments":args}})
    c = resp.get("result", {}).get("content", [])
    return json.loads(c[0]["text"]) if c else {}

def main(url, out_png):
    out_png.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"FLYTO_MCP_ALLOW_LOCALHOST":"1","FLYTO_ALLOWED_HOSTS":"localhost,127.0.0.1","FLYTO_ALLOW_PRIVATE_NETWORK":"true"})
    proc = subprocess.Popen([sys.executable, "-m", "core.mcp_server"], cwd=str(SRC),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1, env=env)
    try:
        send(proc, {"jsonrpc":"2.0","id":1,"method":"initialize",
                    "params":{"protocolVersion":"2025-06-18","clientInfo":{"name":"shot","version":"0.1"},"capabilities":{}}})
        launch = call(proc, "execute_module", module_id="browser.launch",
                      params={"headless":True,"viewport":{"width":1440,"height":900}})
        session = launch.get("browser_session")

        # IndexedDB/localStorage are origin-scoped, so we have to be on
        # the same origin as the target before clearing. Hit /sign-out
        # first (triggers Firebase signOut + clears auth) so the next
        # navigation to /sign-in lands on the public form rather than
        # being bounced to /projects by the onlyGuest gate.
        target = url.rstrip("/")
        # Derive origin from URL (strip path)
        from urllib.parse import urlparse
        u = urlparse(url)
        origin = f"{u.scheme}://{u.netloc}"
        call(proc, "execute_module", module_id="browser.goto",
             params={"url": f"{origin}/sign-out"}, context={"browser_session":session})
        time.sleep(1.5)
        call(proc, "execute_module", module_id="browser.evaluate",
             params={"script":"try{indexedDB.deleteDatabase('firebaseLocalStorageDb');}catch(e){};localStorage.clear();sessionStorage.clear();"},
             context={"browser_session":session})
        call(proc, "execute_module", module_id="browser.goto",
             params={"url":url}, context={"browser_session":session})
        time.sleep(2.5)
        shot = call(proc, "execute_module", module_id="browser.screenshot",
                    params={"path":str(out_png),"full_page":True},
                    context={"browser_session":session})
        print(f"saved={shot.get('status')} -> {out_png}", file=sys.stderr)
        call(proc, "execute_module", module_id="browser.close",
             params={}, context={"browser_session":session})
    finally:
        try: proc.stdin.close(); proc.wait(timeout=5)
        except Exception: proc.kill()

if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
