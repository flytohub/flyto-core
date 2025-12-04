"""
Circuit Breaker Pattern (Level 4)

Fault tolerance pattern that prevents cascading failures.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

from .base import (
    BasePattern,
    PatternResult,
    PatternState,
    register_pattern,
)

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failure threshold reached, requests rejected
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0


@register_pattern(
    pattern_id='pattern.circuit_breaker',
    version='1.0.0',
    category='resilience',
    tags=['circuit-breaker', 'fault-tolerance', 'resilience', 'protection'],

    label='Circuit Breaker',
    label_key='patterns.circuit_breaker.label',
    description='Prevent cascading failures with circuit breaker pattern',
    description_key='patterns.circuit_breaker.description',

    icon='Shield',
    color='#EF4444',

    config_schema={
        'failure_threshold': {
            'type': 'number',
            'label': 'Failure Threshold',
            'description': 'Number of failures before opening circuit',
            'default': 5,
            'min': 1,
            'max': 100
        },
        'success_threshold': {
            'type': 'number',
            'label': 'Success Threshold',
            'description': 'Successes needed in half-open to close circuit',
            'default': 2,
            'min': 1,
            'max': 10
        },
        'timeout_ms': {
            'type': 'number',
            'label': 'Reset Timeout (ms)',
            'description': 'Time before attempting to close open circuit',
            'default': 30000,
            'min': 1000,
            'max': 300000
        },
        'half_open_max_calls': {
            'type': 'number',
            'label': 'Half-Open Max Calls',
            'description': 'Max concurrent calls in half-open state',
            'default': 1,
            'min': 1,
            'max': 10
        }
    },

    examples=[
        {
            'name': 'External API protection',
            'description': 'Protect against failing external API',
            'config': {
                'failure_threshold': 5,
                'success_threshold': 3,
                'timeout_ms': 60000
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class CircuitBreaker(BasePattern):
    """
    Circuit Breaker Pattern

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Failure threshold reached, requests immediately rejected
    - HALF_OPEN: Testing phase, limited requests allowed

    Transitions:
    - CLOSED -> OPEN: When failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After timeout_ms elapsed
    - HALF_OPEN -> CLOSED: When success_threshold successes
    - HALF_OPEN -> OPEN: On any failure
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        self.failure_threshold = self.config.get('failure_threshold', 5)
        self.success_threshold = self.config.get('success_threshold', 2)
        self.timeout_ms = self.config.get('timeout_ms', 30000)
        self.half_open_max_calls = self.config.get('half_open_max_calls', 1)

        self._circuit_state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._state_changed_at: float = time.time()
        self._half_open_calls: int = 0
        self._lock = asyncio.Lock()

    @property
    def circuit_state(self) -> CircuitState:
        """Get current circuit state, checking for timeout transition"""
        if self._circuit_state == CircuitState.OPEN:
            elapsed = (time.time() - self._state_changed_at) * 1000
            if elapsed >= self.timeout_ms:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._circuit_state

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state"""
        old_state = self._circuit_state
        self._circuit_state = new_state
        self._state_changed_at = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._stats.consecutive_successes = 0

        logger.info(f"Circuit breaker: {old_state.value} -> {new_state.value}")

    def _record_success(self):
        """Record a successful call"""
        self._stats.total_calls += 1
        self._stats.successful_calls += 1
        self._stats.consecutive_failures = 0
        self._stats.consecutive_successes += 1
        self._stats.last_success_time = time.time()

        if self._circuit_state == CircuitState.HALF_OPEN:
            if self._stats.consecutive_successes >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)

    def _record_failure(self):
        """Record a failed call"""
        self._stats.total_calls += 1
        self._stats.failed_calls += 1
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0
        self._stats.last_failure_time = time.time()

        if self._circuit_state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)
        elif self._circuit_state == CircuitState.CLOSED:
            if self._stats.consecutive_failures >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)

    def _should_allow_request(self) -> bool:
        """Check if request should be allowed"""
        state = self.circuit_state  # This checks timeout

        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.OPEN:
            return False
        else:  # HALF_OPEN
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> PatternResult:
        """
        Execute function with circuit breaker protection

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            PatternResult with execution result or circuit open error
        """
        start_time = time.time()

        async with self._lock:
            if not self._should_allow_request():
                self._stats.rejected_calls += 1
                elapsed_ms = (time.time() - start_time) * 1000

                pattern_result = PatternResult(
                    success=False,
                    error='Circuit breaker is OPEN',
                    elapsed_ms=elapsed_ms,
                    state=PatternState.CIRCUIT_OPEN,
                    metadata={
                        'circuit_state': self._circuit_state.value,
                        'consecutive_failures': self._stats.consecutive_failures,
                        'time_until_retry_ms': self.timeout_ms - (time.time() - self._state_changed_at) * 1000
                    }
                )
                self._update_metrics(pattern_result)
                return pattern_result

        try:
            self.state = PatternState.RUNNING

            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            async with self._lock:
                self._record_success()

            elapsed_ms = (time.time() - start_time) * 1000

            pattern_result = PatternResult(
                success=True,
                value=result,
                elapsed_ms=elapsed_ms,
                state=PatternState.SUCCESS,
                metadata={
                    'circuit_state': self._circuit_state.value,
                    'consecutive_successes': self._stats.consecutive_successes
                }
            )
            self._update_metrics(pattern_result)
            self.state = PatternState.SUCCESS
            return pattern_result

        except Exception as e:
            async with self._lock:
                self._record_failure()

            elapsed_ms = (time.time() - start_time) * 1000

            pattern_result = PatternResult(
                success=False,
                error=str(e),
                elapsed_ms=elapsed_ms,
                state=PatternState.FAILED,
                metadata={
                    'circuit_state': self._circuit_state.value,
                    'consecutive_failures': self._stats.consecutive_failures,
                    'exception_type': type(e).__name__
                }
            )
            self._update_metrics(pattern_result)
            self.state = PatternState.FAILED
            return pattern_result

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        return {
            'state': self._circuit_state.value,
            'total_calls': self._stats.total_calls,
            'successful_calls': self._stats.successful_calls,
            'failed_calls': self._stats.failed_calls,
            'rejected_calls': self._stats.rejected_calls,
            'consecutive_failures': self._stats.consecutive_failures,
            'consecutive_successes': self._stats.consecutive_successes
        }

    def reset(self):
        """Reset circuit breaker to closed state"""
        self._circuit_state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._state_changed_at = time.time()
        self._half_open_calls = 0
        logger.info("Circuit breaker reset to CLOSED")
