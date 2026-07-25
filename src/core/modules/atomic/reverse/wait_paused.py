# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Wait Paused Module

Block until the debugged page hits a breakpoint (or is already paused),
returning the call frames at the pause point.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ...types import StabilityLevel

# Registry timeout must stay above the largest allowed caller timeout_ms so
# BaseModule.run()'s outer asyncio.wait_for (base.py:218) never fires first —
# that would skip the CDP listener cleanup this module relies on the caller
# (reverse.detach) to eventually run.
_MAX_CALLER_TIMEOUT_MS = 300000
_REGISTRY_TIMEOUT_MS = 310000


@register_module(
    module_id='reverse.wait_paused',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'debugger', 'cdp', 'pause', 'breakpoint'],
    label='Wait for Pause',
    label_key='modules.reverse.wait_paused.label',
    description='Block until the page hits a breakpoint',
    description_key='modules.reverse.wait_paused.description',
    icon='Pause',
    color='#DC2626',

    input_types=['object'],
    output_types=['object'],

    can_receive_from=['reverse.*', 'flow.*'],
    can_connect_to=['reverse.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    params_schema=compose(
        presets.TIMEOUT_MS(key='timeout_ms', default=30000, max_ms=_MAX_CALLER_TIMEOUT_MS),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.wait_paused.output.status.description'},
        'paused': {'type': 'boolean', 'description': 'Whether the page paused before the timeout',
                'description_key': 'modules.reverse.wait_paused.output.paused.description'},
        'reason': {'type': 'string', 'description': 'CDP pause reason (e.g. "other", "debuggerStatement")',
                'description_key': 'modules.reverse.wait_paused.output.reason.description'},
        'callFrames': {'type': 'array', 'description': 'Call frames at the pause point',
                'description_key': 'modules.reverse.wait_paused.output.callFrames.description'},
    },
    examples=[
        {'name': 'Wait up to 30s for a breakpoint hit', 'params': {}},
        {'name': 'Wait up to 2 minutes', 'params': {'timeout_ms': 120000}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=_REGISTRY_TIMEOUT_MS,
    required_permissions=['browser.debug'],
)
class ReverseWaitPausedModule(BaseModule):
    """Block until the debugged page hits a breakpoint."""

    module_name = "Wait for Pause"
    module_description = "Block until the page hits a breakpoint"
    required_permission = "browser.debug"

    def validate_params(self) -> None:
        timeout_ms = self.params.get('timeout_ms', 30000)
        self.timeout_ms = min(int(timeout_ms), _MAX_CALLER_TIMEOUT_MS)

    async def execute(self) -> Dict[str, Any]:
        session = self.context.get('reverse_session')
        if not session:
            raise RuntimeError("No active debugger session. Please run reverse.attach first")

        pause = await session.wait_paused(self.timeout_ms / 1000)
        if pause is None:
            return {'status': 'success', 'paused': False}

        return {
            'status': 'success',
            'paused': True,
            'reason': pause.get('reason', ''),
            'callFrames': pause.get('callFrames', []),
        }
