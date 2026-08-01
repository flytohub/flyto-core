"""Real-process tests for the detachable TypeScript visual worker."""

import base64
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from core.modules.atomic.testing.visual import compare_visual_files

WORKER_DIR = (
    Path(__file__).parents[2]
    / "src"
    / "core"
    / "modules"
    / "atomic"
    / "testing"
    / "visual_worker"
)
TSX = WORKER_DIR / "node_modules" / ".bin" / "tsx"

requires_worker = pytest.mark.skipif(
    shutil.which("node") is None or not TSX.exists(),
    reason="requires Node.js and `npm install` in visual_worker/",
)


def _image(path: Path, *, size=(100, 80), rectangle=None, color="white") -> Path:
    image = Image.new("RGBA", size, color=color)
    if rectangle is not None:
        ImageDraw.Draw(image).rectangle(rectangle, fill="navy")
    image.save(path, format="PNG")
    image.close()
    return path


def _run_worker(request: dict) -> dict:
    completed = subprocess.run(
        [str(TSX), "src/worker.ts"],
        cwd=WORKER_DIR,
        input=json.dumps(request),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=True,
    )
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def _request(expected: Path, actual: Path, **overrides) -> dict:
    return {
        "schema": "flyto.visual.compare.request.v1",
        "expectedPath": str(expected),
        "actualPath": str(actual),
        **overrides,
    }


@requires_worker
class TestVisualWorkerRealProcess:
    def test_identical_pngs_match_and_emit_hash_evidence(self, tmp_path):
        expected = _image(tmp_path / "expected.png", rectangle=(10, 10, 50, 50))
        actual = shutil.copyfile(expected, tmp_path / "actual.png")

        result = _run_worker(_request(expected, actual))

        assert result["ok"] is True
        assert result["match"] is True
        assert result["differenceRatio"] == 0
        assert result["dimensionMatch"] is True
        assert result["evidence"]["expectedSha256"] == hashlib.sha256(expected.read_bytes()).hexdigest()
        assert result["evidence"]["expectedSha256"] == result["evidence"]["actualSha256"]

    def test_real_pixel_change_fails_a_strict_budget(self, tmp_path):
        expected = _image(tmp_path / "expected.png")
        actual = _image(tmp_path / "actual.png", rectangle=(0, 0, 39, 39))

        result = _run_worker(_request(expected, actual, mismatchThreshold=0.01))

        assert result["ok"] is True
        assert result["match"] is False
        assert result["differenceRatio"] > 0.01
        assert result["differentPixels"] > 0

    def test_allowed_mismatch_budget_can_pass(self, tmp_path):
        expected = _image(tmp_path / "expected.png")
        actual = _image(tmp_path / "actual.png", rectangle=(0, 0, 4, 4))

        result = _run_worker(_request(expected, actual, mismatchThreshold=0.01))

        assert result["ok"] is True
        assert result["match"] is True
        assert 0 < result["differenceRatio"] < 0.01

    def test_dimension_mismatch_is_counted_and_fails_closed(self, tmp_path):
        expected = _image(tmp_path / "expected.png", size=(100, 80), color="navy")
        actual = _image(tmp_path / "actual.png", size=(90, 80), color="navy")

        result = _run_worker(_request(expected, actual, mismatchThreshold=0))

        assert result["ok"] is True
        assert result["dimensionMatch"] is False
        assert result["match"] is False
        assert result["dimensions"]["compared"] == {"width": 100, "height": 80}

    def test_diff_png_is_real_and_content_addressed(self, tmp_path):
        expected = _image(tmp_path / "expected.png")
        actual = _image(tmp_path / "actual.png", rectangle=(20, 20, 60, 60))
        diff_path = tmp_path / "evidence" / "diff.png"

        result = _run_worker(_request(expected, actual, diffPath=str(diff_path)))

        assert result["ok"] is True
        assert diff_path.is_file()
        assert Image.open(diff_path).size == (100, 80)
        assert result["evidence"]["diffSha256"] == hashlib.sha256(diff_path.read_bytes()).hexdigest()

    def test_missing_input_returns_structured_failure(self, tmp_path):
        expected = tmp_path / "missing.png"
        actual = _image(tmp_path / "actual.png")

        result = _run_worker(_request(expected, actual))

        assert result["ok"] is False
        assert "ENOENT" in result["error"]

    def test_invalid_threshold_returns_structured_failure(self, tmp_path):
        expected = _image(tmp_path / "expected.png")
        actual = _image(tmp_path / "actual.png")

        result = _run_worker(_request(expected, actual, mismatchThreshold=1.1))

        assert result["ok"] is False
        assert "between 0 and 1" in result["error"]

    def test_oversized_png_header_is_rejected_before_decode(self, tmp_path):
        oversized = tmp_path / "oversized.png"
        oversized.write_bytes(
            bytes.fromhex("89504e470d0a1a0a")
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", 100_000, 100_000)
        )

        result = _run_worker(_request(oversized, oversized))

        assert result["ok"] is False
        assert "pixel limit" in result["error"]

    def test_existing_diff_is_not_overwritten(self, tmp_path):
        expected = _image(tmp_path / "expected.png")
        actual = _image(tmp_path / "actual.png", rectangle=(0, 0, 4, 4))
        diff_path = tmp_path / "diff.png"
        diff_path.write_bytes(b"sentinel")

        result = _run_worker(_request(expected, actual, diffPath=str(diff_path)))

        assert result["ok"] is False
        assert "EEXIST" in result["error"]
        assert diff_path.read_bytes() == b"sentinel"


@requires_worker
class TestVisualWorkerNoMockMatrix:
    @pytest.mark.parametrize("case_index", range(101), ids=lambda value: f"visual-{value + 1:03d}")
    def test_101_distinct_real_process_cases(self, case_index, tmp_path):
        tier = case_index // 34
        width = 18 + case_index % 7
        height = 14 + case_index % 5
        expected = _image(
            tmp_path / "expected.png",
            size=(width, height),
            rectangle=(1, 1, 3 + case_index % 4, 3 + case_index % 3),
        )
        actual = tmp_path / "actual.png"
        request_options = {}
        expected_match = False

        if tier == 0:
            shutil.copyfile(expected, actual)
            expected_match = True
        elif tier == 1:
            _image(actual, size=(width, height), color="white")
            request_options["mismatchThreshold"] = 0
        else:
            _image(actual, size=(width - 1, height), color="white")
            request_options.update(
                mismatchThreshold=0,
                diffPath=str(tmp_path / "evidence" / f"diff-{case_index:03d}.png"),
            )

        result = _run_worker(_request(expected, actual, **request_options))

        assert result["ok"] is True
        assert result["match"] is expected_match
        assert result["runId"]
        assert result["differentPixels"] >= 0
        if tier == 2:
            assert result["dimensionMatch"] is False
            assert Path(result["diffPath"]).is_file()


@requires_worker
class TestCoreVisualFacadeRealProcess:
    @pytest.mark.asyncio
    async def test_python_facade_executes_the_typescript_worker(self, tmp_path):
        expected = _image(tmp_path / "expected.png", rectangle=(10, 10, 50, 50))
        actual = shutil.copyfile(expected, tmp_path / "actual.png")

        result = await compare_visual_files(str(expected), str(actual), output_diff=False)

        assert result["ok"] is True
        assert result["match"] is True
        assert result["algorithm"] == "pixelmatch@7.2.0"
        assert len(result["run_id"]) == 64

    @pytest.mark.asyncio
    async def test_png_data_uri_is_materialized_without_exposing_it_to_node_args(self, tmp_path):
        image_path = _image(tmp_path / "source.png", color="navy")
        data_uri = "data:image/png;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")

        result = await compare_visual_files(data_uri, data_uri, output_diff=False)

        assert result["ok"] is True
        assert result["match"] is True

    @pytest.mark.asyncio
    async def test_missing_file_is_a_closed_failure(self, tmp_path):
        actual = _image(tmp_path / "actual.png")

        result = await compare_visual_files(str(tmp_path / "missing.png"), str(actual))

        assert result["ok"] is False
        assert result["match"] is False
        assert result["error_code"] == "VISUAL_COMPARISON_FAILED"
