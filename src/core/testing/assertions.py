"""
Test Assertions

Provides assertion functions for workflow testing.
All assertions return AssertionResult for detailed reporting.

Design principles:
- Non-throwing: Returns results instead of raising exceptions
- Detailed: Includes expected vs actual values
- Composable: Assertions can be combined
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Pattern, Union


class AssertionType(str, Enum):
    """Types of assertions"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    MATCHES = "matches"
    STATUS = "status"
    STEP_COMPLETED = "step_completed"
    STEP_SKIPPED = "step_skipped"
    OUTPUT_MATCHES = "output_matches"
    CONTEXT_HAS = "context_has"
    CUSTOM = "custom"


@dataclass
class AssertionResult:
    """
    Result of an assertion check.

    Attributes:
        passed: Whether assertion passed
        assertion_type: Type of assertion
        message: Human-readable result message
        expected: Expected value
        actual: Actual value
        path: JSON path to the checked value
        details: Additional details
    """
    passed: bool
    assertion_type: AssertionType
    message: str
    expected: Any = None
    actual: Any = None
    path: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "passed": self.passed,
            "assertion_type": self.assertion_type.value,
            "message": self.message,
            "expected": self._serialize(self.expected),
            "actual": self._serialize(self.actual),
            "path": self.path,
            "details": self.details,
        }

    def _serialize(self, value: Any) -> Any:
        """Serialize value for JSON"""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        if isinstance(value, (list, tuple)):
            return [self._serialize(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        return str(value)


@dataclass
class Assertion:
    """
    An assertion to check against workflow execution results.

    Usage:
        assertion = Assertion(
            type=AssertionType.EQUALS,
            path="result.status",
            expected="success",
        )
        result = assertion.check(execution_result)
    """
    type: AssertionType
    expected: Any = None
    path: Optional[str] = None
    message: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)

    def check(self, data: Dict[str, Any]) -> AssertionResult:
        """
        Check assertion against data.

        Args:
            data: Execution result data

        Returns:
            AssertionResult with pass/fail status
        """
        actual = self._get_value(data, self.path) if self.path else data

        if self.type == AssertionType.EQUALS:
            return self._check_equals(actual)
        elif self.type == AssertionType.NOT_EQUALS:
            return self._check_not_equals(actual)
        elif self.type == AssertionType.CONTAINS:
            return self._check_contains(actual)
        elif self.type == AssertionType.NOT_CONTAINS:
            return self._check_not_contains(actual)
        elif self.type == AssertionType.MATCHES:
            return self._check_matches(actual)
        elif self.type == AssertionType.STATUS:
            return self._check_status(data)
        elif self.type == AssertionType.STEP_COMPLETED:
            return self._check_step_completed(data)
        elif self.type == AssertionType.STEP_SKIPPED:
            return self._check_step_skipped(data)
        elif self.type == AssertionType.OUTPUT_MATCHES:
            return self._check_output_matches(data)
        elif self.type == AssertionType.CONTEXT_HAS:
            return self._check_context_has(data)
        else:
            return AssertionResult(
                passed=False,
                assertion_type=self.type,
                message=f"Unknown assertion type: {self.type}",
            )

    def _get_value(self, data: Any, path: str) -> Any:
        """Get value at path (dot notation)"""
        if not path:
            return data

        parts = path.split('.')
        current = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    index = int(part)
                    current = current[index]
                except (ValueError, IndexError):
                    return None
            else:
                return None

        return current

    def _check_equals(self, actual: Any) -> AssertionResult:
        """Check equality"""
        passed = actual == self.expected
        return AssertionResult(
            passed=passed,
            assertion_type=AssertionType.EQUALS,
            message=self.message or (
                f"Expected {self.path} to equal {self.expected}"
                if self.path else f"Expected value to equal {self.expected}"
            ),
            expected=self.expected,
            actual=actual,
            path=self.path,
        )

    def _check_not_equals(self, actual: Any) -> AssertionResult:
        """Check inequality"""
        passed = actual != self.expected
        return AssertionResult(
            passed=passed,
            assertion_type=AssertionType.NOT_EQUALS,
            message=self.message or f"Expected {self.path} to not equal {self.expected}",
            expected=f"not {self.expected}",
            actual=actual,
            path=self.path,
        )

    def _check_contains(self, actual: Any) -> AssertionResult:
        """Check containment"""
        if isinstance(actual, str):
            passed = self.expected in actual
        elif isinstance(actual, (list, tuple)):
            passed = self.expected in actual
        elif isinstance(actual, dict):
            passed = self.expected in actual
        else:
            passed = False

        return AssertionResult(
            passed=passed,
            assertion_type=AssertionType.CONTAINS,
            message=self.message or f"Expected {self.path} to contain {self.expected}",
            expected=self.expected,
            actual=actual,
            path=self.path,
        )

    def _check_not_contains(self, actual: Any) -> AssertionResult:
        """Check non-containment"""
        result = self._check_contains(actual)
        result.passed = not result.passed
        result.assertion_type = AssertionType.NOT_CONTAINS
        result.message = self.message or f"Expected {self.path} to not contain {self.expected}"
        return result

    def _check_matches(self, actual: Any) -> AssertionResult:
        """Check regex match"""
        if not isinstance(actual, str):
            return AssertionResult(
                passed=False,
                assertion_type=AssertionType.MATCHES,
                message=f"Expected string for regex match, got {type(actual).__name__}",
                expected=self.expected,
                actual=actual,
                path=self.path,
            )

        pattern = self.expected if isinstance(self.expected, Pattern) else re.compile(self.expected)
        passed = bool(pattern.search(actual))

        return AssertionResult(
            passed=passed,
            assertion_type=AssertionType.MATCHES,
            message=self.message or f"Expected {self.path} to match pattern {self.expected}",
            expected=str(self.expected),
            actual=actual,
            path=self.path,
        )

    def _check_status(self, data: Dict[str, Any]) -> AssertionResult:
        """Check workflow status"""
        actual_status = data.get('status') or data.get('__event__') or data.get('ok')
        expected_status = self.expected

        # Normalize status values
        if actual_status is True:
            actual_status = 'success'
        elif actual_status is False:
            actual_status = 'error'

        passed = actual_status == expected_status

        return AssertionResult(
            passed=passed,
            assertion_type=AssertionType.STATUS,
            message=self.message or f"Expected status to be {expected_status}",
            expected=expected_status,
            actual=actual_status,
            path="status",
        )

    def _check_step_completed(self, data: Dict[str, Any]) -> AssertionResult:
        """Check that a step was completed"""
        step_id = self.expected
        completed_steps = data.get('completed_steps', [])
        execution_log = data.get('execution_log', [])

        # Check in completed_steps list
        passed = step_id in completed_steps

        # Also check execution log
        if not passed:
            for log in execution_log:
                if log.get('step_id') == step_id and log.get('status') == 'success':
                    passed = True
                    break

        return AssertionResult(
            passed=passed,
            assertion_type=AssertionType.STEP_COMPLETED,
            message=self.message or f"Expected step {step_id} to be completed",
            expected=step_id,
            actual=completed_steps,
            path="completed_steps",
        )

    def _check_step_skipped(self, data: Dict[str, Any]) -> AssertionResult:
        """Check that a step was skipped"""
        step_id = self.expected
        skipped_steps = data.get('skipped_steps', [])
        execution_log = data.get('execution_log', [])

        passed = step_id in skipped_steps

        # Also check execution log
        if not passed:
            for log in execution_log:
                if log.get('step_id') == step_id and log.get('status') == 'skipped':
                    passed = True
                    break

        return AssertionResult(
            passed=passed,
            assertion_type=AssertionType.STEP_SKIPPED,
            message=self.message or f"Expected step {step_id} to be skipped",
            expected=step_id,
            actual=skipped_steps,
            path="skipped_steps",
        )

    def _check_output_matches(self, data: Dict[str, Any]) -> AssertionResult:
        """Check that outputs match expected pattern"""
        outputs = data.get('outputs', {})
        expected_outputs = self.expected

        if not isinstance(expected_outputs, dict):
            return AssertionResult(
                passed=False,
                assertion_type=AssertionType.OUTPUT_MATCHES,
                message="Expected outputs must be a dictionary",
                expected=expected_outputs,
                actual=outputs,
            )

        mismatches = []
        for key, expected_value in expected_outputs.items():
            actual_value = outputs.get(key)
            if actual_value != expected_value:
                mismatches.append({
                    "key": key,
                    "expected": expected_value,
                    "actual": actual_value,
                })

        passed = len(mismatches) == 0

        return AssertionResult(
            passed=passed,
            assertion_type=AssertionType.OUTPUT_MATCHES,
            message=self.message or "Expected outputs to match",
            expected=expected_outputs,
            actual=outputs,
            path="outputs",
            details={"mismatches": mismatches} if mismatches else {},
        )

    def _check_context_has(self, data: Dict[str, Any]) -> AssertionResult:
        """Check that context has expected keys/values"""
        context = data.get('context', {}) or data.get('variables', {})
        expected = self.expected

        if isinstance(expected, str):
            # Just check key exists
            passed = expected in context
            return AssertionResult(
                passed=passed,
                assertion_type=AssertionType.CONTEXT_HAS,
                message=self.message or f"Expected context to have key {expected}",
                expected=expected,
                actual=list(context.keys()),
                path="context",
            )

        if isinstance(expected, dict):
            # Check key-value pairs
            mismatches = []
            for key, value in expected.items():
                if key not in context:
                    mismatches.append({"key": key, "issue": "missing"})
                elif context[key] != value:
                    mismatches.append({
                        "key": key,
                        "expected": value,
                        "actual": context[key],
                    })

            passed = len(mismatches) == 0
            return AssertionResult(
                passed=passed,
                assertion_type=AssertionType.CONTEXT_HAS,
                message=self.message or "Expected context to have values",
                expected=expected,
                actual=context,
                path="context",
                details={"mismatches": mismatches} if mismatches else {},
            )

        return AssertionResult(
            passed=False,
            assertion_type=AssertionType.CONTEXT_HAS,
            message="Expected must be string or dict",
            expected=expected,
            actual=context,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def assert_equals(
    path: str,
    expected: Any,
    message: Optional[str] = None,
) -> Assertion:
    """Create equality assertion"""
    return Assertion(
        type=AssertionType.EQUALS,
        path=path,
        expected=expected,
        message=message,
    )


def assert_contains(
    path: str,
    expected: Any,
    message: Optional[str] = None,
) -> Assertion:
    """Create containment assertion"""
    return Assertion(
        type=AssertionType.CONTAINS,
        path=path,
        expected=expected,
        message=message,
    )


def assert_status(
    expected: str,
    message: Optional[str] = None,
) -> Assertion:
    """Create status assertion"""
    return Assertion(
        type=AssertionType.STATUS,
        expected=expected,
        message=message,
    )


def assert_step_completed(
    step_id: str,
    message: Optional[str] = None,
) -> Assertion:
    """Create step completed assertion"""
    return Assertion(
        type=AssertionType.STEP_COMPLETED,
        expected=step_id,
        message=message,
    )


def assert_step_skipped(
    step_id: str,
    message: Optional[str] = None,
) -> Assertion:
    """Create step skipped assertion"""
    return Assertion(
        type=AssertionType.STEP_SKIPPED,
        expected=step_id,
        message=message,
    )


def assert_output_matches(
    expected: Dict[str, Any],
    message: Optional[str] = None,
) -> Assertion:
    """Create output matching assertion"""
    return Assertion(
        type=AssertionType.OUTPUT_MATCHES,
        expected=expected,
        message=message,
    )


def assert_context_has(
    expected: Union[str, Dict[str, Any]],
    message: Optional[str] = None,
) -> Assertion:
    """Create context assertion"""
    return Assertion(
        type=AssertionType.CONTEXT_HAS,
        expected=expected,
        message=message,
    )


def assert_matches(
    path: str,
    pattern: str,
    message: Optional[str] = None,
) -> Assertion:
    """Create regex match assertion"""
    return Assertion(
        type=AssertionType.MATCHES,
        path=path,
        expected=pattern,
        message=message,
    )
