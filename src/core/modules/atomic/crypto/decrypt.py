# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Crypto Decrypt Module
AES symmetric decryption (matches crypto.encrypt).
"""
import base64
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError


logger = logging.getLogger(__name__)


@register_module(
    module_id='crypto.decrypt',
    version='1.0.0',
    category='crypto',
    tags=['crypto', 'decrypt', 'aes', 'security', 'advanced'],
    label='Decrypt',
    label_key='modules.crypto.decrypt.label',
    description='AES symmetric decryption',
    description_key='modules.crypto.decrypt.description',
    icon='Unlock',
    color='#10B981',
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
            'ciphertext',
            type='text',
            label='Ciphertext',
            label_key='modules.crypto.decrypt.params.ciphertext.label',
            description='Encrypted ciphertext to decrypt',
            description_key='modules.crypto.decrypt.params.ciphertext.description',
            required=True,
            placeholder='base64 or hex encoded ciphertext...',
            group=FieldGroup.BASIC,
        ),
        field(
            'key',
            type='password',
            label='Passphrase',
            label_key='modules.crypto.decrypt.params.key.label',
            description='Decryption passphrase (must match encryption passphrase)',
            description_key='modules.crypto.decrypt.params.key.description',
            required=True,
            placeholder='your-secret-passphrase',
            group=FieldGroup.BASIC,
        ),
        field(
            'mode',
            type='string',
            label='Mode',
            label_key='modules.crypto.decrypt.params.mode.label',
            description='Decryption mode (must match encryption mode)',
            description_key='modules.crypto.decrypt.params.mode.description',
            default='GCM',
            options=[
                {'value': 'CBC', 'label': 'AES-CBC'},
                {'value': 'GCM', 'label': 'AES-GCM'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'input_format',
            type='string',
            label='Input Format',
            label_key='modules.crypto.decrypt.params.input_format.label',
            description='Encoding format of the ciphertext input',
            description_key='modules.crypto.decrypt.params.input_format.description',
            default='base64',
            options=[
                {'value': 'base64', 'label': 'Base64'},
                {'value': 'hex', 'label': 'Hexadecimal'},
            ],
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'plaintext': {
            'type': 'string',
            'description': 'Decrypted plaintext',
            'description_key': 'modules.crypto.decrypt.output.plaintext.description',
        },
        'algorithm': {
            'type': 'string',
            'description': 'Decryption algorithm used',
            'description_key': 'modules.crypto.decrypt.output.algorithm.description',
        },
    },
    examples=[
        {
            'title': 'Decrypt AES-GCM ciphertext',
            'title_key': 'modules.crypto.decrypt.examples.gcm.title',
            'params': {
                'ciphertext': '<base64-encoded-ciphertext>',
                'key': 'my-secret-passphrase',
                'mode': 'GCM',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def crypto_decrypt(context: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypt ciphertext using AES symmetric decryption."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
    except ImportError:
        raise ModuleError(
            "cryptography library is required for crypto.decrypt. "
            "Install with: pip install cryptography"
        )

    params = context['params']
    ciphertext = params.get('ciphertext')
    key = params.get('key')
    mode = params.get('mode', 'GCM')
    input_format = params.get('input_format', 'base64')

    if not ciphertext:
        raise ValidationError("Missing required parameter: ciphertext", field="ciphertext")
    if not key:
        raise ValidationError("Missing required parameter: key", field="key")

    # Decode input
    try:
        if input_format == 'hex':
            packed = bytes.fromhex(ciphertext)
        else:
            packed = base64.b64decode(ciphertext)
    except Exception as e:
        raise ValidationError(f"Failed to decode ciphertext ({input_format}): {e}", field="ciphertext")

    # Extract salt (first 16 bytes)
    if len(packed) < 16:
        raise ModuleError("Ciphertext too short: missing salt")

    salt = packed[:16]

    # Derive key from passphrase using same PBKDF2 parameters as encrypt
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    derived_key = kdf.derive(key.encode('utf-8'))

    try:
        if mode == 'GCM':
            # Unpack: salt (16) + nonce (12) + ciphertext
            if len(packed) < 28:
                raise ModuleError("Ciphertext too short for AES-GCM: missing nonce")
            nonce = packed[16:28]
            ciphertext_bytes = packed[28:]

            aesgcm = AESGCM(derived_key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_bytes, None)

        elif mode == 'CBC':
            # Unpack: salt (16) + iv (16) + ciphertext
            if len(packed) < 32:
                raise ModuleError("Ciphertext too short for AES-CBC: missing IV")
            iv = packed[16:32]
            ciphertext_bytes = packed[32:]

            cipher = Cipher(algorithms.AES(derived_key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(ciphertext_bytes) + decryptor.finalize()

            # Remove PKCS7 padding
            unpadder = sym_padding.PKCS7(128).unpadder()
            plaintext_bytes = unpadder.update(padded_data) + unpadder.finalize()

        else:
            raise ValidationError(f"Unsupported decryption mode: {mode}", field="mode")

    except ValidationError:
        raise
    except ModuleError:
        raise
    except Exception as e:
        raise ModuleError(f"Decryption failed (wrong key or corrupted data): {e}")

    plaintext = plaintext_bytes.decode('utf-8')
    logger.info(f"Decrypted {len(plaintext_bytes)} bytes using AES-{mode}")

    return {
        'ok': True,
        'data': {
            'plaintext': plaintext,
            'algorithm': 'AES-256',
        },
    }
