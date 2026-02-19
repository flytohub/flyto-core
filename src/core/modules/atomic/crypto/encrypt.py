# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Crypto Encrypt Module
AES symmetric encryption using Fernet (PBKDF2 key derivation).
"""
import base64
import hashlib
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError


logger = logging.getLogger(__name__)


@register_module(
    module_id='crypto.encrypt',
    version='1.0.0',
    category='crypto',
    tags=['crypto', 'encrypt', 'aes', 'security', 'advanced'],
    label='Encrypt',
    label_key='modules.crypto.encrypt.label',
    description='AES symmetric encryption',
    description_key='modules.crypto.encrypt.description',
    icon='Lock',
    color='#DC2626',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'crypto.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,
    timeout_ms=10000,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=[],

    params_schema=compose(
        field(
            'plaintext',
            type='text',
            label='Plaintext',
            label_key='modules.crypto.encrypt.params.plaintext.label',
            description='Text to encrypt',
            description_key='modules.crypto.encrypt.params.plaintext.description',
            required=True,
            placeholder='Secret message...',
            group=FieldGroup.BASIC,
        ),
        field(
            'key',
            type='password',
            label='Passphrase',
            label_key='modules.crypto.encrypt.params.key.label',
            description='Encryption passphrase (key is derived via PBKDF2)',
            description_key='modules.crypto.encrypt.params.key.description',
            required=True,
            placeholder='your-secret-passphrase',
            group=FieldGroup.BASIC,
        ),
        field(
            'mode',
            type='string',
            label='Mode',
            label_key='modules.crypto.encrypt.params.mode.label',
            description='Encryption mode',
            description_key='modules.crypto.encrypt.params.mode.description',
            default='GCM',
            options=[
                {'value': 'CBC', 'label': 'AES-CBC'},
                {'value': 'GCM', 'label': 'AES-GCM'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'output_format',
            type='string',
            label='Output Format',
            label_key='modules.crypto.encrypt.params.output_format.label',
            description='Encoding format for the ciphertext output',
            description_key='modules.crypto.encrypt.params.output_format.description',
            default='base64',
            options=[
                {'value': 'base64', 'label': 'Base64'},
                {'value': 'hex', 'label': 'Hexadecimal'},
            ],
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'ciphertext': {
            'type': 'string',
            'description': 'Encrypted ciphertext',
            'description_key': 'modules.crypto.encrypt.output.ciphertext.description',
        },
        'algorithm': {
            'type': 'string',
            'description': 'Encryption algorithm used',
            'description_key': 'modules.crypto.encrypt.output.algorithm.description',
        },
        'mode': {
            'type': 'string',
            'description': 'Encryption mode used',
            'description_key': 'modules.crypto.encrypt.output.mode.description',
        },
    },
    examples=[
        {
            'title': 'Encrypt with AES-GCM',
            'title_key': 'modules.crypto.encrypt.examples.gcm.title',
            'params': {
                'plaintext': 'Hello, World!',
                'key': 'my-secret-passphrase',
                'mode': 'GCM',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def crypto_encrypt(context: Dict[str, Any]) -> Dict[str, Any]:
    """Encrypt plaintext using AES symmetric encryption."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
    except ImportError:
        raise ModuleError(
            "cryptography library is required for crypto.encrypt. "
            "Install with: pip install cryptography"
        )

    params = context['params']
    plaintext = params.get('plaintext')
    key = params.get('key')
    mode = params.get('mode', 'GCM')
    output_format = params.get('output_format', 'base64')

    if not plaintext:
        raise ValidationError("Missing required parameter: plaintext", field="plaintext")
    if not key:
        raise ValidationError("Missing required parameter: key", field="key")

    import os as _os

    # Derive a 256-bit key from passphrase using PBKDF2
    salt = _os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    derived_key = kdf.derive(key.encode('utf-8'))
    plaintext_bytes = plaintext.encode('utf-8')

    if mode == 'GCM':
        nonce = _os.urandom(12)
        aesgcm = AESGCM(derived_key)
        ciphertext_bytes = aesgcm.encrypt(nonce, plaintext_bytes, None)
        # Pack: salt (16) + nonce (12) + ciphertext
        packed = salt + nonce + ciphertext_bytes

    elif mode == 'CBC':
        iv = _os.urandom(16)
        # PKCS7 padding
        padder = sym_padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext_bytes) + padder.finalize()

        cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ciphertext_bytes = encryptor.update(padded_data) + encryptor.finalize()
        # Pack: salt (16) + iv (16) + ciphertext
        packed = salt + iv + ciphertext_bytes

    else:
        raise ValidationError(f"Unsupported encryption mode: {mode}", field="mode")

    # Encode output
    if output_format == 'hex':
        ciphertext_str = packed.hex()
    else:
        ciphertext_str = base64.b64encode(packed).decode('utf-8')

    logger.info(f"Encrypted {len(plaintext_bytes)} bytes using AES-{mode}")

    return {
        'ok': True,
        'data': {
            'ciphertext': ciphertext_str,
            'algorithm': 'AES-256',
            'mode': mode,
        },
    }
