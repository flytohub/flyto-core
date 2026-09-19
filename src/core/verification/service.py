"""Suite execution routes mounted on the existing authenticated runner app.

The Engine persists definitions, execution snapshots and terminal results.
This bounded process-local registry only represents currently hosted work;
a restart is observable as an unavailable runner execution, never a pass.
"""
from __future__ import annotations

import asyncio
import importlib.util
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import Field

from .adapters import Adapters, Connection
from .contracts import Contract, Suite, digest
from .runtime import execute_suite, now

MAX_RECORDS = 1000
RETENTION_SECONDS = 3600


def prune_records(records, *, reserve=False):
    terminal = sorted((row['finished_at'], key) for key, row in records.items()
                      if row.get('finished_at') is not None)
    cutoff = time.monotonic() - RETENTION_SECONDS
    for finished, key in terminal:
        if finished <= cutoff or (reserve and len(records) >= MAX_RECORDS):
            records.pop(key, None)


async def adapter_readiness():
    ready = {'http': True, 'postgres': importlib.util.find_spec('asyncpg') is not None, 'web': False}
    if importlib.util.find_spec('playwright') is not None:
        from playwright.async_api import async_playwright
        try:
            async with async_playwright() as browser:
                ready['web'] = Path(browser.chromium.executable_path).is_file()
        except Exception:
            pass
    return ready


def failed_result(body, partial):
    result = dict(partial or {})
    result.pop('evidence_digest', None)
    result.update(schema_version='flyto.product-verification.result.v1', run_id=body.run_id,
                  suite={'id': body.suite.id, 'version': body.suite.version, 'digest': digest(body.suite.model_dump())},
                  environment=body.environment, runner='flyto-core.verification.v1',
                  outcome='error', reason='runner_execution_error', ended_at=now())
    result.setdefault('started_at', result['ended_at'])
    result.setdefault('cases', [{'case_id': case.id, 'name': case.name, 'version': case.version,
                                 'outcome': 'not-run', 'attempts': []} for case in body.suite.cases])
    result['evidence_digest'] = digest(result)
    return result


class SuiteRunRequest(Contract):
    run_id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    org_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    suite: Suite
    environment: dict[str, Any] = Field(max_length=16)
    connections: dict[str, dict[str, Any]] = Field(max_length=20)


def mount_suite_routes(app, authenticate):
    records = {}
    tasks = {}

    def owned(run_id, org_id, project_id):
        prune_records(records)
        row = records.get(run_id)
        if row is None or row['org_id'] != org_id or row['project_id'] != project_id:
            raise HTTPException(404, 'runner execution unavailable')
        return row

    @app.get('/suite-capabilities', dependencies=[Depends(authenticate)])
    async def capabilities():
        ready = await adapter_readiness()
        return {'schema_version': 'flyto.product-verification.runner.v1',
                'adapters': [key for key, available in ready.items() if available],
                'adapter_readiness': ready, 'max_concurrency': 4,
                'active': len(tasks), 'web_scope': 'isolated_ip_fixture',
                'database_scope': 'provisioned_query_readonly',
                'state': 'ready' if all(ready.values()) else 'degraded',
                'terminal_retention_seconds': RETENTION_SECONDS, 'max_records': MAX_RECORDS}

    @app.post('/suite-runs', dependencies=[Depends(authenticate)])
    async def submit(body: SuiteRunRequest):
        prune_records(records)
        request_digest = digest(body.model_dump())
        if body.run_id in records:
            row = owned(body.run_id, body.org_id, body.project_id)
            if row['request_digest'] != request_digest:
                raise HTTPException(409, 'run ID is already bound to another request')
            return {'execution_id': body.run_id, 'status': row['status']}
        prune_records(records, reserve=True)
        if len(tasks) >= 4 or len(records) >= MAX_RECORDS:
            raise HTTPException(429, 'runner capacity reached')
        try:
            connections = {key: Connection(**value) for key, value in body.connections.items()}
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, 'invalid connection bindings') from exc
        row = {'org_id': body.org_id, 'project_id': body.project_id,
               'request_digest': request_digest, 'status': 'running', 'result': None, 'cancel': asyncio.Event()}
        records[body.run_id] = row

        async def work():
            try:
                row['result'] = await execute_suite(body.suite, body.environment, Adapters(connections),
                    run_id=body.run_id, cancel=row['cancel'], progress=lambda result: row.update(result=result))
                row['status'] = 'complete'
            except Exception:
                row['result'] = failed_result(body, row['result'])
                row['status'] = 'error'
            finally:
                row['finished_at'] = time.monotonic()
                tasks.pop(body.run_id, None)
        tasks[body.run_id] = asyncio.create_task(work())
        return {'execution_id': body.run_id, 'status': 'running'}

    @app.get('/suite-runs/{run_id}', dependencies=[Depends(authenticate)])
    async def read(run_id: str, org_id: str, project_id: str):
        row = owned(run_id, org_id, project_id)
        return {'execution_id': run_id, 'status': row['status'], 'result': row['result']}

    @app.post('/suite-runs/{run_id}/cancel', dependencies=[Depends(authenticate)])
    async def cancel(run_id: str, org_id: str, project_id: str):
        row = owned(run_id, org_id, project_id)
        task = tasks.get(run_id)
        if task:
            row['cancel'].set()
        return {'execution_id': run_id, 'status': row['status'], 'cancel_requested': task is not None}
