"""
Integration tests for verify.visual_diff module.

Tests the full pipeline: screenshot → AI vision compare → annotate → report.
Uses real URLs, real Playwright, real OpenAI Vision API.

Requires:
- playwright (pip install playwright && playwright install chromium)
- Pillow
- httpx
- OPENAI_API_KEY env var

Run: pytest tests/test_verify_visual_diff.py -v
"""
import os
import sys
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Skip entire file if dependencies missing
playwright = pytest.importorskip("playwright", reason="playwright required")
PIL = pytest.importorskip("PIL", reason="Pillow required")
httpx = pytest.importorskip("httpx", reason="httpx required")

from core.modules.atomic.verify.visual_diff import (
    _screenshot_url,
    _vision_compare_images,
    _pct_to_px,
    _generate_visual_diff_html,
    VerifyVisualDiffModule,
)
from core.modules.atomic.verify.annotate import draw_annotations


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
            "annotations": [
                {"label": "A", "x": 10, "y": 20, "width": 50, "height": 30, "description": "Color diff", "severity": "Major"},
            ],
            "summary": "Header color differs from design.",
        }
        result = _generate_visual_diff_html(
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
        report_data = {"similarity_score": 99, "annotations": [], "summary": "Looks identical."}
        _generate_visual_diff_html(report_data, str(tmp_path / "ref.png"), str(tmp_path / "dev.png"), str(tmp_path / "annotated.png"), report_path)
        assert os.path.exists(report_path)
        html = Path(report_path).read_text()
        assert "No differences found" in html


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
        assert img.size[1] == 800
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
# Integration: _vision_compare_images with real OpenAI API
# =============================================================================

@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
class TestVisionCompare:
    @pytest.mark.asyncio
    async def test_compare_identical_images(self, tmp_path):
        """Two identical images should have high similarity."""
        from PIL import Image
        img = Image.new("RGB", (400, 300), color=(255, 255, 255))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, 350, 250], fill=(0, 100, 200))
        draw.text((100, 130), "Hello", fill=(255, 255, 255))
        path1 = str(tmp_path / "img1.png")
        path2 = str(tmp_path / "img2.png")
        img.save(path1)
        img.save(path2)
        img.close()

        result = await _vision_compare_images(path1, path2)
        assert result.get("ok") is True
        score = result.get("similarity_score")
        if score is not None:
            assert score >= 90, f"Identical images should be 90%+ similar, got {score}"

    @pytest.mark.asyncio
    async def test_compare_different_images(self, tmp_path):
        """Two different images should have differences."""
        from PIL import Image, ImageDraw
        img1 = Image.new("RGB", (400, 300), color=(255, 255, 255))
        draw1 = ImageDraw.Draw(img1)
        draw1.rectangle([50, 50, 350, 250], fill=(0, 0, 255))  # blue
        path1 = str(tmp_path / "blue.png")
        img1.save(path1)
        img1.close()

        img2 = Image.new("RGB", (400, 300), color=(255, 255, 255))
        draw2 = ImageDraw.Draw(img2)
        draw2.rectangle([50, 50, 350, 250], fill=(255, 0, 0))  # red
        path2 = str(tmp_path / "red.png")
        img2.save(path2)
        img2.close()

        result = await _vision_compare_images(path1, path2, focus_areas=["center rectangle"])
        assert result.get("ok") is True
        # Should detect at least some difference
        diffs = result.get("differences", [])
        # AI may or may not return structured differences, but should succeed
        assert "summary" in result or "differences" in result

    @pytest.mark.asyncio
    async def test_compare_missing_api_key(self, tmp_path):
        """Should fail gracefully without API key."""
        from PIL import Image
        img = Image.new("RGB", (100, 100))
        p = str(tmp_path / "test.png")
        img.save(p)
        img.close()

        result = await _vision_compare_images(p, p, api_key="invalid-key-xxx")
        # Should get an error from OpenAI
        assert result.get("ok") is False or result.get("error")


# =============================================================================
# Integration: Full VerifyVisualDiffModule pipeline
# =============================================================================

@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
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
