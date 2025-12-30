"""
Webhook Handler

Webhook signature verification and payload parsing.
"""

import hashlib
import hmac
from typing import Any, Dict, Union


class WebhookHandler:
    """
    Webhook signature verification and handling.

    Usage:
        handler = WebhookHandler(secret="webhook_secret")
        if handler.verify_signature(payload, signature):
            data = handler.parse(payload)
    """

    def __init__(
        self,
        secret: str,
        signature_header: str = "X-Signature",
        algorithm: str = "sha256",
    ):
        """
        Initialize webhook handler.

        Args:
            secret: Webhook secret for HMAC verification
            signature_header: Header containing signature
            algorithm: HMAC algorithm (sha256, sha1)
        """
        self.secret = secret.encode() if isinstance(secret, str) else secret
        self.signature_header = signature_header
        self.algorithm = algorithm

    def compute_signature(self, payload: Union[str, bytes]) -> str:
        """Compute HMAC signature for payload."""
        if isinstance(payload, str):
            payload = payload.encode()

        if self.algorithm == "sha256":
            mac = hmac.new(self.secret, payload, hashlib.sha256)
        elif self.algorithm == "sha1":
            mac = hmac.new(self.secret, payload, hashlib.sha1)
        else:
            raise ValueError(f"Unsupported algorithm: {self.algorithm}")

        return mac.hexdigest()

    def verify_signature(
        self,
        payload: Union[str, bytes],
        signature: str,
    ) -> bool:
        """
        Verify webhook signature.

        Args:
            payload: Raw request body
            signature: Signature from header

        Returns:
            True if signature is valid
        """
        # Handle prefixed signatures like "sha256=..."
        if "=" in signature:
            sig_algo, sig_value = signature.split("=", 1)
        else:
            sig_value = signature

        expected = self.compute_signature(payload)
        return hmac.compare_digest(expected, sig_value)

    def parse(
        self,
        payload: Union[str, bytes],
        content_type: str = "application/json",
    ) -> Dict[str, Any]:
        """Parse webhook payload."""
        import json

        if isinstance(payload, bytes):
            payload = payload.decode()

        if "json" in content_type:
            return json.loads(payload)
        elif "form" in content_type:
            from urllib.parse import parse_qs
            return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(payload).items()}
        else:
            return {"raw": payload}
