#!/usr/bin/env python

import os
import time

import andor
import datautils.structures.mp

from .... import log
from .. import utils


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)

# allow stop/start of acquisition on AT_ERR_NODATA
allow_reacquire = True


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

    #def queue(self, nbytes=None, dtype=None):
    #    i = self.shared_index
    #    super(SharedBufferQueue, self).queue(nbytes=nbytes, dtype=dtype)
    #    return i


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
        if 'log_serfs' in config:
            utils.log_serf_to_directory(self, config['log_serfs'])

    def exit(self):
        logger.debug("CameraSerf[%s] exit", self)
        self.camera.stop_acquisition()
        self.camera.disconnect()
        datautils.structures.mp.TimedSerf.exit(self)

    def connect(self):
        logger.debug("CameraSerf[%s] connect", self)
        self.camera = andor.open_camera(self.config['loc'])

    def restart_acquisition(self):
        logger.debug("CameraSerf[%s] restart_acquisition", self)
        self.camera.stop_acquisition()
        self.camera.start_acquisition()

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
        logger.debug("CameraSerf[%s] update_buffers: %s", self, id(im))
        o = im
        while hasattr(o, 'base'):
            o = o.base
        bid = id(o)
        if bid not in self.grab_buffer_index_map:
            raise Exception
        gi = self.grab_buffer_index_map[bid]
        return gi

    def grab(self, meta):
        logger.debug("CameraSerf[%s] grab", self)
        for _ in xrange(self.nframes + 1):
            self.camera.buffers.queue()
        self.trigger()  # 0
        t = self.trigger_wait
        time.sleep(t)
        reacquired = False
        for i in xrange(self.nframes):
            self.trigger()  # i + 1
            try:
                #if not hasattr(self, 'kill_me'):
                #    self.kill_me = 0
                #self.kill_me += 1
                #if (self.kill_me % 20) == 0:
                #    raise andor.error.AndorNoData('fake')

                im = self.camera.capture(
                    n=1, timeout=self.timeout, crop=False,
                    autostart=False, trigger=False, retries=10)
            except andor.error.AndorNoData as e:
                logger.error(
                    "AT_ERR_NODATA on grab %s: %s" % (i, e))
                if not allow_reacquire:
                    raise e
                reacquired = True
                logger.error("attempting to restart acquisition")
                t0 = time.time()
                self.camera.stop_acquisition()
                self.camera.start_acquisition()
                self.triggers = 0
                for _ in xrange(self.nframes + 1 - i):
                    self.camera.buffers.queue()
                self.trigger()
                time.sleep(self.trigger_wait)
                self.trigger()
                im = self.camera.capture(
                    n=1, timeout=self.timeout, crop=False,
                    autostart=False, trigger=False, retries=10)
                t1 = time.time()
                logger.error(
                    "acquisition restart worked[%s]"
                    % (t1 - t0, ))
                buffer_index = self.update_buffers(im)
                self.send('nodata', buffer_index)
            self.triggers -= 1
            buffer_index = self.update_buffers(im)
            m = meta.copy()
            m.update(im.meta)
            if reacquired:
                m['reacquired'] = True
            m['buffer_index'] = buffer_index
            # report buffer as ready
            self.send('grab', m)

    def regrab(self, meta, trigger_next=True, flush=False):
        logger.debug("CameraSerf[%s] regrab", self)
        reacquired = False
        if trigger_next:
            self.camera.buffers.queue()  # queue next regrab
            #self.buffers.lock_grab(bi)
            self.trigger()  # trigger next regrab
        if self.triggers == 0:
            self.trigger()
        try:
            im = self.camera.capture(
                n=1, timeout=self.timeout, crop=False,
                autostart=False, trigger=False, retries=10)
        except andor.error.AndorNoData as e:
            logger.error(
                "AT_ERR_NODATA on regrab: %s" % e)
            if not allow_reacquire:
                raise e
            reacquired = True
            logger.error("attempting to restart acquisition")
            t0 = time.time()
            self.camera.stop_acquisition()
            self.camera.start_acquisition()
            self.triggers = 0
            self.camera.buffers.queue()
            self.trigger()
            im = self.camera.capture(
                n=1, timeout=self.timeout, crop=False,
                autostart=False, trigger=False, retries=10)
            if trigger_next:
                self.camera.buffers.queue()
                self.trigger()
            t1 = time.time()
            logger.error(
                "acquisition restart worked[%s]"
                % (t1 - t0, ))
            buffer_index = self.update_buffers(im)
            self.send('nodata', buffer_index)
        self.triggers -= 1
        buffer_index = self.update_buffers(im)
        meta.update(im.meta)
        meta['buffer_index'] = buffer_index
        if reacquired:
            meta['reacquired'] = True
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
                    im[:] = v
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

    def restart_acquisition(self):
        logger.debug("CameraLord[%s] restart_acquisition", self)
        self.send('restart_acquisition')

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

    def nodata(self, buffer_index):
        logger.debug("CameraLord[%s] nodata: %s", self, buffer_index)
