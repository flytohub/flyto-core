"""
Process Mining - Process Discovery and Analysis

Discover process patterns from execution logs:
- Event log analysis (XES compatible)
- Process model discovery (Alpha, Heuristic, Inductive miners)
- Conformance checking
- Bottleneck analysis
- Process variant analysis

Reference: ITEM_PIPELINE_SPEC.md Section 15
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class EventLifecycle(Enum):
    """Event lifecycle states (XES standard)."""
    START = "start"
    COMPLETE = "complete"
    SUSPEND = "suspend"
    RESUME = "resume"
    ABORT = "abort"
    AUTOSKIP = "autoskip"


class DiscoveryAlgorithm(Enum):
    """Process discovery algorithms."""
    ALPHA = "alpha"          # Alpha Miner (fast, structured processes)
    HEURISTIC = "heuristic"  # Heuristic Miner (noise tolerant)
    INDUCTIVE = "inductive"  # Inductive Miner (guarantees soundness)
    DFG = "dfg"              # Directly-Follows Graph (simplest)


@dataclass
class ProcessEvent:
    """
    Single process event (XES compatible).

    Represents one activity occurrence in a process instance.
    """
    case_id: str                    # Case/process instance ID
    activity: str                   # Activity name
    timestamp: datetime             # Event timestamp
    resource: Optional[str] = None  # Executor (user, system, etc.)
    lifecycle: EventLifecycle = EventLifecycle.COMPLETE

    # Additional attributes
    attributes: Dict[str, Any] = field(default_factory=dict)

    # Cost/performance
    cost: Optional[float] = None
    duration_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "case_id": self.case_id,
            "activity": self.activity,
            "timestamp": self.timestamp.isoformat(),
            "resource": self.resource,
            "lifecycle": self.lifecycle.value,
            "attributes": self.attributes,
            "cost": self.cost,
            "duration_ms": self.duration_ms,
        }


@dataclass
class EventLog:
    """
    Event log containing multiple process events.

    Compatible with XES (eXtensible Event Stream) format.
    """
    log_id: str
    name: str
    events: List[ProcessEvent] = field(default_factory=list)

    # Metadata
    source: Optional[str] = None
    created_at: Optional[datetime] = None

    # Computed statistics (lazy)
    _stats: Optional[Dict[str, Any]] = field(default=None, repr=False)

    @property
    def case_count(self) -> int:
        """Number of unique cases."""
        return len(set(e.case_id for e in self.events))

    @property
    def event_count(self) -> int:
        """Total number of events."""
        return len(self.events)

    @property
    def activity_count(self) -> int:
        """Number of unique activities."""
        return len(set(e.activity for e in self.events))

    @property
    def start_time(self) -> Optional[datetime]:
        """Earliest event timestamp."""
        if not self.events:
            return None
        return min(e.timestamp for e in self.events)

    @property
    def end_time(self) -> Optional[datetime]:
        """Latest event timestamp."""
        if not self.events:
            return None
        return max(e.timestamp for e in self.events)

    def get_cases(self) -> Dict[str, List[ProcessEvent]]:
        """Group events by case ID."""
        cases: Dict[str, List[ProcessEvent]] = {}
        for event in self.events:
            if event.case_id not in cases:
                cases[event.case_id] = []
            cases[event.case_id].append(event)
        # Sort events within each case by timestamp
        for case_events in cases.values():
            case_events.sort(key=lambda e: e.timestamp)
        return cases

    def get_trace(self, case_id: str) -> List[str]:
        """Get activity sequence for a case."""
        cases = self.get_cases()
        if case_id not in cases:
            return []
        return [e.activity for e in cases[case_id]]


@dataclass
class ProcessVariant:
    """A unique process execution path (trace variant)."""
    variant_id: str
    activities: List[str]          # Activity sequence
    case_count: int                # Number of cases following this path
    percentage: float              # Percentage of total cases
    avg_duration: timedelta        # Average case duration
    example_case_id: Optional[str] = None


@dataclass
class BottleneckInfo:
    """Bottleneck analysis result for an activity."""
    activity: str
    avg_waiting_time: timedelta
    avg_processing_time: timedelta
    max_waiting_time: timedelta
    utilization: float             # 0-1
    queue_length_avg: float
    suggestions: List[str] = field(default_factory=list)


@dataclass
class ProcessMetrics:
    """Comprehensive process metrics."""
    log_id: str
    analysis_timestamp: datetime

    # Time metrics
    avg_case_duration: timedelta
    median_case_duration: timedelta
    min_case_duration: timedelta
    max_case_duration: timedelta
    throughput_per_day: float

    # Efficiency metrics
    rework_rate: float              # Percentage of cases with repeated activities
    automation_rate: float          # Percentage of automated activities
    first_time_right_rate: float    # Cases completed without rework

    # Bottleneck analysis
    bottleneck_activities: List[BottleneckInfo] = field(default_factory=list)
    waiting_time_breakdown: Dict[str, timedelta] = field(default_factory=dict)

    # Variant analysis
    variant_count: int = 0
    top_variants: List[ProcessVariant] = field(default_factory=list)

    # Resource metrics
    resource_utilization: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "log_id": self.log_id,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "avg_case_duration_seconds": self.avg_case_duration.total_seconds(),
            "median_case_duration_seconds": self.median_case_duration.total_seconds(),
            "throughput_per_day": self.throughput_per_day,
            "rework_rate": self.rework_rate,
            "automation_rate": self.automation_rate,
            "first_time_right_rate": self.first_time_right_rate,
            "variant_count": self.variant_count,
            "bottlenecks": [
                {
                    "activity": b.activity,
                    "avg_waiting_time_seconds": b.avg_waiting_time.total_seconds(),
                    "suggestions": b.suggestions,
                }
                for b in self.bottleneck_activities
            ],
        }


@dataclass
class ProcessModel:
    """Discovered process model."""
    model_id: str
    name: str
    algorithm: DiscoveryAlgorithm

    # Model representation
    nodes: List[Dict[str, Any]]    # Activities/places
    edges: List[Dict[str, Any]]    # Transitions

    # Quality metrics
    fitness: float = 0.0           # How well log fits model
    precision: float = 0.0         # Model doesn't allow too much
    generalization: float = 0.0    # Model can generalize

    # Source
    source_log_id: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class Deviation:
    """Conformance deviation."""
    case_id: str
    deviation_type: str  # "missing_activity" | "unexpected_activity" | "wrong_order"
    expected: Optional[str] = None
    actual: Optional[str] = None
    timestamp: Optional[datetime] = None
    severity: str = "warning"  # "warning" | "error"


@dataclass
class ConformanceResult:
    """Conformance checking result."""
    log_id: str
    model_id: str
    checked_at: datetime

    # Quality metrics (0-1)
    fitness: float          # How well traces fit the model
    precision: float        # Model doesn't over-generalize
    generalization: float   # Model can handle unseen cases

    # Deviation details
    conforming_cases: int
    deviating_cases: int
    deviations: List[Deviation] = field(default_factory=list)

    @property
    def conformance_rate(self) -> float:
        """Percentage of conforming cases."""
        total = self.conforming_cases + self.deviating_cases
        return self.conforming_cases / total if total > 0 else 0.0


class ProcessDiscovery:
    """
    Process discovery interface.

    Discovers process models from event logs.
    """

    async def discover_model(
        self,
        event_log: EventLog,
        algorithm: DiscoveryAlgorithm = DiscoveryAlgorithm.HEURISTIC,
        noise_threshold: float = 0.0,
    ) -> ProcessModel:
        """
        Discover process model from event log.

        Args:
            event_log: Input event log
            algorithm: Discovery algorithm to use
            noise_threshold: Filter out infrequent behavior (0-1)

        Returns:
            Discovered ProcessModel
        """
        raise NotImplementedError("Implementation required")

    async def calculate_metrics(
        self,
        event_log: EventLog,
        include_variants: bool = True,
        include_bottlenecks: bool = True,
        top_variants_count: int = 10,
    ) -> ProcessMetrics:
        """
        Calculate process metrics from event log.

        Args:
            event_log: Input event log
            include_variants: Include variant analysis
            include_bottlenecks: Include bottleneck analysis
            top_variants_count: Number of top variants to include

        Returns:
            ProcessMetrics with analysis results
        """
        raise NotImplementedError("Implementation required")

    async def check_conformance(
        self,
        event_log: EventLog,
        process_model: ProcessModel,
        detailed_deviations: bool = True,
    ) -> ConformanceResult:
        """
        Check conformance between log and model.

        Args:
            event_log: Actual execution log
            process_model: Expected process model
            detailed_deviations: Include deviation details

        Returns:
            ConformanceResult with metrics and deviations
        """
        raise NotImplementedError("Implementation required")

    async def suggest_improvements(
        self,
        metrics: ProcessMetrics,
        process_model: ProcessModel = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate AI-powered improvement suggestions.

        Args:
            metrics: Process metrics
            process_model: Optional process model for context

        Returns:
            List of improvement suggestions with expected impact
        """
        raise NotImplementedError("Implementation required")


__all__ = [
    # Enums
    'EventLifecycle',
    'DiscoveryAlgorithm',
    # Data structures
    'ProcessEvent',
    'EventLog',
    'ProcessVariant',
    'BottleneckInfo',
    'ProcessMetrics',
    'ProcessModel',
    'Deviation',
    'ConformanceResult',
    # Interface
    'ProcessDiscovery',
]
