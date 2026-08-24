"""End-to-end proof for `workflows/totp_login_action.yaml`.

The workflow's whole claim is that a run cannot report success unless the site
recorded the action. Schema validation cannot establish that, and neither can a
mocked page: the claim is about a server that refuses a wrong one-time password
and only then registers a punch.

So this drives the real engine, through a real browser, against a site that
validates TOTP with an implementation independent of `crypto.totp`, and asserts
against what the site recorded rather than what the run believed it clicked.

Marked `browser` and `e2e`: it needs Playwright Chromium and binds a local
port, so it is excluded from the default suite.
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from fixtures.totp_site import PASSWORD, SECRET_B32, USERNAME, TotpSite  # noqa: E402

WORKFLOW = ROOT / "workflows" / "totp_login_action.yaml"

# Base32 for a different seed. The obvious "wrong" value to reach for is the
# encoding of the same bytes, which is not wrong at all. Derived rather than
# written out: a high-entropy Base32 literal is indistinguishable from a real
# seed to a secret scanner, and `fixtures/totp_site.py` already builds its own
# the same way.
WRONG_SECRET = base64.b32encode(b"a-completely-different-seed!").decode()

pytestmark = [pytest.mark.browser, pytest.mark.e2e]


def _params(site: TotpSite, secret: str, evidence: Path) -> dict:
    return {
        "login_url": f"{site.base_url}/login",
        "username": USERNAME,
        "password": PASSWORD,
        "totp_secret": secret,
        # The *_method params and otp_field_selector are deliberately omitted.
        # They carry defaults in the workflow's `params:` block, so leaving
        # them out proves the engine applies declared defaults — it reads
        # `params:`, and a `inputs:` block would be inert.
        "username_field": "Employee ID",
        "password_field": "Password",
        "login_button": "Sign in",
        "otp_button": "Verify",
        "signed_in_selector": "#attendance",
        "action_url": f"{site.base_url}/attendance",
        "action_button_selector": "#clock-in",
        "confirmation_selector": "#punch-confirmation",
        "evidence_path": str(evidence),
    }


async def _run(site: TotpSite, secret: str, evidence: Path):
    from core.engine.workflow.engine import WorkflowEngine

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    engine = WorkflowEngine(workflow, _params(site, secret, evidence))
    error = None
    try:
        await engine.execute()
    except Exception as exc:  # the failure itself is the assertion
        error = exc
    recorded = json.loads(urllib.request.urlopen(site.base_url + "/state").read())
    return error, recorded["punches"], engine.execution_log or []


@pytest.fixture(autouse=True)
def _allow_loopback(monkeypatch, tmp_path):
    # The SSRF guard blocks loopback by design; only operator environment
    # policy may open it, and only as narrowly as this.
    monkeypatch.setenv("FLYTO_ALLOWED_HOSTS", "127.0.0.1")
    monkeypatch.setenv("FLYTO_SANDBOX_DIR", str(tmp_path))


@pytest.mark.asyncio
async def test_correct_secret_signs_in_punches_and_leaves_evidence(tmp_path):
    evidence = tmp_path / "punch.png"
    with TotpSite() as site:
        error, punches, log = await _run(site, SECRET_B32, evidence)

    assert error is None, f"workflow failed: {error}"
    assert len(punches) == 1, f"the site recorded {punches}, expected exactly one punch"
    assert evidence.exists() and evidence.stat().st_size > 0
    assert [entry["status"] for entry in log] == ["success"] * len(log)


@pytest.mark.asyncio
async def test_wrong_secret_cannot_report_success(tmp_path):
    """The property the workflow exists for.

    A run that submits a code the site refuses must fail, must not write
    evidence, and above all must leave the site with nothing recorded.
    """
    evidence = tmp_path / "punch.png"
    with TotpSite() as site:
        error, punches, log = await _run(site, WRONG_SECRET, evidence)

    assert error is not None, "a refused one-time password was reported as success"
    assert punches == [], f"the site recorded {punches} despite a refused code"
    assert not evidence.exists(), "evidence was written for an action that never happened"
    # It must get as far as submitting the code, or the test proves nothing
    # about the code being the thing that was rejected.
    assert any(entry.get("step_id") == "submit_otp" for entry in log)
