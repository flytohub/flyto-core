"""
Enterprise Orchestrator Implementation

Robot management, job scheduling, and execution coordination.

For usage:
    from src.core.enterprise.orchestrator.impl import get_orchestrator
    orchestrator = get_orchestrator()
"""

import asyncio
import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from . import (
    JobExecution,
    JobStatus,
    Orchestrator,
    OrchestratorStats,
    RetryPolicy,
    Robot,
    RobotCapabilities,
    RobotManager,
    RobotRequirements,
    RobotStatus,
    RobotType,
    ScheduledJob,
    Scheduler,
    ScheduleType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Cron Parser (Simple Implementation)
# =============================================================================

class CronParser:
    """Simple cron expression parser."""

    @staticmethod
    def parse(expression: str) -> Dict[str, List[int]]:
        """
        Parse cron expression into component values.

        Format: minute hour day_of_month month day_of_week
        Supports: *, */n, n, n-m, n,m,o
        """
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {expression}")

        names = ["minute", "hour", "day_of_month", "month", "day_of_week"]
        ranges = [
            (0, 59),  # minute
            (0, 23),  # hour
            (1, 31),  # day of month
            (1, 12),  # month
            (0, 6),   # day of week (0=Sunday)
        ]

        result = {}
        for i, (part, name, (min_val, max_val)) in enumerate(zip(parts, names, ranges)):
            result[name] = CronParser._parse_field(part, min_val, max_val)

        return result

    @staticmethod
    def _parse_field(field: str, min_val: int, max_val: int) -> List[int]:
        """Parse a single cron field."""
        if field == "*":
            return list(range(min_val, max_val + 1))

        if field.startswith("*/"):
            step = int(field[2:])
            return list(range(min_val, max_val + 1, step))

        if "-" in field:
            start, end = map(int, field.split("-"))
            return list(range(start, end + 1))

        if "," in field:
            return [int(x) for x in field.split(",")]

        return [int(field)]

    @staticmethod
    def get_next_run(expression: str, after: datetime = None) -> datetime:
        """Get next run time after given datetime."""
        after = after or datetime.utcnow()
        parsed = CronParser.parse(expression)

        # Start from next minute
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Find next matching time (limit search to 1 year)
        for _ in range(525600):  # ~1 year in minutes
            if (
                candidate.minute in parsed["minute"]
                and candidate.hour in parsed["hour"]
                and candidate.day in parsed["day_of_month"]
                and candidate.month in parsed["month"]
                and candidate.weekday() in [d % 7 for d in parsed["day_of_week"]]
            ):
                return candidate
            candidate += timedelta(minutes=1)

        raise ValueError(f"Cannot find next run for: {expression}")


# =============================================================================
# Robot Manager Implementation
# =============================================================================

class RobotManagerImpl(RobotManager):
    """
    Robot manager implementation.

    Features:
    - Robot registration and lifecycle
    - Health monitoring via heartbeat
    - Capability-based matching
    - Load balancing
    """

    def __init__(self):
        self._robots: Dict[str, Robot] = {}
        self._heartbeat_timeout = timedelta(seconds=60)
        self._execution_assignments: Dict[str, str] = {}  # execution_id -> robot_id

    async def register(self, robot: Robot) -> str:
        """Register a new robot."""
        if not robot.robot_id:
            robot.robot_id = f"robot_{uuid.uuid4().hex[:12]}"

        robot.registered_at = datetime.utcnow()
        robot.last_heartbeat = datetime.utcnow()
        robot.status = RobotStatus.AVAILABLE

        self._robots[robot.robot_id] = robot
        logger.info(f"Registered robot: {robot.robot_id} ({robot.name})")

        return robot.robot_id

    async def unregister(self, robot_id: str) -> bool:
        """Unregister a robot."""
        if robot_id in self._robots:
            del self._robots[robot_id]
            # Clean up assignments
            to_remove = [
                eid for eid, rid in self._execution_assignments.items()
                if rid == robot_id
            ]
            for eid in to_remove:
                del self._execution_assignments[eid]

            logger.info(f"Unregistered robot: {robot_id}")
            return True
        return False

    async def heartbeat(
        self,
        robot_id: str,
        status: RobotStatus,
        metrics: Dict[str, Any] = None,
    ) -> None:
        """Update robot heartbeat."""
        robot = self._robots.get(robot_id)
        if not robot:
            raise ValueError(f"Robot not found: {robot_id}")

        robot.last_heartbeat = datetime.utcnow()
        robot.status = status

        logger.debug(f"Heartbeat from {robot_id}: {status.value}")

    async def get_robot(self, robot_id: str) -> Optional[Robot]:
        """Get robot by ID."""
        return self._robots.get(robot_id)

    async def get_available_robots(
        self,
        requirements: RobotRequirements = None,
    ) -> List[Robot]:
        """Get available robots matching requirements."""
        # Check for stale heartbeats
        now = datetime.utcnow()
        for robot in self._robots.values():
            if robot.last_heartbeat:
                if now - robot.last_heartbeat > self._heartbeat_timeout:
                    robot.status = RobotStatus.DISCONNECTED

        available = [
            r for r in self._robots.values()
            if r.is_available
        ]

        if requirements:
            available = self._filter_by_requirements(available, requirements)

        # Sort by load (least loaded first)
        available.sort(key=lambda r: r.current_load)

        return available

    def _filter_by_requirements(
        self,
        robots: List[Robot],
        req: RobotRequirements,
    ) -> List[Robot]:
        """Filter robots by requirements."""
        result = []

        for robot in robots:
            # Check excluded
            if robot.robot_id in req.excluded_robots:
                continue

            # Check environment
            if req.environments:
                if not any(env in robot.environments for env in req.environments):
                    continue

            # Check capabilities
            if req.capabilities:
                robot_caps = set()
                if robot.capabilities.browser:
                    robot_caps.add("browser")
                if robot.capabilities.desktop:
                    robot_caps.add("desktop")
                if robot.capabilities.vision:
                    robot_caps.add("vision")
                if robot.capabilities.ai:
                    robot_caps.add("ai")
                robot_caps.update(robot.capabilities.custom)

                if not all(cap in robot_caps for cap in req.capabilities):
                    continue

            # Check version
            if req.min_version and robot.version:
                if robot.version < req.min_version:
                    continue

            # Preferred robots get priority
            result.append(robot)

        # Sort preferred first
        if req.preferred_robots:
            result.sort(
                key=lambda r: 0 if r.robot_id in req.preferred_robots else 1
            )

        return result

    async def assign_job(
        self,
        robot_id: str,
        execution_id: str,
    ) -> bool:
        """Assign job to robot."""
        robot = self._robots.get(robot_id)
        if not robot or not robot.is_available:
            return False

        robot.current_load += 1
        robot.current_job_id = execution_id
        if robot.current_load >= robot.max_concurrent_jobs:
            robot.status = RobotStatus.BUSY

        self._execution_assignments[execution_id] = robot_id

        logger.info(f"Assigned execution {execution_id} to robot {robot_id}")
        return True

    async def release_robot(self, robot_id: str) -> bool:
        """Release robot after job completion."""
        robot = self._robots.get(robot_id)
        if not robot:
            return False

        robot.current_load = max(0, robot.current_load - 1)
        if robot.current_load == 0:
            robot.current_job_id = None
        if robot.status == RobotStatus.BUSY and robot.current_load < robot.max_concurrent_jobs:
            robot.status = RobotStatus.AVAILABLE

        logger.info(f"Released robot {robot_id}")
        return True

    async def get_all_robots(self) -> List[Robot]:
        """Get all registered robots."""
        return list(self._robots.values())


# =============================================================================
# Scheduler Implementation
# =============================================================================

class SchedulerImpl(Scheduler):
    """
    Job scheduler implementation.

    Features:
    - Cron and interval scheduling
    - One-time and event-triggered jobs
    - Execution tracking
    - Retry handling
    """

    def __init__(self):
        self._jobs: Dict[str, ScheduledJob] = {}
        self._executions: Dict[str, JobExecution] = {}
        self._pending_queue: List[str] = []  # execution_ids

    async def create_schedule(self, job: ScheduledJob) -> str:
        """Create a new scheduled job."""
        if not job.job_id:
            job.job_id = f"job_{uuid.uuid4().hex[:12]}"

        job.created_at = datetime.utcnow()
        job.updated_at = job.created_at

        # Calculate next run
        job.next_run = self._calculate_next_run(job)

        self._jobs[job.job_id] = job
        logger.info(f"Created schedule: {job.job_id} ({job.name})")

        return job.job_id

    async def update_schedule(
        self,
        job_id: str,
        updates: Dict[str, Any],
    ) -> ScheduledJob:
        """Update scheduled job."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        for key, value in updates.items():
            if hasattr(job, key):
                setattr(job, key, value)

        job.updated_at = datetime.utcnow()
        job.next_run = self._calculate_next_run(job)

        return job

    async def delete_schedule(self, job_id: str) -> bool:
        """Delete scheduled job."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            logger.info(f"Deleted schedule: {job_id}")
            return True
        return False

    async def enable_schedule(self, job_id: str) -> ScheduledJob:
        """Enable a disabled schedule."""
        return await self.update_schedule(job_id, {"enabled": True})

    async def disable_schedule(self, job_id: str) -> ScheduledJob:
        """Disable a schedule."""
        return await self.update_schedule(job_id, {"enabled": False})

    async def trigger_now(
        self,
        job_id: str,
        params: Dict[str, Any] = None,
    ) -> JobExecution:
        """Trigger job immediately."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        execution = JobExecution(
            execution_id=f"exec_{uuid.uuid4().hex[:12]}",
            job_id=job_id,
            workflow_id=job.workflow_id,
            status=JobStatus.PENDING,
            params=params or job.params,
            trigger_type="manual",
            triggered_by="api",
            max_attempts=job.retry_policy.max_retries + 1 if job.retry_policy else 1,
        )

        self._executions[execution.execution_id] = execution
        self._pending_queue.append(execution.execution_id)

        logger.info(f"Triggered job {job_id} -> execution {execution.execution_id}")
        return execution

    async def get_schedule(self, job_id: str) -> Optional[ScheduledJob]:
        """Get scheduled job by ID."""
        return self._jobs.get(job_id)

    async def list_schedules(
        self,
        workflow_id: str = None,
        enabled_only: bool = False,
    ) -> List[ScheduledJob]:
        """List scheduled jobs."""
        result = []
        for job in self._jobs.values():
            if workflow_id and job.workflow_id != workflow_id:
                continue
            if enabled_only and not job.enabled:
                continue
            result.append(job)
        return result

    async def get_upcoming_jobs(self, hours: int = 24) -> List[ScheduledJob]:
        """Get jobs scheduled to run within time window."""
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours)

        upcoming = []
        for job in self._jobs.values():
            if job.enabled and job.next_run and job.next_run <= cutoff:
                upcoming.append(job)

        upcoming.sort(key=lambda j: j.next_run or datetime.max)
        return upcoming

    async def get_execution(self, execution_id: str) -> Optional[JobExecution]:
        """Get job execution by ID."""
        return self._executions.get(execution_id)

    async def list_executions(
        self,
        job_id: str = None,
        status: JobStatus = None,
        limit: int = 100,
    ) -> List[JobExecution]:
        """List job executions."""
        result = []
        for execution in self._executions.values():
            if job_id and execution.job_id != job_id:
                continue
            if status and execution.status != status:
                continue
            result.append(execution)

        # Sort by most recent first
        result.sort(key=lambda e: e.started_at or datetime.min, reverse=True)
        return result[:limit]

    async def cancel_execution(
        self,
        execution_id: str,
        reason: str = None,
    ) -> JobExecution:
        """Cancel a running execution."""
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution not found: {execution_id}")

        if execution.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            return execution

        execution.status = JobStatus.CANCELLED
        execution.completed_at = datetime.utcnow()
        execution.error = reason or "Cancelled by user"

        if execution.execution_id in self._pending_queue:
            self._pending_queue.remove(execution.execution_id)

        logger.info(f"Cancelled execution: {execution_id}")
        return execution

    async def complete_execution(
        self,
        execution_id: str,
        result: Dict[str, Any] = None,
        error: str = None,
    ) -> JobExecution:
        """Complete an execution."""
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution not found: {execution_id}")

        execution.completed_at = datetime.utcnow()
        if execution.started_at:
            execution.duration_ms = int(
                (execution.completed_at - execution.started_at).total_seconds() * 1000
            )

        if error:
            execution.status = JobStatus.FAILED
            execution.error = error
        else:
            execution.status = JobStatus.COMPLETED
            execution.result = result

        # Update job last run info
        job = self._jobs.get(execution.job_id)
        if job:
            job.last_run = execution.completed_at
            job.last_run_status = execution.status
            job.next_run = self._calculate_next_run(job)

        return execution

    async def start_execution(self, execution_id: str, robot_id: str) -> JobExecution:
        """Mark execution as started."""
        execution = self._executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution not found: {execution_id}")

        execution.status = JobStatus.RUNNING
        execution.started_at = datetime.utcnow()
        execution.robot_id = robot_id

        if execution.execution_id in self._pending_queue:
            self._pending_queue.remove(execution.execution_id)

        return execution

    async def get_pending_executions(self) -> List[JobExecution]:
        """Get pending executions in queue order."""
        return [
            self._executions[eid]
            for eid in self._pending_queue
            if eid in self._executions
        ]

    async def check_due_jobs(self) -> List[JobExecution]:
        """Check for jobs that are due to run and create executions."""
        now = datetime.utcnow()
        created = []

        for job in self._jobs.values():
            if not job.enabled:
                continue
            if not job.next_run or job.next_run > now:
                continue

            # Create execution
            execution = await self.trigger_now(job.job_id)
            execution.trigger_type = "scheduled"
            created.append(execution)

        return created

    def _calculate_next_run(self, job: ScheduledJob) -> Optional[datetime]:
        """Calculate next run time for job."""
        now = datetime.utcnow()

        if job.schedule_type == ScheduleType.CRON and job.cron_expression:
            try:
                return CronParser.get_next_run(job.cron_expression, now)
            except Exception as e:
                logger.error(f"Failed to parse cron: {e}")
                return None

        elif job.schedule_type == ScheduleType.INTERVAL and job.interval_seconds:
            base = job.last_run or now
            return base + timedelta(seconds=job.interval_seconds)

        elif job.schedule_type == ScheduleType.ONCE and job.run_at:
            if job.run_at > now:
                return job.run_at
            return None

        elif job.schedule_type == ScheduleType.EVENT:
            return None  # Event-triggered, no scheduled time

        return None


# =============================================================================
# Orchestrator Implementation
# =============================================================================

class OrchestratorImpl(Orchestrator):
    """
    Main orchestrator implementation.

    Coordinates robots, jobs, and executions.
    """

    def __init__(
        self,
        robot_manager: RobotManager = None,
        scheduler: Scheduler = None,
    ):
        self._robot_manager = robot_manager or RobotManagerImpl()
        self._scheduler = scheduler or SchedulerImpl()
        super().__init__(self._robot_manager, self._scheduler)

        # Job handler (workflow executor)
        self._job_handler: Optional[Callable] = None

    def set_job_handler(self, handler: Callable) -> None:
        """Set the job execution handler."""
        self._job_handler = handler

    async def get_stats(self) -> OrchestratorStats:
        """Get current orchestrator statistics."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Robot stats
        robots = await self._robot_manager.get_all_robots()
        total = len(robots)
        available = sum(1 for r in robots if r.status == RobotStatus.AVAILABLE)
        busy = sum(1 for r in robots if r.status == RobotStatus.BUSY)
        offline = sum(1 for r in robots if r.status in (RobotStatus.OFFLINE, RobotStatus.DISCONNECTED))

        # Execution stats
        all_executions = await self._scheduler.list_executions(limit=10000)
        pending = sum(1 for e in all_executions if e.status == JobStatus.PENDING)
        running = sum(1 for e in all_executions if e.status == JobStatus.RUNNING)

        today_executions = [
            e for e in all_executions
            if e.started_at and e.started_at >= today_start
        ]
        completed = sum(1 for e in today_executions if e.status == JobStatus.COMPLETED)
        failed = sum(1 for e in today_executions if e.status == JobStatus.FAILED)

        # Performance
        durations = [e.duration_ms for e in today_executions if e.duration_ms > 0]
        avg_duration = int(sum(durations) / len(durations)) if durations else 0

        success_rate = completed / len(today_executions) if today_executions else 0.0

        return OrchestratorStats(
            timestamp=now,
            total_robots=total,
            available_robots=available,
            busy_robots=busy,
            offline_robots=offline,
            jobs_pending=pending,
            jobs_running=running,
            jobs_completed_today=completed,
            jobs_failed_today=failed,
            avg_job_duration_ms=avg_duration,
            success_rate_today=success_rate,
        )

    async def dispatch_job(self, execution: JobExecution) -> bool:
        """Dispatch job to available robot."""
        # Get job for requirements
        job = await self._scheduler.get_schedule(execution.job_id)
        requirements = job.robot_requirements if job else None

        # Find available robot
        robots = await self._robot_manager.get_available_robots(requirements)
        if not robots:
            logger.warning(f"No available robot for execution {execution.execution_id}")
            return False

        robot = robots[0]

        # Assign and start
        assigned = await self._robot_manager.assign_job(
            robot.robot_id, execution.execution_id
        )
        if not assigned:
            return False

        await self._scheduler.start_execution(execution.execution_id, robot.robot_id)

        # Execute job asynchronously
        asyncio.create_task(self._execute_job(execution, robot))

        return True

    async def _execute_job(self, execution: JobExecution, robot: Robot) -> None:
        """Execute job on robot."""
        try:
            if self._job_handler:
                result = await self._job_handler(execution, robot)
                await self._scheduler.complete_execution(
                    execution.execution_id,
                    result=result,
                )
            else:
                # Mock execution
                await asyncio.sleep(0.5)
                await self._scheduler.complete_execution(
                    execution.execution_id,
                    result={"status": "mock_completed"},
                )

        except Exception as e:
            logger.error(f"Job execution failed: {e}", exc_info=True)
            await self._scheduler.complete_execution(
                execution.execution_id,
                error=str(e),
            )

        finally:
            await self._robot_manager.release_robot(robot.robot_id)

    async def process_queue(self) -> int:
        """Process pending job queue."""
        # Check for due jobs
        await self._scheduler.check_due_jobs()

        # Get pending executions
        pending = await self._scheduler.get_pending_executions()

        dispatched = 0
        for execution in pending:
            success = await self.dispatch_job(execution)
            if success:
                dispatched += 1

        return dispatched

    async def run_scheduler_loop(self, interval_seconds: int = 10) -> None:
        """Run scheduler loop continuously."""
        logger.info("Starting scheduler loop")
        while True:
            try:
                dispatched = await self.process_queue()
                if dispatched > 0:
                    logger.info(f"Dispatched {dispatched} jobs")
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}", exc_info=True)

            await asyncio.sleep(interval_seconds)


# =============================================================================
# Singleton Instances
# =============================================================================

_robot_manager: RobotManagerImpl = None
_scheduler: SchedulerImpl = None
_orchestrator: OrchestratorImpl = None


def get_robot_manager() -> RobotManagerImpl:
    """Get robot manager singleton."""
    global _robot_manager
    if _robot_manager is None:
        _robot_manager = RobotManagerImpl()
    return _robot_manager


def get_scheduler() -> SchedulerImpl:
    """Get scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerImpl()
    return _scheduler


def get_orchestrator() -> OrchestratorImpl:
    """Get orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = OrchestratorImpl(
            get_robot_manager(),
            get_scheduler(),
        )
    return _orchestrator


__all__ = [
    # Implementations
    "RobotManagerImpl",
    "SchedulerImpl",
    "OrchestratorImpl",
    "CronParser",
    # Factory functions
    "get_robot_manager",
    "get_scheduler",
    "get_orchestrator",
]
