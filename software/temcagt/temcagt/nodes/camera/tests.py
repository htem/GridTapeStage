#!/usr/bin/env python
"""
in camera process: (proxy communicates with process)
    - grabs to shared memory
    - does normalization

in frame thread: (proxy communicates with process)
    - generate frame norms (to/from shared memory)

in save thread: (proxy communicates with process)
    - save grabs (from shared memory)
    - save norms (from shared memory)
    - save frame (from shared memory)

in analysis thread: (proxy communicates with process)
    - check contrast
    - check shift

the camera node does the following:
    - manages proxies
    - broadcasts images
    main loop:
        is save done? [else wait]
        queue grabs
        poll grabs
        check shifts
        regrab?
        report finished
        queue build frame
        save grab/norms?
        when frame done, save frame
        queue frame broadcast
"""

import ctypes
import datetime
import logging
import multiprocessing
import os
import time

import concurrent.futures
import cv2
import numpy

import andor
import datautils.structures.mp
import montage
import pizco

from .. import base
from ...config.checkers import require
from ... import log
from . import utils


logger = log.get_logger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)


class SharedBufferQueue(andor.bufferqueue.BufferQueue):
    def __init__(self, handle, shared_buffers, nbytes=None, dtype=None):
        super(SharedBufferQueue, self).__init__(handle, nbytes, dtype)
        self.shared_buffers = shared_buffers
        self.shared_index = 0

    def _allocate(self, n, dtype='uint16'):
        b = self.shared_buffers[self.shared_index]
        self.shared_index += 1
        if self.shared_index >= len(self.shared_buffers):
            self.shared_index = 0
        return b


class CameraSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, grab_buffers):
        logger.debug(
            "CameraSerf[%s] setup: %s, %s", self, config, grab_buffers)
        self.config = config
        self.triggers = 0
        self.nframes = self.config['nframes']
        self.connect()
        self.configure(config['features'])
        self.setup_buffers(grab_buffers)

    def exit(self):
        logger.debug("CameraSerf[%s] exit", self)
        self.camera.stop_acquisition()
        self.camera.disconnect()
        datautils.structures.mp.TimedSerf.exit(self)

    def connect(self):
        logger.debug("CameraSerf[%s] connect", self)
        self.camera = andor.open_camera(self.config['loc'])

    def configure(self, features):
        logger.debug("CameraSerf[%s] configure: %s", self, features)
        self.camera.stop_acquisition()
        if 'SFT' in self.config['loc']:
            try:
                for f in features:
                    setattr(self.camera, f, features[f])
            except:
                pass
        else:
            for f in features:
                setattr(self.camera, f, features[f])
        self.camera.start_acquisition()
        self.trigger_wait = max(
            self.config['features']['ExposureTime'] * 0.5, 0.01)
        self.crop = self.camera.calculate_crop()
        self.timeout = self.camera.calculate_timeout()

    def setup_buffers(self, grab_buffers):
        logger.debug("CameraSerf[%s] setup_buffers: %s", self, grab_buffers)
        h = self.camera.AOIHeight
        w = self.camera.AOIWidth
        s = self.camera.AOIStride
        if self.config['crop'] != [h, w, s]:
            raise ValueError(
                "Buffers size in config['crop'][%s] does not match camera[%s]"
                % (self.config['crop'], (h, w, s)))
        grab_buffer_objects = [b for b in grab_buffers]
        buffers = []
        self.grabs = []
        self.grab_buffer_index_map = {}
        for (i, b) in enumerate(grab_buffer_objects):
            buffers.append(utils.buffer_as_array(b, 'u2'))
            self.grabs.append(utils.buffer_as_array(b, 'u2', (h, w, s)))
            if id(b) in self.grab_buffer_index_map:
                raise Exception("Invalid duplicate buffer id %s" % (id(b), ))
            self.grab_buffer_index_map[id(b)] = i
        sbq = SharedBufferQueue(self.camera.handle, buffers)
        self.camera.buffers = sbq
        self.camera.buffers.nbytes = buffers[0].size * 2

    def trigger(self):
        logger.debug("CameraSerf[%s] trigger", self)
        self.camera.trigger()
        self.triggers += 1

    def update_buffers(self, im):
        logger.debug("CameraSerf[%s] update_buffers: %s", self, im)
        o = im
        while hasattr(o, 'base'):
            o = o.base
        bid = id(o)
        if bid not in self.grab_buffer_index_map:
            raise Exception
        gi = self.grab_buffer_index_map[bid]
        return gi

    def grab(self):
        logger.debug("CameraSerf[%s] grab", self)
        [self.camera.buffers.queue() for _ in xrange(self.nframes + 1)]  # 0
        self.trigger()  # 0
        t = self.trigger_wait
        time.sleep(t)
        for i in xrange(self.nframes):
            self.trigger()  # i + 1
            im = self.camera.capture(
                n=1, timeout=self.timeout, crop=False,
                autostart=False, trigger=False, retries=10)
            self.triggers -= 1
            buffer_index = self.update_buffers(im)
            meta = im.meta
            meta['buffer_index'] = buffer_index
            # report buffer gi as ready
            self.send('grab', meta)

    def regrab(self, trigger_next=True, flush=False):
        logger.debug("CameraSerf[%s] regrab", self)
        if trigger_next:
            self.camera.buffers.queue()  # queue next regrab
            self.trigger()  # trigger next regrab
        if self.triggers == 0:
            self.trigger()
        im = self.camera.capture(
            n=1, timeout=self.timeout, crop=False,
            autostart=False, trigger=False, retries=10)
        self.triggers -= 1
        buffer_index = self.update_buffers(im)
        meta = im.meta
        meta['buffer_index'] = buffer_index
        if flush:
            return
        self.send('grab', meta)

    def single(self):
        logger.debug("CameraSerf[%s] single", self)
        self.regrab(trigger_next=False)

    def flush(self):
        logger.debug("CameraSerf[%s] flush", self)
        [
            self.regrab(trigger_next=False, flush=True)
            for i in xrange(self.triggers)]

    def cool(self, value=None):
        logger.debug("CameraSerf[%s] cool: %s", self, value)
        # on new sdk requires stopping and restarting acquisition
        if value is None:
            if 'SFT' in self.config['loc']:
                return {
                    'SensorCooling': False,
                    'TemperatureStatus': 'Stabilised',
                    'TemperatureControl': '0.00',
                    'SensorTemperature': 0.0,
                    'FanSpeed': 'On',
                    }
            # return cooling information
            cool_info = dict([(k, getattr(self.camera, k)) for k in (
                "SensorCooling", "TemperatureStatus",
                "TemperatureControl", "SensorTemperature", "FanSpeed")])
            self.send('cool', cool_info)
            return
        if self.camera.SensorCooling == value:
            return
        self.camera.stop_acquisition()
        self.camera.SensorCooling = value
        self.camera.start_acquisition()


class FrameSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, norm_buffers, frame_buffer):
        logger.debug(
            "FrameSerf[%s] setup: %s, %s, %s",
            self, config, norm_buffers, frame_buffer)
        self.config = config
        self.norm_buffers = norm_buffers
        self.frame_buffer = frame_buffer
        self.norm_queue = []
        self.setup_buffers()

    def setup_buffers(self):
        logger.debug("FrameSerf[%s] setup_buffers", self)
        h, w, _ = self.config['crop']
        self.norms = [
            montage.io.Image(utils.buffer_as_array(b, 'f4', (h, w)))
            for b in self.norm_buffers]
        self.frame = montage.io.Image(
            utils.buffer_as_array(self.frame_buffer, 'u2', (h, w)))

    def add_norm(self, buffer_index):
        logger.debug("FrameSerf[%s] add_norm: %s", self, buffer_index)
        self.norm_queue.append(self.norms[buffer_index].copy())
        self.norm_queue[-1].meta['buffer_index'] = buffer_index

    def pop_norm(self, index=0):
        logger.debug("FrameSerf[%s] pop_norm: %s", self, index)
        self.norm_queue.pop(index)

    def queue_len(self):
        logger.debug("FrameSerf[%s] queue_len", self)
        return len(self.norm_queue)

    def clear_norm_queue(self):
        logger.debug("FrameSerf[%s] clear_norm_queue", self)
        self.norm_queue = []

    def build_frame(self, shifts):
        logger.debug("FrameSerf[%s] build_frame: %s", self, shifts)
        if len(shifts) != (len(self.norm_queue) - 1):
            raise ValueError(
                "len(shifts)[%s] != (len(norms)-1)[%s]"
                % (len(shifts), len(self.norm_queue) - 1))
        # deshift and average
        frame = montage.ops.transform.shift.deshift_and_average(
            self.norm_queue, shifts)
        # stretch
        fmin, fmax, _, _ = cv2.minMaxLoc(frame)
        cv2.normalize(frame, frame, 0, 65535, cv2.NORM_MINMAX)
        self.frame[:, :] = frame.astype('u2')
        # frame meta data [fmin, fmax]
        meta = {
            'range': (fmin, fmax),
            'buffer_indices': [
                n.meta['buffer_index'] for n in self.norm_queue],
        }
        self.send('frame', meta)


class AnalysisSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, grab_buffers, norm_buffers, bg_buffer):
        logger.debug(
            "AnalysisSerf[%s] setup: %s, %s, %s, %s",
            self, config, grab_buffers, norm_buffers, bg_buffer)
        self.config = config
        self.image_size = config['crop'][:2]
        self.grab_buffers = grab_buffers
        self.norm_buffers = norm_buffers
        self.bg_buffer = bg_buffer
        self.setup_buffers()
        self.configure_contrast(self.config['contrast'])
        self.configure_shift(self.config['shift'])

    def set_config(self, config):
        logger.debug("AnalysisSerf[%s] set_config: %s", self, config)
        self.config = config
        self.configure_contrast(self.config['contrast'])
        self.configure_shift(self.config['shift'])

    def setup_buffers(self):
        logger.debug("AnalysisSerf[%s] setup_buffers", self)
        h, w, s = self.config['crop']
        self.grabs = [
            montage.io.Image(utils.buffer_as_array(b, 'u2', (h, w, s)))
            for b in self.grab_buffers]
        self.norms = [
            utils.buffer_as_array(b, 'f4', (h, w)) for b in self.norm_buffers]
        self.bg = montage.io.Image(
            utils.buffer_as_array(self.bg_buffer, 'f4', (h, w)))

    def configure_contrast(self, cfg):
        logger.debug("AnalysisSerf[%s] configure_contrast: %s", self, cfg)
        self.contrast_results = [None for _ in xrange(len(self.norms))]
        self.contrast_crop = montage.ops.transform.cropping.calculate_crop(
            self.image_size, cfg['crop'])

    def configure_shift(self, cfg):
        logger.debug("AnalysisSerf[%s] configure_shift: %s", self, cfg)
        self.shift_results = [dict() for _ in xrange(len(self.norms))]
        self.shift_measurer = montage.ops.measures.shift.ShiftMeasurer(
            cfg['tcrop'], cfg['mcrop'], cfg['method'], self.image_size)

    def check_contrast(self, buffer_index):
        logger.debug("AnalysisSerf[%s] check_contrast: %s", self, buffer_index)
        result = montage.ops.measures.contrast.check_contrast(
            self.norms[buffer_index], self.contrast_crop)
        self.contrast_results[buffer_index] = result
        self.send('contrast', buffer_index, result)

    def clear_template(self):
        logger.debug("AnalysisSerf[%s] clear_template", self)
        self.shift_measurer.set_template(None)

    def set_template(self, buffer_index):
        logger.debug("AnalysisSerf[%s] set_template: %s", self, buffer_index)
        self.shift_measurer.set_template(self.norms[buffer_index])

    def normalize_grab(self, buffer_index):
        logger.debug("AnalysisSerf[%s] normalize_grab: %s", self, buffer_index)
        #cv2.multiply(
        #    self.grabs[buffer_index], self.bg,
        #    self.norms[buffer_index], dtype=cv2.CV_32F)
        self.norms[buffer_index][:, :] = self.grabs[buffer_index] * self.bg
        self.send('norm', buffer_index)

    def check_shift(self, buffer_index):
        logger.debug("AnalysisSerf[%s] check_shift: %s", self, buffer_index)
        result = self.shift_measurer.match(
            self.norms[buffer_index])
        self.shift_results[buffer_index] = result
        self.send('shift', buffer_index, result)

    def analyze_grab(self, buffer_index):
        logger.debug("AnalysisSerf[%s] analyze_grab: %s", self, buffer_index)
        self.normalize_grab(buffer_index)
        self.check_contrast(buffer_index)
        if self.shift_measurer.template is None:
            self.set_template(buffer_index)
        else:
            self.check_shift(buffer_index)


class SaverSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, grab_buffers, norm_buffers, frame_buffer):
        logger.debug(
            "SaverSerf[%s] setup: %s, %s, %s, %s",
            self, config, grab_buffers, norm_buffers, frame_buffer)
        # accumulate then save (to give the ability to drop bad frames)
        self.config = config
        self.grab_buffers = grab_buffers
        self.norm_buffers = norm_buffers
        self.frame_buffer = frame_buffer
        self.setup_buffers()

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
        self.frame = montage.io.Image(
            utils.buffer_as_array(self.frame_buffer, 'u2', (h, w)))

    def save_grabs(self, indicies, metas):
        logger.debug("SaverSerf[%s] save_grabs: %s, %s", self, indicies, metas)
        for (i, m) in zip(indicies, metas):
            self.grabs[i].meta = m
            self.grabs[i].meta['grab'] = i
            fn = utils.imwrite(self.grabs[i], self.config, 'grab')
            self.send('grab', i, fn)

    def save_norms(self, indicies, metas):
        logger.debug("SaverSerf[%s] save_norms: %s, %s", self, indicies, metas)
        for (i, m) in zip(indicies, metas):
            self.norms[i].meta = m
            self.norms[i].meta['grab'] = i
            fn = utils.imwrite(self.norms[i], self.config, 'norm')
            self.send('norm', i, fn)

    def save_frame(self, meta):
        logger.debug("SaverSerf[%s] save_frame: %s", self, meta)
        self.frame.meta = meta
        fn = utils.imwrite(self.frame, self.config, 'frame')
        self.send('frame', fn)


class CameraLord(datautils.structures.mp.Lord):
    def __init__(self, config, buffers):
        logger.debug("CameraLord[%s] __init__: %s, %s", self, config, buffers)
        datautils.structures.mp.Lord.__init__(self)
        self.config = config
        self.buffers = buffers
        self._grab_indices = []
        self.cool_info = None

    def start(self, wait=True):
        logger.debug("CameraLord[%s] start", self)
        datautils.structures.mp.Lord.start(self, CameraSerf, (
            self.config, self.buffers.grab_buffers), wait=wait)

    def set_cooling(self, value):
        logger.debug("CameraLord[%s] set_cooling: %s", self, value)
        self.send('cool', value)

    def poll_cooling(self):
        logger.debug("CameraLord[%s] poll_cooling", self)
        self.cool_info = None
        self.send('cool', None)
        while self.cool_info is None:
            self.update()
        return self.cool_info

    def cool(self, info):
        logger.debug("CameraLord[%s] cool: %s", self, info)
        self.cool_info = info

    def get_grab(self, index):
        logger.debug("CameraLord[%s] get_grab: %s", self, index)
        """index relative to capture"""
        return self.buffers.grabs[self._grab_indices[index]]

    def start_grab(self, meta):
        logger.debug("CameraLord[%s] start_grab", self)
        meta['camera'] = self.config['index']
        self.send('grab')
        for g in self.buffers.grabs:
            g.meta = meta.copy()

    def grab(self, meta):
        logger.debug("CameraLord[%s] grab: %s", self, meta)
        index = meta['buffer_index']
        self.buffers.grabs[index].meta.update(meta)
        self._grab_indices.append(index)

    def regrab(self, trigger_next=True, flush=False):
        logger.debug(
            "CameraLord[%s] regrab: %s, %s", self, trigger_next, flush)
        self.send('regrab', trigger_next, flush)

    def single(self):
        logger.debug("CameraLord[%s] single", self)
        self.send('single')

    def flush(self):
        logger.debug("CameraLord[%s] flush", self)
        self.send('flush')


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
                self.buffers.frame_buffer), wait=wait)

    def add_norm(self, buffer_index):
        logger.debug("FrameLord[%s] add_norm: %s", self, buffer_index)
        self.send('add_norm', buffer_index)

    def pop_norm(self, index=0):
        logger.debug("FrameLord[%s] pop_norm: %s", self, index)
        self.send('pop_norm', index)

    def clear_norm_queue(self):
        self.send('clear_norm_queue')

    def build_frame(self, shifts):
        logger.debug("FrameLord[%s] build_frame: %s", self, shifts)
        self.send('build_frame', shifts)

    def frame(self, meta):
        logger.debug("FrameLord[%s] frame: %s", self, meta)
        # get meta from norms
        meta['shifts'] = []
        meta['contrasts'] = []
        meta['frame counts'] = []
        meta['times'] = []
        for ni in meta['buffer_indices']:
            n = self.buffers.norms[ni]
            meta.update(n.meta)
            if 'shift' in n.meta:
                meta['shifts'].append(n.meta['shift'])
            meta['contrasts'].append(n.meta['contrast'])
            meta['frame counts'].append(n.meta['frame count'])
            meta['times'].append(n.meta['DateTime'].strftime('%y%m%d%H%M%S%f'))
        self.buffers.frame.meta = meta


class AnalysisLord(datautils.structures.mp.Lord):
    def __init__(self, config, buffers):
        logger.debug(
            "AnalysisLord[%s] __init__: %s, %s", self, config, buffers)
        datautils.structures.mp.Lord.__init__(self)
        self.config = config
        self.buffers = buffers
        self.contrast_results = [None for _ in xrange(len(self.buffers.norms))]
        self.shift_results = [{} for _ in xrange(len(self.buffers.norms))]

    def start(self, wait=True):
        logger.debug("AnalysisLord[%s] start", self)
        datautils.structures.mp.Lord.start(
            self, AnalysisSerf, (
                self.config, self.buffers.grab_buffers,
                self.buffers.norm_buffers, self.buffers.bg_buffer), wait=wait)

    def set_config(self, config):
        logger.debug("AnalysisLord[%s] set_config: %s", self, config)
        self.send('set_config', config)

    def clear_template(self):
        logger.debug("AnalysisLord[%s] clear_template", self)
        self.send('clear_template')

    def set_template(self, index):
        logger.debug("AnalysisLord[%s] set_template: %s", self, index)
        self.send('set_template', index)

    def check_shift(self, index):
        logger.debug("AnalysisLord[%s] check_shift: %s", self, index)
        self.send('check_shift', index)

    def analyze_grab(self, index):
        logger.debug("AnalysisLord[%s] analyze_grab: %s", self, index)
        self.send('analyze_grab', index)

    def norm(self, index):
        logger.debug("AnalysisLord[%s] norm: %s", self, index)

    def contrast(self, index, result):
        logger.debug("AnalysisLord[%s] contrast: %s, %s", self, index, result)
        self.contrast_results[index] = result

    def shift(self, index, result):
        logger.debug("AnalysisLord[%s] shift: %s, %s", self, index, result)
        self.shift_results[index] = result


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
                self.buffers.norm_buffers, self.buffers.frame_buffer
            ), wait=wait)

    def save_grabs(self, indices):
        ms = [self.buffers.grabs[i].meta for i in indices]
        self.send('save_grabs', indices, ms)

    def save_norms(self, indices):
        ms = [self.buffers.norms[i].meta for i in indices]
        self.send('save_norms', indices, ms)

    def save_frame(self):
        self.send('save_frame', self.buffers.frame.meta)

    def grab(self, index, fn):
        pass

    def norm(self, index, fn):
        pass

    def frame(self, fn):
        pass


def time_call(l, s, *args, **kwargs):
    t0 = time.time()
    l.send(s, *args, **kwargs)
    when_finished(l, s)
    t1 = time.time()
    print("%s took %s" % (s, (t1 - t0)))


def when_finished(l, s):
    if l.state() == 'wait':
        l.update()
    if l.state() == 'wait':
        return
    while l.state() == s:
        l.update()


def test_camera_lord(config=None):
    cfg = default_config
    ccfg = base.resolve_config('camera')
    cfg['loc'] = ccfg['loc']
    cfg['addr'] = ccfg['addr']
    if config is not None:
        cfg.update(config)
    buffers = SharedBuffers(cfg)
    buffers.bg[:, :] = 2.
    lord = CameraLord(cfg, buffers)
    lord.start()
    while lord.state() is None:
        lord.update()
    time_call(lord, 'single')
    im = lord.get_grab(0)
    lord.update()
    time_call(lord, 'grab')
    time_call(lord, 'flush')
    time_call(lord, 'grab')
    time_call(lord, 'flush')
    time_call(lord, 'grab')
    time_call(lord, 'flush')
    lord.stop()
    return im, lord, buffers


def test_frame_lord(config=None):
    cfg = default_config
    ccfg = base.resolve_config('camera')
    cfg['loc'] = ccfg['loc']
    cfg['addr'] = ccfg['addr']
    if config is not None:
        cfg.update(config)
    buffers = SharedBuffers(cfg)
    buffers.norms[0][:, :] = 10.
    buffers.norms[1][:, :] = 2.
    buffers.norms[2][:, :] = 3.
    buffers.norms[3][:, :] = 3.
    buffers.norms[4][:, :] = 2.
    buffers.norms[0][1200, 1200] = 100.
    buffers.norms[1][1200, 1200] = 100.
    buffers.norms[2][1201, 1201] = 100.
    buffers.norms[3][1199, 1199] = 100.
    buffers.norms[4][1200, 1200] = 100.
    shifts = [
        #{'x': 0, 'y': 0},
        #{'x': 1, 'y': 1},
        #{'x': -1, 'y': -1},
        {'x': 0, 'y': 0},
        {'x': 0, 'y': 0},
        {'x': 0, 'y': 0},
    ]
    lord = FrameLord(cfg, buffers)
    lord.start(wait=True)
    time_call(lord, 'add_norm', 0)
    time_call(lord, 'add_norm', 1)
    time_call(lord, 'add_norm', 2)
    time_call(lord, 'add_norm', 3)
    time_call(lord, 'build_frame', shifts)
    frame0 = buffers.frame.copy()
    time_call(lord, 'add_norm', 4)
    time_call(lord, 'pop_norm', 0)
    time_call(lord, 'build_frame', shifts)
    frame1 = buffers.frame.copy()
    buffers.norms[0][:, :] = 0.
    buffers.norms[1][:, :] = 0.
    buffers.norms[2][:, :] = 0.
    buffers.norms[3][:, :] = 0.
    buffers.norms[4][:, :] = 0.
    time_call(lord, 'build_frame', shifts)
    frame2 = buffers.frame.copy()
    lord.update()
    lord.stop()
    return frame0, frame1, frame2


def test_analysis_lord(config=None):
    cfg = default_config
    ccfg = base.resolve_config('camera')
    cfg['loc'] = ccfg['loc']
    cfg['addr'] = ccfg['addr']
    if config is not None:
        cfg.update(config)
    buffers = SharedBuffers(cfg)
    lord = AnalysisLord(cfg, buffers)
    lord.start(wait=True)
    buffers.grabs[0][:, :] = 10.
    buffers.grabs[1][:, :] = 2.
    buffers.grabs[2][:, :] = 3.
    buffers.grabs[3][:, :] = 3.
    buffers.grabs[4][:, :] = 2.
    buffers.bg[:, :] = 2.
    time_call(lord, 'normalize_grab', 0)
    assert numpy.all(buffers.norms[0] == 20.)
    time_call(lord, 'normalize_grab', 1)
    assert numpy.all(buffers.norms[1] == 4.)
    time_call(lord, 'normalize_grab', 2)
    assert numpy.all(buffers.norms[2] == 6.)
    time_call(lord, 'normalize_grab', 3)
    assert numpy.all(buffers.norms[3] == 6.)
    time_call(lord, 'normalize_grab', 4)
    assert numpy.all(buffers.norms[4] == 4.)
    time_call(lord, 'check_contrast', 0)
    print lord.contrast_results[0]
    time_call(lord, 'check_contrast', 1)
    print lord.contrast_results[1]
    time_call(lord, 'check_contrast', 2)
    print lord.contrast_results[2]
    time_call(lord, 'check_contrast', 3)
    print lord.contrast_results[3]
    time_call(lord, 'check_contrast', 4)
    print lord.contrast_results[4]
    time_call(lord, 'set_template', 0)
    time_call(lord, 'check_shift', 1)
    print lord.shift_results[1]
    time_call(lord, 'check_shift', 2)
    print lord.shift_results[2]
    time_call(lord, 'check_shift', 3)
    print lord.shift_results[3]
    time_call(lord, 'check_shift', 4)
    print lord.shift_results[4]
    lord.stop()
    return lord, buffers


def test_saver_lord(config=None):
    pass


def test_node(config=None):
    cfg = default_config
    ccfg = base.resolve_config('camera')
    cfg['loc'] = ccfg['loc']
    cfg['addr'] = ccfg['addr']
    if config is not None:
        cfg.update(config)
    node = CameraNode(cfg)
    node.connect()
    return node


def test_node_grab(config=None):
    node = test_node(config)

    def time_grab(meta=None):
        t0 = time.time()
        m = {'row': 0, 'col': 0}
        if meta is not None:
            m.update(meta)
        node.start_grab(m)
        t1 = time.time()
        while node.controller.state == 'save':
            node.update_controller()
        t2 = time.time()
        print("Grab: %.6f" % (t1 - t0))
        print("Save: %.6f" % (t2 - t1))
    time_grab()
    return node, time_grab
