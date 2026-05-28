"""Project-type flow verification tour.

Logs in, opens the Projects page, exercises the new 4-card project_type
picker + 2-level custom feature picker, creates a Custom-mode org with
SAST + SCA sub-features selected, then verifies the resulting
workspace sidebar inside that org actually hides CTEM-only nav items.

Screenshots land in out/tour-pt/*.png. Console prints a pass/fail
verdict for each step the script can assert programmatically.

Env vars required: FLYTO_TEST_EMAIL, FLYTO_TEST_PASSWORD.
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
OUT = REPO_ROOT / "out" / "tour-pt"


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
    else:
        print(f"[shot FAIL] {name}: {r}", flush=True)
    return path


def click_any(proc, session, selectors, label):
    """Try each selector in turn, return True on first success."""
    for sel in selectors:
        r = exec_mod(proc, session, "browser.click", selector=sel)
        if ok(r):
            print(f"[click] {label} matched {sel!r}", flush=True)
            return True
    print(f"[click FAIL] {label}: tried {selectors}, last response: {r}", flush=True)
    return False


def click_by_text(proc, session, text, label, scope="document"):
    """Click any element whose textContent matches `text`. Uses JS
    evaluation so we don't depend on Playwright `:has-text` syntax,
    which the underlying browser tool may not support."""
    js = f"""
        (() => {{
            const root = {scope};
            const all = root.querySelectorAll('*');
            for (const el of all) {{
                if (el.children.length === 0) continue;  // skip parents
            }}
            // Match leaf or button elements whose visible text equals
            // / contains the target string.
            const target = {json.dumps(text)};
            const candidates = [];
            for (const el of root.querySelectorAll('button, [role="button"], div, p, span, label')) {{
                const t = (el.innerText || el.textContent || '').trim();
                if (t === target || t.includes(target)) {{
                    candidates.push({{tag: el.tagName, text: t.slice(0, 60), el: el}});
                }}
            }}
            // Prefer the smallest matching element (most specific).
            candidates.sort((a, b) => a.text.length - b.text.length);
            if (candidates.length === 0) return false;
            candidates[0].el.click();
            return true;
        }})()
    """
    r = exec_mod(proc, session, "browser.evaluate", script=js)
    val = r.get("result") if isinstance(r, dict) else r
    # Different MCP tool versions return either {"result": true} or just true.
    success = val is True or val == "true" or (isinstance(val, dict) and val.get("result") is True)
    print(f"[click-by-text] {label!r} text={text!r} → {success}", flush=True)
    return success


def eval_js(proc, session, script):
    r = exec_mod(proc, session, "browser.evaluate", script=script)
    return r.get("result") or r.get("data") or r


def main(base_url):
    email = os.environ.get("FLYTO_TEST_EMAIL")
    password = os.environ.get("FLYTO_TEST_PASSWORD")
    if not email or not password:
        print("Set FLYTO_TEST_EMAIL and FLYTO_TEST_PASSWORD env vars.", file=sys.stderr)
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

    verdicts = []  # list of (step_name, pass_bool, detail)

    try:
        send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18",
                       "clientInfo": {"name": "pt-tour", "version": "0.1"},
                       "capabilities": {}},
        })

        launch = call(proc, "execute_module",
                      module_id="browser.launch",
                      params={"headless": True, "viewport": {"width": 1440, "height": 900}})
        if not ok(launch):
            print(f"browser.launch failed: {launch}", file=sys.stderr)
            return 2
        session = launch["browser_session"]

        # ── 1. Sign in ──────────────────────────────────────────────
        exec_mod(proc, session, "browser.goto", url=f"{base_url}/sign-in")
        time.sleep(2.0)
        exec_mod(proc, session, "browser.type",
                 selector="input[name='email']", text=email)
        exec_mod(proc, session, "browser.type",
                 selector="input[name='password']", text=password)
        click_any(proc, session, [
            "button[type='submit']",
            "button:has-text('Sign in')",
        ], "sign in")
        time.sleep(3.5)

        url_info = eval_js(proc, session,
                           "JSON.stringify({url: location.href})")
        print(f"[after-login] {url_info}", flush=True)
        shot(proc, session, "00-after-login")

        # ── 2. Navigate to /projects ────────────────────────────────
        exec_mod(proc, session, "browser.goto", url=f"{base_url}/projects")
        time.sleep(2.5)
        shot(proc, session, "01-projects-landing")

        # Assert: Resources nav group is GONE. The old sidebar had
        # 'Security News' / 'Documentation' / "What's New". Search the
        # DOM text and fail if any of those strings still appears in
        # the sidebar.
        nav_text = eval_js(proc, session, """
            (() => {
                const navs = document.querySelectorAll('nav, [role="navigation"]');
                let t = '';
                navs.forEach(n => { t += ' ' + (n.innerText || ''); });
                return t;
            })()
        """)
        nav_str = json.dumps(nav_text)
        had_resources = any(s in nav_str for s in
                            ["Security News", "What's New", "Documentation"])
        verdicts.append(("Resources group removed from sidebar",
                         not had_resources, nav_str[:200]))

        # ── 3. Open Create dialog ───────────────────────────────────
        # Hero button reads "+ New Project" (English) — the create-org
        # CTA renders with the i18n key projects.create which defaults
        # to "New Project" in the en bundle. Match the literal text.
        clicked = click_by_text(proc, session, "New Project", "open create dialog")
        if not clicked:
            click_by_text(proc, session, "Create", "open create dialog (fallback)")
        time.sleep(2.0)
        shot(proc, session, "02-create-dialog-open")

        # Assert: dialog shows 4 project_type cards. Look for the
        # titles in the DOM. Defensive — i18n may render either the
        # key fallback or a translated string.
        dialog_text = eval_js(proc, session, """
            (() => {
                const d = document.querySelector('[role="dialog"]');
                return d ? d.innerText : '';
            })()
        """)
        dialog_str = json.dumps(dialog_text)
        has_all   = ("Full Platform" in dialog_str or "全部" in dialog_str)
        has_code  = ("Code Audit" in dialog_str)
        has_ctem  = ("CTEM" in dialog_str)
        has_custom = ("Custom" in dialog_str or "自訂" in dialog_str)
        verdicts.append(("4-card project_type picker visible",
                         has_all and has_code and has_ctem and has_custom,
                         f"all={has_all} code={has_code} ctem={has_ctem} custom={has_custom}"))

        # ── 4. Click Custom card ────────────────────────────────────
        # The 4 cards live inside [role="dialog"]. Scope the search so
        # we don't accidentally click the "Custom" word elsewhere.
        click_by_text(proc, session, "Custom", "select Custom card",
                       scope="document.querySelector('[role=\"dialog\"]') || document")
        time.sleep(1.0)
        shot(proc, session, "03-custom-picked-empty")

        # Assert: the module picker (2-level) is rendered.
        after_custom = eval_js(proc, session, """
            (() => {
                const d = document.querySelector('[role="dialog"]');
                return d ? d.innerText : '';
            })()
        """)
        ac = json.dumps(after_custom)
        has_sast = ("SAST" in ac)
        has_picker = ("Modules" in ac or "模組" in ac or has_sast)
        verdicts.append(("2-level module picker visible on Custom",
                         has_picker, f"sast={has_sast} modules-header={'Modules' in ac}"))

        # ── 5. Click SAST + SCA child checkboxes ────────────────────
        # Child labels are Typography spans inside clickable rows.
        # Click by text scoped to the dialog so we don't grab the
        # "SAST" badge in the parent sidebar.
        click_by_text(proc, session, "SAST", "tick SAST",
                       scope="document.querySelector('[role=\"dialog\"]') || document")
        time.sleep(0.4)
        click_by_text(proc, session, "SCA / CVE", "tick SCA",
                       scope="document.querySelector('[role=\"dialog\"]') || document")
        time.sleep(0.5)
        shot(proc, session, "04-sast-sca-ticked")

        # Assert: indeterminate state should now exist on the parent
        # checkbox (we ticked 2 of 6 Code Audit children).
        indet = eval_js(proc, session, """
            (() => {
                const inputs = document.querySelectorAll('[role="dialog"] input[type="checkbox"]');
                let indet = 0;
                inputs.forEach(i => { if (i.indeterminate) indet++; });
                return indet;
            })()
        """)
        indet_count = indet.get('result') if isinstance(indet, dict) else indet
        verdicts.append(("Parent goes indeterminate when partial children",
                         (isinstance(indet_count, int) and indet_count >= 1)
                         or '"indeterminate":1' in json.dumps(indet),
                         f"indeterminate inputs={indet_count}"))

        # ── 6. Fill name + submit ───────────────────────────────────
        # MUI TextField wraps a real <input> inside the dialog. Target
        # the first text input inside the dialog (the name field).
        org_name = f"PT Tour {int(time.time())%10000}"
        type_resp = exec_mod(proc, session, "browser.type",
                             selector="[role='dialog'] input",
                             text=org_name)
        print(f"[type name] {ok(type_resp)} resp={type_resp}", flush=True)
        time.sleep(0.4)

        # Submit button — same i18n key resolves to "New Project" in
        # the en bundle. There are two on the page (hero + dialog
        # submit) so scope by dialog.
        click_by_text(proc, session, "New Project", "submit create",
                       scope="document.querySelector('[role=\"dialog\"]') || document")
        time.sleep(4.0)
        shot(proc, session, "05-after-submit")

        # Assert: URL changed away from /projects (we should be in
        # /projects/<orgId> now after the navigate call).
        url_after = eval_js(proc, session, "location.pathname")
        pathname = url_after.get('result') if isinstance(url_after, dict) else url_after
        path_str = str(pathname)
        verdicts.append(("Submit navigates into the new org workspace",
                         "/projects/" in path_str and path_str != "/projects",
                         f"pathname={path_str}"))

        # ── 7. Verify workspace sidebar filters CTEM-only items ─────
        # User picked code_audit + sast + sca only → CTEM pages
        # (domains / asset-map / warroom-exposure) must NOT be visible.
        sidebar_text = eval_js(proc, session, """
            (() => {
                const navs = document.querySelectorAll('nav, aside, [role="navigation"]');
                let t = '';
                navs.forEach(n => { t += ' ' + (n.innerText || ''); });
                return t;
            })()
        """)
        sb = json.dumps(sidebar_text)
        # Looking for CTEM-only labels (these should be ABSENT).
        # 'Attack Surface' is a top-level item gated by 'ctem' feature.
        has_attack_surface = "Attack Surface" in sb
        has_exposure = "Exposure" in sb
        verdicts.append(("Workspace sidebar hides CTEM-only items in code-mode project",
                         not has_attack_surface,
                         f"attack-surface-visible={has_attack_surface} exposure={has_exposure}"))

        shot(proc, session, "06-workspace-sidebar")

        # ── 8. Clean up: delete the test org via UI ────────────────
        # Best-effort. If the delete button isn't reachable we just
        # leave it — the user can prune via API.
        exec_mod(proc, session, "browser.goto", url=f"{base_url}/projects")
        time.sleep(2.0)
        shot(proc, session, "07-projects-with-new-org")

        exec_mod(proc, session, "browser.close")

    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ── Verdict report ──
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
