"""
HuggingFace Runtime Policy

Provides runtime resolution for HuggingFace task modules.
Determines whether to execute locally or via Inference API.

This module bridges the gap between Core and the UI backend's
InstalledModelProvider service.
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional
from dataclasses import dataclass
from enum import Enum

from .constants import (
    INSTALLED_MODELS_PATH,
    ENV_OFFLINE_MODE,
    ENV_HF_TOKEN,
    ENV_HF_TOKEN_ALT,
    DownloadStatus,
    TASK_API_METHODS,
    ErrorMessages,
)


logger = logging.getLogger(__name__)


class RuntimeMode(Enum):
    """Execution mode for HuggingFace models"""
    LOCAL = "local"
    INFERENCE_API = "inference_api"


@dataclass
class RuntimePolicy:
    """Result of runtime policy resolution"""
    mode: RuntimeMode
    model_id: str
    local_path: Optional[str] = None
    can_execute: bool = True
    error: Optional[str] = None
    requires_token: bool = False


class HuggingFaceRuntime:
    """
    HuggingFace Runtime Manager

    Resolves execution policy based on:
    1. Offline mode (requires local)
    2. User preference
    3. Model download status
    """

    @classmethod
    def get_installed_model(cls, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get installed model info from storage.

        Args:
            model_id: HuggingFace model ID (e.g., "openai/whisper-large-v3")

        Returns:
            Model info dict or None if not found
        """
        try:
            if not INSTALLED_MODELS_PATH.exists():
                return None

            with open(INSTALLED_MODELS_PATH, 'r') as f:
                data = json.load(f)

            models = data.get('models', [])
            for model in models:
                if model.get('model_id') == model_id:
                    return model

            return None

        except Exception as e:
            logger.warning(f"Failed to read installed models: {e}")
            return None

    @classmethod
    def is_offline_mode(cls) -> bool:
        """Check if running in offline mode"""
        return os.environ.get(ENV_OFFLINE_MODE, '').lower() == 'true'

    @classmethod
    def get_hf_token(cls) -> Optional[str]:
        """Get HuggingFace token from environment"""
        return os.environ.get(ENV_HF_TOKEN) or os.environ.get(ENV_HF_TOKEN_ALT)

    @classmethod
    def resolve_policy(
        cls,
        model_id: str,
        prefer_local: bool = True
    ) -> RuntimePolicy:
        """
        Resolve runtime execution policy for a model.

        Decision order:
        1. offline_mode=true → require LOCAL (error if not downloaded)
        2. prefer_local=true and downloaded → LOCAL
        3. downloaded → LOCAL
        4. else → INFERENCE_API (requires HF_TOKEN)

        Args:
            model_id: HuggingFace model ID
            prefer_local: Whether to prefer local execution

        Returns:
            RuntimePolicy with execution details
        """
        model_info = cls.get_installed_model(model_id)
        is_downloaded = (
            model_info and
            model_info.get('download_status') == DownloadStatus.DOWNLOADED
        )
        local_path = model_info.get('local_path') if model_info else None
        offline_mode = cls.is_offline_mode()

        # Offline mode: require local
        if offline_mode:
            if not is_downloaded:
                return RuntimePolicy(
                    mode=RuntimeMode.LOCAL,
                    model_id=model_id,
                    can_execute=False,
                    error=ErrorMessages.format(
                        ErrorMessages.MODEL_NOT_DOWNLOADED,
                        model_id=model_id
                    )
                )
            return RuntimePolicy(
                mode=RuntimeMode.LOCAL,
                model_id=model_id,
                local_path=local_path,
                can_execute=True
            )

        # Downloaded: prefer local
        if is_downloaded and prefer_local:
            return RuntimePolicy(
                mode=RuntimeMode.LOCAL,
                model_id=model_id,
                local_path=local_path,
                can_execute=True
            )

        # Fallback to Inference API
        hf_token = cls.get_hf_token()
        if not hf_token:
            return RuntimePolicy(
                mode=RuntimeMode.INFERENCE_API,
                model_id=model_id,
                can_execute=False,
                requires_token=True,
                error=ErrorMessages.HF_TOKEN_REQUIRED
            )

        return RuntimePolicy(
            mode=RuntimeMode.INFERENCE_API,
            model_id=model_id,
            can_execute=True,
            requires_token=True
        )


async def run_local_pipeline(
    task: str,
    model_path: str,
    inputs: Any,
    **kwargs
) -> Any:
    """
    Run a HuggingFace pipeline locally.

    Args:
        task: Pipeline task type (e.g., "automatic-speech-recognition")
        model_path: Local path to the model
        inputs: Pipeline input
        **kwargs: Additional pipeline arguments

    Returns:
        Pipeline output
    """
    def _run():
        try:
            from transformers import pipeline
        except ImportError:
            raise ImportError(ErrorMessages.TRANSFORMERS_REQUIRED)

        pipe = pipeline(task, model=model_path, **kwargs)
        return pipe(inputs)

    return await asyncio.to_thread(_run)


async def run_inference_api(
    model_id: str,
    inputs: Any,
    task: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Run inference via HuggingFace Inference API.

    Args:
        model_id: HuggingFace model ID
        inputs: API input
        task: Optional task hint
        **kwargs: Additional API parameters

    Returns:
        API response
    """
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        raise ImportError(ErrorMessages.HF_HUB_REQUIRED)

    hf_token = HuggingFaceRuntime.get_hf_token()
    if not hf_token:
        raise ValueError(ErrorMessages.HF_TOKEN_REQUIRED)

    client = InferenceClient(token=hf_token)

    # Look up the API method from the mapping
    api_method_name = TASK_API_METHODS.get(task) if task else None

    if api_method_name and hasattr(client, api_method_name):
        api_method = getattr(client, api_method_name)
        return await asyncio.to_thread(
            api_method,
            inputs,
            model=model_id,
            **kwargs
        )

    # Fallback: generic inference via POST
    return await asyncio.to_thread(
        client.post,
        json={"inputs": inputs, **kwargs},
        model=model_id
    )
