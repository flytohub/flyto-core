"""Screenshot the 8 CTEM/Exposure pages the user flagged as ugly.

Pages walked (URL pattern /projects/<orgId>/warroom/<sectionId>):
  exp-posture     態勢總覽 (Posture Overview)
  exp-actions     修復計畫 (Remediation / Action Plan)
  exp-domains     域名情報 (Domain Intel)
  exp-supply      供應鏈 (Supply Chain)
  exp-monitoring  告警中心 (Monitoring)
  exp-threat      威脅情報 (Threat Intel)
  exp-brand       Brand Protection
  exp-ctem        CTEM Actions

Uses the existing Flyto2 org which has the CTEM data populated.
Screenshots land in out/tour-ctem/<section>.png.
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
OUT = REPO_ROOT / "out" / "tour-ctem"


SECTIONS = [
    ("exp-posture",    "01-posture-overview"),
    ("exp-actions",    "02-action-plan"),
    ("exp-domains",    "03-domain-intel"),
    ("exp-supply",     "04-supply-chain"),
    ("exp-monitoring", "05-monitoring"),
    ("exp-threat",     "06-threat-intel"),
    ("exp-brand",      "07-brand-protection"),
    ("exp-ctem",       "08-ctem-actions"),
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


def main(base_url, org_id):
    email = os.environ.get("FLYTO_TEST_EMAIL")
    password = os.environ.get("FLYTO_TEST_PASSWORD")
    if not (email and password):
        print("Set FLYTO_TEST_EMAIL/PASSWORD env vars.", file=sys.stderr)
        return 1

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

    OUT.mkdir(parents=True, exist_ok=True)

    try:
        send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18",
                       "clientInfo": {"name": "ctem-tour", "version": "0.1"},
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

        for section_id, slug in SECTIONS:
            url = f"{base_url}/projects/{org_id}/warroom/{section_id}"
            exec_mod(proc, session, "browser.goto", url=url)
            time.sleep(3.0)  # let queries + charts render
            png = OUT / f"{slug}.png"
            r = exec_mod(proc, session, "browser.screenshot",
                         path=str(png), full_page=True)
            print(f"[shot] {slug} -> {png} ok={ok(r)}", flush=True)

        exec_mod(proc, session, "browser.close")

    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    return 0


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5181"
    org  = sys.argv[2] if len(sys.argv) > 2 else "f3ecb96f19c3a9bcce5a32cbc9863d27"
    sys.exit(main(base, org))
