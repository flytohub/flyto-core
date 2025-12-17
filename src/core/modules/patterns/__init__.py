"""
Advanced Patterns (Level 4)

Enterprise-grade execution patterns for resilient, scalable workflows.
Designed for expert users and enterprise deployments.

Categories:
- retry: Retry patterns with various backoff strategies
- parallel: Parallel and concurrent execution patterns
- resilience: Fault tolerance patterns (circuit breaker)
- rate_limiting: Request rate limiting patterns
- batch: Batch processing and aggregation patterns

Usage:
    from core.modules.patterns import PatternRegistry, PatternExecutor

    # Using pattern directly
    from core.modules.patterns import RetryWithExponentialBackoff

    retry = RetryWithExponentialBackoff({
        'max_retries': 5,
        'initial_delay_ms': 100,
        'backoff_multiplier': 2.0
    })
    result = await retry.execute(my_async_function, arg1, arg2)

    # Using executor
    executor = PatternExecutor()
    result = await executor.execute(
        'pattern.retry.exponential_backoff',
        my_async_function,
        arg1, arg2,
        config={'max_retries': 3}
    )

    # Circuit breaker example
    from core.modules.patterns import CircuitBreaker

    circuit = CircuitBreaker({
        'failure_threshold': 5,
        'timeout_ms': 30000
    })

    result = await circuit.execute(call_external_api)
    if result.state == PatternState.CIRCUIT_OPEN:
        print("Service unavailable, circuit is open")
"""

from .base import (
    BasePattern,
    PatternRegistry,
    PatternExecutor,
    PatternResult,
    PatternState,
    register_pattern,
)

# Retry patterns
from .retry import (
    RetryWithExponentialBackoff,
    RetryWithLinearBackoff,
)

# Parallel patterns
from .parallel import (
    ParallelMap,
    ParallelRace,
)

# Circuit breaker
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)

# Rate limiter patterns
from .rate_limiter import (
    TokenBucketRateLimiter,
    SlidingWindowRateLimiter,
)

# Batch patterns
from .batch import (
    BatchProcessor,
    BatchAggregator,
)


__all__ = [
    # Base classes
    'BasePattern',
    'PatternRegistry',
    'PatternExecutor',
    'PatternResult',
    'PatternState',
    'register_pattern',

    # Retry patterns
    'RetryWithExponentialBackoff',
    'RetryWithLinearBackoff',

    # Parallel patterns
    'ParallelMap',
    'ParallelRace',

    # Circuit breaker
    'CircuitBreaker',
    'CircuitState',

    # Rate limiter patterns
    'TokenBucketRateLimiter',
    'SlidingWindowRateLimiter',

    # Batch patterns
    'BatchProcessor',
    'BatchAggregator',
]


def get_pattern_statistics():
    """Get statistics about registered patterns"""
    return PatternRegistry.get_statistics()


def list_patterns():
    """List all available patterns"""
    return PatternRegistry.list_all()
