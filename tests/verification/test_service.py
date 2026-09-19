import asyncio

import httpx
import pytest

from core.verification import service
from core.verification.contracts import digest
from core.verification_service import create_app


def request_body():
    return {'run_id': 'run-1', 'org_id': 'org-1', 'project_id': 'project-1',
            'environment': {'id': 'env', 'version': 1, 'stage': 'test'}, 'connections': {},
            'suite': {'id': 'suite', 'name': 'Suite', 'cases': [{
                'id': 'case', 'name': 'Case', 'steps': [{
                    'id': 'check', 'adapter': 'http', 'connection': 'missing',
                    'assertions': [{'id': 'ready', 'path': '/body/ready', 'expected': True}],
                }],
            }]}}


@pytest.mark.asyncio
async def test_authenticated_runner_tenant_scope_replay_and_failure_evidence(monkeypatch):
    monkeypatch.setenv('FLYTO_VERIFICATION_API_KEY', 'local-fixture-key')
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runner') as client:
        assert (await client.post('/suite-runs', json=request_body())).status_code == 401
        client.headers['X-Internal-Key'] = 'local-fixture-key'
        response = await client.post('/suite-runs', json=request_body())
        assert response.status_code == 200
        for _ in range(100):
            response = await client.get('/suite-runs/run-1', params={'org_id': 'org-1', 'project_id': 'project-1'})
            if response.json()['status'] != 'running':
                break
            await asyncio.sleep(0.005)
        result = response.json()['result']
        assert result['outcome'] == 'blocked'
        assert result['cases'][0]['attempts'][0]['evidence'][0]['outcome'] == 'blocked'
        assert (await client.get('/suite-runs/run-1', params={'org_id': 'other', 'project_id': 'project-1'})).status_code == 404
        replay = await client.post('/suite-runs', json=request_body())
        assert replay.json()['status'] == 'complete'
        changed = request_body()
        changed['suite']['name'] = 'Different'
        assert (await client.post('/suite-runs', json=changed)).status_code == 409


@pytest.mark.asyncio
async def test_runner_exception_keeps_honest_digested_terminal_result(monkeypatch):
    monkeypatch.setenv('FLYTO_VERIFICATION_API_KEY', 'local-fixture-key')

    async def crash(*args, **kwargs):
        raise RuntimeError('fixture-secret-must-not-appear')

    monkeypatch.setattr(service, 'execute_suite', crash)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://runner',
                                headers={'X-Internal-Key': 'local-fixture-key'}) as client:
        await client.post('/suite-runs', json=request_body())
        await asyncio.sleep(0)
        response = await client.get('/suite-runs/run-1', params={'org_id': 'org-1', 'project_id': 'project-1'})
        payload = response.json()
        assert payload['status'] == 'error'
        result = payload['result']
        assert result['outcome'] == 'error'
        assert result['cases'][0]['outcome'] == 'not-run'
        assert 'fixture-secret' not in response.text
        checksum = result.pop('evidence_digest')
        assert checksum == digest(result)


def test_terminal_retention_never_evicts_active_work(monkeypatch):
    monkeypatch.setattr(service, 'MAX_RECORDS', 3)
    monkeypatch.setattr(service.time, 'monotonic', lambda: 10000)
    records = {'active': {'status': 'running'},
               'old': {'status': 'complete', 'finished_at': 1},
               'recent': {'status': 'complete', 'finished_at': 9998},
               'newest': {'status': 'complete', 'finished_at': 9999}}
    service.prune_records(records)
    assert set(records) == {'active', 'recent', 'newest'}
    service.prune_records(records, reserve=True)
    assert set(records) == {'active', 'newest'}


@pytest.mark.asyncio
async def test_uninstalled_optional_adapters_are_not_advertised_ready(monkeypatch):
    monkeypatch.setattr(service.importlib.util, 'find_spec', lambda _: None)
    assert await service.adapter_readiness() == {'http': True, 'postgres': False, 'web': False}
