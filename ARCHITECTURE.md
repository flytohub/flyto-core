# Flyto2 Core Architecture

## Product Layers

Flyto2 is one product with three independently usable packages. `flyto-ai`
understands, routes, and governs new work and provider use. `flyto-blueprint`
stores, learns from, and scores reusable procedures and never executes them.
`flyto-core`, layer three, validates schemas, executes and replays procedures
deterministically, and emits evidence. Core is a standalone runtime and does not
own the first two layers or hosted product/account logic.

## Boundaries

- Modules expose narrow automation actions and documented parameters.
- Recipes compose modules into repeatable workflows.
- `docs/TOOL_CATALOG.md` is generated from the module registry; it is the
  source of truth for the current 468-module, 85-category public inventory.
- Catalog search and detail carry each module's registry-declared
  `provides_capability` and `plugin`; neither is derived from the module ID.
- Browser modules interact with pages but do not become product business logic.
- Workflow fixtures must stay separate from secret material and local-only
  machine assumptions.
- Warroom modules infer observable site/action/API/state graphs from evidence;
  they do not own product business logic and do not treat LLM output as a gate.
- `docs/reference/` is generated from Python AST and repository assets. It maps
  960 maintained Python files, 5,667 declarations, 483 literal module
  registrations, 28 HTTP operations, 107 environment names, CLI parsers,
  recipes, bundles, and workflows back to source.

## Runtime Components

| Component | Ownership |
|---|---|
| `src/cli` | command parsing, local/remote workflow operations, templates, plugins |
| `src/core/engine`, `runtime`, `workflow` | validation, orchestration, execution, replay |
| `src/core/modules` | registry plus atomic, composite, and third-party capabilities |
| `src/core/modules/atomic/testing/visual_worker` | detachable, credential-free PNG comparison process and content-addressed diff evidence |
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

Private-network authorization is never a global SSRF bypass. An attested
campaign can install an exact task-local host/port scope; redirects and the
connect-time resolver enforce the same scope, while metadata endpoints remain
unconditionally forbidden. The visual worker receives only local PNG paths and
bounded comparison options through one JSON request, runs without provider
credentials, rejects oversized PNG dimensions before decoding, and refuses to
overwrite existing diff evidence or either input image.

Plugin IDs are lookup keys, never filesystem path fragments. The runtime
discovers manifests under the configured plugin root, resolves and confines
each physical directory there, and records the resulting ID-to-directory map.
Later API requests can only select from that validated map; an invalid ID or a
directory symlink that escapes the root fails closed before language detection
or entry-point access.

The separate inert `flyto.plugin.v1` adoption boundary accepts previously
adopted IDs only as an exact list or tuple of at most 256 unique bounded ASCII
reverse-DNS IDs. It validates that collection before membership, so arbitrary
iterables and custom sequences cannot run code through adoption.
Its shared text gate rejects C1 controls, bidi and zero-width formats,
surrogates, private-use, unassigned/noncharacters, and line/paragraph separators
before canonicalization or error projection across values, keys, endpoints, and
allowlists. Failures use stable static text only.

Provider SDKs, browsers, image/crypto/DNS features, and server frameworks are
capability extras. Base-package import cannot assume every extra is installed;
the feature boundary must either provide a safe fallback or return an
actionable named-extra instruction such as `flyto-core[crypto]`.
