"""
Advanced Patterns Base Class and Registry (Level 4)

Enterprise-grade patterns for resilient, scalable workflow execution.
These patterns provide advanced capabilities for expert users and enterprise deployments.

Patterns include:
- RetryWithBackoff: Exponential backoff retry logic
- ParallelMap: Parallel execution of items
- CircuitBreaker: Fault tolerance with circuit breaker
- RateLimiter: Request rate limiting
- BatchProcessor: Batch processing with concurrency control
- Timeout: Configurable timeout wrapper
- Fallback: Fallback execution on failure
- Cache: Result caching

Example:
    @register_pattern(
        pattern_id='pattern.retry_backoff',
        label='Retry with Backoff',
        max_retries=5,
        initial_delay_ms=100,
        max_delay_ms=10000,
        backoff_multiplier=2.0
    )
    class RetryWithBackoff(BasePattern):
        async def execute(self, func, *args, **kwargs):
            # Implementation
            pass
"""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

from ...constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    EXPONENTIAL_BACKOFF_BASE,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class PatternState(Enum):
    """Pattern execution states"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class PatternResult(Generic[T]):
    """Result of pattern execution"""
    success: bool
    value: Optional[T] = None
    error: Optional[str] = None
    attempts: int = 1
    elapsed_ms: float = 0.0
    state: PatternState = PatternState.SUCCESS
    metadata: Dict[str, Any] = field(default_factory=dict)


class PatternRegistry:
    """
    Registry for Advanced Patterns (Level 4)

    Manages enterprise-grade execution patterns for resilient workflows.
    """

    _instance = None
    _patterns: Dict[str, Type['BasePattern']] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        pattern_id: str,
        pattern_class: Type['BasePattern'],
        metadata: Dict[str, Any]
    ):
        """Register a pattern"""
        cls._patterns[pattern_id] = pattern_class
        cls._metadata[pattern_id] = metadata
        logger.debug(f"Pattern registered: {pattern_id}")

    @classmethod
    def get(cls, pattern_id: str) -> Type['BasePattern']:
        """Get pattern class by ID"""
        if pattern_id not in cls._patterns:
            raise ValueError(f"Pattern not found: {pattern_id}")
        return cls._patterns[pattern_id]

    @classmethod
    def has(cls, pattern_id: str) -> bool:
        """Check if pattern exists"""
        return pattern_id in cls._patterns

    @classmethod
    def list_all(cls) -> Dict[str, Type['BasePattern']]:
        """List all registered patterns"""
        return cls._patterns.copy()

    @classmethod
    def get_metadata(cls, pattern_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a pattern"""
        return cls._metadata.get(pattern_id)

    @classmethod
    def get_statistics(cls) -> Dict[str, Any]:
        """Get pattern registry statistics"""
        return {
            "total_patterns": len(cls._patterns),
            "patterns": list(cls._patterns.keys())
        }


class BasePattern(ABC):
    """
    Base class for Advanced Patterns (Level 4)

    Advanced patterns provide enterprise-grade execution capabilities
    such as retry logic, circuit breakers, rate limiting, and more.
    """

    pattern_id: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize pattern with configuration

        Args:
            config: Pattern-specific configuration
        """
        self.config = config or {}
        self.state = PatternState.IDLE
        self.metrics: Dict[str, Any] = {
            'executions': 0,
            'successes': 0,
            'failures': 0,
            'total_time_ms': 0.0
        }

    @abstractmethod
    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> PatternResult:
        """
        Execute the pattern with the given function

        Args:
            func: The function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            PatternResult with execution details
        """
        pass

    def _update_metrics(self, result: PatternResult):
        """Update pattern metrics after execution"""
        self.metrics['executions'] += 1
        self.metrics['total_time_ms'] += result.elapsed_ms

        if result.success:
            self.metrics['successes'] += 1
        else:
            self.metrics['failures'] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get pattern execution metrics"""
        return self.metrics.copy()

    def reset_metrics(self):
        """Reset pattern metrics"""
        self.metrics = {
            'executions': 0,
            'successes': 0,
            'failures': 0,
            'total_time_ms': 0.0
        }


def register_pattern(
    pattern_id: str,
    version: str = "1.0.0",
    category: str = "pattern",
    tags: Optional[List[str]] = None,

    # Display
    label: Optional[str] = None,
    label_key: Optional[str] = None,
    description: Optional[str] = None,
    description_key: Optional[str] = None,

    # Visual
    icon: Optional[str] = None,
    color: Optional[str] = None,

    # Configuration schema
    config_schema: Optional[Dict[str, Any]] = None,

    # Documentation
    examples: Optional[List[Dict[str, Any]]] = None,
    author: Optional[str] = None,
    license: str = "MIT"
):
    """
    Decorator to register an Advanced Pattern (Level 4)

    Example:
        @register_pattern(
            pattern_id='pattern.retry_backoff',
            label='Retry with Backoff',
            description='Retry failed operations with exponential backoff',
            config_schema={
                'max_retries': {'type': 'number', 'default': 3},
                'initial_delay_ms': {'type': 'number', 'default': 100},
                'backoff_multiplier': {'type': 'number', 'default': 2.0}
            }
        )
        class RetryWithBackoff(BasePattern):
            async def execute(self, func, *args, **kwargs):
                # Implementation
                pass
    """
    def decorator(cls):
        if not issubclass(cls, BasePattern):
            raise TypeError(f"{cls.__name__} must inherit from BasePattern")

        cls.pattern_id = pattern_id

        metadata = {
            "pattern_id": pattern_id,
            "version": version,
            "level": 4,  # Level 4 = Advanced Pattern
            "category": category,
            "tags": tags or [],
            "label": label or pattern_id,
            "label_key": label_key,
            "description": description or "",
            "description_key": description_key,
            "icon": icon,
            "color": color,
            "config_schema": config_schema or {},
            "examples": examples or [],
            "author": author,
            "license": license
        }

        PatternRegistry.register(pattern_id, cls, metadata)
        return cls

    return decorator


class PatternExecutor:
    """
    Executor for Advanced Patterns

    Provides a unified interface for executing patterns with
    proper configuration and error handling.
    """

    def __init__(self):
        self._pattern_instances: Dict[str, BasePattern] = {}

    def get_pattern(
        self,
        pattern_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> BasePattern:
        """
        Get or create a pattern instance

        Args:
            pattern_id: Pattern identifier
            config: Pattern configuration

        Returns:
            Pattern instance
        """
        cache_key = f"{pattern_id}:{hash(str(config))}"

        if cache_key not in self._pattern_instances:
            pattern_class = PatternRegistry.get(pattern_id)
            self._pattern_instances[cache_key] = pattern_class(config)

        return self._pattern_instances[cache_key]

    async def execute(
        self,
        pattern_id: str,
        func: Callable,
        *args,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> PatternResult:
        """
        Execute a function with a pattern

        Args:
            pattern_id: Pattern identifier
            func: Function to execute
            *args: Function arguments
            config: Pattern configuration
            **kwargs: Function keyword arguments

        Returns:
            PatternResult
        """
        pattern = self.get_pattern(pattern_id, config)
        return await pattern.execute(func, *args, **kwargs)
