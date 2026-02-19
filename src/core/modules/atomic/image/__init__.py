"""
Image modules
"""
try:
    from .download import *
except ImportError:
    pass
try:
    from .convert import *
except ImportError:
    pass
try:
    from .svg_convert import *
except ImportError:
    pass
try:
    from .resize import *
except ImportError:
    pass
try:
    from .compress import *
except ImportError:
    pass
try:
    from .qrcode_generate import *
except ImportError:
    pass
try:
    from .ocr import *
except ImportError:
    pass
try:
    from .crop import *
except ImportError:
    pass
try:
    from .rotate import *
except ImportError:
    pass
try:
    from .watermark import *
except ImportError:
    pass
