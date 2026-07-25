# Reverse-Engineering Toolkit, Phase 4 — reverse.deobfuscate

## Scope

Delivers Phase 4 of the `reverse.*` toolkit: real semantic JavaScript
deobfuscation (control-flow-flattening reversal, string-array decoding,
self-defending/debug-protection bypass, webpack/browserify unpacking) —
the capability `reverse.code` (Phase 3) explicitly deferred, since pure
Python AST tools can't execute/evaluate JS the way real deobfuscation needs.

## What Changed

- `src/core/modules/atomic/reverse/deobfuscate_worker/` (new): a Node.js
  sidecar — `package.json`/`package-lock.json` pinning `webcrack@2.16.0`,
  and `worker.mjs`, a single-shot worker (reads one JSON line from stdin,
  runs `webcrack(source)`, writes one JSON line to stdout, exits). No
  handshake/ping/shutdown protocol — one process per invocation, spawned
  and killed by the Python module.
- `src/core/modules/atomic/reverse/deobfuscate.py` (new): `reverse.deobfuscate`
  module. Manages its own dedicated Node.js subprocess directly (not the
  generic JSON-RPC plugin runtime in `src/core/runtime/`) — see DECISIONS.md
  for why. Real hard-kill-on-timeout (`proc.kill()` + `proc.wait()`),
  input/output size caps, scrubbed subprocess environment, clear
  `ModuleError`s when Node.js or the worker's `npm install` are missing.
- `src/core/module_policy.py`: added `code.execute` to
  `_DANGEROUS_PERMISSIONS` — the first new dangerous permission since
  `browser.debug`. `reverse.deobfuscate` is the only module that requires it.
- `pyproject.toml` / `MANIFEST.in`: ship the worker's `package.json`/
  `package-lock.json`/`worker.mjs` as package data (not `node_modules`,
  which needs a separate `npm install` regardless of packaging).
- `.github/workflows/ci.yml`: new step auditing the worker's dependency tree
  (`npm ci --ignore-scripts` + `npm audit --audit-level=high`, scoped to the
  worker directory), mirroring the existing root `npm run audit` step.
- Catalog reconciled to 468 modules across 85 categories; docs regenerated
  and the module-count prose hand-fixed across
  README/ARCHITECTURE/STATE/PROJECT/CHANGELOG/docs tree, plus the
  `pyproject.toml`/`server.json`/`demo.py`/`tests/test_public_metadata.py`
  public-description citation contract.

## Key Decisions (see DECISIONS.md for full rationale)

- **Not the generic plugin runtime.** `src/core/runtime/manager.py`'s
  JSON-RPC subprocess system already declares a `node` language config, but
  investigation found it unfinished: declared resource limits are never
  enforced, an `invoke()` timeout never kills the subprocess, and a plugin
  manifest's `modules:` list is never wired into `ModuleRegistry` — no
  example plugin exists anywhere in this repo. Building on it would inherit
  those gaps or require fixing shared infrastructure with a much larger
  blast radius than one new module.
- **System Node.js, not auto-bundled.** This repo has no working Node.js
  auto-bundling mechanism (Playwright's bundled Node is private/fragile; the
  `~/.flyto/node/` downloader referenced in `driver.py` doesn't exist).
  Rather than solving that (a separate, large, unscoped project), this
  module requires a system-installed Node.js 22/24 — the same tradeoff the
  existing plugin `node` config and `reverse.code`'s `jsast` extra already
  accept.
- **webcrack only, not restringer, in this version.** The npm-published
  `restringer` package turned out to be maintained by an unofficial fork
  whose dependency tree has dropped `isolated-vm` — a discrepancy from the
  canonical `HumanSecurity/restringer` project discovered only by checking
  directly, not by trusting a search summary. webcrack alone (which
  unconditionally uses its own `isolated-vm` sandbox) already delivers
  Phase 4's stated goal. Adding restringer later, once its npm situation is
  resolved, is tracked in `tasks.md`.
- **Whole-module permission gate.** Confirmed with the user: `code.execute`
  gates the entire module rather than being conditional on some
  "safe vs full" mode — there turned out to be no zero-execution mode once
  webcrack's own always-on sandboxed evaluation was understood correctly.

## Known Limitations (see STATE.md)

- Requires Node.js 22 or 24 on `PATH` plus a one-time `npm install` in the
  worker directory — not auto-installed.
- No `restringer` in this version (see above); its 40+ modules would be a
  genuine deeper pass but aren't required for Phase 4's stated goal.
- Same process-local/CDP-freeze-adjacent constraints don't apply here (this
  module never touches a browser/CDP session — it operates on a plain JS
  source string, like `reverse.code`), but it is the second `reverse.*`
  module (after the debugger tools) with a real, materially elevated risk
  profile, since it executes caller-supplied JS, even sandboxed.

## Verification

- `tests/modules/test_reverse_deobfuscate.py`: 9 tests — registration,
  permission-gate (denied/allowed), validation (missing/oversized source),
  mocked missing-Node/missing-`node_modules` error paths (run unconditionally),
  and real webcrack execution + real timeout-kill (skipped cleanly if Node/
  worker deps aren't present). All 9 pass against a real Node.js 22.22.2 +
  installed worker in this environment.
- `python scripts/check_documentation.py` passes.
- `pytest tests/test_public_metadata.py` passes (citation contract updated).
- Manual: verified `npm ci --ignore-scripts` + `npm audit` against the
  committed lockfile from a clean `node_modules` (0 vulnerabilities), and
  ran the worker directly (`node worker.mjs`) against a string-array-encoded
  sample, a malformed-JSON input, and a missing-`source` input.
