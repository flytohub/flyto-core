# Nested Template Browser Closure

Date: 2026-08-28
Owner: codex
Branch: `main`

## Outcome

Nested `template.invoke` now preserves one browser session across the child and
the caller's following node. The child borrows the browser runtime without
assuming cleanup ownership. A module-emitted error event follows the normal
step failure contract, and visible waits accept a visible match even if an
earlier duplicate is hidden.

## Real proof

The Cloud parent template ran three steps successfully: browser creation,
nested login template invocation, and a parent-side `text=Notices` visible
wait. Run `20260828-7fdf520a` finished with no error; its authenticated status
endpoint returned HTTP 200 with `completed` and 3/3 steps, and the Cloud UI
returned to its terminal Run state while retaining the browser preview.

This proves login-session handoff only. No attendance or clock-in action was
present or executed.

## Validation

- Focused Core browser, template invocation, lifecycle, and step-executor tests:
  107 passed.
- CI-equivalent offline Core suite: 3,210 passed, 12 skipped, 247 browser
  tests deselected, 0 failed.
- Package sdist and wheel built successfully and both passed Twine checks.
- Python lockfile, root npm runtime, and deobfuscation-worker npm audits found
  zero known vulnerabilities.
- Generated documentation, documentation contract, brand, release-drift, and
  project-memory gates passed; strict Indexer passed 19/19.
- The three new test files are Ruff-clean. The four edited legacy files retain
  72 pre-existing Ruff findings versus 76 at `HEAD`; this change added none and
  removed four.
- A real Playwright wait against the authenticated page succeeded with the
  patched driver.
