#!/usr/bin/env python
"""
Pipeline from labview code:
    1) crop [mask] to central region
        a) template = 400x400
        b) search area = 500x500
    2) quantify image
    3) check for contrast (std dev of pixels) [contrast thresh = 2.0]
    4) find shift
        a) learn 'template' image from first frame (learn pattern 2)
        b) find shifted templates in other frames (match pattern 2)
            i) [match theshold = 340]
        c) take max distance of all shifts
    5) compute shift stats
        a) max shift [max individual frame drift = 4)
        b) drift sum [max = 16.0]
        c) no matches? (images without any template matched regions)
        d) average match [min = 340]
        e) enough contrast? [boolean]
    6) veto? [max vetos = 2]


Python code should
    1) mask image
    2) check contrast [std dev of pixels]
    3) find shift [the fastest and bestest way]
"""

from . import contrast
from . import cropping
from . import linearpolar
from . import focus
from . import histogram
from . import oo
from . import shift
from . import stitching


__all__ = [
    'contrast', 'cropping', 'linearpolar', 'focus', 'histogram', 'oo', 'shift',
    'stitching'
]
