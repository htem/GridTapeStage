#!/usr/bin/env python

import datetime
import os

import numpy

import datautils.structures.mp
import montage

from .... import log
from .. import utils


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


#class SharedBufferQueue(andor.bufferqueue.BufferQueue):
#    def __init__(self, handle, shared_buffers, nbytes=None, dtype=None):
#        super(SharedBufferQueue, self).__init__(handle, nbytes, dtype)
#        self.shared_buffers = shared_buffers
#        self.shared_index = 0
#
#    def _allocate(self, n, dtype='uint16'):
#        b = self.shared_buffers[self.shared_index]
#        self.shared_index += 1
#        if self.shared_index >= len(self.shared_buffers):
#            self.shared_index = 0
#        return b


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
        self.grab_count = 0
        if 'log_serfs' in config:
            utils.log_serf_to_directory(self, config['log_serfs'])

    def exit(self):
        logger.debug("CameraSerf[%s] exit", self)
        datautils.structures.mp.TimedSerf.exit(self)

    def connect(self):
        logger.debug("CameraSerf[%s] connect", self)

    def configure(self, features):
        logger.debug("CameraSerf[%s] configure: %s", self, features)
        self.trigger_wait = max(
            self.config['features']['ExposureTime'] * 0.5, 0.01)

    def setup_buffers(self, grab_buffers):
        logger.debug("CameraSerf[%s] setup_buffers: %s", self, grab_buffers)
        h, w, s = self.config['crop']
        self.grabs = [
            montage.io.Image(utils.buffer_as_array(b, 'u2', (h, w, s)))
            for b in grab_buffers]
        self.bi = 0

    def trigger(self):
        logger.debug("CameraSerf[%s] trigger", self)
        self.triggers += 1

    def grab(self, meta):
        logger.debug("CameraSerf[%s] grab", self)
        # track buffers here
        self.trigger()
        for i in xrange(self.nframes):
            self.trigger()  # i + 1
            g = self.grabs[self.bi]
            g[:, :] = self.grab_count
            self.grab_count += 1
            if self.grab_count > 65535:
                self.grab_count = 0
            self.triggers -= 1
            m = meta.copy()
            m.update(g.meta)
            m['frame count'] = self.grab_count
            m['DateTime'] = datetime.datetime.now()
            m['buffer_index'] = self.bi
            self.bi += 1
            if self.bi >= len(self.grabs):
                self.bi = 0
            # report buffer as ready
            self.send('grab', m)

    def regrab(self, meta, trigger_next=True, flush=False):
        logger.debug("CameraSerf[%s] regrab", self)
        if trigger_next:
            self.trigger()  # trigger next regrab
        if self.triggers == 0:
            self.trigger()
        g = self.grabs[self.bi]
        g[:, :] = self.grab_count
        self.grab_count += 1
        if self.grab_count > 65535:
            self.grab_count = 0
        self.triggers -= 1
        meta.update(g.meta)
        meta['frame count'] = self.grab_count
        meta['DateTime'] = datetime.datetime.now()
        meta['buffer_index'] = self.bi
        self.bi += 1
        if self.bi >= len(self.grabs):
            self.bi = 0
        if flush:
            #self.buffers.unlock_grab(buffer_index)
            return
        if self.config.get('fake', False):
            # check if image should be set to 1 value
            fn = os.path.abspath(os.path.expanduser(
                self.config['fakefile']))
            if os.path.exists(fn):
                with open(fn, 'r') as f:
                    v = int(f.read())
                    g[:] = v
        self.send('grab', meta)

    def single(self, meta):
        logger.debug("CameraSerf[%s] single", self)
        self.regrab(meta, trigger_next=False)

    def flush(self):
        logger.debug("CameraSerf[%s] flush: %s", self, self.triggers)
        [
            self.regrab({}, trigger_next=False, flush=True)
            for i in xrange(self.triggers)]

    def cool(self, value=None):
        logger.debug("CameraSerf[%s] cool: %s", self, value)
        # on new sdk requires stopping and restarting acquisition
        if value is None:
            return {
                'SensorCooling': False,
                'TemperatureStatus': 'Stabilised',
                'TemperatureControl': '0.00',
                'SensorTemperature': 0.0,
                'FanSpeed': 'On',
            }


class CameraLord(datautils.structures.mp.Lord):
    def __init__(self, config, buffers):
        logger.debug("CameraLord[%s] __init__: %s, %s", self, config, buffers)
        datautils.structures.mp.Lord.__init__(self)
        self.config = config
        self.buffers = buffers
        #self._grab_indices = []
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

    def start_grab(self, meta):
        logger.debug("CameraLord[%s] start_grab", self)
        meta['camera'] = self.config['index']
        self.send('grab', meta)

    def grab(self, meta):
        logger.debug("CameraLord[%s] grab: %s", self, meta)
        index = meta['buffer_index']
        self.buffers.lock_grab(meta['buffer_index'])
        self.buffers.grabs[index].meta.update(meta)

    def regrab(self, meta, trigger_next=True, flush=False):
        logger.debug(
            "CameraLord[%s] regrab: %s, %s", self, trigger_next, flush)
        self.send('regrab', meta, trigger_next, flush)

    def single(self, meta):
        logger.debug("CameraLord[%s] single", self)
        self.send('single', meta)

    def flush(self):
        logger.debug("CameraLord[%s] flush", self)
        self.send('flush')
