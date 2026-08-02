# GitHub Code-Scanning Security Closure

## Baseline

The `main` baseline at `6c7a7429f32cc07b965a25e4fa7dc7996c4a3ff2`
had 11 open GitHub code-scanning alerts: seven CodeQL path-injection flows,
two CodeQL incomplete-URL-test findings, one CodeQL exception-information
exposure, and one Grype finding for the PyPI publish action. GitHub Dependabot
and secret-scanning each reported zero open alerts. Local `pip-audit` and npm
audit also reported zero vulnerable dependencies.

## Changes

- `PluginManager` validates every requested plugin ID and uses it only to
  select an ID-to-directory mapping created during confined manifest
  discovery. It no longer constructs candidate paths from an HTTP-derived ID.
- Plugin discovery resolves physical directories, rejects symlinks escaping
  the configured root, and supports namespaced manifest IDs independently of
  physical directory naming.
- MCP HTTP returns a fixed generic error when `Mcp-Name` decoding fails, so
  decoder exception text and chained implementation details cannot reach a
  remote JSON-RPC response.
- Warroom bundle assertions parse URLs and compare exact HTTPS hostname/port
  fields rather than treating an origin as a trusted string prefix.
- Both PyPI publish jobs pin `pypa/gh-action-pypi-publish` to the upstream
  v1.14.2 commit `dc37677b2e1c63e2034f94d8a5b11f265b73ba33`, newer than the
  advisory's first patched v1.13.0 release.

## Local Verification

- Focused security/runtime/MCP/recipe suite: 147 passed.
- Runtime plus API suite: 304 passed.
- Full non-browser/non-E2E suite: 2,336 passed, 13 skipped, 273 deselected;
  coverage 61.39% against the required 60% floor.
- Project-memory, generated-documentation, brand, lockfile, Ruff, and
  `actionlint` checks passed.
- Python `pip-audit` and npm audit: zero vulnerabilities.
- Wheel and sdist build passed; Twine validated the generated artifacts.
- Flyto2 Indexer strict full scan: 19 pass, 0 warn, 0 fail; documentation and
  README scores 100, zero secret findings, and zero high-risk taint flows.

Browser/E2E suites were not run because this security closure changes no
browser behavior and requires no external service or credential. Remote GitHub
alert closure must be confirmed after the change is pushed and the final-sha
Security/CodeQL workflows complete.
