# Tests

`tests/` verifies the runtime engine, module catalog, browser automation,
security guards, packaged recipes, and enterprise smoke paths.

## Test Boundaries

- Unit tests should avoid external network and real credentials.
- Browser tests should use local fixtures or clearly marked public targets.
- Enterprise tests should validate offline/self-hosted behavior without leaking
  proprietary configuration.
- Tests that require real provider keys must skip when the environment variable
  is missing.

## Common Gates

Use focused pytest targets for local work and the repository CI for the full
package, security, and release loop.
