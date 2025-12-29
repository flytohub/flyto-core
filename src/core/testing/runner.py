"""
Workflow Test Runner

Executes test cases against workflows and validates outcomes.
Supports YAML-defined test cases for regression testing.

Design principles:
- Declarative: Tests defined in YAML/JSON
- Isolated: Each test runs in clean environment
- Detailed: Comprehensive failure reporting
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yaml

from .assertions import Assertion, AssertionResult, AssertionType

logger = logging.getLogger(__name__)


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


class WorkflowTestRunner:
    """
    Executes workflow tests and generates reports.

    Usage:
        runner = WorkflowTestRunner()

        # Load tests from file
        runner.load_tests("tests/workflow_tests.yaml")

        # Run all tests
        report = await runner.run_all()

        # Run specific tests
        report = await runner.run_tests(["test_1", "test_2"])

        # Run by tags
        report = await runner.run_by_tags(["regression"])
    """

    def __init__(
        self,
        workflow_executor: Optional[Callable] = None,
        parallel: bool = False,
        max_parallel: int = 5,
    ):
        """
        Initialize test runner.

        Args:
            workflow_executor: Async function to execute workflows
                Signature: async def executor(workflow, params) -> result
            parallel: Whether to run tests in parallel
            max_parallel: Maximum parallel tests
        """
        self._tests: Dict[str, TestCase] = {}
        self._executor = workflow_executor or self._default_executor
        self._parallel = parallel
        self._max_parallel = max_parallel

    async def _default_executor(
        self,
        workflow: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Default workflow executor"""
        try:
            from ..engine import WorkflowEngine
        except ImportError:
            from src.core.engine import WorkflowEngine

        engine = WorkflowEngine(workflow=workflow, params=params)
        result = await engine.execute()

        return {
            "ok": result.get('ok', True),
            "status": "success" if result.get('ok', True) else "error",
            "context": engine.context,
            "execution_log": engine.execution_log,
            "outputs": result.get('outputs', {}),
            "error": result.get('error'),
        }

    def add_test(self, test: TestCase) -> None:
        """Add a test case"""
        self._tests[test.name] = test

    def load_tests(self, path: Union[str, Path]) -> int:
        """
        Load tests from YAML/JSON file.

        Args:
            path: Path to test file

        Returns:
            Number of tests loaded
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Test file not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix in ('.yaml', '.yml'):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        # Handle single test or list of tests
        tests = data.get('tests', [data]) if isinstance(data, dict) else data

        count = 0
        for test_data in tests:
            test = TestCase.from_dict(test_data)
            self.add_test(test)
            count += 1

        logger.info(f"Loaded {count} tests from {path}")
        return count

    def load_workflow(self, workflow_ref: Union[Dict[str, Any], str]) -> Dict[str, Any]:
        """
        Load workflow from reference.

        Args:
            workflow_ref: Workflow dict or path

        Returns:
            Workflow definition
        """
        if isinstance(workflow_ref, dict):
            return workflow_ref

        path = Path(workflow_ref)
        if not path.exists():
            raise FileNotFoundError(f"Workflow not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix in ('.yaml', '.yml'):
                return yaml.safe_load(f)
            else:
                return json.load(f)

    async def run_test(self, test: TestCase) -> TestResult:
        """
        Run a single test.

        Args:
            test: Test case to run

        Returns:
            Test result
        """
        started_at = datetime.now()

        # Handle skipped tests
        if test.skip:
            return TestResult(
                test_name=test.name,
                status=TestStatus.SKIPPED,
                error=test.skip_reason or "Test skipped",
                started_at=started_at,
                finished_at=datetime.now(),
            )

        try:
            # Run setup
            if test.setup:
                await test.setup() if asyncio.iscoroutinefunction(test.setup) else test.setup()

            # Load workflow
            workflow = self.load_workflow(test.workflow)

            # Execute workflow with timeout
            start_time = time.time()
            try:
                result = await asyncio.wait_for(
                    self._executor(workflow, test.inputs),
                    timeout=test.timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                return TestResult(
                    test_name=test.name,
                    status=TestStatus.ERROR,
                    error=f"Test timed out after {test.timeout_ms}ms",
                    duration_ms=test.timeout_ms,
                    started_at=started_at,
                    finished_at=datetime.now(),
                )

            duration_ms = int((time.time() - start_time) * 1000)

            # Run assertions
            assertion_results = []
            for assertion in test.assertions:
                assertion_result = assertion.check(result)
                assertion_results.append(assertion_result)

            # Determine overall status
            all_passed = all(a.passed for a in assertion_results)
            status = TestStatus.PASSED if all_passed else TestStatus.FAILED

            return TestResult(
                test_name=test.name,
                status=status,
                assertions=assertion_results,
                duration_ms=duration_ms,
                execution_result=result,
                started_at=started_at,
                finished_at=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Test {test.name} error: {e}")
            return TestResult(
                test_name=test.name,
                status=TestStatus.ERROR,
                error=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )

        finally:
            # Run teardown
            if test.teardown:
                try:
                    await test.teardown() if asyncio.iscoroutinefunction(test.teardown) else test.teardown()
                except Exception as e:
                    logger.warning(f"Teardown failed for {test.name}: {e}")

    async def run_all(self, report_name: Optional[str] = None) -> TestReport:
        """
        Run all loaded tests.

        Args:
            report_name: Optional report name

        Returns:
            Test report
        """
        return await self.run_tests(
            list(self._tests.keys()),
            report_name=report_name or "All Tests",
        )

    async def run_tests(
        self,
        test_names: List[str],
        report_name: Optional[str] = None,
    ) -> TestReport:
        """
        Run specific tests by name.

        Args:
            test_names: List of test names
            report_name: Optional report name

        Returns:
            Test report
        """
        report = TestReport(
            name=report_name or f"Test Run {uuid.uuid4().hex[:8]}",
            started_at=datetime.now(),
        )

        tests = [self._tests[name] for name in test_names if name in self._tests]

        if self._parallel:
            # Run tests in parallel
            semaphore = asyncio.Semaphore(self._max_parallel)

            async def run_with_semaphore(test: TestCase) -> TestResult:
                async with semaphore:
                    return await self.run_test(test)

            results = await asyncio.gather(
                *[run_with_semaphore(test) for test in tests],
                return_exceptions=True,
            )

            for result in results:
                if isinstance(result, Exception):
                    report.results.append(TestResult(
                        test_name="Unknown",
                        status=TestStatus.ERROR,
                        error=str(result),
                    ))
                else:
                    report.results.append(result)
        else:
            # Run tests sequentially
            for test in tests:
                result = await self.run_test(test)
                report.results.append(result)

        report.finished_at = datetime.now()
        return report

    async def run_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        report_name: Optional[str] = None,
    ) -> TestReport:
        """
        Run tests matching tags.

        Args:
            tags: Tags to match
            match_all: If True, test must have all tags
            report_name: Optional report name

        Returns:
            Test report
        """
        matching = []
        for name, test in self._tests.items():
            if match_all:
                if all(tag in test.tags for tag in tags):
                    matching.append(name)
            else:
                if any(tag in test.tags for tag in tags):
                    matching.append(name)

        return await self.run_tests(
            matching,
            report_name=report_name or f"Tests with tags: {', '.join(tags)}",
        )

    def get_test_names(self) -> List[str]:
        """Get all test names"""
        return list(self._tests.keys())

    def get_tests_by_tag(self, tag: str) -> List[str]:
        """Get test names with specific tag"""
        return [
            name for name, test in self._tests.items()
            if tag in test.tags
        ]


# =============================================================================
# Factory Functions
# =============================================================================

def create_test_runner(
    workflow_executor: Optional[Callable] = None,
    parallel: bool = False,
) -> WorkflowTestRunner:
    """
    Create a test runner.

    Args:
        workflow_executor: Optional custom executor
        parallel: Whether to run tests in parallel

    Returns:
        Configured WorkflowTestRunner
    """
    return WorkflowTestRunner(
        workflow_executor=workflow_executor,
        parallel=parallel,
    )
