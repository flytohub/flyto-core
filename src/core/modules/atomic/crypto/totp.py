# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Crypto TOTP Module
Generate RFC 6238 time-based one-time passwords from an authenticator secret.
"""
import asyncio
import base64
import binascii
import hashlib
import hmac
import logging
import struct
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from ...errors import ValidationError
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)

# RFC 6238 defaults, used when neither the caller nor an otpauth URI says otherwise.
_DEFAULT_DIGITS = 6
_DEFAULT_PERIOD = 30
_DEFAULT_ALGORITHM = 'SHA1'

_HASHES = {
    'SHA1': hashlib.sha1,
    'SHA256': hashlib.sha256,
    'SHA512': hashlib.sha512,
}


def _decode_base32_secret(secret: str) -> bytes:
    """Decode an authenticator Base32 secret.

    Authenticator apps display secrets in lowercase, in space-separated groups,
    and without ``=`` padding. All three forms are accepted here because the
    value is normally copied straight out of the enrolment screen.
    """
    normalized = ''.join(secret.split()).upper()
    if not normalized:
        raise ValidationError("secret must not be empty", field="secret")

    # Base32 decodes in 8-character blocks; restore the padding the UI dropped.
    padding = (-len(normalized)) % 8
    try:
        return base64.b32decode(normalized + ('=' * padding), casefold=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(
            "secret is not valid Base32",
            field="secret",
            hint=(
                "Copy the key your authenticator shows under 'enter a setup key "
                "manually', or paste the whole otpauth:// URI from its enrolment "
                "QR code."
            ),
        ) from exc


def _parse_otpauth_uri(uri: str) -> Tuple[str, Dict[str, Any]]:
    """Split an ``otpauth://totp/...`` URI into its secret and its settings.

    This is the format encoded in every enrolment QR code, so accepting it lets
    a caller import an authenticator entry without transcribing its fields.
    """
    parsed = urlparse(uri)
    if (parsed.netloc or parsed.hostname or '').lower() != 'totp':
        raise ValidationError(
            "only otpauth://totp/ URIs are supported",
            field="secret",
            hint=(
                "An otpauth://hotp/ entry is counter-based, not time-based, so "
                "its code cannot be derived from the clock."
            ),
        )

    query = parse_qs(parsed.query)

    def _single(name: str) -> Optional[str]:
        values = query.get(name)
        return values[0] if values else None

    secret = _single('secret')
    if not secret:
        raise ValidationError("otpauth URI has no 'secret' parameter", field="secret")

    settings: Dict[str, Any] = {'issuer': _single('issuer')}

    # The label is "Issuer:account" or just "account"; it is display metadata
    # only, and the issuer query parameter wins when both are present.
    label = unquote(parsed.path.lstrip('/'))
    if label:
        label_issuer, separator, account = label.partition(':')
        settings['account'] = account.strip() if separator else label.strip()
        if separator and not settings['issuer']:
            settings['issuer'] = label_issuer.strip()
    else:
        settings['account'] = None

    for name in ('digits', 'period'):
        raw = _single(name)
        if raw is not None:
            try:
                settings[name] = int(raw)
            except ValueError as exc:
                raise ValidationError(
                    f"otpauth URI has a non-numeric '{name}' parameter: {raw!r}",
                    field="secret",
                ) from exc

    algorithm = _single('algorithm')
    if algorithm is not None:
        settings['algorithm'] = algorithm.strip().upper()

    return secret, settings


def _hotp(key: bytes, counter: int, digits: int, algorithm: str) -> str:
    """RFC 4226 HOTP — the counter-based primitive TOTP is built on."""
    digest = hmac.new(key, struct.pack('>Q', counter), _HASHES[algorithm]).digest()
    # Dynamic truncation: the low nibble of the last byte picks the offset.
    offset = digest[-1] & 0x0F
    truncated = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** digits)).zfill(digits)


def _resolve_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be an integer", field=name) from exc
    if not minimum <= resolved <= maximum:
        raise ValidationError(
            f"{name} must be between {minimum} and {maximum}", field=name
        )
    return resolved


@register_module(
    module_id='crypto.totp',
    version='1.0.0',
    category='crypto',
    tags=['crypto', 'totp', 'otp', '2fa', 'mfa', 'auth', 'security', 'advanced'],
    label='TOTP Code',
    label_key='modules.crypto.totp.label',
    description='Generate a time-based one-time password (RFC 6238)',
    description_key='modules.crypto.totp.description',
    icon='ShieldCheck',
    color='#DC2626',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['browser.*', 'http.*', 'data.*', 'crypto.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,
    timeout_ms=60000,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema=compose(
        field(
            'secret',
            type='string',
            format='password',
            label='Authenticator Secret',
            label_key='modules.crypto.totp.params.secret.label',
            description=(
                'Base32 setup key from your authenticator, or the full '
                'otpauth:// URI encoded in its enrolment QR code'
            ),
            description_key='modules.crypto.totp.params.secret.description',
            required=True,
            placeholder='JBSWY3DPEHPK3PXP',
            group=FieldGroup.BASIC,
        ),
        field(
            'digits',
            type='number',
            label='Digits',
            label_key='modules.crypto.totp.params.digits.label',
            description='Code length. Taken from the otpauth URI when omitted, otherwise 6',
            description_key='modules.crypto.totp.params.digits.description',
            required=False,
            min=6,
            max=10,
            placeholder='6',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'period',
            type='number',
            label='Period (seconds)',
            label_key='modules.crypto.totp.params.period.label',
            description='Rotation interval. Taken from the otpauth URI when omitted, otherwise 30',
            description_key='modules.crypto.totp.params.period.description',
            required=False,
            min=1,
            max=600,
            placeholder='30',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'algorithm',
            type='select',
            label='Algorithm',
            label_key='modules.crypto.totp.params.algorithm.label',
            description='HMAC hash. "auto" uses the otpauth URI value, otherwise SHA1',
            description_key='modules.crypto.totp.params.algorithm.description',
            default='auto',
            options=[
                {'value': 'auto', 'label': 'Auto (from otpauth URI, else SHA1)'},
                {'value': 'SHA1', 'label': 'SHA1 (default for authenticator apps)'},
                {'value': 'SHA256', 'label': 'SHA256'},
                {'value': 'SHA512', 'label': 'SHA512'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'min_remaining',
            type='number',
            label='Minimum Remaining Validity (seconds)',
            label_key='modules.crypto.totp.params.min_remaining.label',
            description=(
                'Wait for the next code when the current one expires sooner than '
                'this. Prevents submitting a code that rotates in transit'
            ),
            description_key='modules.crypto.totp.params.min_remaining.description',
            required=False,
            default=0,
            min=0,
            max=600,
            placeholder='5',
            group=FieldGroup.ADVANCED,
        ),
        field(
            'at',
            type='number',
            label='Unix Timestamp',
            label_key='modules.crypto.totp.params.at.label',
            description='Generate the code for this instant instead of now. For testing',
            description_key='modules.crypto.totp.params.at.description',
            required=False,
            placeholder='1234567890',
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'code': {
            'type': 'string',
            'description': 'The one-time password, zero-padded to the requested length',
            'description_key': 'modules.crypto.totp.output.code.description',
        },
        'expires_in': {
            'type': 'number',
            'description': 'Seconds this code remains valid',
            'description_key': 'modules.crypto.totp.output.expires_in.description',
        },
        'period': {
            'type': 'number',
            'description': 'Rotation interval used',
            'description_key': 'modules.crypto.totp.output.period.description',
        },
        'digits': {
            'type': 'number',
            'description': 'Code length used',
            'description_key': 'modules.crypto.totp.output.digits.description',
        },
        'algorithm': {
            'type': 'string',
            'description': 'HMAC hash used',
            'description_key': 'modules.crypto.totp.output.algorithm.description',
        },
        'issuer': {
            'type': 'string',
            'description': 'Issuer from the otpauth URI, or null',
            'description_key': 'modules.crypto.totp.output.issuer.description',
        },
        'account': {
            'type': 'string',
            'description': 'Account label from the otpauth URI, or null',
            'description_key': 'modules.crypto.totp.output.account.description',
        },
    },
    examples=[
        {
            'title': 'Generate a code from a Base32 setup key',
            'title_key': 'modules.crypto.totp.examples.basic.title',
            'params': {
                'secret': '${TOTP_SECRET_FROM_VAULT}',
            },
        },
        {
            'title': 'Import an authenticator entry by otpauth URI',
            'title_key': 'modules.crypto.totp.examples.otpauth.title',
            'params': {
                'secret': '${OTPAUTH_URI_FROM_VAULT}',
                'min_remaining': 5,
            },
        },
    ],
    author='Flyto2 Team',
    license='MIT',
)
async def crypto_totp(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an RFC 6238 time-based one-time password."""
    params = context['params']
    secret = params.get('secret')

    if not secret:
        raise ValidationError("Missing required parameter: secret", field="secret")
    if not isinstance(secret, str):
        raise ValidationError("secret must be a string", field="secret")

    secret = secret.strip()
    uri_settings: Dict[str, Any] = {}
    if secret.lower().startswith('otpauth://'):
        secret, uri_settings = _parse_otpauth_uri(secret)

    key = _decode_base32_secret(secret)

    # Precedence: explicit parameter, then the otpauth URI, then the RFC default.
    digits = params.get('digits')
    if digits is None:
        digits = uri_settings.get('digits', _DEFAULT_DIGITS)
    digits = _resolve_int('digits', digits, 6, 10)

    period = params.get('period')
    if period is None:
        period = uri_settings.get('period', _DEFAULT_PERIOD)
    period = _resolve_int('period', period, 1, 600)

    algorithm = params.get('algorithm') or 'auto'
    if str(algorithm).lower() == 'auto':
        algorithm = uri_settings.get('algorithm', _DEFAULT_ALGORITHM)
    algorithm = str(algorithm).strip().upper()
    if algorithm not in _HASHES:
        raise ValidationError(
            f"algorithm must be one of {', '.join(sorted(_HASHES))}",
            field="algorithm",
        )

    at = params.get('at')
    now = time.time() if at is None else float(_resolve_int('at', at, 0, 2 ** 63 - 1))

    min_remaining = _resolve_int('min_remaining', params.get('min_remaining') or 0, 0, 600)
    if min_remaining >= period:
        raise ValidationError(
            f"min_remaining must be shorter than period ({period}s)",
            field="min_remaining",
            hint="Otherwise no code is ever considered fresh enough to submit.",
        )

    remaining = period - (now % period)
    if min_remaining and remaining < min_remaining:
        # A code that rotates while the form is in flight is rejected by the
        # server, so wait out the rest of this window before generating.
        logger.info(
            "TOTP code expires in %.1fs, waiting for the next %ds window",
            remaining, period,
        )
        if at is None:
            await asyncio.sleep(remaining)
            now = time.time()
        else:
            now += remaining
        remaining = period - (now % period)

    counter = int(now // period)
    code = _hotp(key, counter, digits, algorithm)

    # The code and the secret are both sensitive; log only the shape.
    logger.info(
        "Generated %d-digit TOTP (%s, period=%ds), valid for %.1fs",
        digits, algorithm, period, remaining,
    )

    return {
        'ok': True,
        'data': {
            'code': code,
            'expires_in': round(remaining, 3),
            'period': period,
            'digits': digits,
            'algorithm': algorithm,
            'issuer': uri_settings.get('issuer'),
            'account': uri_settings.get('account'),
        },
    }
