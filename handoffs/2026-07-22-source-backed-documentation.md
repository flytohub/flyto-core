# Source-Backed Documentation And Release Gates

## Scope

The documentation audit replaced hand-maintained inventory claims with checked
source and runtime references. Narrative docs now cover purpose, architecture,
features, CLI, APIs, configuration, security, testing, operations, migration,
module/plugin development, workflows, and known limitations.

## Generated Contract

- `scripts/generate_catalog.py` owns the active runtime module catalog.
- `scripts/generate_reference.py` owns source modules, Python declarations,
  literal module registrations, CLI parsers, HTTP operations, environment
  readers, recipes, bundles, and maintained workflow references.
- `docs/documentation-manifest.json` maps every maintained source/configuration
  area to durable documentation.
- `scripts/check_documentation.py` rejects drift, missing ownership, and broken
  local Markdown links.
- `scripts/check_brand_identity.py` enforces Flyto2 naming and the approved 16
  `@flyto2.com` public aliases.

## Behavioral Changes

- Workflow status and evidence reads require the Execution API bearer token.
- Crypto, JWT, DNS, and OpenAI capabilities have explicit installable extras;
  the development extra includes dependencies needed by the offline suite.
- Credential-backed historical AI demo scripts are excluded from pytest
  collection because they contain no pytest cases.

## Verification

Use the command matrix in `docs/TESTING.md`. A release is not closed until
documentation/brand/project-memory checks, audited Ruff surfaces, non-browser
tests and coverage, npm audit, package build plus Twine, and strict full-scan
Indexer verification pass. Browser/E2E integration evidence remains explicit
when its environment exists.
