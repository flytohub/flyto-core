# Flyto2 Reusable Smoke Recipes

Flyto2 UI smoke should be captured as versioned Flyto recipes instead of being
rewritten by an agent for every session.

## Recipe Contract

- Keep recipes parameterized: URL, path, output prefix, and credentials are
  runtime arguments.
- Do not store tokens, PATs, passwords, Firebase sessions, or customer data in
  YAML.
- Save artifacts on every run: desktop screenshot, mobile screenshot, DOM audit
  JSON, and console errors.
- Emit standard JSON that another recipe, CI job, or agent can parse without
  rewriting assertions.
- Use DOM/evaluate checks for text and state. Use screenshots for visual
  evidence only.
- Capture network status as a redacted summary only: no headers, no bodies, and
  no URL query strings.
- Keep selectors generic unless a stable `data-testid` exists. Product smoke
  should survive UI copy changes where possible.
- Treat clean scans as "no qualifying signal observed", not "safe".

## Reuse Model

Use three layers instead of asking an agent to recreate the same browser flow:

- Generic smoke recipe: common health checks for any authenticated Flyto2 page.
- Scenario arguments: page path, required visible labels, output paths, and API
  URL pattern.
- Feature recipe: only split a dedicated recipe when the flow has stable product
  steps such as opening a drawer, starting a scan, completing a task, or
  exporting evidence.

The JSON report is the durable contract. Consumers should read
`desktop.pass_dom_integrity`, `mobile.pass_dom_integrity`, `console_errors`,
`network_sample.requests`, and artifact paths instead of scraping terminal logs.

## Flyto Cloud Bundle Model

Flyto Cloud can import recipe bundles as account-scoped MCP assets without
rewriting the YAML. Keep canonical recipes in this repo, then publish a bundle
manifest that tells Cloud where to place them for a Firebase user.

Recommended folder hierarchy:

```text
Warroom/
  <project_slug>/
    UI Smoke/
    Authenticated UI Smoke/
    Research Footprint/
    Pentest/
    Red Team/
```

The bundle manifest lives at
`src/recipe_bundles/flyto2-warroom-smoke.yaml`. It intentionally stores only
recipe paths, folder placement, scenario defaults, and redaction rules.
Credentials remain runtime arguments supplied by the caller or the user's active
session. Do not persist Firebase sessions, passwords, tokens, cookies, request
headers, response bodies, or URL query strings in the imported bundle.

The reusable service boundary is `core.recipe_bundles`. It has no Firebase
dependency:

```python
from core.recipe_bundles import build_recipe_bundle_plan, load_bundle_manifest

manifest = load_bundle_manifest("src/recipe_bundles/flyto2-warroom-smoke.yaml")
plan = build_recipe_bundle_plan(
    manifest,
    {"project_slug": "acme", "base_url": "https://warroom.example.com"},
)
```

A Cloud importer or future microservice should persist only the returned folder
and recipe asset plan. Runtime credentials stay outside the plan.

## Current Recipes

`flyto2-ui-smoke`

Use when dev auth or an existing authenticated browser context is available.

```bash
flyto recipe flyto2-ui-smoke \
  --base_url http://localhost:5173 \
  --path /footprint \
  --required_text '["Research Summary","Source Ledger","Evidence Timeline"]' \
  --output reports/flyto2-footprint-smoke.json \
  --output_prefix reports/flyto2-footprint
```

`flyto2-ui-login-smoke`

Use when the test must log in. Supply credentials at runtime only.

```bash
flyto recipe flyto2-ui-login-smoke \
  --login_url http://localhost:5173/login \
  --page_url http://localhost:5173/pentest \
  --username "$FLYTO_TEST_EMAIL" \
  --password "$FLYTO_TEST_PASSWORD" \
  --required_text '["Red Team","Pentest","Findings"]' \
  --output reports/flyto2-pentest-smoke.json \
  --output_prefix reports/flyto2-pentest
```

## Recommended Flyto2 Scenario Matrix

- `/footprint`: graph, selected node drawer, Research Footprint entry.
- `/pentest`: project list, scan launch controls, scan status, findings drawer.
- Red Team tab: target picker, preflight warning, running pipeline, log pane.
- Research Footprint drawer: citation chips, source ledger, timeline, missing
  evidence, validation tasks, export/report action.

When a scenario becomes stable and business-critical, split it from the generic
recipe into a dedicated recipe with explicit assertions and artifact names.
