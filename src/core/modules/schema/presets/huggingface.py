"""
HuggingFace Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from .. import validators


def HF_MODEL_ID(
    *,
    task: str,
    key: str = "model_id",
    label: str = "Model",
    label_key: str = "schema.field.hf_model_id",
) -> Dict[str, Dict[str, Any]]:
    """HuggingFace installed model selector with task filter."""
    return field(
        key,
        type="installed_model",
        label=label,
        label_key=label_key,
        required=True,
        task=task,
    )


def HF_PROMPT(
    *,
    key: str = "prompt",
    required: bool = True,
    label: str = "Prompt",
    label_key: str = "schema.field.hf_prompt",
) -> Dict[str, Dict[str, Any]]:
    """Text prompt for LLM generation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        multiline=True,
    )


def HF_TEXT_INPUT(
    *,
    key: str = "text",
    required: bool = True,
    label: str = "Text",
    label_key: str = "schema.field.hf_text_input",
) -> Dict[str, Dict[str, Any]]:
    """Text input for HuggingFace models."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        multiline=True,
    )


def HF_MAX_NEW_TOKENS(
    *,
    key: str = "max_new_tokens",
    default: int = 256,
    label: str = "Max Tokens",
    label_key: str = "schema.field.hf_max_new_tokens",
) -> Dict[str, Dict[str, Any]]:
    """Maximum new tokens to generate."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_TEMPERATURE(
    *,
    key: str = "temperature",
    default: float = 0.7,
    label: str = "Temperature",
    label_key: str = "schema.field.hf_temperature",
) -> Dict[str, Dict[str, Any]]:
    """Sampling temperature for generation."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_TOP_P(
    *,
    key: str = "top_p",
    default: float = 0.95,
    label: str = "Top P",
    label_key: str = "schema.field.hf_top_p",
) -> Dict[str, Dict[str, Any]]:
    """Nucleus sampling probability."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_DO_SAMPLE(
    *,
    key: str = "do_sample",
    default: bool = True,
    label: str = "Do Sample",
    label_key: str = "schema.field.hf_do_sample",
) -> Dict[str, Dict[str, Any]]:
    """Enable sampling for generation."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_MAX_LENGTH(
    *,
    key: str = "max_length",
    default: int = 130,
    label: str = "Max Length",
    label_key: str = "schema.field.hf_max_length",
) -> Dict[str, Dict[str, Any]]:
    """Maximum output length."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_MIN_LENGTH(
    *,
    key: str = "min_length",
    default: int = 30,
    label: str = "Min Length",
    label_key: str = "schema.field.hf_min_length",
) -> Dict[str, Dict[str, Any]]:
    """Minimum output length."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_TOP_K(
    *,
    key: str = "top_k",
    default: int = 5,
    label: str = "Top K",
    label_key: str = "schema.field.hf_top_k",
) -> Dict[str, Dict[str, Any]]:
    """Number of top results to return."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_SOURCE_LANG(
    *,
    key: str = "source_lang",
    label: str = "Source Language",
    label_key: str = "schema.field.hf_source_lang",
) -> Dict[str, Dict[str, Any]]:
    """Source language code for translation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
    )


def HF_TARGET_LANG(
    *,
    key: str = "target_lang",
    label: str = "Target Language",
    label_key: str = "schema.field.hf_target_lang",
) -> Dict[str, Dict[str, Any]]:
    """Target language code for translation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
    )


def HF_AUDIO_PATH(
    *,
    key: str = "audio_path",
    label: str = "Audio File",
    label_key: str = "schema.field.hf_audio_path",
) -> Dict[str, Dict[str, Any]]:
    """Path to audio file."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=True,
    )


def HF_IMAGE_PATH(
    *,
    key: str = "image_path",
    label: str = "Image Path",
    label_key: str = "schema.field.hf_image_path",
) -> Dict[str, Dict[str, Any]]:
    """Path to image file."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=True,
    )


def HF_LANGUAGE(
    *,
    key: str = "language",
    label: str = "Language",
    label_key: str = "schema.field.hf_language",
) -> Dict[str, Dict[str, Any]]:
    """Language code for speech recognition."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Language code (e.g., "en", "zh"). Leave empty for auto-detection.',
    )


def HF_RETURN_TIMESTAMPS(
    *,
    key: str = "return_timestamps",
    default: bool = False,
    label: str = "Return Timestamps",
    label_key: str = "schema.field.hf_return_timestamps",
) -> Dict[str, Dict[str, Any]]:
    """Include timestamps in output."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
    )


def HF_NORMALIZE(
    *,
    key: str = "normalize",
    default: bool = True,
    label: str = "Normalize",
    label_key: str = "schema.field.hf_normalize",
) -> Dict[str, Dict[str, Any]]:
    """Normalize embedding vectors."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
    )

