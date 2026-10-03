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
(`validate_contract`, `judge`, `wrap_angle`). Registration wiring:
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

Booleans must be real `bool`s (`1` and `"true"` are rejected). Identifiers use
the registry's bounded grammar `^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$`, at most
96 characters.

### Evidence spec

| Key | Required | Rule |
| --- | --- | --- |
| `kind` | yes | Identifier: the evidence kind produced (e.g. `displacement`). |
| `observe` | yes | Identifier: which observation the provider reports (e.g. `pose`). |
| `phases` | yes | Non-empty, duplicate-free, ordered subset of `before`, `after`, `settled`; must include `before` and `after`. |
| `measure` | yes | `{"op": ..., "fields": [...]}`. `op` is `distance` (1..3 fields), `along` (exactly 2 position fields plus `heading_field`), or `delta`, `angle_delta`, `abs_angle_delta` (exactly 1 field). Fields are identifiers, no duplicates. `heading_field` (an identifier, not one of `fields`) is required for `along` and forbidden for every other op. |
| `expect` | yes | Exactly one of `{"argument": name}` / `{"argument": name, "scale": number}` (a `number`/`integer` key of `params_schema`; `scale` finite, non-zero, default `1`) or `{"value": number}`. `scale` is not allowed with `value`. |
| `tolerance` | yes | Non-empty mapping with `absolute` and/or `relative`, each finite and ≥ 0. An absent one is normalized to `0`. |
| `settle` | no | `{"max_drift": number ≥ 0}`; requires `settled` in `phases`. |

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
`expect.argument` carries its `scale` (default `1`). The registry stores this
form, so every consumer reads one shape.

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
  phase a mapping of field name to number. Extra phases and fields are ignored.

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

Then, with `last` the last phase listed in `phases` (`settled` when listed,
otherwise `after`):

```
measured = M(before, last)
expected = scale · arguments[expect.argument]          if expect.argument, and op ≠ abs_angle_delta
         = abs(scale · arguments[expect.argument])     if expect.argument, and op = abs_angle_delta
         = expect.value                                otherwise
allowed  = max(tolerance.absolute, tolerance.relative · abs(expected))
error    = abs(wrap(measured − expected))              if op is angle_delta or abs_angle_delta
         = abs(measured − expected)                    otherwise
settle_drift = D(after, settled)                       if the spec declares settle, else None

usable = error ≤ allowed  and  (settle_drift is None or settle_drift ≤ settle.max_drift)
```

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
3. A measured field is absent, not a number, a `bool`, or not finite (for
   `along`, this includes `heading_field` in the `before` phase; it is not read
   from any other phase).
4. `expect.argument` is absent from `arguments`, not a number, a `bool`, or not
   finite.

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

The lift declares no evidence, and that is a limit of v1 worth knowing: every
v1 measure is a *change between two phases* compared with one argument or
constant. "The car ended on floor N" is an absolute end state, and the change
from the starting floor is not an argument the caller supplied. The host still
gets everything else from this contract — the safety class, safe-stop and
cancellation rules, idempotency, and the refuse-never-clamp bound `0 ≤ floor ≤ 40`.
A lift that takes a relative move (`floors`, bounded `−40..40`) can prove it
with `{"measure": {"op": "delta", "fields": ["floor"]}, "expect": {"argument": "floors"}}`.

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

## Relation to the outcome ladder

`judge` decides whether one piece of evidence is usable. It does not assign an
outcome rung ([`core/engine/outcome.py`](../src/core/engine/outcome.py)); a
host that evaluates every declared evidence spec and finds all of them usable
has evaluated a postcondition that held, which is what `verified` means there.
