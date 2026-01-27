"""
HuggingFace Task Modules

Provides core modules for executing HuggingFace tasks with installed models.
Each module handles a specific task type (e.g., speech-to-text, text-generation).

Runtime Policy:
- Offline mode → require local execution (error if model not downloaded)
- User preference=LOCAL → require local (error if not downloaded)
- Model downloaded → prefer local
- Otherwise → use HuggingFace Inference API (requires HF_TOKEN)

Note: These modules only register if 'transformers' package is installed.
"""
import importlib.util

# Only register HuggingFace modules if transformers is installed
_has_transformers = importlib.util.find_spec("transformers") is not None

if _has_transformers:
    try:
        from .speech_to_text import *
    except ImportError:
        pass
    try:
        from .text_generation import *
    except ImportError:
        pass
    try:
        from .summarization import *
    except ImportError:
        pass
    try:
        from .translation import *
    except ImportError:
        pass
    try:
        from .text_classification import *
    except ImportError:
        pass
    try:
        from .image_classification import *
    except ImportError:
        pass
    try:
        from .embedding import *
    except ImportError:
        pass
