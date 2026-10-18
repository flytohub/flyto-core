# Flyto2 optional IoT ecosystem adapters

Independent installation (not part of the default flyto-core dependencies or
execution engine). These examples bind to the released Core module registry
and the flyto2.external_adapters entry point. Cloud/AI Space retain assignment,
approval, task dispatch authority, physical safety policy and final mission
evidence.

## Actual implementation status

| Integration | Implemented here | Not established |
|---|---|---|
| W3C WoT TD 1.1 | Passive, bounded Property/Action/Event import to DISCOVERED offers, admitted only when the TD validates against the vendored official W3C TD 1.1 JSON Schema; write-only properties refused (no observation meaning); export requires real authenticated forms and is itself schema-validated | Import does not approve a device, invoke arbitrary form URLs or prove a device's safe/idempotent claim; `@type` annotations never select a Flyto2 capability |
| Home Assistant | Read entity states; discover lights, switches and sensors; exact light/switch on/off; SQLite intent saved before HTTP; verify observed HA state; no automatic replay of unknown outcomes | Logical HA state is not independent physical evidence; no real live HA acceptance |
| MQTT | Optional paho TLS exact-topic subscription; read-only fresh JSON scalar telemetry; retained samples are ignored | No publish, control, device-side ACK or real broker acceptance |
| Open-RMF | Existing flyto-robotics Open-RMF adapter is reused, not duplicated | Multi-fleet live dispatch and host restart recovery not tested here |
| Matter | Via an authorized Home Assistant Matter integration when exposed as supported HA entities | No native Matter commissioning/controller |
| OPC UA | Not implemented, so there are no OPC UA mapping tests: a mapping test needs a real adapter to test | Requires an adapter, an industrial test endpoint, vendor contract and independent acceptance |
| Viam | Not implemented | Requires authorized Viam machine / SDK integration |
| NVIDIA Isaac Sim | Not implemented | Requires simulator installation, GPU/physics acceptance and license review |

Tuya native API is also not implemented; avoid adding provider-specific code
to flyto-core itself. Do not claim the remaining providers are production-ready.

## Installation (Python 3.10+)

    python -m pip install -e ./examples/integrations
    python -m pip install -e './examples/integrations[mqtt]'

The optional package registers:

- flyto.modules = homeassistant: ha.observe, ha.turn_on, ha.turn_off,
  mqtt.observe. All use the existing Core capability.invoke dispatcher.
- flyto2.external_adapters = homeassistant.entity, mqtt.sensor.

The host must approve discovered resources and capabilities before execution.
For a Home Assistant instance, configure the *trusted execution host* with
FLYTO_HA_URL, FLYTO_HA_TOKEN and FLYTO_HA_LEDGER (persistent private path).
Example resource: homeassistant:light.lobby. HTTP requires an explicit
FLYTO_HA_ALLOW_LOCAL_HTTP=1 for a private/local address; otherwise TLS.
Tokens never appear in a task, manifest, evidence record or the ledger.

**Important:** The SQLite ledger is the single local durable authority for a
bound physical resource and must survive host restart. Do not let two
independent hosts keep separate ledgers for the same resource. Cloud still
needs a single binding and persisted dispatch intent. Ambiguous HTTP outcome
does not permit an automatic second effect. The operator must reconcile with
independent evidence. This reference does not ship cross-host persistence.

MQTT resource: mqtt:ward/temperature. Configure FLYTO_MQTT_HOST, optional
FLYTO_MQTT_PORT (default 8883), FLYTO_MQTT_USER and FLYTO_MQTT_PASSWORD.
MQTT only reads an exact topic with TLS and limited freshness; there is no
command publish, and retained deliveries are not counted as fresh telemetry.

## Regression checks

    PYTHONPATH=examples/integrations:src python3.11 -m pytest -o addopts='' examples/integrations/tests -q
    ruff check examples/integrations

`tests/test_wot_td11_conformance.py` pins the vendored schema by SHA-256 and
asserts that the adapter never admits a TD the official schema refuses, that
the TD 1.1 Recommendation example maps forward to vendor offers, and that an
approved export validates and maps back to the same offers.

Tests use real SQLite transactions and mocked external transports, not a
real light, PLC, robot, MQTT broker or Viam/Matter device. They cover
malformed WoT imports, approval isolation, authenticated form export, duplicate
intent collisions, lost HTTP acknowledgement, failed observation, MQTT
topic/freshness/retained rules and actual Core registry integration.

Before real deployment, run authorized HA end-to-end acceptance (including
disconnect, reboot, state delay and permission denial), bind resources in AI
Space, exercise full Cloud task evidence, test the existing Open-RMF adapter
through host restart, then separately certify other vendor/industrial SDKs.
