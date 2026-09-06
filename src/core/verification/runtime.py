"""Deterministic suite execution with attempt-local evidence and bounded cleanup."""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .contracts import Step, Suite, digest, evaluate

AdapterCall = Callable[[Step, dict], Awaitable[dict]]


class BlockedError(Exception):
    """The operation cannot execute inside the approved environment."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verdict(outcomes: list[str]) -> str:
    if not outcomes:
        return 'not-run'
    for status in ('cancelled', 'timeout', 'error', 'fail', 'blocked', 'not-run'):
        if status in outcomes:
            return status
    return 'pass' if all(s == 'pass' for s in outcomes) else 'skipped'


async def run_step(step: Step, phase: str, attempt: int, context: dict, call: AdapterCall) -> dict:
    receipt = {'step_id': step.id, 'adapter': step.adapter, 'connection': step.connection,
               'phase': phase, 'attempt': attempt, 'started_at': now(), 'outcome': 'not-run',
               'assertions': [], 'run_id': context['run_id']}
    try:
        observation = await asyncio.wait_for(call(step, context), step.timeout_ms / 1000)
        receipt['assertions'] = [evaluate(a, observation) for a in step.assertions]
        receipt['observation'] = observation
        receipt['outcome'] = verdict([a['outcome'] for a in receipt['assertions']])
    except TimeoutError:
        receipt.update(outcome='timeout', reason='step_deadline_exceeded')
    except BlockedError:
        receipt.update(outcome='blocked', reason='operation_outside_environment_contract')
    except asyncio.CancelledError:
        receipt.update(outcome='cancelled', reason='execution_cancelled')
        raise
    except Exception:
        # Exception text may contain credentials, SQL values, or response bodies.
        receipt.update(outcome='error', reason='adapter_execution_error')
    finally:
        receipt['ended_at'] = now()
        context['receipts'].append(receipt)
    return receipt


async def interruptible_step(step, phase, attempt, context, call, remaining, cancel):
    operation = asyncio.create_task(run_step(step, phase, attempt, context, call))
    cancellation = asyncio.create_task(cancel.wait())
    try:
        done, _ = await asyncio.wait([operation, cancellation], timeout=remaining,
                                     return_when=asyncio.FIRST_COMPLETED)
        if cancellation in done or operation not in done:
            operation.cancel()
            with suppress(asyncio.CancelledError):
                await operation
            if cancellation in done:
                raise asyncio.CancelledError()
            raise TimeoutError()
        return await operation
    finally:
        cancellation.cancel()


async def execute_suite(suite: Suite, environment: dict, call: AdapterCall, *,
                        run_id: str | None = None, cancel: asyncio.Event | None = None,
                        progress: Callable[[dict], None] | None = None) -> dict:
    """Every run gets a fresh result graph, including not-run cases and teardown evidence."""
    run_id = run_id or str(uuid.uuid4())
    cancel = cancel or asyncio.Event()
    started = time.monotonic()
    result = {'schema_version': 'flyto.product-verification.result.v1', 'run_id': run_id,
              'suite': {'id': suite.id, 'version': suite.version, 'digest': digest(suite.model_dump())},
              'environment': environment, 'runner': 'flyto-core.verification.v1',
              'started_at': now(), 'outcome': 'not-run', 'cases': []}
    for case in suite.cases:
        result['cases'].append({'case_id': case.id, 'name': case.name, 'version': case.version,
                                'outcome': 'not-run', 'attempts': []})
    statuses = {}
    for case, row in zip(suite.cases, result['cases'], strict=True):
        if cancel.is_set():
            row['outcome'] = 'cancelled'
        elif (time.monotonic() - started) * 1000 >= suite.timeout_ms:
            row['outcome'] = 'timeout'
        elif case.skipped:
            row['outcome'] = 'skipped'
        elif any(statuses.get(dep) != 'pass' for dep in case.depends_on):
            row['outcome'] = 'blocked'
            row['reason'] = 'dependency_did_not_pass'
        else:
            for attempt in range(1, case.retries + 2):
                receipts = []
                context = {'run_id': run_id, 'attempt_id': f'{run_id}:{case.id}:{attempt}',
                           'case_id': case.id, 'attempt': attempt, 'receipts': receipts}
                execution_outcome = 'pass'
                try:
                    for phase, steps in [('precondition', case.preconditions), ('test', case.steps)]:
                        for step in steps:
                            if cancel.is_set():
                                execution_outcome = 'cancelled'
                                break
                            remaining = suite.timeout_ms / 1000 - (time.monotonic() - started)
                            if remaining <= 0:
                                execution_outcome = 'timeout'
                                break
                            receipt = await interruptible_step(step, phase, attempt, context, call, remaining, cancel)
                            if receipt['outcome'] != 'pass':
                                execution_outcome = 'blocked' if phase == 'precondition' else receipt['outcome']
                                break
                        if execution_outcome != 'pass':
                            break
                except TimeoutError:
                    execution_outcome = 'timeout'
                except asyncio.CancelledError:
                    execution_outcome = 'cancelled'
                    cancel.set()
                finally:
                    for step in case.cleanup:
                        await run_step(step, 'cleanup', attempt, context, call)
                cleanup_failed = any(r['phase'] == 'cleanup' and r['outcome'] != 'pass' for r in receipts)
                attempt_outcome = 'error' if cleanup_failed else execution_outcome
                row['attempts'].append({'attempt': attempt, 'outcome': attempt_outcome,
                                        'cleanup_failed': cleanup_failed, 'evidence': receipts})
                row['outcome'] = attempt_outcome
                if progress:
                    progress(result)
                if attempt_outcome in ('pass', 'blocked', 'cancelled', 'timeout') or cleanup_failed:
                    break
        statuses[case.id] = row['outcome']
    result['outcome'] = verdict([r['outcome'] for r in result['cases']])
    result['ended_at'] = now()
    result['duration_ms'] = int((time.monotonic() - started) * 1000)
    result['evidence_digest'] = digest(result)
    return result
