#!/usr/bin/env python

import cv2

import datautils.structures.mp
import montage

from .... import log
from .. import utils


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class FrameSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, norm_buffers, frame_buffers):
        logger.debug(
            "FrameSerf[%s] setup: %s, %s, %s",
            self, config, norm_buffers, frame_buffers)
        self.config = config
        self.norm_buffers = norm_buffers
        self.frame_buffers = frame_buffers
        self.setup_buffers()
        if 'log_serfs' in config:
            utils.log_serf_to_directory(self, config['log_serfs'])

    def setup_buffers(self):
        logger.debug("FrameSerf[%s] setup_buffers", self)
        h, w, _ = self.config['crop']
        self.norms = [
            montage.io.Image(utils.buffer_as_array(b, 'f4', (h, w)))
            for b in self.norm_buffers]
        self.frames = [
            montage.io.Image(utils.buffer_as_array(f, 'u2', (h, w)))
            for f in self.frame_buffers]

    def build_frame(self, shifts, buffer_indices, frame_buffer_index):
        logger.debug(
            "FrameSerf[%s] build_frame: %s, %s, %s",
            self, shifts, buffer_indices, frame_buffer_index)
        assert len(buffer_indices) - 1 == len(shifts)
        norms = [self.norms[i] for i in buffer_indices]
        frame = montage.ops.transform.shift.deshift_and_average(
            norms, shifts)
        fmin, fmax, _, _ = cv2.minMaxLoc(frame)
        cv2.normalize(frame, frame, 0, 65535, cv2.NORM_MINMAX)
        self.frames[frame_buffer_index][:, :] = frame.astype('u2')
        # frame meta data [fmin, fmax]
        meta = {
            'range': (fmin, fmax),
            'buffer_index': frame_buffer_index,
            'buffer_indices': buffer_indices,
            'shifts': shifts,
        }
        self.send('frame', frame_buffer_index, meta)


class FrameLord(datautils.structures.mp.Lord):
    def __init__(self, config, buffers):
        logger.debug("FrameLord[%s] __init__: %s, %s", self, config, buffers)
        datautils.structures.mp.Lord.__init__(self)
        self.config = config
        self.buffers = buffers

    def start(self, wait=True):
        logger.debug("FrameLord[%s] start", self)
        datautils.structures.mp.Lord.start(
            self, FrameSerf, (
                self.config, self.buffers.norm_buffers,
                self.buffers.frame_buffers), wait=wait)

    def build_frame(self, shifts, buffer_indices):
        logger.debug(
            "FrameLord[%s] build_frame: %s, %s",
            self, shifts, buffer_indices)
        frame_buffer_index = self.buffers.request_frame_lock()
        # TODO what to do here?
        if frame_buffer_index is None:
            raise IOError("Failed to find an empty frame buffer")
        [self.buffers.lock_grab(i) for i in buffer_indices]
        self.send('build_frame', shifts, buffer_indices, frame_buffer_index)

    def frame(self, index, meta):
        logger.debug("FrameLord[%s] frame: %s, %s", self, index, meta)
        # get meta from norms
        #meta['shifts'] = []
        meta['contrasts'] = []
        meta['frame counts'] = []
        meta['times'] = []
        for ni in meta['buffer_indices']:
            n = self.buffers.norms[ni]
            meta.update(n.meta)
            #if 'shift' in n.meta:
            #    meta['shifts'].append(n.meta['shift'])
            meta['contrasts'].append(n.meta['contrast'])
            meta['frame counts'].append(n.meta['frame count'])
            meta['times'].append(n.meta['DateTime'].strftime('%y%m%d%H%M%S%f'))
            self.buffers.unlock_grab(ni)
        meta['buffer_index'] = index
        self.buffers.frames[index].meta = meta
