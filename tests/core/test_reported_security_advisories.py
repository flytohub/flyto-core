"""Regression coverage for the 2026-07-31, 2026-08-02 and 2026-08-04 security reports.

The tests keep provider/network handlers fake and assert the protected sink is
never reached when SSRF or path-sandbox validation rejects caller input.
"""

import asyncio
import importlib
import io
import tarfile
import time

import pytest

from core.modules.errors import ModuleError, ValidationError
from core.utils import (
    PathTraversalError,
    SSRFError,
    guarded_aiohttp_request,
)


class _FakeResponse:
    def __init__(self, status=200, data=None, headers=None):
        self.status = status
        self.reason = 'OK'
        self.url = 'https://example.com/result'
        self.headers = headers or {'Content-Type': 'application/json'}
        self._data = data or {'ok': True}
        self.released = False

    async def text(self):
        return 'fake response body'

    async def json(self):
        return self._data

    def release(self):
        self.released = True


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *args, **kwargs):
        raise AssertionError('unguarded GET handler was reached')

    def post(self, *args, **kwargs):
        raise AssertionError('unguarded POST handler was reached')


@pytest.mark.asyncio
async def test_redirect_target_is_revalidated_before_second_request(monkeypatch):
    monkeypatch.setenv('FLYTO_ALLOWED_HOSTS', 'example.com')
    monkeypatch.delenv('FLYTO_ALLOW_PRIVATE_NETWORK', raising=False)
    monkeypatch.delenv('FLYTO_HTTP_DISABLE_SSRF_GUARD', raising=False)

    first_response = _FakeResponse(
        status=302,
        headers={'Location': 'http://169.254.169.254/latest/meta-data/'},
    )

    class RedirectSession:
        def __init__(self):
            self.calls = []

        async def request(self, method, url, **kwargs):
            self.calls.append((method, url))
            if len(self.calls) > 1:
                raise AssertionError('redirect target handler was reached')
            return first_response

    session = RedirectSession()
    with pytest.raises(SSRFError):
        await guarded_aiohttp_request(
            session, 'GET', 'https://example.com/start')

    assert session.calls == [('GET', 'https://example.com/start')]
    assert first_response.released is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('module_name', 'class_name', 'params', 'expected_method'),
    [
        (
            'core.modules.third_party.developer.http.requests',
            'HTTPGetModule',
            {'url': 'https://example.com/data'},
            'GET',
        ),
        (
            'core.modules.third_party.developer.http.requests',
            'HTTPPostModule',
            {'url': 'https://example.com/data', 'json': {'value': 1}},
            'POST',
        ),
        (
            'core.modules.third_party.communication.messaging.slack',
            'SlackSendMessageModule',
            {'webhook_url': 'https://example.com/slack', 'text': 'hello'},
            'POST',
        ),
        (
            'core.modules.third_party.communication.messaging.discord',
            'DiscordSendMessageModule',
            {'webhook_url': 'https://example.com/discord', 'content': 'hello'},
            'POST',
        ),
        (
            'core.modules.third_party.communication.messaging.teams',
            'TeamsSendMessageModule',
            {'webhook_url': 'https://example.com/teams', 'message': 'hello'},
            'POST',
        ),
    ],
)
async def test_reported_http_emitters_use_full_ssrf_guard(
    monkeypatch,
    module_name,
    class_name,
    params,
    expected_method,
):
    module = importlib.import_module(module_name)
    session = _FakeSession()
    response = _FakeResponse()
    calls = []

    monkeypatch.setattr(module, 'enforce_outbound_url', lambda url: url)
    monkeypatch.setattr(
        module, 'guarded_client_session', lambda **kwargs: session)

    async def fake_guarded_request(active_session, method, url, **kwargs):
        calls.append((active_session, method, url))
        return response

    monkeypatch.setattr(module, 'guarded_aiohttp_request', fake_guarded_request)

    instance = getattr(module, class_name)(params, {})
    await instance.execute()

    assert calls == [(session, expected_method, params['url'] if 'url' in params
                      else params['webhook_url'])]
    assert response.released is True


@pytest.mark.asyncio
async def test_oauth2_blocks_metadata_before_session_creation(monkeypatch):
    oauth2 = importlib.import_module('core.modules.atomic.auth.oauth2')
    session_created = False

    def forbidden_session(**kwargs):
        nonlocal session_created
        session_created = True
        raise AssertionError('OAuth2 session was created for a blocked target')

    monkeypatch.setattr(oauth2, 'guarded_client_session', forbidden_session)
    monkeypatch.delenv('FLYTO_ALLOW_PRIVATE_NETWORK', raising=False)
    monkeypatch.delenv('FLYTO_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('FLYTO_HTTP_DISABLE_SSRF_GUARD', raising=False)

    result = await oauth2.auth_oauth2(
        {
            'token_url': 'http://169.254.169.254/latest/meta-data/',
            'grant_type': 'client_credentials',
            'client_id': 'test-client',
        },
        {},
    ).execute()

    assert result['ok'] is False
    assert result['error_code'] == 'SSRF_BLOCKED'
    assert session_created is False


@pytest.mark.asyncio
async def test_oauth2_uses_guarded_request_and_redacts_error_body(monkeypatch):
    oauth2 = importlib.import_module('core.modules.atomic.auth.oauth2')
    session = _FakeSession()
    response = _FakeResponse(
        status=400,
        data={
            'error': 'secret-service-token',
            'error_description': 'sensitive internal response',
        },
    )
    calls = []

    monkeypatch.setattr(oauth2, 'enforce_outbound_url', lambda url: url)
    monkeypatch.setattr(
        oauth2, 'guarded_client_session', lambda **kwargs: session)

    async def fake_guarded_request(active_session, method, url, **kwargs):
        calls.append((active_session, method, url))
        return response

    monkeypatch.setattr(
        oauth2, 'guarded_aiohttp_request', fake_guarded_request)

    result = await oauth2.auth_oauth2(
        {
            'token_url': 'https://example.com/oauth/token',
            'grant_type': 'client_credentials',
            'client_id': 'test-client',
        },
        {},
    ).execute()

    assert calls == [
        (session, 'POST', 'https://example.com/oauth/token'),
    ]
    assert result['ok'] is False
    assert result['error_code'] == 'TOKEN_ENDPOINT_ERROR'
    assert 'secret-service-token' not in repr(result)
    assert 'sensitive internal response' not in repr(result)
    assert response.released is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'module_case',
    ['azure', 'gcs', 'cloud_aws_s3', 'aws_s3'],
)
async def test_cloud_downloads_block_paths_outside_sandbox(
    monkeypatch,
    tmp_path,
    module_case,
):
    sandbox = tmp_path / 'sandbox'
    sandbox.mkdir()
    outside_path = tmp_path / 'outside' / 'attacker-controlled'
    monkeypatch.setenv('FLYTO_SANDBOX_DIR', str(sandbox))
    monkeypatch.setenv('FLYTO_ALLOW_ABSOLUTE_PATHS', 'true')

    if module_case == 'azure':
        module = importlib.import_module(
            'core.modules.third_party.cloud.azure')
        operation = module.AzureDownloadModule(
            {
                'connection_string': 'test-only',
                'container': 'bucket',
                'blob_name': 'payload',
                'destination_path': str(outside_path),
            },
            {},
        ).execute()
    elif module_case == 'gcs':
        module = importlib.import_module('core.modules.third_party.cloud.gcs')
        operation = module.GCSDownloadModule(
            {
                'bucket': 'bucket',
                'object_name': 'payload',
                'destination_path': str(outside_path),
            },
            {},
        ).execute()
    elif module_case == 'cloud_aws_s3':
        module = importlib.import_module(
            'core.modules.third_party.cloud.storage')
        operation = module.aws_s3_download(
            {
                'aws_access_key_id': 'test-only',
                'aws_secret_access_key': 'test-only',
                'bucket': 'bucket',
                'key': 'payload',
                'file_path': str(outside_path),
            },
            {},
        ).execute()
    else:
        module = importlib.import_module(
            'core.modules.third_party.cloud.aws.s3_download')
        operation = module.aws_s3_download(
            {
                'access_key_id': 'test-only',
                'secret_access_key': 'test-only',
                'bucket': 'bucket',
                'key': 'payload',
                'output_path': str(outside_path),
            },
            {},
        ).execute()

    with pytest.raises(PathTraversalError):
        await operation

    assert outside_path.exists() is False


def _make_agent():
    module = importlib.import_module(
        'core.modules.third_party.ai.agents.llm_client'
    )

    class TestAgent(module.LLMClientMixin):
        pass

    return module, TestAgent()


def test_agent_ollama_blocks_metadata_even_when_remote_is_enabled(monkeypatch):
    _, agent = _make_agent()
    monkeypatch.setenv('FLYTO_ALLOW_REMOTE_OLLAMA', 'true')
    monkeypatch.delenv('FLYTO_ALLOW_PRIVATE_NETWORK', raising=False)
    monkeypatch.delenv('FLYTO_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('FLYTO_HTTP_DISABLE_SSRF_GUARD', raising=False)

    with pytest.raises(SSRFError):
        agent.validate_llm_params({
            'llm_provider': 'ollama',
            'ollama_url': 'http://169.254.169.254:80',
        })


@pytest.mark.asyncio
async def test_agent_ollama_uses_pinned_guard_and_redacts_error_body(
    monkeypatch,
):
    module, agent = _make_agent()
    agent.validate_llm_params({
        'llm_provider': 'ollama',
        'ollama_url': 'http://127.0.0.1:11434',
    })
    session = _FakeSession()
    response = _FakeResponse(
        status=500,
        data={'error': 'sensitive internal response'},
    )
    calls = []

    monkeypatch.setattr(
        module, 'guarded_client_session', lambda **kwargs: session
    )

    async def fake_guarded_request(active_session, method, url, **kwargs):
        calls.append((active_session, method, url, kwargs.get('max_redirects')))
        return response

    monkeypatch.setattr(
        module, 'guarded_aiohttp_request', fake_guarded_request
    )

    with pytest.raises(RuntimeError) as exc_info:
        await agent._call_ollama([{'role': 'user', 'content': 'Hi'}])

    assert calls == [
        (session, 'POST', 'http://127.0.0.1:11434/api/chat', 2),
    ]
    assert 'sensitive internal response' not in str(exc_info.value)
    assert response.released is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('module_name', 'module_attr', 'path_param'),
    [
        ('core.modules.atomic.data.csv_read', 'csv_read', 'file_path'),
        ('core.modules.atomic.data.yaml_parse', 'yaml_parse', 'file_path'),
        ('core.modules.atomic.document.excel_read', 'excel_read', 'path'),
        ('core.modules.atomic.document.pdf_parse', 'pdf_parse', 'path'),
        ('core.modules.atomic.image.ocr', 'image_ocr', 'image_path'),
        ('core.modules.atomic.document.word_parse', 'word_parse', 'file_path'),
    ],
)
async def test_reported_file_readers_block_paths_outside_sandbox(
    monkeypatch,
    tmp_path,
    module_name,
    module_attr,
    path_param,
):
    sandbox = tmp_path / 'sandbox'
    sandbox.mkdir()
    outside_path = tmp_path / 'outside' / 'secret'
    monkeypatch.setenv('FLYTO_SANDBOX_DIR', str(sandbox))
    monkeypatch.setenv('FLYTO_ALLOW_ABSOLUTE_PATHS', 'true')

    module = importlib.import_module(module_name)
    operation = getattr(module, module_attr)(
        {path_param: str(outside_path)},
        {},
    ).execute()

    with pytest.raises(PathTraversalError):
        await operation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'module_case',
    ['snapshot', 'trace', 'cookies', 'word_images', 'pdf_generate'],
)
async def test_reported_file_writers_block_paths_outside_sandbox(
    monkeypatch,
    tmp_path,
    module_case,
):
    sandbox = tmp_path / 'sandbox'
    sandbox.mkdir()
    outside_path = tmp_path / 'outside' / 'attacker-controlled'
    monkeypatch.setenv('FLYTO_SANDBOX_DIR', str(sandbox))
    monkeypatch.setenv('FLYTO_ALLOW_ABSOLUTE_PATHS', 'true')

    if module_case == 'snapshot':
        module = importlib.import_module(
            'core.modules.atomic.browser.snapshot'
        )
        with pytest.raises(PathTraversalError):
            module.BrowserSnapshotModule(
                {'format': 'html', 'path': str(outside_path)},
                {},
            )
    elif module_case == 'trace':
        module = importlib.import_module('core.modules.atomic.browser.trace')
        with pytest.raises(PathTraversalError):
            module.BrowserTraceModule(
                {'action': 'stop', 'path': str(outside_path)},
                {},
            )
    elif module_case == 'cookies':
        module = importlib.import_module(
            'core.modules.atomic.browser.cookies_file'
        )
        with pytest.raises(PathTraversalError):
            module.BrowserCookiesFileModule(
                {'action': 'export', 'file_path': str(outside_path)},
                {},
            )
    elif module_case == 'word_images':
        module = importlib.import_module(
            'core.modules.atomic.document.word_parse'
        )
        operation = module.word_parse(
            {
                'file_path': str(sandbox / 'source.docx'),
                'extract_images': True,
                'images_output_dir': str(outside_path),
            },
            {},
        ).execute()
        with pytest.raises(PathTraversalError):
            await operation
    else:
        module = importlib.import_module(
            'core.modules.atomic.document.pdf_generate'
        )
        operation = module.pdf_generate(
            {'content': 'payload', 'output_path': str(outside_path)},
            {},
        ).execute()
        with pytest.raises(PathTraversalError):
            await operation

    assert outside_path.exists() is False


# ---------------------------------------------------------------------------
# 2026-08 reports: Tar Slip (GHSA-pxvx-67rw-8352), regex ReDoS
# (GHSA-v468-p4jx-7vj3), and the port.check IPv6 SSRF bypass
# (GHSA-v7q9-pr72-5fmv).
# ---------------------------------------------------------------------------


def _sandbox(monkeypatch, tmp_path):
    sandbox = tmp_path / 'sandbox'
    sandbox.mkdir()
    monkeypatch.setenv('FLYTO_SANDBOX_DIR', str(sandbox))
    monkeypatch.setenv('FLYTO_ALLOW_ABSOLUTE_PATHS', 'true')
    return sandbox


@pytest.mark.asyncio
async def test_tar_extract_rejects_symlink_slip(monkeypatch, tmp_path):
    """A symlink member pointing outside the sandbox must be rejected before
    extraction, so a following nested member cannot be written through it."""
    sandbox = _sandbox(monkeypatch, tmp_path)
    outside = sandbox / 'outside'
    outside.mkdir()
    out_dir = sandbox / 'out'
    out_dir.mkdir()

    evil = sandbox / 'evil.tar'
    with tarfile.open(evil, 'w') as tf:
        link = tarfile.TarInfo('evil')
        link.type = tarfile.SYMTYPE
        link.linkname = str(outside)
        link.mode = 0o777
        tf.addfile(link)
        payload = b'TAR_SLIP_PWNED\n'
        nested = tarfile.TarInfo('evil/pwned.txt')
        nested.size = len(payload)
        tf.addfile(nested, io.BytesIO(payload))

    module = importlib.import_module('core.modules.atomic.archive.tar_extract')
    with pytest.raises(ModuleError) as excinfo:
        await module.archive_tar_extract(
            {'archive_path': str(evil), 'output_dir': str(out_dir)},
            {},
        ).execute()

    assert excinfo.value.code == 'PATH_TRAVERSAL'
    assert (outside / 'pwned.txt').exists() is False


@pytest.mark.asyncio
async def test_tar_extract_allows_benign_archive(monkeypatch, tmp_path):
    """The hardened pre-check must not break ordinary file/dir extraction."""
    sandbox = _sandbox(monkeypatch, tmp_path)
    out_dir = sandbox / 'out'
    out_dir.mkdir()

    good = sandbox / 'good.tar'
    with tarfile.open(good, 'w') as tf:
        payload = b'hello'
        info = tarfile.TarInfo('nested/a.txt')
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    module = importlib.import_module('core.modules.atomic.archive.tar_extract')
    result = await module.archive_tar_extract(
        {'archive_path': str(good), 'output_dir': str(out_dir)},
        {},
    ).execute()

    assert result['ok'] is True
    assert (out_dir / 'nested' / 'a.txt').read_bytes() == b'hello'


@pytest.mark.asyncio
async def test_regex_match_redos_times_out_without_freezing_loop(monkeypatch):
    """A catastrophic pattern must be abandoned quickly (native regex timeout)
    while the event loop keeps running other tasks — the whole-server freeze
    the advisory describes must not happen."""
    safe = importlib.import_module('core.modules.atomic.regex._safe')
    monkeypatch.setattr(safe, 'REGEX_TIMEOUT_SECONDS', 0.5)
    module = importlib.import_module('core.modules.atomic.regex.match')

    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    beat = asyncio.create_task(heartbeat())
    started = time.monotonic()
    with pytest.raises(ValidationError):
        await module.regex_match(
            {'text': 'a' * 60 + 'b', 'pattern': r'(a|a)*$'},
            {},
        ).execute()
    elapsed = time.monotonic() - started
    beat.cancel()

    assert elapsed < 3.0  # abandoned near the 0.5s budget, not tens of seconds
    assert ticks > 5      # event loop stayed responsive during the match


@pytest.mark.asyncio
async def test_regex_match_rejects_oversized_inputs(monkeypatch):
    """Length caps reject abusive inputs before any matching happens."""
    safe = importlib.import_module('core.modules.atomic.regex._safe')
    module = importlib.import_module('core.modules.atomic.regex.match')

    with pytest.raises(ValidationError):
        await module.regex_match(
            {'text': 'x', 'pattern': 'a' * (safe.MAX_PATTERN_LENGTH + 1)},
            {},
        ).execute()

    with pytest.raises(ValidationError):
        await module.regex_match(
            {'text': 'x' * (safe.MAX_TEXT_LENGTH + 1), 'pattern': 'x'},
            {},
        ).execute()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'host',
    [
        '::ffff:127.0.0.1',        # IPv4-mapped loopback
        '::ffff:169.254.169.254',  # IPv4-mapped cloud metadata
        'nonexistent.invalid.',    # unresolvable -> must fail closed
    ],
)
async def test_port_check_blocks_ipv6_transition_and_fails_closed(
    monkeypatch, host
):
    """port.check must not let IPv6 transition literals skip the SSRF guard,
    and an unresolvable host must be blocked rather than allowed through."""
    monkeypatch.delenv('FLYTO_ALLOW_PORT_SCAN', raising=False)
    module = importlib.import_module('core.modules.atomic.port.check')

    result = await module.port_check(
        {'port': 80, 'host': host, 'connect_timeout': 0.1},
        {},
    ).execute()

    assert result['ok'] is False
    assert result['error_code'] == 'SSRF_BLOCKED'


@pytest.mark.asyncio
async def test_port_check_allows_public_literal(monkeypatch):
    """A public IP literal must still be permitted (no over-blocking)."""
    monkeypatch.delenv('FLYTO_ALLOW_PORT_SCAN', raising=False)
    module = importlib.import_module('core.modules.atomic.port.check')

    async def _closed(host, port, timeout):
        return False

    monkeypatch.setattr(module, '_check_port_async', _closed)
    result = await module.port_check(
        {'port': 80, 'host': '93.184.216.34', 'connect_timeout': 0.1},
        {},
    ).execute()

    assert result.get('error_code') != 'SSRF_BLOCKED'


# ---------------------------------------------------------------------------
# 2026-08-05 reports: browser.download arbitrary file write
# (GHSA-p64w-hgfm-824v) and the browser.goto www-toggle SSRF bypass
# (GHSA-662f-hr85-mg6c).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('module_path', 'class_name', 'params_for'),
    [
        (
            'core.modules.atomic.browser.download',
            'BrowserDownloadModule',
            lambda target: {'selector': '#dl', 'save_path': target},
        ),
        (
            'core.modules.atomic.browser.screenshot',
            'BrowserScreenshotModule',
            lambda target: {'path': target},
        ),
        (
            'core.modules.atomic.browser.pdf',
            'BrowserPdfModule',
            lambda target: {'path': target},
        ),
    ],
)
def test_browser_writers_reject_paths_outside_sandbox(
    monkeypatch, tmp_path, module_path, class_name, params_for
):
    """browser.{download,screenshot,pdf} must refuse a save path outside the
    sandbox. The advisory PoC wrote attacker-controlled bytes byte-perfect to
    /etc/cron.d and ~/.ssh/authorized_keys through browser.download."""
    _sandbox(monkeypatch, tmp_path)
    outside = tmp_path / 'outside' / 'pwned.bin'

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    with pytest.raises(PathTraversalError):
        cls(params_for(str(outside)), {})

    assert outside.exists() is False
    assert outside.parent.exists() is False  # mkdir must not run either


def test_browser_download_accepts_path_inside_sandbox(monkeypatch, tmp_path):
    """The guard must not break the ordinary in-sandbox download."""
    sandbox = _sandbox(monkeypatch, tmp_path)
    target = sandbox / 'downloads' / 'report.pdf'

    module = importlib.import_module('core.modules.atomic.browser.download')
    instance = module.BrowserDownloadModule(
        {'selector': '#dl', 'save_path': str(target)}, {}
    )

    assert instance.save_path.endswith('report.pdf')
    assert target.parent.is_dir()


@pytest.mark.asyncio
async def test_warroom_report_rejects_path_outside_sandbox(monkeypatch, tmp_path):
    """warroom.report writes its evidence pack to a caller-controlled path."""
    _sandbox(monkeypatch, tmp_path)
    outside = tmp_path / 'outside' / 'evidence.md'

    module = importlib.import_module('core.modules.atomic.warroom.report')
    instance = module.WarroomReportModule(
        {'format': 'markdown', 'output_path': str(outside)}, {}
    )

    with pytest.raises(PathTraversalError):
        await instance.execute()

    assert outside.exists() is False


def test_verify_report_rejects_output_dir_outside_sandbox(monkeypatch, tmp_path):
    """An output_dir pointing out of the sandbox is refused at construction."""
    _sandbox(monkeypatch, tmp_path)
    module = importlib.import_module('core.modules.atomic.verify.report')

    with pytest.raises(PathTraversalError):
        module.VerifyReportModule(
            {'results': [], 'output_dir': str(tmp_path / 'outside')}, {}
        )


def test_verify_report_rejects_traversal_in_name(monkeypatch, tmp_path):
    """The filename half of the destination is caller-controlled too, so a
    sandboxed output_dir alone does not contain the write."""
    sandbox = _sandbox(monkeypatch, tmp_path)
    module = importlib.import_module('core.modules.atomic.verify.report')

    instance = module.VerifyReportModule(
        {
            'results': [],
            'output_dir': str(sandbox / 'reports'),
            'name': '../../../../tmp/flyto-escape',
        },
        {},
    )

    with pytest.raises(PathTraversalError):
        instance._report_path('html')


def test_verify_report_escapes_untrusted_values(monkeypatch, tmp_path):
    """The HTML report interpolates page-derived and caller-derived strings;
    they must be escaped so the report cannot be turned into a payload."""
    sandbox = _sandbox(monkeypatch, tmp_path)
    module = importlib.import_module('core.modules.atomic.verify.report')

    instance = module.VerifyReportModule(
        {'results': [], 'output_dir': str(sandbox / 'reports')}, {}
    )
    payload = '<script>alert(1)</script>'
    rendered = instance._generate_html(
        {
            'name': payload,
            'url': payload,
            'created_at': '2026-08-06T00:00:00',
            'summary': {
                'overall_passed': True,
                'pass_rate': 100,
                'total_rules': 1,
                'passed_rules': 1,
                'failed_rules': 0,
                'total_violations': 0,
                'error_count': 0,
                'warning_count': 0,
            },
            'results': [
                {
                    'passed': False,
                    'selector': payload,
                    'violations': [
                        {
                            'severity': 'error" onmouseover="alert(1)',
                            'property': payload,
                            'expected': payload,
                            'actual': payload,
                            'difference': payload,
                        }
                    ],
                }
            ],
            'screenshots': [],
        }
    )

    assert '<script>alert(1)</script>' not in rendered
    assert '&lt;script&gt;' in rendered
    # An unknown severity must not reach the class attribute verbatim.
    assert 'onmouseover=' not in rendered.split('<style>')[0] + rendered.split('</style>')[-1]


@pytest.mark.asyncio
async def test_goto_www_toggle_revalidates_the_toggled_host(monkeypatch):
    """The www-toggle retry navigates to a host the caller also controls, so it
    must pass the SSRF guard. Previously only the submitted host was checked:
    www.evil.test resolved publicly and passed, the connection was refused, and
    the toggle then navigated to evil.test -> 127.0.0.1 unvalidated."""
    monkeypatch.delenv('DEPLOYMENT_MODE', raising=False)
    module = importlib.import_module('core.modules.atomic.browser.goto')

    checked = []

    def fake_validate(url):
        checked.append(url)
        if '://www.' not in url:
            raise SSRFError(f'blocked internal target: {url}')
        return url

    monkeypatch.setattr(module, 'validate_url_with_env_config', fake_validate)

    class _Browser:
        def __init__(self):
            self.navigated = []

        async def goto(self, url, **kwargs):
            self.navigated.append(url)
            return {'url': url}

    instance = module.BrowserGotoModule({'url': 'http://www.evil.test/'}, {})
    browser = _Browser()

    assert await instance._try_www_toggle(browser) is None
    assert browser.navigated == []  # the internal host was never opened
    assert checked == ['http://www.evil.test/', 'http://evil.test/']


@pytest.mark.asyncio
async def test_goto_www_toggle_still_works_for_allowed_hosts(monkeypatch):
    """The retry must keep working when the toggled host is legitimate."""
    monkeypatch.delenv('DEPLOYMENT_MODE', raising=False)
    module = importlib.import_module('core.modules.atomic.browser.goto')
    monkeypatch.setattr(module, 'validate_url_with_env_config', lambda url: url)

    class _Browser:
        def __init__(self):
            self.navigated = []

        async def goto(self, url, **kwargs):
            self.navigated.append(url)
            return {'url': url}

        async def get_hints(self, force=False):
            return {}

    instance = module.BrowserGotoModule({'url': 'http://www.example.com/'}, {})
    browser = _Browser()

    result = await instance._try_www_toggle(browser)
    assert result is not None
    assert result['status'] == 'success'
    assert browser.navigated == ['http://example.com/']


def test_driver_goto_guard_blocks_internal_targets(monkeypatch):
    """Defense in depth: the driver validates every navigation, so a caller
    that derives a new URL and forgets to revalidate is still covered."""
    monkeypatch.delenv('DEPLOYMENT_MODE', raising=False)
    monkeypatch.delenv('FLYTO_ALLOW_PRIVATE_NETWORK', raising=False)
    from core.browser.driver import BrowserDriver

    driver = BrowserDriver()
    with pytest.raises(RuntimeError, match='SSRF protection'):
        driver._guard_navigation('http://169.254.169.254/latest/meta-data/', None)


def test_driver_goto_opt_out_is_sticky_but_never_in_cloud(monkeypatch):
    """Desktop keeps its documented opt-out (and internal re-navigations
    inherit it); cloud modes ignore the opt-out entirely."""
    monkeypatch.delenv('FLYTO_ALLOW_PRIVATE_NETWORK', raising=False)
    from core.browser.driver import BrowserDriver

    monkeypatch.delenv('DEPLOYMENT_MODE', raising=False)
    desktop = BrowserDriver()
    desktop._guard_navigation('http://127.0.0.1:8080/', False)
    assert desktop._ssrf_opt_out is True
    desktop._guard_navigation('http://127.0.0.1:8080/', None)  # inherited

    monkeypatch.setenv('DEPLOYMENT_MODE', 'worker')
    cloud = BrowserDriver()
    cloud._ssrf_opt_out = True
    with pytest.raises(RuntimeError, match='SSRF protection'):
        cloud._guard_navigation('http://127.0.0.1:8080/', False)


# ---------------------------------------------------------------------------
# Same-class findings surfaced while scoping GHSA-p64w (CWE-22, unvalidated
# caller path to a write sink): browser.launch record_video_dir,
# verify.visual_diff / verify.run output_dir, data.dedup hash_file. None of
# these were named in a public advisory; they were the exact pattern the
# advisory describes as recurring wave-over-wave, so they are closed here in
# the same pass rather than left for a wave 3 report.
# ---------------------------------------------------------------------------


def test_browser_launch_rejects_record_video_dir_outside_sandbox(monkeypatch, tmp_path):
    _sandbox(monkeypatch, tmp_path)
    outside = tmp_path / 'outside' / 'videos'

    module = importlib.import_module('core.modules.atomic.browser.launch')
    with pytest.raises(PathTraversalError):
        module.BrowserLaunchModule({'record_video_dir': str(outside)}, {})

    assert outside.exists() is False


def test_browser_launch_allows_no_record_video_dir(monkeypatch, tmp_path):
    """record_video_dir is optional; omitting it must not raise."""
    _sandbox(monkeypatch, tmp_path)
    module = importlib.import_module('core.modules.atomic.browser.launch')
    instance = module.BrowserLaunchModule({}, {})
    assert instance.record_video_dir is None


def test_verify_visual_diff_rejects_output_dir_outside_sandbox(monkeypatch, tmp_path):
    _sandbox(monkeypatch, tmp_path)
    outside = tmp_path / 'outside'

    module = importlib.import_module('core.modules.atomic.verify.visual_diff')
    with pytest.raises(PathTraversalError):
        module.VerifyVisualDiffModule(
            {
                'reference_url': 'https://example.com/a',
                'dev_url': 'https://example.com/b',
                'output_dir': str(outside),
            },
            {},
        )

    assert outside.exists() is False


def test_verify_run_rejects_output_dir_outside_sandbox(monkeypatch, tmp_path):
    _sandbox(monkeypatch, tmp_path)
    outside = tmp_path / 'outside'

    module = importlib.import_module('core.modules.atomic.verify.runner')
    with pytest.raises(PathTraversalError):
        module.VerifyRunModule(
            {'url': 'https://example.com', 'selectors': ['body'], 'output_dir': str(outside)},
            {},
        )

    assert outside.exists() is False


def test_data_dedup_rejects_hash_file_outside_sandbox(monkeypatch, tmp_path):
    """The write-then-rename in _save_hashes would otherwise let a caller
    overwrite an arbitrary existing file via hash_file traversal."""
    _sandbox(monkeypatch, tmp_path)
    victim = tmp_path / 'outside' / 'victim.json'

    module = importlib.import_module('core.modules.atomic.data.dedup')
    with pytest.raises(PathTraversalError):
        module.DataDedupModule(
            {'items': [{'url': 'a'}], 'keys': ['url'], 'hash_file': str(victim)}, {}
        )

    assert victim.exists() is False


def test_data_dedup_allows_no_hash_file(monkeypatch, tmp_path):
    """hash_file is optional (memory/context storage modes); omitting it must
    not raise."""
    _sandbox(monkeypatch, tmp_path)
    module = importlib.import_module('core.modules.atomic.data.dedup')
    instance = module.DataDedupModule(
        {'items': [{'url': 'a'}], 'keys': ['url'], 'storage': 'context'}, {}
    )
    assert instance.hash_file is None


def _handler(module, name):
    """Return the raw async handler for a function-style module.

    register_module() rebinds the name to a BaseModule subclass, so calling
    module.xml_parse(...) would construct the wrapper instead of running the
    handler. The wrapper keeps the original function at __wrapped_func__.
    """
    attr = getattr(module, name)
    return getattr(attr, '__wrapped_func__', attr)

# ---------------------------------------------------------------------------
# Wave 3, closed by coverage rather than by report. The registry-wide audit in
# tests/core/test_write_sink_coverage.py found every remaining module that took
# a caller-supplied path to a filesystem sink without the sandbox helper. None
# of these were reported; they are the modules a fourth advisory wave would
# have been written about. Each is the same CWE-22 shape as the published
# advisories, so each gets the same regression test.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_visual_compare_rejects_diff_path_outside_sandbox(monkeypatch, tmp_path):
    """testing.visual.compare declares no required_permissions, so diff_path was
    an unauthenticated arbitrary file write — the GHSA-p64w-hgfm-824v shape with
    no permission gate in front of it."""
    _sandbox(monkeypatch, tmp_path)
    victim = tmp_path / 'outside' / 'victim.png'

    module = importlib.import_module('core.modules.atomic.testing.visual')
    with pytest.raises(PathTraversalError):
        await module.compare_visual_files(
            'data:image/png;base64,aGk=',
            'data:image/png;base64,aGk=',
            diff_path=str(victim),
        )

    assert victim.exists() is False


@pytest.mark.asyncio
async def test_xml_parse_rejects_file_path_outside_sandbox(monkeypatch, tmp_path):
    """GHSA-wc94-386q-5478 closed data.csv.read / data.yaml.parse / excel.read /
    pdf.parse / image.ocr. data.xml.parse is the same read sink and was missed;
    the parsed document is returned straight to the caller."""
    sandbox = _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'outside' / 'secret.xml'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('<root><token>s3cret</token></root>', encoding='utf-8')

    module = importlib.import_module('core.modules.atomic.data.xml_parse')
    with pytest.raises(PathTraversalError):
        await _handler(module, 'xml_parse')({'params': {'file_path': str(secret)}})

    inside = sandbox / 'ok.xml'
    inside.write_text('<root><a>1</a></root>', encoding='utf-8')
    result = await _handler(module, 'xml_parse')({'params': {'file_path': str(inside)}})
    assert result['ok'] is True


def test_browser_upload_rejects_file_path_outside_sandbox(monkeypatch, tmp_path):
    """browser.upload hands the file's bytes to the visited page, so an
    unconfined file_path exfiltrates host secrets to a remote origin."""
    _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'outside' / 'id_rsa'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('PRIVATE KEY', encoding='utf-8')

    module = importlib.import_module('core.modules.atomic.browser.upload')
    with pytest.raises(PathTraversalError):
        module.BrowserUploadModule({'selector': '#f', 'file_path': str(secret)}, {})


def test_file_delete_rejects_path_outside_sandbox(monkeypatch, tmp_path):
    """os.remove() on an unconfined path is arbitrary file deletion — the
    destructive counterpart of the arbitrary file write advisories."""
    _sandbox(monkeypatch, tmp_path)
    victim = tmp_path / 'outside' / 'important.db'
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_text('data', encoding='utf-8')

    module = importlib.import_module('core.modules.atomic.file.delete')
    with pytest.raises(PathTraversalError):
        module.FileDeleteModule({'file_path': str(victim)}, {})

    assert victim.exists() is True


@pytest.mark.asyncio
async def test_sftp_download_rejects_local_path_outside_sandbox(monkeypatch, tmp_path):
    """GHSA-hmq9-xw4w-7ppc closed destination_path on cloud.{azure,gcs,aws_s3}
    .download. ssh.sftp_download is the same remote-bytes-to-local-path sink."""
    _sandbox(monkeypatch, tmp_path)
    victim = tmp_path / 'outside' / 'authorized_keys'

    module = importlib.import_module('core.modules.atomic.ssh.sftp_download')
    with pytest.raises(PathTraversalError):
        await _handler(module, 'ssh_sftp_download')({'params': {
            'host': 'example.com', 'username': 'u', 'password': 'p',
            'remote_path': '/tmp/x', 'local_path': str(victim),
        }})

    assert victim.parent.exists() is False


@pytest.mark.asyncio
async def test_sftp_upload_rejects_local_path_outside_sandbox(monkeypatch, tmp_path):
    """The read side: local_path is shipped to a caller-chosen SSH host."""
    _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'outside' / 'credentials'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('aws_secret_access_key = ...', encoding='utf-8')

    module = importlib.import_module('core.modules.atomic.ssh.sftp_upload')
    with pytest.raises(PathTraversalError):
        await _handler(module, 'ssh_sftp_upload')({'params': {
            'host': 'example.com', 'username': 'u', 'password': 'p',
            'local_path': str(secret), 'remote_path': '/tmp/stolen',
        }})


@pytest.mark.asyncio
async def test_git_clone_rejects_destination_outside_sandbox(monkeypatch, tmp_path):
    """git writes a whole remote-authored tree at destination; unconfined that
    is an arbitrary file write with a friendlier interface."""
    _sandbox(monkeypatch, tmp_path)
    outside = tmp_path / 'outside' / 'repo'

    module = importlib.import_module('core.modules.atomic.git.clone')
    with pytest.raises(PathTraversalError):
        await _handler(module, 'git_clone')({'params': {
            'url': 'https://github.com/example/repo.git',
            'destination': str(outside),
        }})

    assert outside.exists() is False


@pytest.mark.asyncio
async def test_code_fix_rejects_absolute_source_file_outside_sandbox(monkeypatch, tmp_path):
    """llm.code_fix guarded only against '..', so an absolute path sailed
    through to write_text with model-generated content."""
    _sandbox(monkeypatch, tmp_path)
    victim = tmp_path / 'outside' / 'job'
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_text('original', encoding='utf-8')

    module = importlib.import_module('core.modules.atomic.llm.code_fix')
    result = await _handler(module, 'llm_code_fix')({'params': {
        'issues': [{'file': str(victim), 'message': 'x'}],
        'source_files': [str(victim)],
        'fix_mode': 'apply',
    }})

    # The out-of-sandbox file is dropped before it can be read or written.
    assert result['ok'] is False
    assert victim.read_text(encoding='utf-8') == 'original'


# ---------------------------------------------------------------------------
# Outbound-boundary wave, closed by coverage rather than by report. The
# registry audit in tests/core/test_outbound_guard_coverage.py found the
# modules that reach the network from a caller-supplied target without an SSRF
# guard. Like the filesystem wave above, none were reported; they are what a
# further advisory round would have been written about.
# ---------------------------------------------------------------------------


@pytest.fixture
def _no_private_network(monkeypatch):
    monkeypatch.delenv('FLYTO_ALLOW_PRIVATE_NETWORK', raising=False)
    monkeypatch.delenv('FLYTO_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('FLYTO_HTTP_DISABLE_SSRF_GUARD', raising=False)


def test_outbound_host_guard_blocks_metadata_and_private(_no_private_network):
    """The shared raw-TCP guard: the non-HTTP twin of validate_url_ssrf."""
    from core.utils import enforce_outbound_host

    for blocked in ('169.254.169.254', '10.0.0.5', '192.168.1.1', '::ffff:127.0.0.1'):
        with pytest.raises(SSRFError):
            enforce_outbound_host(blocked, purpose='test')

    # Loopback stays allowed — self-hosted Redis/MySQL/SMTP is the normal case
    # and blocking it would break deployments without closing a path.
    for allowed in ('localhost', '127.0.0.1', '::1'):
        assert enforce_outbound_host(allowed, purpose='test') == allowed


def test_outbound_host_guard_fails_closed_on_unresolvable(_no_private_network):
    """GHSA-v7q9-pr72-5fmv was a fail-open on resolution failure."""
    from core.utils import enforce_outbound_host

    with pytest.raises(SSRFError):
        enforce_outbound_host('no-such-host.invalid', purpose='test')


def test_outbound_host_guard_honours_operator_allowlist(monkeypatch):
    """An operator can still reach an internal host on purpose."""
    from core.utils import enforce_outbound_host

    monkeypatch.setenv('FLYTO_ALLOWED_HOSTS', 'internal.corp')
    assert enforce_outbound_host('internal.corp', purpose='test') == 'internal.corp'


def test_service_url_guard_blocks_metadata_redis(_no_private_network):
    """validate_url_ssrf only speaks http(s); redis:// needed its own path."""
    from core.utils import enforce_outbound_service_url

    with pytest.raises(SSRFError):
        enforce_outbound_service_url('redis://169.254.169.254:6379', purpose='Redis')
    assert enforce_outbound_service_url('redis://localhost:6379', purpose='Redis')


@pytest.mark.asyncio
async def test_ssh_exec_rejects_private_host(_no_private_network):
    """ssh.exec opened a connection to any caller-named host."""
    module = importlib.import_module('core.modules.atomic.ssh.exec')
    with pytest.raises(SSRFError):
        await _handler(module, 'ssh_exec')({'params': {
            'host': '169.254.169.254', 'username': 'u', 'password': 'p',
            'command': 'id',
        }})


@pytest.mark.asyncio
async def test_cache_get_rejects_metadata_redis_url(_no_private_network):
    """redis_url reached aioredis unchecked — an internal port prober."""
    module = importlib.import_module('core.modules.atomic.cache.get')
    with pytest.raises(SSRFError):
        await _handler(module, 'cache_get')({'params': {
            'key': 'k', 'redis_url': 'redis://169.254.169.254:6379',
        }})


@pytest.mark.asyncio
async def test_network_ping_rejects_private_host(_no_private_network):
    """Probing is the module's purpose, which is why the target must be bounded."""
    module = importlib.import_module('core.modules.atomic.network.ping')
    with pytest.raises(SSRFError):
        await _handler(module, 'network_ping')({'params': {'host': '10.0.0.5'}})


def test_browser_connect_rejects_internal_cdp_endpoint(_no_private_network):
    """connect_over_cdp hands full DevTools control of whatever answers, and
    CDP is remote code execution by design."""
    module = importlib.import_module('core.modules.atomic.browser.connect')
    with pytest.raises(SSRFError):
        module.BrowserConnectModule({'ws_endpoint': 'ws://169.254.169.254:9222'}, {})


def test_browser_launch_rejects_internal_proxy(_no_private_network):
    """Every browser request routes through the proxy, and the egress guard
    inspects request URLs — not where the proxy itself points."""
    module = importlib.import_module('core.modules.atomic.browser.launch')
    with pytest.raises(SSRFError):
        module.BrowserLaunchModule({'proxy': 'http://169.254.169.254:8080'}, {})


@pytest.mark.asyncio
async def test_git_clone_rejects_metadata_url(_no_private_network, monkeypatch, tmp_path):
    """_validate_clone_url bounded the transport but never the destination."""
    _sandbox(monkeypatch, tmp_path)
    module = importlib.import_module('core.modules.atomic.git.clone')

    result = await _handler(module, 'git_clone')({'params': {
        'url': 'http://169.254.169.254/latest/meta-data/',
        'destination': str(tmp_path / 'sandbox' / 'repo'),
    }})

    assert result['ok'] is False
    assert result['error_code'] == 'SSRF_BLOCKED'


@pytest.mark.asyncio
async def test_visual_diff_screenshot_rejects_metadata_url(_no_private_network):
    """verify.visual_diff drives a bare playwright browser, so it has no egress
    guard in any deployment mode — the Python-side guard is the only boundary."""
    module = importlib.import_module('core.modules.atomic.verify.visual_diff')
    with pytest.raises(SSRFError):
        await module._screenshot_url(
            'http://169.254.169.254/latest/meta-data/', '/tmp/unused.png'
        )
