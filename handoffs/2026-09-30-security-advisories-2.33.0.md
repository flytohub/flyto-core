# Six reported advisories and the 2.33.0 release

Owner: claude
Branch: claude/security-advisories-2.33.0
Date: 2026-09-30

## What changed

- GHSA-hc4c-6x9g-5fq3 — `src/core/utils.py` `_extract_embedded_ipv4` decodes
  Teredo (`ip.teredo[1]`), IPv4-translated `::ffff:0:a.b.c.d` and ISATAP
  interface identifiers. `is_private_ip`, `_is_metadata_ip`, `validate_url_ssrf`
  and `_SSRFGuardedResolver` all consume it. The `database.*` DSN guard
  (`src/core/modules/atomic/database/_dsn_guard.py`) now uses the same decoder
  instead of its own NAT64/mapped-only copy.
- GHSA-m5gf-24gv-m9g8 — `src/core/verification_service.py` `post_callback` uses
  `guarded_client_session()` and `allow_redirects=False`.
- GHSA-8j62-f337-86xw — `src/core/modules/atomic/llm/_chat_models.py`
  `_http_post` aiohttp fallback and both aiohttp paths in `_providers.py` use
  `guarded_client_session()`.
- GHSA-cqv6-3m5f-qvw2 — `env.set` added to `_DEFAULT_DENYLIST`
  (`src/core/module_policy.py`); `previous_value` gated by `is_env_var_allowed`
  (`src/core/modules/atomic/env/set.py`).
- GHSA-59pf-mh94-r7vv — `verify.visual_diff` routes a non-URL `reference_url`
  through `validate_path_with_env_config` in `validate_params`.
- GHSA-6r7h-3hcc-jwpr — `guard_inference_target` in
  `src/core/modules/atomic/huggingface/_runtime.py`, called in
  `run_inference_api` before `InferenceClient(token=...)`: Hub repo ids pass; a
  URL needs `FLYTO_TRUSTED_LLM_HOSTS` plus the SSRF guard; anything else raises.
- Regression tests: `tests/core/test_reported_advisories_2026_09.py` (46
  cases), including a registry-wide pin of the 20 files still allowed a plain
  `aiohttp.ClientSession` (all fixed vendor hosts; swept by reading every one).
- `.flyto-rules.yaml` grep_deny rules for the removed literals.
- JS test runtime: `undici` 7.29.0 -> 7.30.0 in `package-lock.json` (new high
  advisories turned `npm run audit` red on main after 2026-09-23).
- Release 2.33.0: `pyproject.toml`, `server.json`, `SECURITY.md`,
  `security/advisories.json` (+6), regenerated `SECURITY_STATUS.md` and
  `docs/reference/`, inventory counts, `CHANGELOG.md`, `STATE.md`.

## Why

Minor, not patch: #97 and #98 added features after 2.32.1 was built from
`ee2390f`. `env.set` is denied rather than only redacted because its write also
changes process-wide policy read live (`FLYTO_ALLOWED_HOSTS`,
`FLYTO_ENV_VAR_ALLOWLIST`). The 34 remaining plain aiohttp sessions were not
converted: none takes a caller-chosen host, and converting them would break
`tests/modules/test_search_api.py`'s factory mock for no security gain.

## Verified

- Reporter PoCs (`poc` script in the session scratchpad) against a clean venv:
  PyPI `flyto-core==2.32.1` + `huggingface_hub` 2.0.0 -> all six VULNERABLE
  (HF_TOKEN, runner secret and Bearer key reached a loopback listener); the
  2.33.0 wheel built from this branch -> all six BLOCKED.
- New tests on unmodified `origin/main`: 30 of 46 fail; on this branch 46/46.
- Clean Python 3.11 venv, `pip install -e '.[dev,browser]'`, `npm ci`:
  `pytest -m 'not browser'` 4822 passed, 192 skipped, 0 failed, 65.76% coverage.
- CI gates run locally: release drift PASS, project-memory lint PASS,
  `lock-deps.sh` leaves `requirements.lock` unchanged, `pip_audit` clean,
  `check_documentation.py` PASS, `check_brand_identity.py` PASS, audited-surface
  Ruff PASS, root and deobfuscate-worker `npm run audit` 0 vulnerabilities,
  `python -m build` + `twine check` PASS.
- `flyto-index verify . --full-scan --strict` with the CI-pinned indexer
  (`0dbae85`): 19/19 pass.

## Not verified

- `flyto-index task validate` ran and failed for environmental reasons: it uses
  the indexer's interpreter (no `pytest-cov`, so the repo's `--cov` addopts is
  rejected) and lints the whole repo including `examples/`.
- The workspace indexer at `1dd61d6` reports one `weak_scan_taint` high finding
  (`src/cli/recipe.py:80`, `run_recipe -> load_recipe`) on this branch and on
  unmodified `origin/main` alike. `load_recipe` resolves the path and checks it
  stays under `RECIPES_DIR` (GHSA-mxcc); the newer taint engine does not
  recognise that containment. CI pins `0dbae85`, which passes.
- No live DNS-rebinding or Teredo-routed host was used; the tests model the
  rebinding window by approving the destination check and resolving `localhost`
  at connect time.

## Follow-ups

- Before bumping `INDEXER_SHA`/the CI indexer pin past `0dbae85`, teach the
  taint engine the resolve-and-parents containment in `load_recipe`, or the
  flyto-core verify gate goes red on unchanged code.
