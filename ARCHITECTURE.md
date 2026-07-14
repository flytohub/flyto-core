# Flyto2 Core Architecture

## Boundaries

- Modules expose narrow automation actions and documented parameters.
- Recipes compose modules into repeatable workflows.
- Browser modules interact with pages but do not become product business logic.
- Workflow fixtures must stay separate from secret material and local-only
  machine assumptions.
- Warroom modules infer observable site/action/API/state graphs from evidence;
  they do not own product business logic and do not treat LLM output as a gate.

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
