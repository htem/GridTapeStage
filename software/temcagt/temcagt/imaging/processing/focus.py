#!/usr/bin/env python

import cv2
import numpy

from . import linearpolar


def psd_focus(im, **kwargs):
    psd2d = numpy.abs(numpy.fft.fftshift(numpy.fft.fft2(im))) ** 2.
    return numpy.mean(linearpolar.img2polar(psd2d, **kwargs), 1)


def gradient_focus(im):
    # maximize this for best focus
    return cv2.sumElems(cv2.absdiff(im[1:], im[:-1]))[0]
    #return numpy.array(numpy.sum((im[1:] - im[:-1]) ** 2.))
