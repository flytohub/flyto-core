# Pillow 13 on Python 3.11+, aiohttp 3.14.5, undici 7.30.1

Owner: claude
Branch: claude/pillow-13 (from origin/main 2a428ff)
Date: 2026-10-30

## What changed

- **`image` extra:** `Pillow>=13.0.0,<14; python_version >= '3.11'` and
  `Pillow>=11.3.0,<13; python_version < '3.11'`. 13.0.0 fixes the advisories
  open against 12.3.0 (GHSA-78g4-xqwv-q3g8 among them; 39 reported by
  flyto-cloud's pip-audit). Pillow 13 requires Python 3.11, and this package
  declares `>=3.10`, so 3.10 keeps the 12 line: those advisories have no fix
  there. (The 3.10 split was another Claude session's catch.)
- **`aiohttp>=3.14.4`** (CVE-2026-111748, found by this repository's own
  `pip_audit -r requirements.lock` step, so main's CI step was already red).
  `requirements.lock` regenerated without `--upgrade`: only aiohttp 3.14.5 and
  yarl 1.25.1 moved.
- **`package-lock.json`:** `npm audit fix`, undici 7.30.0 -> 7.30.1 (jsdom's,
  test runtime only; 1 high advisory, already red on main).

## Verified (commands and results)

The steps of `.github/workflows/ci.yml` (job `verify`) on Python 3.11, in a
clean venv with `pip install -e '.[dev,browser]'` and `npm ci --ignore-scripts`:

- `scripts/lock-deps.sh` then `git diff --exit-code requirements.lock`: only
  the intended aiohttp/yarl change; `pip_audit -r requirements.lock`: no known
  vulnerabilities.
- `check_release_drift.py` PASS (2.41.0 unreleased), `check_catalog_facts.py`
  (482 modules), `check_brand_identity.py` PASS.
- `pytest -m 'not browser'` on Pillow 13.0.0 and aiohttp 3.14.5:
  6715 passed, 191 skipped, 479 deselected. (A first run without `npm ci`
  had 63 failures, all `tests/test_hints.py` needing jsdom.) `test_hints.py`
  again after the undici bump: 64 passed.
- `npm run audit` (root and the deobfuscate worker): 0 vulnerabilities.
- `python -m build` + `twine check`: PASSED with the long_description warning
  main already has.
- `flyto-index verify . --full-scan --strict --json`: 19 pass, 2 warn
  (docs_coverage, agent_hygiene), 0 fail, exit 0 -- identical on main 2a428ff.
- The built wheel's `Requires-Dist` evaluated per interpreter: 3.10 gets
  `<13,>=11.3.0`, 3.11 and 3.13 get `<14,>=13.0.0`.

## Not verified

- The `compat` job (3.10, 3.12, 3.13): no 3.10 interpreter here, so a real
  3.10 install was not run; only the wheel metadata was evaluated.
- Browser tests (`-m browser`), excluded from CI as well.

## Follow-ups

- flyto-cloud pins this repository by commit archive; re-pin its
  requirements to the merge commit and relock `requirements-ce.lock`.
