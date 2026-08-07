# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Deterministic visual comparison through a detachable TypeScript worker."""

import asyncio
import base64
import binascii
import json
import logging
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ....utils import validate_path_with_env_config
from ...registry import register_module

logger = logging.getLogger(__name__)

_WORKER_DIR = Path(__file__).parent / "visual_worker"
_WORKER_SCRIPT = _WORKER_DIR / "src" / "worker.ts"
_TSX_CLI = _WORKER_DIR / "node_modules" / "tsx" / "dist" / "cli.mjs"
_MAX_IMAGE_BYTES = 50 * 1024 * 1024
_MAX_STDOUT_BYTES = 1024 * 1024
_SAFE_ENV_VARS = frozenset(
    {"PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
)


def _scrubbed_env() -> Dict[str, str]:
    """Keep provider credentials and unrelated process state out of the worker."""
    return {key: value for key, value in os.environ.items() if key in _SAFE_ENV_VARS}


def _decode_image_input(value: str, name: str, temp_dir: Path) -> Path:
    """Materialize a PNG data URI/raw base64 value or return a local path."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty local PNG path or base64 PNG")

    if value.startswith("data:"):
        header, separator, encoded = value.partition(",")
        if not separator or header.lower() != "data:image/png;base64":
            raise ValueError(f"{name} data URI must use image/png;base64")
    else:
        candidate = Path(value).expanduser()
        if candidate.exists() or len(value) < 128 or candidate.suffix.lower() == ".png":
            # SECURITY: the caller-supplied branch is a real filesystem read, so
            # it is confined to FLYTO_SANDBOX_DIR like every other read sink
            # (data.csv.read, excel.read, pdf.parse — GHSA-wc94-386q-5478).
            return Path(validate_path_with_env_config(str(candidate)))
        encoded = value

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{name} is neither a local file nor valid base64 PNG") from exc
    if not image_bytes or len(image_bytes) > _MAX_IMAGE_BYTES:
        raise ValueError(f"{name} must contain 1-{_MAX_IMAGE_BYTES} decoded bytes")

    image_path = temp_dir / f"{name}.png"
    image_path.write_bytes(image_bytes)
    return image_path


def _ratio(value: Any, name: str, default: float) -> float:
    ratio = default if value is None else float(value)
    if not math.isfinite(ratio) or ratio < 0 or ratio > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return ratio


async def compare_visual_files(
    expected: str,
    actual: str,
    *,
    threshold: float = 0.001,
    color_threshold: float = 0.1,
    output_diff: bool = True,
    diff_path: Optional[str] = None,
    timeout_ms: int = 120_000,
) -> Dict[str, Any]:
    """Compare two real PNG inputs in a bounded, credential-free subprocess."""
    mismatch_threshold = _ratio(threshold, "threshold", 0.001)
    pixel_color_threshold = _ratio(color_threshold, "color_threshold", 0.1)
    timeout_ms = max(1, min(int(timeout_ms), 120_000))

    node_path = shutil.which("node")
    if not node_path:
        return {
            "ok": False,
            "match": False,
            "error_code": "VISUAL_WORKER_NODE_MISSING",
            "error": "Node.js 22 or newer is required for testing.visual.compare",
        }
    if not _TSX_CLI.is_file():
        return {
            "ok": False,
            "match": False,
            "error_code": "VISUAL_WORKER_DEPS_MISSING",
            "error": f"Visual worker dependencies are missing; run npm install --prefix {_WORKER_DIR}",
        }

    with tempfile.TemporaryDirectory(prefix="flyto-visual-input-") as input_dir:
        temp_dir = Path(input_dir)
        try:
            expected_path = _decode_image_input(expected, "expected", temp_dir)
            actual_path = _decode_image_input(actual, "actual", temp_dir)
        except ValueError as exc:
            return {"ok": False, "match": False, "error_code": "INVALID_IMAGE_INPUT", "error": str(exc)}

        resolved_diff_path: Optional[Path] = None
        if output_diff:
            if diff_path:
                # SECURITY: diff_path is caller-controlled and the worker writes
                # attacker-influenceable PNG bytes to it. Unvalidated, this is
                # the same arbitrary file write as browser.download save_path
                # (GHSA-p64w-hgfm-824v), so confine it to FLYTO_SANDBOX_DIR.
                resolved_diff_path = Path(validate_path_with_env_config(diff_path))
            else:
                evidence_dir = Path(tempfile.mkdtemp(prefix="flyto-visual-evidence-"))
                resolved_diff_path = evidence_dir / "diff.png"

        request = {
            "schema": "flyto.visual.compare.request.v1",
            "expectedPath": str(expected_path),
            "actualPath": str(actual_path),
            "mismatchThreshold": mismatch_threshold,
            "colorThreshold": pixel_color_threshold,
        }
        if resolved_diff_path is not None:
            request["diffPath"] = str(resolved_diff_path)

        proc = await asyncio.create_subprocess_exec(
            node_path,
            str(_TSX_CLI),
            str(_WORKER_SCRIPT),
            cwd=str(_WORKER_DIR),
            env=_scrubbed_env(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(json.dumps(request).encode("utf-8")),
                timeout=timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "ok": False,
                "match": False,
                "error_code": "VISUAL_WORKER_TIMEOUT",
                "error": f"Visual comparison timed out after {timeout_ms}ms",
            }

    if proc.returncode != 0:
        error_text = stderr.decode("utf-8", errors="replace")[:2000]
        return {
            "ok": False,
            "match": False,
            "error_code": "VISUAL_WORKER_EXITED",
            "error": f"Visual worker exited with code {proc.returncode}: {error_text}",
        }
    if len(stdout) > _MAX_STDOUT_BYTES:
        return {
            "ok": False,
            "match": False,
            "error_code": "VISUAL_WORKER_OUTPUT_LIMIT",
            "error": "Visual worker output exceeded the safety limit",
        }
    try:
        result = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "match": False,
            "error_code": "VISUAL_WORKER_INVALID_OUTPUT",
            "error": f"Visual worker returned invalid JSON: {exc}",
        }
    if not result.get("ok"):
        return {
            "ok": False,
            "match": False,
            "error_code": "VISUAL_COMPARISON_FAILED",
            "error": result.get("error", "Visual worker failed"),
        }

    return {
        "ok": True,
        "match": bool(result["match"]),
        "difference": result["differenceRatio"],
        "diff_percentage": result["differencePercent"],
        "threshold": result["mismatchThreshold"],
        "diff_image": result.get("diffPath"),
        "dimension_match": result["dimensionMatch"],
        "dimensions": result["dimensions"],
        "different_pixels": result["differentPixels"],
        "total_pixels": result["totalPixels"],
        "algorithm": result["algorithm"],
        "run_id": result["runId"],
        "evidence": result["evidence"],
    }


@register_module(
    module_id="testing.visual.compare",
    version="2.0.0",
    category="atomic",
    subcategory="testing",
    tags=["testing", "visual", "screenshot", "compare", "atomic", "deterministic"],
    label="Visual Compare",
    label_key="modules.testing.visual.compare.label",
    description="Deterministically compare PNG outputs with replayable diff evidence",
    description_key="modules.testing.visual.compare.description",
    icon="Image",
    color="#06B6D4",
    input_types=["string", "object"],
    output_types=["object"],
    can_receive_from=["browser.*", "file.*", "flow.*"],
    can_connect_to=["testing.*", "notify.*", "data.*", "flow.*", "end"],
    timeout_ms=120000,
    retryable=False,
    params_schema={
        "actual": {
            "type": "string",
            "label": "Actual Image",
            "required": True,
            "description": "Local PNG path, PNG data URI, or raw PNG base64",
            "description_key": "modules.testing.visual.compare.params.actual.description",
            "placeholder": "/path/to/actual.png",
        },
        "expected": {
            "type": "string",
            "label": "Expected Image",
            "required": True,
            "description": "Local PNG path, PNG data URI, or raw PNG base64",
            "description_key": "modules.testing.visual.compare.params.expected.description",
            "placeholder": "/path/to/expected.png",
        },
        "threshold": {
            "type": "number",
            "label": "Allowed Difference Ratio",
            "default": 0.001,
            "description": "Maximum changed-pixel ratio allowed (0-1)",
            "description_key": "modules.testing.visual.compare.params.threshold.description",
            "placeholder": "0.001",
        },
        "color_threshold": {
            "type": "number",
            "label": "Pixel Color Threshold",
            "default": 0.1,
            "description": "Per-pixel color sensitivity (0-1)",
        },
        "output_diff": {
            "type": "boolean",
            "label": "Output Diff Image",
            "default": True,
            "description": "Whether to write and return a PNG difference image",
        },
        "diff_path": {
            "type": "string",
            "label": "Diff Image Path",
            "required": False,
            "description": "Optional explicit .png evidence path",
        },
    },
    output_schema={
        "ok": {"type": "boolean", "description": "Whether comparison completed"},
        "match": {"type": "boolean", "description": "Whether the difference is within budget"},
        "difference": {"type": "number", "description": "Changed-pixel ratio (0-1)"},
        "diff_percentage": {"type": "number", "description": "Changed-pixel percentage (0-100)"},
        "diff_image": {"type": "string", "description": "PNG difference evidence path"},
        "evidence": {"type": "object", "description": "Content-addressed comparison evidence"},
    },
)
async def testing_visual_compare(context: Dict[str, Any]) -> Dict[str, Any]:
    """Run the deterministic visual comparison facade."""
    params = context.get("params", {})
    return await compare_visual_files(
        params.get("expected"),
        params.get("actual"),
        threshold=params.get("threshold", 0.001),
        color_threshold=params.get("color_threshold", 0.1),
        output_diff=params.get("output_diff", True),
        diff_path=params.get("diff_path"),
        timeout_ms=context.get("timeout_ms", 120_000),
    )
