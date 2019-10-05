#!/usr/bin/env python

import inspect
import os

from ... import log
from . import base


logger = log.get_logger(__name__)

module_folder = os.path.abspath(
    os.path.dirname(inspect.getfile(inspect.currentframe())))


def build_spec(obj, name):
    spec = base.build_spec(obj, name)
    spec['template'] = open(
        os.path.join(module_folder, 'templates', 'compute.html'), 'r').read()
    # camera spec?
    return spec


def test(addr='tcp://127.0.0.1:21212'):  # REALADDRESS
    import wsrpc
    import pizco
    from tornado.ioloop import IOLoop
    p = pizco.Proxy(addr)
    base.add_wsrpc_to_proxy(p, 'compute')
    if hasattr(IOLoop, '_instance'):
        del IOLoop._instance
    wsrpc.serve.register(build_spec(p, 'compute'))
    wsrpc.serve.serve()
