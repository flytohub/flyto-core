# Runtime Packages

`src/` contains the importable flyto-core runtime. Keep public behavior behind
stable package boundaries so recipes, the CLI, the MCP server, and enterprise
bundles can share the same execution path.

## Boundaries

- `core/` is the workflow engine, module registry, MCP server, validation layer,
  runtime policy checks, and built-in modules.
- `cli/` is the command-line facade. It should call runtime APIs instead of
  reimplementing workflow behavior.
- `recipes/` and `recipe_bundles/` are packaged recipe assets used by CLI,
  MCP, and smoke validation.

## Change Rules

- Module registration changes must keep the catalog, snapshots, and tests in
  sync.
- Browser and network modules must preserve SSRF and localhost opt-in guards.
- Secrets must be accepted via runtime parameters or environment variables, not
  committed YAML defaults.
- Community, SaaS, and enterprise deployments should differ by configuration
  and module policy, not by forked runtime logic.
