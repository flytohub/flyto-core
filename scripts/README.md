# Scripts

Scripts are maintenance utilities for packaging, auditing, docs, release checks,
and local diagnostics. They should be deterministic and safe to run from the
repository root.

## Rules

- Do not require real secrets for static checks.
- Prefer dry-run or check modes for CI-facing scripts.
- Keep generated files out of commits unless the script explicitly refreshes a
  checked-in snapshot.
- Use clear exit codes so CI can fail closed.

## Common Use

Run focused scripts when touching module catalogs, packaged recipes, security
policy, or release evidence. For broad verification, prefer the repository's CI
or pytest gates.
