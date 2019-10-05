#!/usr/bin/env python

import copy
import json
import os
import sys

import datautils
import numpy

from .. import log


logger = log.get_logger(__name__)


class ArgumentError(Exception):
    pass


class CascadeError(Exception):
    pass


class PruneError(Exception):
    pass


def parse_value(v):
    v = v.replace("'", '"')
    try:
        return json.loads(v)
    except (ValueError, SyntaxError) as E:
        logger.error("Invalid syntax[%s] for %s", E, v, exc_info=True)
        raise ArgumentError("Invalid syntax[{}] for {}".format(E, v))


def parse_command_line(args=None):
    if args is None:
        args = sys.argv[1:]
    if divmod(len(args), 2)[1] != 0:
        logger.error("Number of arguments[%s] must be odd", len(args))
        raise ArgumentError(
            "Number of arguments[{}] must be odd".format(len(args)))
    argi = iter(args)
    c = datautils.ddict.DDict()
    for k in argi:
        c[k] = parse_value(argi.next())
    return c


def load(fn):
    fn = os.path.expanduser(fn)
    if not os.path.exists(fn):
        logger.error("Config file %s does not exist", fn)
        raise IOError("Config file {} does not exist".format(fn))
    with open(fn, 'r') as f:
        cfg = json.load(f)
    logger.info("Loaded config from %s: %.50s", fn, cfg)
    return cfg


class NumpyAwareParser(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, numpy.ndarray):
            if obj.ndim == 1:
                return obj.tolist()
            elif obj.ndim == 0:
                return obj.item()
            else:  # Don't encode large arrays
                return None
        elif isinstance(obj, numpy.generic):
            return obj.item()
        return json.JSONEncoder.default(self, obj)


def save(cfg, fn):
    fn = os.path.expanduser(fn)
    # make directory if it doesn't exist
    d = os.path.dirname(fn)
    if d != '' and not os.path.exists(d):
        os.makedirs(d)
    with open(fn, 'w') as f:
        json.dump(cfg, f, cls=NumpyAwareParser)
    logger.info("Saved config to %s: %.50s", fn, cfg)


def parse(cfg):
    if cfg is None:
        return {}
    if isinstance(cfg, dict):
        return copy.deepcopy(cfg)
    if isinstance(cfg, (str, unicode)):  # filename
        return load(cfg)
    logger.error("Unknown cfg type %s: %s", type(cfg), cfg)
    raise TypeError("Unknown cfg type {}: {}".format(type(cfg), cfg))


def cascade(a, b, modify=False):
    if not modify:
        a = copy.deepcopy(a)
    for k in b:
        if isinstance(b[k], dict):
            sa = a.get(k, {})
            if not isinstance(sa, dict):
                raise CascadeError(
                    "Cannot cascade non-dict [{}] with dict [{}]".format(
                        sa, b[k]))
            a[k] = cascade(sa, b[k], modify=True)
        else:
            a[k] = copy.deepcopy(b[k])
    return a


def prune(a, b, modify=False):
    if not modify:
        a = copy.deepcopy(a)
    if isinstance(b, (str, unicode)):
        if b in a:
            del a[b]
    elif isinstance(b, (list, tuple)):
        for sb in b:
            if sb in a:
                del a[sb]
    elif isinstance(b, dict):
        for k in b:
            if isinstance(b[k], dict):
                if len(b[k]) == 0:
                    if k in a:
                        del a[k]
                else:
                    a[k] = prune(a[k], b[k], modify=True)
            else:
                a[k] = prune(a[k], b[k], modify=True)
    else:
        raise PruneError("Invalid prune key [%s] type [%s]" % (b, type(b)))
    return a


def delta(a, b):
    """Find all keys and values in b not in a"""
    d = {}
    for k in b:
        if k not in a:
            d[k] = copy.deepcopy(b[k])
        elif isinstance(a[k], dict):
            if isinstance(b[k], dict):
                dd = delta(a[k], b[k])
                if dd != {}:
                    d[k] = dd
            else:
                d[k] = copy.deepcopy(b[k])
        else:
            if a[k] != b[k]:
                d[k] = copy.deepcopy(b[k])
    return d
