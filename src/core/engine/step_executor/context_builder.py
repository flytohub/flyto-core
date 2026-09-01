# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Step Context Builder

Creates hook context for step-level events.
"""

import time
from datetime import datetime
from typing import Any, Dict, Optional

from ..hooks import HookContext


def create_step_context(
    workflow_id: str,
    workflow_name: str,
    total_steps: int,
    step_config: Dict[str, Any],
    step_index: int,
    context: Dict[str, Any],
    result: Any = None,
    error: Optional[Exception] = None,
    attempt: int = 1,
    max_attempts: int = 1,
    step_start_time: Optional[float] = None,
) -> HookContext:
    """
    Create hook context for step-level events.

    Args:
        workflow_id: Parent workflow ID
        workflow_name: Parent workflow name
        total_steps: Total steps in workflow
        step_config: Step configuration dictionary
        step_index: Index of the step in workflow
        context: Current workflow context
        result: Step execution result (if any)
        error: Exception if step failed
        attempt: Current retry attempt number
        max_attempts: Total retry attempts allowed
        step_start_time: When step execution started

    Returns:
        HookContext for hook callbacks
    """
    step_id = step_config.get('id', f'step_{step_index}')
    module_id = step_config.get('module', '')
    step_params = step_config.get('params', {})

    elapsed_ms = 0.0
    if step_start_time:
        elapsed_ms = (time.time() - step_start_time) * 1000

    hook_context = HookContext(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        step_id=step_id,
        step_index=step_index,
        total_steps=total_steps,
        module_id=module_id,
        params=step_params,
        variables=context.copy(),
        started_at=datetime.fromtimestamp(step_start_time) if step_start_time else None,
        elapsed_ms=elapsed_ms,
        result=result,
        attempt=attempt,
        max_attempts=max_attempts,
    )

    if error:
        hook_context.error = error
        hook_context.error_type = type(error).__name__
        hook_context.error_message = str(error)

    _carry_the_outcome(hook_context, result, error)

    return hook_context


def _carry_the_outcome(hook_context: HookContext, result, error=None) -> None:
    """Put the step's rung where a host can read it.

    Without this the ladder stops at core's own edge. ``verification_status``
    was read by exactly one branch of ``executor.py`` and by nothing in
    flyto-cloud — the field never crossed the boundary, so the twelve-odd
    surfaces that draw an execution for a person had no way to know a step had
    only dispatched an instruction. Zero readers is not a product capability.

    ``HookContext.metadata`` is the channel that already exists and already
    serializes (``models.py:79``), and nothing had ever written to it: the only
    reader in either checkout was ``guards/timeout.py``. So the rung reaches
    every host that installs hooks without one module signature changing, and
    without enabling the trace collector — which is off by default
    (``workflow/engine.py:81``) and which flyto-cloud never turns on, the reason
    the existing machinery has never once fired there.

    Written on both the pre- and post-execute contexts; on the pre-execute one
    both ``result`` and ``error`` are None and the key is simply absent, which
    is the honest state for a step that has not run.

    AND ON THE RAISE PATH, which is where the ladder used to stop dead. A step
    that raised has no return value, so there was nothing to read a rung out of
    and every raise arrived at a host as an execution error -- including the
    ones the contract calls INDETERMINATE. A wait that timed out is the case
    that named this gap: we do not know whether the thing we were waiting for
    happened, only that it had not by the deadline, and reporting that as a
    definite failure is as wrong in its direction as a false green is in its
    own. Now a module that raises `OutcomeError` carries its rung out with it.

    Result first, deliberately. A context carrying BOTH a result and an error
    is describing what the module returned, not what something later raised
    about it.
    """
    # Local import: this module is on the import path of every engine start-up
    # and `outcome` pulls in nothing, but the executor's own import of it is the
    # one that establishes ordering.
    from .executor import step_outcome
    from ..outcome import envelope_from_exception

    found = None
    if result is not None:
        found = step_outcome(result)
        if found is not None:
            rung, claim_by, postcondition = found
            hook_context.metadata['outcome'] = {
                'rung': rung.value,
                'claim_by': claim_by,
                'postcondition': postcondition,
            }
            return

    if error is None:
        return

    # Opt-in only. A module that raised anything else still has no rung here,
    # and reads as FAILED exactly as it did before: inferring a rung from an
    # arbitrary exception would turn every crash in the product into "we cannot
    # say", which invites retrying something that genuinely broke.
    carried = envelope_from_exception(error)
    if carried is None:
        return
    hook_context.metadata['outcome'] = {
        'rung': carried['rung'],
        'claim_by': carried['claim_by'],
        'postcondition': carried['postcondition'],
    }
