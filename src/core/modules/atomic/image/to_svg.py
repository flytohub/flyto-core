"""
Image to SVG Converter - Atomic Module
Converts raster images (PNG/JPG) to SVG vector format using vtracer.
"""
from typing import Dict, Any
from pathlib import Path
from src.core.modules.base import BaseModule
from src.core.modules.registry import register_module


@register_module('image.to_svg')
class ImageToSvgModule(BaseModule):
    """
    Convert raster image to SVG vector format

    Params:
        input (str): Path to input raster image (PNG/JPG)
        output (str): Path to output SVG file
        colors (int): Number of colors for vectorization (default: 16)
        mode (str): 'color' or 'binary' (default: 'color')

    Returns:
        dict: {'ok': bool, 'output': str, 'error': str or None}
    """

    module_name = "Image to SVG"
    module_description = "Convert raster image to SVG vector format"

    def validate_params(self):
        required = ['input', 'output']
        for param in required:
            if param not in self.params:
                raise ValueError(f"Missing required parameter: {param}")

        self.input_path = Path(self.params['input'])
        self.output_path = Path(self.params['output'])
        self.colors = self.params.get('colors', 16)
        self.mode = self.params.get('mode', 'color')

        if not self.input_path.exists():
            raise FileNotFoundError(f"Input not found: {self.input_path}")

    async def execute(self) -> Dict[str, Any]:
        try:
            import vtracer

            vtracer.convert_image_to_svg_py(
                str(self.input_path),
                str(self.output_path),
                colormode=self.mode,
                hierarchical='stacked',
                mode='spline',
                filter_speckle=4,
                color_precision=6,
                layer_difference=16,
                corner_threshold=60,
                length_threshold=4.0,
                max_iterations=10,
                splice_threshold=45,
                path_precision=3
            )

            return {
                'ok': True,
                'output': str(self.output_path),
                'error': None
            }
        except ImportError:
            return {
                'ok': False,
                'output': None,
                'error': 'vtracer not installed. Run: pip install vtracer'
            }
        except Exception as e:
            return {
                'ok': False,
                'output': None,
                'error': str(e)
            }
