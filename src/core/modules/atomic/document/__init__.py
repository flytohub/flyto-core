"""
Document processing modules
"""
try:
    from .pdf_parse import *
except ImportError:
    pass
try:
    from .excel_read import *
except ImportError:
    pass
try:
    from .excel_write import *
except ImportError:
    pass
