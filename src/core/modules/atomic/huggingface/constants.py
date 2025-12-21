"""
HuggingFace Module Constants

Single source of truth for all HuggingFace-related constants.
Prevents hardcoding throughout the codebase.
"""
from pathlib import Path
from typing import Dict, Any


# =============================================================================
# File Paths
# =============================================================================

FLYTO_DATA_DIR = Path.home() / ".flyto"
INSTALLED_MODELS_FILE = "installed_models.json"
INSTALLED_MODELS_PATH = FLYTO_DATA_DIR / INSTALLED_MODELS_FILE


# =============================================================================
# Environment Variables
# =============================================================================

ENV_OFFLINE_MODE = "FLYTO_OFFLINE_MODE"
ENV_HF_TOKEN = "HF_TOKEN"
ENV_HF_TOKEN_ALT = "HUGGINGFACE_TOKEN"


# =============================================================================
# Download Status
# =============================================================================

class DownloadStatus:
    """Model download status constants"""
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    FAILED = "failed"


# =============================================================================
# HuggingFace Task Types
# =============================================================================

class TaskType:
    """HuggingFace pipeline task type constants"""
    # Audio
    AUTOMATIC_SPEECH_RECOGNITION = "automatic-speech-recognition"
    TEXT_TO_SPEECH = "text-to-speech"
    AUDIO_CLASSIFICATION = "audio-classification"

    # Text
    TEXT_GENERATION = "text-generation"
    TEXT2TEXT_GENERATION = "text2text-generation"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    TEXT_CLASSIFICATION = "text-classification"
    QUESTION_ANSWERING = "question-answering"
    FILL_MASK = "fill-mask"
    FEATURE_EXTRACTION = "feature-extraction"

    # Vision
    IMAGE_CLASSIFICATION = "image-classification"
    OBJECT_DETECTION = "object-detection"
    IMAGE_SEGMENTATION = "image-segmentation"
    IMAGE_TO_TEXT = "image-to-text"

    # Multimodal
    VISUAL_QUESTION_ANSWERING = "visual-question-answering"
    DOCUMENT_QUESTION_ANSWERING = "document-question-answering"
    ZERO_SHOT_CLASSIFICATION = "zero-shot-classification"


# =============================================================================
# Task to API Method Mapping
# =============================================================================

# Maps HuggingFace task types to InferenceClient method names
TASK_API_METHODS: Dict[str, str] = {
    TaskType.AUTOMATIC_SPEECH_RECOGNITION: "automatic_speech_recognition",
    TaskType.TEXT_GENERATION: "text_generation",
    TaskType.SUMMARIZATION: "summarization",
    TaskType.TRANSLATION: "translation",
    TaskType.TEXT_CLASSIFICATION: "text_classification",
    TaskType.FEATURE_EXTRACTION: "feature_extraction",
    TaskType.IMAGE_CLASSIFICATION: "image_classification",
    TaskType.QUESTION_ANSWERING: "question_answering",
    TaskType.FILL_MASK: "fill_mask",
    TaskType.TEXT_TO_SPEECH: "text_to_speech",
    TaskType.AUDIO_CLASSIFICATION: "audio_classification",
    TaskType.OBJECT_DETECTION: "object_detection",
    TaskType.IMAGE_SEGMENTATION: "image_segmentation",
    TaskType.IMAGE_TO_TEXT: "image_to_text",
    TaskType.VISUAL_QUESTION_ANSWERING: "visual_question_answering",
    TaskType.DOCUMENT_QUESTION_ANSWERING: "document_question_answering",
    TaskType.ZERO_SHOT_CLASSIFICATION: "zero_shot_classification",
}


# =============================================================================
# Module Metadata Defaults
# =============================================================================

class ModuleDefaults:
    """Default values for module metadata"""
    VERSION = "1.0.0"
    TIMEOUT = 120
    AUDIO_TIMEOUT = 300
    MAX_RETRIES = 2
    CATEGORY = "huggingface"
    AUTHOR = "Flyto2 Team"
    LICENSE = "MIT"
    RETRYABLE = True
    CONCURRENT_SAFE = True
    REQUIRES_CREDENTIALS = False
    HANDLES_SENSITIVE_DATA = False


class Subcategory:
    """Module subcategory constants"""
    TEXT = "text"
    AUDIO = "audio"
    VISION = "vision"


# =============================================================================
# Module Colors (UI theme colors for each task type)
# =============================================================================

class ModuleColors:
    """UI colors for different task modules"""
    # Audio tasks
    SPEECH_TO_TEXT = "#8B5CF6"  # Purple
    TEXT_TO_SPEECH = "#8B5CF6"
    AUDIO_CLASSIFICATION = "#8B5CF6"

    # Text generation tasks
    TEXT_GENERATION = "#8B5CF6"  # Purple
    SUMMARIZATION = "#10B981"    # Green
    TRANSLATION = "#3B82F6"      # Blue

    # Classification tasks
    TEXT_CLASSIFICATION = "#F59E0B"   # Amber
    IMAGE_CLASSIFICATION = "#EC4899"  # Pink

    # Embedding/Vector tasks
    EMBEDDING = "#06B6D4"  # Cyan


# =============================================================================
# Parameter Default Values
# =============================================================================

class ParamDefaults:
    """Default values for module parameters"""
    # Text Generation
    MAX_NEW_TOKENS = 256
    TEMPERATURE = 0.7
    TOP_P = 0.95
    DO_SAMPLE = True

    # Summarization
    SUMMARY_MAX_LENGTH = 130
    SUMMARY_MIN_LENGTH = 30

    # Classification
    TOP_K = 5

    # Speech to Text
    RETURN_TIMESTAMPS = False

    # Embedding
    NORMALIZE = True


# =============================================================================
# Result Keys (for parsing HuggingFace responses)
# =============================================================================

class ResultKeys:
    """Keys used in HuggingFace result parsing"""
    # Text result keys (checked in order)
    TEXT_RESULT_KEYS = ('generated_text', 'summary_text', 'translation_text', 'text')

    # Classification result keys
    LABEL = 'label'
    SCORE = 'score'


# =============================================================================
# Error Messages
# =============================================================================

class ErrorMessages:
    """Standardized error messages"""
    MODEL_NOT_DOWNLOADED = "Model '{model_id}' is not downloaded. Offline mode requires local models."
    HF_TOKEN_REQUIRED = "HF_TOKEN environment variable is required for Inference API"
    FILE_NOT_FOUND = "{file_type} file not found: {path}"
    TRANSFORMERS_REQUIRED = "transformers is required for local HuggingFace execution. Install with: pip install transformers"
    HF_HUB_REQUIRED = "huggingface_hub is required for Inference API. Install with: pip install huggingface_hub"

    @classmethod
    def format(cls, template: str, **kwargs) -> str:
        """Format an error message with parameters"""
        return template.format(**kwargs)
