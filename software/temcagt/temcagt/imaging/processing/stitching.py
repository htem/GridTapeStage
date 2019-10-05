#!/usr/bin/env python
"""
Example template and match crops
tcs = [
    [[500, 1500], [1948, None]],
    [[0, 100], [500, 1500]],
    [[500, 1500], [0, 100]],
]

mcs = [
    [[0, None], [0, 500]],
    [[-500, None], [0, None]],
    [[0, None], [-500, None]],
]

Images should probably be stitched as
cam1, cam2, cam4, cam3

so they are stitched as followed


      3           1

  (match 3)    (match 1)

      4 (match 2) 2
"""

import copy

import cv2
import numpy


def crop_image(im, crop):
    return im[slice(*crop[1]), slice(*crop[0])]


def resolve_crop(im, crop):
    """Convert a crop (i.e. slice definition) to only positive values
    crops might contain None, or - values"""
    # only works for two dimension
    crop = list(crop)
    assert len(crop) == 2
    for i in (0, 1):
        assert len(crop[i]) == 2
        for j in (0, 1):
            if crop[i][j] is None:
                crop[i][j] = j * im.shape[1-j]
            elif crop[i][j] < 0:
                crop[i][j] += im.shape[1-j]
    return crop


def scale_crop(c, s):
    if isinstance(c, (list, tuple)):
        return [scale_crop(ci, s) for ci in c]
    if c is None:
        return c
    return c / s


def find_shift(im0, im1, tcrop, mcrop, method='TM_CCORR_NORMED', start=(0, 0)):
    if isinstance(method, (str, unicode)):
        method = getattr(cv2, method)
    tc = resolve_crop(im0, tcrop)
    t = crop_image(im0, tc)
    mc = resolve_crop(im1, mcrop)
    m = crop_image(im1, mc)
    match = cv2.matchTemplate(
        numpy.array(t).astype('f4'),
        numpy.array(m).astype('f4'), method)
    max_loc = cv2.minMaxLoc(match)[3]
    sx = start[0] + tc[0][0] - max_loc[0] - mc[0][0]
    sy = start[1] + tc[1][0] - max_loc[1] - mc[1][0]
    return sx, sy


def find_shifts(ims, tcrops, mcrops, method='TM_CCORR_NORMED', start=(0, 0)):
    """Find shifts between images by matching regions
    ims : list of images to match (matches 0 to 1, 1 to 2, etc...)
    tcrops : crop definitions for extracting templates
    mcrops : crop defs over which to match template
    method : passed onto cv2.matchTemplate
    start : position of image[0]
    """
    assert len(ims) > 1
    assert len(tcrops) == len(ims) - 1
    assert len(mcrops) == len(tcrops)
    shifts = [start]
    image = ims[0].astype('f4')
    for (i, im) in enumerate(ims[1:]):
        sx, sy = find_shift(
            image, im.astype('f4'), tcrops[i], mcrops[i],
            method, shifts[-1])
        shifts.append([sx, sy])
        image = im
    return shifts


def calculate_weights(shapes, shifts):
    ws = []
    for (shape, s) in zip(shapes, shifts):
        height, width = shape
        w = numpy.ones(shape, dtype='f8')
        for s2 in shifts:
            if id(s) == id(s2):
                continue
            # calculate overlapping block
            left = s2[0] - s[0]
            right = left + width
            left = max(left, 0)
            right = min(width, right)
            top = s2[1] - s[1]
            bottom = top + height
            top = max(top, 0)
            bottom = min(height, bottom)
            if right > 0 and left < width and bottom > 0 and top < height:
                w[top:bottom, left:right] += 1
        ws.append(1. / w)
    return ws


def calculate_bounding_box(shapes, shifts):
    left, right, top, bottom = numpy.inf, -numpy.inf, numpy.inf, -numpy.inf
    for (shape, s) in zip(shapes, shifts):
        left = min(left, s[0])
        right = max(right, s[0] + shape[1])
        top = min(top, s[1])
        bottom = max(bottom, s[1] + shape[0])
    return (
        int(numpy.floor(left)), int(numpy.ceil(right)),
        int(numpy.floor(top)), int(numpy.ceil(bottom)))


def build_canvas(bbox):
    return numpy.empty(((bbox[3] - bbox[2]), (bbox[1] - bbox[0])))


def stitch(ims, shifts, weights=None, bbox=None, canvas=None):
    if weights is None:
        weights = calculate_weights([i.shape for i in ims], shifts)
    if bbox is None:
        bbox = calculate_bounding_box([i.shape for i in ims], shifts)
    left, right, top, bottom = bbox
    if canvas is None:
        canvas = build_canvas(bbox)
        canvas[:, :] = 0.
    for (im, s, w) in zip(ims, shifts, weights):
        e = (
            s[0] - left,
            s[0] + im.shape[1] - left,
            s[1] + im.shape[0] - top,
            s[1] - top,
        )
        canvas[e[3]:e[2], e[0]:e[1]] += im * w
    return canvas


def scalable_stitch(ims, max_shape, shifts, weights=None, bbox=None):
    s = ims[0].shape
    for im in ims[1:]:
        if im.shape != s:
            raise Exception(
                "Invalid images, they must all be the same shape %s != %s"
                % (s, im.shape))
    if s != max_shape:
        # scale things
        # sx and sy are the downsample values
        sx = max_shape[1] / float(s[1])
        sy = max_shape[0] / float(s[0])
        if sx != int(sx) or sy != int(sy):
            raise Exception(
                "Invalid downsampling, %s x %s, must be an integer value"
                % (sx, sy))
        shifts = copy.copy(shifts)
        for i in xrange(len(shifts)):
            shifts[i][0] /= sx
            shifts[i][1] /= sy
        if weights is not None:
            weights = copy.copy(weights)
            for i in xrange(len(weights)):
                weights[i] = weights[i][::sy, ::sx]
                if weights[i].shape != s:
                    raise Exception(
                        "Failed to downsample weights %s to shape %s"
                        % (weights[i].shape, s))
        if bbox is not None:
            bbox = calculate_bounding_box([i.shape for i in ims], shifts)
    return stitch(ims, shifts, weights, bbox)


class Stitcher(object):
    def __init__(self, max_height, max_width, shifts):
        # these are the shifts at 1x downsampling (full size)
        #self.full_size = (float(max_height), float(max_width))
        self.full_size = (
            int(numpy.ceil(max_height)),
            int(numpy.ceil(max_width)))
        # self._weights
        # self._bboxes
        # self._canvases
        #self.shifts = [map(float, s) for s in shifts]
        self.shifts = [map(int, s) for s in shifts]

    @property
    def shifts(self):
        return self._shifts[1]

    @shifts.setter
    def shifts(self, value):
        self._shifts = {
            1: value}
        # reset cache
        shapes = [self.full_size] * len(value)
        self._weights = {
            1: calculate_weights(shapes, value)}
        self._bboxes = {
            1: calculate_bounding_box(shapes, value)}
        self._canvases = {
            1: build_canvas(self._bboxes[1])}

    def lookup_weights(self, ds):
        if ds not in self._weights:
            self._weights[ds] = [w[::ds, ::ds] for w in self._weights[1]]
        return self._weights[ds]

    def lookup_bbox(self, ds):
        if ds not in self._bboxes:
            ss = self.lookup_shifts(ds)
            s = (self.full_size[0] / ds, self.full_size[1] / ds)
            self._bboxes[ds] = calculate_bounding_box([s] * len(ss), ss)
        return self._bboxes[ds]

    def lookup_shifts(self, ds):
        if ds not in self._shifts:
            self._shifts[ds] = [
                [(s[0] / ds), (s[1] / ds)] for s in self._shifts[1]]
        return self._shifts[ds]

    def lookup_canvas(self, ds):
        if ds not in self._canvases:
            self._canvases[ds] = build_canvas(self.lookup_bbox(ds))
        c = self._canvases[ds]
        c[:, :] = 0.
        return c

    def compute(self, ims, tcrops, mcrops):
        pass

    def stitch(self, ims, shifts=None):
        if shifts is not None:
            self.shifts = shifts
        s = ims[0].shape
        dsx = round(self.full_size[1] / float(s[1]))
        dsy = round(self.full_size[0] / float(s[0]))
        if dsx != dsy:
            raise Exception(
                "Failed to stitch images, nonuniform downsampling %s %s"
                % (dsx, dsy))
        ds = dsx
        for im in ims[1:]:
            if im.shape != s:
                raise Exception(
                    "Can only stitch images of equal size %s != %s"
                    % (im.shape, s))
        return stitch(
            ims, self.lookup_shifts(ds), self.lookup_weights(ds),
            self.lookup_bbox(ds), self.lookup_canvas(ds))
