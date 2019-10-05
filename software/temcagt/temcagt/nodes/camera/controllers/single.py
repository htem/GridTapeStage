#!/usr/bin/env python

import logging
import time

from .... import log
from .base import NodeController


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class SingleGrabController(NodeController):
    def __init__(self, node):
        logger.debug("SingleGrabController[%s] __init__: %s", self, node)
        NodeController.__init__(self, node)
        self.requested = None
        self.result = []
        self.nframes = 0
        self.state = 'done'

    def connect(self):
        logger.debug("SingleGrabController[%s] connect", self)
        NodeController.connect(self)
        self.callbacks['camera'] = [
            self.node.camera.attach('grab', self.on_grab), ]
        self.callbacks['norm'] = [
            self.node.norm.attach('norm', self.on_norm), ]
        self.callbacks['analysis'] = [
            self.node.analysis.attach('contrast', self.on_contrast),
            self.node.analysis.attach('shift', self.on_shift), ]
        self.callbacks['frame'] = [
            self.node.frame.attach('frame', self.on_frame), ]
        self.callbacks['stats'] = [
            self.node.stats.attach('stats', self.on_stats), ]

    def disconnect(self):
        logger.debug("SingleGrabController[%s] disconnect", self)
        # finish updating things
        if self.node is not None:
            self.update()
            if self.state != 'done':
                self.until('done')
        NodeController.disconnect(self)

    def on_grab(self, meta):
        logger.debug("SingleGrabController[%s] on_grab: %s", self, meta)
        index = meta['buffer_index']
        self.node.buffers.grabs[index].meta = meta
        #self.result.append(index)
        if self.requested == 'grab':
            #assert len(self.result) == 1
            self.node.stats.compute_stats('grab', index)
            self.result = [index, ]
            #self.state = 'done'
            self.state = 'stats'
            return
        self.node.norm.normalize_grab(index)

    def on_norm(self, index):
        logger.debug("SingleGrabController[%s] on_norm: %s", self, index)
        self.node.buffers.norms[index].meta = \
            self.node.buffers.grabs[index].meta
        if self.requested == 'norm':
            self.node.stats.compute_stats('norm', index)
            self.result = [index, ]
            #self.state = 'done'
            self.state = 'stats'
            return
        self.node.analysis.analyze_grab(index)

    def on_contrast(self, index, result):
        logger.debug(
            "SingleGrabController[%s] on_contrast: %s, %s",
            self, index, result)
        self.node.buffers.norms[index].meta['contrast'] = result
        self.result.append(index)

    def on_shift(self, index, result):
        logger.debug(
            "SingleGrabController[%s] on_shift: %s, %s", self, index, result)
        self.node.buffers.norms[index].meta['shift'] = result
        if self.requested == 'frame':
            if len(self.result) >= self.nframes:
                shifts = [
                    self.node.buffers.norms[i].meta['shift']
                    for i in self.result[1:]]
                self.node.frame.build_frame(shifts, self.result)

    def on_frame(self, index, meta):
        logger.debug(
            "SingleGrabController[%s] on_frame: %s, %s", self, index, meta)
        if self.requested == 'frame':
            #bi = meta['buffer_index']
            # otherwise done with the grabs so unlock them
            self.node.stats.compute_stats('frame', index)
            for i in self.result:
                self.node.buffers.unlock_grab(i)
            self.result = [index, ]
            #self.state = 'done'
            self.state = 'stats'

    def on_stats(self, btype, index, stats):
        logger.debug(
            "SingleGrabController[%s] on_stats: %s, %s", self, btype, index)
        self.node.broadcast_stats(stats)
        self.state = 'done'

    def get_grab(self, meta, until_done=True):
        logger.debug(
            "SingleGrabController[%s] get_grab: %s", self, until_done)
        self.state = 'grab'
        self.requested = 'grab'
        self.result = []
        self.node.camera.single(meta)
        if until_done:
            self.until('done')
            return self.result[0]

    def get_norm(self, meta, until_done=True):
        logger.debug(
            "SingleGrabController[%s] get_norm: %s", self, until_done)
        self.state = 'norm'
        self.requested = 'norm'
        self.result = []
        self.node.camera.single(meta)
        if until_done:
            self.until('done')
            return self.result[0]

    def get_frame(self, meta, until_done=True):
        logger.debug(
            "SingleGrabController[%s] get_frame: %s", self, until_done)
        self.state = 'frame'
        self.requested = 'frame'
        self.result = []
        self.node.analysis.clear_template()
        self.nframes = self.node.config()['nframes']
        [self.node.camera.single(meta) for i in xrange(self.nframes)]
        if until_done:
            self.until('done')
            return self.result[0]

    def update(self, timeout=0.000001):
        #lp = getattr(self, '_lp', -1)
        #t = time.time()
        #w = ((t - lp) > 0.1)
        #if w:
        #    logger.debug(
        #        "SingleGrabController[%s] update: %s", self, self.state)
        try:
            self.node.camera.update(timeout=timeout)
            self.node.norm.update(timeout=timeout)
            self.node.analysis.update(timeout=timeout)
            self.node.frame.update(timeout=timeout)
            self.node.saver.update(timeout=timeout)
            self.node.stats.update(timeout=timeout)
        except Exception as e:
            logger.error(
                "SingleGrabController[%s] update error: %s", self, e)
            logger.error(
                "SingleGrabController[%s] update: new_stats_future: %s",
                self, self.node.new_stats_future)
            if self.node.new_stats_future is not None:
                self.node.new_stats_future.set_exception(e)
            raise e
        #if w:
        #    logger.debug(
        #        "SingleGrabController[%s] update end: %s", self, self.state)
        #    self._lp = time.time()
