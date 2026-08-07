# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Robot Modules

Steps carried out by a robot through its own gateway. The gateway owns the
machine — its identity, its safety envelope, its wheels; these modules only
hand it a bounded plan and report what came back.
"""

from . import plan  # noqa: F401
