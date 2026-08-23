# Decisions

## 2026-08-24 - One outbound policy, whichever HTTP client is installed

Decision: every HTTP client this package constructs enforces the same SSRF
policy. `guarded_client_session` covers aiohttp; `guarded_httpx_client` covers
httpx; a test refuses any `httpx.AsyncClient(` built outside `core/utils.py`.

Why: the two were not equivalent and nothing said which one a deployment would
get. Twelve `httpx.AsyncClient` call sites sat behind `try: import httpx /
except ImportError:` with a guarded aiohttp fallback, and `httpx` was declared
in no dependency group - it arrived transitively through `openai`. So installing
an unrelated extra silently switched the package from a guarded transport to an
unguarded one, reopening the resolve-then-connect window two published
advisories were issued to close. The guard-coverage test could not see it: it
matches source references to guard symbols, and the affected modules do call
`validate_url_with_env_config`; what nothing checked was whether the socket then
went to the address that validation approved.

Consequence: httpx is an explicit dependency of the `ai` extra rather than an
inherited one, and the guarded transport pins the approved address while
preserving `Host` and SNI. Forty bare `aiohttp.ClientSession(` constructions
remain in `src`, most to fixed vendor endpoints that accept no caller-supplied
host; they are not covered by this test and are recorded as follow-up rather
than implied to be safe.

## 2026-08-24 - An operator flag widens a target, it does not remove a guard

Decision: `FLYTO_ALLOW_REMOTE_OLLAMA=true` moves `ai.local_ollama.chat` from
"loopback only" to "a host the shared outbound guard accepts". It no longer
means "no validation".

Why: the module held an outbound-guard exemption stating it was stricter than
the shared guard. That was accurate with the flag unset and false with it set -
the documented configuration for a remote Ollama - at which point a
caller-supplied `ollama_url` reached cloud metadata and RFC1918 space with the
response returned to the caller. The exemption's marker string was the text of
the error message, so the coverage test kept passing over the branch that
skipped the check entirely.

Consequence: Ollama's own port is added to the operator's port policy, and only
that port. A security change that made every real remote Ollama unreachable
would not have been a fix, it would have been a removed feature reported as one.
The exemption is deleted, so the module is now held by the ordinary rule.

## 2026-08-24 - Optional assertions stay optional in registry metadata

Decision: `http.response_assert.body_matches` uses the assertion regex editor
preset but does not declare a required value.

Reason: a parameter's editor and validation shape do not imply that every
workflow must provide it. Status-only and header-only assertions are complete
uses of the module and must not fail static template validation.

## 2026-08-24 - Explicit module failure cannot become workflow success

Decision: a legacy single-mode module result with `ok: false` raises a step
failure before it reaches workflow context. Retry and `on_error` then decide
whether to retry, stop, route to an error edge, or continue with an error value.

Reason: normalizing `ok: false` into an error-typed node result and immediately
converting it back to a plain dictionary let the workflow log and persist a
successful step. That contradicted the result contract and made notification,
network, and security failures appear complete.

## 2026-08-23 - Module label keys are a total registry contract

Decision: every registered module exposes `ui_label_key`. Explicit
`ui_label_key` and legacy `label_key` declarations remain authoritative; when
both are absent, the registry derives `modules.<module_id>.label`.

Reason: a catalog consumer should not need separate code paths for modules that
forgot translation metadata. A deterministic key lets every UI attempt the
same locale lookup and still fall back to the registry's English label when a
locale has not translated that key yet.

## 2026-08-23 - Installed Chrome is a valid browser runtime fallback

Decision: Chromium launch tries Playwright's bundled engine first and then the
supported system `chrome` and `msedge` channels only when the caller supplied
no explicit channel. Persistent and regular contexts use the same ordered
candidate list; worker mode continues to skip persistent profiles.

Reason: a missing Playwright browser cache does not mean the machine has no
browser. Telling an operator to install Chrome while an installed Chrome is
available is both incorrect and leaves browser-based templates unusable. An
explicit channel remains authoritative because silently substituting a
different browser would change a caller-controlled compatibility contract.
## 2026-08-23 - Domain solvers begin with three bounded deterministic contracts

Decision: add exactly three dependency-free baseline providers with stable IDs:
`math.rigid_transform_3d`, `physics.kinematics_constant_acceleration`, and
`chemistry.ideal_dilution`. They accept only explicit bounded units and models,
reject non-finite/boolean/ambiguous inputs, and emit one canonical receipt
schema whose SHA-256 covers canonical nested evidence only while the envelope
is validated separately. Chemistry is ideal
arithmetic only and carries no substance, compatibility, reaction, laboratory,
medical, handling, or safety authority. None of the three validates reality.

Provider semantics are declared, never inferred. A declared semantic contract
has exactly four bounded identifier-list fields and is rejected before registry
mutation when malformed. Existing providers with no semantic contract remain
valid. Capability entries keep their prior identity shape; deterministic
provider-specific contracts live in a separately hashed manifest collection.

Reason: a closed-loop planner needs a small honest executable baseline and
machine-readable evidence, but broad domain claims or label-derived routing
would make catalog prose an authority boundary. Three narrow solvers establish
the extension contract without pretending to complete mathematics, physics, or
chemistry.

## 2026-08-23 - The supported Python range is proven per version, not declared

Decision: `requires-python` is `>= 3.10`, and every version in the declared
range is installed and tested by a CI job.

Why: the previous `>= 3.9` was not a conservative floor, it was a false one.
`aiohttp>=3.14.3` — a base dependency, not an extra — requires 3.10, so a 3.9
install resolved the package and then failed with no matching distribution. The
repository carried real 3.9 accommodation around that broken claim: a
`python_version < '3.10'` starlette branch, a `setuptools<83` build branch, a
Pillow floor held at 11.3.0 and a pytest floor held at 8.4.2 specifically to
stay 3.9-compatible, and an `EntryPoint.dist` fallback in the plugin loader.
Two of those held the project on dependency lines whose newer releases carry
advisory fixes, so the false floor had a security cost, not just a tidiness one.

Consequence: 3.9 users lose nothing, because they never had a working install.
The `compat` job runs 3.10, 3.12 and 3.13 (3.11 is already covered by the main
job); a future floor change has to survive that job before it can be claimed.
The Pillow floor stays at 11.3.0 in this change and moves separately, with the
image suite run against it — the packaging edit that unblocks it is not the
change that should perform it.

## 2026-08-22 - Local workflow paths are canonicalized at CLI selection

Decision: both interactive and non-interactive local CLI selections pass
through one boundary before any workflow read or execution. The boundary
resolves the path, requires an existing regular file and accepts only `.yaml`
or `.yml`. Both execution sinks pass a direct fresh boundary result to the
runner, so a path changed or removed after its initial read fails through the
existing invalid-workflow CLI behavior. It intentionally permits valid absolute
paths and relative traversal outside the current directory; this is not a
repository-root sandbox.

Reason: canonicalizing the selected object closes ambiguous user-input flows at
the CLI sinks without changing the explicit capability to run any local
workflow the operator selected. This is defense-in-depth until evidence proves
otherwise; it does not establish remote exploitability and creates no CVE or
advisory.

Rollback and boundary: revert the helper and its two CLI call sites, the
focused regression test, and the matching CHANGELOG/STATE/DECISIONS entries.
APIs, dependencies, version, module catalog, workflow semantics/content, and
security policy are unchanged.

Implementation attribution: source declaration and line movement is planned to
regenerate, rather than hand-maintain, `docs/FEATURES.md`,
`docs/MIGRATION_STATUS.md`, `docs/WHITEPAPER.md`, `docs/reference/cli.md`,
`docs/reference/python-api.md`, and `docs/reference/source-modules.md`. Those
six generated consumers are part of this boundary change and no broader
documentation surface is attributed to it.

## 2026-08-22 - Core is Flyto2's independently usable execution layer

Decision: publish a repo-local `flyto.product-contract.v1` identifying
`flyto-core` as layer three. Core owns schema validation, deterministic
execution/replay, and evidence. `flyto-ai` owns understanding, routing, and
intent/provider governance; `flyto-blueprint` owns reusable-procedure learning
and scoring and never executes. Each package is independently usable.

Reason: one product promise and explicit package choices prevent public copy
from making Core sound like the whole product or making the package chain sound
mandatory. The wheel follows the same boundary: ship runtime packages and the
two explicitly declared worker sources, but exclude tests, dependency trees,
caches, and bytecode. Rollback is limited to the product-contract, public-copy,
memory, and packaging-rule changes from this decision.

Boundary: this changes no API, version, catalog, dependency, workflow, or
security policy. It does not repair or claim repair of the documented
out-of-process plugin/runtime wiring gaps, and it makes no adoption,
publication, CI, merge, or external-validation claim.

## 2026-08-12 - Capability policy follows the resolved handler identity

Decision: route a legacy module id first, then apply capability policy before
execution using the resolved plugin id whenever the primary or fallback route
can reach a plugin. A legacy-first route retains that plugin id in its
`RoutingResult`.

Reason: policy still precedes all execution, but it cannot precede identity
resolution. `database.scan` may execute `flyto-official/database`; querying the
manifest under `database` returns no declaration and can erase the plugin's
`required_permissions`. The module denylist remains keyed on the canonical
legacy module id, while plugin grants and manifest permissions are keyed on the
handler that can actually run. One pre-execution gate therefore covers both the
primary and its permitted fallback without duplicating policy inside handlers.

## 2026-08-11 - Extension admission is a table, and a successful install must prove itself

Decision: Core manages exactly two extension kinds — `flyto-modules-*` into
`flyto.modules`, `flyto-plugin-*` into `flyto.plugins` — declared once in
`EXTENSION_KINDS` and read by every other decision (classification, install,
entry-point proof, which refresh to run). No Core source names an individual
extension. An install is reported successful only after the installed
distribution is read back and shown to declare at least one entry point in its
kind's group; a first install that fails that proof is uninstalled again, an
upgrade that fails it is not.

Reason: three things were being conflated, and each failed differently.

*What Core is willing to install* was a single hardcoded prefix, so module packs
were unmanageable and the obvious fix — a branch per pack — would have made
every new pack a Core change. It is now data, and the same table is served to
clients at `GET /v1/extensions/kinds` so their idea of what is installable
cannot drift from the one the installer enforces.

*What a successful install means* was "pip exited 0". pip exits 0 for a
typosquat, an empty placeholder, and a package that simply forgot its
`[project.entry-points]` block. Each left the operator with a package Core would
never load and a success message saying otherwise. Proof is the only thing that
distinguishes an extension from a package with a matching name, so it is taken
before success is reported, not after the operator notices nothing appeared.

*What to do when proof fails* is not one answer. On a first install the package
is strictly new and strictly useless, so removing it returns the machine to
where it was. On an upgrade the same removal would take the working version with
it — the operator asked to move forward and would be left with nothing. Rollback
is therefore conditioned on whether the extension existed beforehand, which is
why the prior version is read before pip runs rather than inferred after.

Two constraints are load-bearing:

- A bare name is refused, never completed. `robotics` is ambiguous between
  `flyto-modules-robotics` and `flyto-plugin-robotics`; completing it would
  install a different package than the caller named. The plugin-only
  `install_plugin` keeps its historical bare-name resolution because its prefix
  is unambiguous by construction.
- `restart_required` is reported, not worked around. Python does not un-import,
  so a refresh after an upgrade updates what Core *reports* while leaving what it
  *runs* untouched. Telling the caller the truth is correct; pretending a
  hot-reload happened would make the registry and the interpreter disagree
  silently.

## 2026-08-11 - Remote extension installation needs an opt-in, not just a token

Decision: `GET /v1/extensions` and `/v1/extensions/kinds` require the bearer
token. `POST /v1/extensions/install` and `/uninstall` require the token **and**
`FLYTO_EXTENSIONS_INSTALL_ENABLED=1`. Package-manager stdout/stderr never
appears in a response; failures carry a stable code from a fixed table instead.

Reason: the token is minted automatically at startup for local clients and
authorises module execution — work bounded by module policy. Installing a
package runs its setup.py / PEP 517 backend as host code before any policy,
prefix gate or entry-point proof can apply, which is a strictly larger authority
than anything else the token opens. Treating "held the token" as consent to that
would silently widen what every existing local client is permitted to do. The
loader itself is not gated, because the CLI is a local operator acting directly;
the gate belongs to the transport that made the capability remote.

Stderr is withheld for the same reason it is useful: it names the interpreter,
the index, and — when an operator configures an authenticated mirror — the
credentials embedded in that index URL. A stable code lets a client branch
correctly without any of that crossing the boundary, and the detail stays in the
server log where the operator can already read it.

## 2026-08-11 - Discovery records what a plugin registered, not what it owns

Decision: `ModuleRegistry` keeps a per-pass record — `_pass_registered` and
`_pass_displaced` — for exactly the span of one plugin's `register_all()`, and
every decision `_load_plugin` makes reads that record rather than re-deriving
intent from ownership metadata. A pass that registered something is treated as
the plugin's whole answer; a pass that registered nothing is treated as having
said nothing at all.

Reason: ownership metadata answers "who owns this row now". Three separate
questions were being asked of it that it cannot answer, and each was wrong in a
different direction. Whether a module the plugin owns is still provided — it
looked provided, because the stale row was still there, so a plugin that dropped
a module kept it forever and kept being billed for it in `module_count`. Whether
a row the plugin owns was created by this pass or overwritten from someone else
— a failing registration stamps its own name onto whatever it displaced, so
rollback deleted flyto-core's module instead of giving it back. Whether an empty
result means "cached import, ask the record" or "this plugin provides nothing" —
indistinguishable, so a legitimately empty plugin was handed a previous pass's
modules.

Two constraints are load-bearing:

**The record spans the same window as the owner stamp.** `_pass_registered` is
installed and torn down in the same `try/finally` as `_loading_plugin`, so a
plugin that raises part-way through cannot leave either one attached to the next
plugin's registrations. `_load_plugin` holds the sets as locals, so the `finally`
can clear the class attributes while the rollback still reads what it needs.

**Replay is a repair for a cleared registry, not an override of a live one.**
The contribution record exists because a package that registers as an import
side effect can only be asked once per process, so a clear/discover cycle would
otherwise return a smaller registry than it replaced. That is the only condition
it fires under: `_cleared`, set by `clear()` and consumed by the next pass. The
condition has to be "`clear()` happened" and not "the registry is empty",
because a registry emptied deliberately — by unregistering a plugin's modules
one at a time — looks identical to a cleared one, and replaying into it would
resurrect exactly the modules somebody just removed.

Rejected: comparing registry size before and after each plugin. It is what the
original `module_count` did, and it reads 0 on every pass after the first,
because a cached import re-registers the same ids instead of adding new ones.

## 2026-08-08 - The plugin manifest is specified before it is built, and says so

Decision: `docs/specs/PLUGIN_MANIFEST_SPEC.md` states the language-neutral
plugin contract as a DRAFT, with an implementation-status table naming which of
its guarantees the code enforces today and which are intentions. Sections that
describe unbuilt behaviour are marked SPECIFIED.

Reason: three independent adversarial reviews of candidate designs each returned
a fatal finding, and the shape was the same every time — an authority model
whose gates existed in prose and not in code. Per-plugin module policy,
per-plugin permission scope and manifest-verified integrity were all written in
the present tense against a codebase that had none of them. An operator adopts a
plugin on the strength of what the contract claims, so a contract that overstates
is worse than one that promises nothing.

Three constraints fell out of those reviews and are load-bearing in the spec:

**Sign the code, not the map.** A bundle of declaration alone attests to a
mapping, not to a plugin; `artifact.digest` binds the manifest to what runs. The
existing PyPI Trusted Publishing + SLSA provenance already signs the wheel and is
recognised rather than replaced.

**The address is derived, never declared.** A manifest that names its own
endpoint and token environment variables lets one publisher name another's, and
no other check catches it because nothing binds a freely-chosen suffix to the
publisher. Deriving from the namespace, which is bound, closes it by
construction.

**No absent-means-true boolean crosses a language boundary.** Go's
`json:"usable,omitempty"` on a bool omits false, as does Jackson's NON_DEFAULT;
the field that decides whether a mission counts as proven would silently invert.

Recorded openly: `docs/PLUGIN_SDK.md` already documents a different `plugin.yaml`
and a 14-language runtime that really does spawn subprocesses. Whether
`flyto.plugin.v1` supersedes it or converts to it is an open question in the
spec rather than a decision taken here.

Also recorded, because it is the finding that most needs an owner: the
out-of-process plugin path has no `enforce_module_policy` call, and
`RuntimeInvoker.set_plugin_manager` has no caller, so a workflow step cannot
reach a plugin subprocess today. It is one wiring change from working and the
same change from being a policy bypass.

## 2026-08-14 - Plugin adoption is inert, strict, and offline

Decision: implement only the `flyto.plugin.v1` manifest/adoption boundary in
flyto-core. Every defined object is closed, input is copied into bounded JSON
data before interpretation, identities and relationships are checked exactly,
schema keywords are admitted only on compatible types, and the returned tree is
recursively key-sorted, detached, and immutable after adoption. The shared text
boundary applies the same UTF-8 and size rules to values, mapping keys,
endpoints, and endpoint allowlists. It rejects C1 controls, bidi and zero-width
formats, surrogates, private-use, unassigned/noncharacters, and line/paragraph
separators before canonicalization or unknown-key/error projection. Errors are
stable static messages that reflect no hostile text. A `same_network` allowlist is
a small explicit non-empty list or tuple of unique bounded ASCII host
authorities, validated before matching without DNS. Artifact proof reads an
already-local regular file through one nofollow descriptor with a size bound
that callers cannot raise above the hard cap and exact SHA-256 comparison. A
platform without `O_NOFOLLOW` uses `lstat`/descriptor identity comparison and
still reads only the opened descriptor. Endpoint and token environment names are derived
only from the validated namespace; endpoint locality uses literal loopback or
an explicit host allowlist and performs no DNS lookup. Endpoint and allowlist
validation precedes artifact access, so rejected configuration opens no file.

The set of IDs already adopted by the host crosses the same hostile caller
boundary. It is accepted only as an exact built-in list or tuple with at most
256 unique, bounded, control-free ASCII reverse-DNS plugin IDs. Validation
precedes membership; mappings, generators, custom sequences, and other
arbitrary iterables are rejected without iteration or materialization. Every
failure of that argument uses one stable message that reflects no element.

Adoption does not download, install, load, start, or execute a plugin. It does
not connect this contract to the legacy runtime and does not claim operating
system sandboxing. Those lifecycle and containment questions remain separate.
This supersedes only the 2026-08-08 decision's draft status, not its authority
analysis or warning about the unconnected runtime.

## 2026-08-08 - Policy has a plugin dimension, and it can only narrow

Decision: `enforce_module_policy` takes the plugin a module arrived from, and
three environment variables scope policy to it — `FLYTO_PLUGIN_GRANTS`
(`plugin:permission` pairs), `FLYTO_PLUGIN_DENYLIST`, `FLYTO_PLUGIN_ALLOWLIST`.
A plugin module is checked against its own grants only; the process-global
`FLYTO_GRANTED_PERMISSIONS` does not reach it. The global module filter runs
first, so the plugin dimension can never widen what a plugin may run.

Reason: with one global grant set, a plugin that *honestly* declared
`required_permissions: [shell.execute]` was asking the operator to grant
shell.execute to every module in the process — flyto-core's own and every other
plugin's. Declaring a permission is how a plugin tells the truth about itself,
and it must not be how it acquires reach. An operator who granted shell.execute
so flyto-core could run a build step has not granted it to everything they
install afterwards.

Ownership is assigned, never claimed. The registry stamps the plugin whose
`register_all` is running into the module's metadata and overwrites whatever the
module supplied. The lie worth blocking is not "I am plugin B" but "I am no
plugin at all", because the empty owner is the one the global grant still
covers — so a module registered during a plugin load that supplies
`plugin: ""` is corrected to the loading plugin, and a module registered with no
metadata at all is given the minimum needed to stay attributable rather than
defaulting to first-party.

The marker is cleared in `finally`, so a plugin that raises part-way through
registration cannot leave its name attached to the next plugin's modules.

Scope: this bounds what a plugin's modules may do *inside this process*. It does
not bound a plugin that runs as its own process — nothing here can, and a design
that claims otherwise is describing a sandbox flyto-core does not have.

## 2026-08-08 - A module may declare the capability it provides

Decision: `register_module` accepts `provides_capability`, a single capability
id in the vocabulary a Flyto2 Space uses to bind work to resources. It is stored
in module metadata and read back through `ModuleRegistry.capabilities()`, which
returns `{capability: [module_id, ...]}`. It is optional, defaults to empty, and
almost every module leaves it unset.

Reason: this is the plugin contribution point, read side. Before it, installing
a package added a step to the builder but told the host nothing — a Space's
evidence layer could not learn that a capability had become available until an
operator hand-typed its name into a command somewhere else. "Install the plugin
and the loop can use it" was not expressible.

A capability with several providers is returned whole rather than resolved here.
Which provider runs is a binding decision the host makes with the resources it
has; discarding one would be this registry deciding something it cannot know.

Scope, stated because it is easy to over-read: this serves plugins that arrive
through the Python `flyto.modules` entry point. It is one binding, not the
ecosystem's contribution point — a plugin written in another language cannot use
it at all, and the language-neutral manifest that would serve those is a
separate, unbuilt contract.

`build_module_metadata` takes the new field last and with a default, so callers
outside this repository keep working unchanged.

## 2026-08-08 - Sandbox guard coverage is a CI property, not an author's habit

Decision: every module that declares a path-shaped parameter must route it
through `validate_path_with_env_config`, and
`tests/core/test_write_sink_coverage.py` walks the registry to enforce that on
every run. A parameter may be exempted only by an entry in
`NON_FILESYSTEM_PARAMS` stating what the value actually addresses — a JSONPath,
a URL segment, a remote host path — and the exemption is void the moment the
module's source contains a filesystem call.

Reason: the guard was already centralized and already correct. Every published
arbitrary file read/write advisory against this project
(GHSA-2956-977x-2w3r, GHSA-p34x-fmph-9fjx, GHSA-xchh-cp84-9838,
GHSA-hmq9-xw4w-7ppc, GHSA-wc94-386q-5478, GHSA-p64w-hgfm-824v) is the same
defect: a module that did not call it. Fixing them one report at a time never
converged, because each wave patched the modules that had been named and left
the ones that had not — GHSA-p64w explicitly notes the prior waves missed
`browser.download`. Centralization without a coverage check only moves the
failure from "the guard is wrong" to "the guard was not called", which is
harder to see and just as exploitable. A registry-wide audit at the time this
decision was made found 13 further unguarded modules that no one had reported.

Consequence: adding a module with a path parameter now forces one of two
explicit acts — call the guard, or write down why the parameter is not a path.
Neither can be skipped silently. The cost is that the default sandbox
(the process working directory) is now actually enforced on modules that
previously ignored it, which is a breaking change for callers that passed
absolute paths outside it; `FLYTO_SANDBOX_DIR` is the supported way to widen it.

## 2026-08-08 - The outbound boundary is a host check, not only a URL check

Decision: `core/utils.py` owns three outbound guards, not one.
`enforce_outbound_url` keeps the http(s) path; `enforce_outbound_service_url`
parses the host out of a non-HTTP endpoint (`redis://`, `ws://`, a proxy URL);
`enforce_outbound_host` guards a bare hostname for raw TCP. All three share one
policy — loopback allowed, `FLYTO_ALLOWED_HOSTS` allowed,
`FLYTO_ALLOW_PRIVATE_NETWORK` allowed, otherwise resolve and reject private,
link-local, metadata, or unresolvable — and one resolver, `resolve_guard_ip`,
promoted out of `port.check`. `tests/core/test_outbound_guard_coverage.py`
enforces that every module with a network-shaped parameter reaches one of them.

Reason: `validate_url_ssrf` only understands http(s), so every module that took
a bare host or a `redis://` endpoint had no guard available to call. That is
why the gap was structural rather than careless: Redis, MySQL, SMTP, SSH, the
CDP endpoint, the browser proxy and the network probes were reaching arbitrary
internal addresses with no shared primitive to reach for, and `port.check` had
quietly grown the only correct host resolver in the codebase — the one whose
IPv6 fail-open was GHSA-v7q9-pr72-5fmv. A guard nobody can call is not a
boundary.

Decision: loopback stays allowed for infrastructure connections. Reason:
self-hosted deployments legitimately point Redis, MySQL and SMTP at
`localhost`, and blocking that breaks real operation without closing any path —
a workflow that can reach loopback can already do so through the module's own
default configuration. The attack this bounds is reaching *elsewhere* on the
private network, above all the cloud metadata endpoint.

Consequence: workflows that deliberately target a private host now need
`FLYTO_ALLOWED_HOSTS` or `FLYTO_ALLOW_PRIVATE_NETWORK=true`. Unresolvable hosts
are refused rather than attempted, which is a behaviour change for callers that
relied on a connection error to probe DNS. The coverage test is MRO-aware
because guards are legitimately inherited (`LLMClientMixin` holds the
`ollama_url` guard for `agent.chain` and `agent.autonomous`); a same-file scan
would report those as unguarded and train readers to ignore the test.

## 2026-08-02 - Plugin IDs select discovered directories; they never construct paths

Decision: `PluginManager` records the resolved directory associated with each
validated manifest during discovery. A later `load_plugin(plugin_id)` request
validates the external identifier and uses it only as a dictionary key; it no
longer joins the request value, or naming variants derived from it, onto the
plugin root. Discovery also rejects directory symlinks that resolve outside the
configured root.

Reason: a manifest ID and its physical directory name are separate identities.
Constructing candidate paths from a route parameter unnecessarily coupled them
and left filesystem probes dependent on external input, even though manifest
validation blocked common traversal strings. The discovery map both preserves
namespaced IDs whose directory names differ and gives the runtime a simple
invariant: every path used by language detection and entry-point validation was
enumerated and confined before any load request selected it.

Decision: MCP header decoder exceptions are server-side details. The HTTP
transport returns one fixed `invalid Mcp-Name header encoding` message rather
than reflecting `str(exc)` into a JSON-RPC response.

Reason: current decoder errors are intentionally generic, but keeping exception
text on a remote response path makes that safety depend on every future decoder
implementation. A stable protocol message preserves diagnostics semantics
without exposing paths, parser internals, or chained exception data.

## 2026-07-25 - reverse.deobfuscate (Phase 4): own Node.js subprocess, not the generic plugin runtime; webcrack only, not restringer; new code.execute permission

Decision (delivery mechanism): `reverse.deobfuscate` manages its own Node.js
subprocess directly (`asyncio.create_subprocess_exec('node', worker.mjs, ...)`
in the module's `execute()`) rather than going through the existing polyglot
JSON-RPC plugin runtime (`src/core/runtime/manager.py`/`process.py`/
`languages.py`, documented in `docs/PLUGIN_SDK.md`), even though that system
already declares a `node` language config.

Reason: investigation before writing any code found the generic plugin
runtime unfinished in ways that matter here. `ProcessConfig`'s declared
`max_memory_mb`/`max_cpu_percent` are never enforced anywhere. An `invoke()`
timeout (`process.py`) raises `PluginTimeoutError` but never kills the
subprocess — the abandoned process keeps running. Restart backoff is
declared but unused. Most importantly, a `plugin.yaml` manifest's `modules:`
list is never wired into `ModuleRegistry` — there is no code path that turns
a plugin manifest into a callable module today, and no example `plugin.yaml`
exists anywhere in this repo. Building "the strongest" implementation of a
security-sensitive, code-executing feature on top of that would either
inherit those gaps silently or require first fixing shared plugin
infrastructure with a much larger blast radius than one new module. A
dedicated, self-contained subprocess call is simpler, fully reviewable in one
module, and explicitly fixes the exact "no kill on timeout" gap found in
`process.py` — `reverse.deobfuscate`'s own timeout path calls `proc.kill()`
and awaits `proc.wait()` before raising, unlike the shared runtime.

Decision (Node.js requirement): require a system-installed Node.js 22 or 24
on `PATH`, plus a one-time `npm install` in the sidecar worker directory
(`src/core/modules/atomic/reverse/deobfuscate_worker/`) — the same BYO-runtime
tradeoff the existing plugin `node` language config already makes, and the
same shape of tradeoff `reverse.code`'s `jsast` pip extra makes (clear error
if missing, not auto-installed).

Reason: this repo has no reliable, working Node.js auto-bundling mechanism.
Playwright's bundled Node is reachable only via the private, undocumented
`playwright._impl._driver`, already known to be fragile under PyInstaller
(`src/core/browser/driver.py`'s `_find_external_node()` exists specifically
to work around it). The `~/.flyto/node/` fallback referenced by
`driver.py`'s `_NODE_VERSION` constant has no downloader implemented
anywhere — dead code, not a working mechanism (confirmed by search across
the repo). Building that downloader is a separate, large, not-yet-scoped
project (`tasks.md`), and bundling it into this change would repeat the same
scope-creep this repo's own Phase 3 decision explicitly avoided. Requiring a
system Node.js delivers Phase 4's functional goal now without taking on that
unsolved dependency — Node.js 22/24 is also webcrack's own stated
requirement (even-numbered releases only, since its `isolated-vm` dependency
warns against non-LTS/odd-numbered Node ABI breakage), not an arbitrary
choice made here.

Decision (engine: webcrack only, not restringer, in this first version):
use `webcrack` (npm, published directly by its author `j4k0xb`) as the sole
deobfuscation engine. Do not add `restringer` in this version, despite it
being part of the original plan approved with the user.

Reason: verifying both packages directly (not just trusting search-summary
descriptions) before implementing found two things that changed the plan.
First, the npm-published `restringer` package (`2.2.0`) is maintained by
`ctrl_esc`/`ctrl-escp/restringer`, a 23-star fork — not the canonical,
598-star `HumanSecurity/restringer`. The fork's published `package.json` has
dropped `isolated-vm` as a dependency, while the canonical GitHub repo's
`package.json` still declares it — an unresolved, unexplained discrepancy in
exactly the dependency the whole "safe dynamic evaluation" story rests on,
not something to build a security-relevant feature on without further
verification. Second, reading `webcrack`'s own source
(`deobfuscate/vm.ts`, `createNodeSandbox()`) showed it unconditionally uses
its own `isolated-vm`-backed sandbox (10s per-eval timeout, isolate disposed
after use) as a normal part of every run — there is no "pure zero-execution"
mode when using webcrack at all, which invalidated the original plan's
safe/full mode split (safe was assumed to mean "webcrack only, zero
execution"; that assumption was wrong). webcrack alone already covers
string-array decoding, control-flow-flattening reversal, self-defending/
debug-protection bypass, and webpack/browserify unpacking — restringer's
40+ modules would be a genuine deeper pass, but not required to deliver
Phase 4's stated goal. Adding it later, once its npm situation is resolved
or it's vendored from the canonical repo at a pinned commit, is tracked in
`tasks.md` rather than blocking this change.

Decision (permission): gate the whole module behind one new deny-by-default
permission, `code.execute` (added to `module_policy.py`'s
`_DANGEROUS_PERMISSIONS`), rather than trying to make part of the module
permission-free the way `reverse.code`/`reverse.sourcemap` are.

Reason: confirmed with the user directly, and now on firmer ground than
originally planned — since webcrack itself always executes sandboxed code
(see above), there was never going to be a genuinely zero-execution mode to
carve out an exemption for, unlike `reverse.code`'s pure AST parsing (which
DECISIONS.md's Phase 3 entry below explicitly says "has no elevated
capability to gate"). One permission covering the whole module is simpler to
reason about and review than a per-call conditional gate would have been.

Decision (packaging): ship the worker's `package.json`/`package-lock.json`/
`worker.mjs` (not `node_modules`) as package data for the
`core.modules.atomic.reverse` package (`pyproject.toml`
`[tool.setuptools.package-data]`, `MANIFEST.in`), so a `pip install
flyto-core` still gets the worker source even though `npm install` remains a
separate, required, manual step.

Reason: the repo's package layout (`package-dir = {"" = "src"}`,
`[tool.setuptools.packages.find] where = ["src"]`) only ships what's under
`src/` by default, and the sidecar needs its own directory (not the root
`package.json`, which is explicitly scoped `flyto2-core-test-runtime` for
jsdom browser-contract tests only — conflating a production runtime
dependency with a test-only manifest would be confusing and wrong). Placing
the worker under `src/core/modules/atomic/reverse/deobfuscate_worker/`
keeps it shippable via ordinary Python packaging with two small, explicit
additions rather than a new packaging mechanism.

## 2026-07-25 - reverse.request_breakpoint reuses the Debugger pause pipeline; reverse.attach gains session-snapshot reuse

Decision (request breakpoint): implement request-level breakpoints via CDP's
`DOMDebugger.setXHRBreakpoint`/`removeXHRBreakpoint` — the same mechanism
Chrome DevTools' Sources > XHR/Fetch Breakpoints panel uses — rather than
building a second, Fetch-domain-based interception/pause/continue pipeline.
`ReverseSession` tracks active request breakpoints in a new
`_request_breakpoints` dict keyed by the URL substring itself (CDP has no
separate breakpoint-id concept here, unlike script breakpoints; setting the
same URL twice is idempotent).

Reason: a request breakpoint's *pause* is just another `Debugger.paused`
event (`reason: "XHR"`), which `ReverseSession._on_paused`/`_paused_event`
already handles — so `reverse.wait_paused`, `reverse.resume`,
`reverse.get_call_frames`, and `reverse.evaluate_on_call_frame` all work
against a request-breakpoint pause with zero changes. A Fetch-domain
interception design would have needed its own pause/continue/fail/fulfill
state machine parallel to the existing one, duplicating exactly the
cross-process-scoping and CDP-freeze concerns already documented below for
script breakpoints, for no behavioral gain. `_enrich_pause` now also passes
through CDP's `data` field unfiltered (reason-specific detail, e.g. the
matched URL for an `"XHR"` pause) since its shape varies by pause reason and
guessing at field names across reasons risks silently returning a wrong key.
Verified against a real Chromium instance: setting a breakpoint on `ping.json`,
triggering `fetch('/ping.json')`, and observing `reason == "XHR"` in the pause
result (`tests/modules/test_reverse_modules.py::TestReverseSubPhaseF`).

Decision (session-snapshot reuse): `reverse.attach` now checks whether
`context['reverse_session']` is already enabled and attached to the exact
same page object (`existing.page is browser.real_page`) before deciding to
detach; if so, it returns that session's existing snapshot (script cache,
script/request breakpoint counts, hook count, pause/network-enabled state)
instead of detaching and calling `ReverseSession.enable()` again. A new
`force_new` param (default `False`) opts back into the old unconditional
detach-and-recreate behavior.

Reason: before this, calling `reverse.attach` a second time on the same page
— e.g. a recipe defensively re-attaching without knowing whether a debugger
session was already live — silently discarded every breakpoint, request
breakpoint, and installed hook, and forced Chrome to re-send the full
`Debugger.scriptParsed` backfill for no reason. Comparing the CDP session's
page object directly (rather than, say, comparing URLs) avoids a false-positive
reuse across a same-URL navigation that actually tore down and recreated the
underlying page. If `browser.real_page` differs (navigated to a new page/tab)
or no session exists yet, behavior is unchanged — detach the stale session
(best-effort) and create a fresh one. Verified against a real Chromium
instance: setting a script breakpoint, reattaching without detaching, and
confirming the breakpoint is still present and the session object identity is
unchanged (`tests/modules/test_reverse_modules.py::TestReverseSessionReuse`).

Both additions strengthen Phase 1 rather than opening a new phase — no new
permission, no new transport wiring (the existing `is_reverse =
module_id.startswith("reverse.")` checks in `mcp_handler.py` and
`api/routes/modules.py` already cover the new module id by prefix).
Reconciled the generated catalog to 467 modules across 85 categories.

## 2026-07-25 - reverse.hook rewritten on Object.defineProperty; session idle-timeout reaper added

Decision (hook redesign): `reverse.hook`'s injected JS (`_HOOK_SCRIPT_TEMPLATE`
in `src/core/browser/reverse_session.py`) now traps the target property with
a single `Object.defineProperty(parent, key, {get, set})` accessor instead of
directly overwriting `parent[key]` once at install time.

Reason: the previous one-shot overwrite had two known gaps — a property the
page assigns *after* the init script runs was never wrapped (nothing existed
yet to overwrite), and a page reassigning an already-hooked property silently
clobbered the hook, ending recording with no error. The accessor closes both
gaps at once: the `set` trap re-wraps whatever value gets assigned (including
the first-ever assignment of a not-yet-defined property), and the `get` trap
always returns the current wrapped version. Verified empirically with a
Playwright scratch script across 4 scenarios (hook-before-define, hook survives
reassignment, hooking an existing built-in like `Math.max`, and reload
persistence) before touching the real module, per this codebase's established
"verify empirically first" discipline. `defineProperty` throwing (some
built-ins are non-configurable) falls back to the old one-time direct wrap —
narrower, but not a regression, since that path never worked with reassignment
anyway. Remaining known limitation: a path whose *immediate parent* object
does not exist yet at document-start (e.g. `myNamespace.fn` where
`myNamespace` itself is lazily created later) still cannot be trapped — the
common cases (`window.X`, existing built-in namespaces) are unaffected. No
Python-level API change — `install_hook`/`remove_hook`/`list_hooks`/
`get_hook_records` and `reverse.hook`'s params/output schema are untouched.

Decision (session reaper): added `src/core/session_reaper.py`, a shared
idle-timeout sweep wired identically into all three transports (STDIO
`mcp_server.py`, HTTP MCP `api/routes/mcp.py`, plain REST
`api/routes/modules.py`) plus the HTTP server's `lifespan` (`api/server.py`).
It reaps both `browser_sessions` and `debugger_sessions` uniformly — closing
or detaching, then removing from the relevant dict and from the shared
`session_activity` timestamp map.

Reason: before this, a session was only ever cleaned up by an explicit
`browser.close`/`reverse.detach` call, or (STDIO only) on process EOF. A
session abandoned mid-workflow — client crash, disconnect, forgotten cleanup
— leaked a live Chromium process and/or CDP session for the server's entire
lifetime. This applied to `browser_sessions` too (it never had a reaper
either), so both are swept the same way rather than fixing only the newer
`debugger_sessions` as a half-measure. Default timeout is 30 minutes
(`FLYTO_SESSION_IDLE_TIMEOUT_S` env override), generous enough that a human
actively debugging — including long pauses at a breakpoint while thinking —
is unlikely to trip it; this is an intentional, documented tradeoff, not a
bug. A session with **no** entry in `session_activity` is deliberately left
alone rather than treated as stale — absence of activity data is not evidence
of staleness, and protects any session minted by a code path that (for now
or forever) doesn't call `touch_session`. This also fixed a small pre-existing
gap noticed while wiring the HTTP server's shutdown path: it previously closed
`browser_sessions` on shutdown but never detached `debugger_sessions`.

Both items leave the accepted architectural constraints from earlier phases
in place: sessions are still process-local (not shared across server
instances or restarts — unchanged since Phase 1, mirrors `browser_sessions`'
pre-existing design) and Phase 4 (real semantic deobfuscation) remains
blocked on Node.js infrastructure that doesn't exist in this codebase yet
(see the `reverse.code` decision below).

## 2026-07-25 - reverse.sourcemap hand-rolls VLQ decoding and never fetches anything itself

Decision: `reverse.sourcemap` implements its own Source Map v3 base64-VLQ
decoder and mapping-segment parser (`src/core/modules/atomic/reverse/sourcemap.py`)
rather than depending on a pip package, and never performs an HTTP fetch —
it only accepts the source map JSON (or a `data:` URI) as a plain parameter.

Reason (no dependency): the one plausible candidate, the `sourcemap` package
on PyPI, has an active GitHub repo but its last **PyPI** release is 2017 —
installing it would pull 8-year-old code. The Source Map v3 spec is small
and has been stable for a decade, so hand-rolling the decoder (~150 LOC) was
judged lower-risk than a stale dependency, consistent with `reverse.code`'s
same reasoning for choosing actively-maintained `tree-sitter`/`jsbeautifier`
over alternatives. The decoder was verified against hand-computed VLQ test
vectors (round-tripping an independent encoder through the decoder across
positive/negative/multi-continuation values, plus a full mappings string
with known per-segment deltas) before writing `tests/modules/test_reverse_sourcemap.py`,
the same "verify empirically first" discipline used for Phase 1's CDP
line-number semantics and Phase 2's hook/network/WebSocket mechanics.

Reason (no fetch): `Debugger.scriptParsed`'s `sourceMapURL` field was already
captured by `ReverseSession` and already exposed by `reverse.scripts`
(action=list) — no changes needed there. When `sourceMapURL` points to an
external `.map` file (not an inline `data:` URI), fetching it is a security-
sensitive operation: `http.get` (`src/core/modules/atomic/http/get.py`)
explicitly wires SSRF protection (`validate_url_with_env_config`,
`guarded_aiohttp_request` from `src/core/utils.py`) into every request,
including redirect-hop revalidation. That protection is not ambient — a new
module fetching a URL itself would need to reuse those same helpers
correctly or risk bypassing SSRF guarding entirely. Since the fetch is a
single already-solved step (`http.get`), `reverse.sourcemap` takes the
already-fetched (or already-decoded) text as input instead of duplicating
that security-sensitive code, keeping the module itself session-independent
and permission-free, matching `reverse.code`'s precedent exactly.

## 2026-07-25 - reverse.code (Phase 3) is pure Python, no Node.js, and no permission gate

Decision: `reverse.code`'s beautify/list_functions/list_strings/find_calls
actions are built entirely on `tree-sitter` + `tree-sitter-javascript` (AST
parsing/querying) and `jsbeautifier` (reformatting) — all pure-Python,
prebuilt-wheel pip packages added as a new optional `jsast` extra. No Node.js
subprocess is involved anywhere in this module.

Reason: research into a Node.js-based route (needed for real AST tooling
like `@babel/parser`/`acorn`/`terser`) found the cross-platform Node
invocation problem is not currently solved in this codebase. Playwright's
bundled Node binary is reachable only via `playwright._impl._driver`, a
private module with no compatibility guarantee — and this exact binary is
already known to be unreliable (`src/core/browser/driver.py`'s
`_find_external_node()` exists specifically to work around it crashing
under PyInstaller `--onefile`). The apparent fallback, `~/.flyto/node/`
(referenced by a `_NODE_VERSION` constant in `driver.py`), turned out to
have no downloader anywhere in the repo — it's dead code, not a working
auto-install mechanism. `sandbox.execute_js` was also considered and
rejected as an internal primitive: it's denylisted by default and only
exposes stdout/stderr/exit_code, no structured-output channel. Building
reliable Node infrastructure is its own project, not something to bundle
into this module's scope.

Decision: `reverse.code` declares `required_permissions=[]` — the only
`reverse.*` module with no permission gate.

Reason: every other module in this category is gated behind `browser.debug`
because it reads live in-memory browser state (locals, closures, hook
records, captured network/WebSocket traffic) or freezes the page.
`reverse.code` operates on a plain JS source string passed as a parameter —
it never creates or touches a CDP session, never touches a live page, and
never executes the JS it analyzes (tree-sitter only parses syntax structure;
jsbeautifier only reformats text). There is no elevated capability to gate.

Decision: real semantic deobfuscation (control-flow-flattening reversal,
string-array decoding via constant folding) is explicitly out of scope for
`reverse.code` and deferred to a separate, not-yet-started Phase 4.

Reason: those transforms require actually executing/evaluating JS
(Babel/webcrack-style passes), which pure-Python AST tools cannot do, and
which depends on solving the Node-invocation reliability problem above
first. Scoping `reverse.code` to beautify + structural search (functions,
strings, call sites) delivers real value now without taking on that
unsolved infrastructure dependency.

## 2026-07-25 - reverse.* Phase 2 extends ReverseSession instead of a second session type

Decision: `reverse.hook`, `reverse.network`, and `reverse.websocket` (function
hooking, network-initiator tracing, WebSocket capture) all operate on the same
`ReverseSession`/CDP session that `reverse.attach` already creates, rather
than opening a parallel CDP session or session registry for Network/Page
domain work.

Reason: two independent arguments point the same way. First, Chrome only
populates `Network.requestWillBeSent`'s `initiator.stack` with full JS call
frames when the Debugger agent is active — `ReverseSession.enable()` already
calls `Debugger.enable` unconditionally, so a shared session gets rich
initiator stacks for free, while a standalone Network-only session would get
poorer data. Second, `mcp_handler.py`'s `is_reverse = module_id.startswith("reverse.")`
check and the existing `debugger_session` registry (wired across STDIO MCP,
HTTP MCP, and plain REST in Phase 1) already generically cover any new
`reverse.*` module id — extending the one session type meant Phase 2 needed
zero new transport-wiring changes.

Decision: `reverse.hook` wraps a function that already exists at the time
`install_hook()` runs — a built-in available from document start (e.g.
`window.fetch`, `window.Math.max`) or a page-defined function installed after
the page has already loaded it. It does not implement an
`Object.defineProperty`-based lazy-hook guard for a property a page assigns
*after* our init script runs, and it does not defend against the page later
reassigning the same property out from under an installed hook.

Reason: a fully general lazy-hook (trapping assignment of a not-yet-defined,
possibly-deeply-nested property, and re-trapping after reassignment) is
substantially more complex than direct wrapping, and the direct-wrap approach
already covers the two most common real cases (hooking built-in browser APIs,
and hooking an already-loaded page function after navigation). Documenting
the limitation keeps Phase 2's scope matched to its actual engineering cost;
a lazy-hook guard can be added later as a targeted enhancement if a concrete
use case needs it, without changing `reverse.hook`'s params_schema or the
CDP-level mechanism (`Page.addScriptToEvaluateOnNewDocument` /
`Page.removeScriptToEvaluateOnNewDocument`).

## 2026-07-25 - reverse.* CDP debugger uses a dedicated pause/resume primitive, not BreakpointManager

Decision: `ReverseSession` (src/core/browser/reverse_session.py) owns its own
`asyncio.Event` + last-pause-state dict for pause/resume, mirroring the
existing `browser.dialog` pattern (register a page/CDP event listener, block on
an asyncio primitive with a timeout, clean up in `finally`). It does not reuse
`src/core/engine/breakpoints/manager.py`'s `BreakpointManager`.

Reason: `BreakpointManager` is built for human-approval breakpoints with
pluggable stores (in-memory/Redis/HTTP) so a resolution can reach a different
worker process than the one that created the request. That cross-process value
is moot for a CDP debugger session — the live `CDPSession` object only exists
in the process that called `reverse.attach`, so no other process could ever act
on a pause anyway. A dedicated primitive is simpler and keeps the two
breakpoint concepts (human-approval gates vs. JS execution pauses) from
bleeding into each other's data models. This also means `reverse.*` session
state is process-local, exactly like `browser.*` session state (see STATE.md).

## 2026-07-25 - A paused CDP debugger freezes the page; workflow authors must design around it

Decision: document, rather than engineer around, the fact that while a page is
paused at a `reverse.*` breakpoint, the browser freezes that page's
JS/renderer. Any other `browser.*` step issued against the same page before
`reverse.resume` will block until its own timeout, since Chrome will not
service a generic `Runtime.evaluate`-based call while the isolate is paused
(only `reverse.evaluate_on_call_frame`, which uses
`Debugger.evaluateOnCallFrame`, can execute during a pause, and only in the
scope of the paused call frame).

Reason: this is expected CDP semantics, not a flyto-core bug — trying to make
other browser steps "just work" during a pause would require either a fake
queuing layer or silently no-oping calls, both of which would hide real state
from workflow authors. Recipes that use `reverse.*` breakpoints must trigger
the paused code path without awaiting it (fire-and-forget), call
`reverse.wait_paused`, inspect/resume, and only then issue further `browser.*`
steps against that page.

## 2026-07-22 - Documentation is source-backed and release-controlled

Decision: keep concise narrative guides for intent and operations, generate
exhaustive references from Python AST/runtime catalog/repository assets, map
every maintained source/configuration area to documentation, and reject drift,
broken local links, unowned files, stale Flyto2 naming, or unapproved public
mailboxes in CI.

Reason: hand-maintained totals and symbol lists become stale in a 452-module
runtime. Generated inventory proves coverage while narrative docs remain usable.

## 2026-07-22 - Evidence-bearing workflow reads require authentication

Decision: require the active Execution API bearer token for workflow status and
evidence GET routes, not only workflow mutation and replay routes.

Reason: status and evidence can disclose workflow parameters, outputs, errors,
and artifact paths. They are operational data, not public module metadata.

## 2026-07-22 - Optional capability dependencies use explicit extras

Decision: publish `crypto`, `dns`, and `ai` extras, include their dependencies
in contributor validation, and return package-extra install instructions when
a module cannot load its SDK.

Reason: runtime discovery may expose optional modules, but installation and
failure behavior must still be predictable without bloating the base package.

## 2026-07-21 - Runtime identity and test security state are process-safe

Decision: import the installed Python package only as `core`, reject legacy
`src.core` imports, and permit private-network or auth exceptions only through
fixtures that restore process state. Test helpers that load external modules
must sandbox `sys.modules` instead of modifying imported frameworks.

Reason: duplicate package identities and collection-time environment changes
made auth and SSRF controls depend on test order. A security gate must fail
closed under the complete suite, not only when a test runs alone.

## 2026-07-21 - Coverage measures the control kernel

Decision: retain the 60% line gate for the orchestration and security-control
kernel. Atomic modules, third-party adapters, enterprise overlays, test-runtime
packages, and optional plugin implementations use catalog, schema, contract,
and real integration gates and do not dilute the kernel percentage.

Reason: one aggregate percentage across the control plane and hundreds of
independently deployable adapters was permanently red while hiding which
boundary lacked evidence. The split keeps the kernel threshold enforceable
without skipping adapter tests or lowering the threshold.

## 2026-06-23 - Warroom verification is deterministic first

Decision: Warroom pass/fail decisions come from replayable program evidence:
site/action/API/state graphs, module assertions, screenshots, DOM evidence, and
redacted reports. LLM review is opt-in and advisory only.

Reason: Flyto2 Warroom must work as a verification instrument, not a prompt
wrapper. LLM output cannot make a failing deterministic gate pass by itself.

## 2026-06-21 - Project memory is release-controlled

Decision: keep root project memory files, workflow docs, and handoff registry in
the repository and validate them in CI.

Reason: flyto-core is used to prove product loops. Its own workflow expectations
must be durable, visible, and checked.

## 2026-06-21 - Recipes are product contracts

Decision: maintained recipes should represent executable contracts for product
flows and release smoke, not only demos.

Reason: Flyto2 needs closed-loop verification from UI and API behavior back to
backend state, evidence, and release readiness.
