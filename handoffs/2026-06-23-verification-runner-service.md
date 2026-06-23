# Verification Runner Service

## Summary

Added `core.verification_service`, exposed as the `flyto-verification` console
script. This is the first deployable microservice boundary for Flyto2
Deterministic Product Verification.

## Behavior

- Accepts the existing engine runner contract at `POST /run`:
  `workflowYaml`, `params`, `allowed_targets`, `org_id`, `campaign_id`, and
  `dry_run`.
- Revalidates `target_url` against engine-computed `allowed_targets`.
- Executes server-owned flyto-core workflow YAML and extracts
  `warroom.evidence_pack.v1` from `warroom.report`.
- Builds callback payloads compatible with
  `/api/v1/code/runner/executions/callback`, including `evidence_sig`,
  `evidence_pack`, finding counts, critical counts, and artifacts.
- Uses `FLYTO_ENGINE_CALLBACK_URL` / `FLYTO_ENGINE_URL` plus
  `FLYTO_RUNNER_SECRET` or `FLYTO_VERIFICATION_SECRET` for callback delivery.

## Verification

```text
PYTHONPATH=/Users/chester/flytohub/flyto-core/src python -m pytest /Users/chester/flytohub/flyto-core/tests/test_verification_service.py /Users/chester/flytohub/flyto-core/tests/modules/test_warroom_modules.py -q --no-cov
```

Result: 18 passed.

## Follow-up

- Add a Dockerfile/deploy target once the runtime host is selected.
- Add scheduled replay orchestration after the service is stable in staging.
