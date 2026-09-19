"""Bounded, executable test definitions; credentials never belong in this model."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Outcome = Literal['pass', 'fail', 'error', 'blocked', 'skipped', 'cancelled', 'timeout', 'not-run']
Adapter = Literal['http', 'postgres', 'web']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Assertion(Contract):
    id: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=256)
    operator: Literal['equals', 'contains', 'exists'] = 'equals'
    expected: Any = None


class Step(Contract):
    id: str = Field(min_length=1, max_length=80)
    adapter: Adapter
    connection: str = Field(min_length=1, max_length=80)
    input: dict[str, Any] = Field(default_factory=dict)
    assertions: list[Assertion] = Field(min_length=1, max_length=30)
    timeout_ms: int = Field(default=10000, ge=10, le=60000)


class Case(Contract):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    depends_on: list[str] = Field(default_factory=list, max_length=30)
    preconditions: list[Step] = Field(default_factory=list, max_length=10)
    steps: list[Step] = Field(min_length=1, max_length=30)
    cleanup: list[Step] = Field(default_factory=list, max_length=10)
    retries: int = Field(default=0, ge=0, le=2)
    retry_safe: bool = False
    skipped: bool = False

    @model_validator(mode='after')
    def unique_steps(self):
        ids = [s.id for s in self.preconditions + self.steps + self.cleanup]
        if len(ids) != len(set(ids)):
            raise ValueError('step IDs must be unique within a case')
        if self.retries and not self.retry_safe:
            raise ValueError('retries require an explicitly retry-safe case')
        return self


class Suite(Contract):
    schema_version: Literal['flyto.product-verification.suite.v1'] = 'flyto.product-verification.suite.v1'
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    cases: list[Case] = Field(min_length=1, max_length=100)
    timeout_ms: int = Field(default=120000, ge=10, le=600000)

    @model_validator(mode='after')
    def ordered_dependencies(self):
        seen = set()
        for case in self.cases:
            if case.id in seen or any(dep not in seen for dep in case.depends_on):
                raise ValueError('case IDs must be unique and dependencies must precede the case')
            seen.add(case.id)
        if len(self.model_dump_json()) > 262144:
            raise ValueError('suite definition exceeds 256 KiB')
        return self


def digest(value: Any) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def observe(data: Any, path: str) -> tuple[bool, Any]:
    """Resolve an explicit JSON pointer without expression evaluation."""
    if not path.startswith('/'):
        return False, None
    try:
        for part in path[1:].split('/'):
            part = part.replace('~1', '/').replace('~0', '~')
            data = data[int(part)] if isinstance(data, list) else data[part]
        return True, data
    except (KeyError, IndexError, TypeError, ValueError):
        return False, None


def evaluate(assertion: Assertion, observation: dict) -> dict:
    found, actual = observe(observation, assertion.path)
    passed = found
    if assertion.operator == 'equals':
        passed = found and type(actual) is type(assertion.expected) and actual == assertion.expected
    elif assertion.operator == 'contains':
        passed = found and isinstance(actual, (str, list, dict)) and assertion.expected in actual
    return {**assertion.model_dump(), 'actual': actual, 'observed': found, 'outcome': 'pass' if passed else 'fail'}
