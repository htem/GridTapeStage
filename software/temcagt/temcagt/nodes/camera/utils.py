#!/usr/bin/env python
"""
"""

import ctypes
import multiprocessing
import os

import numpy

import montage

from ... import log


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


def log_serf_to_directory(serf, d):
    d = os.path.abspath(os.path.expanduser(d))
    n = serf.__class__.__name__
    fn = os.path.join(d, n)
    if not os.path.exists(d):
        os.makedirs(d)
    serf.set_log(fn)


def imwrite(im, cfg, imtype):
    #logger.debug("Imwrite: %s, %s, %s, %s", im, im.meta, cfg, imtype)
    logger.debug("Imwrite: %s, %s, %s, %s", id(im), im.meta, cfg, imtype)
    d = cfg['save']['directory']
    fmt = cfg['save']['filename_formats'][imtype]
    fn = os.path.join(d, fmt.format(**im.meta))
    montage.io.imwrite(fn, im)
    return fn


def buffer_as_array(b, dtype, crop=None):
    if hasattr(b, 'get_obj'):
        b = b.get_obj()
    a = numpy.frombuffer(b, dtype)
    if crop is None:
        return a
    if len(crop) == 2:
        h, w = crop
        return a.reshape(h, w)
    elif len(crop) == 3:
        h, w, s = crop
        l = h * s / 2
        return a[:l].reshape(h, s / 2)[:, :w]
    else:
        raise ValueError("Invalid crop: %s" % (crop, ))


def lookup_image_dimensions(config):
    if config['loc'] == 'fake':
        return [128, 128, 256], 32768
    if 'SFT' in config['loc']:
        return [2160, 2560, 5120], 5529600
    crop = [2048, 2048, 4120]
    if config['features'].get('MetadataEnable', False):
        return crop, 4223000
    return crop, 4218880


class SharedBuffers(object):
    def __init__(self, config):
        h, w, s = config['crop']
        n_words = config['n_words']
        n_pixels = h * w
        self.n_frames = config['nframes'] + config['nregrabs']
        self.n_buffer_copies = config['nbuffercopies']
        self.n_buffers = self.n_frames * self.n_buffer_copies

        self.grab_buffers = [
            multiprocessing.RawArray(ctypes.c_uint16, n_words)
            for _ in xrange(self.n_buffers)]
        self.norm_buffers = [
            multiprocessing.RawArray(ctypes.c_float, n_pixels)
            for _ in xrange(self.n_buffers)]
        self.bg_buffer = multiprocessing.RawArray(ctypes.c_float, n_pixels)
        self.frame_buffers = [
            multiprocessing.RawArray(ctypes.c_uint16, n_pixels)
            for _ in xrange(self.n_buffer_copies)]

        self.grabs = [
            montage.io.Image(buffer_as_array(b, 'u2', (h, w, s)))
            for b in self.grab_buffers]
        self.norms = [
            montage.io.Image(buffer_as_array(b, 'f4', (h, w)))
            for b in self.norm_buffers]
        self.bg = montage.io.Image(
            buffer_as_array(self.bg_buffer, 'f4', (h, w)))
        self.bg[:, :] = 1.
        self.frames = [
            montage.io.Image(buffer_as_array(b, 'u2', (h, w)))
            for b in self.frame_buffers]

        # combine norm and grab locks
        # these are more reference counts then locks
        self.grab_locks = [0 for _ in self.grabs]
        self.frame_locks = [0 for _ in self.frames]
        self._frame_lock_index = 0
        #self.locks = {
        #    'grab': [None for _ in self.grabs],
        #    'norm': [None for _ in self.norms],
        #    'frame': [None for _ in self.frames],
        #}

    def get_locks(self):
        return {
            'frame': self.frame_locks[:],
            'grab': self.grab_locks[:],
        }

    def is_ready_for_grab(self):
        # look for 1 unassigned frame
        if not any(f == 0 for f in self.frame_locks):
            return False
        # look for self.n_frames unassigned grabs & norms
        if sum([g == 0 for g in self.grab_locks]) < self.n_frames:
            return False
        return True

    def is_empty(self):
        if any(f != 0 for f in self.frame_locks):
            return False
        if any(g != 0 for g in self.grab_locks):
            return False
        return True

    def lock_grab(self, index):
        self.grab_locks[index] += 1

    def unlock_grab(self, index):
        if self.grab_locks[index] == 0:
            raise ValueError("Attempt to reduce grab lock[%s] to < 1" % index)
        self.grab_locks[index] -= 1

    def _inc_frame_lock_index(self):
        self._frame_lock_index += 1
        if self._frame_lock_index == len(self.frame_locks):
            self._frame_lock_index = 0

    def request_frame_lock(self):
        # always increment frame lock
        self._inc_frame_lock_index()
        si = self._frame_lock_index
        while self.frame_locks[self._frame_lock_index] != 0:
            self._inc_frame_lock_index()
            if self._frame_lock_index == si:
                # failed to find unused frame
                return None
        self.frame_locks[self._frame_lock_index] += 1
        return self._frame_lock_index

    def lock_frame(self, index):
        self.frame_locks[index] += 1

    def unlock_frame(self, index):
        if self.frame_locks[index] == 0:
            raise ValueError("Attempt to reduce frame lock[%s] to < 1" % index)
        self.frame_locks[index] -= 1
