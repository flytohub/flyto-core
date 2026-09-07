import asyncio

import pytest
from pydantic import ValidationError

from core.verification.contracts import Assertion, Suite, evaluate
from core.verification.runtime import BlockedError, execute_suite


def suite(**changes):
    body = {'id': 'suite', 'name': 'Suite', 'cases': [{
        'id': 'case', 'name': 'Case', 'steps': [{
            'id': 'check', 'adapter': 'http', 'connection': 'api',
            'assertions': [{'id': 'body', 'path': '/body/ready', 'expected': True}],
        }],
    }]}
    body.update(changes)
    return Suite.model_validate(body)


@pytest.mark.parametrize('observed', [{}, {'body': {}}, {'body': {'ready': 1}}, {'body': {'ready': False}}])
def test_missing_or_wrong_typed_observation_never_passes(observed):
    a = Assertion(id='ready', path='/body/ready', expected=True)
    assert evaluate(a, observed)['outcome'] == 'fail'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,want', [('ok', 'pass'), ('false', 'fail'), ('error', 'error'), ('blocked', 'blocked'), ('slow', 'timeout')])
async def test_real_outcome_contract(mode, want):
    async def adapter(step, context):
        if mode == 'error':
            raise RuntimeError('secret must never leak')
        if mode == 'blocked':
            raise BlockedError()
        if mode == 'slow':
            await asyncio.sleep(0.2)
        return {'body': {'ready': mode == 'ok'}}
    spec = suite()
    spec.cases[0].steps[0].timeout_ms = 10
    result = await execute_suite(spec, {'id': 'env', 'version': 1}, adapter)
    assert result['outcome'] == want
    assert 'secret must never leak' not in str(result)
    assert result['cases'][0]['attempts'][0]['evidence'][0]['assertions'] or want in ('error', 'blocked', 'timeout')


@pytest.mark.asyncio
async def test_retry_and_rerun_evidence_remain_separate():
    async def adapter(step, context):
        return {'body': {'ready': context['attempt'] == 2}}
    spec = suite()
    spec.cases[0].retries = 1
    spec.cases[0].retry_safe = True
    first = await execute_suite(spec, {'id': 'env', 'version': 1}, adapter)
    second = await execute_suite(spec, {'id': 'env', 'version': 1}, adapter)
    assert first['run_id'] != second['run_id']
    assert first['outcome'] == 'pass'
    attempts = first['cases'][0]['attempts']
    assert [a['outcome'] for a in attempts] == ['fail', 'pass']
    assert [a['evidence'][0]['attempt'] for a in attempts] == [1, 2]
    assert first['suite']['digest'] == second['suite']['digest']
    assert first['evidence_digest'] != second['evidence_digest']


@pytest.mark.asyncio
async def test_cleanup_failure_overrides_pass_and_prevents_retry():
    spec = suite()
    cleanup = spec.cases[0].steps[0].model_copy(update={'id': 'cleanup'})
    spec.cases[0].cleanup = [cleanup]
    spec.cases[0].retries = 1
    spec.cases[0].retry_safe = True
    async def adapter(step, context):
        if step.id == 'cleanup':
            raise RuntimeError('unreachable')
        return {'body': {'ready': True}}
    result = await execute_suite(spec, {}, adapter)
    assert result['outcome'] == 'error'
    assert len(result['cases'][0]['attempts']) == 1
    assert result['cases'][0]['attempts'][0]['cleanup_failed']


@pytest.mark.asyncio
async def test_dependencies_and_cancellation_never_convert_to_pass():
    spec = suite()
    spec.cases.append(spec.cases[0].model_copy(update={'id': 'dependent', 'depends_on': ['case']}))
    async def adapter(step, context):
        return {'body': {'ready': False}}
    result = await execute_suite(spec, {}, adapter)
    assert [c['outcome'] for c in result['cases']] == ['fail', 'blocked']
    cancel = asyncio.Event()
    cancel.set()
    cancelled = await execute_suite(spec, {}, adapter, cancel=cancel)
    assert cancelled['outcome'] == 'cancelled'
    assert not cancelled['cases'][0]['attempts']


def test_contract_rejects_empty_assertions_and_forward_dependencies():
    for cases in ([], [{'id': 'case', 'name': 'Case', 'steps': []}]):
        with pytest.raises(ValidationError):
            suite(cases=cases)
    data = suite().model_dump()
    data['cases'][0]['depends_on'] = ['later']
    with pytest.raises(ValidationError):
        Suite.model_validate(data)
