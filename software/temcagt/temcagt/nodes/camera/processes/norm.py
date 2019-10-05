#!/usr/bin/env python

import cv2

import datautils.structures.mp
import montage

from .... import log
from .. import utils


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class NormSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, grab_buffers, norm_buffers, bg_buffer):
        logger.debug(
            "NormSerf[%s] setup: %s, %s, %s, %s",
            self, config, grab_buffers, norm_buffers, bg_buffer)
        self.config = config
        self.image_size = config['crop'][:2]
        self.grab_buffers = grab_buffers
        self.norm_buffers = norm_buffers
        self.bg_buffer = bg_buffer
        self.setup_buffers()
        if 'log_serfs' in config:
            utils.log_serf_to_directory(self, config['log_serfs'])

    def set_config(self, config):
        logger.debug("NormSerf[%s] set_config: %s", self, config)
        self.config = config

    def setup_buffers(self):
        logger.debug("NormSerf[%s] setup_buffers", self)
        h, w, s = self.config['crop']
        self.grabs = [
            montage.io.Image(utils.buffer_as_array(b, 'u2', (h, w, s)))
            for b in self.grab_buffers]
        self.norms = [
            utils.buffer_as_array(b, 'f4', (h, w)) for b in self.norm_buffers]
        self.bg = montage.io.Image(
            utils.buffer_as_array(self.bg_buffer, 'f4', (h, w)))

    def normalize_grab(self, buffer_index):
        logger.debug("NormSerf[%s] normalize_grab: %s", self, buffer_index)
        # tests on camera node show cv2 is faster (7 ms vs 12 ms)
        cv2.multiply(
            self.grabs[buffer_index], self.bg,
            self.norms[buffer_index], dtype=cv2.CV_32F)
        #self.norms[buffer_index][:, :] = self.grabs[buffer_index] * self.bg
        self.send('norm', buffer_index)


class NormLord(datautils.structures.mp.Lord):
    def __init__(self, config, buffers):
        logger.debug(
            "NormLord[%s] __init__: %s, %s", self, config, buffers)
        datautils.structures.mp.Lord.__init__(self)
        self.config = config
        self.buffers = buffers

    def start(self, wait=True):
        logger.debug("NormLord[%s] start", self)
        datautils.structures.mp.Lord.start(
            self, NormSerf, (
                self.config, self.buffers.grab_buffers,
                self.buffers.norm_buffers, self.buffers.bg_buffer), wait=wait)

    def set_config(self, config):
        logger.debug("NormLord[%s] set_config: %s", self, config)
        self.send('set_config', config)

    def normalize_grab(self, index):
        logger.debug("NormLord[%s] normalize_grab: %s", self, index)
        self.buffers.lock_grab(index)
        self.send('normalize_grab', index)

    def norm(self, index):
        logger.debug("NormLord[%s] norm: %s", self, index)
        self.buffers.unlock_grab(index)
