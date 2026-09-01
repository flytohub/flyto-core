# Flyto2 Core Documentation

Flyto2 turns AI work into verified, replayable procedures: "AI said it
finished. Flyto2 shows the proof." `flyto-ai` understands/routes/governs new
work, `flyto-blueprint` stores/learns/scores procedures and never executes, and
standalone `flyto-core` validates schemas, executes/replays deterministically,
and emits evidence. The repo-local role contract is [`flyto-product.toml`](../flyto-product.toml).

## Start Here

- [Technical Whitepaper](WHITEPAPER.md): product boundary, architecture,
  determinism, security, and limitations.
- [Feature Guide](FEATURES.md): capability map and execution lifecycle.
- [CLI](CLI.md): supported commands and operational behavior.
- [HTTP And MCP API](API.md): routes, authentication, errors, and mount status.
- [Configuration](CONFIGURATION.md): extras, policy, environment, and local state.

## Build Workflows

- [Recipes](RECIPES.md): all 41 packaged recipes.
- [Generated Recipe Reference](reference/recipes.md): exact parameters, step
  count, and module composition for every packaged recipe.
- [YAML Workflow Specification](YAML_WORKFLOW_SPEC.md): workflow schema.
- [DSL](DSL.md): expressions, data references, and control flow.
- [Item Pipeline Specification](specs/ITEM_PIPELINE_SPEC.md): item semantics.
- [Plugin Manifest Specification](specs/PLUGIN_MANIFEST_SPEC.md): the implemented
  inert language-neutral manifest/adoption slice, its bounded existing-ID
  collision input, pre-canonicalization Unicode safety boundary, stable
  non-reflective errors, and lifecycle/runtime guarantees it does not claim.
- [Flyto2 Smoke Recipes](flyto2-smoke-recipes.md): maintained product checks.

## Build Modules And Plugins

- [Tool Catalog](TOOL_CATALOG.md): all 480 active runtime modules, parameters,
  and outputs. Catalog search and detail also report each module's
  registry-declared `provides_capability` and `plugin`, never a derived ID.
- [Module Quick Reference](MODULE_QUICK_REFERENCE.md)
- [Module Specification](MODULE_SPECIFICATION.md)
- [Writing Modules](WRITING_MODULES.md)
- [Register Module Guide](REGISTER_MODULE_GUIDE.md)
- [Plugin SDK](PLUGIN_SDK.md)
- [Module Publishing](MODULE_PUBLISHING_GUIDE.md)

## Architecture And Security

- [Architecture Map](architecture-map.md)
- [Minimal Architecture](CORE_MINIMAL_ARCHITECTURE.md)
- [Security Model](SECURITY_MODEL.md)
- [SSRF Security](SECURITY_SSRF.md)
- [Warroom Deterministic Verification](warroom-deterministic-verification.md)
- [Migration And Capability Status](MIGRATION_STATUS.md)

Architecture decisions and subsystem detail live in [`architecture/`](architecture/).

## Operate And Verify

- [Testing And Release Gates](TESTING.md)
- [Operations](OPERATIONS.md)
- [Migration And Capability Status](MIGRATION_STATUS.md)
- [Generated Reference](reference/README.md)

## Generated Reference

The generated layer makes source coverage auditable without turning narrative
guides into hand-maintained symbol dumps:

- 480 active runtime modules across 88 catalog categories.
- 971 maintained Python files and 6,027 declarations.
- 487 literal module registrations linked to source.
- every static CLI parser and HTTP decorator.
- 108 environment-variable readers.
- every packaged recipe, bundle, and maintained workflow YAML.
- every packaged recipe parameter and composed module step.

Run `.venv/bin/python scripts/check_documentation.py` to reject generated drift,
unowned source/configuration, or broken local links.

## Documentation Contract

- Narrative docs explain intent, invariants, failure behavior, and operator
  decisions.
- Generated docs prove implementation inventory and source ownership.
- Runtime catalog counts come from `ModuleRegistry`, not directory counting.
- Defined-but-unmounted or optional capability is labelled explicitly.
- Public naming is Flyto2 and public examples use registered `@flyto2.com`
  mailboxes.
