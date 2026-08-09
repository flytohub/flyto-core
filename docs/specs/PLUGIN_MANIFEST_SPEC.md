# Flyto2 Plugin Manifest — `flyto.plugin.v1` (DRAFT)

Status: **draft**. Nothing in this document is implemented unless the
[Implementation status](#implementation-status) table says so. Sections marked
**SPECIFIED** describe behaviour that does not exist yet; do not cite them as
though it does.

This is the contract by which a plugin — written in any language — tells Flyto2
what it can do, and by which an operator decides what it may do. flyto-core is
the rules; extensions live outside it; flyto-cloud is the host that adopts them.

---

## Why this exists

flyto-core discovers Python plugins through a `flyto.modules` setuptools entry
point. A module can declare `provides_capability`, and
`ModuleRegistry.capabilities()` reports what installing a package made
available. That works, and it is verified.

It is also **one binding**, not a contribution point. A plugin written in Rust,
Go or TypeScript cannot use a Python entry point at all, and plugins are
explicitly not meant to be language-restricted. This document specifies the
declaration that is language-neutral, and states plainly which parts of it the
code already enforces.

---

## What already exists, verified

Two plugin mechanisms are in the tree today. They are not the same thing and
this spec covers both.

| Mechanism | How a plugin arrives | Goes through the policy gate? |
|---|---|---|
| **In-process (Python)** | `flyto.modules` entry point → `register_all()` → `ModuleRegistry` | **Yes.** `BaseModule.run` calls `enforce_module_policy`, with the plugin the module was registered by |
| **Out-of-process (any language)** | `plugin.yaml` in the plugins directory → `PluginManager.discover_plugins()` → subprocess | **Yes**, since 2026-08-08. `RuntimeInvoker.invoke` gates before routing |

### The out-of-process path, exactly as it stands

- `core/runtime/process.py` spawns plugins with `asyncio.create_subprocess_exec`.
- `core/runtime/languages.py` carries a language table (python, node, typescript,
  deno, bun, go, rust, java, kotlin, csharp, fsharp, ruby, php, binary).
- `flyto-cloud`'s worker lifespan calls `init_plugins()`, which constructs a
  `PluginManager` and discovers plugins, so discovery and process lifecycle are
  live in the worker.
- `StepExecutor` falls through to `get_invoker().invoke(...)` for a module id the
  registry does not know.
- **`RuntimeInvoker.set_plugin_manager` has no caller anywhere.** The invoker's
  `_plugin_manager` is therefore `None`, and `_invoke_plugin` raises
  `PluginNotFoundError`. A workflow step cannot reach a plugin subprocess today.
- `enforce_module_policy` did not appear anywhere in `core/runtime/` or in the
  step executor. **Fixed 2026-08-08:** `RuntimeInvoker.invoke` now gates on the
  resolved module id before routing, so the plugin path and the legacy fallback
  are covered alike. Routing decides *which* handler runs; neither may run what
  policy denies.

The out-of-process runtime was one connection away from working and the same
connection away from being a policy bypass. It is still the first, and no longer
the second.

---

## Authority: what flyto-core can and cannot bound

Say the true thing first, because a contract that overstates its guarantees is
worse than one that has none — an operator adopts on the strength of what it
claims.

**flyto-core cannot contain a plugin that runs as its own process.** There is no
sandbox. A spawned plugin has whatever the operating system gives the user who
started flyto-core. No manifest field changes this, and any design that says
otherwise is describing a sandbox that does not exist.

What *can* be bounded, and now is:

### In-process, enforced today

`enforce_module_policy(module_id, required_permissions, plugin=...)` runs at
`BaseModule.run`, the single execution chokepoint every module passes through —
direct, recipe step, foreach item, composite sub-node, and anything reached via
`flow.invoke` / `template.invoke` / `flow.subflow`.

1. **The global module filter runs first.** `FLYTO_MODULE_DENYLIST` /
   `FLYTO_MODULE_ALLOWLIST`. A plugin cannot name itself into running
   `shell.exec`; that id is denied before anything plugin-specific is consulted.
   **The plugin dimension can only narrow.**
2. **Which plugins may run at all.** `FLYTO_PLUGIN_ALLOWLIST` (if set, only
   these) / `FLYTO_PLUGIN_DENYLIST`.
3. **Dangerous permissions are granted per plugin.** `FLYTO_PLUGIN_GRANTS`, as
   `plugin:permission` pairs. A plugin module is checked against its own grants
   only; the process-global `FLYTO_GRANTED_PERMISSIONS` **does not reach it**.

   The dangerous set is exactly five: `shell.execute`, `subprocess.execute`,
   `payment.process`, `browser.debug`, `code.execute`. A manifest naming
   anything else as dangerous is naming nothing.

   This exists because with one global grant set, a plugin that *honestly*
   declared `required_permissions: [shell.execute]` was asking the operator to
   grant it to every module in the process. Honesty must not be how a plugin
   acquires reach.
4. **Ownership is assigned, never claimed.** The registry stamps the plugin
   whose `register_all` is running and overwrites whatever the module supplied.
   The lie worth blocking is not "I am plugin B" but "I am no plugin at all",
   because the empty owner is the one the global grant still covers.

### Out-of-process — implemented

`RuntimeInvoker.invoke` calls `enforce_module_policy` on the resolved module id
before routing, passing the plugin id from the manifest and that step's declared
`required_permissions`. The three controls above therefore apply identically to
both shapes.

A refusal is returned as `{"ok": false, "error": {"code": "MODULE_POLICY_DENIED"}}`
rather than raised, because `invoke` answers with an envelope and its callers
already treat `ok: false` as a stop — so it still fails closed.

A plugin that declares no permissions, has no manifest, or whose manifest cannot
be read simply declares none: the module filter and the plugin allow/deny list
still apply, so silence cannot buy a denied module id. A manifest lookup that
raises is caught and does **not** open the gate.

### What adoption grants

**Adopting a manifest starts nothing and executes nothing.** A manifest is inert
data. The operator's separate act of installing and running the plugin is what
grants it authority — a distinction worth keeping because it is the honest one:
the authority was always the operator's, and adoption should not manufacture it.

---

## Reaching a plugin

**The manifest never names a host, a port, a path outside its bundle, an
executable, or an environment variable.**

The address is configuration, resolved by the host from the plugin's namespace:

```
FLYTO_PLUGIN_ENDPOINT__<NAMESPACE>     e.g. FLYTO_PLUGIN_ENDPOINT__VISION
FLYTO_PLUGIN_TOKEN__<NAMESPACE>
```

Derived, not declared. If a manifest could choose the variable name, publisher B
could name publisher A's variable and read A's endpoint and credential — and
every other check would pass, because nothing binds a freely-chosen suffix to
the publisher who chose it. Deriving it from the namespace, which *is* bound to
the publisher, closes that by construction.

`locality` is declared and enforced:

| Value | Meaning |
|---|---|
| `same_host` | The endpoint MUST be loopback. Refuse anything else |
| `same_network` | The endpoint MUST match `FLYTO_PLUGIN_ENDPOINT_ALLOWED_HOSTS` |

`same_host` is what "only touch hardware from the machine that has it" looks like
when it is machine-checked instead of conventional.

---

## The manifest

```yaml
# flyto-modules-vision as flyto.plugin.v1.
schema: flyto.plugin.v1

plugin:
  id: com.flyto2.vision            # reverse-DNS, immutable across versions
  namespace: vision                # every module_id must be <namespace>.<verb>
  version: 1.0.0                   # semver
  title: Flyto2 Zone Vision
  summary: Report what a fixed zone camera has already observed.
  license: Apache-2.0
  support_url: https://github.com/flytohub/flyto-modules-vision/issues
  publisher_key_id: flyto2-plugins-2026
  min_host: "2.28.0"

artifact:
  # What actually runs, bound by digest. A manifest that describes an
  # implementation it does not identify attests to a map, not to a plugin.
  kind: pypi                       # pypi | oci | archive | inprocess-python
  name: flyto-modules-vision
  version: "0.1.0"
  digest: "sha256:<wheel digest>"
  attestation: pypi-trusted-publishing   # or: sigstore | none

serve:
  binding: inprocess-python        # inprocess-python | http
  locality: same_host
  request_timeout_ms: 5000
  max_response_bytes: 262144

capabilities:
  - id: vision.observe

evidence:
  - kind: zone.overview
    produced_by: vision.observe

modules:
  - module_id: vision.observe
    provides_capability: vision.observe
    label: Observe Zone
    label_key: modules.vision.observe.label
    description: Report what the fixed camera can currently see in a zone
    category: vision
    icon: Eye
    actuates: false
    idempotent: true
    retryable: true
    timeout_ms: 30000
    required_permissions: []       # only the five dangerous ids mean anything
    params_schema:
      type: object
      additionalProperties: false  # required; an open schema is an open door
      properties:
        zone: { type: string, maxLength: 128 }
```

### Rules a validator MUST apply

- **Unknown keys are refused, naming the key.** Never silently ignored. The
  existing `plugin.yaml` reader silently drops `entry_point`, which is how a
  field can be documented, written by every plugin, and read by nothing.
- `schema` is compared before any other key is parsed.
- Every `modules[].module_id` MUST begin `<namespace>.`.
- The namespace MUST NOT be one flyto-core denies (`shell`, `process`,
  `sandbox`, `database`, `git`, `k8s`, `ssh`, `docker`, `file`, `env`, `flow`,
  `template`) nor one flyto-core ships.
- `required_permissions` accepts only the five dangerous ids. Anything else is
  refused rather than accepted-and-ignored.
- `params_schema` MUST set `additionalProperties: false`, and MUST NOT declare a
  parameter named `url`, `host`, `endpoint`, `address`, `gateway`, `command`,
  `argv`, `token` or `secret`. A host-shaped parameter is how the address rule
  gets reintroduced one plugin at a time.
- A capability MUST NOT be declared for a module that cannot perform it. The
  evidence layer matches a gap to a producer; a module claiming a capability and
  returning nothing turns "escalate to something that can do this" into
  "dispatch to something that cannot", and the mission stalls instead of
  climbing.
- `human.approval` MUST NOT be declared as produced. It is deliberately
  unschedulable: it is asked of a person, not dispatched.

---

## The wire contract

**No boolean may be absent.** Every boolean a plugin sends MUST be present.

This is not pedantry, it is the first thing that broke. `usable` decides whether
a mission counts as proven, and reading absent as true is a Python-shaped
default on a cross-language boundary. Go's most copy-pasted struct tag,
`json:"usable,omitempty"` on a bool, emits `{"kind":"zone.overview"}` for
`Usable: false` — verified by running it. Jackson's `NON_DEFAULT` does the same.
A plugin saying "I looked and the view was blocked" would have been read as
usable evidence, with nothing raising anywhere.

Every request and response body carries its own `contract_version`, not only a
header, so an author debugging with `curl` sees what they are speaking.

---

## Distribution and offline

`artifact.digest` binds the manifest to the implementation. Whatever the
transport, **the thing attested must be the thing that runs**; a bundle of
declaration alone attests to a mapping.

The existing Python exemplars publish through PyPI Trusted Publishing with SLSA
build provenance, which already signs the wheel. That is `kind: pypi` with
`attestation: pypi-trusted-publishing`, and it is recognised rather than
replaced — the work is not thrown away.

Offline: an adopted plugin's manifest, artifact and attestation MUST be
installable from a local path with no network, because the enterprise build
cannot depend on a hosted registry. A registry is where a plugin is *found*, not
where it is *verified*.

---

## Implementation status

| Part | Status |
|---|---|
| `provides_capability` + `ModuleRegistry.capabilities()` | **Implemented**, verified against a real installed plugin |
| Per-plugin grants, allow/deny, ownership stamping (in-process) | **Implemented**, 24 tests |
| Global filter runs before the plugin dimension | **Implemented** |
| Manifest schema and validator | **Not implemented** |
| `artifact.digest` verification | **Not implemented** |
| Derived endpoint/token env names | **Not implemented** |
| `locality` enforcement | **Not implemented** |
| Policy gate on the out-of-process path | **Implemented**, 7 tests |
| Registry / adoption in flyto-cloud | **Not implemented** |

## Open questions

- **Reconciling with the existing `plugin.yaml`.** `docs/PLUGIN_SDK.md`
  documents a different manifest and a 14-language table. Whether
  `flyto.plugin.v1` supersedes it, or the two coexist with a converter, is not
  decided here.
- **Per-plugin policy for out-of-process plugins** needs the plugin id to reach
  the gate; where that call belongs is a design decision, not a field.
- **Namespace allocation.** Reverse-DNS ids are self-asserted until a registry
  allocates them against `publisher_key_id`.

## Related

- [Security model](../SECURITY_MODEL.md)
- [Plugin SDK guide](../PLUGIN_SDK.md) — the existing `plugin.yaml`
- [Module specification](../MODULE_SPECIFICATION.md)
- [Register module guide](../REGISTER_MODULE_GUIDE.md)
