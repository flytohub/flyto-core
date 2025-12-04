"""
Parallel Execution Patterns (Level 4)

Advanced patterns for parallel and concurrent execution.
"""
import asyncio
import logging
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, TypeVar

from .base import (
    BasePattern,
    PatternResult,
    PatternState,
    register_pattern,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


@register_pattern(
    pattern_id='pattern.parallel.map',
    version='1.0.0',
    category='parallel',
    tags=['parallel', 'map', 'concurrent', 'batch'],

    label='Parallel Map',
    label_key='patterns.parallel.map.label',
    description='Execute a function on multiple items in parallel with concurrency control',
    description_key='patterns.parallel.map.description',

    icon='GitBranch',
    color='#8B5CF6',

    config_schema={
        'max_concurrency': {
            'type': 'number',
            'label': 'Max Concurrency',
            'description': 'Maximum number of concurrent executions',
            'default': 5,
            'min': 1,
            'max': 100
        },
        'fail_fast': {
            'type': 'boolean',
            'label': 'Fail Fast',
            'description': 'Stop all executions on first failure',
            'default': False
        },
        'timeout_per_item_ms': {
            'type': 'number',
            'label': 'Timeout per Item (ms)',
            'description': 'Timeout for each item execution (0 = no timeout)',
            'default': 0
        },
        'preserve_order': {
            'type': 'boolean',
            'label': 'Preserve Order',
            'description': 'Return results in original order',
            'default': True
        }
    },

    examples=[
        {
            'name': 'Parallel API calls',
            'description': 'Fetch multiple URLs in parallel',
            'config': {
                'max_concurrency': 10,
                'fail_fast': False,
                'timeout_per_item_ms': 5000
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class ParallelMap(BasePattern):
    """
    Parallel Map Pattern

    Executes a function on multiple items in parallel with:
    - Concurrency limiting (semaphore)
    - Optional fail-fast behavior
    - Per-item timeout
    - Order preservation
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.max_concurrency = self.config.get('max_concurrency', 5)
        self.fail_fast = self.config.get('fail_fast', False)
        self.timeout_per_item_ms = self.config.get('timeout_per_item_ms', 0)
        self.preserve_order = self.config.get('preserve_order', True)

        self._semaphore: Optional[asyncio.Semaphore] = None
        self._cancel_flag = False

    async def _execute_item(
        self,
        index: int,
        item: Any,
        func: Callable,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute function on a single item with semaphore control"""
        async with self._semaphore:
            if self._cancel_flag:
                return {
                    'index': index,
                    'success': False,
                    'error': 'Cancelled due to fail_fast',
                    'item': item
                }

            try:
                start = time.time()

                # Apply timeout if configured
                if self.timeout_per_item_ms > 0:
                    timeout = self.timeout_per_item_ms / 1000.0
                    if asyncio.iscoroutinefunction(func):
                        result = await asyncio.wait_for(
                            func(item, **kwargs),
                            timeout=timeout
                        )
                    else:
                        result = await asyncio.wait_for(
                            asyncio.to_thread(func, item, **kwargs),
                            timeout=timeout
                        )
                else:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(item, **kwargs)
                    else:
                        result = func(item, **kwargs)

                elapsed_ms = (time.time() - start) * 1000

                return {
                    'index': index,
                    'success': True,
                    'value': result,
                    'elapsed_ms': elapsed_ms,
                    'item': item
                }

            except asyncio.TimeoutError:
                if self.fail_fast:
                    self._cancel_flag = True
                return {
                    'index': index,
                    'success': False,
                    'error': 'Timeout',
                    'item': item
                }

            except Exception as e:
                if self.fail_fast:
                    self._cancel_flag = True
                return {
                    'index': index,
                    'success': False,
                    'error': str(e),
                    'item': item
                }

    async def execute(
        self,
        func: Callable,
        items: Iterable[Any],
        **kwargs
    ) -> PatternResult:
        """
        Execute function on all items in parallel

        Args:
            func: Function to execute on each item
            items: Iterable of items to process
            **kwargs: Additional arguments for func

        Returns:
            PatternResult with list of results
        """
        start_time = time.time()
        self.state = PatternState.RUNNING
        self._cancel_flag = False
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

        items_list = list(items)

        # Create tasks for all items
        tasks = [
            self._execute_item(i, item, func, **kwargs)
            for i, item in enumerate(items_list)
        ]

        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        processed_results = []
        success_count = 0
        failure_count = 0

        for result in results:
            if isinstance(result, Exception):
                processed_results.append({
                    'success': False,
                    'error': str(result)
                })
                failure_count += 1
            else:
                processed_results.append(result)
                if result.get('success'):
                    success_count += 1
                else:
                    failure_count += 1

        # Sort by index if preserving order
        if self.preserve_order:
            processed_results.sort(key=lambda x: x.get('index', 0))

        elapsed_ms = (time.time() - start_time) * 1000

        # Determine overall success
        overall_success = failure_count == 0 or not self.fail_fast

        pattern_result = PatternResult(
            success=overall_success,
            value=processed_results,
            elapsed_ms=elapsed_ms,
            state=PatternState.SUCCESS if overall_success else PatternState.FAILED,
            metadata={
                'total_items': len(items_list),
                'success_count': success_count,
                'failure_count': failure_count,
                'max_concurrency': self.max_concurrency
            }
        )

        self._update_metrics(pattern_result)
        self.state = pattern_result.state
        return pattern_result


@register_pattern(
    pattern_id='pattern.parallel.race',
    version='1.0.0',
    category='parallel',
    tags=['parallel', 'race', 'first', 'concurrent'],

    label='Parallel Race',
    label_key='patterns.parallel.race.label',
    description='Execute multiple functions and return the first successful result',
    description_key='patterns.parallel.race.description',

    icon='Zap',
    color='#EF4444',

    config_schema={
        'timeout_ms': {
            'type': 'number',
            'label': 'Timeout (ms)',
            'description': 'Maximum time to wait for first result',
            'default': 10000
        },
        'cancel_losers': {
            'type': 'boolean',
            'label': 'Cancel Losers',
            'description': 'Cancel remaining tasks after winner',
            'default': True
        }
    },

    examples=[
        {
            'name': 'Fastest API response',
            'description': 'Query multiple APIs and use fastest response',
            'config': {
                'timeout_ms': 5000,
                'cancel_losers': True
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class ParallelRace(BasePattern):
    """
    Parallel Race Pattern

    Executes multiple functions concurrently and returns
    the result of the first one to complete successfully.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.timeout_ms = self.config.get('timeout_ms', 10000)
        self.cancel_losers = self.config.get('cancel_losers', True)

    async def execute(
        self,
        funcs: List[Callable],
        *args,
        **kwargs
    ) -> PatternResult:
        """
        Execute all functions and return first successful result

        Args:
            funcs: List of functions to race
            *args: Arguments for all functions
            **kwargs: Keyword arguments for all functions

        Returns:
            PatternResult with first successful result
        """
        start_time = time.time()
        self.state = PatternState.RUNNING

        async def execute_func(index: int, func: Callable):
            """Execute a single function"""
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return {'index': index, 'success': True, 'value': result}
            except Exception as e:
                return {'index': index, 'success': False, 'error': str(e)}

        # Create tasks
        tasks = [
            asyncio.create_task(execute_func(i, func))
            for i, func in enumerate(funcs)
        ]

        winner = None
        timeout = self.timeout_ms / 1000.0

        try:
            # Wait for first successful completion
            done, pending = await asyncio.wait(
                tasks,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Find successful result
            for task in done:
                result = task.result()
                if result.get('success'):
                    winner = result
                    break

            # If no success yet, wait for remaining
            while not winner and pending:
                done, pending = await asyncio.wait(
                    pending,
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    result = task.result()
                    if result.get('success'):
                        winner = result
                        break

            # Cancel remaining tasks if winner found
            if winner and self.cancel_losers:
                for task in pending:
                    task.cancel()

        except asyncio.TimeoutError:
            # Cancel all pending tasks
            for task in tasks:
                if not task.done():
                    task.cancel()

        elapsed_ms = (time.time() - start_time) * 1000

        if winner:
            pattern_result = PatternResult(
                success=True,
                value=winner.get('value'),
                elapsed_ms=elapsed_ms,
                state=PatternState.SUCCESS,
                metadata={
                    'winner_index': winner.get('index'),
                    'total_racers': len(funcs)
                }
            )
        else:
            pattern_result = PatternResult(
                success=False,
                error='No successful result within timeout',
                elapsed_ms=elapsed_ms,
                state=PatternState.TIMEOUT if elapsed_ms >= self.timeout_ms else PatternState.FAILED,
                metadata={'total_racers': len(funcs)}
            )

        self._update_metrics(pattern_result)
        self.state = pattern_result.state
        return pattern_result
