"""
JSON-RPC Protocol Implementation

Handles encoding/decoding of JSON-RPC messages for plugin communication.
Protocol version: 0.1.0

Security:
- Input validation using Pydantic models
- Error message filtering to prevent secret leakage
- Size limits on messages
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# Security: Maximum sizes for protocol messages
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_STEP_ID_LENGTH = 256
MAX_STRING_VALUE_LENGTH = 1024 * 1024  # 1MB for individual string values


# Security: Patterns that might indicate secrets in error messages
SECRET_PATTERNS = [
    re.compile(r'password["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.IGNORECASE),
    re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.IGNORECASE),
    re.compile(r'secret["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.IGNORECASE),
    re.compile(r'token["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.IGNORECASE),
    re.compile(r'bearer\s+[a-zA-Z0-9_\-\.]+', re.IGNORECASE),
    re.compile(r'aws[_-]?access[_-]?key["\']?\s*[:=]\s*["\']?[^"\'}\s]+', re.IGNORECASE),
    re.compile(r'private[_-]?key["\']?\s*[:=]', re.IGNORECASE),
    re.compile(r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----'),
    re.compile(r'ghp_[a-zA-Z0-9]+'),  # GitHub personal access token
    re.compile(r'sk-[a-zA-Z0-9]+'),  # OpenAI API key
    re.compile(r'AKIA[A-Z0-9]{16}'),  # AWS access key ID
]


def filter_sensitive_data(message: str) -> str:
    """
    Filter potentially sensitive data from error messages.

    Security: Prevents accidental leakage of secrets in error messages.

    Args:
        message: Error message that might contain secrets

    Returns:
        Sanitized message with secrets redacted
    """
    if not message:
        return message

    filtered = message
    for pattern in SECRET_PATTERNS:
        filtered = pattern.sub('[REDACTED]', filtered)

    return filtered


def validate_message_size(data: str) -> None:
    """
    Validate message size is within limits.

    Args:
        data: JSON string

    Raises:
        ValueError: If message is too large
    """
    if len(data) > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message too large ({len(data)} bytes, max {MAX_MESSAGE_SIZE})"
        )

# Protocol constants
JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "0.1.0"


# Pydantic models for validation
class InvokeParams(BaseModel):
    """Validated parameters for invoke requests."""
    step: str = Field(..., max_length=MAX_STEP_ID_LENGTH)
    input: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    timeoutMs: int = Field(default=30000, ge=100, le=600000)

    @field_validator('step')
    @classmethod
    def validate_step(cls, v: str) -> str:
        """Validate step ID format."""
        if not v or not v.strip():
            raise ValueError('Step ID cannot be empty')
        # Security: Check for path traversal in step ID
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError('Step ID contains invalid characters')
        return v.strip()


class HandshakeParams(BaseModel):
    """Validated parameters for handshake requests."""
    protocolVersion: str = Field(..., max_length=32)
    pluginId: str = Field(..., max_length=256)
    executionId: str = Field(..., max_length=256)


class ShutdownParams(BaseModel):
    """Validated parameters for shutdown requests."""
    reason: str = Field(default="shutdown", max_length=256)
    gracePeriodMs: int = Field(default=5000, ge=0, le=60000)


class SecretsResolveParams(BaseModel):
    """Validated parameters for secrets.resolve requests."""
    refs: List[str] = Field(default_factory=list, max_length=100)

    @field_validator('refs')
    @classmethod
    def validate_refs(cls, v: List[str]) -> List[str]:
        """Validate secret refs format."""
        for ref in v:
            if not ref.startswith('flyto://secrets/'):
                raise ValueError(f'Invalid secret ref format: {ref}')
            if len(ref) > 512:
                raise ValueError('Secret ref too long')
        return v


class BrowserConnectParams(BaseModel):
    """Validated parameters for browser.connect requests."""
    sessionId: str = Field(..., max_length=256)
    headless: bool = Field(default=True)


class ValidatedJsonRpcRequest(BaseModel):
    """Fully validated JSON-RPC request."""
    jsonrpc: str = Field(default=JSONRPC_VERSION)
    method: str = Field(..., max_length=64)
    params: Dict[str, Any] = Field(default_factory=dict)
    id: int = Field(..., ge=0)

    @field_validator('method')
    @classmethod
    def validate_method(cls, v: str) -> str:
        """Validate method name."""
        allowed_methods = {
            'handshake', 'invoke', 'shutdown', 'ping',
            'secrets.resolve', 'browser.connect', 'browser.page', 'browser.close'
        }
        if v not in allowed_methods:
            raise ValueError(f'Unknown method: {v}')
        return v

    def get_typed_params(self) -> BaseModel:
        """Get params as the appropriate typed model."""
        method_param_map = {
            'invoke': InvokeParams,
            'handshake': HandshakeParams,
            'shutdown': ShutdownParams,
            'secrets.resolve': SecretsResolveParams,
            'browser.connect': BrowserConnectParams,
        }
        model = method_param_map.get(self.method)
        if model:
            return model(**self.params)
        return BaseModel()


class ValidatedJsonRpcResponse(BaseModel):
    """Fully validated JSON-RPC response."""
    jsonrpc: str = Field(default=JSONRPC_VERSION)
    id: int = Field(..., ge=0)
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    @model_validator(mode='after')
    def validate_result_or_error(self) -> 'ValidatedJsonRpcResponse':
        """Ensure either result or error is set, not both."""
        if self.result is not None and self.error is not None:
            raise ValueError('Response cannot have both result and error')
        return self

# Standard JSON-RPC error codes
class ErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Flyto-specific error codes
    STEP_NOT_FOUND = -32001
    VALIDATION_ERROR = -32002
    PERMISSION_DENIED = -32003
    SECRET_NOT_PROVIDED = -32004
    TIMEOUT = -32005
    RESOURCE_EXHAUSTED = -32006
    BROWSER_NOT_AVAILABLE = -32007
    BROWSER_CONNECTION_FAILED = -32008
    LANGUAGE_NOT_SUPPORTED = -32009


@dataclass
class JsonRpcRequest:
    """JSON-RPC 2.0 Request object."""
    method: str
    params: Dict[str, Any]
    id: int
    jsonrpc: str = JSONRPC_VERSION

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params,
            "id": self.id,
        })

    @classmethod
    def from_json(cls, data: str, validate: bool = True) -> "JsonRpcRequest":
        """
        Deserialize from JSON string.

        Args:
            data: JSON string
            validate: If True, perform security validation

        Raises:
            ValueError: If message is too large or invalid
            json.JSONDecodeError: If invalid JSON
        """
        # Security: Check message size
        if validate:
            validate_message_size(data)

        obj = json.loads(data)

        # Security: Use Pydantic validation
        if validate:
            validated = ValidatedJsonRpcRequest(**obj)
            return cls(
                method=validated.method,
                params=validated.params,
                id=validated.id,
                jsonrpc=validated.jsonrpc,
            )

        return cls(
            method=obj["method"],
            params=obj.get("params", {}),
            id=obj["id"],
            jsonrpc=obj.get("jsonrpc", JSONRPC_VERSION),
        )


@dataclass
class JsonRpcResponse:
    """JSON-RPC 2.0 Response object."""
    id: int
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    jsonrpc: str = JSONRPC_VERSION

    def to_json(self) -> str:
        """Serialize to JSON string."""
        obj = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
        }
        if self.error is not None:
            obj["error"] = self.error
        else:
            obj["result"] = self.result
        return json.dumps(obj)

    @classmethod
    def from_json(cls, data: str, filter_secrets: bool = True) -> "JsonRpcResponse":
        """
        Deserialize from JSON string.

        Args:
            data: JSON string
            filter_secrets: If True, filter sensitive data from error messages

        Raises:
            ValueError: If message is too large
            json.JSONDecodeError: If invalid JSON
        """
        # Security: Check message size
        validate_message_size(data)

        obj = json.loads(data)

        # Security: Filter sensitive data from error messages
        error = obj.get("error")
        if error and filter_secrets:
            if "message" in error:
                error["message"] = filter_sensitive_data(error["message"])
            if "data" in error and isinstance(error["data"], str):
                error["data"] = filter_sensitive_data(error["data"])
            # Also filter nested details
            if "data" in error and isinstance(error["data"], dict):
                for key in ["details", "stderr", "stdout", "trace"]:
                    if key in error["data"] and isinstance(error["data"][key], str):
                        error["data"][key] = filter_sensitive_data(error["data"][key])

        return cls(
            id=obj["id"],
            result=obj.get("result"),
            error=error,
            jsonrpc=obj.get("jsonrpc", JSONRPC_VERSION),
        )

    @property
    def is_error(self) -> bool:
        """Check if response is an error."""
        return self.error is not None

    @property
    def is_success(self) -> bool:
        """Check if response is successful."""
        return self.error is None


class ProtocolEncoder:
    """Encodes messages for plugin communication."""

    @staticmethod
    def encode_handshake(
        protocol_version: str,
        plugin_id: str,
        execution_id: str,
        request_id: int,
    ) -> str:
        """
        Encode handshake request.

        Args:
            protocol_version: Protocol version (e.g., "0.1.0")
            plugin_id: Plugin identifier
            execution_id: Current execution ID
            request_id: Request ID for correlation

        Returns:
            JSON-RPC request string
        """
        request = JsonRpcRequest(
            method="handshake",
            params={
                "protocolVersion": protocol_version,
                "pluginId": plugin_id,
                "executionId": execution_id,
            },
            id=request_id,
        )
        return request.to_json()

    @staticmethod
    def encode_invoke(
        step: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any],
        request_id: int,
        timeout_ms: int = 30000,
    ) -> str:
        """
        Encode invoke request.

        Args:
            step: Step ID to invoke
            input_data: Input parameters
            config: Static configuration
            context: Execution context
            request_id: Request ID for correlation
            timeout_ms: Timeout in milliseconds

        Returns:
            JSON-RPC request string
        """
        request = JsonRpcRequest(
            method="invoke",
            params={
                "step": step,
                "input": input_data,
                "config": config,
                "context": context,
                "timeoutMs": timeout_ms,
            },
            id=request_id,
        )
        return request.to_json()

    @staticmethod
    def encode_shutdown(
        reason: str,
        grace_period_ms: int,
        request_id: int,
    ) -> str:
        """
        Encode shutdown request.

        Args:
            reason: Reason for shutdown
            grace_period_ms: Grace period in milliseconds
            request_id: Request ID for correlation

        Returns:
            JSON-RPC request string
        """
        request = JsonRpcRequest(
            method="shutdown",
            params={
                "reason": reason,
                "gracePeriodMs": grace_period_ms,
            },
            id=request_id,
        )
        return request.to_json()

    @staticmethod
    def encode_ping(request_id: int) -> str:
        """
        Encode ping request for health check.

        Args:
            request_id: Request ID for correlation

        Returns:
            JSON-RPC request string
        """
        request = JsonRpcRequest(
            method="ping",
            params={},
            id=request_id,
        )
        return request.to_json()

    @staticmethod
    def encode_secrets_resolve(
        secret_refs: list,
        request_id: int,
    ) -> str:
        """
        Encode secrets resolve request (plugin -> core).

        Args:
            secret_refs: List of secret reference strings
            request_id: Request ID for correlation

        Returns:
            JSON-RPC request string
        """
        request = JsonRpcRequest(
            method="secrets.resolve",
            params={
                "refs": secret_refs,
            },
            id=request_id,
        )
        return request.to_json()

    @staticmethod
    def encode_browser_connect(
        session_id: str,
        headless: bool,
        request_id: int,
    ) -> str:
        """
        Encode browser connect request (plugin -> core).

        Plugins use this to request a shared browser session.
        Core returns a WebSocket endpoint for CDP connection.

        Args:
            session_id: Session identifier for the browser
            headless: Whether to run in headless mode
            request_id: Request ID for correlation

        Returns:
            JSON-RPC request string
        """
        request = JsonRpcRequest(
            method="browser.connect",
            params={
                "sessionId": session_id,
                "headless": headless,
            },
            id=request_id,
        )
        return request.to_json()

    @staticmethod
    def encode_browser_page(
        session_id: str,
        context_id: Optional[str],
        request_id: int,
    ) -> str:
        """
        Encode browser page request (plugin -> core).

        Plugins use this to request a new page in a browser session.

        Args:
            session_id: Browser session identifier
            context_id: Optional browser context identifier
            request_id: Request ID for correlation

        Returns:
            JSON-RPC request string
        """
        request = JsonRpcRequest(
            method="browser.page",
            params={
                "sessionId": session_id,
                "contextId": context_id,
            },
            id=request_id,
        )
        return request.to_json()

    @staticmethod
    def encode_browser_close(
        session_id: str,
        request_id: int,
    ) -> str:
        """
        Encode browser close request (plugin -> core).

        Args:
            session_id: Browser session to close
            request_id: Request ID for correlation

        Returns:
            JSON-RPC request string
        """
        request = JsonRpcRequest(
            method="browser.close",
            params={
                "sessionId": session_id,
            },
            id=request_id,
        )
        return request.to_json()


class ProtocolDecoder:
    """Decodes messages from plugin communication."""

    @staticmethod
    def decode_response(data: str) -> JsonRpcResponse:
        """
        Decode JSON-RPC response.

        Args:
            data: JSON string

        Returns:
            JsonRpcResponse object

        Raises:
            json.JSONDecodeError: If invalid JSON
            KeyError: If missing required fields
        """
        return JsonRpcResponse.from_json(data)

    @staticmethod
    def decode_request(data: str) -> JsonRpcRequest:
        """
        Decode JSON-RPC request (for plugin-initiated messages).

        Args:
            data: JSON string

        Returns:
            JsonRpcRequest object

        Raises:
            json.JSONDecodeError: If invalid JSON
            KeyError: If missing required fields
        """
        return JsonRpcRequest.from_json(data)

    @staticmethod
    def extract_result(response: JsonRpcResponse, filter_secrets: bool = True) -> Dict[str, Any]:
        """
        Extract result from response, normalizing format.

        Security: Filters sensitive data from error messages.

        Args:
            response: JSON-RPC response
            filter_secrets: If True, filter sensitive data from errors

        Returns:
            Normalized result dict with 'ok', 'data', 'error' fields
        """
        if response.is_error:
            error = response.error
            error_message = error.get("message", "Unknown error")
            error_details = error.get("data")

            # Security: Filter sensitive data from error messages
            if filter_secrets:
                error_message = filter_sensitive_data(error_message)
                if isinstance(error_details, str):
                    error_details = filter_sensitive_data(error_details)
                elif isinstance(error_details, dict):
                    # Deep filter dict values
                    error_details = _filter_dict_secrets(error_details)

            return {
                "ok": False,
                "error": {
                    "code": error.get("code", "UNKNOWN_ERROR"),
                    "message": error_message,
                    "details": error_details,
                },
            }

        result = response.result or {}

        # Result already has 'ok' field - return as-is
        if "ok" in result:
            return result

        # Wrap raw result
        return {
            "ok": True,
            "data": result,
        }


def _filter_dict_secrets(d: Dict[str, Any], max_depth: int = 3) -> Dict[str, Any]:
    """
    Recursively filter secrets from a dictionary.

    Args:
        d: Dictionary to filter
        max_depth: Maximum recursion depth

    Returns:
        Filtered dictionary
    """
    if max_depth <= 0:
        return d

    result = {}
    for key, value in d.items():
        if isinstance(value, str):
            result[key] = filter_sensitive_data(value)
        elif isinstance(value, dict):
            result[key] = _filter_dict_secrets(value, max_depth - 1)
        elif isinstance(value, list):
            result[key] = [
                filter_sensitive_data(v) if isinstance(v, str)
                else _filter_dict_secrets(v, max_depth - 1) if isinstance(v, dict)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result


def create_error_response(
    request_id: int,
    code: int,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> JsonRpcResponse:
    """
    Create a JSON-RPC error response.

    Args:
        request_id: Request ID to correlate with
        code: Error code
        message: Error message
        data: Additional error data

    Returns:
        JsonRpcResponse with error
    """
    error = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = data

    return JsonRpcResponse(id=request_id, error=error)


def create_success_response(
    request_id: int,
    result: Dict[str, Any],
) -> JsonRpcResponse:
    """
    Create a JSON-RPC success response.

    Args:
        request_id: Request ID to correlate with
        result: Result data

    Returns:
        JsonRpcResponse with result
    """
    return JsonRpcResponse(id=request_id, result=result)
