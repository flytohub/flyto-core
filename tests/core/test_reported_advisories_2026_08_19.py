"""Regression coverage for the 2026-08-18/19 security reports.

Five reports, four distinct sinks (two of them describe the same `llm.agent`
parameter from different reporters):

* GHSA-4346-4gqg-59f9 — `BaseIntegration._request` builds every `integration.*`
  request on a bare session and attaches the operator's environment credentials
  to whatever host the caller named.
* GHSA-45hf-2fmj-q442 — `cloud.{aws_s3,azure,gcs}.upload` read a caller-supplied
  `file_path` with no sandbox check, while their download twins have one.
* GHSA-f9q4-fp8j-r5h7 / GHSA-pp5w-w9c3-qfv2 — `llm.agent` fetches a
  caller-supplied inline `base_url` with no SSRF guard, unlike `llm.chat` and
  `ai.model`.
* GHSA-9x26-9vhm-2qhw — `db.postgresql.query` and `db.mongodb.{find,insert}`
  open a TCP connection to whatever host a caller-supplied `connection_string`
  names, unlike `db.mysql.query`.

Every test asserts the guard rejects the input *before* the sink is reached, so
none of them need the optional third-party driver to be installed.
"""

import importlib

import pytest

from core.utils import PathTraversalError, SSRFError


@pytest.fixture
def _no_private_network(monkeypatch):
    monkeypatch.delenv('FLYTO_ALLOW_PRIVATE_NETWORK', raising=False)
    monkeypatch.delenv('FLYTO_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('FLYTO_HTTP_DISABLE_SSRF_GUARD', raising=False)


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


# ---------------------------------------------------------------------------
# GHSA-9x26-9vhm-2qhw — client-supplied DSN as an SSRF primitive
# ---------------------------------------------------------------------------

DSN_MODULES = [
    (
        'core.modules.third_party.database.connectors.postgresql',
        'postgresql_query',
        {'connection_string': 'postgresql://u:p@169.254.169.254:5432/x',
         'query': 'SELECT 1'},
    ),
    (
        'core.modules.third_party.database.connectors.mongodb_find',
        'mongodb_find',
        {'connection_string': 'mongodb://10.0.0.5:27017',
         'database': 'prod', 'collection': 'sessions', 'filter': {}},
    ),
    (
        'core.modules.third_party.database.connectors.mongodb_insert',
        'mongodb_insert',
        {'connection_string': 'mongodb://192.168.1.10:27017',
         'database': 'prod', 'collection': 'audit', 'document': {'a': 1}},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(('module_name', 'handler_name', 'params'), DSN_MODULES)
async def test_client_dsn_cannot_reach_a_private_target(
    _no_private_network, module_name, handler_name, params,
):
    """The guard must fire before the driver import, so a deployment without
    asyncpg/motor installed is still protected rather than accidentally safe."""
    module = importlib.import_module(module_name)

    with pytest.raises(SSRFError):
        await _handler(module, handler_name)({'params': params})


@pytest.mark.asyncio
async def test_mongodb_multi_host_dsn_checks_every_host(_no_private_network):
    """`mongodb://public,internal/db` must not pass on the strength of its
    first host — urlsplit only reports that one."""
    module = importlib.import_module(
        'core.modules.third_party.database.connectors.mongodb_find'
    )

    with pytest.raises(SSRFError):
        await _handler(module, 'mongodb_find')({'params': {
            'connection_string': 'mongodb://example.com:27017,169.254.169.254:27017/x',
            'database': 'prod',
            'collection': 'sessions',
            'filter': {},
        }})


@pytest.mark.asyncio
async def test_loopback_dsn_stays_allowed(_no_private_network):
    """Self-hosted Postgres on localhost is the normal case; blocking it would
    break deployments without closing a path. Reaching the missing driver is
    the proof that the guard passed."""
    module = importlib.import_module(
        'core.modules.third_party.database.connectors.postgresql'
    )

    with pytest.raises((ImportError, OSError, Exception)) as excinfo:
        await _handler(module, 'postgresql_query')({'params': {
            'connection_string': 'postgresql://u:p@127.0.0.1:1/x',
            'query': 'SELECT 1',
        }})
    assert not isinstance(excinfo.value, SSRFError)


# ---------------------------------------------------------------------------
# GHSA-45hf-2fmj-q442 — upload modules read any host file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aws_s3_upload_confines_file_path(monkeypatch, tmp_path):
    _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'outside' / 'credentials'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('aws_secret_access_key = REAL')
    module = importlib.import_module('core.modules.third_party.cloud.storage')

    with pytest.raises(PathTraversalError):
        await _handler(module, 'aws_s3_upload')({'params': {
            'file_path': str(secret),
            'bucket': 'attacker-bkt',
            'key': 'loot',
            'aws_access_key_id': 'AKIAEXAMPLE',
            'aws_secret_access_key': 'attacker-secret',
        }})


@pytest.mark.asyncio
@pytest.mark.parametrize(('module_name', 'class_name', 'params'), [
    (
        'core.modules.third_party.cloud.azure',
        'AzureUploadModule',
        {'container': 'x', 'blob_name': 'loot',
         'connection_string': 'DefaultEndpointsProtocol=https;AccountName=a;AccountKey=k;'},
    ),
    (
        'core.modules.third_party.cloud.gcs',
        'GCSUploadModule',
        {'bucket': 'attacker-bkt', 'object_name': 'loot'},
    ),
])
async def test_class_upload_modules_confine_file_path(
    monkeypatch, tmp_path, module_name, class_name, params,
):
    _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'outside' / 'id_rsa'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('PRIVATE KEY')
    module = importlib.import_module(module_name)
    module_class = getattr(module, class_name)

    with pytest.raises(PathTraversalError):
        instance = module_class({**params, 'file_path': str(secret)}, {})
        await instance.execute()


@pytest.mark.asyncio
async def test_upload_inside_the_sandbox_still_works(monkeypatch, tmp_path):
    """The guard must confine the read, not forbid uploading. Reaching the
    missing SDK is the proof that the path was accepted."""
    sandbox = _sandbox(monkeypatch, tmp_path)
    payload = sandbox / 'report.csv'
    payload.write_text('a,b\n1,2\n')
    module = importlib.import_module('core.modules.third_party.cloud.storage')

    with pytest.raises(ImportError):
        await _handler(module, 'aws_s3_upload')({'params': {
            'file_path': str(payload),
            'bucket': 'my-bucket',
            'key': 'report.csv',
            'aws_access_key_id': 'AKIAEXAMPLE',
            'aws_secret_access_key': 'secret',
        }})


# ---------------------------------------------------------------------------
# GHSA-f9q4-fp8j-r5h7 / GHSA-pp5w-w9c3-qfv2 — llm.agent inline base_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('target', [
    'http://169.254.169.254/v1',
    'http://10.0.0.5:54331/v1',
    'http://127.0.0.1:9300/v1',
])
def test_llm_agent_inline_base_url_is_ssrf_guarded(_no_private_network, target):
    """The credential guard on this path allows public attacker hosts by
    design, so it was never an SSRF control. A caller-supplied key made it
    no-op entirely."""
    agent = importlib.import_module('core.modules.atomic.llm.agent')

    with pytest.raises(SSRFError):
        agent._resolve_chat_model({'params': {
            'provider': 'openai',
            'model': 'gpt-4o',
            'api_key': 'sk-caller-own-key',
            'base_url': target,
        }})


def test_llm_agent_sub_node_config_base_url_is_ssrf_guarded(_no_private_network):
    """The backward-compat sub-node config dict reaches the same builder and
    must not be a way around the check."""
    agent = importlib.import_module('core.modules.atomic.llm.agent')

    with pytest.raises(SSRFError):
        agent._resolve_chat_model({'inputs': {'model': {
            '__data_type__': 'ai_model',
            'config': {
                'provider': 'openai',
                'model': 'gpt-4o',
                'api_key': 'sk-caller-own-key',
                'base_url': 'http://169.254.169.254/v1',
            },
        }}})


@pytest.mark.asyncio
async def test_llm_agent_reports_ssrf_blocked(_no_private_network):
    """Surfaced as the same error_code its guarded siblings use, not as a
    generic failure."""
    agent = importlib.import_module('core.modules.atomic.llm.agent')

    result = await _handler(agent, 'llm_agent')({'params': {
        'task': 'Say hello',
        'provider': 'openai',
        'model': 'gpt-4o',
        'api_key': 'sk-caller-own-key',
        'base_url': 'http://169.254.169.254/v1',
    }})

    assert result['ok'] is False
    assert result['error_code'] == 'SSRF_BLOCKED'


# ---------------------------------------------------------------------------
# GHSA-4346-4gqg-59f9 — BaseIntegration._request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_request_blocks_private_target(_no_private_network):
    """A caller-named Jira domain is an outbound target like any other."""
    jira = importlib.import_module('core.modules.integrations.jira.integration')

    integration = jira.JiraIntegration(
        domain='169.254.169.254',
        email='ops@example.com',
        api_token='operator-token',
    )
    try:
        with pytest.raises(SSRFError):
            await integration.create_issue(project_key='X', summary='y')
    finally:
        await integration.close()


@pytest.mark.asyncio
async def test_env_credentials_are_not_sent_to_a_caller_named_host(
    _no_private_network, monkeypatch,
):
    """The exfiltration half: the target is a perfectly ordinary public host,
    so the SSRF guard passes it. What must not travel there is the operator's
    own credential."""
    from core.modules.integrations.base import IntegrationCredentialError

    monkeypatch.setenv('JIRA_EMAIL', 'ops@example.com')
    monkeypatch.setenv('JIRA_API_TOKEN', 'operator-token')
    monkeypatch.setenv('JIRA_DOMAIN', 'real-tenant.atlassian.net')
    monkeypatch.delenv('FLYTO_TRUSTED_INTEGRATION_HOSTS', raising=False)
    create_issue = importlib.import_module(
        'core.modules.integrations.jira.modules.create_issue'
    )

    module = create_issue.JiraCreateIssueModule({
        'domain': 'attacker.example.com',
        'project_key': 'X',
        'summary': 'y',
    }, {})

    with pytest.raises(IntegrationCredentialError):
        await module.execute()


@pytest.mark.asyncio
async def test_salesforce_env_token_is_not_sent_to_a_caller_named_host(
    _no_private_network, monkeypatch,
):
    from core.modules.integrations.base import IntegrationCredentialError

    monkeypatch.setenv('SALESFORCE_ACCESS_TOKEN', 'operator-bearer-token')
    monkeypatch.setenv('SALESFORCE_INSTANCE_URL', 'https://real.my.salesforce.com')
    monkeypatch.delenv('FLYTO_TRUSTED_INTEGRATION_HOSTS', raising=False)
    query = importlib.import_module(
        'core.modules.integrations.salesforce.modules.query'
    )

    module = query.SalesforceQueryModule({
        'instance_url': 'https://attacker.example.com',
        'soql': 'SELECT Id FROM Account',
    }, {})

    with pytest.raises(IntegrationCredentialError):
        await module.execute()


@pytest.mark.asyncio
async def test_caller_supplied_credentials_may_go_to_a_caller_named_host(
    _no_private_network, monkeypatch,
):
    """A caller's own token is the caller's own secret. Refusing it would break
    the multi-tenant case the modules exist for, and closes nothing — the SSRF
    guard still governs where the request goes. Reaching the network is the
    proof that both guards passed."""
    monkeypatch.delenv('JIRA_EMAIL', raising=False)
    monkeypatch.delenv('JIRA_API_TOKEN', raising=False)
    monkeypatch.delenv('JIRA_DOMAIN', raising=False)
    create_issue = importlib.import_module(
        'core.modules.integrations.jira.modules.create_issue'
    )
    jira_module = importlib.import_module(
        'core.modules.integrations.jira.integration'
    )

    reached = {}

    async def _fake_request(self, method, endpoint, **kwargs):
        reached['url'] = self._build_url(endpoint)
        from core.modules.integrations.base import APIResponse
        return APIResponse(ok=True, status=201, data={'key': 'X-1', 'id': '1'})

    monkeypatch.setattr(
        jira_module.JiraIntegration, '_request', _fake_request, raising=False,
    )

    module = create_issue.JiraCreateIssueModule({
        'domain': 'their-own-tenant.atlassian.net',
        'project_key': 'X',
        'summary': 'y',
        'email': 'caller@example.com',
        'api_token': 'caller-own-token',
    }, {})
    result = await module.execute()

    assert result['ok'] is True
    assert 'their-own-tenant.atlassian.net' in reached['url']


def test_env_credential_target_guard_honours_the_operator_allowlist(monkeypatch):
    """An operator running a Jira behind their own proxy needs a way to say so
    that is not 'turn the guard off'."""
    from core.modules.integrations.base import (
        IntegrationCredentialError,
        assert_env_credential_target_allowed,
    )

    monkeypatch.setenv('FLYTO_TRUSTED_INTEGRATION_HOSTS', 'jira-proxy.corp,*.mycorp.com')

    assert_env_credential_target_allowed(
        'https://jira-proxy.corp/rest/api/3/issue',
        service_name='jira', operator_hosts=(), credentials_from_env=True,
    )
    assert_env_credential_target_allowed(
        'https://anything.mycorp.com/rest/api',
        service_name='jira', operator_hosts=(), credentials_from_env=True,
    )
    with pytest.raises(IntegrationCredentialError):
        assert_env_credential_target_allowed(
            'https://evil.example.com/rest/api',
            service_name='jira', operator_hosts=(), credentials_from_env=True,
        )


# ---------------------------------------------------------------------------
# Found by the gates rather than by a report: the same asymmetry as
# GHSA-45hf-2fmj-q442 — a guarded twin in the same file vouching for an
# unguarded sibling — in three modules nobody had written up.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_qrcode_logo_path_is_confined(monkeypatch, tmp_path):
    """`output_path` was confined; `logo_path` was opened and its pixels
    embedded in the returned image."""
    _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'outside' / 'private.png'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_bytes(b'\x89PNG\r\n\x1a\n')
    module = importlib.import_module('core.modules.atomic.image.qrcode_generate')

    with pytest.raises(PathTraversalError):
        await _handler(module, 'qrcode_generate')({'params': {
            'data': 'https://example.com',
            'logo_path': str(secret),
        }})


def test_verify_annotate_image_path_is_confined(monkeypatch, tmp_path):
    """`output_path` was confined; the image being read was not, and it is
    drawn into that output."""
    _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'outside' / 'screenshot.png'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_bytes(b'\x89PNG\r\n\x1a\n')
    module = importlib.import_module('core.modules.atomic.verify.annotate')

    with pytest.raises(PathTraversalError):
        module.VerifyAnnotateModule({
            'image_path': str(secret),
            'annotations': [{'label': 'x', 'x': 0, 'y': 0, 'width': 1, 'height': 1}],
        }, {})


def test_load_ruleset_rejects_an_absolute_path_outside_the_sandbox(
    monkeypatch, tmp_path,
):
    """`save_ruleset` moved to the shared helper for GHSA-p34x-fmph-9fjx;
    `load_ruleset` kept the '..' denylist that advisory called insufficient."""
    _sandbox(monkeypatch, tmp_path)
    secret = tmp_path / 'outside' / 'rules.yaml'
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text('rules: []\n')
    ruleset = importlib.import_module('core.modules.atomic.verify.ruleset')

    with pytest.raises(PathTraversalError):
        ruleset.load_ruleset(str(secret))


def test_azure_connection_string_endpoint_is_guarded(_no_private_network):
    """The whole destination arrives as one string, so the endpoint inside it
    never looked like a network parameter."""
    from core.modules.third_party.cloud._azure_endpoint import enforce_azure_endpoint

    with pytest.raises(SSRFError):
        enforce_azure_endpoint(
            'DefaultEndpointsProtocol=https;AccountName=a;AccountKey=k;'
            'BlobEndpoint=http://169.254.169.254/;'
        )

    # No endpoint and no account: the development-storage form, which resolves
    # to the local emulator the host guard permits anyway.
    assert enforce_azure_endpoint('UseDevelopmentStorage=true')
