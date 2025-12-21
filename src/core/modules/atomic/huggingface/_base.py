"""
HuggingFace Base Module

Provides a base class for all HuggingFace task modules.
Eliminates code duplication and enforces consistent behavior.
"""
import logging
import os
from abc import abstractmethod
from typing import Any, Dict, Optional

from .constants import TaskType, ModuleDefaults, ErrorMessages, ResultKeys
from ._runtime import HuggingFaceRuntime, RuntimeMode, run_local_pipeline, run_inference_api


logger = logging.getLogger(__name__)


class HuggingFaceTaskExecutor:
    """
    Base executor for HuggingFace tasks.

    Provides common execution logic that can be reused across task modules.
    Each task module should use this executor rather than duplicating logic.
    """

    def __init__(self, task_type: str):
        """
        Initialize executor for a specific task type.

        Args:
            task_type: HuggingFace pipeline task type (use TaskType constants)
        """
        self.task_type = task_type

    async def execute(
        self,
        model_id: str,
        inputs: Any,
        prefer_local: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute the HuggingFace task.

        Args:
            model_id: HuggingFace model ID
            inputs: Task-specific input
            prefer_local: Whether to prefer local execution
            **kwargs: Additional task-specific parameters

        Returns:
            Execution result dict
        """
        # Resolve runtime policy
        policy = HuggingFaceRuntime.resolve_policy(model_id, prefer_local)

        if not policy.can_execute:
            raise RuntimeError(policy.error)

        logger.info(
            f"Running {self.task_type} with model {model_id} "
            f"in {policy.mode.value} mode"
        )

        # Execute based on policy
        if policy.mode == RuntimeMode.LOCAL:
            result = await self._execute_local(
                model_path=policy.local_path or model_id,
                inputs=inputs,
                **kwargs
            )
        else:
            result = await self._execute_api(
                model_id=model_id,
                inputs=inputs,
                **kwargs
            )

        return {
            'raw_result': result,
            'model_id': model_id,
            'runtime': policy.mode.value
        }

    async def execute_with_file(
        self,
        model_id: str,
        file_path: str,
        file_type: str = "File",
        prefer_local: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute task with file input.

        Handles the difference between local (file path) and API (file bytes) execution.
        This eliminates duplicated logic in modules like speech_to_text and image_classification.

        Args:
            model_id: HuggingFace model ID
            file_path: Path to the input file
            file_type: Type description for error messages (e.g., "Audio", "Image")
            prefer_local: Whether to prefer local execution
            **kwargs: Additional task-specific parameters

        Returns:
            Execution result dict
        """
        # Validate file exists
        validate_file_exists(file_path, file_type)

        # Resolve runtime policy
        policy = HuggingFaceRuntime.resolve_policy(model_id, prefer_local)

        if not policy.can_execute:
            raise RuntimeError(policy.error)

        logger.info(
            f"Running {self.task_type} with model {model_id} "
            f"in {policy.mode.value} mode"
        )

        # Execute based on policy with appropriate input format
        if policy.mode == RuntimeMode.LOCAL:
            # Local execution: use file path directly
            result = await self._execute_local(
                model_path=policy.local_path or model_id,
                inputs=file_path,
                **kwargs
            )
        else:
            # API execution: read file bytes
            file_bytes = read_file_bytes(file_path)
            result = await self._execute_api(
                model_id=model_id,
                inputs=file_bytes,
                **kwargs
            )

        return {
            'raw_result': result,
            'model_id': model_id,
            'runtime': policy.mode.value
        }

    async def _execute_local(
        self,
        model_path: str,
        inputs: Any,
        **kwargs
    ) -> Any:
        """Execute task locally using transformers pipeline"""
        return await run_local_pipeline(
            task=self.task_type,
            model_path=model_path,
            inputs=inputs,
            **kwargs
        )

    async def _execute_api(
        self,
        model_id: str,
        inputs: Any,
        **kwargs
    ) -> Any:
        """Execute task via Inference API"""
        return await run_inference_api(
            model_id=model_id,
            inputs=inputs,
            task=self.task_type,
            **kwargs
        )


def validate_file_exists(file_path: str, file_type: str = "File") -> None:
    """
    Validate that a file exists.

    Args:
        file_path: Path to validate
        file_type: Type description for error message

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            ErrorMessages.format(
                ErrorMessages.FILE_NOT_FOUND,
                file_type=file_type,
                path=file_path
            )
        )


def read_file_bytes(file_path: str) -> bytes:
    """
    Read file contents as bytes.

    Args:
        file_path: Path to file

    Returns:
        File contents as bytes
    """
    with open(file_path, 'rb') as f:
        return f.read()


def normalize_text_result(result: Any) -> str:
    """
    Normalize various result formats to a text string.

    Args:
        result: Raw result from HuggingFace

    Returns:
        Normalized text string
    """
    if isinstance(result, list) and len(result) > 0:
        first = result[0]
        if isinstance(first, dict):
            # Check common keys
            for key in ResultKeys.TEXT_RESULT_KEYS:
                if key in first:
                    return first[key]
        return str(first)
    elif isinstance(result, dict):
        for key in ResultKeys.TEXT_RESULT_KEYS:
            if key in result:
                return result[key]
    return str(result) if result else ''


def normalize_classification_result(result: Any) -> Dict[str, Any]:
    """
    Normalize classification result to standard format.

    Args:
        result: Raw classification result

    Returns:
        Dict with labels, top_label, top_score
    """
    labels = []

    if isinstance(result, list):
        if len(result) > 0 and isinstance(result[0], list):
            labels = result[0]  # Nested list format
        else:
            labels = result  # Flat list format
    elif isinstance(result, dict):
        labels = [result]

    top_label = labels[0][ResultKeys.LABEL] if labels else ''
    top_score = labels[0][ResultKeys.SCORE] if labels else 0.0

    return {
        'labels': labels,
        'top_label': top_label,
        'top_score': top_score
    }
