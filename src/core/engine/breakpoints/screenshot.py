# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Screenshot Upload

Handles screenshot storage for browser.interact breakpoints.
Supports local file storage (desktop) and cloud storage (GCS/S3).
"""

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class ScreenshotUploader(Protocol):
    """Protocol for screenshot upload backends."""

    async def upload(
        self,
        data: bytes,
        breakpoint_id: str,
        media_type: str = "image/jpeg",
    ) -> str:
        """Upload screenshot bytes and return a URL."""
        ...


class LocalScreenshotUploader:
    """
    Save screenshots to local filesystem and serve via /api/screenshots/.

    For desktop (local) mode — saves to ~/.flyto/screenshots/.
    """

    def __init__(self, base_dir: Optional[str] = None, base_url: str = "/api/screenshots"):
        self._base_dir = Path(base_dir) if base_dir else Path.home() / ".flyto" / "screenshots"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._base_url = base_url.rstrip("/")

    async def upload(
        self,
        data: bytes,
        breakpoint_id: str,
        media_type: str = "image/jpeg",
    ) -> str:
        ext = "jpg" if "jpeg" in media_type else "png"
        filename = f"{breakpoint_id}.{ext}"
        filepath = self._base_dir / filename
        filepath.write_bytes(data)
        logger.debug("Screenshot saved: %s (%d bytes)", filepath, len(data))
        return f"{self._base_url}/{filename}"


class GCSScreenshotUploader:
    """
    Upload screenshots to Google Cloud Storage.

    For cloud mode — uploaded to a GCS bucket, returns signed URL.
    """

    def __init__(
        self,
        bucket_name: str = "",
        prefix: str = "breakpoints/screenshots",
        expiration: int = 3600,
    ):
        self._bucket_name = bucket_name or os.environ.get("GCS_SCREENSHOT_BUCKET", "flyto-screenshots")
        self._prefix = prefix
        self._expiration = expiration

    async def upload(
        self,
        data: bytes,
        breakpoint_id: str,
        media_type: str = "image/jpeg",
    ) -> str:
        try:
            from google.cloud import storage
            import datetime as dt

            client = storage.Client()
            bucket = client.bucket(self._bucket_name)

            ext = "jpg" if "jpeg" in media_type else "png"
            blob_name = f"{self._prefix}/{breakpoint_id}.{ext}"
            blob = bucket.blob(blob_name)
            blob.upload_from_string(data, content_type=media_type)

            url = blob.generate_signed_url(
                expiration=dt.timedelta(seconds=self._expiration),
                method="GET",
            )
            logger.debug("Screenshot uploaded to GCS: %s", blob_name)
            return url

        except ImportError:
            logger.warning("google-cloud-storage not installed, falling back to base64")
            return ""
        except Exception as e:
            logger.warning("GCS upload failed: %s, falling back to base64", e)
            return ""


class HttpScreenshotUploader:
    """
    Upload screenshots to control plane API.

    For cloud workers — POST to control plane, which stores in GCS/local.
    """

    def __init__(self, base_url: str, auth_token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token

    async def upload(
        self,
        data: bytes,
        breakpoint_id: str,
        media_type: str = "image/jpeg",
    ) -> str:
        try:
            import httpx

            headers = {"Content-Type": media_type}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/breakpoints/{breakpoint_id}/screenshot",
                    content=data,
                    headers=headers,
                )
                if resp.status_code == 200:
                    return resp.json().get("url", "")
                logger.warning("Screenshot upload failed: %s", resp.status_code)
                return ""
        except ImportError:
            logger.warning("httpx not installed for screenshot upload")
            return ""
        except Exception as e:
            logger.warning("Screenshot upload failed: %s", e)
            return ""


# Global uploader instance
_screenshot_uploader: Optional[ScreenshotUploader] = None


def get_screenshot_uploader() -> Optional[ScreenshotUploader]:
    """Get the global screenshot uploader (None = use base64 inline)."""
    return _screenshot_uploader


def set_screenshot_uploader(uploader: ScreenshotUploader) -> None:
    """Set the global screenshot uploader."""
    global _screenshot_uploader
    _screenshot_uploader = uploader


def auto_configure_screenshot_uploader() -> Optional[ScreenshotUploader]:
    """
    Auto-detect deployment mode and configure the screenshot uploader.

    Environment variables:
    - DEPLOYMENT_MODE: "local", "cloud", "worker"
    - CONTROL_PLANE_URL: for worker mode (uploads via HTTP)
    - GCS_SCREENSHOT_BUCKET: for cloud mode (uploads to GCS)

    Returns:
        Configured uploader (also set as global), or None for local inline base64
    """
    mode = os.environ.get("DEPLOYMENT_MODE", "local")
    uploader = None

    if mode == "worker":
        control_plane_url = os.environ.get("CONTROL_PLANE_URL", "")
        if control_plane_url:
            auth_token = os.environ.get("WORKER_AUTH_TOKEN", "")
            uploader = HttpScreenshotUploader(control_plane_url, auth_token)
            logger.info("Screenshot uploader: HTTP → %s", control_plane_url[:30])

    elif mode == "cloud":
        bucket = os.environ.get("GCS_SCREENSHOT_BUCKET", "")
        if bucket:
            uploader = GCSScreenshotUploader(bucket_name=bucket)
            logger.info("Screenshot uploader: GCS bucket=%s", bucket)
        else:
            uploader = LocalScreenshotUploader()
            logger.info("Screenshot uploader: local filesystem")

    else:
        # Local mode: no uploader, use inline base64 (original behavior)
        logger.debug("Screenshot uploader: none (local mode, inline base64)")
        return None

    if uploader:
        set_screenshot_uploader(uploader)
    return uploader
