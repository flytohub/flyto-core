"""
Core Utilities - Shared utility functions

This module contains reusable utility functions to reduce code duplication.
"""
import os
import socket
import ipaddress
import logging
from typing import Any, Dict, Optional, TypeVar, Callable
from urllib.parse import urlparse
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


# =============================================================================
# SSRF Protection
# =============================================================================

# Private IP ranges that should be blocked
PRIVATE_IP_RANGES = [
    ipaddress.ip_network('10.0.0.0/8'),        # RFC 1918 Class A
    ipaddress.ip_network('172.16.0.0/12'),     # RFC 1918 Class B
    ipaddress.ip_network('192.168.0.0/16'),    # RFC 1918 Class C
    ipaddress.ip_network('127.0.0.0/8'),       # Loopback
    ipaddress.ip_network('169.254.0.0/16'),    # Link-local
    ipaddress.ip_network('0.0.0.0/8'),         # Current network
    ipaddress.ip_network('100.64.0.0/10'),     # Shared address space (CGN)
    ipaddress.ip_network('192.0.0.0/24'),      # IETF Protocol Assignments
    ipaddress.ip_network('192.0.2.0/24'),      # TEST-NET-1
    ipaddress.ip_network('198.51.100.0/24'),   # TEST-NET-2
    ipaddress.ip_network('203.0.113.0/24'),    # TEST-NET-3
    ipaddress.ip_network('224.0.0.0/4'),       # Multicast
    ipaddress.ip_network('240.0.0.0/4'),       # Reserved
    ipaddress.ip_network('255.255.255.255/32'), # Broadcast
    # IPv6
    ipaddress.ip_network('::1/128'),           # Loopback
    ipaddress.ip_network('fc00::/7'),          # Unique local
    ipaddress.ip_network('fe80::/10'),         # Link-local
    ipaddress.ip_network('ff00::/8'),          # Multicast
]

# Blocked hostnames
BLOCKED_HOSTNAMES = {
    'localhost',
    'localhost.localdomain',
    '127.0.0.1',
    '::1',
    '0.0.0.0',
    'metadata.google.internal',      # GCP metadata
    '169.254.169.254',               # AWS/Azure/GCP metadata
    'metadata.internal',
}


class SSRFError(ValueError):
    """Raised when a URL targets a blocked internal resource."""
    pass


def is_private_ip(ip_str: str) -> bool:
    """
    Check if an IP address is in a private/internal range.

    Args:
        ip_str: IP address string

    Returns:
        True if the IP is private/internal
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in PRIVATE_IP_RANGES:
            if ip in network:
                return True
        return False
    except ValueError:
        # Invalid IP, treat as potentially unsafe
        return True


def validate_url_ssrf(
    url: str,
    allow_private: bool = False,
    allowed_hosts: Optional[list] = None,
) -> str:
    """
    Validate a URL for SSRF attacks.

    This function checks if a URL targets internal/private resources
    and raises SSRFError if so. Supports allowlist for controlled private access.

    Security Modes:
    - Default (production): Block private IPs, localhost, metadata endpoints
    - allow_private=True: Allow all (for development/self-hosted)
    - allowed_hosts=['example.internal']: Allow only specified hosts

    Args:
        url: URL to validate
        allow_private: If True, allow private IPs (for dev/self-hosted)
        allowed_hosts: List of allowed hostnames/IPs for private access

    Returns:
        The validated URL

    Raises:
        SSRFError: If the URL targets a blocked resource
        ValueError: If the URL is malformed

    Example:
        # Block all private (production default)
        validate_url_ssrf("http://internal.corp.com")  # Raises SSRFError

        # Allow specific hosts (controlled access)
        validate_url_ssrf("http://internal.corp.com", allowed_hosts=["internal.corp.com"])

        # Allow all (development)
        validate_url_ssrf("http://localhost:8080", allow_private=True)
    """
    # Development/self-hosted mode - allow all
    if allow_private:
        return url

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}")

    # Check scheme
    if parsed.scheme not in ('http', 'https'):
        raise SSRFError(f"URL scheme not allowed: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL missing hostname")

    hostname_lower = hostname.lower()

    # Check if host is in allowlist (controlled private access)
    if allowed_hosts:
        for allowed in allowed_hosts:
            if hostname_lower == allowed.lower():
                logger.debug(f"SSRF: Allowing {hostname} (in allowlist)")
                return url
            # Support wildcard: *.example.com
            if allowed.startswith('*.') and hostname_lower.endswith(allowed[1:].lower()):
                logger.debug(f"SSRF: Allowing {hostname} (matches {allowed})")
                return url

    # Block known dangerous hostnames (metadata endpoints, etc.)
    if hostname_lower in BLOCKED_HOSTNAMES:
        raise SSRFError(f"Hostname blocked: {hostname}")

    # Resolve hostname and check IP
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        for family, _, _, _, sockaddr in addr_info:
            ip = sockaddr[0]
            if is_private_ip(ip):
                raise SSRFError(
                    f"URL resolves to private IP: {hostname} -> {ip}. "
                    f"Use 'allowed_hosts' to enable controlled private access."
                )
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for {hostname}: {e}")

    return url


def get_ssrf_config() -> dict:
    """
    Get SSRF configuration from environment.

    Environment variables:
    - FLYTO_ALLOW_PRIVATE_NETWORK: true/false (default: false)
    - FLYTO_ALLOWED_HOSTS: comma-separated list of allowed hosts

    Returns:
        dict with allow_private and allowed_hosts
    """
    allow_private = os.environ.get('FLYTO_ALLOW_PRIVATE_NETWORK', 'false').lower() == 'true'
    allowed_hosts_str = os.environ.get('FLYTO_ALLOWED_HOSTS', '')
    allowed_hosts = [h.strip() for h in allowed_hosts_str.split(',') if h.strip()]

    return {
        'allow_private': allow_private,
        'allowed_hosts': allowed_hosts or None,
    }


def validate_url_with_env_config(url: str) -> str:
    """
    Validate URL using environment-based SSRF configuration.

    Uses FLYTO_ALLOW_PRIVATE_NETWORK and FLYTO_ALLOWED_HOSTS env vars.

    Args:
        url: URL to validate

    Returns:
        The validated URL

    Raises:
        SSRFError: If the URL targets a blocked resource
    """
    config = get_ssrf_config()
    return validate_url_ssrf(url, **config)
