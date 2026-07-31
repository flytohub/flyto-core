"""Regression coverage for the 2026-07-31 security reports.

The tests keep provider/network handlers fake and assert the protected sink is
never reached when SSRF or path-sandbox validation rejects caller input.
"""

import importlib

import pytest

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
