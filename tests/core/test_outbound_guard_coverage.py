# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Registry-wide coverage for the outbound network boundary.

The SSRF sibling of ``test_write_sink_coverage.py``, and the same story: the
guards in ``core/utils.py`` are centralized and correct, but calling them was a
thing an author had to remember, so the published advisories
(GHSA-pgwh-4jj4-qm8v, GHSA-c9hr-64h3-gxpc, GHSA-jx74-cqjv-2c67,
GHSA-cjg2-qmrg-6h4h, GHSA-6whm-vq2p-8m93, GHSA-h8xc-824q-pwfh,
GHSA-2mr3-rxrq-238c, GHSA-662f-hr85-mg6c, GHSA-v7q9-pr72-5fmv) are all
"this one module didn't". This walks every registered module and fails the
build on any outbound parameter that never reaches a guard.

Two things make this stricter than a plain grep:

* **MRO-aware.** ``agent.chain`` and ``agent.autonomous`` inherit their guard
  from ``LLMClientMixin`` in another file. Scanning only the defining module
  would report them as unguarded and train the reader to ignore this test.
* **The allowlist is verified, not trusted.** A module excused for
  implementing its own validation must still contain that validator
  (:func:`test_local_validator_allowlist_still_has_its_validator`), and a
  module excused for making no request must still make none
  (:func:`test_no_request_allowlist_makes_no_outbound_call`).

Adding a module with a URL or host parameter therefore forces one of two
explicit acts: call a guard, or write down why the parameter never reaches the
network.
"""

import re
import sys
from pathlib import Path

import pytest

from core.modules import atomic  # noqa: F401 — registers the module catalog
from core.modules.integrations import jira, salesforce, slack  # noqa: F401
from core.modules.registry.core import ModuleRegistry

# The integration.* families are imported explicitly above because nothing else
# in the package imports them, so they never reached this sweep — the whole
# family shares one unguarded sink and none of it was visible here
# (GHSA-4346-4gqg-59f9). Security coverage tracks the source tree, not whichever
# subset a default import happens to register.

# Parameter names that denote an outbound network target. `connection_string`
# and friends are here because GHSA-9x26-9vhm-2qhw was a DSN: a whole target
# packed into one string, named nothing like a host, and therefore invisible to
# this sweep while the sibling that spelled its target `host` was guarded.
OUTBOUND_PARAM_RE = re.compile(
    r"(^|_)(url|urls|uri|endpoint|endpoints|host|hostname|origin|webhook"
    r"|callback|server|proxy|connection_string|connection_uri|dsn"
    r"|domain|domains)$"
)

# The guards in core/utils.py, plus the browser driver's navigation/egress
# guards. Referencing any of them counts as reaching the boundary.
#
# `assert_env_credential_endpoint_allowed` is deliberately NOT in this list,
# though it is a security check on the same parameter. It answers "may the
# operator's key travel there", permits any public host by design, and no-ops
# entirely when the caller supplies its own key. Counting it here is what let
# `llm.agent` read as guarded while it fetched a caller-supplied `base_url` with
# no SSRF check at all — GHSA-pp5w-w9c3-qfv2 and GHSA-f9q4-fp8j-r5h7, two
# reporters on one unguarded parameter. A guard list is only as good as its
# weakest member's actual promise.
GUARD_SYMBOLS = (
    "validate_url_ssrf",
    "validate_url_with_env_config",
    "enforce_outbound_url",
    "enforce_outbound_host",
    "enforce_outbound_service_url",
    "enforce_azure_endpoint",
    "guarded_aiohttp_request",
    "guarded_client_session",
    "ssrf_guarded_connector",
    "trusted_outbound_network_scope",
    "guard_client_dsn",
    "enforce_dsn_target",
    "is_private_ip",
    "resolve_guard_ip",
    "_guard_navigation",
)

# Anything that opens a connection. Used for the no-request allowlist tripwire.
# Groups are non-capturing on purpose: re.findall returns group contents when a
# pattern has capturing groups, which silently yields empty strings instead of
# the matched call and makes the tripwire fire on modules it should not.
OUTBOUND_CALL_RE = re.compile(
    r"\baiohttp\.|\bhttpx\.|\brequests\.(?:get|post|put|patch|delete|head|request)\("
    r"|urllib\.request|urlopen\("
    r"|socket\.create_connection|connect_over_cdp\("
    r"|smtplib\.|aioredis|from_url\("
    r"|\.goto\(|\.fetch\("
)


# Parameters that match OUTBOUND_PARAM_RE but never become a network target.
NO_REQUEST_PARAMS = {
    "dns.lookup": {
        "domain": "the name being resolved, sent as a query to the system "
                  "resolver; this module opens no connection to the domain itself"
    },
    "network.whois": {
        "domain": "an argv element for the whois client, which picks the registry "
                  "server itself; the caller does not choose what is connected to"
    },
    "browser.cookies": {
        "domain": "a cookie attribute used to scope or filter jar entries; no "
                  "navigation or request is made to it"
    },
    "validate.url": {
        "url": "parsed with urlparse and reported on; the module never requests it"
    },
    "verify.report": {
        "url": "echoed into the generated report as a label; never fetched"
    },
    "warroom.public_site_verify": {
        "base_url": "labels the report; the observations are supplied by the caller, "
                    "this module does not visit the site"
    },
    "flow.trigger": {
        "poll_url": "emitted as trigger metadata for the scheduler to act on; this "
                    "module performs no polling itself"
    },
    "browser.throttle": {
        "url": "rate-limit bucket key for pacing decisions, not a request target"
    },
    "browser.frame": {
        "url": "selects which already-loaded iframe to switch into; no navigation"
    },
    "browser.robots": {
        "check_url": "matched against robots.txt rules; the fetch is of the current "
                     "page's own origin, not of this value"
    },
    "reverse.breakpoint": {
        "url": "passed to CDP only as a filter for scripts already loaded in the "
               "attached page; this module never requests the URL"
    },
    "reverse.request_breakpoint": {
        "url": "passed to CDP only as an XHR/fetch breakpoint substring; it does "
               "not initiate the matching request"
    },
    "training.practice.analyze": {
        "url": "passed to the OSS DailyPracticeEngine stub as report input; the "
               "module and engine make no outbound request"
    },
    "training.practice.execute": {
        "url": "passed to the OSS DailyPracticeEngine stub as practice metadata; "
               "the module and engine make no outbound request"
    },
    "training.practice.infer_schema": {
        "url": "passed to the OSS DailyPracticeEngine stub as schema metadata; "
               "the module and engine make no outbound request"
    },
    "testing.http.run_suite": {
        "base_url": "placeholder implementation; returns canned results without "
                    "issuing any request"
    },
}

# Parameters excused for a reason that a marker in the source can attest to:
# the module validates locally instead of calling a shared guard, the value is
# handed to a third party rather than requested here, or the request is
# delegated to a component that guards it and the marker attests to that
# delegation. The first element
# is the marker that must still be present; if it disappears, the exemption is
# void and the test fails.
LOCAL_VALIDATOR_PARAMS = {
    "integration.jira.create_issue": {
        "domain": (
            "credentials_from_env=self.credentials_from_env",
            "the request is delegated to BaseIntegration._request, which runs "
            "enforce_outbound_url and the env-credential target guard on the URL "
            "built from this domain. The marker is the provenance flag the "
            "wrapper must pass for that credential guard to work at all; without "
            "it the operator's token is indistinguishable from the caller's and "
            "the exemption is void",
        )
    },
    "integration.jira.search_issues": {
        "domain": (
            "credentials_from_env=self.credentials_from_env",
            "same delegation to BaseIntegration._request as create_issue; the "
            "marker is the credential-provenance flag that guard depends on",
        )
    },
    "integration.salesforce.query": {
        "instance_url": (
            "credentials_from_env=self.credentials_from_env",
            "the request is delegated to BaseIntegration._request, which guards "
            "the URL built from this instance_url; the marker is the credential-"
            "provenance flag that guard depends on",
        )
    },
    "integration.salesforce.create_record": {
        "instance_url": (
            "credentials_from_env=self.credentials_from_env",
            "same delegation to BaseIntegration._request as query; the marker is "
            "the credential-provenance flag that guard depends on",
        )
    },
    "integration.salesforce.update_record": {
        "instance_url": (
            "credentials_from_env=self.credentials_from_env",
            "same delegation to BaseIntegration._request as query; the marker is "
            "the credential-provenance flag that guard depends on",
        )
    },
    "communication.twilio.make_call": {
        "twiml_url": (
            "'Url': self.twiml_url",
            "passed to Twilio's REST API as the 'Url' form field, so Twilio's "
            "infrastructure fetches it — this runner never does. The marker is "
            "that hand-off; if the module starts requesting the value itself "
            "the marker goes and this exemption fails",
        )
    },
    "browser.sitemap": {
        "sitemap_url": (
            "_SITEMAP_JS",
            "fetched by in-page JavaScript, so it is covered by the browser "
            "egress guard (driver._install_egress_guard) rather than a Python call",
        ),
        "max_urls": ("_SITEMAP_JS", "an integer cap, not a URL; matches the name rule only"),
    },
}


# Captured at import, before any test can mutate the registry. Several suites
# snapshot and restore ModuleRegistry, and the integration.* families are only
# in the catalog because this file imported them — a coverage gate whose view of
# the catalog depends on test ordering is not a gate.
_CATALOG = dict(ModuleRegistry.get_all_metadata(filter_by_stability=False))
_MODULE_CLASSES = {module_id: ModuleRegistry.get(module_id) for module_id in _CATALOG}


def _module_sources(module_id: str):
    """Every file that can hold this module's guard: its own, plus its MRO.

    Mixins matter here — LLMClientMixin carries the ollama_url guard for
    agent.chain and agent.autonomous, which live in different files.
    """
    module_class = _MODULE_CLASSES[module_id]
    paths, seen = [], set()

    for klass in module_class.__mro__:
        module = sys.modules.get(klass.__module__)
        path = getattr(module, "__file__", None)
        if path and path not in seen and "/core/base" not in path:
            seen.add(path)
            paths.append(Path(path))

    wrapped = getattr(module_class, "__wrapped_func__", None)
    if wrapped is not None:
        module = sys.modules.get(wrapped.__module__)
        path = getattr(module, "__file__", None)
        if path and path not in seen:
            paths.append(Path(path))

    return paths


def _source_blob(module_id: str) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in _module_sources(module_id))


def _registry_outbound_params():
    # Security coverage must include beta/experimental modules. Runtime
    # visibility filters are product policy, not a reason to omit a sink from
    # CI boundary checks.
    for module_id, metadata in sorted(_CATALOG.items()):
        schema = metadata.get("params_schema") or {}
        names = sorted(n for n in schema if OUTBOUND_PARAM_RE.search(n))
        if names:
            yield module_id, names


def test_registry_is_populated():
    """Guard against the suite passing vacuously on an empty registry."""
    assert len(_CATALOG) > 300
    assert sum(1 for _ in _registry_outbound_params()) > 40


def test_every_outbound_param_module_reaches_a_guard():
    """No module may take a URL or host parameter without reaching a guard.

    A failure here is the precondition for every SSRF advisory this project has
    published.
    """
    offenders = []

    for module_id, names in _registry_outbound_params():
        if any(symbol in _source_blob(module_id) for symbol in GUARD_SYMBOLS):
            continue

        excused = set(NO_REQUEST_PARAMS.get(module_id, {}))
        excused |= set(LOCAL_VALIDATOR_PARAMS.get(module_id, {}))
        unexplained = [name for name in names if name not in excused]
        if unexplained:
            offenders.append(f"{module_id}: {unexplained}")

    assert not offenders, (
        "These modules take an outbound network parameter but never reach an "
        "SSRF guard:\n  "
        + "\n  ".join(offenders)
        + "\n\nCall enforce_outbound_url (HTTP), enforce_outbound_service_url "
          "(redis://, ws://, proxies) or enforce_outbound_host (raw TCP: DB, "
          "SMTP, SSH) — or record the parameter in NO_REQUEST_PARAMS / "
          "LOCAL_VALIDATOR_PARAMS with a reason."
    )


@pytest.mark.parametrize("module_id", sorted(NO_REQUEST_PARAMS))
def test_no_request_allowlist_makes_no_outbound_call(module_id):
    """A 'never requests it' exemption is void once the module makes a request.

    ``testing.http.run_suite`` is a placeholder today; the day it is implemented
    it will open a connection, fail here, and have to be guarded — rather than
    inheriting an exemption written when it did nothing.
    """
    calls = sorted(set(OUTBOUND_CALL_RE.findall(_source_blob(module_id))))

    assert not calls, (
        f"{module_id} is in NO_REQUEST_PARAMS on the grounds that it issues no "
        f"outbound request, but its sources now contain {calls}. Route the "
        f"parameter through a guard and drop the exemption."
    )


@pytest.mark.parametrize("module_id", sorted(LOCAL_VALIDATOR_PARAMS))
def test_local_validator_allowlist_still_has_its_validator(module_id):
    """A module excused for validating locally must still do so.

    Without this, deleting the inline check would silently convert a documented
    exemption into an unguarded module.
    """
    blob = _source_blob(module_id)
    missing = [
        f"{name} (expected marker: {marker!r})"
        for name, (marker, _reason) in LOCAL_VALIDATOR_PARAMS[module_id].items()
        if marker not in blob
    ]

    assert not missing, (
        f"{module_id} is excused from the shared guard because it validates "
        f"locally, but that validation is gone: {missing}. Either restore it or "
        f"switch the module to the shared guard."
    )


def test_allowlists_have_no_stale_entries():
    """Allowlisted modules and parameters must still exist and still match."""
    live = dict(_registry_outbound_params())
    stale = []

    for label, table in (
        ("NO_REQUEST_PARAMS", NO_REQUEST_PARAMS),
        ("LOCAL_VALIDATOR_PARAMS", LOCAL_VALIDATOR_PARAMS),
    ):
        for module_id, params in table.items():
            if module_id not in live:
                stale.append(f"{label}: {module_id} no longer takes an outbound param")
                continue
            for name in params:
                if name not in live[module_id]:
                    stale.append(f"{label}: {module_id}.{name} is gone")

    assert not stale, "Allowlists have drifted from the registry:\n  " + "\n  ".join(stale)


def test_allowlist_entries_state_a_reason():
    """A bare exemption is not reviewable; require a real sentence."""
    thin = [
        f"{module_id}.{name}"
        for module_id, params in NO_REQUEST_PARAMS.items()
        for name, reason in params.items()
        if len(reason.strip()) < 25
    ]
    thin += [
        f"{module_id}.{name}"
        for module_id, params in LOCAL_VALIDATOR_PARAMS.items()
        for name, (_marker, reason) in params.items()
        if len(reason.strip()) < 25
    ]
    assert not thin, f"These allowlist entries need a substantive reason: {thin}"
