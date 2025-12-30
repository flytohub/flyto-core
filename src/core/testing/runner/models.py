"""
Test Runner Models

Data classes for the test runner system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from ..assertions import Assertion, AssertionResult, AssertionType


class TestStatus(str, Enum):
    """Test execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestCase:
    """
    A single test case definition.

    Attributes:
        name: Test name
        description: Test description
        workflow: Workflow definition or path
        inputs: Input parameters
        assertions: List of assertions to check
        timeout_ms: Maximum execution time
        skip: Whether to skip this test
        tags: Tags for filtering
    """
    name: str
    workflow: Union[Dict[str, Any], str]
    inputs: Dict[str, Any] = field(default_factory=dict)
    assertions: List[Assertion] = field(default_factory=list)
    description: str = ""
    timeout_ms: int = 30000
    skip: bool = False
    skip_reason: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    setup: Optional[Callable] = None
    teardown: Optional[Callable] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        """Create from dictionary"""
        assertions = []
        for assertion_data in data.get('assertions', []):
            assertions.append(Assertion(
                type=AssertionType(assertion_data.get('type', 'equals')),
                path=assertion_data.get('path'),
                expected=assertion_data.get('expected'),
                message=assertion_data.get('message'),
                options=assertion_data.get('options', {}),
            ))

        # Handle expect shorthand
        expect = data.get('expect', {})
        if expect:
            if 'status' in expect:
                assertions.append(Assertion(
                    type=AssertionType.STATUS,
                    expected=expect['status'],
                ))
            if 'final_context' in expect:
                assertions.append(Assertion(
                    type=AssertionType.CONTEXT_HAS,
                    expected=expect['final_context'],
                ))
            if 'completed_steps' in expect:
                for step_id in expect['completed_steps']:
                    assertions.append(Assertion(
                        type=AssertionType.STEP_COMPLETED,
                        expected=step_id,
                    ))
            if 'skipped_steps' in expect:
                for step_id in expect['skipped_steps']:
                    assertions.append(Assertion(
                        type=AssertionType.STEP_SKIPPED,
                        expected=step_id,
                    ))

        return cls(
            name=data.get('name', 'Unnamed Test'),
            description=data.get('description', ''),
            workflow=data.get('workflow', {}),
            inputs=data.get('inputs', {}),
            assertions=assertions,
            timeout_ms=data.get('timeout_ms', 30000),
            skip=data.get('skip', False),
            skip_reason=data.get('skip_reason'),
            tags=data.get('tags', []),
        )


@dataclass
class TestResult:
    """
    Result of a single test execution.

    Attributes:
        test_name: Name of the test
        status: Final status
        assertions: Assertion results
        duration_ms: Execution time
        error: Error message if failed
        execution_result: Raw execution result
    """
    test_name: str
    status: TestStatus
    assertions: List[AssertionResult] = field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None
    execution_result: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @property
    def passed(self) -> bool:
        """Check if test passed"""
        return self.status == TestStatus.PASSED

    @property
    def failed_assertions(self) -> List[AssertionResult]:
        """Get failed assertions"""
        return [a for a in self.assertions if not a.passed]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "test_name": self.test_name,
            "status": self.status.value,
            "passed": self.passed,
            "assertions": [a.to_dict() for a in self.assertions],
            "failed_assertions": [a.to_dict() for a in self.failed_assertions],
            "duration_ms": self.duration_ms,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


@dataclass
class TestReport:
    """
    Complete test run report.

    Attributes:
        name: Report name
        results: Individual test results
        started_at: Start time
        finished_at: End time
    """
    name: str
    results: List[TestResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @property
    def total(self) -> int:
        """Total test count"""
        return len(self.results)

    @property
    def passed(self) -> int:
        """Passed test count"""
        return len([r for r in self.results if r.status == TestStatus.PASSED])

    @property
    def failed(self) -> int:
        """Failed test count"""
        return len([r for r in self.results if r.status == TestStatus.FAILED])

    @property
    def skipped(self) -> int:
        """Skipped test count"""
        return len([r for r in self.results if r.status == TestStatus.SKIPPED])

    @property
    def errors(self) -> int:
        """Error test count"""
        return len([r for r in self.results if r.status == TestStatus.ERROR])

    @property
    def duration_ms(self) -> int:
        """Total duration"""
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return sum(r.duration_ms for r in self.results)

    @property
    def success_rate(self) -> float:
        """Success rate (0-1)"""
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    @property
    def all_passed(self) -> bool:
        """Check if all tests passed"""
        return self.failed == 0 and self.errors == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "success_rate": self.success_rate,
            "all_passed": self.all_passed,
            "results": [r.to_dict() for r in self.results],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    def to_summary(self) -> str:
        """Generate text summary"""
        lines = [
            f"Test Report: {self.name}",
            f"{'=' * 50}",
            f"Total: {self.total}",
            f"Passed: {self.passed}",
            f"Failed: {self.failed}",
            f"Skipped: {self.skipped}",
            f"Errors: {self.errors}",
            f"Duration: {self.duration_ms}ms",
            f"Success Rate: {self.success_rate:.1%}",
            "",
        ]

        for result in self.results:
            status_icon = {
                TestStatus.PASSED: "[PASS]",
                TestStatus.FAILED: "[FAIL]",
                TestStatus.SKIPPED: "[SKIP]",
                TestStatus.ERROR: "[ERR!]",
            }.get(result.status, "[????]")

            lines.append(f"{status_icon} {result.test_name} ({result.duration_ms}ms)")

            if result.failed_assertions:
                for assertion in result.failed_assertions:
                    lines.append(f"       - {assertion.message}")

            if result.error:
                lines.append(f"       Error: {result.error}")

        return "\n".join(lines)
