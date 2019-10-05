#!/usr/bin/env python
"""
Image processor class that
    - accepts configuration parameters
    - accepts images
    - returns results
"""

import inspect

from . import contrast
from . import shift
from ...config.checkers import require
from ... import log


logger = log.get_logger(__name__)


def get_kwarg_checker(f):
    """ Generate kwarg check: kwarg_check(name)
    This is used for checking if a given name is a valid kwargs.

    If function has kwargs (spec.keywords is not None) than anything can
    be a kwargs.

    If spec.keywords is None than check if name is in spec.defaults
    """
    s = inspect.getargspec(f)
    if s.keywords is not None:
        return lambda k: True
    kwargs = s.args[-len(s.defaults):]
    return lambda k: k in kwargs


class ImageProcessor(object):
    def __init__(self, config=None):
        self.config = {}
        if config is not None:
            self.config.update(config)
        self.set_function(lambda images, **kwargs: [])
        self.valid = True
        self.result = None

    def __repr__(self):
        return "{}.{} at {} function {}".format(
            self.__module__, self.__class__, hex(id(self)),
            getattr(getattr(self, '_func', {}), '_name', 'None'))

    def set_function(self, f):
        self._func = f
        self._iskw = get_kwarg_checker(f)

    def validate(self):
        return True

    def configure(self, config):
        self.config.update(config)

    def check_config(self):
        pass

    def submit(self, images):
        self.check_config()
        kwargs = dict(
            [(k, self.config[k]) for k in self.config if self._iskw(k)])
        logger.debug("ImageProcessor[%s] submit with %s",
                     self, (hex(id(images)), kwargs))
        self.result = self._func(images, **kwargs)
        self.valid = self.validate()
        logger.debug("ImageProcessor[%s] valid? %s", self, self.valid)


class ContrastChecker(ImageProcessor):
    def __init__(self, config=None):
        ImageProcessor.__init__(self, config)
        self.set_function(contrast.check_contrast)

    def check_config(self):
        [require(self.config, k) for k in 'crop min'.split()]

    def validate(self):
        return self.result >= self.config['min']


class ShiftChecker(ImageProcessor):
    def __init__(self, config=None):
        ImageProcessor.__init__(self, config)
        self.set_function(shift.find_shifts)

    def check_config(self):
        [require(self.config, k) for k in
            'tcrop mcrop method max_shift min_match'.split()]

    def validate(self):
        return (
            all([i['d'] <= self.config['max_shift'] for i in self.result]) and
            all([i['m'] >= self.config['min_match'] for i in self.result]))
