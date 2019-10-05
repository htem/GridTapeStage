#!/usr/bin/env python

import datautils.structures.mp
import montage

from .... import log
from .. import utils


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class SaverSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, grab_buffers, norm_buffers, frame_buffers):
        logger.debug(
            "SaverSerf[%s] setup: %s, %s, %s, %s",
            self, config, grab_buffers, norm_buffers, frame_buffers)
        # accumulate then save (to give the ability to drop bad frames)
        self.config = config
        self.grab_buffers = grab_buffers
        self.norm_buffers = norm_buffers
        self.frame_buffers = frame_buffers
        self.setup_buffers()
        if 'log_serfs' in config:
            utils.log_serf_to_directory(self, config['log_serfs'])

    def set_config(self, config):
        logger.debug("SaverSerf[%s] set_config: %s", self, config)
        self.config = config

    def setup_buffers(self):
        logger.debug("SaverSerf[%s] setup_buffers", self)
        h, w, s = self.config['crop']
        self.grabs = [
            montage.io.Image(utils.buffer_as_array(b, 'u2', (h, w, s)))
            for b in self.grab_buffers]
        self.norms = [
            montage.io.Image(utils.buffer_as_array(b, 'f4', (h, w)))
            for b in self.norm_buffers]
        self.frames = [
            montage.io.Image(utils.buffer_as_array(b, 'u2', (h, w)))
            for b in self.frame_buffers]

    def save_grab(self, index, meta):
        logger.debug("SaverSerf[%s] save_grab: %s, %s", self, index, meta)
        self.grabs[index].meta = meta
        fn = utils.imwrite(self.grabs[index], self.config, 'grab')
        self.send('grab', index, fn)

    def save_grabs(self, indicies, metas):
        logger.debug("SaverSerf[%s] save_grabs: %s, %s", self, indicies, metas)
        for (i, (bi, m)) in enumerate(zip(indicies, metas)):
            self.grabs[bi].meta = m
            self.grabs[bi].meta['grab'] = i
            fn = utils.imwrite(self.grabs[bi], self.config, 'grab')
            self.send('grab', bi, fn)

    def save_norm(self, index, meta):
        logger.debug("SaverSerf[%s] save_norm: %s, %s", self, index, meta)
        self.norms[index].meta = meta
        fn = utils.imwrite(self.norms[index], self.config, 'norm')
        self.send('norm', index, fn)

    def save_norms(self, indicies, metas):
        logger.debug("SaverSerf[%s] save_norms: %s, %s", self, indicies, metas)
        for (i, (bi, m)) in enumerate(zip(indicies, metas)):
            self.norms[bi].meta = m
            self.norms[bi].meta['grab'] = i
            fn = utils.imwrite(self.norms[bi], self.config, 'norm')
            self.send('norm', bi, fn)

    def save_frame(self, index, meta):
        logger.debug("SaverSerf[%s] save_frame: %s, %s", self, index, meta)
        self.frames[index].meta = meta
        fn = utils.imwrite(self.frames[index], self.config, 'frame')
        self.send('frame', index, fn)


class SaverLord(datautils.structures.mp.Lord):
    def __init__(self, config, buffers):
        logger.debug("SaverLord[%s] shift: %s, %s", self, config, buffers)
        datautils.structures.mp.Lord.__init__(self)
        self.config = config
        self.buffers = buffers

    def set_config(self, config):
        logger.debug("SaverLord[%s] set_config: %s", self, config)
        self.send('set_config', config)

    def start(self, wait=True):
        logger.debug("SaverLord[%s] start", self)
        datautils.structures.mp.Lord.start(
            self, SaverSerf, (
                self.config, self.buffers.grab_buffers,
                self.buffers.norm_buffers, self.buffers.frame_buffers
            ), wait=wait)

    def save_grab(self, index):
        logger.debug("SaverLord[%s] save_grab: %s", self, index)
        self.buffers.lock_grab(index)
        meta = self.buffers.grabs[index].meta.copy()
        self.send('save_grab', index, meta)

    def save_grabs(self, indices, **meta):
        logger.debug("SaverLord[%s] save_grabs: %s", self, meta)
        ms = []
        for i in indices:
            m = self.buffers.grabs[i].meta.copy()
            self.buffers.lock_grab(i)
            m.update(meta)
            ms.append(m)
        self.send('save_grabs', indices, ms)

    def save_norm(self, index):
        logger.debug("SaverLord[%s] save_norm: %s", self, index)
        self.buffers.lock_grab(index)
        meta = self.buffers.norms[index].meta.copy()
        self.send('save_norm', index, meta)

    def save_norms(self, indices, **meta):
        logger.debug("SaverLord[%s] save_norms: %s", self, meta)
        ms = []
        for i in indices:
            m = self.buffers.norms[i].meta.copy()
            self.buffers.lock_grab(i)
            m.update(meta)
            ms.append(m)
        self.send('save_norms', indices, ms)

    def save_frame(self, index, **meta):
        logger.debug("SaverLord[%s] save_frame: %s, %s", self, index, meta)
        self.buffers.lock_frame(index)
        m = self.buffers.frames[index].meta.copy()
        m.update(meta)
        self.send('save_frame', index, m)

    def grab(self, index, fn):
        self.buffers.unlock_grab(index)

    def norm(self, index, fn):
        self.buffers.unlock_grab(index)

    def frame(self, index, fn):
        self.buffers.unlock_frame(index)
