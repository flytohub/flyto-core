# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Scheduler Delay Module
Async delay/sleep for workflow timing control.

WHY THIS ONE CAN CLAIM `verified`, WHEN ALMOST NOTHING CAN

`verified` is defined as "a postcondition was evaluated and it held", and the
reason it is out of reach for nearly every side-effecting module is not the
missing declaration -- it is that the module has no way to look at the thing it
changed. `file.write` can stat the file and still not claim it, because
`st_size` does not establish durability: there is more reality past the
measurement.

There is no more reality past the measurement here. This module's entire
contract is "execution paused for `seconds`", the caller states the duration,
and elapsed time is directly measurable with a monotonic clock. So the
predicate is declared on the decorator --

    at least `seconds` of monotonic time elapsed between entry and return

-- and evaluated below, on the raw `time.monotonic()` difference. `claim_by` is
CALLER, because `seconds` is the caller's number: when the predicate does not
hold, a contract somebody asked for was broken, and `outcome.py` calls that
FAILED rather than INDETERMINATE.

THE TOLERANCE, and why there is one. asyncio's event loop is allowed to fire a
timer early by up to the monotonic clock's resolution: `base_events._run_once`
compares against `self.time() + self._clock_resolution`, so a correct
`asyncio.sleep` can return a few nanoseconds short. A predicate without that
slack would mark correct sleeps FAILED on a fast clock, which is the same
mistake as `file.write` calling a newline-translated write a failure. The
tolerance is `time.get_clock_info('monotonic').resolution` -- the same quantity
the event loop uses, not a hand-picked fudge.

The predicate is evaluated on the unrounded elapsed time on purpose.
`delayed_seconds` is rounded to milliseconds for readability, and rounding can
move a value by up to half a millisecond -- enough to turn a delay that
genuinely satisfied the request into a report that says it did not.

WHAT IS NOT CLAIMED: that the delay was no LONGER than asked. An event loop
that is busy will overshoot by however long it is busy, and no rung here says
otherwise. The postcondition is a floor, and it is written as one.
"""
import asyncio
import logging
import time
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

#: The predicate, in the one place both the declaration and the evaluation can
#: read it. `register_module(postcondition=...)` is what lets the engine leave a
#: `verified` claim standing (`outcome.ceiling_for`); the function below is what
#: makes the claim true.
POSTCONDITION = 'at least `seconds` of monotonic time elapsed between entry and return'

#: The slack asyncio itself allows a timer, from the same source asyncio reads:
#: `base_events.BaseEventLoop.__init__` sets `_clock_resolution` to exactly this
#: and `_run_once` fires any callback due within it. Typically ~1e-9 s.
CLOCK_RESOLUTION = time.get_clock_info('monotonic').resolution


def _delay_outcome(*, requested: float, elapsed: float) -> Dict[str, Any]:
    """VERIFIED when the floor held, FAILED when it did not.

    Pure, and takes the elapsed time rather than measuring it, so the failing
    branch is reachable in a test without having to break a clock.
    """
    held = elapsed >= requested - CLOCK_RESOLUTION
    measurement = {
        'kind': 'monotonic_elapsed',
        'requested_seconds': requested,
        'elapsed_seconds': elapsed,
        'tolerance_seconds': CLOCK_RESOLUTION,
        'measured_by': (
            'time.monotonic() read before and after the sleep, unrounded'
        ),
        'detail': (
            'A floor, not a window: a busy event loop overshoots and nothing '
            'here objects. The tolerance is the monotonic clock resolution, '
            'which is the slack asyncio allows a timer to fire early.'
        ),
    }

    if held:
        return envelope(
            Outcome.VERIFIED,
            # CALLER: `seconds` is the caller's number, so a violation is a
            # broken contract rather than an inference of ours going wrong.
            claim_by=ClaimBy.CALLER,
            postcondition=POSTCONDITION,
            effects=[measurement],
        )
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.CALLER,
        postcondition=POSTCONDITION,
        effects=[
            measurement,
            {
                'kind': 'delay_shorter_than_requested',
                'predicate': POSTCONDITION,
                'short_by_seconds': requested - elapsed,
                'detail': (
                    'Execution resumed before the requested duration had '
                    'passed, by more than the clock resolution. The caller '
                    'asked for this duration, so this is a failed '
                    'postcondition and not an unknown.'
                ),
            },
        ],
    )


@register_module(
    module_id='scheduler.delay',
    version='1.0.0',
    category='scheduler',
    tags=['scheduler', 'delay', 'sleep', 'wait', 'pause'],
    label='Delay / Sleep',
    label_key='modules.scheduler.delay.label',
    description='Pause execution for a specified duration',
    description_key='modules.scheduler.delay.description',
    icon='Clock',
    color='#7C3AED',
    input_types=['any'],
    output_types=['json'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=False,
    concurrent_safe=True,

    # The declaration that lets the claim below stand. Without it the engine
    # caps this module at `observed` (core/engine/outcome.py, ceiling_for) --
    # `verified` means a postcondition was evaluated, and an undeclared module
    # has no predicate the claim could be about. See the module docstring for
    # why this one is genuinely provable when almost none are.
    postcondition=POSTCONDITION,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'seconds',
            type='number',
            label='Delay Seconds',
            label_key='modules.scheduler.delay.params.seconds.label',
            description='Number of seconds to delay',
            description_key='modules.scheduler.delay.params.seconds.description',
            required=True,
            min=0,
            max=3600,
            group=FieldGroup.BASIC,
        ),
        field(
            'message',
            type='string',
            label='Message',
            label_key='modules.scheduler.delay.params.message.label',
            description='Optional message to include in the result',
            description_key='modules.scheduler.delay.params.message.description',
            placeholder='Waiting for rate limit...',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'delayed_seconds': {
            'type': 'number',
            'description': 'Actual number of seconds delayed',
            'description_key': 'modules.scheduler.delay.output.delayed_seconds.description',
        },
        'message': {
            'type': 'string',
            'description': 'The provided message or default',
            'description_key': 'modules.scheduler.delay.output.message.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the pause was followed: "verified" when at least the '
                'requested monotonic time elapsed, "failed" when execution '
                'resumed early. A floor, not a window -- overshoot is not '
                'reported as a violation'
            ),
            'description_key': 'modules.scheduler.delay.output.outcome.description',
        },
    },
    timeout_ms=3660000,  # slightly more than max delay (1 hour + 1 minute)
)
async def scheduler_delay(context: Dict[str, Any]) -> Dict[str, Any]:
    """Pause execution for a specified duration."""
    params = context['params']
    seconds = params.get('seconds')

    if seconds is None:
        raise ValidationError("Missing required parameter: seconds", field="seconds")

    seconds = float(seconds)
    if seconds < 0:
        raise ValidationError("Delay seconds must be >= 0", field="seconds")
    if seconds > 3600:
        raise ValidationError(
            "Delay seconds must be <= 3600 (1 hour)",
            field="seconds",
            hint="For longer delays, consider using a scheduler or cron job"
        )

    message = params.get('message', 'Delay completed')

    start = time.monotonic()
    await asyncio.sleep(seconds)
    # Unrounded: the predicate is evaluated on this, `delayed_seconds` reports
    # the rounded one. Rounding to milliseconds can move a value by half a
    # millisecond, which is enough to make a delay that satisfied the request
    # read as one that did not.
    elapsed = time.monotonic() - start
    actual_delay = round(elapsed, 3)

    return {
        'ok': True,
        'data': {
            'delayed_seconds': actual_delay,
            'message': message,
            'outcome': _delay_outcome(requested=seconds, elapsed=elapsed),
        }
    }
