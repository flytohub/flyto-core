# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Secret redaction for outputs and persisted evidence.

Two levels:

  redact_sensitive(data)        — key-name based: dict values under a key like
                                  api_key/secret/token/password become
                                  [REDACTED]. Strings are left untouched. This is
                                  the long-standing behaviour used for live module
                                  output (re-exported by step_executor).

  redact_for_persistence(data)  — everything redact_sensitive does PLUS value-level
                                  masking of credential-bearing STRINGS (URL
                                  user:pass@, known token formats, JWTs, bearer
                                  tokens). Used before writing evidence/trace to
                                  disk, where a red-team run against a target with
                                  creds would otherwise leave them in plaintext.
"""

import re
from typing import Any

# Key names whose values are sensitive regardless of content.
_SENSITIVE_KEY_PATTERN = re.compile(
    r'(?i)(api[_-]?key|secret|password|passwd|token|credential|auth|private[_-]?key|bearer|jwt|session)',
)

# Value-level patterns: high-signal credential formats. Kept conservative to
# avoid mangling ordinary scraped text.
_REDACT_TOKEN = '[REDACTED]'

# URL userinfo:  scheme://user:pass@host  ->  scheme://[REDACTED]@host
_URL_CREDS = re.compile(r'(?i)\b([a-z][a-z0-9+.\-]*://)[^:/?#\s@]+:[^@/?#\s]+@')

_VALUE_PATTERNS = [
    re.compile(r'sk-[A-Za-z0-9_\-]{16,}'),                       # OpenAI-style
    re.compile(r'gh[posru]_[A-Za-z0-9]{20,}'),                   # GitHub tokens
    re.compile(r'AIza[0-9A-Za-z_\-]{20,}'),                      # Google API key
    re.compile(r'xox[baprs]-[A-Za-z0-9\-]{10,}'),                # Slack tokens
    re.compile(r'AKIA[0-9A-Z]{16}'),                             # AWS access key id
    re.compile(r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'),  # JWT (eyJ = {" base64)
    re.compile(r'(?i)bearer\s+[A-Za-z0-9._\-]{16,}'),            # Bearer <token>
]


def redact_text(value: str) -> str:
    """Mask credential-bearing substrings inside a single string."""
    if not value:
        return value
    redacted = _URL_CREDS.sub(r'\1' + _REDACT_TOKEN + '@', value)
    for pat in _VALUE_PATTERNS:
        redacted = pat.sub(_REDACT_TOKEN, redacted)
    return redacted


def redact_sensitive(data: Any, depth: int = 0) -> Any:
    """Key-name based redaction. Strings are returned unchanged.

    Only recurses up to 10 levels to bound runtime on pathological structures.
    """
    if depth > 10 or data is None:
        return data
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if _SENSITIVE_KEY_PATTERN.search(str(key)):
                out[key] = _REDACT_TOKEN
            else:
                out[key] = redact_sensitive(value, depth + 1)
        return out
    if isinstance(data, (list, tuple)):
        return [redact_sensitive(item, depth + 1) for item in data]
    return data


def redact_for_persistence(data: Any, depth: int = 0) -> Any:
    """Key-based redaction + value-level masking of credential strings."""
    if depth > 10 or data is None:
        return data
    if isinstance(data, str):
        return redact_text(data)
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if _SENSITIVE_KEY_PATTERN.search(str(key)):
                out[key] = _REDACT_TOKEN
            else:
                out[key] = redact_for_persistence(value, depth + 1)
        return out
    if isinstance(data, (list, tuple)):
        return [redact_for_persistence(item, depth + 1) for item in data]
    return data
