"""Visual verification of the 2-level Custom feature picker.

Drives the browser to /projects, opens the New Project dialog, clicks
the Custom card (using a scoped selector that finds the dialog by
title not by [role="dialog"]), then ticks SAST + SCA + Threat Intel
and screenshots the resulting state to prove:

  - The 2-level picker renders when Custom is selected
  - Parent checkboxes show indeterminate when only some children ticked
  - Child checkboxes are clickable
  - The "X/N selected" counter appears
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
OUT = REPO_ROOT / "out" / "tour-cp"


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
        print(f"[shot] {name}", flush=True)


def eval_js(proc, session, script):
    r = exec_mod(proc, session, "browser.evaluate", script=script)
    return r.get("result") if isinstance(r, dict) else r


# Click an element whose visible text matches `text`, scoped to the
# create-project dialog (identified by its "New Project" h5 title, not
# by `[role="dialog"]` — the page has multiple of those). Walks up
# from the matching text node to the nearest element with `cursor:
# pointer` (the actual clickable card / row) and dispatches click.
CLICK_IN_CREATE_DIALOG_JS = """
    (() => {
        const target = %s;

        // Find THE create dialog. It's the [role="dialog"] whose
        // descendant h5 reads "New Project".
        const dialogs = document.querySelectorAll('[role="dialog"]');
        let root = null;
        for (const d of dialogs) {
            const h5 = d.querySelector('h5');
            if (h5 && h5.innerText.trim() === 'New Project') {
                root = d;
                break;
            }
        }
        if (!root) return {status: 'no-dialog', dialogCount: dialogs.length};

        // Find the smallest element whose direct text content contains
        // the target. Walk up to find a clickable ancestor (cursor:
        // pointer or has onclick or is a checkbox input).
        const all = root.querySelectorAll('*');
        let best = null;
        for (const el of all) {
            const tc = (el.innerText || '').trim();
            if (!tc.includes(target)) continue;
            // Prefer leaf elements with this text directly.
            if (best === null || tc.length < (best.innerText || '').length) {
                best = el;
            }
        }
        if (!best) return {status: 'no-text-match'};

        // Walk up to nearest clickable.
        let target_el = best;
        for (let i = 0; i < 8 && target_el; i++) {
            const style = window.getComputedStyle(target_el);
            if (style.cursor === 'pointer') break;
            if (target_el.onclick) break;
            target_el = target_el.parentElement;
        }
        target_el = target_el || best;
        target_el.click();
        return {status: 'clicked', tag: target_el.tagName,
                snippet: (target_el.innerText || '').slice(0, 80)};
    })()
"""


def click_in_dialog(proc, session, text):
    script = CLICK_IN_CREATE_DIALOG_JS % json.dumps(text)
    r = exec_mod(proc, session, "browser.evaluate", script=script)
    result = r.get("result") if isinstance(r, dict) else r
    print(f"[click-in-dialog] {text!r} → {result}", flush=True)
    return result


def main(base_url):
    email = os.environ.get("FLYTO_TEST_EMAIL")
    password = os.environ.get("FLYTO_TEST_PASSWORD")
    if not email or not password:
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

    try:
        send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18",
                       "clientInfo": {"name": "cp-tour", "version": "0.1"},
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

        # Open Create dialog
        exec_mod(proc, session, "browser.goto", url=f"{base_url}/projects")
        time.sleep(2.5)
        # Use the same JS approach to find + click the hero "+ New Project".
        eval_js(proc, session, """
            (() => {
                for (const b of document.querySelectorAll('button')) {
                    const t = (b.innerText || '').trim();
                    if (t.includes('New Project') && !b.closest('[role="dialog"]')) {
                        b.click();
                        return true;
                    }
                }
                return false;
            })()
        """)
        time.sleep(1.5)
        shot(proc, session, "01-dialog-default")

        # Click Custom card
        click_in_dialog(proc, session, "Custom")
        time.sleep(1.0)
        shot(proc, session, "02-custom-selected")

        # Tick SAST (Code Audit child)
        click_in_dialog(proc, session, "SAST")
        time.sleep(0.4)

        # Tick SCA / CVE (Code Audit child)
        click_in_dialog(proc, session, "SCA / CVE")
        time.sleep(0.4)

        # Tick Threat Intel (Attack Surface child) — proves the CTEM
        # group also expands and accepts clicks
        click_in_dialog(proc, session, "Threat Intel")
        time.sleep(0.4)
        shot(proc, session, "03-three-children-ticked")

        # Now click the "Code Audit" parent header (toggle-all). With
        # 2 of 6 Code Audit children ticked, this should turn ALL of
        # them ON (because not-all means "some or none" → click goes
        # to "all on").
        click_in_dialog(proc, session, "Code Audit")
        time.sleep(0.4)
        shot(proc, session, "04-code-audit-all-on")

        # Check what the dialog looks like — count checkboxes and
        # indeterminate state to assert state.
        snapshot = eval_js(proc, session, """
            (() => {
                // Find the create dialog by its title.
                const dialogs = document.querySelectorAll('[role="dialog"]');
                let root = null;
                for (const d of dialogs) {
                    const h5 = d.querySelector('h5');
                    if (h5 && h5.innerText.trim() === 'New Project') {
                        root = d; break;
                    }
                }
                if (!root) return {error: 'no-dialog'};
                const inputs = root.querySelectorAll('input[type="checkbox"]');
                let checked = 0, indet = 0;
                inputs.forEach(i => {
                    if (i.indeterminate) indet++;
                    else if (i.checked) checked++;
                });
                return {
                    inputs: inputs.length,
                    checked: checked,
                    indeterminate: indet,
                    text_includes_modules: (root.innerText || '').includes('Modules'),
                    text_includes_code_audit: (root.innerText || '').includes('Code Audit'),
                };
            })()
        """)
        print(f"\n[snapshot] {snapshot}", flush=True)

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
    sys.exit(main(base))
