# Capability Contract — `flyto.capability-contract.v1`

A capability provider — a device driver, a lift controller, an ERP connector,
a camera, any installed package — plugs into Flyto2 with one thing: a
`@register_module(...)` call that names the capability it provides and carries
a **capability contract**. The contract says, as data, what the capability does
to the world, how risky it is, and what evidence proves it worked. A host
(Flyto2 Cloud, Desktop, or any other runtime) reads the contract from the
registry and enforces and verifies it generically, so the host contains no
provider-specific code.

Implementation: [`src/core/capability_contract.py`](../src/core/capability_contract.py)
(`validate_contract`, `judge`, `wrap_angle`; `MEASURE_OPS`, `ABSOLUTE_OPS`). Registration wiring:
[`decorators.py`](../src/core/modules/registry/decorators.py),
[`metadata.py`](../src/core/modules/registry/metadata.py),
[`core.py`](../src/core/modules/registry/core.py) (`ModuleRegistry.register`).

## Declaring a contract

```python
@register_module(
    module_id="lift.move_to_floor",
    provides_capability="lift.move_to_floor",
    params_schema={
        "floor": {"type": "integer", "min": 0, "max": 40, "required": True},
    },
    contract={
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "effects": ["lift.floor-changed"],
        "requires": ["lift.doors-closed"],
        "evidence": [...],
    },
    can_receive_from=["*"],
    can_connect_to=["*"],
)
```

`contract` is optional. A module without one behaves exactly as before, and its
metadata has no `contract` key. Declaring `contract` requires
`provides_capability`.

## Schema

The key set is closed at every level: an unknown key is an error, not ignored.

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `schema` | string | no | If present, must be `flyto.capability-contract.v1`. Always present after validation. |
| `actuates` | bool | yes | The capability changes the physical or external world. |
| `safety_class` | string | yes | `read_only`, `controlled`, `movement` or `dangerous`. `read_only` with `actuates: true` is rejected. |
| `requires_safe_stop` | bool | yes | The host must be able to issue a safe stop while this runs. |
| `cancellable` | bool | yes | The call can be cancelled once started. |
| `idempotent` | bool | yes | A retry with the same call id never repeats the effect. |
| `effects` | list of identifiers | no (default `[]`) | 0..16 effect identifiers, no duplicates. |
| `requires` | list of identifiers | no (default `[]`) | 0..16 precondition identifiers, no duplicates. |
| `evidence` | list of evidence specs | no (default `[]`) | 0..8 evidence specs, below. |
| `role` | string | no (2.36.0) | `safe_stop`: this capability stops the resource. See [Optional keys](#optional-keys-2360). |
| `artifacts` | list | no (2.36.0) | Output artifacts a completed call returns. |
| `recovery` | mapping | no (2.36.0) | Capabilities a planner may use instead after a failure, and guidance text. |
| `expected_duration_ms` | integer | no (2.36.0) | The call's deadline budget, 1..3,600,000 ms. |

Booleans must be real `bool`s (`1` and `"true"` are rejected). Identifiers use
the registry's bounded grammar `^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$`, at most
96 characters.

### Evidence spec

| Key | Required | Rule |
| --- | --- | --- |
| `kind` | yes | Identifier: the evidence kind produced (e.g. `displacement`). |
| `observe` | yes | Identifier: which observation the provider reports (e.g. `pose`). |
| `phases` | yes | Non-empty, duplicate-free, ordered subset of `before`, `after`, `settled`; must include `before` and `after`. An absolute op (`distance_to`, `angle_to`) must include `after`; `before` is optional for it. |
| `measure` | yes | `{"op": ..., "fields": [...]}`. `op` is `distance` or `distance_to` (1..3 fields), `along` (exactly 2 position fields plus `heading_field`), or `delta`, `angle_delta`, `abs_angle_delta`, `angle_to` (exactly 1 field). Fields are identifiers, no duplicates. `heading_field` (an identifier, not one of `fields`) is required for `along` and forbidden for every other op. Optional `frame` (2.38.0, an identifier): every observed phase must carry that `frame`. |
| `expect` | yes | For the relative ops, exactly one of `{"argument": name}` / `{"argument": name, "scale": number}` (a `number`/`integer` key of `params_schema`; `scale` finite, non-zero, default `1`) or `{"value": number}`; `scale` is not allowed with `value`. For the absolute ops, see [Absolute targets](#absolute-targets-2380). |
| `tolerance` | yes | Non-empty mapping with `absolute` and/or `relative`, each finite and ≥ 0. An absent one is normalized to `0`. An absolute op requires `relative` to be `0` (or absent). |
| `settle` | no | `{"max_drift": number ≥ 0}`; requires `settled` in `phases`. |

### Absolute targets (2.38.0)

Every other op measures a *change between two phases*. That cannot prove an
end state: "it is now at the place it was sent to", "the car is on the floor it
was asked for". A provider that reports success while it stopped short is
believed by any relative measure of how far it went. The two absolute ops
compare the **last declared phase alone** with a target taken from the call's
own arguments:

| `op` | `fields` | `expect` |
| --- | --- | --- |
| `distance_to` | 1..3 | `{"arguments": {field: parameter, ...}}` — one parameter name per measured field, exactly the measured fields, each a `number`/`integer` key of `params_schema`. No `scale`, no `value`. |
| `angle_to` | exactly 1 | `{"argument": parameter}`, or `{"argument": parameter, "optional": true}` when the call may leave the target out. `optional` must be a `bool`; `optional: true` on a parameter `params_schema` marks `required: true` is rejected. No `scale`, no `value`. |

Their `tolerance.relative` must be `0`: the target is a place, not an amount,
so there is nothing for a fraction to be a fraction of. Name the reference
frame the arguments are written in with `measure.frame`, so an observation in
another frame (a drifting odometry pose against a map coordinate) is never
compared with it.

A navigation that must end within 0.30 m of the asked map point, and facing the
asked heading when one is asked:

```json
[{"kind": "arrival", "observe": "map_pose", "phases": ["after", "settled"],
  "measure": {"op": "distance_to", "fields": ["x", "y"], "frame": "map"},
  "expect": {"arguments": {"x": "x", "y": "y"}},
  "tolerance": {"absolute": 0.30}},
 {"kind": "arrival.heading", "observe": "map_pose", "phases": ["after", "settled"],
  "measure": {"op": "angle_to", "fields": ["yaw"], "frame": "map"},
  "expect": {"argument": "yaw_radians", "optional": true},
  "tolerance": {"absolute": 0.30}}]
```

Normalized: `frame` appears only when declared, `expect.optional` only when
`true`, and the tolerance carries `relative: 0`. A contract that uses neither op
nor `frame` normalizes, and hashes, exactly as on 2.37.

**Feature detection.** A 2.37 core rejects these ops and the `frame` key. A
provider that must also load there declares this evidence only when
`"distance_to" in core.capability_contract.MEASURE_OPS`.

### Optional keys (2.36.0)

These four keys let a host stop carrying provider knowledge: which capability
stops a resource, which ones return a picture or a file, what to try after a
failure, and how long a call may run. Each appears in the normalized contract
**only when declared**, so a contract without them normalizes, and the manifest
hashes, exactly as on 2.35.

| Key | Rule |
| --- | --- |
| `role` | One of `safe_stop`. A `safe_stop` contract must be `cancellable: false`, `requires_safe_stop: false` and `idempotent: true`: the stop is not cancelled, needs no stop of its own and is safe to repeat. A host runs it immediately, with no approval queue or confirmation. |
| `artifacts` | 1..8 declarations `{"kind": identifier, "media_types": [...], "max_bytes": int}`. `kind` is unique; `media_types` holds 1..8 distinct lower-case `type/subtype` strings with no parameters; `max_bytes` is an integer in 1..20,971,520 (20 MiB). |
| `recovery` | `{"capabilities": [identifier, ...], "observe": identifier, "guidance": text}`. `capabilities` (1..8, distinct) is required: capability ids a planner may use as substitutes after this one fails. `observe` names an observation the adapter reports to explain the failure (e.g. `recovery_context`). `guidance` is at most 500 characters of planner-facing text. |
| `expected_duration_ms` | Integer in 1..3,600,000. The deadline a host gives the call. When absent, a host uses the module's `timeout_ms`, then its own default. |

Booleans are rejected where an integer is required (`max_bytes`,
`expected_duration_ms`), as everywhere else in the schema.

**Artifact transport.** A call that produces declared artifacts reports them in
its adapter result evidence as
`"artifacts": [{"kind": ..., "media_type": ..., "data_base64": ...}]`. A host
keeps an artifact only when its `kind` is declared, its `media_type` is one the
declaration lists and its decoded size is within `max_bytes`; a completed call
of a contract that declares artifacts but returned none that pass is a failed
call.

**Feature detection.** The schema is closed, so a 2.35 core rejects these keys.
A provider that must load on both lines sends them only when
`"role" in core.capability_contract.OPTIONAL_FIELDS` (the frozenset exists from
2.36.0).

### Parameter bounds

Bounds are not a contract field: they are `params_schema` `min` / `max` (plus
`unit`). When `actuates` is true, **every** parameter whose `type` is `number`
or `integer` must declare finite numeric `min` and `max` with `min ≤ max`. A
host refuses (never clamps) an argument outside them.

When a contract is declared, `params_schema` must also be JSON-serializable
(no `NaN`, no Python objects), because it travels beside the contract in the
capability manifest.

### Normalized form

`validate_contract(contract, params_schema)` returns the normalized form, built
from fresh containers: it always carries `schema`, `effects`, `requires`,
`evidence`, every tolerance carries both `absolute` and `relative`, and every
`expect.argument` carries its `scale` (default `1`). The optional `role`,
`artifacts`, `recovery` and `expected_duration_ms` appear only when declared.
The registry stores this form, so every consumer reads one shape.

## Where a contract is published

- `ModuleRegistry.get_metadata(id)["contract"]` and `get_all_metadata()`.
- `core.catalog.module.get_module_detail(id)["contract"]` (`None` when absent).
  Detail also reports `timeout_ms`, and `timeout` (seconds) now derives from it.
- The capability manifest (`flyto.core.capability-manifest.v1`) gains, **only
  when at least one module declares a contract**:

  ```json
  "contract_count": 1,
  "contracts": {
    "lift.move_to_floor": {
      "module_id": "lift.move_to_floor",
      "contract": { "schema": "flyto.capability-contract.v1", "...": "..." },
      "params_schema": { "floor": { "type": "integer", "min": 0, "max": 40 } }
    }
  }
  ```

  An installation without contracts produces byte-for-byte the manifest (and
  hash) it produced before contracts existed. If two modules contract the same
  capability, the entry belongs to the lexicographically lowest module id.

## Judging evidence

`judge(evidence_spec, arguments, observations)` is pure. A host that cannot
import Core re-implements it from this section and must reach identical
verdicts.

Input:

- `evidence_spec` — one item of `contract["evidence"]`.
- `arguments` — the arguments the capability was invoked with.
- `observations` — `{"before": {...}, "after": {...}, "settled": {...}}`, each
  phase a mapping of field name to number, plus a string `frame` when the
  spec's measure names one. Extra phases and fields are ignored.

Output: `{"usable", "measured", "expected", "allowed", "settle_drift", "reason"}`.

### Arithmetic

Let `f₁..fₙ` be `measure.fields`, and `wrap(a)` the angle `a` wrapped into the
half-open interval **(−π, π]**:

```
wrap(a) = r + 2π   if r ≤ −π
          r        otherwise
  where r = a − 2π·n, n = the integer nearest a / 2π (ties to even)
        (Python: math.remainder(a, 2π))
```

`M(p, q)` — the measure from phase `p` to phase `q` (for `along`, `h` is
`p[heading_field]`, the heading held at the *start* phase, in radians):

| `op` | `M(p, q)` |
| --- | --- |
| `distance` | `sqrt( Σᵢ (q[fᵢ] − p[fᵢ])² )` |
| `along` | `(q[f₁] − p[f₁])·cos(h) + (q[f₂] − p[f₂])·sin(h)` — signed displacement projected onto the starting heading |
| `delta` | `q[f₁] − p[f₁]` |
| `angle_delta` | `wrap(q[f₁] − p[f₁])` |
| `abs_angle_delta` | `abs(wrap(q[f₁] − p[f₁]))` |

`D(after, settled)` — how far the observation still moved after the action
ended; always a magnitude:

| `op` | `D(after, settled)` |
| --- | --- |
| `distance`, `along` | `sqrt( Σᵢ (settled[fᵢ] − after[fᵢ])² )` (euclidean over `fields`) |
| `delta` | `abs(settled[f₁] − after[f₁])` |
| `angle_delta`, `abs_angle_delta` | `abs(wrap(settled[f₁] − after[f₁]))` |

For the absolute ops `D` is the same: euclidean over `fields` for
`distance_to`, `abs(wrap(settled[f₁] − after[f₁]))` for `angle_to`.

Then, with `last` the last phase listed in `phases` (`settled` when listed,
otherwise `after`):

```
measured = M(before, last)                             relative ops
         = sqrt( Σᵢ (last[fᵢ] − tᵢ)² ),                op = distance_to,
             tᵢ = arguments[expect.arguments[fᵢ]]
         = last[f₁]                                    op = angle_to
expected = scale · arguments[expect.argument]          if expect.argument, op relative, op ≠ abs_angle_delta
         = abs(scale · arguments[expect.argument])     if expect.argument, and op = abs_angle_delta
         = expect.value                                if expect.value
         = 0                                           op = distance_to
         = arguments[expect.argument]                  op = angle_to
allowed  = max(tolerance.absolute, tolerance.relative · abs(expected))
           (= tolerance.absolute for the absolute ops, whose relative is 0)
error    = abs(wrap(measured − expected))              if op is angle_delta, abs_angle_delta or angle_to
         = abs(measured − expected)                    otherwise
settle_drift = D(after, settled)                       if the spec declares settle, else None

usable = error ≤ allowed  and  (settle_drift is None or settle_drift ≤ settle.max_drift)
```

An absolute op never reads `before`, even when `phases` lists it (a listed
phase must still be observed). `distance_to` reports `expected = 0`: the
distance it wanted from the target.

**An omitted optional target.** For `angle_to` with `expect.optional: true`,
when `arguments` is a mapping and `arguments[expect.argument]` is absent or
`null`, the verdict is decided **before anything else is checked**:
`usable: true`, `measured`/`expected`/`allowed`/`settle_drift` `None`, reason
`argument '<name>' was not given; no target to check`. A present but
non-numeric value is not an omission; it is rule 5 below.

The measured quantity runs from `before` to the **last** declared phase, not to
`after`: the effect that counts is the one that is still there once the
provider says the world has settled. `after` is used only for the settle drift.

Comparisons are inclusive (`≤`) and on unrounded IEEE-754 doubles. For an
expectation of `value: 0` (a "this must not change" check, such as holding a
heading), `allowed` is simply `tolerance.absolute`.

### When the data is missing

These are never exceptions; they are `usable: false` with a reason, and
`measured`/`expected`/`allowed` are `None`. Checked in this order:

1. `observations` is not a mapping.
2. A phase listed in the spec's `phases` is absent or not a mapping — every
   declared phase is required, so a spec with `settle` (which needs `settled`
   in `phases`) is unusable without a `settled` observation.
3. The spec's measure names a `frame` and that phase's `frame` is not equal to
   it (absent counts as different). Reason: `phase '<p>' is not in frame '<f>'`.
   Rules 2–4 run phase by phase, in `phases` order.
4. A measured field is absent, not a number, a `bool`, or not finite (for
   `along`, this includes `heading_field` in the `before` phase; it is not read
   from any other phase).
5. `expect.argument` — or, for `distance_to`, one of `expect.arguments`, checked
   in `fields` order — is absent from `arguments`, not a number, a `bool`, or
   not finite. Reason: `argument '<name>' is missing or not a finite number`.

The exact reason strings are part of the contract: every verdict in
[`tests/core/vectors/capability_contract_absolute_targets.json`](../tests/core/vectors/capability_contract_absolute_targets.json)
(spec, arguments, observations and the full verdict) must be reproduced by a
re-implementation. Numbers in a `reason` are formatted with Python's `.6g`.

A malformed `evidence_spec` itself raises `ValueError` — it is a programming
error, not an observation.

### Worked example: a displacement

Spec (an `advance` of a mobile base):

```json
{"kind": "displacement", "observe": "pose", "phases": ["before", "after", "settled"],
 "measure": {"op": "distance", "fields": ["x", "y"]},
 "expect": {"argument": "distance_m"},
 "tolerance": {"absolute": 0.03, "relative": 0.3},
 "settle": {"max_drift": 0.02}}
```

Arguments `{"distance_m": 0.10}`. Observations: before `(x 1.000, y 2.000)`,
after `(1.100, 2.040)`, settled `(1.110, 2.040)`.

```
measured     = M(before, settled) = sqrt(0.110² + 0.040²)   = 0.117047
expected     = 1 · 0.10                                     = 0.10
allowed      = max(0.03, 0.3 · 0.10)                        = 0.03
error        = |0.117047 − 0.10|                            = 0.017047  ≤ 0.03   ✓
settle_drift = D(after, settled) = sqrt(0.010² + 0²)        = 0.010     ≤ 0.02   ✓
usable       = true
```

Had it stopped at `(1.060, 2.000)` (after and settled): `measured = 0.06`,
`error = 0.04 > 0.03` → `usable = false`.

### Worked example: a signed displacement along the heading (`along`, `scale`)

`distance` is unsigned and counts a sideways slide as progress. `along`
projects the movement onto the heading the provider reported at `before`, so
only travel in the intended direction counts, and its sign says which way.

```json
{"kind": "displacement", "observe": "pose", "phases": ["before", "after", "settled"],
 "measure": {"op": "along", "fields": ["x", "y"], "heading_field": "yaw"},
 "expect": {"argument": "distance_m"},
 "tolerance": {"absolute": 0.03, "relative": 0.3},
 "settle": {"max_drift": 0.02}}
```

Advance, arguments `{"distance_m": 0.10}`. Before `(x 1.000, y 1.000, yaw π/2)`
(facing +y), after `(1.010, 1.110)`, settled `(1.010, 1.115)`.

```
h            = before.yaw                                   = π/2
measured     = 0.010·cos(π/2) + 0.115·sin(π/2)              = 0.115
expected     = 1 · 0.10                                     = 0.10
allowed      = max(0.03, 0.3 · 0.10)                        = 0.03
error        = |0.115 − 0.10|                               = 0.015  ≤ 0.03   ✓
settle_drift = sqrt(0² + 0.005²)                            = 0.005  ≤ 0.02   ✓
usable       = true
```

The 0.010 m sideways slip contributes nothing to `measured`.

A retreat declares the same spec with `"expect": {"argument": "distance_m",
"scale": -1}`: the caller still asks for a positive `distance_m`, and the
expectation is backwards travel. Arguments `{"distance_m": 0.2}`, before
`(0, 0, yaw 0)`, after and settled `(−0.19, 0)`:

```
measured     = −0.19·cos 0 + 0·sin 0                        = −0.19
expected     = −1 · 0.2                                     = −0.2
allowed      = max(0.03, 0.3 · |−0.2|)                      = 0.06
error        = |−0.19 − (−0.2)|                             = 0.01  ≤ 0.06   ✓
usable       = true
```

Had it driven forward 0.19 m instead, `error = |0.19 + 0.2| = 0.39` → unusable.

### Worked example: a rotation

Spec:

```json
{"kind": "rotation", "observe": "pose", "phases": ["before", "after"],
 "measure": {"op": "abs_angle_delta", "fields": ["yaw"]},
 "expect": {"argument": "yaw_radians"},
 "tolerance": {"absolute": 0.1, "relative": 0.2}}
```

Arguments `{"yaw_radians": -1.0}`. Observations: before `yaw 3.0`, after
`yaw -2.25` (the heading crossed ±π).

```
raw difference = −2.25 − 3.0                 = −5.25
wrap(−5.25)    = −5.25 + 2π                  = 1.033185
measured       = abs(1.033185)               = 1.033185
expected       = abs(−1.0)                   = 1.0
allowed        = max(0.1, 0.2 · 1.0)         = 0.2
error          = |wrap(1.033185 − 1.0)|      = 0.033185  ≤ 0.2   ✓
usable         = true   (settle_drift = None: no settle declared)
```

`abs_angle_delta` checks the magnitude of the turn, not its direction.

### Worked example: a signed rotation across ±π (`angle_delta`)

Use `angle_delta` when direction matters. Its error is itself wrapped, so a
turn that crosses ±π is compared by the short way round.

```json
{"kind": "rotation", "observe": "pose", "phases": ["before", "after", "settled"],
 "measure": {"op": "angle_delta", "fields": ["yaw"]},
 "expect": {"argument": "yaw_radians"},
 "tolerance": {"absolute": 0.1, "relative": 0.2},
 "settle": {"max_drift": 0.02}}
```

Before `yaw 3.10`, after and settled `yaw −3.10`:

```
measured = wrap(−3.10 − 3.10) = wrap(−6.20) = −6.20 + 2π   = +0.083185
```

| asked `yaw_radians` | expected | allowed | error | usable |
| --- | --- | --- | --- | --- |
| `0.0832` | 0.0832 | max(0.1, 0.01664) = 0.1 | 0.000015 | yes |
| `1.5708` | 1.5708 | max(0.1, 0.31416) = 0.31416 | 1.487615 | no |

And before `yaw 0.2`, settled `yaw 3.4 − 2π (≈ −2.883185)`, asked `−3.0`:

```
measured = wrap(−2.883185 − 0.2)            = −3.083185
expected = −3.0
allowed  = max(0.1, 0.2 · 3.0)              = 0.6
error    = |wrap(−3.083185 − (−3.0))|       = 0.083185  ≤ 0.6   ✓
```

### Worked example: a reported arrival that stopped short (`distance_to`)

The navigation spec from [Absolute targets](#absolute-targets-2380). The call
asked for `{"x": 1.196, "y": -0.005, "yaw_radians": 0.0028}`; the provider
reported success, and its map pose after and once settled was
`(x 0.566, y −0.005, yaw 0.01)`.

```
arrival:          measured = sqrt((0.566 − 1.196)² + (−0.005 − (−0.005))²) = 0.63
                  expected = 0,  allowed = 0.30,  error = 0.63 > 0.30   → usable = false
arrival.heading:  measured = 0.01,  expected = 0.0028
                  error = |wrap(0.01 − 0.0028)| = 0.0072 ≤ 0.30          → usable = true
```

The heading held, which proves nothing about the place: the call is not
verified. Asked without `yaw_radians`, the heading item is `usable: true` with
`measured: None` (no target to check), and the position item alone decides.

A lift that must end on the asked floor uses the same op in one dimension:
`{"op": "distance_to", "fields": ["floor"]}`, `{"arguments": {"floor":
"floor"}}`, `tolerance.absolute 0`. Asked floor 7, observed 6 after: measured
`1`, unusable.

### A "must not change" check (`heading.hold`)

An expectation of `value: 0` with an absolute tolerance says a quantity must
stay put while something else happens. A linear move that must keep its
heading within 0.15 rad:

```json
{"kind": "heading.hold", "observe": "pose", "phases": ["before", "after", "settled"],
 "measure": {"op": "abs_angle_delta", "fields": ["yaw"]},
 "expect": {"value": 0},
 "tolerance": {"absolute": 0.15}}
```

Before `yaw 0`, settled `yaw 0.02`: `measured = 0.02`, `allowed = 0.15` → usable.
A rotation that must not wander uses the same shape over position:
`distance` of `["x", "y"]`, `expect.value 0`, `tolerance.absolute 0.05` — a
0.06 m drift while turning is unusable.

### Reference: the motion contracts of flyto-modules-robotics

flyto-modules-robotics (PR #9) declares its motions with the operators above,
chosen so its verdicts equal Flyto2 Cloud's earlier built-in motion check:

- `motion.advance` / `motion.retreat`: `along` over `["x", "y"]` with
  `heading_field: "yaw"`, `expect.argument: distance_m` (retreat with
  `scale: -1`), tolerance `absolute 0.03, relative 0.3`, `settle.max_drift 0.02`;
  plus `heading.hold` (`abs_angle_delta`, expected 0, absolute 0.15).
- `motion.rotate`: signed `angle_delta` over `["yaw"]`, `expect.argument:
  yaw_radians`, tolerance `absolute 0.1, relative 0.2`; plus a position-drift
  item (`distance`, expected 0, absolute 0.05).
- `motion.navigate` (with a 2.38.0 core): `distance_to` over `["x", "y"]` in
  frame `map`, observed as `map_pose`, after and settled; plus `angle_to` over
  `["yaw"]` with an optional `yaw_radians`. Tolerances follow the robot's own
  navigation goal checker plus a small margin.

These are a provider's choices, not Core vocabulary: Core knows only the
operators.

## Writing a provider

A provider is an ordinary Python distribution. It exposes a `register_all`
callable through the `flyto.modules` entry point group; Core calls it during
plugin discovery. Every module it registers is attributed to the plugin, and if
`register_all` raises — including because a contract is invalid — the whole
plugin is rolled back: none of its modules remain registered.

`pyproject.toml`:

```toml
[project]
name = "acme-building"
dependencies = ["flyto-core>=2.35.1"]

[project.entry-points."flyto.modules"]
acme_building = "acme_building:register_all"
```

`acme_building/__init__.py`:

```python
# Optional: one line describing the pack, shown beside its modules.
PACK_DESCRIPTION = "Building lifts and stock control"


def register_all():
    # Importing the modules runs their @register_module decorators.
    from . import lift, inventory  # noqa: F401
```

`PACK_DESCRIPTION` is an optional module-level string in the module that
defines the entry point callable. Core reads it (never calls anything) when the
plugin loads; a value that is not a non-empty string counts as no description.
It is reported as `PluginInfo.description` and, when present, as `description`
on the pack's entry in the capability manifest:

```json
"plugins": [
  {
    "id": "acme_building",
    "version": "1.0.0",
    "module_count": 2,
    "module_ids": ["acme.inventory.adjust", "acme.lift.move_to_floor"],
    "description": "Building lifts and stock control"
  }
]
```

`module_ids` (sorted) lists every module the pack owns — what
`ModuleRegistry.get_plugin_modules` answers — so a host can show a pack as one
resource without reverse-mapping module ids. Each module's owner is also its
`plugin` field in catalog detail and MCP `get_module_info`, beside its
`contract`. An installation without plugins keeps the same manifest and hash.

### A lift

```python
# acme_building/lift.py
from core.modules.registry import register_module


@register_module(
    module_id="acme.lift.move_to_floor",
    provides_capability="lift.move_to_floor",
    label="Move lift to floor",
    description="Send the lift car to a floor and report the floor it stopped at",
    params_schema={"floor": {"type": "integer", "min": 0, "max": 40, "required": True}},
    contract={
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,             # sending the car to floor N twice leaves it at N
        "effects": ["lift.floor-changed"],
        "requires": ["lift.doors-closed"],
        "evidence": [],
    },
    can_receive_from=["*"],
    can_connect_to=["*"],
)
async def move_to_floor(context):
    ...
```

The lift above declares no evidence; before 2.38.0 it could not, because
every measure was a *change between two phases* and "the car ended on floor N"
is an absolute end state. Since 2.38.0 it proves it with an absolute target
(see [Absolute targets](#absolute-targets-2380)):

```python
        "evidence": [{
            "kind": "floor.reached",
            "observe": "car",           # the controller reports {"floor": n}
            "phases": ["after"],
            "measure": {"op": "distance_to", "fields": ["floor"]},
            "expect": {"arguments": {"floor": "floor"}},
            "tolerance": {"absolute": 0},
        }],
```

The host also gets everything else from this contract — the safety class,
safe-stop and cancellation rules, idempotency, and the refuse-never-clamp bound
`0 ≤ floor ≤ 40`. A lift that takes a relative move (`floors`, bounded
`−40..40`) proves it with `{"measure": {"op": "delta", "fields": ["floor"]},
"expect": {"argument": "floors"}}`.

### An inventory update

```python
# acme_building/inventory.py
from core.modules.registry import register_module


@register_module(
    module_id="acme.inventory.adjust",
    provides_capability="inventory.adjust",
    label="Adjust stock",
    description="Add or remove units of a stock item and report the new count",
    params_schema={
        "sku": {"type": "string", "required": True},
        "quantity": {"type": "integer", "min": -1000, "max": 1000, "required": True},
    },
    contract={
        "actuates": True,               # it changes an external system of record
        "safety_class": "controlled",
        "requires_safe_stop": False,
        "cancellable": False,
        "idempotent": True,             # the call id is the adjustment's idempotency key
        "effects": ["inventory.changed"],
        "evidence": [{
            "kind": "stock-adjusted",
            "observe": "stock-level",   # the connector reports {"on-hand": n}
            "phases": ["before", "after"],
            "measure": {"op": "delta", "fields": ["on-hand"]},
            "expect": {"argument": "quantity"},
            "tolerance": {"absolute": 0},
        }],
    },
    can_receive_from=["*"],
    can_connect_to=["*"],
)
async def adjust(context):
    ...
```

### A motion

```python
@register_module(
    module_id="acme.base.advance",
    provides_capability="motion.advance",
    label="Advance",
    description="Drive straight ahead a bounded distance and stop",
    params_schema={
        "distance_m": {"type": "number", "min": 0.05, "max": 2.0, "unit": "m", "required": True},
        "speed_mps": {"type": "number", "min": 0.02, "max": 0.25, "unit": "m/s", "default": 0.12},
    },
    contract={
        "actuates": True,
        "safety_class": "movement",
        "requires_safe_stop": True,
        "cancellable": True,
        "idempotent": True,
        "effects": ["position.changed"],
        "requires": ["observation.fresh"],
        "evidence": [
            {
                "kind": "displacement",
                "observe": "pose",              # the provider reports {"x", "y", "yaw"}
                "phases": ["before", "after", "settled"],
                "measure": {"op": "along", "fields": ["x", "y"], "heading_field": "yaw"},
                "expect": {"argument": "distance_m"},
                "tolerance": {"absolute": 0.03, "relative": 0.3},
                "settle": {"max_drift": 0.02},
            },
            {
                "kind": "heading.hold",
                "observe": "pose",
                "phases": ["before", "after", "settled"],
                "measure": {"op": "abs_angle_delta", "fields": ["yaw"]},
                "expect": {"value": 0},
                "tolerance": {"absolute": 0.15},
            },
        ],
    },
    can_receive_from=["*"],
    can_connect_to=["*"],
)
async def advance(context):
    ...
```

A provider can self-check before shipping:

```python
from core.capability_contract import judge

verdict = judge(spec, {"distance_m": 0.10},
                {"before": {"x": 0, "y": 0, "yaw": 0},
                 "after": {"x": 0.11, "y": 0, "yaw": 0},
                 "settled": {"x": 0.11, "y": 0, "yaw": 0}})
assert verdict["usable"]
```

## Other languages

`@register_module` is how a contract is written **in Python**. It is not the
platform spec. The spec is the registry row the decorator produces — module
id, display fields, `params_schema`, connection rules and this contract —
and since 2.37.0 that row has a language-neutral form,
[`flyto.pack.v1`](specs/PACK_MANIFEST_SPEC.md). Any program that emits the
same rows is loaded into the same registry and is indistinguishable from a
Python pack to the catalog, the capability manifest, MCP search, workflows and
a capability host.

See what a Python pack's decorators produce:

```bash
flyto pack manifest robotics                      # an installed flyto.modules entry point
flyto pack manifest acme_building:register_all --version 1.0.0
```

Write the same thing in Node.js (`examples/packs/node-greeter/`):

```js
const { definePack, registerModule, main } = require('./flyto');

definePack({ id: 'com.example.greeter', version: '0.1.0', namespaces: ['greeter'] });

registerModule({
  module_id: 'greeter.greet',
  label: 'Greet',
  params_schema: { name: { type: 'string', label: 'Name', required: true } },
  provides_capability: 'greeter.greet',
  contract: { actuates: false, safety_class: 'read_only', requires_safe_stop: false,
              cancellable: true, idempotent: true },
  handler: async ({ name }) => ({ greeting: `Hello, ${name}!` }),
});

main();   // `node index.js --manifest` prints flyto.pack.v1; `node index.js` serves JSON-RPC
```

The field names are the decorator's keyword names, and the validator applies
the decorator's defaults, so the Node row and the Python row for the same
module normalize to identical JSON (asserted in
`tests/core/pack/test_node_example_pack.py`). The contract inside is validated
by the same `validate_contract`, including the finite `min`/`max` rule for an
actuating contract's numeric parameters.

A host installs such a pack with `core.pack.host.install_pack(dir,
trusted_keys=...)`: the tree digest and ed25519 publisher signature are
checked offline, the modules are registered under the pack id as owner (so
`FLYTO_PLUGIN_GRANTS` and the allow/deny lists apply to it), and calls go over
JSON-RPC on stdio (`subprocess-jsonrpc`) or to a host-configured loopback or
allow-listed endpoint (`http`). The pack process receives parameters and
identifiers only — never the execution context. An ERP connector, an OpenRMF
fleet adapter or any third-party program is a pack this way; a robot keeps
running stock software and only its host-side adapter is a pack.

## Running a contract without Desktop

[`CAPABILITY_HOST.md`](CAPABILITY_HOST.md) describes `flyto run
--capability-host`, a generic host in Core that enforces these contracts for
a run started from the command line.

## Relation to the outcome ladder

`judge` decides whether one piece of evidence is usable. It does not assign an
outcome rung ([`core/engine/outcome.py`](../src/core/engine/outcome.py)); a
host that evaluates every declared evidence spec and finds all of them usable
has evaluated a postcondition that held, which is what `verified` means there.
