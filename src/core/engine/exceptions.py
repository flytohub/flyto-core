# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Workflow Engine Exceptions

Custom exception classes for workflow execution errors.
"""


class StepTimeoutError(Exception):
    """Raised when a step execution times out"""

    def __init__(self, step_id: str, timeout: int):
        self.step_id = step_id
        self.timeout = timeout
        super().__init__(f"Step '{step_id}' timed out after {timeout} seconds")


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails"""

    def __init__(self, message: str, step_id: str = None, original_error: Exception = None):
        self.step_id = step_id
        self.original_error = original_error
        super().__init__(message)


class StepExecutionError(Exception):
    """Raised when a step execution fails"""

    def __init__(self, step_id: str, message: str, original_error: Exception = None):
        self.step_id = step_id
        self.original_error = original_error
        super().__init__(message)


class FlowControlError(Exception):
    """Raised when flow control logic fails"""

    def __init__(self, message: str, step_id: str = None):
        self.step_id = step_id
        super().__init__(message)


class VariableResolutionError(Exception):
    """Raised when variable resolution fails"""

    def __init__(self, variable: str, message: str):
        self.variable = variable
        super().__init__(f"Failed to resolve '{variable}': {message}")


def is_policy_refusal(error) -> bool:
    """True when `error` was raised, at any depth, by the capability gate.

    A capability refusal is not a step error. ``on_error: continue``, an error
    edge, a foreach's per-item tolerance and a parallel batch's non-stop policy
    all exist so a workflow can carry on past something that went wrong. None of
    them is a licence to carry on past a module the operator's policy refused to
    run: the refusal fired precisely because the workflow was not entitled to
    that module, and a workflow that could absorb its own refusal would report
    success while a security control was firing inside it.

    The refusal is re-wrapped on the way up — ModulePolicyError inside a
    StepExecutionError inside a WorkflowExecutionError inside the next engine's
    StepExecutionError, once per nesting level — so the check has to walk the
    chain rather than look at the exception in hand.

    Only the deliberate links are followed: ``original_error`` (this module's
    own wrapping convention) and ``__cause__`` (``raise ... from``).
    ``__context__`` is not, because it records whatever merely happened to be in
    flight when an exception was raised; following it would let an unrelated
    refusal handled earlier in the same frame make an ordinary failure
    unabsorbable.
    """
    from ..module_policy import ModulePolicyError

    seen = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, ModulePolicyError):
            return True
        seen.add(id(error))
        error = getattr(error, 'original_error', None) or error.__cause__
    return False

class BrowserWaitTimeout(RuntimeError):
    """A wait whose predicate had not held by the deadline.

    A subclass of RuntimeError so every existing `except RuntimeError` around a
    wait keeps catching it, and a distinct type so a caller that cares can tell
    "it had not happened yet" from "we could not look". `browser.wait` is the
    caller that cares: by the outcome contract a timeout is INDETERMINATE, not
    FAILED.

    IT LIVES HERE, NOT BESIDE THE DRIVER THAT RAISES IT, and that is a
    packaging constraint rather than a taste. `core/browser/driver.py` imports
    playwright at module level, and playwright is an optional extra -- so a
    module that imported this type from there made playwright a hard
    requirement for importing the registry at all. Measured on the built wheel:

        core/modules/atomic/browser/wait.py -> core/browser/__init__.py
        -> core/browser/driver.py -> ModuleNotFoundError: No module named 'playwright'

    `import core.modules` failed outright in a base install, which is what the
    release pipeline's import test exists to catch. This module imports nothing
    beyond the standard library, so both sides can name the type.
    """
