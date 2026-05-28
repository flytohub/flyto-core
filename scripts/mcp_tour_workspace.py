"""Workspace-sidebar filter verification.

Creates a project_type=custom org via API with ONLY code-audit children
selected, then drives the browser into that workspace and screenshots
the sidebar. The sidebar must contain code-audit items (Code Audit /
Pentest / etc.) and must NOT contain CTEM-only items (Attack Surface).

Run from the flyto-core repo. Env required:
  FLYTO_TEST_EMAIL / FLYTO_TEST_PASSWORD  — UI login
  FLYTO_DEV_TOKEN                          — for API call (dev-mode JWT)
"""

import json
import os
import sys
import subprocess
import time
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
OUT = REPO_ROOT / "out" / "tour-ws"


def send(proc, req):
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
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
    if "error" in resp:
        return {"status": "error", "error": resp["error"]}
    content = resp.get("result", {}).get("content", [])
    if not content:
        return {}
    text = content[0].get("text", "{}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def ok(r):
    return r.get("status") == "success" or r.get("ok") is True


def exec_mod(proc, session, module_id, **params):
    return call(proc, "execute_module",
                module_id=module_id, params=params,
                context={"browser_session": session} if session else {})


def shot(proc, session, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    r = exec_mod(proc, session, "browser.screenshot",
                 path=str(path), full_page=False)
    if ok(r):
        print(f"[shot] {name} -> {path}", flush=True)
    return path


def eval_js(proc, session, script):
    r = exec_mod(proc, session, "browser.evaluate", script=script)
    return r.get("result") if isinstance(r, dict) else r


def api_call(method, path, body=None, token=""):
    """Direct HTTP to the engine (no MCP — simpler for the setup step)."""
    url = f"http://localhost:8080{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error_status": e.code, "body": e.read().decode()}


def main(base_url):
    email = os.environ.get("FLYTO_TEST_EMAIL")
    password = os.environ.get("FLYTO_TEST_PASSWORD")
    token = os.environ.get("FLYTO_DEV_TOKEN", "")
    if not email or not password:
        print("Set FLYTO_TEST_EMAIL/PASSWORD env vars.", file=sys.stderr)
        return 1
    if not token:
        print("Set FLYTO_DEV_TOKEN env var (dev-mode JWT for the engine API).",
              file=sys.stderr)
        return 1

    # ── 1. Create a code-mode org via API ───────────────────────────
    org_resp = api_call("POST", "/api/v1/code/orgs", {
        "name": "WS Sidebar Test",
        "slug": f"ws-sb-{int(time.time())}"[:30],
        "project_type": "custom",
        "custom_features": ["code_audit", "sast", "sca"],
    }, token=token)
    if "id" not in org_resp:
        print(f"create org failed: {org_resp}", file=sys.stderr)
        return 2
    org_id = org_resp["id"]
    print(f"[setup] created org {org_id} project_type=custom features=[code_audit,sast,sca]",
          flush=True)

    # Also verify the resolver returns the expected page set
    caps = api_call("GET", f"/api/v1/me/capabilities?org_id={org_id}",
                    token=token)
    vp = caps.get("visible_pages", [])
    if isinstance(vp, dict):
        vp = list(vp.keys())
    print(f"[setup] visible_pages from /me/capabilities: {sorted(vp)}",
          flush=True)
    api_has_domains = "domains" in vp
    api_has_asset_map = "asset_map" in vp
    api_has_warroom_exposure = "warroom_exposure" in vp
    api_has_issues = "issues" in vp
    api_has_repos = "repos" in vp

    # ── 2. Launch browser, log in, navigate to the new org ──────────
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

    verdicts = []

    try:
        send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18",
                       "clientInfo": {"name": "ws-tour", "version": "0.1"},
                       "capabilities": {}},
        })

        launch = call(proc, "execute_module",
                      module_id="browser.launch",
                      params={"headless": True, "viewport": {"width": 1440, "height": 900}})
        session = launch["browser_session"]

        # Login
        exec_mod(proc, session, "browser.goto", url=f"{base_url}/sign-in")
        time.sleep(2.0)
        exec_mod(proc, session, "browser.type",
                 selector="input[name='email']", text=email)
        exec_mod(proc, session, "browser.type",
                 selector="input[name='password']", text=password)
        exec_mod(proc, session, "browser.click",
                 selector="button[type='submit']")
        time.sleep(3.5)

        # Navigate to the workspace of the freshly-created org
        target = f"{base_url}/projects/{org_id}"
        exec_mod(proc, session, "browser.goto", url=target)
        time.sleep(4.0)  # let workspace + capabilities query settle
        shot(proc, session, "00-workspace-loaded")

        # Pull the visible nav text — both global sidebar and any
        # workspace-internal nav. Compare against the API answer.
        nav_text = eval_js(proc, session, """
            (() => {
                const navs = document.querySelectorAll('nav, aside, [role="navigation"]');
                let t = '';
                navs.forEach(n => { t += ' || ' + (n.innerText || ''); });
                return t;
            })()
        """)
        nav_str = json.dumps(nav_text)

        # CTEM-only labels (should be ABSENT)
        ui_has_attack_surface = "Attack Surface" in nav_str
        ui_has_domains = "Domains" in nav_str
        ui_has_exposure = "Exposure" in nav_str
        # Code-only labels (should be PRESENT)
        ui_has_code_audit = "Code Audit" in nav_str

        verdicts.append((
            "Engine API filter: domains hidden (CTEM-only)",
            not api_has_domains,
            f"api visible_pages contains 'domains'={api_has_domains}",
        ))
        verdicts.append((
            "Engine API filter: asset_map hidden (CTEM-only)",
            not api_has_asset_map,
            f"api visible_pages contains 'asset_map'={api_has_asset_map}",
        ))
        verdicts.append((
            "Engine API filter: warroom_exposure hidden (CTEM-only)",
            not api_has_warroom_exposure,
            f"api visible_pages contains 'warroom_exposure'={api_has_warroom_exposure}",
        ))
        verdicts.append((
            "Engine API filter: issues visible (Code feature)",
            api_has_issues,
            f"api visible_pages contains 'issues'={api_has_issues}",
        ))
        verdicts.append((
            "Engine API filter: repos visible (Code feature)",
            api_has_repos,
            f"api visible_pages contains 'repos'={api_has_repos}",
        ))
        verdicts.append((
            "UI sidebar: 'Attack Surface' nav item NOT shown",
            not ui_has_attack_surface,
            f"nav text contains 'Attack Surface'={ui_has_attack_surface}",
        ))
        verdicts.append((
            "UI sidebar: 'Code Audit' nav item shown",
            ui_has_code_audit,
            f"nav text contains 'Code Audit'={ui_has_code_audit}",
        ))

        exec_mod(proc, session, "browser.close")

    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ── 3. Cleanup: delete the test org ─────────────────────────────
    api_call("DELETE", f"/api/v1/code/orgs/{org_id}", token=token)
    print(f"[cleanup] deleted org {org_id}", flush=True)

    print("\n=== VERDICTS ===")
    passed = 0
    for name, p, detail in verdicts:
        mark = "PASS" if p else "FAIL"
        if p:
            passed += 1
        print(f"  [{mark}] {name}")
        if not p:
            print(f"         detail: {detail}")
    print(f"\n{passed}/{len(verdicts)} checks passed.")
    return 0 if passed == len(verdicts) else 1


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5181"
    sys.exit(main(base))
