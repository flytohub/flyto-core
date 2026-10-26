# Offline chain verifier, neutral contract wording, resource faults in the adapter contract

Owner: claude
Branch: claude/chain-verify-20261026 (from origin/main 253561a; local, not pushed)
Date: 2026-10-26

## What changed

**M10: `core/chain` and `flyto chain verify`.** The spec is flyto-cloud's
reference verifier `scripts/verify_chain.py`, its format module
`services/execution_chain/record.py` and its key module `signing.py`, all on
`feat/unified-platform-integration-20261018` at 7b1ad6507.

- `src/core/chain/record.py` holds the `flyto.execution-chain.v1` format:
  - closed key sets, `prev` links and `head`, `seq`, stage order;
  - the `STAGES` table of who may write each stage. Cloud may write S6 only
    with `host_verified: false`;
  - one attestation per section.

  Canonical bytes are `core.pack.manifest.canonical_bytes`, re-exported, so
  core has one implementation.
- `src/core/chain/keys.py` holds `flyto.execution-chain-keys.v1`:
  - an `ALGORITHMS` table: `ed25519` (what Cloud issues) and
    `ecdsa-p256-sha256`;
  - trust through signed rotations. A key that no rotation names is an
    anchor;
  - the `not_before <= at < not_after` window;
  - revocation with `retained_heads`.
- `src/core/chain/verify.py` checks, in this order: links, signatures, the
  `INVARIANTS` table, then the `COMPLETENESS` table. The invariants are:
  - S6 sits on the S5 it names;
  - S7 ran the contract S1 judged;
  - S8 brackets the effect.

  `TRUST_MODES` has `all` and `host-only`. The exit codes are 0 verified,
  1 refused and 2 incomplete. The verifier opens no socket and takes no key
  from an export unless that file is passed as `--keys`.
- `src/cli/chain.py` adds `flyto chain verify <record.json> --keys <keys.json>`.
  `--keys` can repeat. It takes a document, a `{signer: document}` map, an
  export, or a list of these. `--cloud-keys` and `--host-keys` are accepted as
  aliases. `src/cli/main.py` wires it in.
- `tests/core/chain/fixtures/golden/` holds a record and key documents. They
  were made by Cloud's own `record.py` and `signing.py` in a venv that had
  only `cryptography`. `make_golden.py` reproduces them byte for byte.

**Domain-neutral wording.** `src/core/capability_contract.py` used to say "The
robot ended at map (x, y)" or "the car ended on floor N". It now says "The
resource ended at position (x, y)" or "it ended facing heading h", which
matches `distance_to` and `angle_to`. `tests/core/test_domain_neutral_wording.py`
covers the generic contract modules.

**Resource fault in the adapter contract.** This follows Cloud's
`equipment_fault.py` and `local/equipment_faults.py` and uses the same names.
`src/core/adapter_status.py` adds:
- `fault: {reason, since}`. `null` means checked with no fault; an absent key
  means unknown; a field that cannot be read is a fault;
- the `fault_code` exception attribute and `AdapterFaultError`;
- `status_payload`, a field-by-field read of `connection_status()` /
  `transport_status()`.

`CapabilityHost` changes:
- a raised fault is recorded on the call (`fault`) and latched;
- `CapabilityHost.connection_status()` reports the latched fault until the
  adapter answers `fault: None`.

An adapter that reports nothing stays valid. Its records and its status
(`None`) have no `fault` key. `docs/specs/PORTABLE_CAPABILITY_SPEC.md` gains a
"Reporting a fault" section.

## Verified

What was run:

- `pytest -m 'not browser'` (Python 3.11, `.[dev,browser]`, root `npm ci`):
  6714 passed, 192 skipped, 0 failed, coverage 73.38%.
- New tests: 38 chain/CLI, 28 fault, 9 wording.
- `ruff check`: clean on the CI-audited list and on every file this lane
  touched.
- `check_release_drift`, `check_catalog_facts` and `check_brand_identity`:
  pass.
- `python -m build` and `twine check`: pass. `twine check` warns that
  `long_description` is missing; that warning was already on main.
- The fixed-scanner `verify --full-scan --strict`: 19 pass, 2 fail
  (`docs_coverage`, `agent_hygiene`). origin/main 253561a fails the same two:
  #143 removed AGENTS.md, CLAUDE.md and README wiring.

- Failing first: all three new test modules failed at collection
  (`core.chain`, `cli.chain` and `core.adapter_status` were missing). The
  wording test failed on `capability_contract.py:98`.
- Parity with Cloud's `scripts/verify_chain.py` on 11 mutated golden records:
  all 11 give the same result. Core's codes are a superset: it also reports
  signature failures alongside a broken link. For a wrong record schema core
  says `CHAIN_RECORD_SCHEMA` (the `record.py` code), and the reference says
  `CHAIN_RECORD_INVALID`.

## Not verified

- GitHub CI, PyPI publish, and a GitHub archive tarball hash for a new Cloud pin.
- Cloud running against this core: no Cloud test was run with this commit pinned.
- `--payloads`, a separate `--revocations` list and observer (cross-host) S8
  evidence from design 4.4 are not implemented.
- MCP `task(action='validate')`: the MCP server is pinned to another root. The
  CLI strict verify was run instead.
