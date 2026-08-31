# Isolated runtime authority and browser-profile convergence

## Scope

This candidate was built in an isolated clone whose push URL is disabled. It
does not modify the working repository used by the parallel Claude session.

Core now treats per-run module policy, sibling-template resolution, and browser
profile identity as opaque host capabilities. `template.invoke` propagates
those capabilities without exposing raw sibling definitions to expressions,
enforces the same scoped policy in children, and refuses recursion beyond 16
levels. Persistent Chromium profiles use an owner-only directory derived from a
one-way principal digest; launch no longer deletes Chromium singleton lock
files. Legacy unscoped local profiles remain compatible.

`browser.click` is 1.3.1. Automatic popup adoption remains backward compatible,
an explicitly requested new tab fails when none opens, and `hidden` waits track
visible matches so hidden duplicate DOM nodes cannot produce a false result.

## Verification

- Core non-browser/non-E2E suite: 3,090 passed, 126 skipped, 276 deselected,
  zero failed; 64.05% coverage against a 60% requirement.
- Focused wait, hint, metadata, and version contracts: 77 passed.
- Generated reference and documentation contract: passed; 967 maintained
  Python files and 5,712 declarations.
- Coordinated Cloud run against this exact Core source: 7,459 backend tests
  passed, 5 skipped, zero failed. Cloud frontend: 3,209 passed and production
  build completed.

## Limits and handoff

No source was merged or pushed and no deployment, authenticated third-party
site, real attendance action, production credential, or physical robot was
used. The original repositories must remain authoritative until this two-repo
candidate is reviewed and integrated together; landing only one side would
leave the Cloud/Core runtime contract incomplete.
