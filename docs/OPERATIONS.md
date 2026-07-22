# Operations

## Local CLI

Install into an isolated environment and choose only required extras. Run
`flyto modules --format json` to capture the active module set before deploying
automation that depends on optional integrations.

## Execution API

```bash
export FLYTO_API_TOKEN='replace-with-a-secret'
flyto serve --host 127.0.0.1 --port 8333
```

The loopback bind is the safe default. A reverse proxy must preserve bearer
headers, restrict origins, apply request limits, and terminate TLS. Do not make
the generated token file web-readable or mount it into unrelated containers.

## Verification Runner

Use `Dockerfile.verification` or the `flyto-verification` entry point. Configure
`FLYTO_VERIFICATION_API_KEY` and a trusted callback allowlist before accepting
`POST /run`. Keep the service private to the orchestration network.

## Observability

Operational evidence includes:

- process logs and command exit status;
- workflow execution IDs and per-step trace;
- evidence directory and artifact paths;
- replay start step and result;
- module/catalog version and environment;
- verification graph/report contract;
- callback outcome and redacted error details.

Do not log bearer tokens, provider keys, cookies, authorization headers, DSNs,
or unredacted workflow context.

## Upgrade Procedure

1. Read `CHANGELOG.md` and security notes.
2. Rebuild the virtual environment from bounded dependencies.
3. Run documentation, brand, test, build, npm audit, and Indexer gates.
4. Compare `flyto modules --format json` before and after the upgrade.
5. Run representative recipes with non-production credentials.
6. Verify evidence redaction and replay on a failed fixture.
7. Roll out to loopback/private staging before wider exposure.

## Failure Triage

- **401/403:** caller token or internal key is missing/invalid.
- **503 auth not initialized:** service lacks required protected-route state;
  fix configuration rather than bypassing the dependency.
- **Module blocked:** inspect allow/deny patterns and requested permissions.
- **Browser session missing:** launch a browser or pass the correct session ID.
- **Replay not found:** preserve `.flyto-runs`/evidence state for the execution.
- **Callback rejected:** add only the exact trusted callback host needed.
- **Catalog drift:** regenerate both catalog and source references.

## Release Artifacts

Build with `python -m build`, inspect the wheel/sdist contents, and validate with
Twine before publishing. PyPI metadata, GitHub README totals, docs, MCP registry
metadata, and release notes must use the generated 451-module/84-category
snapshot until the catalog changes.
