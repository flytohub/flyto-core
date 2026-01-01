"""
HuggingFace Speech-to-Text Module

Transcribe audio to text using ASR models like Whisper.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from .constants import TaskType, ModuleDefaults, ModuleColors, ParamDefaults, Subcategory
from ._base import HuggingFaceTaskExecutor


logger = logging.getLogger(__name__)

# Task-specific executor
_executor = HuggingFaceTaskExecutor(TaskType.AUTOMATIC_SPEECH_RECOGNITION)


@register_module(
    module_id='huggingface.speech-to-text',
    version=ModuleDefaults.VERSION,
    category=ModuleDefaults.CATEGORY,
    subcategory=Subcategory.AUDIO,
    tags=['huggingface', 'audio', 'speech', 'transcription', 'asr', 'whisper'],
    label='Speech to Text',
    label_key='huggingface.speech_to_text.label',
    description='Transcribe audio to text using HuggingFace models (Whisper, etc.)',
    description_key='huggingface.speech_to_text.description',
    icon='Mic',
    color=ModuleColors.SPEECH_TO_TEXT,

    input_types=['audio', 'file'],
    output_types=['text'],
    can_connect_to=['string.*', 'file.*'],
    can_receive_from=['data.*', 'string.*', 'file.*', 'image.*', 'api.*', 'flow.*', 'start'],

    timeout=ModuleDefaults.AUDIO_TIMEOUT,
    retryable=ModuleDefaults.RETRYABLE,
    max_retries=ModuleDefaults.MAX_RETRIES,
    concurrent_safe=ModuleDefaults.CONCURRENT_SAFE,

    requires_credentials=ModuleDefaults.REQUIRES_CREDENTIALS,
    handles_sensitive_data=ModuleDefaults.HANDLES_SENSITIVE_DATA,

    # Schema-driven params
    params_schema=compose(
        presets.HF_MODEL_ID(task=TaskType.AUTOMATIC_SPEECH_RECOGNITION),
        presets.HF_AUDIO_PATH(),
        presets.HF_LANGUAGE(),
        presets.HF_RETURN_TIMESTAMPS(default=ParamDefaults.RETURN_TIMESTAMPS),
    ),
    output_schema={
        'text': {'type': 'string', 'description': 'Transcribed text'},
        'chunks': {'type': 'array', 'description': 'Timestamped chunks (if return_timestamps=true)'}
    },
    author=ModuleDefaults.AUTHOR,
    license=ModuleDefaults.LICENSE
)
async def huggingface_speech_to_text(context: Dict[str, Any]) -> Dict[str, Any]:
    """Transcribe audio to text using HuggingFace ASR models"""
    params = context['params']
    model_id = params['model_id']
    audio_path = params['audio_path']
    language = params.get('language')
    return_timestamps = params.get('return_timestamps', ParamDefaults.RETURN_TIMESTAMPS)

    # Build execution kwargs
    exec_kwargs = {'return_timestamps': return_timestamps}
    if language:
        exec_kwargs['generate_kwargs'] = {'language': language}

    # Execute task - handles file path vs bytes automatically
    exec_result = await _executor.execute_with_file(
        model_id=model_id,
        file_path=audio_path,
        file_type="Audio",
        **exec_kwargs
    )

    # Normalize output
    raw = exec_result['raw_result']
    if isinstance(raw, dict):
        text = raw.get('text', '')
        chunks = raw.get('chunks', [])
    else:
        text = str(raw)
        chunks = []

    logger.info(f"Transcribed {len(text)} characters from {audio_path}")

    return {
        'ok': True,
        'text': text,
        'chunks': chunks if return_timestamps else [],
        'model_id': model_id,
        'runtime': exec_result['runtime']
    }
