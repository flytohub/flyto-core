"""
Retry Patterns (Level 4)

Advanced retry patterns with exponential backoff, jitter, and custom strategies.
"""
import asyncio
import logging
import random
import time
from typing import Any, Callable, Dict, List, Optional, Set, Type

from .base import (
    BasePattern,
    PatternResult,
    PatternState,
    register_pattern,
)

logger = logging.getLogger(__name__)


@register_pattern(
    pattern_id='pattern.retry.exponential_backoff',
    version='1.0.0',
    category='retry',
    tags=['retry', 'backoff', 'resilience', 'fault-tolerance'],

    label='Retry with Exponential Backoff',
    label_key='patterns.retry.exponential_backoff.label',
    description='Retry failed operations with exponential backoff and optional jitter',
    description_key='patterns.retry.exponential_backoff.description',

    icon='RefreshCw',
    color='#F59E0B',

    config_schema={
        'max_retries': {
            'type': 'number',
            'label': 'Max Retries',
            'description': 'Maximum number of retry attempts',
            'default': 3,
            'min': 1,
            'max': 10
        },
        'initial_delay_ms': {
            'type': 'number',
            'label': 'Initial Delay (ms)',
            'description': 'Initial delay before first retry',
            'default': 100,
            'min': 10,
            'max': 10000
        },
        'max_delay_ms': {
            'type': 'number',
            'label': 'Max Delay (ms)',
            'description': 'Maximum delay between retries',
            'default': 10000,
            'min': 100,
            'max': 60000
        },
        'backoff_multiplier': {
            'type': 'number',
            'label': 'Backoff Multiplier',
            'description': 'Multiplier for exponential backoff',
            'default': 2.0,
            'min': 1.1,
            'max': 5.0
        },
        'jitter': {
            'type': 'boolean',
            'label': 'Add Jitter',
            'description': 'Add random jitter to prevent thundering herd',
            'default': True
        },
        'retryable_exceptions': {
            'type': 'array',
            'label': 'Retryable Exceptions',
            'description': 'Exception types that should trigger retry (empty = all)',
            'default': []
        }
    },

    examples=[
        {
            'name': 'API call with retry',
            'description': 'Retry API calls with exponential backoff',
            'config': {
                'max_retries': 5,
                'initial_delay_ms': 200,
                'backoff_multiplier': 2.0,
                'jitter': True
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class RetryWithExponentialBackoff(BasePattern):
    """
    Retry with Exponential Backoff Pattern

    Retries failed operations with exponentially increasing delays.
    Supports jitter to prevent thundering herd problem.

    Formula: delay = min(initial_delay * (multiplier ^ attempt), max_delay)
    With jitter: delay = delay * random(0.5, 1.5)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.max_retries = self.config.get('max_retries', 3)
        self.initial_delay_ms = self.config.get('initial_delay_ms', 100)
        self.max_delay_ms = self.config.get('max_delay_ms', 10000)
        self.backoff_multiplier = self.config.get('backoff_multiplier', 2.0)
        self.jitter = self.config.get('jitter', True)
        self.retryable_exceptions: Set[Type[Exception]] = set()

        # Parse retryable exceptions
        exception_names = self.config.get('retryable_exceptions', [])
        for name in exception_names:
            if hasattr(__builtins__, name):
                self.retryable_exceptions.add(getattr(__builtins__, name))

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        delay_ms = self.initial_delay_ms * (self.backoff_multiplier ** attempt)
        delay_ms = min(delay_ms, self.max_delay_ms)

        if self.jitter:
            # Add jitter: multiply by random factor between 0.5 and 1.5
            jitter_factor = 0.5 + random.random()
            delay_ms *= jitter_factor

        return delay_ms / 1000.0  # Convert to seconds

    def _should_retry(self, exception: Exception) -> bool:
        """Check if exception should trigger retry"""
        if not self.retryable_exceptions:
            return True  # Retry all exceptions

        return any(
            isinstance(exception, exc_type)
            for exc_type in self.retryable_exceptions
        )

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> PatternResult:
        """Execute function with retry logic"""
        start_time = time.time()
        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                self.state = PatternState.RUNNING

                # Execute the function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Success
                elapsed_ms = (time.time() - start_time) * 1000
                pattern_result = PatternResult(
                    success=True,
                    value=result,
                    attempts=attempt + 1,
                    elapsed_ms=elapsed_ms,
                    state=PatternState.SUCCESS,
                    metadata={'final_attempt': attempt + 1}
                )
                self._update_metrics(pattern_result)
                self.state = PatternState.SUCCESS
                return pattern_result

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries + 1} failed: {e}"
                )

                # Check if we should retry
                if attempt < self.max_retries and self._should_retry(e):
                    delay = self._calculate_delay(attempt)
                    logger.info(f"Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                else:
                    break

        # All retries exhausted
        elapsed_ms = (time.time() - start_time) * 1000
        pattern_result = PatternResult(
            success=False,
            error=str(last_exception),
            attempts=self.max_retries + 1,
            elapsed_ms=elapsed_ms,
            state=PatternState.FAILED,
            metadata={
                'exception_type': type(last_exception).__name__,
                'all_attempts_failed': True
            }
        )
        self._update_metrics(pattern_result)
        self.state = PatternState.FAILED
        return pattern_result


@register_pattern(
    pattern_id='pattern.retry.linear_backoff',
    version='1.0.0',
    category='retry',
    tags=['retry', 'backoff', 'linear', 'resilience'],

    label='Retry with Linear Backoff',
    label_key='patterns.retry.linear_backoff.label',
    description='Retry failed operations with linear delay increase',
    description_key='patterns.retry.linear_backoff.description',

    icon='RefreshCw',
    color='#3B82F6',

    config_schema={
        'max_retries': {
            'type': 'number',
            'label': 'Max Retries',
            'default': 3
        },
        'delay_ms': {
            'type': 'number',
            'label': 'Delay (ms)',
            'description': 'Fixed delay between retries',
            'default': 1000
        },
        'increment_ms': {
            'type': 'number',
            'label': 'Increment (ms)',
            'description': 'Delay increment per retry',
            'default': 500
        }
    },

    examples=[
        {
            'name': 'Database reconnect',
            'config': {
                'max_retries': 5,
                'delay_ms': 1000,
                'increment_ms': 1000
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class RetryWithLinearBackoff(BasePattern):
    """
    Retry with Linear Backoff Pattern

    Retries failed operations with linearly increasing delays.
    Formula: delay = base_delay + (increment * attempt)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.max_retries = self.config.get('max_retries', 3)
        self.delay_ms = self.config.get('delay_ms', 1000)
        self.increment_ms = self.config.get('increment_ms', 500)

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        delay_ms = self.delay_ms + (self.increment_ms * attempt)
        return delay_ms / 1000.0

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> PatternResult:
        """Execute function with linear retry logic"""
        start_time = time.time()
        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                self.state = PatternState.RUNNING

                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                elapsed_ms = (time.time() - start_time) * 1000
                pattern_result = PatternResult(
                    success=True,
                    value=result,
                    attempts=attempt + 1,
                    elapsed_ms=elapsed_ms,
                    state=PatternState.SUCCESS
                )
                self._update_metrics(pattern_result)
                return pattern_result

            except Exception as e:
                last_exception = e

                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    await asyncio.sleep(delay)

        elapsed_ms = (time.time() - start_time) * 1000
        pattern_result = PatternResult(
            success=False,
            error=str(last_exception),
            attempts=self.max_retries + 1,
            elapsed_ms=elapsed_ms,
            state=PatternState.FAILED
        )
        self._update_metrics(pattern_result)
        return pattern_result
