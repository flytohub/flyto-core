# Adapter template pack

Evidence level: **D2** (template against its own simulated axis). It drives
no hardware.

A starting point for a third party who wants a device to be used by any
`flyto.pack.v1` host without changing that host. The pack carries its own
capability contracts ([`flyto.capability-contract.v1`](../../../docs/CAPABILITY_CONTRACT.md)),
and the runner serves them over JSON-RPC on stdio
([`flyto.pack.v1`](../../../docs/specs/PACK_MANIFEST_SPEC.md)). It follows the
portable-capability guidance (flyto-core PR #140,
`docs/specs/PORTABLE_CAPABILITY_SPEC.md`, not merged at the time of writing).

| File | What to change |
| --- | --- |
| `flyto-pack.json` | Your pack id, namespace, capabilities, bounds and evidence. Keep `role: safe_stop` on the stop. |
| `runner/main.py` | Replace `Axis` with your device. Keep the envelope, the refusal of out-of-bounds values and the separate stop. |

## The three capabilities

- `positioner.move_to` moves (`actuates: true`, `safety_class: movement`). Its
  one argument has a finite `min` and `max`; a value outside them is refused,
  never clamped. It is not idempotent, so a host never resends it blindly.
  Its evidence is judged by the host from the reported position, not from the
  runner's `ok`.
- `positioner.read_position` only reads.
- `positioner.halt` is the stop: its own capability, uncancellable, idempotent.

## Check it, offline

```bash
flyto pack conform examples/packs/adapter-template            # static checks, then the runner
flyto pack conform examples/packs/adapter-template --static-only
flyto pack conform my-pack --trusted-key vendor=vendor.pub --json > conformance.json
```

Run the full form against your simulator, or with the machine clear of
people: it calls the actuating capability once inside its bounds and once
outside them. What each check means and the version matrix:
[`ADAPTER_COMPATIBILITY_MATRIX.md`](../../../docs/specs/ADAPTER_COMPATIBILITY_MATRIX.md).

## Shipping it

```bash
flyto pack keygen --private vendor.key --public vendor.pub
flyto pack sign my-pack --key vendor.key --key-id vendor
flyto pack conform my-pack --trusted-key vendor=vendor.pub
```

A conformant report is not hardware acceptance. That needs the device, its
own receipts, a measured stop and an independent observation.
