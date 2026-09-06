"""All representations of recorded HTTP JSON must honor secret redaction."""
import json

import pytest
from aiohttp import web

from core.verification.adapters import Adapters, Connection
from core.verification.contracts import Step


@pytest.mark.asyncio
async def test_json_text_cannot_restore_redacted_credentials():
    async def respond(_request):
        return web.json_response({'state': 'ready', 'nested': {'api_key': 'fixture-private-value'}})

    app = web.Application()
    app.router.add_get('/state', respond)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    adapter = Adapters({'api': Connection('http', f'http://127.0.0.1:{port}', isolated=True)})
    step = Step.model_validate({'id': 'observe', 'adapter': 'http', 'connection': 'api',
        'input': {'path': '/state'}, 'assertions': [{'id': 'ready', 'path': '/body/state', 'expected': 'ready'}]})
    try:
        evidence = await adapter(step, {'run_id': 'redaction', 'attempt_id': 'redaction-1', 'case_id': 'safe'})
        assert evidence['body']['state'] == 'ready'
        assert evidence['body']['nested']['api_key'] == '[redacted]'
        assert 'fixture-private-value' not in json.dumps(evidence)
    finally:
        await runner.cleanup()
