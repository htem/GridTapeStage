#!/usr/bin/env python

import inspect
import os
import time


from . import base


module_folder = os.path.abspath(
    os.path.dirname(inspect.getfile(inspect.currentframe())))


def timethis(f):
    def wrapped(*args, **kwargs):
        t = time.time()
        r = f(*args, **kwargs)
        t = time.time() - t
        print("%s took %s" % (f.__name__, t))
        return r
    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__
    return wrapped


def build_spec(obj, name):
    spec = base.build_spec(obj, name)
    spec['template'] = open(
        os.path.join(module_folder, 'templates', 'camera.html'), 'r').read()

    return spec


def test(addr='tcp://127.0.0.1:11020'):
    import wsrpc
    import pizco
    from tornado.ioloop import IOLoop
    p = pizco.Proxy(addr)
    base.add_wsrpc_to_proxy(p, 'camera')
    if hasattr(IOLoop, '_instance'):
        del IOLoop._instance
    wsrpc.serve.register(build_spec(p, 'camera'))
    wsrpc.serve.serve()
