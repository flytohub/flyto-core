import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


def get_module(module_id: str):
    from core.modules import atomic  # noqa: F401
    from core.modules.registry import ModuleRegistry

    return ModuleRegistry.get(module_id)


@pytest.mark.asyncio
async def test_warroom_discover_builds_redacted_site_graph():
    mod = get_module("warroom.discover")
    page = {
        "url": "https://app.flyto2.com/projects?token=secret",
        "title": "Projects",
        "text": "Projects Run workflow",
        "horizontal_overflow": False,
        "controls": [
            {
                "tag": "button",
                "text": "Run workflow",
                "data-testid": "run-workflow",
                "authorization": "Bearer secret",
            }
        ],
        "requests": [
            {
                "method": "POST",
                "url": "https://app.flyto2.com/api/workflows/run?session=secret",
                "status": 200,
                "headers": {"authorization": "Bearer secret"},
            }
        ],
    }
    result = await mod({"target": page["url"], "pages": [page], "use_browser": False}, {}).execute()

    graph = result["site_graph"]
    assert result["ok"] is True
    assert graph["target"] == "https://app.flyto2.com/projects"
    assert graph["pages"][0]["control_count"] == 1
    assert graph["actions"][0]["selector"] == '[data-testid="run-workflow"]'
    assert graph["apis"][0]["url"] == "https://app.flyto2.com/api/workflows/run"
    assert graph["scores"]["p0"] == 0


@pytest.mark.asyncio
async def test_warroom_discover_flags_deterministic_p0_p1_findings():
    mod = get_module("warroom.discover")
    page = {
        "url": "https://app.flyto2.com/reports",
        "text": "",
        "controls": [],
        "horizontal_overflow": True,
        "console_errors": ["boom"],
        "requests": [{"method": "GET", "url": "https://app.flyto2.com/api/reports", "status": 500}],
    }
    result = await mod({"target": page["url"], "pages": [page], "use_browser": False}, {}).execute()

    findings = {item["code"]: item for item in result["site_graph"]["findings"]}
    assert findings["blank_screen"]["severity"] == "P0"
    assert findings["console_error"]["severity"] == "P0"
    assert findings["api_5xx"]["severity"] == "P0"
    assert findings["ghost_api_type_c"]["severity"] == "P0"
    assert findings["horizontal_overflow"]["severity"] == "P1"
    assert result["scores"]["p0"] == 4
    assert result["scores"]["p1"] == 1


@pytest.mark.asyncio
async def test_warroom_discover_builds_intent_state_and_reachable_coverage_graphs():
    mod = get_module("warroom.discover")
    page = {
        "url": "https://app.flyto2.com/projects",
        "title": "Projects",
        "text": "Projects pending partial stale expired",
        "router_paths": ["/projects", "/settings/billing", "/settings/sso"],
        "business_state": {"credits_remaining": 0},
        "controls": [
            {"tag": "button", "text": "Generate report", "data-testid": "generate-report"},
        ],
        "requests": [
            {
                "method": "POST",
                "url": "https://app.flyto2.com/api/reports",
                "status": 200,
                "trigger": "generate-report",
                "has_ui_effect": False,
            },
            {
                "method": "POST",
                "url": "https://app.flyto2.com/api/invite",
                "status": 200,
                "source": "openapi",
                "ui_path": False,
            },
        ],
        "state_assertions": [
            {"id": "credits_gate", "expected": "disabled", "observed": "enabled"},
        ],
    }

    result = await mod({"target": page["url"], "pages": [page], "use_browser": False}, {}).execute()
    graph = result["site_graph"]
    findings = {item["code"]: item for item in graph["findings"]}

    assert graph["intents"][0]["verb"] == "generate"
    assert graph["actions"][0]["intent_id"] == graph["intents"][0]["id"]
    assert graph["scores"]["reachable_coverage"] == 0.333
    assert graph["scores"]["observed_coverage"] == 1.0
    assert {"pending", "partial", "stale", "expired"}.issubset(set(graph["pages"][0]["states"]))
    assert findings["ghost_api_type_a"]["severity"] == "P1"
    assert findings["ghost_api_type_b"]["severity"] == "P1"
    assert findings["state_contradiction"]["severity"] == "P0"


@pytest.mark.asyncio
async def test_warroom_state_contradictions_cover_credits_api_error_and_capability_hidden():
    mod = get_module("warroom.discover")
    result = await mod({
        "target": "https://app.flyto2.com/verification",
        "pages": [
            {
                "url": "https://app.flyto2.com/verification",
                "text": "Product Verification",
                "business_state": {"credits_remaining": 0},
                "controls": [{"tag": "button", "text": "Run verification", "disabled": False}],
            },
            {
                "url": "https://app.flyto2.com/report",
                "text": "Error",
                "business_state": {"success": True},
                "controls": [],
            },
            {
                "url": "https://app.flyto2.com/governance",
                "text": "Loading capability",
                "controls": [],
                "state_assertions": [
                    {
                        "id": "capability_resolved_before_hidden",
                        "expected": "capability_loading_visible",
                        "observed": "hidden",
                    }
                ],
            },
        ],
        "use_browser": False,
    }, {}).execute()

    findings = [item for item in result["site_graph"]["findings"] if item["code"] == "state_contradiction"]
    messages = {item["message"] for item in findings}
    assert len(findings) >= 3
    assert any("credits are exhausted" in message for message in messages)
    assert any("API reported success" in message for message in messages)
    assert any(item["evidence"].get("assertion_id") == "capability_resolved_before_hidden" for item in findings)


@pytest.mark.asyncio
async def test_warroom_generate_scenarios_outputs_replay_yaml():
    discover = get_module("warroom.discover")
    generate = get_module("warroom.generate_scenarios")
    graph = (await discover({
        "target": "https://app.flyto2.com/projects",
        "pages": [{"url": "https://app.flyto2.com/projects", "text": "Projects", "controls": []}],
        "use_browser": False,
    }, {}).execute())["site_graph"]

    result = await generate({"site_graph": graph, "name": "Projects regression"}, {}).execute()

    assert result["ok"] is True
    assert result["scenarios"]["name"] == "Projects regression"
    assert result["scenarios"]["steps"][0]["module"] == "browser.goto"
    assert "browser.evaluate" in result["workflow"]
    assert "warroom.scenarios.v1" in result["workflow"]


@pytest.mark.asyncio
async def test_warroom_public_site_verify_flags_homepage_timeout_as_p0():
    mod = get_module("warroom.public_site_verify")
    result = await mod({
        "base_url": "https://flyto2.com",
        "required_routes": ["/", "/robots.txt", "/sitemap.xml", "/llms.txt", "/llms-full.txt"],
        "observations": {
            "dns_matrix": [{"host": "flyto2.com", "ok": True}],
            "tls_matrix": [{"host": "flyto2.com", "ok": True}],
            "route_matrix": [
                {"path": "/", "timed_out": True, "error": "timeout"},
                {"path": "/robots.txt", "status": 200},
                {"path": "/sitemap.xml", "status": 200},
                {"path": "/llms.txt", "status": 200},
                {"path": "/llms-full.txt", "status": 200},
            ],
            "browser_matrix": [{"path": "/", "status": "timeout", "ok": False}],
            "seo_geo_matrix": {
                "title": False,
                "meta_description": True,
                "canonical": True,
                "open_graph": True,
                "structured_data": True,
                "llms_txt": True,
                "sitemap": True,
                "robots": True,
                "server_rendered_content": False,
            },
        },
    }, {}).execute()

    findings = {item["code"]: item for item in result["findings"]}
    assert result["contract"] == "flyto2.public_site_verification.v1"
    assert result["ok"] is False
    assert result["p0_findings"] == 2
    assert findings["critical_route_unavailable"]["severity"] == "P0"
    assert findings["browser_render_unverified"]["severity"] == "P0"
    assert result["p1_findings"] == 2


@pytest.mark.asyncio
async def test_warroom_public_site_verify_accepts_complete_route_browser_geo_evidence():
    mod = get_module("warroom.public_site_verify")
    required_routes = ["/", "/robots.txt", "/sitemap.xml", "/llms.txt", "/llms-full.txt"]
    result = await mod({
        "base_url": "https://flyto2.com",
        "generated_at": "2026-06-23T00:00:00+00:00",
        "required_routes": required_routes,
        "observations": {
            "dns_matrix": [{"host": "flyto2.com", "ok": True}],
            "tls_matrix": [{"host": "flyto2.com", "ok": True}],
            "route_matrix": [{"path": path, "status": 200} for path in required_routes],
            "browser_matrix": [{"path": "/", "status": "ok", "ok": True}],
            "seo_geo_matrix": {
                "title": True,
                "meta_description": True,
                "canonical": True,
                "open_graph": True,
                "structured_data": True,
                "llms_txt": True,
                "sitemap": True,
                "robots": True,
                "server_rendered_content": True,
            },
        },
    }, {}).execute()

    assert result["ok"] is True
    assert result["generated_at"] == "2026-06-23T00:00:00+00:00"
    assert result["p0_findings"] == 0
    assert result["p1_findings"] == 0
    assert result["scores"]["public_route_readiness"] == 1.0
    assert result["scores"]["seo_geo_readiness"] == 1.0


@pytest.mark.asyncio
async def test_testing_e2e_run_steps_executes_modules_and_assertions():
    mod = get_module("testing.e2e.run_steps")
    result = await mod({
        "steps": [
            {
                "id": "assert_ok",
                "module": "test.assert_true",
                "params": {"condition": True},
                "assertions": [{"path": "passed", "operator": "==", "expected": True}],
            }
        ],
    }, {}).execute()

    assert result["ok"] is True
    assert result["passed"] == 1
    assert result["results"][0]["assertions"][0]["passed"] is True


@pytest.mark.asyncio
async def test_testing_e2e_run_steps_fails_closed_on_assertion_error():
    mod = get_module("testing.e2e.run_steps")
    result = await mod({
        "steps": [
            {
                "id": "assert_bad",
                "module": "test.assert_true",
                "params": {"condition": True},
                "assertions": [{"path": "passed", "operator": "==", "expected": False, "severity": "P0"}],
            }
        ],
    }, {}).execute()

    assert result["ok"] is False
    assert result["failed"] == 1
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["severity"] == "P0"


@pytest.mark.asyncio
async def test_testing_scenario_run_executes_bdd_module_steps():
    mod = get_module("testing.scenario.run")
    result = await mod({
        "scenario": {
            "name": "Run button works",
            "given": ["an authenticated session"],
            "when": [{"module": "test.assert_true", "params": {"condition": True}}],
            "then": [{"module": "test.assert_true", "params": {"condition": True}}],
        }
    }, {}).execute()

    assert result["ok"] is True
    assert result["summary"]["failed"] == 0
    assert any(step.get("note_only") for step in result["steps"])


@pytest.mark.asyncio
async def test_warroom_run_and_report_create_evidence_pack():
    run_mod = get_module("warroom.run")
    report_mod = get_module("warroom.report")
    scenarios = {
        "name": "No browser deterministic scenario",
        "steps": [{"id": "assert_ok", "module": "test.assert_true", "params": {"condition": True}}],
    }

    run = await run_mod({"scenarios": scenarios}, {}).execute()
    report = await report_mod({
        "scenarios": scenarios,
        "run_result": run,
        "artifacts": {"url": "https://app.flyto2.com/dashboard?token=secret"},
    }, {}).execute()

    assert run["ok"] is True
    assert run["evaluation"]["passed"] is True
    assert report["ok"] is True
    assert report["evidence_pack"]["verdict"] == "pass"
    assert report["evidence_pack"]["artifacts"]["url"] == "https://app.flyto2.com/dashboard"


@pytest.mark.asyncio
async def test_warroom_report_preserves_visual_dom_and_network_artifacts():
    report_mod = get_module("warroom.report")
    report = await report_mod({
        "site_graph": {"scores": {"p0": 1, "observed_coverage": 1.0, "reachable_coverage": 0.5}},
        "run_result": {"ok": True, "passed": 1, "failed": 0, "total": 1, "results": []},
        "artifacts": {
            "screenshot": {"status": "success", "filepath": "/tmp/warroom.png"},
            "dom_snapshot": {"format": "html", "content": "<button>Run</button>", "size_bytes": 20},
            "network_log": {"count": 1, "requests": [{"url": "https://app.flyto2.com/api/run", "status": 200}]},
        },
    }, {}).execute()

    artifacts = report["evidence_pack"]["artifacts"]
    assert artifacts["screenshot"]["filepath"] == "/tmp/warroom.png"
    assert artifacts["dom_snapshot"]["content"] == "<button>Run</button>"
    assert artifacts["network_log"]["requests"][0]["status"] == 200
    assert report["evidence_pack"]["scores"]["p0"] == 1


@pytest.mark.asyncio
async def test_warroom_report_unwraps_workflow_engine_module_output():
    report_mod = get_module("warroom.report")
    workflow_wrapped_run = {
        "ok": True,
        "data": {
            "ok": True,
            "passed": 1,
            "failed": 0,
            "total": 1,
            "results": [{"id": "assert_ok", "status": "passed"}],
        },
    }

    report = await report_mod({"run_result": workflow_wrapped_run}, {}).execute()

    assert report["evidence_pack"]["scores"]["replay_reliability"] == 1.0
    assert report["evidence_pack"]["run"]["passed"] == 1


@pytest.mark.asyncio
async def test_warroom_llm_review_is_manual_and_advisory_only():
    mod = get_module("warroom.llm_review")
    result = await mod({
        "enabled": False,
        "evidence_pack": {"token": "secret", "verdict": "fail"},
    }, {}).execute()

    assert result["ok"] is True
    assert result["status"] == "skipped_disabled"
    assert result["advisory_only"] is True
    assert result["redacted_evidence"]["token"] == "[REDACTED]"
