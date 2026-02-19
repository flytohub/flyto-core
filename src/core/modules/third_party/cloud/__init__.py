# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cloud Integrations
AWS S3, Google Workspace, Google Cloud Storage, Azure Blob Storage
"""

from .storage import *
from .gcs import *
from .azure import *
from . import aws
from . import google

__all__ = [
    # Cloud modules will be auto-discovered by module registry
    'aws',
    'google',
]
