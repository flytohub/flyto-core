import pytest

from core.verification_service import (
    VerificationRunRequest,
    count_findings,
    execute_verification,
    target_allowed,
)


def test_verification_scope_allows_only_engine_computed_hosts():
    assert target_allowed("https://app.flyto2.com/projects", ["https://app.flyto2.com"])
    assert target_allowed("https://app.flyto2.com/projects", ["app.flyto2.com"])
    assert not target_allowed("https://evil.example.com/projects", ["https://app.flyto2.com"])


@pytest.mark.asyncio
async def test_verification_service_rejects_target_outside_scope():
    result = await execute_verification(
        VerificationRunRequest(
            workflowYaml="name: blocked\nsteps: []\n",
            params={"target_url": "https://evil.example.com"},
            allowed_targets=["https://app.flyto2.com"],
        )
    )

    payload = result.callback_payload()
    assert result.status == "failed"
    assert result.verdict == "blocked"
    assert "outside" in result.error_message
    assert payload["status"] == "failed"
    assert payload["evidence_sig"].startswith("sha256:")


@pytest.mark.asyncio
async def test_verification_service_executes_warroom_yaml_and_emits_evidence_pack():
    workflow = """
name: Verification Service Contract
steps:
  - id: discover
    module: warroom.discover
    params:
      target: "{{target_url}}"
      use_browser: false
      pages:
        - url: "{{target_url}}"
          text: "Product Verification"
          router_paths:
            - "/verification"
            - "/settings/billing/enterprise/sso"
          business_state:
            credits_remaining: 0
          controls:
            - tag: button
              text: "Run verification"
              data-testid: "run-verification"
              disabled: false
          requests:
            - method: POST
              url: "https://app.flyto2.com/api/verification/run"
              status: 200
              trigger: "run-verification"
              has_ui_effect: false
  - id: generate
    module: warroom.generate_scenarios
    params:
      site_graph: ${discover.site_graph}
      name: Verification Service Replay
  - id: replay
    module: warroom.run
    params:
      scenarios: ${generate.scenarios}
      stop_on_failure: true
  - id: evidence_pack
    module: warroom.report
    params:
      site_graph: ${discover.site_graph}
      scenarios: ${generate.scenarios}
      run_result: ${replay}
      artifacts:
        target_url: "{{target_url}}"
        graph_contract: warroom.product_verification.v1
        verification_service: flyto-verification
      format: json
"""

    result = await execute_verification(
        VerificationRunRequest(
            workflowYaml=workflow,
            params={"target_url": "https://app.flyto2.com/verification"},
            allowed_targets=["https://app.flyto2.com"],
        )
    )

    payload = result.callback_payload()
    assert result.status == "complete"
    assert result.evidence_pack is not None
    assert result.evidence_pack["schema_version"] == "warroom.evidence_pack.v1"
    assert result.evidence_pack["artifacts"]["verification_service"] == "flyto-verification"
    assert result.findings_count >= 2
    assert result.critical_count >= 1
    assert payload["runner_execution_id"].startswith("verification-")
    assert payload["evidence_pack"]["scores"]["reachable_coverage"] == 0.5
    assert payload["evidence_sig"].startswith("sha256:")


@pytest.mark.asyncio
async def test_verification_service_dry_run_returns_planned_evidence():
    result = await execute_verification(
        VerificationRunRequest(
            workflowYaml="name: dry\nsteps: []\n",
            params={"target_url": "https://app.flyto2.com"},
            allowed_targets=["https://app.flyto2.com"],
            dry_run=True,
        )
    )

    assert result.status == "complete"
    assert result.verdict == "planned"
    assert result.evidence_pack is not None
    assert count_findings(result.evidence_pack) == (0, 0)
    assert result.callback_payload()["evidence_pack"]["artifacts"]["dry_run"] is True
