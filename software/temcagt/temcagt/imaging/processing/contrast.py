#!/usr/bin/env python
"""
"""

import numpy

from . import cropping
from ... import log


logger = log.get_logger(__name__)


def check_contrast(im, crop=None):
    """
    Require pre-cropping
    """
    logger.debug("check_contrast")
    if isinstance(im, (list, tuple)):
        return [check_contrast(i, crop) for i in im]
    if crop is not None:
        r = numpy.std(cropping.crop(im, crop))
    else:
        r = numpy.std(im)
    logger.debug("check_contrast result %s" % r)
    return r
