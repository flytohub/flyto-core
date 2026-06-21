# Claude Notes

Read `STATE.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and the latest handoff
before changing workflow, module, recipe, or browser validation behavior.

- Treat recipes as executable product-loop contracts.
- Keep credentials as runtime inputs or environment values, never checked-in
  docs or fixtures.
- Prefer DOM extraction and JavaScript evaluation for browser assertions; use
  screenshots only for visual/layout verification.
- Run `bash scripts/lint-project-memory.sh` after editing project memory files.
