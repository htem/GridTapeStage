#!/usr/bin/env python
"""
In general, things must be imported explicitly to avoid
extra dependencies
"""

from . import config

__all__ = ['config']

__version_info__ = (0, 1, 0)
__version__ = "{}.{}.{}".format(*__version_info__)

import os
import subprocess
try:
    __gitcommit__ = subprocess.check_output(
        ["git", "log", "-1", "--pretty='%H'"],
        cwd=os.path.dirname(__file__)).strip()[1:8]
except Exception:
    __gitcommit__ = 'unknown'

__version_full__ = ".".join((__version__, __gitcommit__))
