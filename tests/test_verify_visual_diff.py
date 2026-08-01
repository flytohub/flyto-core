"""
Integration tests for verify.visual_diff module.

Tests the full pipeline: screenshot → deterministic TypeScript comparison → report.
Uses real URLs, real Playwright, and the real visual worker subprocess.

Requires:
- playwright (pip install playwright && playwright install chromium)
- Pillow
- npm install in src/core/modules/atomic/testing/visual_worker

Run: pytest tests/test_verify_visual_diff.py -v
"""
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Skip entire file if dependencies missing
playwright = pytest.importorskip("playwright", reason="playwright required")
PIL = pytest.importorskip("PIL", reason="Pillow required")
from core.modules.atomic.verify.visual_diff import (  # noqa: E402
    VerifyVisualDiffModule,
    _generate_visual_diff_html,
    _pct_to_px,
    _screenshot_url,
)
from core.modules.composite.test.ui_review import UIReview  # noqa: E402

# =============================================================================
# Unit: _pct_to_px conversion
# =============================================================================

class TestPctToPx:
    def test_basic_conversion(self):
        """Convert percentage coordinates to pixels."""
        diffs = [{"label": "A", "x_pct": 10, "y_pct": 20, "w_pct": 30, "h_pct": 10, "description": "test"}]
        result = _pct_to_px(diffs, 1280, 800)
        assert len(result) == 1
        assert result[0]["label"] == "A"
        assert result[0]["x"] == 128    # 10% of 1280
        assert result[0]["y"] == 160    # 20% of 800
        assert result[0]["width"] == 384  # 30% of 1280
        assert result[0]["height"] == 80  # 10% of 800
        assert result[0]["description"] == "test"

    def test_zero_percent(self):
        """0% maps to 0px."""
        diffs = [{"label": "Z", "x_pct": 0, "y_pct": 0, "w_pct": 0, "h_pct": 0}]
        result = _pct_to_px(diffs, 1920, 1080)
        assert result[0]["x"] == 0
        assert result[0]["y"] == 0

    def test_full_percent(self):
        """100% maps to full dimension."""
        diffs = [{"label": "F", "x_pct": 0, "y_pct": 0, "w_pct": 100, "h_pct": 100}]
        result = _pct_to_px(diffs, 800, 600)
        assert result[0]["width"] == 800
        assert result[0]["height"] == 600

    def test_empty_list(self):
        """Empty input returns empty output."""
        assert _pct_to_px([], 1280, 800) == []

    def test_multiple_differences(self):
        """Multiple differences converted correctly."""
        diffs = [
            {"label": "A", "x_pct": 10, "y_pct": 10, "w_pct": 20, "h_pct": 5},
            {"label": "B", "x_pct": 50, "y_pct": 50, "w_pct": 10, "h_pct": 10},
        ]
        result = _pct_to_px(diffs, 1000, 1000)
        assert len(result) == 2
        assert result[0]["x"] == 100
        assert result[1]["x"] == 500


# =============================================================================
# Unit: _generate_visual_diff_html
# =============================================================================

class TestGenerateReport:
    def test_generates_html_file(self, tmp_path):
        """HTML report is created with correct content."""
        # Create dummy screenshots
        from PIL import Image
        for name in ["ref.png", "dev.png", "annotated.png"]:
            img = Image.new("RGB", (100, 100), color=(200, 200, 200))
            img.save(str(tmp_path / name))
            img.close()

        report_path = str(tmp_path / "report.html")
        report_data = {
            "similarity_score": 82,
            "passed": False,
            "difference_percentage": 18,
            "threshold_percentage": 0.1,
            "algorithm": "pixelmatch@7.2.0",
            "run_id": "run-123",
            "annotations": [
                {"label": "A", "x": 10, "y": 20, "width": 50, "height": 30, "description": "Color diff", "severity": "Major"},
            ],
            "summary": "Header color differs from design.",
        }
        _generate_visual_diff_html(
            report_data,
            str(tmp_path / "ref.png"),
            str(tmp_path / "dev.png"),
            str(tmp_path / "annotated.png"),
            report_path,
        )
        assert os.path.exists(report_path)
        html = Path(report_path).read_text()
        assert "82%" in html
        assert "Color diff" in html
        assert "Header color differs" in html
        assert "ref.png" in html
        assert "annotated.png" in html

    def test_no_annotations_report(self, tmp_path):
        """Report with zero differences still generates."""
        from PIL import Image
        for name in ["ref.png", "dev.png", "annotated.png"]:
            img = Image.new("RGB", (100, 100))
            img.save(str(tmp_path / name))
            img.close()

        report_path = str(tmp_path / "empty_report.html")
        report_data = {
            "similarity_score": 99,
            "passed": True,
            "difference_percentage": 0,
            "threshold_percentage": 0.1,
            "annotations": [],
            "summary": "Looks identical.",
        }
        _generate_visual_diff_html(report_data, str(tmp_path / "ref.png"), str(tmp_path / "dev.png"), str(tmp_path / "annotated.png"), report_path)
        assert os.path.exists(report_path)
        html = Path(report_path).read_text()
        assert "No differences found" in html

    def test_untrusted_report_text_is_html_escaped(self, tmp_path):
        report_path = str(tmp_path / "escaped.html")
        report_data = {
            "similarity_score": 0,
            "passed": False,
            "annotations": [{"label": "<img src=x>", "description": "<script>alert(1)</script>"}],
            "summary": "<svg onload=alert(1)>",
        }
        _generate_visual_diff_html(report_data, "ref.png", "dev.png", "diff.png", report_path)
        rendered = Path(report_path).read_text()
        assert "<script>alert(1)</script>" not in rendered
        assert "<svg onload=alert(1)>" not in rendered
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


class TestUIReviewFailClosed:
    def test_missing_comparison_cannot_be_reported_as_passed(self):
        review = UIReview(params={}, context={})
        review.step_results = {"screenshot": {"path": "current.png"}}

        result = review._build_output({})

        assert result["status"] == "failed"
        assert result["passed"] is False
        assert result["diff_percentage"] is None

    def test_real_ratio_and_percentage_contract_are_not_confused(self):
        review = UIReview(params={"diff_threshold": 0.001}, context={})
        review.step_results = {
            "compare": {"ok": True, "match": True, "difference": 0.0005, "diff_percentage": 0.05}
        }

        result = review._build_output({})

        assert result["passed"] is True
        assert result["diff_percentage"] == 0.05


# =============================================================================
# Integration: _screenshot_url with real Playwright
# =============================================================================

class TestScreenshotUrl:
    @pytest.mark.asyncio
    async def test_screenshot_public_url(self, tmp_path):
        """Screenshot a real public URL."""
        output = str(tmp_path / "screenshot.png")
        result = await _screenshot_url("https://example.com", output)
        assert os.path.exists(result)
        from PIL import Image
        img = Image.open(result)
        assert img.size[0] == 1280  # default viewport
        assert img.size[1] >= 800
        img.close()

    @pytest.mark.asyncio
    async def test_screenshot_custom_viewport(self, tmp_path):
        """Screenshot with custom viewport size."""
        output = str(tmp_path / "mobile.png")
        await _screenshot_url("https://example.com", output, viewport_width=375, viewport_height=667)
        from PIL import Image
        img = Image.open(output)
        assert img.size == (375, 667)
        img.close()


# =============================================================================
# Integration: Full VerifyVisualDiffModule pipeline
# =============================================================================

class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_compare_two_urls(self, tmp_path):
        """Full pipeline: compare example.com with itself (should be ~100% similar)."""
        module = VerifyVisualDiffModule(
            params={
                "reference_url": "https://example.com",
                "dev_url": "https://example.com",
                "output_dir": str(tmp_path / "report"),
            },
            context={},
        )
        module.validate_params()
        result = await module.execute()

        assert result["ok"] is True
        data = result["data"]
        assert "similarity_score" in data
        assert data["passed"] is True
        assert data["advisory"]["owner"] == "flyto-ai"
        assert data["advisory"]["can_override_gate"] is False
        assert "annotations" in data
        assert "annotated_image" in data
        assert "report_path" in data
        assert "summary" in data
        assert os.path.exists(data["annotated_image"])
        assert os.path.exists(data["report_path"])

        # Report should be valid HTML
        html = Path(data["report_path"]).read_text()
        assert "Visual Diff Report" in html

    @pytest.mark.asyncio
    async def test_compare_url_with_local_image(self, tmp_path):
        """Pipeline with local image as reference."""
        # Create a simple reference image
        from PIL import Image
        ref = Image.new("RGB", (1280, 800), color=(200, 200, 200))
        ref_path = str(tmp_path / "reference.png")
        ref.save(ref_path)
        ref.close()

        module = VerifyVisualDiffModule(
            params={
                "reference_url": ref_path,
                "dev_url": "https://example.com",
                "output_dir": str(tmp_path / "mixed"),
            },
            context={},
        )
        module.validate_params()
        result = await module.execute()

        assert result["ok"] is True
        assert os.path.exists(result["data"]["annotated_image"])

    def test_validate_missing_reference(self):
        """Validation fails without reference_url."""
        with pytest.raises(ValueError, match="reference_url"):
            VerifyVisualDiffModule(
                params={"dev_url": "https://example.com"},
                context={},
            )

    def test_validate_missing_dev_url(self):
        """Validation fails without dev_url."""
        with pytest.raises(ValueError, match="dev_url"):
            VerifyVisualDiffModule(
                params={"reference_url": "https://example.com"},
                context={},
            )
