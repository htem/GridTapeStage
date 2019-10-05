#!/usr/bin/env python
"""
Compute an image histogram
"""

import cv2
import numpy


def histogram(im, **kwargs):
    if 'bins' not in kwargs:
        bins = int(numpy.sqrt(im.size))
    else:
        bins = int(kwargs['bins'])
    mi, ma = [int(v) for v in cv2.minMaxLoc(im)[:2]]
    if mi == ma:
        return numpy.zeros(bins)
    return (
        cv2.calcHist(
            [im], [0], None, [bins], [mi, ma]).reshape(bins),
        numpy.linspace(mi, ma, bins))
    #n = numpy.sqrt(im.size)
    #kwargs['bins'] = kwargs.get('bins', n)
    #return numpy.histogram(im.flat, **kwargs)
