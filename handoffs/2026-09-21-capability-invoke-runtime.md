# Flyto2 Core capability invocation runtime — 2026-09-21

## Goal

Give Flyto2 Cloud and external equipment hosts one canonical workflow primitive
for device capabilities without moving discovery, approval, routing, or
device-specific protocols into Core.

## Implemented

- Added atomic module `capability.invoke`.
- The module accepts only a bounded `resource_id`, `capability_id`, and flat
  JSON-scalar `arguments` object.
- Execution requires the host to inject an object whose class carries
  `_flyto_runtime_opaque = True` and which exposes async `invoke(request)`.
- Missing/untrusted runtime authority fails closed.
- Non-completed host outcomes become module failures; completed calls return the
  host's structured record to the ordinary workflow result/evidence path.
- Registered `capability` as an atomic module category.

## Boundary

Core does not discover equipment, approve capabilities, choose resources, load
ROS/vendor transports, or decide whether an actuation is safe. Those are
control-plane/adapter-host responsibilities. A host must scope the opaque
dispatcher to the exact job authority before injecting it.

## Verification

- `PYTHONPATH=src python -m pytest tests/core/test_capability_invoke_module.py tests/test_registry_system.py tests/modules/test_atomic_coverage.py -q --no-cov`
- Result: 145 passed, 1 skipped.

Generated-reference/documentation gates and final repository CI are run as part
of the coordinating Cloud/Core closure before merge.
