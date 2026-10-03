# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Secret redaction for execution traces, outputs, and persisted evidence.

Two levels:

  redact_sensitive(data)        — key-name based: dict values under a key like
                                  api_key/secret/token/password become
                                  [REDACTED]. Strings are left untouched. Used for
                                  live module output (re-exported by step_executor).

  redact_for_persistence(data)  — everything redact_sensitive does PLUS value-level
                                  masking of credential-bearing STRINGS (URL
                                  user:pass@, known token formats, JWTs, private
                                  keys, Basic-auth, Stripe/AWS/GCP/Slack/GitHub
                                  tokens). Used at the trace/API boundary and
                                  before writing trace/evidence to disk, where a
                                  red-team run against a target with creds would
                                  otherwise leave them in plaintext.

The execution trace is returned to MCP/API clients AND persisted, so a recipe
that carries a token/DSN as a param must not echo it back. trace.py runs
redact_for_persistence at every to_dict() boundary (inputParams, output, step
params, item input/output, error messages).
"""

import re
from typing import Any

# Key names whose values are sensitive regardless of content.
_SENSITIVE_KEY_PATTERN = re.compile(
    r'(?i)(api[_-]?key|secret|password|passwd|token|credential|auth|'
    r'private[_-]?key|bearer|jwt|session|access[_-]?key|client[_-]?secret|'
    r'set[_-]?cookie|cookie)',
)

_REDACT_TOKEN = '[REDACTED]'

# URL userinfo:  scheme://user:pass@host  ->  scheme://[REDACTED]@host
_URL_CREDS = re.compile(r'(?i)\b([a-z][a-z0-9+.\-]*://)[^:/?#\s@]+:[^@/?#\s]+@')

# Value-level patterns: high-signal credential formats. Kept conservative to
# avoid mangling ordinary scraped text.
_VALUE_PATTERNS = [
    # PEM private keys (multi-line) — collapse the whole block.
    re.compile(
        r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----'
        r'.*?-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----',
        re.DOTALL,
    ),
    re.compile(r'(?i)authorization:\s*basic\s+[A-Za-z0-9+/=]+'),   # Basic auth header
    re.compile(r'(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+'), # Bearer auth header
    re.compile(r'sk-[A-Za-z0-9_\-]{16,}'),                        # OpenAI-style
    re.compile(r'(?i)[sr]k_(?:live|test)_[A-Za-z0-9]{16,}'),      # Stripe secret/restricted
    re.compile(r'gh[posru]_[A-Za-z0-9]{20,}'),                    # GitHub tokens
    re.compile(r'AIza[0-9A-Za-z_\-]{20,}'),                       # Google API key
    re.compile(r'ya29\.[0-9A-Za-z_\-]+'),                         # Google OAuth token
    re.compile(r'xox[baprs]-[A-Za-z0-9\-]{10,}'),                 # Slack tokens
    re.compile(r'AKIA[0-9A-Z]{16}'),                              # AWS access key id
    re.compile(r'(?i)aws_secret_access_key["\'\s:=]+[A-Za-z0-9/+]{40}'),  # AWS secret
    re.compile(r'AC[0-9a-fA-F]{32}'),                             # Twilio Account SID
    re.compile(r'SK[0-9a-fA-F]{32}'),                             # Twilio API key SID
    re.compile(r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'),  # JWT
    re.compile(r'(?i)bearer\s+[A-Za-z0-9._\-]{16,}'),             # bare "bearer <token>"
]

# Generic high-entropy fallback: a long unbroken base64/hex-ish run that looks
# like a secret. Bounded so ordinary words/hashes-in-prose are unlikely to hit.
_HIGH_ENTROPY = re.compile(r'\b[A-Za-z0-9+/_\-]{40,}={0,2}\b')


def redact_text(value: str) -> str:
    """Mask credential-bearing substrings inside a single string."""
    if not value or not isinstance(value, str):
        return value
    redacted = _URL_CREDS.sub(r'\1' + _REDACT_TOKEN + '@', value)
    for pat in _VALUE_PATTERNS:
        redacted = pat.sub(_REDACT_TOKEN, redacted)
    # High-entropy fallback last, only on tokens still containing both letters
    # AND digits (a heuristic that skips plain words / hex commit prose less).
    def _maybe_redact(m: "re.Match") -> str:
        tok = m.group(0)
        has_alpha = any(c.isalpha() for c in tok)
        has_digit = any(c.isdigit() for c in tok)
        if has_alpha and has_digit:
            return _REDACT_TOKEN
        return tok
    redacted = _HIGH_ENTROPY.sub(_maybe_redact, redacted)
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
    if depth > 12 or data is None:
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


# ---------------------------------------------------------------------------
# Step parameters
# ---------------------------------------------------------------------------
#
# A step's parameters reach hooks (and so every host's step log) and the trace
# before the module has run. The key pattern above is tuned for OUTPUTS and is
# wrong for parameters in both directions: it redacts `author`, `session_id`
# and `max_tokens`, which an operator needs to read, and it misses the
# parameter that actually carries a password in a browser workflow -- `text`
# on a field labelled "Password", or the schema's own `sensitive_text`.
#
# So parameters get their own rule, built from four sources, any one of which
# is enough:
#
#   1. the name looks like a credential (`password`, `api_key`, `secret`,
#      `sensitive_text`, `access_token`, ...);
#   2. the module's schema declares the field `secret` / `format: password`;
#   3. the module class says so for these params (`sensitive_params`), for a
#      free-text field that is only a credential when another field says it is;
#   4. the module found out at runtime and said so in its result under
#      SENSITIVE_PARAMS_KEY -- an `<input type=password>` behind a selector
#      that names nothing of the sort.
#
# Empty values and bare references (`{{env.LOGIN_PASSWORD}}`,
# `${env.LOGIN_PASSWORD}`) are left as they are: neither is a secret, and the
# reference is exactly what an operator needs to see to debug the run.

#: Result key a module uses to name parameters it found sensitive while running.
SENSITIVE_PARAMS_KEY = '_sensitive_params'

_SENSITIVE_PARAM_NAME = re.compile(
    r'(?i)(password|passwd|passphrase|passcode|pwd|secret|credential|'
    r'private[_-]?key|api[_-]?key|access[_-]?key|bearer|'
    r'(?:^|[_-])sensitive[_-]|'
    r'(?:^|[_-])token(?:$|[_-]))',
)

_BARE_REFERENCE = re.compile(r'^\s*(?:\{\{[^{}]+\}\}|\$\{[^{}]+\})\s*$')


def is_sensitive_param_name(name: Any) -> bool:
    """True when a parameter's name alone marks its value as a credential."""
    return bool(_SENSITIVE_PARAM_NAME.search(str(name)))


def _declared_sensitive(module_id: Any, params: dict) -> frozenset:
    """Names the registry schema or the module class mark sensitive.

    Best effort by construction: redaction must never be the reason a step
    cannot be logged, so a lookup that fails declares nothing and the name
    rule still applies.
    """
    if not module_id or not isinstance(module_id, str):
        return frozenset()
    lookup_id = 'template.invoke' if module_id.startswith('template.invoke:') else module_id
    try:
        from ..modules.registry import ModuleRegistry

        names = set(ModuleRegistry.secret_param_names(lookup_id))
        if ModuleRegistry.has(lookup_id):
            declare = getattr(ModuleRegistry.get(lookup_id), 'sensitive_params', None)
            if callable(declare):
                names.update(declare(params) or ())
        return frozenset(names)
    except Exception:  # noqa: BLE001 - see docstring
        return frozenset()


def _keep_visible(value: Any) -> bool:
    # A boolean is a switch, never the secret: `case_sensitive`, `use_token`.
    if value is None or value == '' or isinstance(value, bool):
        return True
    return isinstance(value, str) and bool(_BARE_REFERENCE.match(value))


def runtime_sensitive_params(result: Any) -> frozenset:
    """Parameter names a module reported sensitive in its result."""
    if not isinstance(result, dict):
        return frozenset()
    named = result.get(SENSITIVE_PARAMS_KEY)
    if not isinstance(named, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(str(name) for name in named)


def redact_step_params(
    module_id: Any,
    params: Any,
    extra: Any = (),
) -> Any:
    """A copy of a step's parameters safe to hand to hooks and the trace.

    Top level only for the schema/class/runtime sources (they name top-level
    parameters); the name rule also applies inside nested dicts, so
    ``{"auth": {"password": ...}}`` is covered. The input is never mutated:
    the executor resolves its own copy of the parameters for the module.
    """
    if not isinstance(params, dict):
        return params
    named = set(_declared_sensitive(module_id, params))
    named.update(str(name) for name in (extra or ()))
    return {
        key: (
            value if _keep_visible(value)
            else _REDACT_TOKEN if (key in named or is_sensitive_param_name(key))
            else _redact_nested_params(value, 1)
        )
        for key, value in params.items()
    }


def _redact_nested_params(data: Any, depth: int) -> Any:
    if depth > 10:
        return data
    if isinstance(data, dict):
        return {
            key: (
                value if _keep_visible(value)
                else _REDACT_TOKEN if is_sensitive_param_name(key)
                else _redact_nested_params(value, depth + 1)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_redact_nested_params(item, depth + 1) for item in data]
    return data
