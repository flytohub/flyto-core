# Capability Host — run a capability pack with flyto-core alone

A capability pack is a Python distribution that registers steps through
`@register_module(provides_capability=..., contract=...)` (see
[`CAPABILITY_CONTRACT.md`](CAPABILITY_CONTRACT.md)). At run time such a step,
and Core's own `capability.invoke`, hand `{resource_id, capability_id,
arguments}` to an opaque dispatcher the host put in the workflow context. Flyto2
Desktop builds that dispatcher itself. `core.capability_host.CapabilityHost` is
the same authority for a plain `flyto run`, so a pack and its adapter run with
nothing but flyto-core installed.

Implementation: [`src/core/capability_host/host.py`](../src/core/capability_host/host.py).
CLI glue: [`src/cli/capability_host.py`](../src/cli/capability_host.py).

## Command line

```bash
pip install flyto-core <a capability pack> <its adapter package>

# Read-only capabilities only: anything actuating is refused.
flyto run inspect.yaml --capability-host <adapter-id> --resource <resource-id>

# Allow named actuating capabilities for this run.
flyto run move.yaml --capability-host <adapter-id> --resource <resource-id> \
  --allow motion.advance,motion.rotate
```

| Flag | Meaning |
| --- | --- |
| `--capability-host ADAPTER_ID` | Entry-point name in the `flyto2.external_adapters` group. Exactly one installed distribution must register it. |
| `--resource RESOURCE_ID` | The commanded resource. The adapter factory is called with it, and a request naming any other resource is refused. |
| `--allow IDS` | Comma-separated, repeatable. The actuating capabilities this run may execute. |
| `--yes-physical` | Confirm actuation on a physical deployment without a prompt. |
| `--capability-evidence PATH` | Where the call records are written (JSON). Default: the CLI output directory. |

`--resource`, `--allow` and `--yes-physical` without `--capability-host` are an
error. Pressing Ctrl-C during a run calls the adapter's `safe_stop()` before the
CLI exits.

## Adapter interface

An adapter package registers a factory:

```toml
[project.entry-points."flyto2.external_adapters"]
acme.lift = "acme_lift.adapter:build_adapter"   # build_adapter(resource_id) -> adapter
```

The adapter object is duck-typed; it is the same interface Flyto2 Desktop calls.

| Member | Used for |
| --- | --- |
| `invoke(request)` | `request` has `call_id`, `capability_id`, `arguments`, `deadline_seconds`. Returns an object or mapping with `outcome` (`completed`, `refused`, `timeout`, `cancelled`, `failed`), `detail`, `evidence`. |
| `cancel(call_id)` | Called after a `timeout` or `failed` outcome. |
| `safe_stop()` | Called after `cancel` on `timeout`/`failed`, on Ctrl-C, and by `emergency_stop()`. |
| `observe(phase=..., execution_id=...)` | Optional. Returns a mapping of observations (e.g. `{"pose": {...}}`). Phases: `before`, `after`, `post_stop`, and `preflight` for the deployment check. |
| `deployment_mode` | Optional attribute or method. `"simulation"` marks a simulated deployment; anything else, or nothing, is treated as physical. When absent, `observe(phase="preflight")["deployment_mode"]` is read. |
| `wait_until_stationary(seconds)` | Optional. Used before the `settled` observation; otherwise the host waits one second. |
| `disconnect()` | Optional. Called when the run ends. |

## Policy

The host reads each capability's contract from the registry. It holds no
thresholds, units or capability names of its own; safety floors (a clearance
minimum, a speed limit) belong to the adapter that owns the equipment.

1. **Resource match.** A request for any resource other than `--resource` is
   refused.
2. **Contract lookup.** If the providers of a capability declare no contract,
   or disagree on it, the capability is treated as actuating (fail closed).
3. **Allow list.** An actuating capability runs only when `--allow` names it.
   A capability whose contract has `role: safe_stop` is always allowed.
4. **Physical deployment.** Before an actuating call (other than the stop),
   the host asks the adapter for its deployment. Unless it is `simulation`,
   the call needs `--yes-physical` or a typed `yes` at an interactive prompt
   that names the capability, resource and arguments. With no terminal and no
   flag, the call is refused. The stop never waits for a prompt.
5. **Deadline.** `expected_duration_ms` from the contract, else the module's
   `timeout_ms`, else 60 s; clamped to 1 s .. 1 h. The adapter should honour
   it, and the host enforces it as well: a call that has not returned 5 s
   after its deadline is recorded as `timeout` with `"host_watchdog": true`
   and safe-stopped (the adapter thread is abandoned, not killed). Calls on
   one host run one at a time; `emergency_stop()` never waits for them.
6. **Observation.** The phases are the union of the contract's evidence
   `phases`. `before` is observed before the call. After a completed call, or
   an actuating call that ended `timeout`, `failed` or `cancelled`, `after` is
   observed, then — when declared — `settled`. The contract phase `settled`
   is the adapter phase `post_stop`; the adapter API keeps that name because
   released hosts call it.
7. **Safe stop.** A `timeout` or `failed` outcome (including an adapter that
   raises, returns an unknown outcome, or hangs past its deadline, and an
   actuating call failed for returning no declared artifact) is followed by `cancel(call_id)` and
   `safe_stop()`, and the record says what each returned.
8. **Pass-through.** The adapter's outcome, detail and evidence are recorded
   verbatim. A refusal stays a refusal, and the host never rewrites arguments,
   so an adapter that refuses rather than clamps keeps that behaviour.
9. **Evidence.** Each evidence spec is judged with
   `core.capability_contract.judge` against the observation named by its
   `observe` key. The verdicts are recorded beside the outcome; they do not
   change it.
10. **Artifacts.** When the contract declares `artifacts`, a completed call's
    `evidence.artifacts` are checked against the declaration (kind, media type,
    size) and saved under the output directory. A completed call that returns
    no artifact passing the check is recorded as `failed`.

## Call record

Every call produces one record (`schema: flyto.capability-host.v1`):

```json
{
  "schema": "flyto.capability-host.v1",
  "call_id": "cap-…",
  "run_id": "run-…",
  "adapter_id": "acme.lift",
  "commanded_resource_id": "lift-a",
  "capability_id": "lift.move_to_floor",
  "arguments": {"floor": 3},
  "contract_status": "declared",
  "policy": {"actuates": true, "safe_stop_role": false, "deployment": "simulation"},
  "deadline_seconds": 120.0,
  "outcome": "completed",
  "detail": "",
  "adapter_evidence": {},
  "observations": {"before": {}, "after": {}, "settled": {}},
  "verification": {"verified": true, "verdicts": [{"kind": "floor.reached", "usable": true}]},
  "started_at": 0.0,
  "finished_at": 0.0
}
```

A record the host refused carries `refused_by: "host"`; an adapter refusal
does not.

## Library use

```python
from core.capability_host import CapabilityHost
from core.engine.workflow.engine import WorkflowEngine

host = CapabilityHost(adapter_id="acme.lift", resource_id="lift-a",
                      allow=["lift.move_to_floor"], confirm=None)
engine = WorkflowEngine(workflow, params, initial_context=host.context())
await engine.execute()
records = host.records()
host.close()
```

`confirm` is a callable that receives the prompt text and returns `True` to
proceed; `None` refuses every physical actuation that `yes_physical` does not
cover.

## Scope

- Flyto2 Desktop keeps its own dispatcher; it does not use this host.
- The HTTP API (`flyto serve`) does not create a capability host. Its existing
  `X-Flyto-Host-Capability-*` proxy is unchanged.
