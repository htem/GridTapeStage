#!/usr/bin/env python

import inspect
import os

from . import base

module_folder = os.path.abspath(
    os.path.dirname(inspect.getfile(inspect.currentframe())))


def build_spec(obj, name):
    spec = base.build_spec(obj, name)
    spec['template'] = open(
        os.path.join(module_folder, 'templates', 'motion.html'), 'r').read()
    return spec


def test(addr='tcp://127.0.0.1:11010'):
    import wsrpc
    import pizco
    from tornado.ioloop import IOLoop
    p = pizco.Proxy(addr)
    base.add_wsrpc_to_proxy(p, 'motion')
    if hasattr(IOLoop, '_instance'):
        del IOLoop._instance
    wsrpc.serve.register(build_spec(p, 'motion'))
    wsrpc.serve.serve()
