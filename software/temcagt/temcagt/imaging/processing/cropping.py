#!/usr/bin/env python
"""
"""

from ... import log


logger = log.get_logger(__name__)


def calculate_crop(im, dims):
    logger.debug("calculate_crop %s %s", hex(id(im)), dims)
    if isinstance(dims, (float, int)):  # square: h and w
        h, w = im.shape
        hd = dims / 2
        r = [(h / 2 - hd, h / 2 + hd), (w / 2 - hd, w / 2 + hd)]
    elif isinstance(dims[0], (float, int)):  # rect: h x w
        h, w = im.shape
        hy = dims[0] / 2
        hx = dims[1] / 2
        r = [(h / 2 - hy, h / 2 + hy), (w / 2 - hx, w / 2 + hx)]
    else:
        r = dims
    logger.debug("calculate_crop result %s", r)
    return r


def crop(im, dims):
    logger.debug("crop %s %s", hex(id(im)), dims)
    if isinstance(im, (list, tuple)):
        return [crop(i, calculate_crop(im[0], dims)) for i in im]
    dims = calculate_crop(im, dims)
    return im[[slice(*d) for d in dims]]
