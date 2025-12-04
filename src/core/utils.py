"""
Core Utilities - Shared utility functions

This module contains reusable utility functions to reduce code duplication.
"""
import os
import logging
from typing import Any, Dict, Optional, TypeVar, Callable
from functools import wraps

from .constants import EnvVars, ErrorMessages


logger = logging.getLogger(__name__)

T = TypeVar('T')


# =============================================================================
# API Key Validation
# =============================================================================

def get_api_key(env_var: str, required: bool = True) -> Optional[str]:
    """
    Get API key from environment variable.

    Args:
        env_var: Environment variable name
        required: If True, raise error when key is missing

    Returns:
        API key value or None

    Raises:
        ValueError: If required=True and key is missing
    """
    value = os.environ.get(env_var)

    if required and not value:
        error_msg = ErrorMessages.format(
            ErrorMessages.API_KEY_MISSING,
            env_var=env_var
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    return value


def validate_api_key(env_var: str) -> str:
    """
    Validate and return API key.

    Args:
        env_var: Environment variable name

    Returns:
        API key value

    Raises:
        ValueError: If key is missing
    """
    return get_api_key(env_var, required=True)


# =============================================================================
# Parameter Validation
# =============================================================================

def validate_required_param(
    params: Dict[str, Any],
    param_name: str,
    param_type: Optional[type] = None
) -> Any:
    """
    Validate a required parameter exists and optionally check its type.

    Args:
        params: Parameters dictionary
        param_name: Name of the required parameter
        param_type: Expected type (optional)

    Returns:
        Parameter value

    Raises:
        ValueError: If parameter is missing or wrong type
    """
    if param_name not in params:
        raise ValueError(
            ErrorMessages.format(
                ErrorMessages.MISSING_REQUIRED_PARAM,
                param_name=param_name
            )
        )

    value = params[param_name]

    if param_type is not None and not isinstance(value, param_type):
        raise ValueError(
            ErrorMessages.format(
                ErrorMessages.INVALID_PARAM_TYPE,
                param_name=param_name,
                expected=param_type.__name__,
                actual=type(value).__name__
            )
        )

    return value


def get_param(
    params: Dict[str, Any],
    param_name: str,
    default: T = None,
    param_type: Optional[type] = None
) -> T:
    """
    Get a parameter with optional default and type checking.

    Args:
        params: Parameters dictionary
        param_name: Name of the parameter
        default: Default value if not present
        param_type: Expected type (optional)

    Returns:
        Parameter value or default
    """
    value = params.get(param_name, default)

    if value is not None and param_type is not None:
        if not isinstance(value, param_type):
            raise ValueError(
                ErrorMessages.format(
                    ErrorMessages.INVALID_PARAM_TYPE,
                    param_name=param_name,
                    expected=param_type.__name__,
                    actual=type(value).__name__
                )
            )

    return value


# =============================================================================
# Type Conversion
# =============================================================================

def auto_convert_type(value: str) -> Any:
    """
    Automatically convert string to appropriate type.

    Args:
        value: String value to convert

    Returns:
        Converted value (bool, int, float, or str)
    """
    if not isinstance(value, str):
        return value

    # Boolean
    lower_value = value.lower()
    if lower_value in ('true', 'yes', 'y', '1'):
        return True
    if lower_value in ('false', 'no', 'n', '0'):
        return False

    # Number
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    # String (default)
    return value


# =============================================================================
# Execution Helpers
# =============================================================================

def safe_execute(func: Callable[..., T], *args, **kwargs) -> Optional[T]:
    """
    Safely execute a function and return None on error.

    Args:
        func: Function to execute
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Function result or None on error
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Safe execute failed: {e}")
        return None


def ensure_list(value: Any) -> list:
    """
    Ensure value is a list.

    Args:
        value: Any value

    Returns:
        List containing the value(s)
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def ensure_dict(value: Any) -> dict:
    """
    Ensure value is a dictionary.

    Args:
        value: Any value

    Returns:
        Dictionary
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {}


# =============================================================================
# String Helpers
# =============================================================================

def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate string to maximum length.

    Args:
        s: String to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


# =============================================================================
# Logging Helpers
# =============================================================================

def log_execution(module_id: str):
    """
    Decorator to log module execution.

    Args:
        module_id: Module identifier
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger.info(f"Executing module: {module_id}")
            try:
                result = await func(*args, **kwargs)
                logger.info(f"Module {module_id} completed successfully")
                return result
            except Exception as e:
                logger.error(f"Module {module_id} failed: {e}")
                raise
        return wrapper
    return decorator
