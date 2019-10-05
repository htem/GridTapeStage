#!/usr/bin/env python

import logging
import time

from .... import log


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class NodeController(object):
    def __init__(self, node):
        logger.debug("NodeController[%s] __init__: %s", self, node)
        self.node = node
        self.state = 'init'
        self.callbacks = {}
        self.connect()

    def connect(self):
        logger.debug("NodeController[%s] connect", self)
        # connect callbacks and store them in self.callbacks
        # by attr (self.callbacks[attr] = [cbid0, cbid1, ...])
        self.state = 'connect'

    def disconnect(self):
        logger.debug("NodeController[%s] disconnect", self)
        self.state = 'disconnect'
        if self.node is not None:
            for attr in self.callbacks:
                if hasattr(self.node, attr):
                    obj = getattr(self.node, attr)
                    [obj.detatch(cbid) for cbid in self.callbacks[attr]]
        self.callbacks = {}
        self.node = None

    def until(self, test_function, timeout=0.000001):
        if isinstance(test_function, (str, unicode)):
            test_function = lambda state=test_function: self.state == state
        logger.debug(
            "NodeController[%s] until: %s", self,
            getattr(test_function, '__name__', 'UNKNOWN'))
        while not test_function():
            #s = ""
            #if hasattr(self, 'saving'):
            #    s = self.saving
            #logger.debug(
            #    "%s() %s: %s", test_function.__name__, test_function(), s)
            self.update(timeout=timeout)
        logger.debug(
            "NodeController[%s] until [done]: %s", self,
            getattr(test_function, '__name__', 'UNKNOWN'))

    def update(self, timeout=0.000001):
        logger.debug("NodeController[%s] update", self)
        raise NotImplementedError("NodeController.update is abstract")

    def __del__(self):
        logger.debug("NodeController[%s] __del__", self)
        self.disconnect()
        del self.node
