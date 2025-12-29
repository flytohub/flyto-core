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
