"""Visual tour: log in, walk every known route, screenshot each.

Designed to surface theme / layout regressions across the whole app
after a global change (e.g. MUI default colour or input height tweak).

Output: out/tour/*.png — one per route. No DOM snapshots saved (too
verbose for ~20 pages); add `--with-dom` if you ever need them.
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
OUT = REPO_ROOT / "out" / "tour"


# Routes that need only the orgId. We discover orgId from the projects
# page (first project card) and substitute it in. workroom-section
# slugs are picked from sections.ts — using two representative ones.
ORG_ROUTES = [
    "/projects/{orgId}/dashboard",
    "/projects/{orgId}/issues",
    "/projects/{orgId}/repos",
    "/projects/{orgId}/domains",
    "/projects/{orgId}/pentest",
    "/projects/{orgId}/autofix",
    "/projects/{orgId}/pulse",
    "/projects/{orgId}/org",
    "/projects/{orgId}/settings",
    "/projects/{orgId}/reports",
    "/projects/{orgId}/asset-map",
    "/projects/{orgId}/warroom/security",
    "/projects/{orgId}/warroom/architecture",
]

PUBLIC_ROUTES = [
    "/sign-in",
    "/sign-up",
    "/forgot-password",
]

GLOBAL_ROUTES = [
    "/projects",
    "/flyto/resources/news",
    "/flyto/resources/changelog",
]


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
        "params": {"name": name, "arguments": args}
    })
    if "error" in resp:
        return {"status": "error", "error": resp["error"]}
    content = resp.get("result", {}).get("content", [])
    if not content:
        return {}
    try:
        return json.loads(content[0]["text"])
    except Exception:
        return {"raw": content[0].get("text", "")}


def ok(r):
    return r.get("status") == "success" or r.get("ok") is True


def execute(proc, session, module_id, **params):
    return call(proc, "execute_module",
                module_id=module_id, params=params,
                context={"browser_session": session} if session else {})


def shot(proc, session, name, base_url, path):
    url = base_url.rstrip("/") + path
    r = execute(proc, session, "browser.goto", url=url)
    if not ok(r):
        print(f"  [{name}] goto failed: {r}", file=sys.stderr)
        return False
    # Variable render time — dashboards have charts + react-query that
    # take a moment, login pages are instant. Pick a middle 2.5s.
    time.sleep(2.5)
    out_png = OUT / f"{name}.png"
    r = execute(proc, session, "browser.screenshot",
                path=str(out_png), full_page=True)
    if ok(r):
        print(f"  [{name}] -> {out_png.name}", file=sys.stderr)
        return True
    print(f"  [{name}] screenshot failed: {r}", file=sys.stderr)
    return False


def main(base_url):
    email = os.environ.get("FLYTO_TEST_EMAIL")
    password = os.environ.get("FLYTO_TEST_PASSWORD")
    if not email or not password:
        print("set FLYTO_TEST_EMAIL and FLYTO_TEST_PASSWORD", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({
        "FLYTO_MCP_ALLOW_LOCALHOST": "1",
        "FLYTO_ALLOWED_HOSTS": "localhost,127.0.0.1",
        "FLYTO_ALLOW_PRIVATE_NETWORK": "true",
    })

    proc = subprocess.Popen(
        [sys.executable, "-m", "core.mcp_server"],
        cwd=str(SRC),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, env=env,
    )

    try:
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18",
                               "clientInfo": {"name": "tour", "version": "0.1"},
                               "capabilities": {}}})
        launch = call(proc, "execute_module",
                      module_id="browser.launch",
                      params={"headless": True, "viewport": {"width": 1440, "height": 900}})
        session = launch.get("browser_session")
        print(f"[launch] session={session}", file=sys.stderr)

        # ── Phase 1: public routes (no auth) ───────────────────────
        # Start the unauth tour by force-signing out so /sign-in et al
        # don't bounce us back to /projects via the onlyGuest gate.
        execute(proc, session, "browser.goto", url=f"{base_url.rstrip('/')}/sign-out")
        time.sleep(1.5)
        execute(proc, session, "browser.evaluate",
                script="try{indexedDB.deleteDatabase('firebaseLocalStorageDb');}catch(e){};localStorage.clear();sessionStorage.clear();")
        print("[phase: public]", file=sys.stderr)
        for path in PUBLIC_ROUTES:
            name = "public-" + path.strip("/").replace("/", "-")
            shot(proc, session, name, base_url, path)

        # ── Phase 2: log in once ──────────────────────────────────
        print("[phase: login]", file=sys.stderr)
        execute(proc, session, "browser.goto", url=f"{base_url.rstrip('/')}/sign-in")
        time.sleep(1.5)
        execute(proc, session, "browser.type",
                selector="input[name='email']", text=email)
        execute(proc, session, "browser.type",
                selector="input[name='password']", text=password)
        execute(proc, session, "browser.click", selector="button[type='submit']")
        time.sleep(3.5)

        # ── Phase 3: global authed routes ────────────────────────
        print("[phase: global]", file=sys.stderr)
        for path in GLOBAL_ROUTES:
            name = "global-" + path.strip("/").replace("/", "-")
            shot(proc, session, name, base_url, path)

        # ── Phase 4: walk per-org pages ──────────────────────────
        # orgId comes from FLYTO_TEST_ORG_ID (cheapest), since
        # browser.evaluate in this MCP build doesn't reliably round-trip
        # string return values and the Projects card uses onClick (no
        # <a href>) so we can't grab it from the DOM either. Get it via
        #   docker exec flyto-engine-postgres-1 psql -U flyto -d flyto \
        #     -tAc "SELECT id FROM organizations LIMIT 1;"
        org_id = os.environ.get("FLYTO_TEST_ORG_ID")
        if not org_id:
            print("[skip per-org] set FLYTO_TEST_ORG_ID to enable", file=sys.stderr)
        else:
            print(f"[discover orgId] {org_id}", file=sys.stderr)
            print("[phase: per-org]", file=sys.stderr)
            for tmpl in ORG_ROUTES:
                path = tmpl.format(orgId=org_id)
                name = "org-" + tmpl.split("/")[-1].replace(":", "").replace("{orgId}", "")
                # Special case warroom which has 2 path segments
                if "warroom" in tmpl:
                    name = "org-warroom-" + tmpl.split("/")[-1]
                shot(proc, session, name, base_url, path)

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
