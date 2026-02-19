# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Webhook Trigger Manager — HTTP webhook-driven workflow triggers.

Pro feature gated behind FeatureFlag.WEBHOOK_TRIGGERS.
Handles registration, HMAC-SHA256 signature verification,
header/method filtering, and payload mapping.
"""

import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.licensing import FeatureFlag, LicenseError, LicenseManager

from .base import (
    BaseTriggerManager,
    TriggerConfig,
    TriggerEvent,
    TriggerStatus,
    TriggerType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================


@dataclass
class WebhookConfig(TriggerConfig):
    """Webhook-specific trigger configuration."""

    # HMAC secret for signature verification (empty = no verification)
    secret: str = ""

    # HTTP methods accepted by this webhook endpoint
    allowed_methods: List[str] = field(default_factory=lambda: ["POST"])

    # Required header key/value pairs (all must match)
    headers_filter: Dict[str, str] = field(default_factory=dict)

    # Maps webhook payload fields to workflow input params.
    # Keys = workflow param names, values = dot-separated payload paths.
    # Example: {"repo": "repository.full_name", "branch": "ref"}
    payload_mapping: Dict[str, str] = field(default_factory=dict)


# =============================================================================
# Webhook Trigger Manager
# =============================================================================


class WebhookTriggerManager(BaseTriggerManager):
    """
    Manages webhook-based workflow triggers.

    Each registered webhook gets a unique trigger_id that serves as
    its URL path segment.  Incoming HTTP requests are validated against
    the registered configuration (method, headers, HMAC signature)
    before a ``TriggerEvent`` is emitted.
    """

    def __init__(self) -> None:
        self._require_feature()
        super().__init__()

    # ── Feature gate ────────────────────────────────────────────────────

    @staticmethod
    def _require_feature() -> None:
        """Verify that the WEBHOOK_TRIGGERS feature is licensed."""
        manager = LicenseManager.get_instance()
        if not manager.has_feature(FeatureFlag.WEBHOOK_TRIGGERS):
            raise LicenseError(
                "Webhook Triggers requires a Pro license",
                feature=FeatureFlag.WEBHOOK_TRIGGERS,
            )

    # ── Registration ────────────────────────────────────────────────────

    def register_webhook(
        self,
        workflow_id: str,
        name: str,
        secret: str = "",
        allowed_methods: Optional[List[str]] = None,
        payload_mapping: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WebhookConfig:
        """
        Register a new webhook trigger for a workflow.

        Args:
            workflow_id: The workflow to execute when the webhook fires.
            name: Human-readable name for this webhook.
            secret: Shared secret for HMAC-SHA256 signature verification.
            allowed_methods: Accepted HTTP methods (default: ``["POST"]``).
            payload_mapping: Maps webhook payload paths to workflow params.
            metadata: Arbitrary extra metadata.

        Returns:
            The registered ``WebhookConfig``.
        """
        self._require_feature()

        config = WebhookConfig(
            trigger_id=str(uuid.uuid4()),
            trigger_type=TriggerType.WEBHOOK,
            workflow_id=workflow_id,
            name=name,
            secret=secret,
            allowed_methods=allowed_methods or ["POST"],
            payload_mapping=payload_mapping or {},
            metadata=metadata or {},
        )

        return self.register(config)  # type: ignore[return-value]

    # ── Signature verification ──────────────────────────────────────────

    def verify_signature(
        self,
        trigger_id: str,
        payload_bytes: bytes,
        signature: str,
    ) -> bool:
        """
        Verify an HMAC-SHA256 signature for a webhook payload.

        The expected signature format is the hex digest of
        ``HMAC-SHA256(secret, payload_bytes)``.  Leading ``sha256=``
        prefixes are stripped automatically for compatibility with
        GitHub-style signatures.

        Returns:
            ``True`` if the signature is valid (or if no secret is
            configured for this trigger).  ``False`` otherwise.
        """
        config = self.get(trigger_id)
        if config is None:
            return False

        webhook_cfg: WebhookConfig = config  # type: ignore[assignment]

        # No secret configured — skip verification
        if not webhook_cfg.secret:
            return True

        expected = hmac.new(
            webhook_cfg.secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        # Strip common prefix (e.g. "sha256=abc..." -> "abc...")
        clean_sig = signature
        if clean_sig.startswith("sha256="):
            clean_sig = clean_sig[7:]

        return hmac.compare_digest(expected, clean_sig)

    # ── Payload mapping ─────────────────────────────────────────────────

    @staticmethod
    def map_payload(
        config: WebhookConfig,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Map a raw webhook payload to workflow input params.

        Uses ``config.payload_mapping`` where keys are the workflow
        param names and values are dot-separated paths into the payload.
        If a path is missing from the payload the param is silently
        skipped.

        Example mapping::

            {"repo": "repository.full_name", "branch": "ref"}

        With payload::

            {"repository": {"full_name": "org/repo"}, "ref": "main"}

        Produces::

            {"repo": "org/repo", "branch": "main"}
        """
        if not config.payload_mapping:
            return dict(payload)

        mapped: Dict[str, Any] = {}
        for param_name, path in config.payload_mapping.items():
            value = payload
            try:
                for segment in path.split("."):
                    if isinstance(value, dict):
                        value = value[segment]
                    else:
                        raise KeyError(segment)
                mapped[param_name] = value
            except (KeyError, TypeError):
                # Path not found — skip this param
                logger.debug(
                    "Payload mapping: path '%s' not found for param '%s'",
                    path,
                    param_name,
                )
                continue

        return mapped

    # ── Processing ──────────────────────────────────────────────────────

    def process_webhook(
        self,
        trigger_id: str,
        method: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Optional[TriggerEvent]:
        """
        Validate an incoming webhook request and create a trigger event.

        Checks performed in order:
        1. Trigger exists and is ACTIVE.
        2. HTTP method is allowed.
        3. Required headers match.

        Note: HMAC signature verification should be done separately
        via ``verify_signature()`` before calling this method when the
        raw body bytes are still available.

        Args:
            trigger_id: The registered trigger to match against.
            method: HTTP method of the incoming request.
            headers: HTTP headers (keys are case-insensitive).
            payload: Parsed JSON body.

        Returns:
            A ``TriggerEvent`` if all checks pass, otherwise ``None``.
        """
        self._require_feature()

        config = self.get(trigger_id)
        if config is None:
            logger.warning("Webhook trigger not found: %s", trigger_id)
            return None

        webhook_cfg: WebhookConfig = config  # type: ignore[assignment]

        # Must be active
        if webhook_cfg.status != TriggerStatus.ACTIVE:
            logger.info(
                "Webhook trigger %s is %s, skipping",
                trigger_id,
                webhook_cfg.status.value,
            )
            return None

        # Method check
        upper_method = method.upper()
        allowed_upper = [m.upper() for m in webhook_cfg.allowed_methods]
        if upper_method not in allowed_upper:
            logger.info(
                "Webhook trigger %s: method %s not in %s",
                trigger_id,
                upper_method,
                allowed_upper,
            )
            return None

        # Headers filter — case-insensitive key matching
        lower_headers = {k.lower(): v for k, v in headers.items()}
        for req_key, req_val in webhook_cfg.headers_filter.items():
            actual = lower_headers.get(req_key.lower())
            if actual != req_val:
                logger.info(
                    "Webhook trigger %s: header '%s' mismatch "
                    "(expected '%s', got '%s')",
                    trigger_id,
                    req_key,
                    req_val,
                    actual,
                )
                return None

        # Map payload
        mapped_payload = self.map_payload(webhook_cfg, payload)

        event = TriggerEvent(
            event_id=str(uuid.uuid4()),
            trigger_id=trigger_id,
            trigger_type=TriggerType.WEBHOOK,
            workflow_id=webhook_cfg.workflow_id,
            payload=mapped_payload,
            triggered_at=datetime.utcnow(),
            metadata={
                "method": upper_method,
                "raw_payload_keys": list(payload.keys()),
            },
        )

        logger.info(
            "Webhook trigger %s fired event %s for workflow %s",
            trigger_id,
            event.event_id,
            event.workflow_id,
        )

        return event


__all__ = [
    "WebhookConfig",
    "WebhookTriggerManager",
]
