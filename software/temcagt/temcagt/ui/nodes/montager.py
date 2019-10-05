#!/usr/bin/env python

import inspect
import os

from ... import log
from . import base
from . import camera
from . import motion
#from . import compute
#from . import tape


logger = log.get_logger(__name__)

module_folder = os.path.abspath(
    os.path.dirname(inspect.getfile(inspect.currentframe())))


def build_spec(obj, name):
    spec = base.build_spec(obj, name)
    spec['template'] = open(
        os.path.join(module_folder, 'templates', 'montager.html'), 'r').read()
    return spec


def test(addr='tcp://127.0.0.1:11000', host=None):
    import wsrpc
    import pizco
    from tornado.ioloop import IOLoop
    logger.debug("Connecting to proxy")
    p = pizco.Proxy(addr)
    logger.debug("adding __wsrpc__ to montager")
    base.add_wsrpc_to_proxy(p, 'montager')
    logger.debug("connecting to motion")
    cfg = p.config()
    m = pizco.Proxy(cfg['motion']['addr'])
    logger.debug("adding __wsrpc__ to motion")
    base.add_wsrpc_to_proxy(m, 'motion')
    logger.debug("Connecting to cameras")
    cs = [pizco.Proxy(c['addr']) for c in cfg['cameras']]
    logger.debug("adding __wsrpc__ to cameras")
    [base.add_wsrpc_to_proxy(c, 'camera') for c in cs]
    #comp = pizco.Proxy(cfg['compute']['addr'])
    #logger.debug("adding __wsrpc__ to compute")
    #base.add_wsrpc_to_proxy(comp, 'compute')
    #logger.debug("adding __wsrpc__ to tape")
    #t = pizco.Proxy(cfg['tape']['addr'])
    #base.add_wsrpc_to_proxy(t, 'tape')
    logger.debug("Clearing IOLoop")
    if hasattr(IOLoop, '_instance'):
        del IOLoop._instance
    logger.debug("Registering montager")
    wsrpc.serve.register(build_spec(p, 'montager'))
    logger.debug("Registering motion")
    wsrpc.serve.register(motion.build_spec(m, 'motion'))
    logger.debug("Registering cameras")
    for (ci, c) in enumerate(cs):
        wsrpc.serve.register(camera.build_spec(c, 'cam{}'.format(ci)))
    #logger.debug("Registering compute")
    #wsrpc.serve.register(compute.build_spec(comp, 'compute'))
    #wsrpc.serve.register(tape.build_spec(t, 'tape'))
    logger.debug("Serving")
    # add default route
    wsrpc.serve.serve(
        address=host, debug=True,
        default_route='/montager/templates/monitor.html')
