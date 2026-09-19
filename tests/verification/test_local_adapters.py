"""Controlled HTTP -> PostgreSQL -> Chromium proof. Never uses production data."""
import os
import uuid
from urllib.parse import urlsplit

import pytest
from aiohttp import web

from core.verification.adapters import Adapters, Connection
from core.verification.contracts import Suite
from core.verification.runtime import execute_suite

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_api_database_ui_flow_and_cleanup(tmp_path):
    dsn = os.environ.get('FLYTO_PV_FIXTURE_PG_URL')
    if not dsn:
        pytest.skip('Set FLYTO_PV_FIXTURE_PG_URL to a disposable PostgreSQL database')
    import asyncpg
    db = await asyncpg.connect(dsn)
    table = 'pv_' + uuid.uuid4().hex
    await db.execute(f'CREATE TABLE {table} (id TEXT PRIMARY KEY, state TEXT NOT NULL)')
    sentinel = 'unrelated_' + uuid.uuid4().hex
    await db.execute(f'INSERT INTO {table} VALUES ($1, $2)', sentinel, 'preserve')

    async def put(request):
        body = await request.json()
        await db.execute(f'INSERT INTO {table} VALUES ($1, $2)', body['id'], 'ready')
        return web.json_response({'created': True, 'id': body['id']}, status=201)

    async def delete(request):
        result = await db.execute(f'DELETE FROM {table} WHERE id=$1', request.match_info['id'])
        return web.json_response({'deleted': result == 'DELETE 1'})

    async def page(request):
        row = await db.fetchrow(f'SELECT state FROM {table} WHERE id=$1', request.match_info['id'])
        return web.Response(text='<main>' + (row['state'] if row else 'missing') + '</main>', content_type='text/html')

    app = web.Application()
    app.router.add_post('/records', put)
    app.router.add_delete('/records/{id}', delete)
    app.router.add_get('/ui/{id}', page)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    endpoint = f'http://127.0.0.1:{port}'
    adapters = Adapters({
        'api': Connection('http', endpoint, isolated=True),
        'db': Connection('postgres', f'postgresql://127.0.0.1:{urlsplit(dsn).port or 5432}', isolated=True, database_dsn=dsn, queries={
            'find_record': f'SELECT state FROM {table} WHERE id=$1',
            'forbidden_write': f'DELETE FROM {table} RETURNING id',
        }),
        'ui': Connection('web', endpoint, isolated=True),
    })
    def step(step_id, adapter, connection, inputs, path, expected):
        return {'id': step_id, 'adapter': adapter, 'connection': connection, 'input': inputs,
                'timeout_ms': 15000, 'assertions': [{'id': step_id, 'path': path, 'expected': expected}]}
    spec = Suite.model_validate({'id': 'checkout', 'name': 'API database UI', 'cases': [{
        'id': 'order', 'name': 'Create and observe an isolated order',
        'steps': [
            step('create', 'http', 'api', {'method': 'POST', 'path': '/records', 'json': {'id': '{{attempt_id}}'}}, '/body/created', True),
            step('database', 'postgres', 'db', {'query_id': 'find_record', 'arguments': ['{{attempt_id}}']}, '/rows/0/state', 'ready'),
            step('ui', 'web', 'ui', {'path': '/ui/{{attempt_id}}', 'selector': 'main'}, '/text', 'ready'),
        ],
        'cleanup': [step('remove', 'http', 'api', {'method': 'DELETE', 'path': '/records/{{attempt_id}}'}, '/body/deleted', True)],
    }]})
    try:
        results = [await execute_suite(spec, {'id': 'fixture', 'version': 1}, adapters) for _ in range(2)]
        for result in results:
            assert result['outcome'] == 'pass', result
            evidence = result['cases'][0]['attempts'][0]['evidence']
            assert [r['adapter'] for r in evidence] == ['http', 'postgres', 'web', 'http']
            assert all(r['outcome'] == 'pass' for r in evidence)
        assert results[0]['run_id'] != results[1]['run_id']
        assert await db.fetchval(f'SELECT count(*) FROM {table}') == 1
        assert await db.fetchval(f'SELECT state FROM {table} WHERE id=$1', sentinel) == 'preserve'
        denied = spec.model_copy(deep=True)
        denied.cases[0].steps = [denied.cases[0].steps[1].model_copy(update={'input': {'query_id': 'forbidden_write'}})]
        denied.cases[0].cleanup = []
        rejected = await execute_suite(denied, {'id': 'fixture', 'version': 1}, adapters)
        assert rejected['outcome'] == 'error'
        assert await db.fetchval(f'SELECT count(*) FROM {table}') == 1
        import json
        (tmp_path / 'cross-layer-evidence.json').write_text(json.dumps(results, indent=2))
    finally:
        await runner.cleanup()
        await db.execute(f'DROP TABLE {table}')
        await db.close()
