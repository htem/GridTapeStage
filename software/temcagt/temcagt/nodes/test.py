#!/usr/bin/env python

import time

import concurrent.futures

from . import base


class TestNode(base.IONode):
    def __init__(self, cfg=None):
        base.IONode.__init__(self, cfg)
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def long_task(self, in_pool=False):
        """Run long tasks in pools and return futures"""
        if in_pool is False:
            return self._pool.submit(self.long_task, in_pool=True)
        print("This is a long running task")
        time.sleep(2)
        print("still going...")
        time.sleep(2)
        print("done!")
        return
