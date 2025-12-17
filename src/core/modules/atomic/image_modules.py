"""
Image Processing Atomic Modules
Following atomic module standards - single responsibility, no coupling
"""
from typing import Dict, Any
from pathlib import Path
from core.modules.base import BaseModule
from core.modules.registry import register_module


@register_module('image.compress')
class ImageCompressModule(BaseModule):
    """
    Compress image to reduce file size

    Params:
        input (str): Path to input image file
        output (str): Path to output compressed image
        quality (int): Compression quality 1-100 (optional, default: 85)

    Returns:
        dict: {
            'status': 'success',
            'original_size': int (bytes),
            'compressed_size': int (bytes),
            'reduction': float (percentage)
        }

    Example:
        ```yaml
        - id: compress
          module: image.compress
          params:
            input: photo.jpg
            output: photo_compressed.jpg
            quality: 85
        ```
    """

    module_name = "Image Compress"
    module_description = "Compress image to reduce file size"

    def validate_params(self):
        """Validate parameters"""
        required = ['input', 'output']
        for param in required:
            if param not in self.params:
                raise ValueError(f"Missing required parameter: {param}")

        self.input_path = Path(self.params['input'])
        self.output_path = Path(self.params['output'])
        self.quality = self.params.get('quality', 85)

        if not self.input_path.exists():
            raise FileNotFoundError(f"Input image not found: {self.input_path}")

        if not (1 <= self.quality <= 100):
            raise ValueError(f"Quality must be 1-100, got: {self.quality}")

    async def execute(self) -> Dict[str, Any]:
        """Execute image compression"""
        try:
            from PIL import Image

            # Get original size
            original_size = self.input_path.stat().st_size

            # Open and compress
            with Image.open(self.input_path) as img:
                # Convert RGBA to RGB if needed
                if img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = rgb_img

                # Save with compression
                img.save(
                    self.output_path,
                    'JPEG',
                    quality=self.quality,
                    optimize=True
                )

            # Get compressed size
            compressed_size = self.output_path.stat().st_size
            reduction = ((original_size - compressed_size) / original_size) * 100

            return {
                'status': 'success',
                'original_size': original_size,
                'compressed_size': compressed_size,
                'reduction': round(reduction, 2),
                'output': str(self.output_path)
            }

        except ImportError:
            return {
                'status': 'error',
                'error': 'PIL (Pillow) not installed. Run: pip install Pillow',
                'error_type': 'DependencyError'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }


@register_module('image.convert')
class ImageConvertModule(BaseModule):
    """
    Convert image format (jpg, png, webp, etc)

    Params:
        input (str): Path to input image file
        output (str): Path to output image (extension determines format)
        quality (int): Quality for lossy formats (optional, default: 95)

    Returns:
        dict: {
            'status': 'success',
            'from_format': str,
            'to_format': str,
            'size': int (bytes)
        }

    Example:
        ```yaml
        - id: convert
          module: image.convert
          params:
            input: photo.jpg
            output: photo.png
        ```
    """

    module_name = "Image Convert"
    module_description = "Convert image format (jpg→png, png→webp, etc)"

    def validate_params(self):
        """Validate parameters"""
        required = ['input', 'output']
        for param in required:
            if param not in self.params:
                raise ValueError(f"Missing required parameter: {param}")

        self.input_path = Path(self.params['input'])
        self.output_path = Path(self.params['output'])
        self.quality = self.params.get('quality', 95)

        if not self.input_path.exists():
            raise FileNotFoundError(f"Input image not found: {self.input_path}")

    async def execute(self) -> Dict[str, Any]:
        """Execute image format conversion"""
        try:
            from PIL import Image

            # Determine formats
            from_format = self.input_path.suffix.lstrip('.').upper()
            to_format = self.output_path.suffix.lstrip('.').upper()

            # Normalize format names
            format_map = {
                'JPG': 'JPEG',
                'JPEG': 'JPEG',
                'PNG': 'PNG',
                'WEBP': 'WEBP',
                'GIF': 'GIF',
                'BMP': 'BMP',
                'TIFF': 'TIFF'
            }

            to_format = format_map.get(to_format, to_format)

            # Open and convert
            with Image.open(self.input_path) as img:
                # Handle transparency for formats that don't support it
                if to_format == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        rgb_img.paste(img, mask=img.split()[-1])
                    else:
                        rgb_img.paste(img)
                    img = rgb_img

                # Save in new format
                save_kwargs = {}
                if to_format in ('JPEG', 'WEBP'):
                    save_kwargs['quality'] = self.quality
                    save_kwargs['optimize'] = True

                img.save(self.output_path, to_format, **save_kwargs)

            # Get file size
            output_size = self.output_path.stat().st_size

            return {
                'status': 'success',
                'from_format': from_format,
                'to_format': to_format,
                'size': output_size,
                'output': str(self.output_path)
            }

        except ImportError:
            return {
                'status': 'error',
                'error': 'PIL (Pillow) not installed. Run: pip install Pillow',
                'error_type': 'DependencyError'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }


@register_module('image.resize')
class ImageResizeModule(BaseModule):
    """
    Resize image to specific dimensions

    Params:
        input (str): Path to input image file
        output (str): Path to output resized image
        width (int): Target width in pixels
        height (int): Target height in pixels (optional, maintains aspect ratio if omitted)
        maintain_aspect (bool): Maintain aspect ratio (optional, default: true)

    Returns:
        dict: {
            'status': 'success',
            'original_size': [width, height],
            'new_size': [width, height]
        }

    Example:
        ```yaml
        - id: resize
          module: image.resize
          params:
            input: photo.jpg
            output: thumbnail.jpg
            width: 800
            height: 600
        ```
    """

    module_name = "Image Resize"
    module_description = "Resize image to specific dimensions"

    def validate_params(self):
        """Validate parameters"""
        required = ['input', 'output', 'width']
        for param in required:
            if param not in self.params:
                raise ValueError(f"Missing required parameter: {param}")

        self.input_path = Path(self.params['input'])
        self.output_path = Path(self.params['output'])
        self.width = int(self.params['width'])
        self.height = int(self.params.get('height', 0))
        self.maintain_aspect = self.params.get('maintain_aspect', True)

        if not self.input_path.exists():
            raise FileNotFoundError(f"Input image not found: {self.input_path}")

        if self.width <= 0:
            raise ValueError(f"Width must be positive, got: {self.width}")

    async def execute(self) -> Dict[str, Any]:
        """Execute image resize"""
        try:
            from PIL import Image

            with Image.open(self.input_path) as img:
                original_size = img.size

                # Calculate target size
                if self.maintain_aspect and self.height == 0:
                    # Calculate height maintaining aspect ratio
                    aspect_ratio = img.height / img.width
                    target_height = int(self.width * aspect_ratio)
                    target_size = (self.width, target_height)
                elif self.maintain_aspect:
                    # Use thumbnail to maintain aspect ratio
                    img.thumbnail((self.width, self.height), Image.Resampling.LANCZOS)
                    target_size = img.size
                else:
                    # Exact size, ignore aspect ratio
                    target_size = (self.width, self.height)

                # Resize
                if not self.maintain_aspect or self.height == 0:
                    img = img.resize(target_size, Image.Resampling.LANCZOS)

                # Save
                img.save(self.output_path)

            return {
                'status': 'success',
                'original_size': list(original_size),
                'new_size': list(target_size),
                'output': str(self.output_path)
            }

        except ImportError:
            return {
                'status': 'error',
                'error': 'PIL (Pillow) not installed. Run: pip install Pillow',
                'error_type': 'DependencyError'
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'error_type': type(e).__name__
            }
