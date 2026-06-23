# 2026-06-23 Public Site Verification

## Scope

Added deterministic public-site verification to Warroom so `flyto2.com`
readiness can be evaluated from evidence instead of a health score or LLM
summary.

## Changes

- Added `warroom.public_site_verify`.
- Added `src/recipes/flyto2-public-site-verification.yaml`.
- Added tests for homepage timeout P0 classification and full evidence pass.

## Contract

The module emits `flyto2.public_site_verification.v1` with:

- `dns_matrix`
- `tls_matrix`
- `route_matrix`
- `browser_matrix`
- `seo_geo_matrix`
- `p0_findings`
- `p1_findings`
- readiness scores

Critical route, DNS, TLS, and browser proof failures are P0. AI crawler blocking
is P1 visibility evidence, not a homepage availability P0.

## Verification

```bash
python -m pytest tests/modules/test_warroom_modules.py -q --no-cov
```

Result: 12 passed.
