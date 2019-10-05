#!/usr/bin/env python
"""

ROI definition should only require a minimum set of points. Such as:

    - left, right, top, bottom
    - top-left, bottom-right
    - center, width, height
    - left, top, width, height
    - any of the above plus normalized vertices to specify non rectangular
        rois enclosed in this rectangle
    etc...

"""

import operator
import numpy

class ROIError(ValueError):
    pass


class ROIConflict(ROIError):
    pass


def pick_one(values):
    if len(values) == 0:
        return None
    elif len(values) == 1:
        return values[0]
    if all([x==values[0] for x in values]):
        return values[0]
    raise ValueError


def resolve(
        left=None, right=None, top=None, bottom=None,
        center=None, width=None, height=None, vertices=None):
    vs = []
    if left is None and width is None:
        return None
    if left is not None:
        vs.append(left)
    if right is not None and width is not None:
        vs.append(right - width)
    if center is not None and width is not None:
        vs.append(center[0] - width / 2.)
    try:
        left = pick_one(vs)
    except ValueError:
        raise ROIConflict("Ambiguous left: %s" % (vs,))
    vs = []
    if right is None and width is None:
        return None
    if right is not None:
        vs.append(right)
    if left is not None and width is not None:
        vs.append(left + width)
    if center is not None and width is not None:
        vs.append(center[0] + width / 2.)
    try:
        right = pick_one(vs)
    except ValueError:
        raise ROIConflict("Ambiguous right: %s" % (vs,))
    vs = []
    if top is None and height is None:
        return None
    if top is not None:
        vs.append(top)
    if bottom is not None and height is not None:
        vs.append(bottom - height)
    if center is not None and height is not None:
        vs.append(center[1] - height / 2.)
    try:
        top = pick_one(vs)
    except ValueError:
        raise ROIConflict("Ambiguous top: %s" % (vs,))
    vs = []
    if bottom is None and height is None:
        return None
    if bottom is not None:
        vs.append(bottom)
    if top is not None and height is not None:
        vs.append(top + height)
    if center is not None and height is not None:
        vs.append(center[1] + height / 2.)
    try:
        bottom = pick_one(vs)
    except ValueError:
        raise ROIConflict("Ambiguous bottom: %s" % (vs,))
    # at this point top bottom left and right should be resolved
    assert left is not None
    assert right is not None
    assert top is not None
    assert bottom is not None
    w = (right - left)
    if width is None:
        width = w
    else:
        if width != w:
            raise ROIConflict(
                "Ambiguous width: %s" % ((width, w),))
    h = (bottom - top)
    if height is None:
        height = h
    else:
        if height != h:
            raise ROIConflict(
                "Ambiguous height: %s" % ((height, h),))
    c = [(left + right) / 2., (top + bottom) / 2.]
    if center is None:
        center = c
    else:
        if center != c:
            raise ROIConflict(
                "Ambiguous center: %s" % ((center, c),))

    #if vertices is not None:
    #    vertices_array = numpy.array(vertices)
    #    if vertices_array.min() < 0.0 or vertices_array.max() > 1.0:
    #        raise ROIConflict("Vertices should be between 0 and 1")
    return {
        'center': center, 'width': width, 'height': height,
        'left': left, 'right': right, 'top': top, 'bottom': bottom,
        'vertices': vertices,
    }


def offset(roi, center):
    rroi = resolve(**roi)
    return {
        'left': rroi['left'] + center['x'],
        'top': rroi['top'] + center['y'],
        'width': rroi['width'],
        'height': rroi['height'],
        'vertices': rroi['vertices'],
    }

def scale(roi, factor):
    rroi = resolve(**roi)
    # first find center
    c = {'x': rroi['left'] + rroi['width']/2, 'y': rroi['top'] + rroi['height']/2}
    #unoffset by center
    rroi = unoffset(rroi,c)
    # scale all values
    for x in ['left','width']:
        rroi[x] = int(rroi[x]*factor['x'])
    for y in ['top','height']:
        rroi[y] = int(rroi[y]*factor['y'])
    # bring back to original coordinate space
    rroi = offset(rroi,c)
    return rroi


def unoffset(roi, center):
    rroi = resolve(**roi)
    return {
        'left': rroi['left'] - center['x'],
        'top': rroi['top'] - center['y'],
        'width': rroi['width'],
        'height': rroi['height'],
	'vertices': rroi['vertices'],
    }


def check_against_bounds(roi, bounds):
    rroi = resolve(**roi)
    for k in ('left', 'top'):
        if rroi[k] < bounds[k]:
            raise ROIError("roi %s out of bounds" % (k, ))
    for k in ('right', 'bottom'):
        if rroi[k] > bounds[k]:
            raise ROIError("roi %s out of bounds" % (k, ))
