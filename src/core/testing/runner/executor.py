"""
Test Runner Executor

Executes workflow tests and generates reports.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yaml

from .models import TestCase, TestReport, TestResult, TestStatus

logger = logging.getLogger(__name__)


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
            from ...engine import WorkflowEngine
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

    def load_workflow(
        self,
        workflow_ref: Union[Dict[str, Any], str]
    ) -> Dict[str, Any]:
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
                if asyncio.iscoroutinefunction(test.setup):
                    await test.setup()
                else:
                    test.setup()

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
                    if asyncio.iscoroutinefunction(test.teardown):
                        await test.teardown()
                    else:
                        test.teardown()
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
