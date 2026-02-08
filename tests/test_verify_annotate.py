"""
Tests for verify.annotate module — real Pillow image processing, no mocks.

Tests:
- Single annotation draws correctly
- Multiple annotations with auto-labeling (A, B, C)
- Custom colors
- Output file creation and size
- Missing image error handling
- Empty annotations error
"""
import os
import tempfile
import pytest
from pathlib import Path

# Ensure Pillow is available
pytest.importorskip("PIL", reason="Pillow required for verify.annotate tests")

from PIL import Image

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.modules.atomic.verify.annotate import draw_annotations, VerifyAnnotateModule


@pytest.fixture
def test_image(tmp_path):
    """Create a real 800x600 test image with some content."""
    img = Image.new("RGB", (800, 600), color=(240, 240, 240))
    # Draw some colored rectangles to simulate page content
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 20, 750, 80], fill=(30, 30, 120))   # header
    draw.rectangle([50, 100, 350, 300], fill=(255, 255, 255))  # form
    draw.rectangle([50, 320, 200, 360], fill=(0, 120, 255))   # button
    draw.text((100, 40), "Header", fill=(255, 255, 255))

    img_path = str(tmp_path / "test_page.png")
    img.save(img_path)
    return img_path


@pytest.fixture
def output_path(tmp_path):
    return str(tmp_path / "annotated.png")


# =============================================================================
# Unit: draw_annotations function
# =============================================================================

class TestDrawAnnotations:
    def test_single_annotation(self, test_image, output_path):
        """Draw one annotation and verify output exists."""
        annotations = [
            {"label": "A", "x": 50, "y": 320, "width": 150, "height": 40, "description": "Button color wrong"}
        ]
        result = draw_annotations(test_image, annotations, output_path)

        assert result["annotation_count"] == 1
        assert os.path.exists(result["output_path"])
        # Verify image dimensions match original
        img = Image.open(result["output_path"])
        assert img.size == (800, 600)
        img.close()

    def test_multiple_annotations(self, test_image, output_path):
        """Draw 5 annotations with auto-labeling."""
        annotations = [
            {"label": "A", "x": 50, "y": 20, "width": 700, "height": 60, "description": "Header background"},
            {"label": "B", "x": 50, "y": 100, "width": 300, "height": 200, "description": "Form layout"},
            {"label": "C", "x": 50, "y": 320, "width": 150, "height": 40, "description": "Button style"},
            {"label": "D", "x": 400, "y": 100, "width": 350, "height": 200, "description": "Missing sidebar"},
            {"label": "E", "x": 0, "y": 560, "width": 800, "height": 40, "description": "Footer missing"},
        ]
        result = draw_annotations(test_image, annotations, output_path)
        assert result["annotation_count"] == 5
        assert os.path.exists(output_path)

    def test_custom_hex_colors(self, test_image, output_path):
        """Custom hex colors for annotations."""
        annotations = [
            {"label": "X", "x": 100, "y": 100, "width": 200, "height": 100, "color": "#FF0000"},
            {"label": "Y", "x": 400, "y": 100, "width": 200, "height": 100, "color": "#00FF00"},
        ]
        result = draw_annotations(test_image, annotations, output_path)
        assert result["annotation_count"] == 2
        assert os.path.exists(output_path)

    def test_output_directory_created(self, test_image, tmp_path):
        """Output directory is created if it doesn't exist."""
        deep_path = str(tmp_path / "a" / "b" / "c" / "annotated.png")
        annotations = [{"label": "A", "x": 0, "y": 0, "width": 50, "height": 50}]
        result = draw_annotations(test_image, annotations, deep_path)
        assert os.path.exists(deep_path)

    def test_large_annotation_count(self, test_image, output_path):
        """Test with more annotations than colors in palette (cycles)."""
        annotations = [
            {"label": chr(65 + i), "x": 10 + (i % 4) * 200, "y": 10 + (i // 4) * 100, "width": 180, "height": 80}
            for i in range(12)
        ]
        result = draw_annotations(test_image, annotations, output_path)
        assert result["annotation_count"] == 12

    def test_annotation_with_long_description(self, test_image, output_path):
        """Long description is truncated (not crash)."""
        annotations = [{
            "label": "A",
            "x": 50, "y": 50, "width": 100, "height": 50,
            "description": "A" * 200,  # very long
        }]
        result = draw_annotations(test_image, annotations, output_path)
        assert result["annotation_count"] == 1

    def test_zero_size_annotation(self, test_image, output_path):
        """Zero-size annotation doesn't crash."""
        annotations = [{"label": "Z", "x": 100, "y": 100, "width": 0, "height": 0}]
        result = draw_annotations(test_image, annotations, output_path)
        assert result["annotation_count"] == 1


# =============================================================================
# Unit: VerifyAnnotateModule
# =============================================================================

class TestVerifyAnnotateModule:
    @pytest.mark.asyncio
    async def test_module_execute(self, test_image, tmp_path):
        """Module executes and returns correct result structure."""
        output = str(tmp_path / "mod_output.png")
        module = VerifyAnnotateModule(
            params={
                "image_path": test_image,
                "annotations": [
                    {"label": "A", "x": 50, "y": 50, "width": 100, "height": 100, "description": "Test"},
                ],
                "output_path": output,
            },
            context={},
        )
        module.validate_params()
        result = await module.execute()

        assert result["ok"] is True
        assert result["data"]["annotation_count"] == 1
        assert os.path.exists(result["data"]["output_path"])

    @pytest.mark.asyncio
    async def test_module_default_output_path(self, test_image):
        """Module generates default output path with _annotated suffix."""
        module = VerifyAnnotateModule(
            params={
                "image_path": test_image,
                "annotations": [{"label": "A", "x": 0, "y": 0, "width": 50, "height": 50}],
            },
            context={},
        )
        module.validate_params()
        result = await module.execute()

        assert result["ok"] is True
        assert "_annotated" in result["data"]["output_path"]
        assert os.path.exists(result["data"]["output_path"])
        # Cleanup
        os.remove(result["data"]["output_path"])

    @pytest.mark.asyncio
    async def test_module_missing_image(self, tmp_path):
        """Module returns error for non-existent image."""
        module = VerifyAnnotateModule(
            params={
                "image_path": str(tmp_path / "nonexistent.png"),
                "annotations": [{"label": "A", "x": 0, "y": 0, "width": 50, "height": 50}],
            },
            context={},
        )
        module.validate_params()
        result = await module.execute()
        assert result["ok"] is False

    def test_module_validate_missing_annotations(self, test_image):
        """Validation fails if annotations is empty."""
        with pytest.raises(ValueError, match="annotations"):
            VerifyAnnotateModule(
                params={"image_path": test_image, "annotations": []},
                context={},
            )

    def test_module_validate_missing_image_path(self):
        """Validation fails if image_path is missing."""
        with pytest.raises(ValueError, match="image_path"):
            VerifyAnnotateModule(
                params={"annotations": [{"label": "A", "x": 0, "y": 0, "width": 50, "height": 50}]},
                context={},
            )


# =============================================================================
# Composite: round-trip (create image → annotate → read back → verify pixels)
# =============================================================================

class TestAnnotateRoundTrip:
    def test_annotation_modifies_pixels(self, test_image, output_path):
        """Annotated image should differ from original at annotation coordinates."""
        annotations = [{"label": "A", "x": 100, "y": 100, "width": 200, "height": 100, "color": "#FF0000"}]
        draw_annotations(test_image, annotations, output_path)

        original = Image.open(test_image).convert("RGB")
        annotated = Image.open(output_path).convert("RGB")

        # Sample pixel at center of annotation (150, 150)
        orig_pixel = original.getpixel((150, 150))
        ann_pixel = annotated.getpixel((150, 150))

        # The annotated pixel should have red tint from the overlay
        assert ann_pixel != orig_pixel, f"Pixel should differ: orig={orig_pixel} ann={ann_pixel}"

        original.close()
        annotated.close()

    def test_annotation_preserves_untouched_areas(self, test_image, output_path):
        """Pixels far from annotations should be unchanged."""
        annotations = [{"label": "A", "x": 0, "y": 0, "width": 50, "height": 50}]
        draw_annotations(test_image, annotations, output_path)

        original = Image.open(test_image).convert("RGB")
        annotated = Image.open(output_path).convert("RGB")

        # Sample pixel far from annotation (700, 500)
        orig_pixel = original.getpixel((700, 500))
        ann_pixel = annotated.getpixel((700, 500))
        assert orig_pixel == ann_pixel, f"Untouched pixel should match: orig={orig_pixel} ann={ann_pixel}"

        original.close()
        annotated.close()
