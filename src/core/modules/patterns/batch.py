"""
Batch Processing Patterns (Level 4)

Advanced patterns for batch processing with chunking and aggregation.
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
    pattern_id='pattern.batch.processor',
    version='1.0.0',
    category='batch',
    tags=['batch', 'chunk', 'bulk', 'processing'],

    label='Batch Processor',
    label_key='patterns.batch.processor.label',
    description='Process items in batches with configurable chunk size and concurrency',
    description_key='patterns.batch.processor.description',

    icon='Layers',
    color='#10B981',

    config_schema={
        'batch_size': {
            'type': 'number',
            'label': 'Batch Size',
            'description': 'Number of items per batch',
            'default': 10,
            'min': 1,
            'max': 1000
        },
        'max_concurrent_batches': {
            'type': 'number',
            'label': 'Max Concurrent Batches',
            'description': 'Maximum batches to process in parallel',
            'default': 3,
            'min': 1,
            'max': 20
        },
        'delay_between_batches_ms': {
            'type': 'number',
            'label': 'Delay Between Batches (ms)',
            'description': 'Delay between batch executions',
            'default': 0
        },
        'continue_on_error': {
            'type': 'boolean',
            'label': 'Continue on Error',
            'description': 'Continue processing if a batch fails',
            'default': True
        }
    },

    examples=[
        {
            'name': 'Database bulk insert',
            'description': 'Insert records in batches of 100',
            'config': {
                'batch_size': 100,
                'max_concurrent_batches': 5,
                'continue_on_error': True
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class BatchProcessor(BasePattern):
    """
    Batch Processor Pattern

    Features:
    - Chunks items into batches of configurable size
    - Parallel batch execution with concurrency control
    - Configurable delay between batches
    - Error handling per batch
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.batch_size = self.config.get('batch_size', 10)
        self.max_concurrent_batches = self.config.get('max_concurrent_batches', 3)
        self.delay_between_batches_ms = self.config.get('delay_between_batches_ms', 0)
        self.continue_on_error = self.config.get('continue_on_error', True)

    def _chunk_items(self, items: List[Any]) -> List[List[Any]]:
        """Split items into batches"""
        return [
            items[i:i + self.batch_size]
            for i in range(0, len(items), self.batch_size)
        ]

    async def _process_batch(
        self,
        batch_index: int,
        batch: List[Any],
        func: Callable,
        semaphore: asyncio.Semaphore,
        **kwargs
    ) -> Dict[str, Any]:
        """Process a single batch"""
        async with semaphore:
            try:
                start = time.time()

                if asyncio.iscoroutinefunction(func):
                    result = await func(batch, **kwargs)
                else:
                    result = func(batch, **kwargs)

                elapsed_ms = (time.time() - start) * 1000

                return {
                    'batch_index': batch_index,
                    'success': True,
                    'value': result,
                    'items_count': len(batch),
                    'elapsed_ms': elapsed_ms
                }

            except Exception as e:
                logger.error(f"Batch {batch_index} failed: {e}")
                return {
                    'batch_index': batch_index,
                    'success': False,
                    'error': str(e),
                    'items_count': len(batch)
                }

    async def execute(
        self,
        func: Callable,
        items: Iterable[Any],
        **kwargs
    ) -> PatternResult:
        """
        Process items in batches

        Args:
            func: Function to process each batch (receives list of items)
            items: Iterable of items to process
            **kwargs: Additional arguments for func

        Returns:
            PatternResult with batch processing results
        """
        start_time = time.time()
        self.state = PatternState.RUNNING

        items_list = list(items)
        batches = self._chunk_items(items_list)

        semaphore = asyncio.Semaphore(self.max_concurrent_batches)
        results = []
        failed_batches = []

        for i, batch in enumerate(batches):
            batch_result = await self._process_batch(
                i, batch, func, semaphore, **kwargs
            )
            results.append(batch_result)

            if not batch_result['success']:
                failed_batches.append(i)
                if not self.continue_on_error:
                    break

            # Delay between batches
            if self.delay_between_batches_ms > 0 and i < len(batches) - 1:
                await asyncio.sleep(self.delay_between_batches_ms / 1000.0)

        elapsed_ms = (time.time() - start_time) * 1000

        success = len(failed_batches) == 0
        if self.continue_on_error:
            success = len(failed_batches) < len(batches)

        pattern_result = PatternResult(
            success=success,
            value=results,
            elapsed_ms=elapsed_ms,
            state=PatternState.SUCCESS if success else PatternState.FAILED,
            metadata={
                'total_items': len(items_list),
                'total_batches': len(batches),
                'successful_batches': len(batches) - len(failed_batches),
                'failed_batches': failed_batches,
                'batch_size': self.batch_size
            }
        )

        self._update_metrics(pattern_result)
        self.state = pattern_result.state
        return pattern_result


@register_pattern(
    pattern_id='pattern.batch.aggregator',
    version='1.0.0',
    category='batch',
    tags=['batch', 'aggregate', 'collect', 'buffer'],

    label='Batch Aggregator',
    label_key='patterns.batch.aggregator.label',
    description='Aggregate items and process in batches when threshold reached',
    description_key='patterns.batch.aggregator.description',

    icon='Archive',
    color='#6366F1',

    config_schema={
        'batch_size': {
            'type': 'number',
            'label': 'Batch Size',
            'description': 'Number of items to trigger batch processing',
            'default': 10,
            'min': 1,
            'max': 1000
        },
        'max_wait_ms': {
            'type': 'number',
            'label': 'Max Wait (ms)',
            'description': 'Maximum time to wait before processing partial batch',
            'default': 5000
        },
        'flush_on_error': {
            'type': 'boolean',
            'label': 'Flush on Error',
            'description': 'Process remaining items on error',
            'default': True
        }
    },

    examples=[
        {
            'name': 'Log aggregation',
            'description': 'Aggregate logs and flush every 100 or 5 seconds',
            'config': {
                'batch_size': 100,
                'max_wait_ms': 5000
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class BatchAggregator(BasePattern):
    """
    Batch Aggregator Pattern

    Collects items and processes them when:
    - Batch size threshold is reached
    - Max wait time elapsed
    - Manual flush is called
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.batch_size = self.config.get('batch_size', 10)
        self.max_wait_ms = self.config.get('max_wait_ms', 5000)
        self.flush_on_error = self.config.get('flush_on_error', True)

        self._buffer: List[Any] = []
        self._last_flush = time.time()
        self._process_func: Optional[Callable] = None
        self._lock = asyncio.Lock()

    async def add(self, item: Any) -> Optional[PatternResult]:
        """
        Add item to buffer, process if threshold reached

        Args:
            item: Item to add

        Returns:
            PatternResult if batch was processed, None otherwise
        """
        async with self._lock:
            self._buffer.append(item)

            # Check if we should flush
            should_flush = (
                len(self._buffer) >= self.batch_size or
                self._time_since_last_flush() >= self.max_wait_ms
            )

            if should_flush and self._process_func:
                return await self._flush_internal()

        return None

    def _time_since_last_flush(self) -> float:
        """Get time since last flush in ms"""
        return (time.time() - self._last_flush) * 1000

    async def _flush_internal(self) -> PatternResult:
        """Internal flush without lock"""
        if not self._buffer:
            return PatternResult(
                success=True,
                value=[],
                metadata={'items_processed': 0}
            )

        items = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = time.time()

        start_time = time.time()

        try:
            if asyncio.iscoroutinefunction(self._process_func):
                result = await self._process_func(items)
            else:
                result = self._process_func(items)

            elapsed_ms = (time.time() - start_time) * 1000

            return PatternResult(
                success=True,
                value=result,
                elapsed_ms=elapsed_ms,
                state=PatternState.SUCCESS,
                metadata={'items_processed': len(items)}
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            return PatternResult(
                success=False,
                error=str(e),
                elapsed_ms=elapsed_ms,
                state=PatternState.FAILED,
                metadata={'items_processed': 0, 'items_lost': len(items)}
            )

    async def flush(self) -> PatternResult:
        """Manually flush buffer"""
        async with self._lock:
            return await self._flush_internal()

    async def execute(
        self,
        func: Callable,
        items: Optional[Iterable[Any]] = None,
        **kwargs
    ) -> PatternResult:
        """
        Set process function and optionally add items

        Args:
            func: Function to process batches
            items: Optional initial items to add
            **kwargs: Additional arguments (unused)

        Returns:
            PatternResult after processing all items
        """
        self._process_func = func
        self.state = PatternState.RUNNING

        results = []

        if items:
            for item in items:
                result = await self.add(item)
                if result:
                    results.append(result)

        # Final flush
        final_result = await self.flush()
        results.append(final_result)

        # Aggregate results
        total_processed = sum(
            r.metadata.get('items_processed', 0)
            for r in results
        )
        all_success = all(r.success for r in results)

        pattern_result = PatternResult(
            success=all_success,
            value=[r.value for r in results if r.success],
            state=PatternState.SUCCESS if all_success else PatternState.FAILED,
            metadata={
                'total_items_processed': total_processed,
                'batch_count': len(results)
            }
        )

        self._update_metrics(pattern_result)
        self.state = pattern_result.state
        return pattern_result
