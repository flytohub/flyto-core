# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
