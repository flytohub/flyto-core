# Plugin Template

`plugin-template/` is the starting point for third-party or enterprise flyto-core
plugins. It should remain minimal, documented, and free of Flyto2 private
infrastructure assumptions.

## Expectations

- Plugins register modules through the `flyto.modules` entry point.
- Plugin examples must use placeholder credentials only.
- Enterprise-only modules should be controlled by packaging, policy, or
  deployment configuration rather than changing the shared runtime.
- Keep template dependencies narrow so plugin authors can audit what they ship.
