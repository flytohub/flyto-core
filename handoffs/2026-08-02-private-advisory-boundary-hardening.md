# Private Advisory Boundary Hardening

## Baseline

Six private GitHub security reports remained in triage. Three older reports had
already been fixed on `main` by the guarded HTTP and cloud-download hardening,
but had not received a maintainer response. Three newer reports identified an
unguarded agent Ollama endpoint and incomplete filesystem confinement across
registered reader and writer modules.

This handoff intentionally omits private report identifiers, proof-of-concept
payloads, and reporter details until coordinated disclosure.

## Changes

- Agent-chain Ollama endpoints are loopback-only by default. Loopback traffic
  runs inside an exact host/port trusted scope, and operator-enabled remote
  traffic uses the shared connect-time DNS and per-redirect SSRF guards.
- Ollama error bodies are no longer reflected through agent module exceptions.
- Reported CSV, YAML, Excel, PDF, image, browser persistence, and document
  paths are canonicalized against `FLYTO_SANDBOX_DIR` before reads, directory
  creation, browser trace/snapshot writes, cookie import/export, document image
  extraction, or PDF generation.
- Existing fixtures now set an explicit temporary sandbox when exercising
  legitimate absolute test paths.
- Regression coverage rejects metadata endpoints and verifies every reported
  file sink is unreachable for a path outside the configured sandbox.
- Dependency floors select patched cryptography releases on every supported
  Python version and patched Starlette/build-tool releases on Python 3.10+.
  Python 3.9 retains explicit compatible branches where upstream dropped that
  interpreter before publishing a patched release.

## Verification

- Advisory regression suite: 25 passed.
- Existing module and LLM compatibility suite: 93 passed.
- Browser cookie export/import round-trip: 1 passed.
- Final non-browser/non-E2E suite: 2,349 passed, 13 skipped, 273 deselected;
  required line coverage remained above the 60% gate at 61.39%.
- Final advisory and agent compatibility rerun: 67 passed.
- Python 3.11 environment dependency audit: no known vulnerabilities.
- Base-runtime lock audit: no known vulnerabilities.
- Main and reverse-worker npm audits: no known vulnerabilities.
- Ruff, GitHub Actions workflow lint, documentation, brand, and project-memory
  checks: passed.
- Package sdist/wheel build and Twine checks: passed.
- Strict Indexer verify: 19 passed, zero warnings or failures.
- Indexer target audit reports no remaining filesystem finding on the changed
  modules and no finding on the new Ollama request path. Two unrelated
  heuristics in the same LLM file remain classified as review/drop false
  positives: a literal environment-key read and a fixed-host Gemini URL.

Local release gates are complete. Remote CI evidence and private advisory
responses will be recorded after the pushed commit has passed required checks.
