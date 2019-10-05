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

import numpy
import pylab

import cv2

from . import cropping
from ... import log


logger = log.get_logger(__name__)


def parse_shift_results(shifts):
    logger.debug("parse_shift_results %s",
                 map(lambda im: hex(id(im)), shifts))
    h, w = shifts[0].shape
    hh = h / 2
    hw = w / 2
    rs = []
    for s in shifts:
        m = s.max()
        y, x = numpy.where(s == m)
        x = x[0] - hw
        y = y[0] - hh
        d = (x * x + y * y) ** 0.5
        rs.append(dict(x=x, y=y, d=d, m=m))
    logger.debug("parse_shift_results result %s", rs)
    return rs


def find_shifts(ims, tcrop=400, mcrop=500, method='TM_CCORR_NORMED'):
    """
    Requires full images

    Returns list of dicts of shift information for each subsequent frame
    relative to the first (used as a template).

    Shift information includes:
        x : x coordinate of maximum matching shift
        y : y coordinate
        m : magnitude of match
    """
    logger.debug("find_shifts %s", (map(lambda im: hex(id(im)), ims),
                 tcrop, mcrop, method))
    if ims[0].dtype in (numpy.float32, numpy.uint8):
        tc = lambda a: a
    else:
        tc = lambda a: a.astype('f4')
    method = getattr(cv2, method)
    t = tc(cropping.crop(ims[0], tcrop))
    mims = cropping.crop(ims[1:], mcrop)
    shifts = [cv2.matchTemplate(t, tc(mim), method) for mim in mims]
    #for i in xrange(len(shifts)):
    #    pylab.figure()
    #    pylab.subplot(221)
    #    pylab.imshow(t)
    #    pylab.subplot(222)
    #    pylab.imshow(mims[i])
    #    pylab.subplot(223)
    #    pylab.imshow(shifts[i])
    return parse_shift_results(shifts)


def deshift(ims, shifts):
    """
    shifts : dict(x, y, d, m)
    """
    logger.debug("deshift %s", (map(lambda im: hex(id(im)), ims),
                 shifts))
    sims = [numpy.ma.masked_array(ims[0], numpy.zeros_like(ims[0])), ]
    for (im, shift) in zip(ims[1:], shifts):
        s = numpy.roll(numpy.roll(im, -shift['x'], 1), -shift['y'], 0)
        # mask array
        s = numpy.ma.masked_array(s, numpy.zeros_like(s))
        s.mask[:, -shift['x']:] = True
        s.mask[-shift['y']:, :] = True
        sims.append(s)
    return sims


def deshift_and_average(ims, shifts):
    logger.debug("deshift_and_average %s", (map(lambda im: hex(id(im)), ims),
                 shifts))
    if ims[0].dtype != numpy.dtype('f4'):
        raise NotImplementedError("deshift_and_average only works for f4")
    mim = ims[0]
    n = numpy.ones(mim.shape, dtype='f4')
    for i in xrange(1, len(ims)):
        im = ims[i]
        shift = shifts[i-1]
        x = shift['x']
        y = shift['y']
        if x >= 0:
            ix = im.shape[1] - x
            if y >= 0:
                iy = im.shape[0] - y
                #mim[:iy, :ix] += im[y:, x:]
                #n[:iy, :ix] += 1
                cv2.add(mim[:iy, :ix], im[y:, x:])
                cv2.add(n[:iy, :ix], 1)
            else:  # y < 0
                #mim[-y:, :ix] += im[:y, x:]
                #n[-y:, :ix] += 1
                cv2.add(mim[-y:, :ix], im[:y, x:])
                cv2.add(n[-y:, :ix], 1)
        else:  # x < 0
            if y >= 0:
                iy = im.shape[0] - y
                cv2.add(mim[:iy, -x:], im[y:, :x])
                cv2.add(n[:iy, -x:], 1)
            else:  # y < 0
                cv2.add(mim[-y:, -x:], im[:y, :x])
                cv2.add(n[-y:, -x:], 1)
    return cv2.divide(mim, n)
