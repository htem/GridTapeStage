#!/usr/bin/env python

import inspect
import json
import os
from cStringIO import StringIO

import numpy
from PIL import Image

import montage
import wsrpc


from ... import nodes


# TODO
# - error reporting (and logging)

module_folder = os.path.abspath(
    os.path.dirname(inspect.getfile(inspect.currentframe())))
static_folder = os.path.abspath(os.path.join(module_folder, 'static'))
template_folder = os.path.abspath(os.path.join(module_folder, 'templates'))


# TODO memoize this for multiple clients?
def image_to_string(im):
    # TODO datatypes
    # TODO stretch?
    im -= im.min()
    if im.max() != 0.:
        sim = ((im - im.min()) * (255. / (im.max() - im.min())))
    else:
        sim = im
    im = Image.fromarray(sim.astype('u1'))
    io = StringIO()
    im.save(io, format='jpeg')
    io.seek(0)
    return io.read().encode('base64')


# TODO convert image to png
def fix_types(r):
    if isinstance(r, (dict, )):
        return dict([(k, fix_types(r[k])) for k in r])
    elif isinstance(r, Exception):
        return {
            'type': 'exception',
            'class': str(r.__class__.__name__),
            'message': str(r.message),
        }
    elif isinstance(r, montage.io.Image):
        return image_to_string(r)
    elif isinstance(r, (tuple, list, set)):
        return [fix_types(v) for v in r]
    elif isinstance(r, numpy.ndarray):
        if r.ndim == 0 or r.size == 1:
            return float(r)
        #elif r.ndim == 2:
        #    return image_to_string(r)
        else:
            return fix_types(r.tolist())  # TODO make this more flexible
    elif isinstance(r, numpy.floating):
        return float(r)
    elif isinstance(r, numpy.integer):
        return int(r)
    elif isinstance(r, (float, int, str, unicode)):
        return r
    print("Failed to convert: %s, %s" % (type(r), r))
    return r
    #return json.JSONEncoder.default(r)


# TODO subclass config.parser.NumpyAwareParser?
class ImageAwareJSONEncoder(json.JSONEncoder):
    def default(self, o):
        return fix_types(o)


def add_wsrpc_to_proxy(p, class_name):
    # lookup class
    c = nodes.base.resolve_class(class_name)
    spec = wsrpc.wrapper.build_function_spec(c)
    # have to be creative to assign attribute to the proxy
    p.__dict__['__wsrpc__'] = lambda s=spec: s
    return p


def build_spec(obj, name):
    spec = {
        'name': name,
        'object': obj,
        'static_folder': static_folder,
        'template_folder': template_folder,
        'encoder': ImageAwareJSONEncoder,
    }
    return spec
