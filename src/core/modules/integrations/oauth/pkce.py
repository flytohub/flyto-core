"""
PKCE (Proof Key for Code Exchange) Support

Implements RFC 7636 for enhanced OAuth security.
"""

import base64
import hashlib
import secrets


class PKCEChallenge:
    """
    PKCE challenge generator for OAuth 2.0.

    Generates a code verifier and SHA256 challenge for the
    Authorization Code flow with PKCE extension.

    Attributes:
        code_verifier: Random string used to verify the authorization
        code_challenge: SHA256 hash of verifier, base64url encoded
        code_challenge_method: Always "S256" (SHA256)
    """

    def __init__(self):
        """Generate code verifier and challenge."""
        # Generate 43-128 character code verifier (RFC 7636)
        self.code_verifier = secrets.token_urlsafe(32)

        # Generate challenge (SHA256 hash of verifier, base64url encoded)
        digest = hashlib.sha256(self.code_verifier.encode()).digest()
        self.code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.code_challenge_method = "S256"

    def __repr__(self) -> str:
        """String representation."""
        return f"PKCEChallenge(method={self.code_challenge_method})"
