# Reverse-Engineering Toolkit, Phase 3

## Scope

Adds `reverse.code` to the `reverse.*` category (see
`2026-07-25-reverse-debugger-phase1.md` and `-phase2.md`): beautify minified
JavaScript and search its AST for function declarations, string literals, and
call sites. This closes `ROADMAP.md` 0.5's Phase 3 item. True semantic
deobfuscation (control-flow-flattening reversal, string-array decoding) is
now explicitly Phase 4 — not started, blocked on Node.js infrastructure that
doesn't exist yet in this repo.

## What Changed

- `src/core/modules/atomic/reverse/code.py`: `reverse.code`
  (beautify/list_functions/list_strings/find_calls). Pure Python — no
  Node.js subprocess anywhere. Uses `tree-sitter` + `tree-sitter-javascript`
  for AST parsing (a manual recursive tree-walk via `child_by_field_name`,
  not correlated queries — simpler to reason about for `function_declaration`
  / `variable_declarator`-assigned function/arrow expressions /
  `method_definition` / `call_expression`) and `jsbeautifier` for
  reformatting. Both raise a `ModuleError` with an actionable
  `pip install 'flyto-core[jsast]'` message on `ImportError`, matching the
  existing convention in `crypto.encrypt`/etc. for optional SDKs.
- New `jsast` extra in `pyproject.toml`
  (`tree-sitter`, `tree-sitter-javascript`, `jsbeautifier`), added to the
  `all` composite and to `dev` (so `pip install -e '.[dev]'` picks it up for
  contributors/CI — no new npm packages, no `package-lock.json`/CI changes).
- **No permission gate** — `required_permissions=[]`, the only `reverse.*`
  module without one. It takes a raw `source` string param (typically piped
  from a prior `reverse.scripts` get_source step) and never creates a CDP
  session or touches a live page, so it carries none of the risk the
  `browser.debug` gate exists for.
- Catalog reconciled to 465 modules across 85 categories; same doc/citation
  sweep as Phase 1/2, caught the citation-contract test in the same pass.

## Key Research That Shaped This (see DECISIONS.md)

Before committing to pure Python, three research passes checked whether a
Node.js-based route (needed for eventual real deobfuscation via
`@babel`/`acorn`/`terser`) was viable now:

- Playwright's bundled Node binary is reachable only via
  `playwright._impl._driver.compute_driver_executable()` — a private,
  no-compatibility-guarantee module, and this exact binary is already known
  to be fragile (`src/core/browser/driver.py`'s `_find_external_node()`
  exists specifically to route around it crashing under PyInstaller).
- The apparent fallback, `~/.flyto/node/` (a `_NODE_VERSION` constant
  referenced in `driver.py`), has **no downloader anywhere in the repo** —
  it's dead code, not a working auto-install mechanism.
- `sandbox.execute_js` was considered and rejected as an internal primitive
  to build on: denylisted by default, and only exposes
  stdout/stderr/exit_code with no structured-output channel.

Conclusion: the Node-invocation reliability problem isn't solved yet, so
Phase 3 ships the pure-Python subset that's genuinely achievable now
(beautify + structural AST search), and Phase 4 (real semantic
deobfuscation) waits until that infrastructure is worth building.

## Known Limitations (see STATE.md, DECISIONS.md)

- No real deobfuscation: no control-flow-flattening reversal, no
  string-array decoding via constant folding, no VM-based unpacking. Those
  need an actual JS engine, not just an AST parser.
- Requires the `jsast` extra to be installed; a clear error is raised
  otherwise (verified in tests via `monkeypatch.setitem(sys.modules, ...,
  None)` to simulate `ImportError` without actually uninstalling anything).

## Verification

- Query API and manual tree-walk approach (`child_by_field_name`) verified
  standalone against a scratch script covering all four action types plus
  jsbeautifier, before writing the final module — same "verify empirically
  first" discipline as Phase 1/2.
- `tests/modules/test_reverse_code.py` (new, 13 tests): registration,
  beautify, list_functions (all four function kinds: declaration, assigned
  function expression, assigned arrow function, method), list_strings,
  find_calls (plain identifier and member-expression callee, plus no-match),
  validation errors, and the missing-optional-dependency error path. No
  `@pytest.mark.browser` — this is the first `reverse.*` module that runs in
  the plain offline suite.
- `python scripts/check_documentation.py` passes.
- `bash scripts/lint-project-memory.sh` passes.
- `tests/test_public_metadata.py` (citation contract) passes.
