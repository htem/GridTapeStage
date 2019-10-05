#!/usr/bin/env python
import warnings

__all__ = []

try:
    from . import camera
    __all__.append('camera')
except ImportError as e:
    warnings.warn("camera ui import failed: {}".format(e))

try:
    from . import compute
    __all__.append('compute')
except ImportError as e:
    warnings.warn("compute ui import failed: {}".format(e))

try:
    from . import control
    __all__.append('control')
except ImportError as e:
    warnings.warn("control ui import failed: {}".format(e))

try:
    from . import montager
    __all__.append('montager')
except ImportError as e:
    warnings.warn("montager ui import failed: {}".format(e))

try:
    from . import motion
    __all__.append('motion')
except ImportError as e:
    warnings.warn("motion ui import failed: {}".format(e))

try:
    from . import tape
    __all__.append('tape')
except ImportError as e:
    warnings.warn("tape ui import failed: {}".format(e))

try:
    from . import tapecamera
    __all__.append('tapecamera')
except ImportError as e:
    warnings.warn("tapecamera ui import failed: {}".format(e))

try:
    from . import test
    __all__.append('test')
except ImportError as e:
    warnings.warn("test ui import failed: {}".format(e))
