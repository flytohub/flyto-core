"""
Experience Auto-Archiving
Automatically archives training results, errors, and successes to vector database
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import json
from .knowledge_store import KnowledgeStore
from .quality_filter import QualityFilter


logger = logging.getLogger(__name__)


class ExperienceArchiver:
    """
    Automatically archives experiences to knowledge base
    """

    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        enable_quality_filter: bool = True
    ):
        """
        Initialize experience archiver

        Args:
            knowledge_store: KnowledgeStore instance
            enable_quality_filter: Enable quality filtering
        """
        self.store = knowledge_store
        self.quality_filter = QualityFilter() if enable_quality_filter else None

    def archive_practice_result(
        self,
        website: str,
        result: Dict[str, Any],
        analysis: Optional[str] = None
    ) -> Optional[str]:
        """
        Archive daily practice result

        Args:
            website: Target website URL
            result: Practice execution result
            analysis: Optional analysis text

        Returns:
            Entry ID or None if filtered
        """
        # Extract key information
        success = result.get("status") == "success"
        steps_count = len(result.get("steps", []))
        duration = result.get("duration", 0)

        # Build content
        content_parts = [
            f"Daily Practice on {website}:",
            f"Status: {result.get('status')}",
            f"Steps executed: {steps_count}",
            f"Duration: {duration:.2f}s"
        ]

        if analysis:
            content_parts.append(f"Analysis: {analysis}")

        if result.get("errors"):
            content_parts.append(f"Errors: {len(result['errors'])} encountered")

        content = " | ".join(content_parts)

        # Build metadata
        metadata = {
            "source": "daily_practice",
            "category": "success" if success else "error",
            "website": website,
            "steps_count": steps_count,
            "duration": duration,
            "timestamp": datetime.now().isoformat()
        }

        # Quality filter check
        if self.quality_filter:
            should_archive, score, reason = self.quality_filter.should_archive(content, metadata)
            if not should_archive:
                logger.debug(f"Filtered practice result (score={score:.2f}, reason={reason})")
                return None
            metadata["quality_score"] = score

        # Store with metadata
        entry_id = self.store.store(content=content, metadata=metadata)

        return entry_id

    def archive_speed_race(
        self,
        task_name: str,
        race_result: Dict[str, Any]
    ) -> Optional[str]:
        """
        Archive speed race result

        Args:
            task_name: Task name
            race_result: Race execution result

        Returns:
            Entry ID or None if filtered
        """
        stats = race_result.get("stats", {})

        content = (
            f"Speed Race - {task_name}: "
            f"Best time: {stats.get('best_time', 0):.2f}s, "
            f"Average: {stats.get('avg_time', 0):.2f}s, "
            f"Success rate: {stats.get('success_rate', 0):.1f}%, "
            f"Total rounds: {race_result.get('rounds', 0)}"
        )

        metadata = {
            "source": "speed_race",
            "category": "performance",
            "task_name": task_name,
            "best_time": stats.get("best_time"),
            "avg_time": stats.get("avg_time"),
            "success_rate": stats.get("success_rate"),
            "timestamp": datetime.now().isoformat()
        }

        # Quality filter check
        if self.quality_filter:
            should_archive, score, reason = self.quality_filter.should_archive(content, metadata)
            if not should_archive:
                logger.debug(f"Filtered speed race (score={score:.2f}, reason={reason})")
                return None
            metadata["quality_score"] = score

        entry_id = self.store.store(content=content, metadata=metadata)

        return entry_id

    def archive_error(
        self,
        module_id: str,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None,
        solution: Optional[str] = None
    ) -> Optional[str]:
        """
        Archive error case

        Args:
            module_id: Module that encountered error
            error_type: Error type/class
            error_message: Error message
            context: Additional context
            solution: Optional solution description

        Returns:
            Entry ID or None if filtered
        """
        content_parts = [
            f"Error in {module_id}:",
            f"Type: {error_type}",
            f"Message: {error_message}"
        ]

        if solution:
            content_parts.append(f"Solution: {solution}")

        content = " | ".join(content_parts)

        metadata = {
            "source": "error_log",
            "category": "error",
            "module_id": module_id,
            "error_type": error_type,
            "timestamp": datetime.now().isoformat()
        }

        if context:
            metadata["context"] = json.dumps(context)

        if solution:
            metadata["has_solution"] = True

        # Quality filter check
        if self.quality_filter:
            should_archive, score, reason = self.quality_filter.should_archive(content, metadata)
            if not should_archive:
                logger.debug(f"Filtered error log (score={score:.2f}, reason={reason})")
                return None
            metadata["quality_score"] = score

        entry_id = self.store.store(content=content, metadata=metadata)

        return entry_id

    def archive_success_pattern(
        self,
        strategy_name: str,
        success_rate: float,
        description: str,
        use_cases: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Archive successful strategy pattern

        Args:
            strategy_name: Strategy name
            success_rate: Success rate (0-100)
            description: Strategy description
            use_cases: Optional list of use cases

        Returns:
            Entry ID or None if filtered
        """
        content = (
            f"Success Pattern - {strategy_name}: "
            f"{description} | "
            f"Success rate: {success_rate:.1f}%"
        )

        if use_cases:
            content += f" | Use cases: {', '.join(use_cases)}"

        metadata = {
            "source": "success_pattern",
            "category": "success",
            "strategy_name": strategy_name,
            "success_rate": success_rate,
            "timestamp": datetime.now().isoformat()
        }

        # Quality filter check
        if self.quality_filter:
            should_archive, score, reason = self.quality_filter.should_archive(content, metadata)
            if not should_archive:
                logger.debug(f"Filtered success pattern (score={score:.2f}, reason={reason})")
                return None
            metadata["quality_score"] = score

        entry_id = self.store.store(content=content, metadata=metadata)

        return entry_id

    def archive_module_improvement(
        self,
        module_id: str,
        version: str,
        changes: str,
        impact: str
    ) -> Optional[str]:
        """
        Archive module improvement/changelog

        Args:
            module_id: Module identifier
            version: Version number
            changes: Description of changes
            impact: Impact description

        Returns:
            Entry ID or None if filtered
        """
        content = (
            f"Module Improvement - {module_id} v{version}: "
            f"{changes} | Impact: {impact}"
        )

        metadata = {
            "source": "module_changelog",
            "category": "improvement",
            "module_id": module_id,
            "version": version,
            "timestamp": datetime.now().isoformat()
        }

        # Quality filter check
        if self.quality_filter:
            should_archive, score, reason = self.quality_filter.should_archive(content, metadata)
            if not should_archive:
                logger.debug(f"Filtered module improvement (score={score:.2f}, reason={reason})")
                return None
            metadata["quality_score"] = score

        entry_id = self.store.store(content=content, metadata=metadata)

        return entry_id

    def batch_archive(
        self,
        experiences: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Archive multiple experiences at once

        Args:
            experiences: List of experience dicts with 'type' and data

        Returns:
            List of entry IDs
        """
        entries = []

        for exp in experiences:
            exp_type = exp.get("type")

            if exp_type == "practice":
                entry_id = self.archive_practice_result(
                    website=exp["website"],
                    result=exp["result"],
                    analysis=exp.get("analysis")
                )
            elif exp_type == "race":
                entry_id = self.archive_speed_race(
                    task_name=exp["task_name"],
                    race_result=exp["result"]
                )
            elif exp_type == "error":
                entry_id = self.archive_error(
                    module_id=exp["module_id"],
                    error_type=exp["error_type"],
                    error_message=exp["error_message"],
                    context=exp.get("context"),
                    solution=exp.get("solution")
                )
            elif exp_type == "success":
                entry_id = self.archive_success_pattern(
                    strategy_name=exp["strategy_name"],
                    success_rate=exp["success_rate"],
                    description=exp["description"],
                    use_cases=exp.get("use_cases")
                )
            elif exp_type == "improvement":
                entry_id = self.archive_module_improvement(
                    module_id=exp["module_id"],
                    version=exp["version"],
                    changes=exp["changes"],
                    impact=exp["impact"]
                )
            else:
                continue

            entries.append({
                "content": f"Archived {exp_type} experience",
                "metadata": {"type": exp_type}
            })

        # Batch store
        ids = self.store.store_batch(entries)
        return ids

    def get_archive_stats(self) -> Dict[str, Any]:
        """
        Get archiving statistics

        Returns:
            Statistics dict
        """
        stats = self.store.get_stats()

        result = {
            "total_archived": stats.get("total_entries", 0),
            "collection": stats.get("collection"),
            "provider": stats.get("embedding_provider")
        }

        # Add quality filter stats if enabled
        if self.quality_filter:
            filter_stats = self.quality_filter.get_stats()
            result["quality_filter"] = filter_stats

        return result


class AutoArchiveTrigger:
    """
    Automatic archiving trigger on events
    """

    def __init__(self, archiver: ExperienceArchiver):
        """
        Initialize trigger

        Args:
            archiver: ExperienceArchiver instance
        """
        self.archiver = archiver
        self.enabled = True

    def on_practice_complete(
        self,
        website: str,
        result: Dict[str, Any],
        analysis: Optional[str] = None
    ):
        """
        Triggered when practice completes

        Args:
            website: Target website
            result: Practice result
            analysis: Optional analysis
        """
        if not self.enabled:
            return

        try:
            entry_id = self.archiver.archive_practice_result(
                website=website,
                result=result,
                analysis=analysis
            )
            return entry_id
        except Exception as e:
            logger.error(f"Auto-archive failed: {e}")
            return None

    def on_race_complete(self, task_name: str, result: Dict[str, Any]):
        """
        Triggered when race completes

        Args:
            task_name: Task name
            result: Race result
        """
        if not self.enabled:
            return

        try:
            entry_id = self.archiver.archive_speed_race(
                task_name=task_name,
                race_result=result
            )
            return entry_id
        except Exception as e:
            logger.error(f"Auto-archive failed: {e}")
            return None

    def on_module_error(
        self,
        module_id: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Triggered when module encounters error

        Args:
            module_id: Module identifier
            error: Exception instance
            context: Additional context
        """
        if not self.enabled:
            return

        try:
            entry_id = self.archiver.archive_error(
                module_id=module_id,
                error_type=type(error).__name__,
                error_message=str(error),
                context=context
            )
            return entry_id
        except Exception as e:
            logger.error(f"Auto-archive failed: {e}")
            return None

    def enable(self):
        """Enable auto-archiving"""
        self.enabled = True

    def disable(self):
        """Disable auto-archiving"""
        self.enabled = False
