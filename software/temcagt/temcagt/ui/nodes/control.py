#!/usr/bin/env python

import inspect
import os

import flask

from ... import log
from . import base
from . import camera
from . import compute
from . import montager
from . import motion
from . import scope
from . import tape
from . import tapecamera


logger = log.get_logger(__name__)

module_folder = os.path.abspath(
    os.path.dirname(inspect.getfile(inspect.currentframe())))


def build_spec(obj, name):
    spec = base.build_spec(obj, name)
    spec['template'] = open(
        os.path.join(module_folder, 'templates', 'control.html'), 'r').read()
    return spec


def test(addr='tcp://127.0.0.1:11060', host=None):
    import wsrpc
    import pizco
    from tornado.ioloop import IOLoop
    logger.debug("Connecting to proxy")
    p = pizco.Proxy(addr)
    logger.debug("adding __wsrpc__ to control")
    base.add_wsrpc_to_proxy(p, 'control')
    logger.debug("connecting to motion")
    cfg = p.config()
    m = pizco.Proxy(cfg['motion']['addr'])
    logger.debug("adding __wsrpc__ to motion")
    base.add_wsrpc_to_proxy(m, 'motion')
    logger.debug("Connecting to cameras")
    cs = [pizco.Proxy(c['addr']) for c in cfg['cameras']]
    logger.debug("adding __wsrpc__ to cameras")
    [base.add_wsrpc_to_proxy(c, 'camera') for c in cs]
    logger.debug("connecting to montager")
    mo = pizco.Proxy(cfg['montager']['addr'])
    logger.debug("adding __wsrpc__ to montager")
    base.add_wsrpc_to_proxy(mo, 'montager')
    comp = pizco.Proxy(cfg['compute']['addr'])
    logger.debug("adding __wsrpc__ to compute")
    base.add_wsrpc_to_proxy(comp, 'compute')
    microscope = pizco.Proxy(cfg['scope']['addr'])
    logger.debug("adding __wsrpc__ to scope")
    base.add_wsrpc_to_proxy(microscope, 'scope')
    logger.debug("adding __wsrpc__ to tape")
    t = pizco.Proxy(cfg['tape']['addr'])
    base.add_wsrpc_to_proxy(t, 'tape')
    logger.debug("adding __wsrpc__ to tapecamera")
    tc = pizco.Proxy(cfg['tapecamera']['addr'])
    base.add_wsrpc_to_proxy(tc, 'tapecamera')
    logger.debug("Clearing IOLoop")
    if hasattr(IOLoop, '_instance'):
        del IOLoop._instance
    logger.debug("Registering control")
    wsrpc.serve.register(build_spec(p, 'control'))
    logger.debug("Registering compute")
    wsrpc.serve.register(compute.build_spec(comp, 'compute'))
    logger.debug("Registering scope")
    wsrpc.serve.register(scope.build_spec(microscope, 'scope'))
    logger.debug("Registering motion")
    wsrpc.serve.register(motion.build_spec(m, 'motion'))
    logger.debug("Registering montager")
    wsrpc.serve.register(montager.build_spec(mo, 'montager'))
    logger.debug("Registering cameras")
    for (ci, c) in enumerate(cs):
        wsrpc.serve.register(camera.build_spec(c, 'cam{}'.format(ci)))
    logger.debug("Registering tape")
    wsrpc.serve.register(tape.build_spec(t, 'tape'))
    logger.debug("Registering tapecamera")
    wsrpc.serve.register(tapecamera.build_spec(tc, 'tapecamera'))
    logger.debug("Serving")
    # add default route
    wsrpc.serve.serve(
        address=host, debug=True,
        default_route='/control/templates/control.html')
