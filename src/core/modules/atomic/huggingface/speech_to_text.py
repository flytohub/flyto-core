"""
HuggingFace Speech-to-Text Module

Transcribe audio to text using ASR models like Whisper.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
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

    timeout=ModuleDefaults.AUDIO_TIMEOUT,
    retryable=ModuleDefaults.RETRYABLE,
    max_retries=ModuleDefaults.MAX_RETRIES,
    concurrent_safe=ModuleDefaults.CONCURRENT_SAFE,

    requires_credentials=ModuleDefaults.REQUIRES_CREDENTIALS,
    handles_sensitive_data=ModuleDefaults.HANDLES_SENSITIVE_DATA,

    params_schema={
        'model_id': {
            'type': 'installed_model',
            'label': 'Model',
            'label_key': 'huggingface.speech_to_text.params.model_id.label',
            'description': 'HuggingFace model to use',
            'description_key': 'huggingface.speech_to_text.params.model_id.description',
            'required': True,
            'task': TaskType.AUTOMATIC_SPEECH_RECOGNITION
        },
        'audio_path': {
            'type': 'string',
            'label': 'Audio File',
            'label_key': 'huggingface.speech_to_text.params.audio_path.label',
            'description': 'Path to audio file (wav, mp3, flac, etc.)',
            'description_key': 'huggingface.speech_to_text.params.audio_path.description',
            'required': True
        },
        'language': {
            'type': 'string',
            'label': 'Language',
            'label_key': 'huggingface.speech_to_text.params.language.label',
            'description': 'Language code (e.g., "en", "zh", "ja"). Leave empty for auto-detection.',
            'description_key': 'huggingface.speech_to_text.params.language.description',
            'required': False
        },
        'return_timestamps': {
            'type': 'boolean',
            'label': 'Return Timestamps',
            'label_key': 'huggingface.speech_to_text.params.return_timestamps.label',
            'description': 'Include word/chunk timestamps in output',
            'description_key': 'huggingface.speech_to_text.params.return_timestamps.description',
            'required': False,
            'default': ParamDefaults.RETURN_TIMESTAMPS
        }
    },
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
