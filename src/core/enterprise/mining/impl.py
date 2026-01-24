"""
Process Mining Implementation

Pure Python implementation of process discovery and analysis.
Implements DFG-based discovery, metrics calculation, and conformance checking.

For actual usage:
    from src.core.enterprise.mining.impl import get_discovery
    discovery = get_discovery()
"""

import logging
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Any, Dict, List, Optional, Set, Tuple

from . import (
    BottleneckInfo,
    ConformanceResult,
    Deviation,
    DiscoveryAlgorithm,
    EventLifecycle,
    EventLog,
    ProcessDiscovery,
    ProcessEvent,
    ProcessMetrics,
    ProcessModel,
    ProcessVariant,
)

logger = logging.getLogger(__name__)


class ProcessDiscoveryImpl(ProcessDiscovery):
    """
    Process discovery implementation using pure Python.

    Supports DFG-based discovery with optional noise filtering.
    """

    def __init__(self):
        self._models: Dict[str, ProcessModel] = {}

    async def discover_model(
        self,
        event_log: EventLog,
        algorithm: DiscoveryAlgorithm = DiscoveryAlgorithm.DFG,
        noise_threshold: float = 0.0,
    ) -> ProcessModel:
        """
        Discover process model from event log.

        Currently implements DFG (Directly-Follows Graph) algorithm.
        Other algorithms fall back to DFG with appropriate parameters.
        """
        logger.info(
            f"Discovering model from log {event_log.log_id} "
            f"using {algorithm.value} algorithm"
        )

        # Get cases and traces
        cases = event_log.get_cases()
        if not cases:
            raise ValueError("Event log is empty")

        # Build directly-follows graph
        dfg = self._build_dfg(cases)

        # Apply noise threshold
        if noise_threshold > 0:
            dfg = self._filter_noise(dfg, noise_threshold)

        # Extract activities and start/end activities
        activities = self._extract_activities(cases)
        start_activities = self._extract_start_activities(cases)
        end_activities = self._extract_end_activities(cases)

        # Build model structure
        nodes = []
        edges = []

        # Add activity nodes
        for activity in activities:
            node = {
                "id": activity,
                "type": "activity",
                "label": activity,
                "is_start": activity in start_activities,
                "is_end": activity in end_activities,
                "frequency": sum(1 for events in cases.values()
                               for e in events if e.activity == activity),
            }
            nodes.append(node)

        # Add edges from DFG
        for (source, target), count in dfg.items():
            edge = {
                "id": f"{source}->{target}",
                "source": source,
                "target": target,
                "frequency": count,
                "label": str(count),
            }
            edges.append(edge)

        # Calculate model quality metrics
        fitness = self._calculate_fitness(event_log, dfg)
        precision = self._calculate_precision(event_log, dfg)

        model_id = f"model_{uuid.uuid4().hex[:8]}"
        model = ProcessModel(
            model_id=model_id,
            name=f"Discovered from {event_log.name}",
            algorithm=algorithm,
            nodes=nodes,
            edges=edges,
            fitness=fitness,
            precision=precision,
            generalization=0.8,  # Estimated
            source_log_id=event_log.log_id,
            created_at=datetime.utcnow(),
        )

        self._models[model_id] = model
        logger.info(f"Discovered model {model_id} with {len(nodes)} nodes, {len(edges)} edges")

        return model

    def _build_dfg(
        self,
        cases: Dict[str, List[ProcessEvent]]
    ) -> Dict[Tuple[str, str], int]:
        """Build directly-follows graph from cases."""
        dfg: Dict[Tuple[str, str], int] = Counter()

        for case_events in cases.values():
            # Sort by timestamp
            sorted_events = sorted(case_events, key=lambda e: e.timestamp)

            # Count transitions
            for i in range(len(sorted_events) - 1):
                source = sorted_events[i].activity
                target = sorted_events[i + 1].activity
                dfg[(source, target)] += 1

        return dict(dfg)

    def _filter_noise(
        self,
        dfg: Dict[Tuple[str, str], int],
        threshold: float,
    ) -> Dict[Tuple[str, str], int]:
        """Filter infrequent edges based on threshold."""
        if not dfg:
            return dfg

        max_freq = max(dfg.values())
        min_count = int(max_freq * threshold)

        return {edge: count for edge, count in dfg.items() if count >= min_count}

    def _extract_activities(
        self,
        cases: Dict[str, List[ProcessEvent]]
    ) -> Set[str]:
        """Extract all unique activities."""
        activities = set()
        for events in cases.values():
            for event in events:
                activities.add(event.activity)
        return activities

    def _extract_start_activities(
        self,
        cases: Dict[str, List[ProcessEvent]]
    ) -> Set[str]:
        """Extract activities that start cases."""
        starts = set()
        for events in cases.values():
            if events:
                sorted_events = sorted(events, key=lambda e: e.timestamp)
                starts.add(sorted_events[0].activity)
        return starts

    def _extract_end_activities(
        self,
        cases: Dict[str, List[ProcessEvent]]
    ) -> Set[str]:
        """Extract activities that end cases."""
        ends = set()
        for events in cases.values():
            if events:
                sorted_events = sorted(events, key=lambda e: e.timestamp)
                ends.add(sorted_events[-1].activity)
        return ends

    def _calculate_fitness(
        self,
        event_log: EventLog,
        dfg: Dict[Tuple[str, str], int],
    ) -> float:
        """Calculate fitness (how well log fits DFG)."""
        cases = event_log.get_cases()
        if not cases:
            return 0.0

        total_transitions = 0
        valid_transitions = 0

        for events in cases.values():
            sorted_events = sorted(events, key=lambda e: e.timestamp)
            for i in range(len(sorted_events) - 1):
                source = sorted_events[i].activity
                target = sorted_events[i + 1].activity
                total_transitions += 1
                if (source, target) in dfg:
                    valid_transitions += 1

        return valid_transitions / total_transitions if total_transitions > 0 else 1.0

    def _calculate_precision(
        self,
        event_log: EventLog,
        dfg: Dict[Tuple[str, str], int],
    ) -> float:
        """Calculate precision (model doesn't allow too much)."""
        # Simplified: based on edge frequency distribution
        if not dfg:
            return 0.0

        frequencies = list(dfg.values())
        total = sum(frequencies)

        # High precision if most edges are frequently used
        if total == 0:
            return 0.0

        # Calculate entropy-based precision
        used_ratio = len([f for f in frequencies if f > 1]) / len(frequencies)
        return min(0.5 + used_ratio * 0.5, 1.0)

    async def calculate_metrics(
        self,
        event_log: EventLog,
        include_variants: bool = True,
        include_bottlenecks: bool = True,
        top_variants_count: int = 10,
    ) -> ProcessMetrics:
        """Calculate comprehensive process metrics."""
        logger.info(f"Calculating metrics for log {event_log.log_id}")

        cases = event_log.get_cases()
        if not cases:
            raise ValueError("Event log is empty")

        # Calculate case durations
        case_durations = []
        for case_id, events in cases.items():
            if len(events) >= 2:
                sorted_events = sorted(events, key=lambda e: e.timestamp)
                duration = sorted_events[-1].timestamp - sorted_events[0].timestamp
                case_durations.append((case_id, duration))

        if not case_durations:
            # All cases have single events
            case_durations = [(cid, timedelta(0)) for cid in cases.keys()]

        durations_td = [d for _, d in case_durations]
        durations_sec = [d.total_seconds() for d in durations_td]

        # Time metrics
        avg_duration = timedelta(seconds=mean(durations_sec)) if durations_sec else timedelta(0)
        median_duration = timedelta(seconds=median(durations_sec)) if durations_sec else timedelta(0)
        min_duration = min(durations_td) if durations_td else timedelta(0)
        max_duration = max(durations_td) if durations_td else timedelta(0)

        # Throughput
        if event_log.start_time and event_log.end_time:
            log_duration_days = (event_log.end_time - event_log.start_time).days or 1
            throughput = len(cases) / log_duration_days
        else:
            throughput = 0.0

        # Rework rate (cases with repeated activities)
        rework_cases = 0
        for events in cases.values():
            activities = [e.activity for e in events]
            if len(activities) != len(set(activities)):
                rework_cases += 1
        rework_rate = rework_cases / len(cases) if cases else 0.0

        # Automation rate (check resource field)
        automated_events = 0
        total_events = 0
        for events in cases.values():
            for event in events:
                total_events += 1
                if event.resource and event.resource.lower() in ("system", "bot", "automated", "robot"):
                    automated_events += 1
        automation_rate = automated_events / total_events if total_events > 0 else 0.0

        # First time right rate
        first_time_right = len(cases) - rework_cases
        first_time_right_rate = first_time_right / len(cases) if cases else 0.0

        # Variant analysis
        variants = []
        variant_count = 0
        if include_variants:
            variants, variant_count = self._analyze_variants(
                cases, case_durations, top_variants_count
            )

        # Bottleneck analysis
        bottlenecks = []
        waiting_times: Dict[str, timedelta] = {}
        if include_bottlenecks:
            bottlenecks, waiting_times = self._analyze_bottlenecks(cases)

        # Resource utilization
        resource_util = self._calculate_resource_utilization(cases)

        return ProcessMetrics(
            log_id=event_log.log_id,
            analysis_timestamp=datetime.utcnow(),
            avg_case_duration=avg_duration,
            median_case_duration=median_duration,
            min_case_duration=min_duration,
            max_case_duration=max_duration,
            throughput_per_day=throughput,
            rework_rate=rework_rate,
            automation_rate=automation_rate,
            first_time_right_rate=first_time_right_rate,
            bottleneck_activities=bottlenecks,
            waiting_time_breakdown=waiting_times,
            variant_count=variant_count,
            top_variants=variants,
            resource_utilization=resource_util,
        )

    def _analyze_variants(
        self,
        cases: Dict[str, List[ProcessEvent]],
        case_durations: List[Tuple[str, timedelta]],
        top_count: int,
    ) -> Tuple[List[ProcessVariant], int]:
        """Analyze process variants (unique traces)."""
        # Build trace -> cases mapping
        trace_cases: Dict[Tuple[str, ...], List[str]] = defaultdict(list)
        for case_id, events in cases.items():
            sorted_events = sorted(events, key=lambda e: e.timestamp)
            trace = tuple(e.activity for e in sorted_events)
            trace_cases[trace].append(case_id)

        # Build duration lookup
        duration_lookup = {cid: dur for cid, dur in case_durations}

        # Create variants
        variants = []
        total_cases = len(cases)

        for trace, case_ids in trace_cases.items():
            # Calculate average duration for this variant
            variant_durations = [
                duration_lookup.get(cid, timedelta(0))
                for cid in case_ids
            ]
            avg_dur = timedelta(
                seconds=mean(d.total_seconds() for d in variant_durations)
            ) if variant_durations else timedelta(0)

            variant = ProcessVariant(
                variant_id=f"variant_{len(variants) + 1}",
                activities=list(trace),
                case_count=len(case_ids),
                percentage=len(case_ids) / total_cases if total_cases > 0 else 0,
                avg_duration=avg_dur,
                example_case_id=case_ids[0] if case_ids else None,
            )
            variants.append(variant)

        # Sort by frequency and take top N
        variants.sort(key=lambda v: v.case_count, reverse=True)

        return variants[:top_count], len(trace_cases)

    def _analyze_bottlenecks(
        self,
        cases: Dict[str, List[ProcessEvent]],
    ) -> Tuple[List[BottleneckInfo], Dict[str, timedelta]]:
        """Analyze bottlenecks in the process."""
        # Track waiting and processing times per activity
        activity_waiting: Dict[str, List[float]] = defaultdict(list)
        activity_processing: Dict[str, List[float]] = defaultdict(list)

        for events in cases.values():
            sorted_events = sorted(events, key=lambda e: e.timestamp)

            for i, event in enumerate(sorted_events):
                # Waiting time: time since previous event
                if i > 0:
                    prev_event = sorted_events[i - 1]
                    waiting = (event.timestamp - prev_event.timestamp).total_seconds()
                    activity_waiting[event.activity].append(waiting)

                # Processing time from event duration or estimate
                if event.duration_ms:
                    activity_processing[event.activity].append(event.duration_ms / 1000)
                elif i < len(sorted_events) - 1:
                    # Estimate from gap to next event
                    next_event = sorted_events[i + 1]
                    processing = (next_event.timestamp - event.timestamp).total_seconds() * 0.3
                    activity_processing[event.activity].append(processing)

        bottlenecks = []
        waiting_times: Dict[str, timedelta] = {}

        # Identify bottlenecks (activities with high waiting times)
        for activity, wait_times in activity_waiting.items():
            if not wait_times:
                continue

            avg_wait = mean(wait_times)
            max_wait = max(wait_times)
            avg_proc = mean(activity_processing.get(activity, [0]))

            # Calculate utilization
            total_time = avg_wait + avg_proc
            utilization = avg_proc / total_time if total_time > 0 else 0

            waiting_times[activity] = timedelta(seconds=avg_wait)

            # Generate suggestions
            suggestions = []
            if avg_wait > 3600:  # > 1 hour
                suggestions.append("Consider adding parallel processing capacity")
            if utilization < 0.5:
                suggestions.append("Activity has low utilization - review resource allocation")
            if max_wait > avg_wait * 3:
                suggestions.append("High variance in waiting times - investigate outlier cases")

            bottleneck = BottleneckInfo(
                activity=activity,
                avg_waiting_time=timedelta(seconds=avg_wait),
                avg_processing_time=timedelta(seconds=avg_proc),
                max_waiting_time=timedelta(seconds=max_wait),
                utilization=utilization,
                queue_length_avg=avg_wait / (avg_proc + 1),
                suggestions=suggestions,
            )
            bottlenecks.append(bottleneck)

        # Sort by waiting time (longest first)
        bottlenecks.sort(key=lambda b: b.avg_waiting_time, reverse=True)

        return bottlenecks, waiting_times

    def _calculate_resource_utilization(
        self,
        cases: Dict[str, List[ProcessEvent]],
    ) -> Dict[str, float]:
        """Calculate resource utilization."""
        resource_events: Dict[str, int] = Counter()
        total_events = 0

        for events in cases.values():
            for event in events:
                total_events += 1
                if event.resource:
                    resource_events[event.resource] += 1

        if total_events == 0:
            return {}

        # Normalize to 0-1 range based on most active resource
        max_events = max(resource_events.values()) if resource_events else 1

        return {
            resource: count / max_events
            for resource, count in resource_events.items()
        }

    async def check_conformance(
        self,
        event_log: EventLog,
        process_model: ProcessModel,
        detailed_deviations: bool = True,
    ) -> ConformanceResult:
        """Check conformance between log and model."""
        logger.info(
            f"Checking conformance of log {event_log.log_id} "
            f"against model {process_model.model_id}"
        )

        # Build allowed transitions from model
        allowed_transitions: Set[Tuple[str, str]] = set()
        for edge in process_model.edges:
            allowed_transitions.add((edge["source"], edge["target"]))

        # Build valid activities from model
        valid_activities: Set[str] = set()
        start_activities: Set[str] = set()
        end_activities: Set[str] = set()

        for node in process_model.nodes:
            valid_activities.add(node["id"])
            if node.get("is_start"):
                start_activities.add(node["id"])
            if node.get("is_end"):
                end_activities.add(node["id"])

        cases = event_log.get_cases()
        conforming = 0
        deviating = 0
        deviations: List[Deviation] = []

        for case_id, events in cases.items():
            sorted_events = sorted(events, key=lambda e: e.timestamp)
            case_conforms = True

            for i, event in enumerate(sorted_events):
                # Check activity validity
                if event.activity not in valid_activities:
                    case_conforms = False
                    if detailed_deviations:
                        deviations.append(Deviation(
                            case_id=case_id,
                            deviation_type="unexpected_activity",
                            expected=None,
                            actual=event.activity,
                            timestamp=event.timestamp,
                            severity="error",
                        ))
                    continue

                # Check start activity
                if i == 0 and start_activities and event.activity not in start_activities:
                    case_conforms = False
                    if detailed_deviations:
                        deviations.append(Deviation(
                            case_id=case_id,
                            deviation_type="wrong_start",
                            expected=str(start_activities),
                            actual=event.activity,
                            timestamp=event.timestamp,
                            severity="warning",
                        ))

                # Check transition
                if i > 0:
                    prev_activity = sorted_events[i - 1].activity
                    if (prev_activity, event.activity) not in allowed_transitions:
                        case_conforms = False
                        if detailed_deviations:
                            deviations.append(Deviation(
                                case_id=case_id,
                                deviation_type="wrong_order",
                                expected=f"Valid transition from {prev_activity}",
                                actual=f"{prev_activity} -> {event.activity}",
                                timestamp=event.timestamp,
                                severity="warning",
                            ))

                # Check end activity
                if i == len(sorted_events) - 1 and end_activities and event.activity not in end_activities:
                    case_conforms = False
                    if detailed_deviations:
                        deviations.append(Deviation(
                            case_id=case_id,
                            deviation_type="wrong_end",
                            expected=str(end_activities),
                            actual=event.activity,
                            timestamp=event.timestamp,
                            severity="warning",
                        ))

            if case_conforms:
                conforming += 1
            else:
                deviating += 1

        # Calculate quality metrics
        total = conforming + deviating
        fitness = conforming / total if total > 0 else 0.0

        return ConformanceResult(
            log_id=event_log.log_id,
            model_id=process_model.model_id,
            checked_at=datetime.utcnow(),
            fitness=fitness,
            precision=process_model.precision,
            generalization=process_model.generalization,
            conforming_cases=conforming,
            deviating_cases=deviating,
            deviations=deviations if detailed_deviations else [],
        )

    async def suggest_improvements(
        self,
        metrics: ProcessMetrics,
        process_model: ProcessModel = None,
    ) -> List[Dict[str, Any]]:
        """Generate improvement suggestions based on metrics."""
        suggestions = []

        # Rework suggestions
        if metrics.rework_rate > 0.2:
            suggestions.append({
                "id": "reduce_rework",
                "category": "quality",
                "title": "Reduce rework rate",
                "description": f"Current rework rate is {metrics.rework_rate:.1%}. "
                             "Consider adding validation steps or checkpoints.",
                "expected_impact": {
                    "time_reduction": "15-25%",
                    "cost_reduction": "10-20%",
                },
                "priority": "high",
                "actions": [
                    "Add input validation at process start",
                    "Implement quality checkpoints",
                    "Review and update documentation",
                ],
            })

        # Automation suggestions
        if metrics.automation_rate < 0.5:
            suggestions.append({
                "id": "increase_automation",
                "category": "efficiency",
                "title": "Increase automation",
                "description": f"Current automation rate is {metrics.automation_rate:.1%}. "
                             "Identify manual activities for automation.",
                "expected_impact": {
                    "time_reduction": "30-50%",
                    "consistency": "improved",
                },
                "priority": "medium",
                "actions": [
                    "Identify repetitive manual tasks",
                    "Implement RPA for data entry",
                    "Add automated validations",
                ],
            })

        # Bottleneck suggestions
        for bottleneck in metrics.bottleneck_activities[:3]:
            if bottleneck.avg_waiting_time.total_seconds() > 3600:
                suggestions.append({
                    "id": f"bottleneck_{bottleneck.activity}",
                    "category": "performance",
                    "title": f"Address bottleneck: {bottleneck.activity}",
                    "description": f"Average waiting time is "
                                 f"{bottleneck.avg_waiting_time.total_seconds()/3600:.1f} hours.",
                    "expected_impact": {
                        "time_reduction": "20-40%",
                    },
                    "priority": "high",
                    "actions": bottleneck.suggestions or [
                        "Add parallel processing",
                        "Optimize resource allocation",
                        "Review activity prerequisites",
                    ],
                })

        # Variant reduction suggestions
        if metrics.variant_count > 10:
            suggestions.append({
                "id": "standardize_process",
                "category": "standardization",
                "title": "Standardize process execution",
                "description": f"Found {metrics.variant_count} process variants. "
                             "Consider standardizing the happy path.",
                "expected_impact": {
                    "training_cost": "reduced",
                    "error_rate": "reduced",
                },
                "priority": "medium",
                "actions": [
                    "Document standard operating procedure",
                    "Implement guided workflows",
                    "Add process enforcement rules",
                ],
            })

        # Throughput suggestions
        if metrics.throughput_per_day < 10:
            suggestions.append({
                "id": "improve_throughput",
                "category": "capacity",
                "title": "Improve throughput",
                "description": f"Current throughput is {metrics.throughput_per_day:.1f} cases/day.",
                "expected_impact": {
                    "capacity_increase": "50-100%",
                },
                "priority": "medium",
                "actions": [
                    "Parallelize independent activities",
                    "Reduce handoff delays",
                    "Optimize resource scheduling",
                ],
            })

        return suggestions


# Singleton instance
_discovery_instance: ProcessDiscoveryImpl = None


def get_discovery() -> ProcessDiscoveryImpl:
    """Get the process discovery singleton instance."""
    global _discovery_instance
    if _discovery_instance is None:
        _discovery_instance = ProcessDiscoveryImpl()
    return _discovery_instance


__all__ = [
    "ProcessDiscoveryImpl",
    "get_discovery",
]
