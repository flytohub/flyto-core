# Flyto2 Core Architecture

## Boundaries

- Modules expose narrow automation actions and documented parameters.
- Recipes compose modules into repeatable workflows.
- `docs/TOOL_CATALOG.md` is generated from the module registry; it is the
  source of truth for the current 452-module, 84-category public inventory.
- Browser modules interact with pages but do not become product business logic.
- Workflow fixtures must stay separate from secret material and local-only
  machine assumptions.
- Warroom modules infer observable site/action/API/state graphs from evidence;
  they do not own product business logic and do not treat LLM output as a gate.
- `docs/reference/` is generated from Python AST and repository assets. It maps
  932 maintained Python files, 5,351 declarations, 466 literal module
  registrations, 22 HTTP operations, 93 environment names, CLI parsers,
  recipes, bundles, and workflows back to source.

## Runtime Components

| Component | Ownership |
|---|---|
| `src/cli` | command parsing, local/remote workflow operations, templates, plugins |
| `src/core/engine`, `runtime`, `workflow` | validation, orchestration, execution, replay |
| `src/core/modules` | registry plus atomic, composite, and third-party capabilities |
| `src/core/api` | local authenticated Execution API and MCP HTTP transport |
| `src/core/verification_service.py` | isolated deterministic runner boundary |
| `src/core/browser` | browser lifecycle and Playwright integration |
| `src/core/evidence`, `state`, `metering` | persistence, artifacts, usage, and recovery |
| `src/recipes`, `src/recipe_bundles`, `workflows` | maintained executable workflow assets |

## Public Interfaces

The public interfaces are the three console scripts, Python imports, module
metadata/schema, YAML workflow contract, MCP stdio/HTTP operations, Execution
API routes, verification service routes, plugin entry-point/protocol contract,
and packaged recipes. Source-defined plugin HTTP handlers are not public server
routes until an authenticated application explicitly mounts them.

## Data Flow

1. A recipe or caller selects modules and parameters.
2. Module validation checks the required input shape.
3. Execution returns structured results, artifacts, screenshots, or assertions.
4. Product-loop checks feed CI, release evidence, or manual audit work.
5. Failing steps identify the product contract that needs repair.
6. Warroom evidence packs can be consumed by release gates or Cloud UI without
   storing runtime credentials.

## Deployment / Edition

- Developer mode runs recipes locally against local or staging services.
- CI mode runs maintained bundles and smoke checks without interactive secrets.
- Enterprise mode should support local-only validation for compose, Helm,
  browser, API, backup, and no-egress workflows.

## Trust Boundary

Untrusted input includes recipe YAML, module parameters, browser pages, network
responses, generated artifacts, and filesystem paths. Modules must validate
inputs, keep secrets outside checked-in fixtures, and avoid silently passing
broken product assertions.

Warroom reports must redact secret-looking keys and strip URL query strings.
LLM review is explicit opt-in and advisory only.

Provider SDKs, browsers, image/crypto/DNS features, and server frameworks are
capability extras. Base-package import cannot assume every extra is installed;
the feature boundary must either provide a safe fallback or return an
actionable named-extra instruction such as `flyto-core[crypto]`.
