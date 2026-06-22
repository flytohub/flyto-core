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
    assert findings["horizontal_overflow"]["severity"] == "P1"
    assert result["scores"]["p0"] == 3
    assert result["scores"]["p1"] == 1


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
