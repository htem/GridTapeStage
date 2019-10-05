#!/usr/bin/env python

import numpy
from shapely.geometry import Polygon

from ... import log


logger = log.get_logger(__name__)

def intersect(tpts,rpts):
    """uses py2d package http://sseemayer.github.io/Py2D/documentation.html
    to determine if two polygons (defined by vertices) intersect"""
    tpoly = Polygon(tpts)
    rpoly = Polygon(rpts)
    return tpoly.intersects(rpoly)

def calculate_coordinates(cfg):
    logger.info("calculate_coordinates %s", cfg)
    bbpts = {
        'grid': grid_coordinates,
        'pull': pull_coordinates,
        'offset': offset_coordinates,
    }[cfg['method']](cfg)
    # return bounding box if rectangular roi
    if cfg.get('vertices',None) is None:
        return bbpts
    # if use_vertices flag set to flase then also return bbpts
    if cfg.get('use_vertices',True) is False:
        return bbpts
    # otherwise remove tiles not in the roi
    # vertices are normalized, so we turn them into real coordsinates here
    rpts  = numpy.array(cfg['vertices']) * \
            numpy.array([cfg['width'],cfg['height']]) + \
            numpy.array([cfg['left'],cfg['top']])
    xfov, yfov = cfg['fov']
    hxfov = xfov / 2.
    hyfov = yfov / 2.
    npts = [] 
    for p in bbpts:
        x, y, _, _ = p
        l = x - hxfov
        r = x + hxfov
        t = y - hyfov
        b = y + hyfov
        tpts = numpy.array([[l, t], [r, t], [r, b], [l, b]])
        if intersect(tpts, rpts):
            npts.append(p)
    return npts



def skip_points(points, skip):
    if skip == 0:
        return points
    cpts = []
    i = 0
    pp = None
    for p in points:
        x, y, _, _ = p
        if pp is None:
            cpts.append(p)
            i = 0
        else:
            dx = pp[0] - x
            dy = pp[1] - y
            if (dx != 0) and (dy != 0):  # if moved row and column
                # if skipped last one
                if (i != 0):
                    # add previous point
                    cpts.append(pp)
                # and this one
                cpts.append(p)
                i = 0
            elif i >= skip:
                cpts.append(p)
                i = 0
            else:
                i += 1
        pp = p
    if i != 0:
        cpts.append(p)
    return cpts


def distribute(n_instances, pts):
    if n_instances == 0:
        return []
    skip = int(numpy.floor(
        len(pts) / float(n_instances))) - 1
    skip = max(0, skip)
    c = 0
    n = 0
    indices = []
    for i in xrange(len(pts)):
        if n >= n_instances:
            break
        if c == skip:
            indices.append(i)
            n += 1
            c = 0
        else:
            c += 1
    return indices


def grid_coordinates(cfg):
    """
    cfg
        fov, overlap, center, width, height

    width and height are the imaged region NOT the movement region

    Returns 4 arrays, xs, ys, rows, cols, of position centers
    """
    logger.info("grid_coordinates: %s", cfg)
    xstep = cfg['fov'][0] * (1. - cfg['overlap'][0])
    ystep = cfg['fov'][1] * (1. - cfg['overlap'][1])
    nxsteps = numpy.ceil((cfg['width']) / xstep)
    nysteps = numpy.ceil((cfg['height']) / ystep)

    # offset left & top by 1/2 of 'extra'
    xextra = (
        (nxsteps * xstep) - cfg['width'] + cfg['fov'][0] * cfg['overlap'][0])
    yextra = (
        (nysteps * ystep) - cfg['height'] + cfg['fov'][1] * cfg['overlap'][1])
    left = cfg['center'][0] + (cfg['fov'][0] - cfg['width'] - xextra) / 2.
    top = cfg['center'][1] + (cfg['fov'][1] - cfg['height'] - yextra) / 2.

    logger.info("xstep: %s", xstep)
    logger.info("ystep: %s", ystep)
    logger.info("left: %s", left)
    logger.info("top: %s", top)
    logger.info("nxsteps: %s", nxsteps)
    logger.info("nysteps: %s", nysteps)

    cs = numpy.arange(nxsteps)
    rs = numpy.arange(nysteps)
    xs = left + xstep * cs
    ys = top + ystep * rs
    pts = []
    direction = 1
    if cfg['fast_axis'] == 'y':
        for (c, x) in zip(cs, xs):
            for (r, y) in zip(rs[::direction], ys[::direction]):
                pts.append((x, y, r + 1, c + 1))
            direction *= -1
    else:
        for (r, y) in zip(rs, ys):
            for (c, x) in zip(cs[::direction], xs[::direction]):
                pts.append((x, y, r + 1, c + 1))
            direction *= -1
    return pts


def pull_coordinates(cfg):
    """
    cfg
        fov, overlap, center, width, height

    width and height are the imaged region NOT the movement region

    Returns 4 arrays, xs, ys, rows, cols, of position centers
    """
    logger.info("pull_coordinates: %s", cfg)
    xstep = cfg['fov'][0] * (1. - cfg['overlap'][0])
    ystep = cfg['fov'][1] * (1. - cfg['overlap'][1])
    nxsteps = numpy.ceil((cfg['width']) / xstep)
    nysteps = numpy.ceil((cfg['height']) / ystep)

    # offset left & top by 1/2 of 'extra'
    xextra = (
        (nxsteps * xstep) - cfg['width'] + cfg['fov'][0] * cfg['overlap'][0])
    yextra = (
        (nysteps * ystep) - cfg['height'] + cfg['fov'][1] * cfg['overlap'][1])
    left = cfg['center'][0] + (cfg['fov'][0] - cfg['width'] - xextra) / 2.
    top = cfg['center'][1] + (cfg['fov'][1] - cfg['height'] - yextra) / 2.

    logger.info("xstep: %s", xstep)
    logger.info("ystep: %s", ystep)
    logger.info("left: %s", left)
    logger.info("top: %s", top)
    logger.info("nxsteps: %s", nxsteps)
    logger.info("nysteps: %s", nysteps)

    cs = numpy.arange(nxsteps)
    rs = numpy.arange(nysteps)
    xs = left + xstep * cs
    ys = top + ystep * rs
    pts = []
    for (r, y) in zip(rs, ys):
        for (c, x) in zip(cs, xs):
            pts.append((x, y, r + 1, c + 1))
    return pts


def offset_coordinates(cfg):
    """
        fov, overlap, center, width, height

    width and height are the imaged region NOT the movement region

    Returns 4 arrays, xs, ys, rows, cols, of position centers
    """
    logger.info("offset_coordinates: %s", cfg)
    xstep = cfg['fov'][0] * (1. - cfg['overlap'][0])
    ystep = cfg['fov'][1] * (1. - cfg['overlap'][1])
    hxstep = xstep / 2.
    nxsteps = numpy.ceil((cfg['width']) / xstep)
    nysteps = numpy.ceil((cfg['height']) / ystep)

    # offset left & top by 1/2 of 'extra'
    xextra = (
        (nxsteps * xstep) - cfg['width'] + cfg['fov'][0] * cfg['overlap'][0])
    yextra = (
        (nysteps * ystep) - cfg['height'] + cfg['fov'][1] * cfg['overlap'][1])
    left = cfg['center'][0] + (cfg['fov'][0] - cfg['width'] - xextra) / 2.
    top = cfg['center'][1] + (cfg['fov'][1] - cfg['height'] - yextra) / 2.

    logger.info("xstep: %s", xstep)
    logger.info("ystep: %s", ystep)
    logger.info("left: %s", left)
    logger.info("top: %s", top)
    logger.info("nxsteps: %s", nxsteps)
    logger.info("nysteps: %s", nysteps)

    cs = numpy.arange(nxsteps)
    rs = numpy.arange(nysteps)
    xs = left + xstep * cs
    ys = top + ystep * rs
    pts = []
    for (r, y) in zip(rs, ys):
        for (c, x) in zip(cs, xs):
            if (r % 2) == 0:  # even rows
                pts.append((x, y, r + 1, c + 1))
            else:  # offset odd rows
                pts.append((x - hxstep, y, r + 1, c + 1))
                if (c == cs[-1]):  # last column
                    pts.append((x + hxstep, y, r + 1, c + 2))
    return pts
