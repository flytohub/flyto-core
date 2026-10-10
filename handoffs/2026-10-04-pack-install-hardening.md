# Pack install hardening (adversarial review of PR #127)

Owner: claude
Branch: claude/pack-review-fixes
Date: 2026-10-04

## What changed

Adversarial review of the language-neutral packs work (PR #127, merged as
f8c44b2). Four defects were reproduced with failing tests first, then fixed:

1. **Code swapped after verification ran unverified.** `install_pack` checked
   the tree digest and signature against the source directory, but the
   `PluginManager` spawned the process lazily (first call, and again after a
   crash) from that same directory. Any file changed after install ran. Now a
   `subprocess-jsonrpc` pack is copied into a host-private `mkdtemp` directory
   by `core.pack.manifest.stage_pack_tree`, which hashes the bytes it writes;
   the digest compared with `artifact.digest` is the copy's, and the runtime is
   registered against the copy. Refusals remove the copy; `uninstall_pack`
   removes it. (`src/core/pack/manifest.py`, `src/core/pack/host.py`)
2. **Namespace squatting.** The static `DENIED_NAMESPACES` list does not
   include several namespaces flyto-core ships (`capability`, `vision`, `ui`,
   `webhook`, `email`, `slack`, ...) nor any Python pack's. A pack could publish
   `capability.*` beside `capability.invoke`, or join another vendor's
   namespace. The registry transaction now refuses a namespace held by another
   owner's module or declared by another installed external pack.
3. **Capability meaning hijack / safe-stop DoS.** `registry_contract_lookup`
   returns `ambiguous` (host fails closed) when providers disagree. A pack that
   declared an existing capability with a different contract, or none, turned
   another vendor's `role: safe_stop` capability into a refused call. Now
   refused unless the contract is identical (a second identical provider is
   still allowed).
4. **Concurrent install race.** Two `install_pack` calls for one id could both
   pass the `ALREADY_INSTALLED` check (6 threads -> 2 installs). Installs are
   now serialized by `_INSTALL_LOCK`.

Tests: `tests/core/pack/test_pack_hardening.py` (10 tests; 8 failed on
f8c44b2). Docs: `docs/specs/PACK_MANIFEST_SPEC.md` "Installing", CHANGELOG
`[Unreleased]` / Security.

## Why

The owner's model is "Cloud only knows: a resource installed a module pack
which provides these capabilities". That only holds if a pack cannot change
what an installed capability means, cannot impersonate another owner's
namespace, and runs the code that was signed.

Rejected: re-checking the digest at each spawn (still racy between check and
exec); constraining `provides_capability` to the pack's namespaces (would stop
an OpenRMF pack from providing a standard capability another pack also
provides).

## Verified

- `pytest tests/core/pack`: 86 passed (76 existing + 10 new; Node e2e ran,
  node v23).
- `ruff check src/core/pack tests/core/pack`: clean.
- Full `pytest -m 'not browser and not e2e'` in the shared dev venv: 5169
  passed; failures are `tests/test_hints.py` (Node deps absent in the
  worktree) and `test_version_identity` (stale editable install) — both fail
  identically on f8c44b2 with the change stashed.
- CI on the PR (see PR checks).

## Not verified

- flyto-indexer exploration could not answer for this code: the shared index
  is built from the main checkout, which sits at 82a87fd (before packs), and
  worktrees are excluded. References were checked with grep instead.
- Key ids are not bound to pack ids: any key in the host's trusted set may
  sign any pack id. That is host trust policy, left as is.
- No OS sandbox for subprocess packs (unchanged). Staged files are owner
  read-only but a same-user process can still alter them.
- No robot, Gazebo or ROS 2 run; capability host and adapter safety rules
  untouched.

## Follow-ups

- Consider adding flyto-core's shipped namespaces to `DENIED_NAMESPACES` so
  `flyto.plugin.v1` plugins get the same protection statically.
- flyto-cloud still does not call `install_pack`.
