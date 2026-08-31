# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What the http, network and dns modules are entitled to claim.

Eleven modules with about forty return paths between them, and the tests are
organised by the argument each rung rests on rather than by module, because
that is what a later edit would have to break.

Three things are pinned deliberately and would be easy to lose:

* Every return shape carries an envelope, not just the happy one. A contract
  attached only where things went well leaves a consumer reading
  ``data['outcome']`` raising KeyError on precisely the results somebody needed
  to look at, and -- worse -- silently claims nothing where it should say
  `indeterminate`.

* The rungs that rest on an ABSENCE are pinned individually: a ping with zero
  replies, a scan where nothing answered, a whois that parsed no field, a DNS
  answer with no records, an assert run with no assertions. Each of those is a
  payload that would be byte-identical if the effect had not happened, and each
  is the exact shape of the `file.write` bug this contract exists to stop. A
  future edit that promotes one of them to a confident rung has to delete a
  test that says why it is wrong.

* `http.response_assert` is the only VERIFIED in the group, so the tests that
  fence it in matter more than the one that grants it: no assertions is not a
  pass, a skipped check is not a pass, and the postcondition string that makes
  the rung legal names the limit of what was verified.

Local servers, real sockets, real subprocesses. The one thing mocked anywhere
below is `socket.getaddrinfo`, and only to reach resolver failures a test cannot
provoke without a network.
"""

import asyncio
import os
import socket
import sys

import pytest
from aiohttp import web

from core.engine.outcome import (
    ClaimBy,
    Outcome,
    ceiling_for,
    outranks,
    read_envelope,
)
from core.engine.step_executor.executor import step_outcome
from core.modules.registry import ModuleRegistry

from core.modules.atomic.dns.lookup import (
    _lookup_with_socket,
    _records_outcome,
    dns_lookup,
)
from core.modules.atomic.http.batch import http_batch
from core.modules.atomic.http.get import http_get
from core.modules.atomic.http.paginate import http_paginate
from core.modules.atomic.http.response_assert import (
    POSTCONDITION,
    http_response_assert,
)
from core.modules.atomic.http.session import _session_outcome, http_session
from core.modules.atomic.http.webhook_wait import _find_free_port, http_webhook_wait
from core.modules.atomic.network.ping import _ping_outcome, network_ping
from core.modules.atomic.network.port_scan import (
    PROBE_OPEN,
    PROBE_REFUSED,
    PROBE_SILENT,
    _probe_port,
    _scan_outcome,
    network_port_scan,
)
from core.modules.atomic.network.traceroute import _traceroute_outcome
from core.modules.atomic.network.whois import _whois_outcome, network_whois
from core.modules.errors import NetworkError, ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(module, **params):
    """One call through the wrapper `@register_module` actually stores."""
    return await module(params, {}).execute()


def _envelope(payload):
    """The envelope on a payload, insisting it is well-formed.

    `read_envelope` returns None for a dict whose `rung` is not a rung, so a
    typo in a module cannot pass here as a conservative claim.
    """
    found = read_envelope(payload)
    assert found is not None, f"no well-formed envelope on {payload!r}"
    return found


def _data_envelope(result):
    """The envelope where `to_legacy_dict` would leave it: inside `data`."""
    assert 'data' in result, f"result has no data key: {sorted(result)}"
    return _envelope(result['data'])


@pytest.fixture
def loopback_listener():
    """A real listening TCP socket on 127.0.0.1, and its port."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('127.0.0.1', 0))
    server.listen(8)
    yield server.getsockname()[1]
    server.close()


def _free_tcp_port():
    """A port nothing is listening on, released before it is used."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


async def _handle_ok(request):
    return web.json_response({'items': [1, 2], 'message': 'hello'})


async def _handle_500(request):
    return web.json_response({'error': 'boom'}, status=500)


async def _handle_page(request):
    pages = {1: ['a', 'b'], 2: ['c'], 3: []}
    page = int(request.rel_url.query.get('page', 1))
    return web.json_response({'results': pages.get(page, [])})


@pytest.fixture
async def server():
    """A real aiohttp server on loopback, reachable through the SSRF guard."""
    os.environ['FLYTO_ALLOW_PRIVATE_NETWORK'] = 'true'
    app = web.Application()
    app.router.add_route('*', '/ok', _handle_ok)
    app.router.add_route('*', '/boom', _handle_500)
    app.router.add_get('/page', _handle_page)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    yield f'http://127.0.0.1:{runner.addresses[0][1]}'
    await runner.cleanup()
    os.environ.pop('FLYTO_ALLOW_PRIVATE_NETWORK', None)


# ===========================================================================
# The rungs that rest on an ABSENCE
#
# Each case here produces a payload that would be identical if the effect had
# not happened. They are grouped together because they are one argument made
# five times, and because a future edit is far more likely to promote one of
# them than to invent a new rung outright.
# ===========================================================================


class TestAnAbsenceIsNeverAnObservation:
    def test_a_ping_with_no_replies_is_dispatched_not_observed(self):
        """`packets_transmitted` is real; `0 received` confirms nothing.

        DISPATCHED is the exactly-right rung and it is a real one, not a
        consolation: the packets left us and nobody acknowledged them, which is
        the bottom rung stated word for word.
        """
        found = _ping_outcome(
            summary_parsed=True, packets_sent=4, packets_received=0,
            exit_code=2, stderr_excerpt='',
        )
        assert found['rung'] == Outcome.DISPATCHED.value
        assert found['effects'][0]['kind'] == 'icmp_no_replies'

    def test_a_ping_whose_summary_did_not_parse_is_indeterminate(self):
        """The one that catches a fabricated 100% loss.

        With no summary line, `packets_received=0` and `packet_loss_pct=100.0`
        are the defaults this module initialises to -- the same values a
        genuinely dead host produces. The module still returns `ok: True`, so
        without this rung the result is a confident "host is down" that
        measured nothing at all.
        """
        found = _ping_outcome(
            summary_parsed=False, packets_sent=4, packets_received=0,
            exit_code=68, stderr_excerpt='ping: cannot resolve nope.invalid',
        )
        assert found['rung'] == Outcome.INDETERMINATE.value
        assert found['effects'][0]['measured_by'] is None

    def test_a_scan_where_nothing_answered_is_dispatched(self):
        """Every probe timed out, so `closed_ports` is a guess with a name."""
        found = _scan_outcome(
            host='example.test', ports_probed=16,
            open_count=0, refused_count=0, silent_count=16,
        )
        assert found['rung'] == Outcome.DISPATCHED.value
        assert found['effects'][0]['kind'] == 'tcp_no_response'

    def test_a_dns_answer_with_no_records_is_accepted_not_observed(self):
        """`records: []` reads the same as never having asked.

        The server did answer, which is why this is ACCEPTED rather than
        DISPATCHED -- but nothing in the payload says anything about the zone.
        """
        found = _records_outcome(
            domain='example.com', record_type='MX', records=[], ttl=None,
            resolver='dnspython',
        )
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['effects'][0]['measured_by'] is None

    def test_a_whois_that_parsed_nothing_is_accepted_not_observed(self):
        """Null registrar and dates are absences of a match, not facts.

        An unregistered domain and a ccTLD whose format these regexes do not
        cover produce the identical payload, so the rung cannot rest on it.
        Bytes did arrive, which ACCEPTED covers and OBSERVED would overstate.
        """
        found = _whois_outcome(
            domain='example.test', raw_bytes=42, parsed_fields=[],
            name_server_count=0, exit_code=0,
        )
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['effects'][0]['kind'] == 'whois_answered_unparsed'

    def test_a_traceroute_of_pure_asterisks_is_dispatched(self):
        """`total_hops` counts rows, and a row of `*` is not a router."""
        hops = [{'hop_number': n, 'ip': '*', 'hostname': '*'} for n in range(1, 6)]
        found = _traceroute_outcome(
            host='example.test', hops=hops, exit_code=0, stderr_excerpt='',
        )
        assert found['rung'] == Outcome.DISPATCHED.value
        assert found['effects'][0]['hops_parsed'] == 5
        assert found['effects'][0]['hops_identified'] == 0

    def test_an_assert_run_with_no_assertions_is_not_a_pass(self):
        """The vacuous green: `ok: True` for having checked nothing."""
        found = _run_assert_sync({'response': {'status': 200}})
        assert found['ok'] is True
        assert found['total'] == 0
        assert found['outcome']['rung'] == Outcome.INDETERMINATE.value


def _run_assert_sync(params):
    """`http.response_assert` is pure, so a loop per call is cheap and clear."""
    return asyncio.run(http_response_assert(params, {}).execute())


# ===========================================================================
# network.ping
# ===========================================================================


class TestPing:
    async def test_replies_from_loopback_are_observed(self):
        """A real ping, and the only rung in the group earned by counting.

        Loopback so this measures the ladder rather than the host's network:
        one packet, one reply, counted by `ping` itself.
        """
        result = await _run(network_ping, host='127.0.0.1', count=1, timeout=1)

        assert result['ok'] is True
        assert result['data']['packets_received'] >= 1
        found = _data_envelope(result)
        assert found['rung'] == Outcome.OBSERVED.value
        assert found['effects'][0]['kind'] == 'icmp_replies_counted'
        assert found['effects'][0]['exit_code'] == 0

    async def test_it_is_never_verified_because_nothing_declares_a_postcondition(self):
        """The ceiling, as a test rather than a comment.

        `ceiling_for(None)` is OBSERVED, and a reachable host is the best case
        this module has. Reaching for VERIFIED would need a predicate, and
        "the host answered ICMP" is not one anybody stated.
        """
        metadata = ModuleRegistry.get_metadata('network.ping') or {}
        assert metadata.get('postcondition') is None
        assert ceiling_for(None) is Outcome.OBSERVED

    def test_observed_outranks_the_answer_for_a_silent_host(self):
        """The two ping rungs are ordered, and in the direction that matters."""
        alive = _ping_outcome(
            summary_parsed=True, packets_sent=1, packets_received=1,
            exit_code=0, stderr_excerpt='',
        )
        silent = _ping_outcome(
            summary_parsed=True, packets_sent=1, packets_received=0,
            exit_code=2, stderr_excerpt='',
        )
        assert outranks(alive['rung'], silent['rung'])


# ===========================================================================
# network.port_scan
# ===========================================================================


class TestPortScan:
    async def test_an_accepted_connection_is_observed(self, loopback_listener):
        """A completed handshake, against a socket this test opened itself."""
        result = await _run(
            network_port_scan, host='127.0.0.1',
            ports=str(loopback_listener), timeout=2.0,
        )

        assert result['data']['open_ports'] == [loopback_listener]
        found = _data_envelope(result)
        assert found['rung'] == Outcome.OBSERVED.value
        assert found['effects'][0]['kind'] == 'tcp_connections_accepted'

    async def test_a_refusal_is_also_observed_because_the_host_answered(self):
        """No service found, and the machine's reachability still measured.

        This is the distinction the probe used to throw away: a RST is the host
        talking to us, and collapsing it into the same `False` as a timeout is
        what made `open_ports: []` unreadable.
        """
        port = _free_tcp_port()
        result = await _run(
            network_port_scan, host='127.0.0.1', ports=str(port), timeout=2.0,
        )

        assert result['data']['open_ports'] == []
        assert result['data']['closed_ports'] == [port]
        found = _data_envelope(result)
        assert found['rung'] == Outcome.OBSERVED.value
        assert found['effects'][0]['kind'] == 'tcp_connections_refused'
        assert found['effects'][0]['refused'] == 1

    async def test_the_probe_reports_which_of_the_three_happened(self, loopback_listener):
        """The measurement the rung rests on, tested where it is made."""
        assert await _probe_port('127.0.0.1', loopback_listener, 2.0) == PROBE_OPEN
        assert await _probe_port('127.0.0.1', _free_tcp_port(), 2.0) == PROBE_REFUSED

    def test_a_silent_scan_and_a_refused_scan_do_not_share_a_rung(self):
        """Identical `closed_ports`, different answers -- which is the point."""
        refused = _scan_outcome(
            host='h', ports_probed=1, open_count=0, refused_count=1, silent_count=0)
        silent = _scan_outcome(
            host='h', ports_probed=1, open_count=0, refused_count=0, silent_count=1)
        assert refused['rung'] == Outcome.OBSERVED.value
        assert silent['rung'] == Outcome.DISPATCHED.value
        assert PROBE_SILENT != PROBE_REFUSED


# ===========================================================================
# network.traceroute
# ===========================================================================


class TestTraceroute:
    def test_an_identified_hop_is_observed(self):
        """A router answered with its own address; nobody reported it to us."""
        hops = [
            {'hop_number': 1, 'ip': '192.0.2.1', 'hostname': 'gw', 'latency_ms': 1.0},
            {'hop_number': 2, 'ip': '*', 'hostname': '*', 'latency_ms': None},
        ]
        found = _traceroute_outcome(
            host='example.test', hops=hops, exit_code=0, stderr_excerpt='')

        assert found['rung'] == Outcome.OBSERVED.value
        assert found['effects'][0]['hops_identified'] == 1
        assert found['effects'][0]['last_identified_hop'] == '192.0.2.1'

    def test_nothing_parsed_is_indeterminate_not_a_zero_hop_route(self):
        """`total_hops: 0` with `ok: True` is the module initialising."""
        found = _traceroute_outcome(
            host='example.test', hops=[], exit_code=1,
            stderr_excerpt='traceroute: unknown host')

        assert found['rung'] == Outcome.INDETERMINATE.value
        assert found['effects'][0]['stderr_excerpt']

    def test_reaching_the_destination_is_not_claimed(self):
        """The rung is about the path seen, never about arrival.

        Nothing in this module resolves the target or compares it with the last
        hop, so a trace that stops five networks short reports the same
        OBSERVED as one that arrives. The effect says `hops_identified` and not
        `destination_reached` for that reason.
        """
        hops = [{'hop_number': 1, 'ip': '192.0.2.1', 'hostname': 'gw'}]
        found = _traceroute_outcome(
            host='example.test', hops=hops, exit_code=0, stderr_excerpt='')
        assert 'destination_reached' not in found['effects'][0]


# ===========================================================================
# network.whois
# ===========================================================================


class TestWhois:
    def test_a_parsed_record_is_observed(self):
        """Registration data extracted from bytes the registry sent."""
        found = _whois_outcome(
            domain='example.com', raw_bytes=2048,
            parsed_fields=['registrar', 'expiration_date'],
            name_server_count=2, exit_code=0,
        )
        assert found['rung'] == Outcome.OBSERVED.value
        assert found['effects'][0]['parsed_fields'] == ['expiration_date', 'registrar']

    async def test_a_domain_starting_with_a_dash_is_refused(self):
        """Argument injection into `whois`, closed.

        `domain` becomes argv[1], and whois parses its own options out of that
        position: "-h 169.254.169.254" is read as -h with a host attached, so
        the caller picks which server this connects to on port 43. No shell is
        involved, so this is argument injection rather than command injection,
        and the fix is the same shape -- refuse what cannot be a hostname.
        """
        with pytest.raises(ValidationError):
            await _run(network_whois, domain='-h 169.254.169.254')

    async def test_a_domain_containing_whitespace_is_refused(self):
        """The other half of the same guard; no legal domain has a space."""
        with pytest.raises(ValidationError):
            await _run(network_whois, domain='example.com -h evil.test')


# ===========================================================================
# dns.lookup
# ===========================================================================


class TestDnsLookup:
    async def test_records_from_the_socket_resolver_are_observed(self):
        """`localhost` resolves from /etc/hosts, so this needs no network."""
        result = await _lookup_with_socket('localhost', 'A', 5)

        assert result['ok'] is True
        assert result['data']['records']
        found = _data_envelope(result)
        assert found['rung'] == Outcome.OBSERVED.value
        assert found['effects'][0]['resolver'] == 'socket.getaddrinfo'

    async def test_an_empty_domain_is_failed_because_nothing_was_sent(self):
        result = await _run(dns_lookup, domain='   ')

        assert result['ok'] is False
        found = _data_envelope(result)
        assert found['rung'] == Outcome.FAILED.value

    async def test_a_missing_resolver_library_is_failed(self, monkeypatch):
        """Nothing left this process, so FAILED and not INDETERMINATE."""
        monkeypatch.setitem(sys.modules, 'dns', None)
        result = await _run(dns_lookup, domain='example.com', record_type='MX')

        assert result['error_code'] == 'MISSING_DEPENDENCY'
        assert _data_envelope(result)['rung'] == Outcome.FAILED.value

    async def test_eai_noname_is_failed_and_every_other_gaierror_is_not(
        self, monkeypatch
    ):
        """The split that decides whether retrying is meaningful.

        EAI_NONAME is the resolver saying the name does not resolve -- the same
        definite negative as NXDOMAIN. EAI_AGAIN is a temporary failure, and
        collapsing the two into one error state is what makes an automation
        give up on the recoverable one and hammer the hopeless one.
        """
        def _raise(errno):
            def _fail(*args, **kwargs):
                raise socket.gaierror(errno, 'boom')
            return _fail

        monkeypatch.setattr(socket, 'getaddrinfo', _raise(socket.EAI_NONAME))
        definite = await _lookup_with_socket('nope.invalid', 'A', 5)
        assert _data_envelope(definite)['rung'] == Outcome.FAILED.value

        monkeypatch.setattr(socket, 'getaddrinfo', _raise(socket.EAI_AGAIN))
        temporary = await _lookup_with_socket('nope.invalid', 'A', 5)
        assert _data_envelope(temporary)['rung'] == Outcome.INDETERMINATE.value

    async def test_a_resolver_timeout_is_indeterminate(self, monkeypatch):
        """A timeout is the textbook indeterminate: nobody said anything."""
        def _never(*args, **kwargs):
            import time as _time
            _time.sleep(3)
            return []

        monkeypatch.setattr(socket, 'getaddrinfo', _never)
        result = await _lookup_with_socket('slow.invalid', 'A', 0)

        assert result['error_code'] == 'TIMEOUT'
        assert _data_envelope(result)['rung'] == Outcome.INDETERMINATE.value

    async def test_every_socket_path_carries_an_envelope(self, monkeypatch):
        """The KeyError test: four shapes, four envelopes.

        A fifth added later without one fails here rather than in a consumer.
        """
        shapes = []
        shapes.append(await _lookup_with_socket('localhost', 'A', 5))

        def _fail(*args, **kwargs):
            raise socket.gaierror(socket.EAI_NONAME, 'boom')
        monkeypatch.setattr(socket, 'getaddrinfo', _fail)
        shapes.append(await _lookup_with_socket('nope.invalid', 'A', 5))

        def _boom(*args, **kwargs):
            raise RuntimeError('resolver exploded')
        monkeypatch.setattr(socket, 'getaddrinfo', _boom)
        shapes.append(await _lookup_with_socket('nope.invalid', 'A', 5))

        assert [_data_envelope(shape)['rung'] for shape in shapes] == [
            Outcome.OBSERVED.value,
            Outcome.FAILED.value,
            Outcome.INDETERMINATE.value,
        ]


# ===========================================================================
# http.get / http.request's argument, applied
# ===========================================================================


class TestHttpGet:
    async def test_a_2xx_is_accepted_and_no_higher(self, server):
        """A status line is the peer reporting on its own work.

        Not OBSERVED: nothing here reads the resource back. There is no second
        request and no comparison, only the answer to the very message we sent.
        """
        result = await _run(http_get, url=f'{server}/ok')

        found = _data_envelope(result)
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['claim_by'] == ClaimBy.NONE.value
        assert found['effects'][0]['status'] == 200
        assert outranks(ceiling_for(None), found['rung'])

    async def test_a_decoded_body_reports_no_byte_count(self, server):
        """The number this module refuses to invent.

        `len()` over a decoded string is characters and over a parsed object is
        a number of keys. Either one printed as `bytes_received` would read
        like a measurement of the wire and would not be one, so the field is
        null and `declared_content_length` is named for the claim it is.
        """
        result = await _run(http_get, url=f'{server}/ok')

        body_effect = _data_envelope(result)['effects'][1]
        assert body_effect['bytes_received'] is None
        assert body_effect['declared_content_length'] is not None

    async def test_a_non_2xx_raises_and_therefore_carries_no_rung(self, server):
        """The gap in this module, pinned so it is not mistaken for a rung.

        `http.get` signals failure by raising, and an exception has no payload
        for an envelope to live in. The INDETERMINATE that a timeout deserves
        is unattachable here until these paths return instead.
        """
        with pytest.raises(NetworkError):
            await _run(http_get, url=f'{server}/boom')


# ===========================================================================
# http.batch
# ===========================================================================


class TestHttpBatch:
    async def test_each_request_carries_its_own_rung(self, server):
        """Per request, because `data` is a list and per-batch would be lost.

        `wrap_legacy_result` turns each entry into its own Item and discards
        every sibling key at the top level, so a batch-level envelope could not
        be read. Each entry survives, and `step_outcome` walks them.
        """
        dead = _free_tcp_port()
        result = await _run(http_batch, requests=[
            {'url': f'{server}/ok', 'label': 'live'},
            {'url': f'http://127.0.0.1:{dead}/', 'label': 'dead'},
        ])

        live, no_answer = result['data']
        assert _envelope(live)['rung'] == Outcome.ACCEPTED.value
        assert _envelope(no_answer)['rung'] == Outcome.INDETERMINATE.value

    async def test_the_step_is_as_confirmed_as_its_weakest_request(self, server):
        """One unanswered probe makes the whole step indeterminate."""
        dead = _free_tcp_port()
        result = await _run(http_batch, requests=[
            {'url': f'{server}/ok'},
            {'url': f'http://127.0.0.1:{dead}/'},
        ])

        rung, _claim_by, _expected = step_outcome(result)
        assert rung is Outcome.INDETERMINATE

    async def test_a_non_2xx_is_still_accepted(self, server):
        """The rung answers "how far", not "did it succeed".

        A 500 is the peer receiving the probe and choosing a reply just as much
        as a 200 is -- and for the pentest batches this module exists for, the
        500 is frequently the finding. `ok` beside it carries success.
        """
        result = await _run(http_batch, requests=[{'url': f'{server}/boom'}])

        entry = result['data'][0]
        assert entry['ok'] is False
        assert _envelope(entry)['rung'] == Outcome.ACCEPTED.value

    async def test_a_byte_count_here_is_a_real_byte_count(self, server):
        """Unlike `http.get`, this module reads bytes and decodes afterwards."""
        result = await _run(http_batch, requests=[{'url': f'{server}/ok'}])

        effect = _envelope(result['data'][0])['effects'][0]
        assert effect['bytes_received'] > 0

    async def test_an_empty_batch_is_failed(self):
        """Nothing was sent, which is knowable rather than unknown."""
        result = await _run(http_batch, requests=[])

        assert result['ok'] is False
        assert _envelope(result)['rung'] == Outcome.FAILED.value

    async def test_an_ssrf_refusal_is_failed_for_the_whole_batch(self):
        """The gate runs over every request before the session opens."""
        result = await _run(http_batch, requests=[
            {'url': 'http://169.254.169.254/latest/meta-data/'},
        ])

        assert result['error_code'] == 'SSRF_BLOCKED'
        assert _envelope(result)['rung'] == Outcome.FAILED.value


# ===========================================================================
# http.session
# ===========================================================================


class TestHttpSession:
    async def test_the_step_rung_is_the_weakest_request(self, server):
        """Two levels of envelope, and the top one is a minimum.

        `results` is a key inside `data` that `_outcome_payloads` does not
        descend into, so the step-level envelope has to exist and has to be the
        weakest -- a login that timed out followed by two 200s is not an
        accepted session.
        """
        result = await _run(http_session, requests=[
            {'url': f'{server}/ok', 'label': 'one'},
            {'url': f'{server}/boom', 'label': 'two'},
        ], stop_on_error=False)

        assert [_envelope(entry)['rung'] for entry in result['results']] == [
            Outcome.ACCEPTED.value, Outcome.ACCEPTED.value,
        ]
        assert _envelope(result)['rung'] == Outcome.ACCEPTED.value

    async def test_stop_on_error_is_visible_in_the_effect(self, server):
        """Requests after the break did not happen and are not a rung.

        They are not DISPATCHED either. `requests_declared` beside
        `requests_attempted` is how a reader sees how much of the sequence the
        rung is about.
        """
        result = await _run(http_session, requests=[
            {'url': f'{server}/boom'},
            {'url': f'{server}/ok'},
        ], stop_on_error=True)

        effect = _envelope(result)['effects'][0]
        assert effect['requests_declared'] == 2
        assert effect['requests_attempted'] == 1

    async def test_an_ssrf_refusal_makes_the_session_failed(self):
        """FAILED wins over everything: nothing left this machine."""
        result = await _run(http_session, requests=[
            {'url': 'http://169.254.169.254/latest/meta-data/'},
        ])

        assert _envelope(result['results'][0])['rung'] == Outcome.FAILED.value
        assert _envelope(result)['rung'] == Outcome.FAILED.value

    async def test_no_requests_is_failed(self):
        result = await _run(http_session, requests=[])
        assert _envelope(result)['rung'] == Outcome.FAILED.value

    def test_failed_is_reported_ahead_of_indeterminate(self):
        """A session carrying both reports the one somebody has to act on."""
        from core.engine.outcome import envelope as _envelope_of

        mixed = _session_outcome(
            results=[
                {'status': None, 'outcome': _envelope_of(Outcome.INDETERMINATE)},
                {'status': None, 'outcome': _envelope_of(Outcome.FAILED)},
            ],
            requests_declared=2,
            cookie_count=0,
        )
        assert mixed['rung'] == Outcome.FAILED.value


# ===========================================================================
# http.paginate
# ===========================================================================


class TestHttpPaginate:
    async def test_pages_that_came_back_are_accepted(self, server):
        result = await _run(
            http_paginate, url=f'{server}/page', strategy='page',
            data_path='results', page_size=2, max_pages=5,
        )

        assert result['ok'] is True
        found = _envelope(result)
        assert found['rung'] == Outcome.ACCEPTED.value
        assert found['effects'][0]['pages_fetched'] == result['pages_fetched']

    async def test_the_effect_says_a_page_is_a_parsed_body_not_a_2xx(self, server):
        """The gap named in the data, because the count cannot see it.

        Nothing in this module inspects a status code, so a 500 whose body is
        JSON counts as a fetched page and contributes whatever its body held.
        `measured_by` says "responses whose body parsed as JSON" rather than
        "pages of data", which is the difference between a description and a
        claim.
        """
        result = await _run(
            http_paginate, url=f'{server}/boom', strategy='page',
            data_path='results', max_pages=1,
        )

        found = _envelope(result)
        assert found['rung'] == Outcome.ACCEPTED.value
        assert 'parsed as JSON' in found['effects'][0]['measured_by']
        assert result['total_items'] == 0

    async def test_an_unknown_strategy_is_failed(self, server):
        """Refused before anything was sent."""
        result = await _run(http_paginate, url=f'{server}/page', strategy='nope')

        assert result['error_code'] == 'INVALID_STRATEGY'
        assert _envelope(result)['rung'] == Outcome.FAILED.value

    async def test_an_ssrf_refusal_is_failed(self):
        result = await _run(
            http_paginate, url='http://169.254.169.254/', strategy='page')

        assert result['error_code'] == 'SSRF_BLOCKED'
        assert _envelope(result)['rung'] == Outcome.FAILED.value

    async def test_every_return_carries_an_envelope(self, server):
        """All seven returns go through `_make_result`, so all seven do."""
        shapes = [
            await _run(http_paginate, url=f'{server}/page', strategy='page',
                       data_path='results', max_pages=1),
            await _run(http_paginate, url=f'{server}/page', strategy='nope'),
            await _run(http_paginate, url='http://169.254.169.254/', strategy='page'),
        ]
        assert all(read_envelope(shape) is not None for shape in shapes)


# ===========================================================================
# http.webhook_wait -- the one that observes, and the one that measures a
# rejection nothing else could see
# ===========================================================================


class TestWebhookWait:
    async def test_a_received_callback_is_observed(self):
        """Traffic in the other direction, and the only OBSERVED in http.

        Somebody else's request arrives at a socket we opened and is read off
        it. Nothing is taken on anyone's word.
        """
        import aiohttp

        port = _find_free_port()
        waiting = asyncio.create_task(
            _run(http_webhook_wait, port=port, path='/hook', timeout=10)
        )

        async with aiohttp.ClientSession() as client:
            for _ in range(100):
                try:
                    async with client.get(f'http://127.0.0.1:{port}/health'):
                        break
                except aiohttp.ClientError:
                    await asyncio.sleep(0.05)
            async with client.post(
                f'http://127.0.0.1:{port}/hook', json={'event': 'ping'}
            ) as response:
                assert response.status == 200

        result = await asyncio.wait_for(waiting, timeout=15)

        assert result['ok'] is True
        found = _envelope(result)
        assert found['rung'] == Outcome.OBSERVED.value
        assert found['effects'][0]['method'] == 'POST'
        assert found['effects'][0]['body_bytes'] > 0

    async def test_it_stops_at_observed_because_nothing_authenticates_it(self):
        """The gap between OBSERVED and VERIFIED, stated in the effect.

        No signature, no shared secret, no schema: anything that can reach the
        port sets the event. So this observes that A callback arrived, never
        that the right one did.
        """
        metadata = ModuleRegistry.get_metadata('http.webhook_wait') or {}
        assert metadata.get('postcondition') is None

    async def test_a_timeout_is_indeterminate_and_counts_405s(self):
        """The failure that used to leave no trace whatsoever.

        A webhook arriving with the wrong method is answered 405 and never sets
        the event, so the run reported a plain timeout while the sender had a
        405 in its logs. `rejected_method` is the measurement that tells those
        two timeouts apart.
        """
        import aiohttp

        port = _find_free_port()
        waiting = asyncio.create_task(
            _run(http_webhook_wait, port=port, path='/hook',
                 timeout=2, expected_method='POST')
        )

        async with aiohttp.ClientSession() as client:
            for _ in range(100):
                try:
                    async with client.get(f'http://127.0.0.1:{port}/health'):
                        break
                except aiohttp.ClientError:
                    await asyncio.sleep(0.05)
            async with client.get(f'http://127.0.0.1:{port}/hook') as response:
                assert response.status == 405

        result = await asyncio.wait_for(waiting, timeout=15)

        assert result['error_code'] == 'TIMEOUT'
        found = _envelope(result)
        assert found['rung'] == Outcome.INDETERMINATE.value
        assert found['effects'][0]['rejected_method'] == 1


# ===========================================================================
# http.response_assert -- the only VERIFIED in the group
# ===========================================================================


class TestResponseAssert:
    def test_assertions_that_held_are_verified_by_the_caller(self):
        """A postcondition was evaluated and it held, which is the definition.

        `claim_by` is CALLER because the predicates came from parameters, and
        that is also what makes the failing case FAILED rather than
        INDETERMINATE: there is a stated contract to break.
        """
        result = _run_assert_sync({
            'response': {'status': 200, 'body': '{"ok": true}'},
            'status': 200,
            'body_contains': 'ok',
        })

        found = _envelope(result)
        assert found['rung'] == Outcome.VERIFIED.value
        assert found['claim_by'] == ClaimBy.CALLER.value
        assert found['postcondition'] == POSTCONDITION

    def test_the_postcondition_names_the_limit_of_what_was_verified(self):
        """The clause that stops this from being a false green.

        This module opens no socket. It grades a response another step
        captured, and cannot know whether that response is stale, from a
        different request, or a literal the caller typed. `verified` here means
        the assertions held over the recorded response -- never that the HTTP
        effect it describes happened.
        """
        metadata = ModuleRegistry.get_metadata('http.response_assert') or {}
        assert metadata['postcondition'] == POSTCONDITION
        assert 'supplied by the caller' in POSTCONDITION
        assert ceiling_for(metadata['postcondition']) is Outcome.VERIFIED

    def test_a_broken_assertion_is_failed_not_indeterminate(self):
        result = _run_assert_sync({
            'response': {'status': 500},
            'status': 200,
        })

        found = _envelope(result)
        assert result['ok'] is False
        assert found['rung'] == Outcome.FAILED.value
        assert found['claim_by'] == ClaimBy.CALLER.value
        assert found['effects'][0]['first_failure'] == 'status'

    def test_a_status_supplied_as_a_string_asserts_nothing(self):
        """The vacuous pass, reachable by accident.

        `_assert_status` branches on int, on list and on a "200-299" range
        string, and has none for a bare "200" -- which is what a resolved
        template hands it. Nothing is evaluated, `ok` is True, and only the
        rung says so.
        """
        result = _run_assert_sync({'response': {'status': 200}, 'status': '200'})

        assert result['ok'] is True
        assert result['total'] == 0
        assert _envelope(result)['rung'] == Outcome.INDETERMINATE.value

    def test_a_check_that_could_not_run_is_not_a_check_that_failed(
        self, monkeypatch
    ):
        """A missing library is INDETERMINATE, not a broken contract.

        Without the skip marker this lands as a failed assertion, and the run
        reports FAILED for a reason that has nothing to do with the response.
        """
        monkeypatch.setitem(sys.modules, 'jsonschema', None)
        result = _run_assert_sync({
            'response': {'status': 200, 'body': '{"a": 1}'},
            'status': 200,
            'schema': {'type': 'object'},
        })

        found = _envelope(result)
        assert result['ok'] is False
        assert found['rung'] == Outcome.INDETERMINATE.value
        assert found['effects'][0]['skipped'] == 1

    def test_a_real_failure_beside_a_skip_is_still_failed(self, monkeypatch):
        """Precedence, matching `step_outcome`: the actionable answer wins."""
        monkeypatch.setitem(sys.modules, 'jsonschema', None)
        result = _run_assert_sync({
            'response': {'status': 500, 'body': '{"a": 1}'},
            'status': 200,
            'schema': {'type': 'object'},
        })

        assert _envelope(result)['rung'] == Outcome.FAILED.value

    def test_fail_fast_records_that_the_run_was_cut_short(self):
        """`total: 1` must be distinguishable from "one check was asked for"."""
        result = _run_assert_sync({
            'response': {'status': 500, 'body': 'nope'},
            'status': 200,
            'body_contains': 'yes',
            'fail_fast': True,
        })

        assert result['stopped_early'] is True
        assert _envelope(result)['effects'][0]['stopped_early'] is True


# ===========================================================================
# Where the envelope has to live
# ===========================================================================


class TestTheEnvelopeSurvivesTheStepBoundary:
    async def test_a_data_dict_module_keeps_its_envelope_through_the_wrapper(self):
        """`to_legacy_dict` returns exactly {ok, data} and drops every sibling.

        The modules here that return `{'ok', 'data'}` put the envelope inside
        `data`; the ones that return a flat dict rely on `wrap_legacy_result`
        sweeping their fields into `data`. Both are checked, because getting
        this wrong loses the contract silently.
        """
        from core.modules.items import items_to_legacy_context, wrap_legacy_result

        nested = await _run(network_ping, host='127.0.0.1', count=1, timeout=1)
        legacy = items_to_legacy_context(wrap_legacy_result(nested))
        assert read_envelope(legacy['data']) is not None

    def test_a_flat_dict_module_keeps_its_envelope_through_the_wrapper(self):
        from core.modules.items import items_to_legacy_context, wrap_legacy_result

        flat = _run_assert_sync({'response': {'status': 200}, 'status': 200})
        assert 'data' not in flat
        legacy = items_to_legacy_context(wrap_legacy_result(flat))
        assert read_envelope(legacy['data']) is not None
