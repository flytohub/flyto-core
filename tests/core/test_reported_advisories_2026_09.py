"""Regression coverage for the 2026-09-17..23 security reports.

Six reports, six sinks:

* GHSA-hc4c-6x9g-5fq3 — `_extract_embedded_ipv4` decoded five of the six IPv6
  transition forms. The Teredo encoding of 169.254.169.254 passed every guard
  that depends on it, including the connect-time resolver.
* GHSA-m5gf-24gv-m9g8 — the verification callback checked `callback_url` once
  and then posted the runner secret through a plain session that resolved the
  host again (and followed redirects with the secret header attached).
* GHSA-8j62-f337-86xw — the aiohttp fallback of `llm._chat_models._http_post`
  (the branch a base install without httpx runs) had no connect-time guard.
* GHSA-cqv6-3m5f-qvw2 — `env.set` returned any host variable as
  `previous_value` and was not on the default denylist, although `env.get` is
  denied for exactly that read.
* GHSA-59pf-mh94-r7vv — `verify.visual_diff` confined `output_dir` but opened
  a local `reference_url` image from anywhere on the host.
* GHSA-6r7h-3hcc-jwpr — `huggingface.*` passed a caller `model_id` straight to
  `InferenceClient`, which treats a URL as the endpoint and sends `HF_TOKEN`
  to it.

Where a test proves a connection is refused, it runs a real local listener and
asserts the listener saw nothing, with a permissive-policy control that proves
the same harness does see the request when the guard allows it.
"""

import importlib
import ipaddress
import socket
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import core.module_policy as module_policy
from core.module_policy import ModuleFilter, ModulePolicyError, enforce_module_policy
from core.utils import (
    CredentialEndpointError,
    PathTraversalError,
    SSRFError,
    _extract_embedded_ipv4,
    _is_metadata_ip,
    _SSRFGuardedResolver,
    is_private_ip,
    validate_url_ssrf,
)

SRC = Path(__file__).resolve().parents[2] / 'src'

# Teredo: server 65.54.227.120, client 169.254.169.254 (stored bit-inverted).
TEREDO_METADATA = '2001:0:4136:e378:8000:ffff:5601:5601'
TEREDO_LOOPBACK = '2001:0:4136:e378:8000:ffff:80ff:fffe'
TEREDO_PUBLIC = '2001:0:4136:e378:8000:ffff:f7f7:f7f7'  # client 8.8.8.8


@pytest.fixture
def _no_private_network(monkeypatch):
    monkeypatch.delenv('FLYTO_ALLOW_PRIVATE_NETWORK', raising=False)
    monkeypatch.delenv('FLYTO_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('FLYTO_HTTP_DISABLE_SSRF_GUARD', raising=False)
    monkeypatch.delenv('FLYTO_VSCODE_LOCAL_MODE', raising=False)


def _sandbox(monkeypatch, tmp_path):
    sandbox = tmp_path / 'sandbox'
    sandbox.mkdir()
    monkeypatch.setenv('FLYTO_SANDBOX_DIR', str(sandbox))
    monkeypatch.setenv('FLYTO_ALLOW_ABSOLUTE_PATHS', 'true')
    return sandbox


def _handler(module, name):
    """The raw async handler behind a function-style module wrapper."""
    attr = getattr(module, name)
    return getattr(attr, '__wrapped_func__', attr)


class _Listener:
    """A loopback HTTP server that records every request it receives."""

    def __init__(self, status=200, body=b'{}', headers=None):
        self.requests = []
        listener = self

        class Handler(BaseHTTPRequestHandler):
            def _respond(self):
                length = int(self.headers.get('Content-Length') or 0)
                if length:
                    self.rfile.read(length)
                listener.requests.append((self.command, self.path, dict(self.headers)))
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _respond  # noqa: N815 - http.server dispatch name
            do_POST = _respond  # noqa: N815 - http.server dispatch name

            def log_message(self, *args):
                pass

        self._server = HTTPServer(('127.0.0.1', 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()


# ---------------------------------------------------------------------------
# GHSA-hc4c-6x9g-5fq3 — Teredo (and the other unlisted transition forms)
# ---------------------------------------------------------------------------

EMBEDDED_PRIVATE = [
    (TEREDO_METADATA, '169.254.169.254', 'Teredo metadata'),
    (TEREDO_LOOPBACK, '127.0.0.1', 'Teredo loopback'),
    ('::ffff:0:a9fe:a9fe', '169.254.169.254', 'IPv4-translated (SIIT) metadata'),
    ('2001:db8::5efe:a9fe:a9fe', '169.254.169.254', 'ISATAP metadata'),
    ('2001:db8::200:5efe:a00:1', '10.0.0.1', 'ISATAP (u/l bit) RFC 1918'),
]


@pytest.mark.parametrize(('address', 'embedded', 'form'), EMBEDDED_PRIVATE)
def test_transition_form_embedded_ipv4_is_decoded(address, embedded, form):
    assert str(_extract_embedded_ipv4(ipaddress.ip_address(address))) == embedded, form
    assert is_private_ip(address) is True, form


def test_teredo_metadata_is_a_metadata_address():
    assert _is_metadata_ip(TEREDO_METADATA) is True


def test_teredo_with_a_public_client_stays_reachable():
    """The fix decodes the endpoint; it does not blanket-block 2001:0::/32."""
    assert str(_extract_embedded_ipv4(ipaddress.ip_address(TEREDO_PUBLIC))) == '8.8.8.8'
    assert is_private_ip(TEREDO_PUBLIC) is False


@pytest.mark.parametrize('address', ['2606:4700:4700::1111', '2001:4860:4860::8888'])
def test_ordinary_public_ipv6_is_not_decoded(address):
    assert _extract_embedded_ipv4(ipaddress.ip_address(address)) is None
    assert is_private_ip(address) is False


def test_validate_url_ssrf_rejects_the_reported_teredo_url(_no_private_network):
    with pytest.raises(SSRFError):
        validate_url_ssrf(f'http://[{TEREDO_METADATA}]/latest/meta-data/')


@pytest.mark.asyncio
@pytest.mark.parametrize('allow_private', [False, True])
async def test_connect_time_resolver_rejects_teredo_metadata(allow_private):
    """The rebinding guard consults the same decoder, so it inherited the gap."""

    class TeredoResolver:
        async def resolve(self, host, port, family):
            return [{
                'hostname': host, 'host': TEREDO_METADATA, 'port': port,
                'family': socket.AF_INET6, 'proto': 0, 'flags': 0,
            }]

        async def close(self):
            return None

    resolver = _SSRFGuardedResolver(allow_private=allow_private)
    await resolver._inner.close()
    resolver._inner = TeredoResolver()
    try:
        with pytest.raises(SSRFError, match='metadata'):
            await resolver.resolve('rebind.example', 80, socket.AF_INET6)
    finally:
        await resolver.close()


@pytest.mark.parametrize('address', [
    TEREDO_METADATA, '2002:a9fe:a9fe::', '64:ff9b:1::a9fe:a9fe', '::ffff:0:a9fe:a9fe',
])
def test_database_dsn_guard_uses_the_shared_decoder(address):
    """database.* had its own NAT64/mapped-only decoder and relied on the
    stdlib for 6to4, whose answer differs between supported Pythons."""
    dsn_guard = importlib.import_module('core.modules.atomic.database._dsn_guard')
    assert dsn_guard._is_blocked_ip(ipaddress.ip_address(address)) is True


# ---------------------------------------------------------------------------
# GHSA-m5gf-24gv-m9g8 — verification callback resolve-then-connect
# ---------------------------------------------------------------------------

@pytest.fixture
def _callback_check_passed(monkeypatch):
    """Model the rebinding window: the one-shot destination check has already
    approved the host, and only the connection is left to decide."""
    service = importlib.import_module('core.verification_service')
    monkeypatch.setattr(service, '_callback_destination_allowed', lambda url: True)
    monkeypatch.setenv('FLYTO_RUNNER_SECRET', 'runner-secret-value')
    return service


@pytest.mark.asyncio
async def test_callback_does_not_deliver_the_runner_secret_to_a_rebound_address(
    _no_private_network, _callback_check_passed,
):
    with _Listener() as listener, pytest.raises(SSRFError):
        await _callback_check_passed.post_callback(
            f'http://localhost:{listener.port}/cb', {'ok': True},
        )
    assert listener.requests == []


@pytest.mark.asyncio
async def test_callback_harness_reaches_the_listener_when_policy_allows(
    monkeypatch, _callback_check_passed,
):
    """Control: the same call lands when the operator permits private targets,
    so the refusal above is the guard and not a broken harness."""
    monkeypatch.setenv('FLYTO_ALLOW_PRIVATE_NETWORK', 'true')
    with _Listener() as listener:
        await _callback_check_passed.post_callback(
            f'http://localhost:{listener.port}/cb', {'ok': True},
        )
    assert len(listener.requests) == 1
    assert listener.requests[0][2].get('X-Internal-Key') == 'runner-secret-value'


@pytest.mark.asyncio
async def test_callback_does_not_follow_a_redirect_with_the_secret(
    monkeypatch, _callback_check_passed,
):
    monkeypatch.setenv('FLYTO_ALLOW_PRIVATE_NETWORK', 'true')
    with _Listener() as target:
        with _Listener(status=307, headers={
            'Location': f'http://127.0.0.1:{target.port}/stolen',
        }) as engine, pytest.raises(RuntimeError, match='307'):
            await _callback_check_passed.post_callback(
                f'http://localhost:{engine.port}/cb', {'ok': True},
            )
        assert len(engine.requests) == 1
    assert target.requests == []


# ---------------------------------------------------------------------------
# GHSA-8j62-f337-86xw — llm aiohttp fallback without a connect-time guard
# ---------------------------------------------------------------------------

@pytest.fixture
def _base_install(monkeypatch):
    """The import posture of a deployment without the optional httpx extra."""
    monkeypatch.setitem(sys.modules, 'httpx', None)


@pytest.mark.asyncio
async def test_chat_model_fallback_refuses_a_rebound_base_url(
    _no_private_network, _base_install,
):
    chat_models = importlib.import_module('core.modules.atomic.llm._chat_models')
    with _Listener(body=b'{"choices": []}') as listener, pytest.raises(SSRFError):
        await chat_models._http_post(
            f'http://localhost:{listener.port}/chat/completions',
            {'Authorization': 'Bearer sk-dummy'},
            {'model': 'x', 'messages': []},
        )
    assert listener.requests == []


@pytest.mark.asyncio
async def test_chat_model_fallback_harness_reaches_the_listener_when_allowed(
    monkeypatch, _base_install,
):
    monkeypatch.setenv('FLYTO_ALLOW_PRIVATE_NETWORK', 'true')
    chat_models = importlib.import_module('core.modules.atomic.llm._chat_models')
    with _Listener(body=b'{"choices": []}') as listener:
        result = await chat_models._http_post(
            f'http://localhost:{listener.port}/chat/completions',
            {'Authorization': 'Bearer sk-dummy'},
            {'model': 'x', 'messages': []},
        )
    assert result == {'choices': []}
    assert len(listener.requests) == 1


@pytest.mark.asyncio
async def test_legacy_provider_fallback_refuses_a_rebound_base_url(
    _no_private_network, _base_install,
):
    providers = importlib.import_module('core.modules.atomic.llm._providers')
    with _Listener(body=b'{"choices": []}') as listener, pytest.raises(SSRFError):
        await providers.call_openai_with_tools(
            [{'role': 'user', 'content': 'x'}], [], 'x', 0.0, 'sk-dummy',
            f'http://localhost:{listener.port}/v1',
        )
    assert listener.requests == []


# ---------------------------------------------------------------------------
# GHSA-cqv6-3m5f-qvw2 — env.set previous_value as an env read
# ---------------------------------------------------------------------------

@pytest.fixture
def default_policy(monkeypatch):
    monkeypatch.delenv('FLYTO_MODULE_ALLOWLIST', raising=False)
    monkeypatch.delenv('FLYTO_MODULE_DENYLIST', raising=False)
    monkeypatch.delenv('FLYTO_GRANTED_PERMISSIONS', raising=False)
    monkeypatch.delenv('FLYTO_ENV_VAR_ALLOWLIST', raising=False)
    monkeypatch.setattr(module_policy, 'module_filter', ModuleFilter())


def _env_set():
    return _handler(importlib.import_module('core.modules.atomic.env.set'), 'env_set')


def test_env_set_is_denied_by_default(default_policy):
    assert module_policy.module_filter.is_allowed('env.set') is False
    with pytest.raises(ModulePolicyError):
        enforce_module_policy('env.set', [])


@pytest.mark.asyncio
async def test_env_set_reported_request_is_refused_through_execute_module(
    default_policy, monkeypatch,
):
    """The reporter's exact MCP `execute_module` call."""
    from core.mcp_handler import execute_module

    monkeypatch.setenv('FLYTO_TEST_REPORTED_SECRET', 'real-host-secret')
    result = await execute_module(
        'env.set', {'name': 'FLYTO_TEST_REPORTED_SECRET', 'value': 'x'},
    )
    assert 'real-host-secret' not in repr(result)
    assert result.get('ok') is not True
    import os
    assert os.environ['FLYTO_TEST_REPORTED_SECRET'] == 'real-host-secret'


@pytest.mark.asyncio
async def test_opted_in_env_set_withholds_the_previous_value(monkeypatch):
    """An operator who enables env.set but not env.get grants a write, not a read."""
    monkeypatch.setenv('FLYTO_MODULE_ALLOWLIST', 'env.set')
    monkeypatch.delenv('FLYTO_ENV_VAR_ALLOWLIST', raising=False)
    monkeypatch.setattr(module_policy, 'module_filter', ModuleFilter())
    monkeypatch.setenv('FLYTO_TEST_REPORTED_SECRET', 'real-host-secret')

    result = await _env_set()({'params': {'name': 'FLYTO_TEST_REPORTED_SECRET', 'value': 'x'}})

    assert result['data']['previous_value'] is None
    import os
    assert os.environ['FLYTO_TEST_REPORTED_SECRET'] == 'x'


@pytest.mark.asyncio
async def test_env_set_previous_value_follows_the_env_read_allowlist(monkeypatch):
    monkeypatch.setenv('FLYTO_MODULE_ALLOWLIST', 'env.set')
    monkeypatch.setenv('FLYTO_ENV_VAR_ALLOWLIST', 'MY_APP_*')
    monkeypatch.setattr(module_policy, 'module_filter', ModuleFilter())
    monkeypatch.setenv('MY_APP_PORT', '3000')

    result = await _env_set()({'params': {'name': 'MY_APP_PORT', 'value': '4000'}})

    assert result['data']['previous_value'] == '3000'


# ---------------------------------------------------------------------------
# GHSA-59pf-mh94-r7vv — verify.visual_diff local reference image read
# ---------------------------------------------------------------------------

def _visual_diff(params):
    module = importlib.import_module('core.modules.atomic.verify.visual_diff')
    return module.VerifyVisualDiffModule(params, {})


def test_visual_diff_rejects_a_reference_image_outside_the_sandbox(monkeypatch, tmp_path):
    sandbox = _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'host_secrets' / 'private_scan.png'
    secret.parent.mkdir()
    secret.write_bytes(b'\x89PNG\r\n\x1a\n')

    with pytest.raises(PathTraversalError):
        _visual_diff({
            'reference_url': str(secret),
            'dev_url': 'https://example.com/',
            'output_dir': str(sandbox / 'report'),
        })
    assert not (sandbox / 'report').exists()


def test_visual_diff_rejects_a_traversing_reference_path(monkeypatch, tmp_path):
    sandbox = _sandbox(monkeypatch, tmp_path)
    with pytest.raises(PathTraversalError):
        _visual_diff({
            'reference_url': str(sandbox / '..' / 'outside.png'),
            'dev_url': 'https://example.com/',
            'output_dir': str(sandbox / 'report'),
        })


def test_visual_diff_accepts_a_reference_image_inside_the_sandbox(monkeypatch, tmp_path):
    sandbox = _sandbox(monkeypatch, tmp_path)
    reference = sandbox / 'reference.png'
    reference.write_bytes(b'\x89PNG\r\n\x1a\n')

    module = _visual_diff({
        'reference_url': str(reference),
        'dev_url': 'https://example.com/',
        'output_dir': str(sandbox / 'report'),
    })
    assert Path(module.reference_url) == reference.resolve()


def test_visual_diff_url_reference_is_left_to_the_egress_guard(monkeypatch, tmp_path):
    sandbox = _sandbox(monkeypatch, tmp_path)
    module = _visual_diff({
        'reference_url': 'https://example.com/design',
        'dev_url': 'https://example.com/',
        'output_dir': str(sandbox / 'report'),
    })
    assert module.reference_url == 'https://example.com/design'


# ---------------------------------------------------------------------------
# GHSA-6r7h-3hcc-jwpr — huggingface model_id URL receives HF_TOKEN
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_hub(monkeypatch):
    """A stand-in `huggingface_hub` that records every client the runtime builds."""
    built = []

    class InferenceClient:
        def __init__(self, token=None, **kwargs):
            self.token = token
            self.calls = []
            built.append(self)

        def text_generation(self, inputs, model=None, **kwargs):
            self.calls.append(model)
            return 'generated'

    module = types.ModuleType('huggingface_hub')
    module.InferenceClient = InferenceClient
    monkeypatch.setitem(sys.modules, 'huggingface_hub', module)
    monkeypatch.setenv('HF_TOKEN', 'hf_operator_SECRET_token_value')
    monkeypatch.delenv('FLYTO_TRUSTED_LLM_HOSTS', raising=False)
    return built


def _runtime():
    return importlib.import_module('core.modules.atomic.huggingface._runtime')


@pytest.mark.asyncio
@pytest.mark.parametrize('model_id', [
    'http://127.0.0.1:8099/',
    'https://attacker.example/v1/',
    'HTTPS://attacker.example/',
])
async def test_url_model_id_never_reaches_a_token_bound_client(fake_hub, model_id):
    with pytest.raises(CredentialEndpointError):
        await _runtime().run_inference_api(model_id, 'hi', task='text-generation')
    assert fake_hub == []


@pytest.mark.asyncio
async def test_reported_module_path_does_not_send_the_token(fake_hub, _no_private_network):
    """Through the registered module, as the reporter drove it."""
    module = importlib.import_module('core.modules.atomic.huggingface.text_generation')
    handler = _handler(module, 'huggingface_text_generation')
    with pytest.raises(CredentialEndpointError):
        await handler({'params': {
            'model_id': 'http://127.0.0.1:8099/', 'prompt': 'hi',
        }})
    assert fake_hub == []


@pytest.mark.asyncio
@pytest.mark.parametrize('model_id', ['../../etc', 'a/b/c', 'org/model?x=1', 'org//model', ' gpt2'])
async def test_malformed_model_id_is_refused(fake_hub, model_id):
    with pytest.raises(ValueError):
        await _runtime().run_inference_api(model_id, 'hi', task='text-generation')
    assert fake_hub == []


@pytest.mark.asyncio
@pytest.mark.parametrize('model_id', ['gpt2', 'openai/whisper-large-v3', 'Helsinki-NLP/opus-mt-en-de'])
async def test_hub_repository_ids_still_run(fake_hub, model_id):
    result = await _runtime().run_inference_api(model_id, 'hi', task='text-generation')
    assert result == 'generated'
    assert fake_hub[0].calls == [model_id]


@pytest.mark.asyncio
async def test_operator_trusted_endpoint_is_still_usable(fake_hub, monkeypatch, _no_private_network):
    """Dedicated Inference Endpoints keep working when the operator names them."""
    monkeypatch.setenv('FLYTO_TRUSTED_LLM_HOSTS', '93.184.216.34')
    endpoint = 'https://93.184.216.34/'
    result = await _runtime().run_inference_api(endpoint, 'hi', task='text-generation')
    assert result == 'generated'
    assert fake_hub[0].calls == [endpoint]


@pytest.mark.asyncio
async def test_trusted_endpoint_host_is_still_ssrf_guarded(fake_hub, monkeypatch, _no_private_network):
    monkeypatch.setenv('FLYTO_TRUSTED_LLM_HOSTS', '169.254.169.254')
    with pytest.raises(SSRFError):
        await _runtime().run_inference_api(
            'http://169.254.169.254/', 'hi', task='text-generation',
        )
    assert fake_hub == []


def test_every_huggingface_inference_call_goes_through_the_guarded_sink():
    """One sink guards every task module only while there is one sink."""
    package = SRC / 'core' / 'modules' / 'atomic' / 'huggingface'
    constructions = [
        path.name
        for path in sorted(package.glob('*.py'))
        if 'InferenceClient(' in path.read_text(encoding='utf-8')
    ]
    assert constructions == ['_runtime.py']


# Files still allowed a plain `aiohttp.ClientSession(`: every construction in
# them talks to a fixed vendor host (api.openai.com, api.github.com, ...) and a
# caller value can reach only the path. Swept while scoping GHSA-8j62; the
# three constructions whose host a caller chose are gone. A new file that
# needs a plain session must justify its host here, in review.
FIXED_VENDOR_HOST_SESSIONS = frozenset({
    'core/modules/atomic/ai/embed.py',
    'core/modules/atomic/ai/extract.py',
    'core/modules/atomic/vision/analyze.py',
    'core/modules/atomic/vision/compare.py',
    'core/modules/third_party/ai/agents/llm_client.py',
    'core/modules/third_party/ai/agents/tool_use.py',
    'core/modules/third_party/ai/services.py',
    'core/modules/third_party/cloud/google/calendar_create.py',
    'core/modules/third_party/cloud/google/calendar_list.py',
    'core/modules/third_party/cloud/google/gmail_search.py',
    'core/modules/third_party/cloud/google/gmail_send.py',
    'core/modules/third_party/communication/messaging/telegram.py',
    'core/modules/third_party/communication/messaging/whatsapp.py',
    'core/modules/third_party/communication/twilio.py',
    'core/modules/third_party/developer/github.py',
    'core/modules/third_party/developer/http/search.py',
    'core/modules/third_party/payment/stripe.py',
    'core/modules/third_party/productivity/airtable.py',
    'core/modules/third_party/productivity/tools/notion_create_page.py',
    'core/modules/third_party/productivity/tools/notion_query.py',
})


def test_plain_aiohttp_sessions_exist_only_for_fixed_vendor_hosts():
    """The aiohttp twin of `test_no_module_constructs_an_unguarded_httpx_client`.

    A caller-chosen host must connect through `guarded_client_session`, or the
    build-time URL check is undone by a second DNS lookup at connect time.
    """
    utils = SRC / 'core' / 'utils.py'
    found = set()
    for path in sorted(SRC.rglob('*.py')):
        if path == utils:
            continue
        for line in path.read_text(encoding='utf-8').splitlines():
            if 'aiohttp.ClientSession(' in line and not line.lstrip().startswith('#'):
                found.add(path.relative_to(SRC).as_posix())
                break
    unexpected = sorted(found - FIXED_VENDOR_HOST_SESSIONS)
    assert not unexpected, (
        'construct aiohttp sessions through core.utils.guarded_client_session '
        'when the host is not a fixed vendor endpoint: ' + ', '.join(unexpected)
    )
    stale = sorted(FIXED_VENDOR_HOST_SESSIONS - found)
    assert not stale, 'remove converted files from the allowlist: ' + ', '.join(stale)
