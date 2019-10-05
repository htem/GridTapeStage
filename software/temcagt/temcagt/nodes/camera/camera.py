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

import datetime
import logging
import os

import concurrent.futures
import cv2
import numpy

import montage
import pizco

from .. import base
from ... import config
from ... import log

from . import controllers
from . import processes
from . import utils

default_config = {
    "loc": 'SFT-1000',
    "addr": 'tcp://127.0.0.1:11020',
    #"log_serfs": "~/Desktop/serf_logs",  # define to log serf states
    "nframes": 4,
    "index": 0,
    "nbuffercopies": 10,
    #"crop": (2048, 2048, 4120),  # for actual camera
    #"n_words": 4223000,  # for actual camera, with meta data
    #"n_words": 4218880,  # for actual camera, no meta data
    #"crop": (2160, 2560, 5120),  # for sim camera
    #"n_words": 5529600,  # for sim camera
    "features": {
        "CycleMode": "Continuous",
        "TriggerMode": "Software",
        "ExposureTime": 0.025,
        "AOIHeight": 2048,
        "AOIWidth": 2048,
        "AccumulateCount": 1,
        "MetadataEnable": False,
        "MetadataTimestamp": False,
        "Overlap": True,
        "PixelEncoding": "Mono16",
        "PixelReadoutRate": "270 MHz",
        "SimplePreAmpGainControl": "16-bit (low noise & high well capacity)",
        "SpuriousNoiseFilter": True,
    },
    #"fake": True,
    #"fakefile": "~/.temcagt/fake/camera",
    "contrast": {
        "crop": 400,
        "min": 0.01,
        "name": "contrast",
    },
    "shift": {
        "tcrop": 400,
        "mcrop": 500,
        "method": "TM_CCORR_NORMED",
        "max_shift": 4,
        "min_match": 0.8,
        #"max_shift": 400000,  # to make all grabs success
        #"min_match": 0.0,
        "name": "shift",
    },
    "broadcast": {
        "enable": True,
        "downsample": 8,
        "frame": True,
        "percentiles": [5, 95],
    },
    "stream": {
        "enable": False,
        "delay": 0.5,
        "grab_type": None,
    },
    "stats": {
        "enable": True,
        "beam": True,
        "mean": True,
        "crop": 512,
        "std": True,
        "focus": True,
        "histogram": True,
        "focus_method": "gradient_focus",
    },
    "nregrabs": 1,
    "save": {
        "directory": "/tmp",
        "filename_formats": {
            "grab": '{camera}/{row:04.0f}/'
                    '{row:04.0f}_{col:04.0f}_{camera}_{grab}_'
                    '{DateTime:%y%m%d%H%M%S%f}.tif',

            "norm": '{camera}/{row:04.0f}/'
                    '{row:04.0f}_{col:04.0f}_{camera}_{grab}_n_'
                    '{DateTime:%y%m%d%H%M%S%f}.tif',
            "frame": '{camera}/{row:04.0f}/'
                     '{row:04.0f}_{col:04.0f}_{camera}_m.tif',
            "metric": '{camera}/'
                      'cam{camera}_{metric}_'
                      '{DateTime:%y%m%d%H%M%S%f}.tif',
        },
        "grab": False,
        "norm": False,
        "frame": True,
        "on_fail": True,  # should be True/False
    },
}

logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class CameraNode(base.IONode):
    def __init__(self, cfg=None):
        crop, n_words = utils.lookup_image_dimensions(cfg)
        cfg['crop'] = crop
        cfg['n_words'] = n_words
        base.IONode.__init__(self, cfg)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        self.new_image = pizco.Signal(nargs=1)
        self.new_stats = pizco.Signal(nargs=1)
        self.new_stats_future = None

        self.buffers = None
        self.camera = None
        self.frame = None
        self.norm = None
        self.analysis = None
        self.saver = None
        self.stats = None
        self.controller = None

        self.meta = {}  # non-grab meta
        self.mean_percentiles = None
        self._stream_cb = None

    def __repr__(self):
        cfg = self.config()
        return "{}.{} at {} addr {} loc {}".format(
            self.__module__, self.__class__, hex(id(self)),
            cfg.get('addr', ''), cfg.get('loc', ''))

    def __del__(self):
        logger.debug("CameraNode[%s] __del__", self)
        self.disconnect(force=True)
        super(CameraNode, self).__del__()

    def config_delta(self, delta):
        logger.debug("CameraNode[%s] config_delta: %s", self, delta)
        if not self.connected():
            return
        # if anything changes buffer sizes, then disconnect and reconnect
        if (
                "nframes" in delta or
                "nregrabs" in delta or
                "features" in delta or
                "loc" in delta or
                "crop" in delta or
                "n_words" in delta or
                "fake" in delta or
                "fakefile" in delta):
            logger.debug("CameraNode[%s] config_delta(reconnecting)", self)
            self.disconnect()
            self.connect()
        if 'save' in delta:
            logger.debug("CameraNode[%s] config_delta(updating saver)", self)
            self.saver.set_config(self.config())
        if 'contrast' in delta or 'shift' in delta:
            logger.debug(
                "CameraNode[%s] config_delta(updating analysis)", self)
            self.analysis.set_config(self.config())
        if 'stats' in delta:
            logger.debug(
                "CameraNode[%s] config_delta(updating stats)", self)
            self.stats.set_config(self.config())
        if 'stream' in delta:
            if delta['stream'].get('enable', False):
                if self._stream_cb is None:
                    self.start_streaming()
            else:
                if self._stream_cb is not None:
                    self.stop_streaming()

    def connect(self):
        logger.debug("CameraNode[%s] connect", self)
        if self.connected():
            return
        self.check_config()
        cfg = self.config()

        # handle each process
        if self.buffers is not None:
            bg = self.buffers.bg[:, :]
            logger.debug("CameraNode[%s] connect: found bg: %s", self, bg)
        else:
            bg = None
        self.buffers = utils.SharedBuffers(cfg)
        if (
                self.camera is not None and self.camera.process is not None
                and self.camera.process.is_alive()):
            self.camera.stop()
        self.camera = processes.CameraLord(cfg, self.buffers)
        if (
                self.frame is not None and self.frame.process is not None
                and self.frame.process.is_alive()):
            self.frame.stop()
        self.frame = processes.FrameLord(cfg, self.buffers)
        if (
                self.norm is not None and self.norm.process is not None
                and self.norm.process.is_alive()):
            self.norm.stop()
        self.norm = processes.NormLord(cfg, self.buffers)
        if (
                self.analysis is not None and self.analysis.process is not None
                and self.analysis.process.is_alive()):
            self.analysis.stop()
        self.analysis = processes.AnalysisLord(cfg, self.buffers)
        if (
                self.saver is not None and self.saver.process is not None
                and self.saver.process.is_alive()):
            self.saver.stop()
        self.saver = processes.SaverLord(cfg, self.buffers)
        if (
                self.stats is not None and self.stats.process is not None
                and self.stats.process.is_alive()):
            self.stats.stop()
        self.stats = processes.StatsLord(cfg, self.buffers)

        logger.debug("CameraNode[%s] connect: set bg: %s", self, id(bg))
        self.set_background(bg)

        self.camera.start()
        self.norm.start()
        self.analysis.start()
        self.frame.start()
        self.saver.start()
        self.stats.start()

    def disconnect(self, force=False):
        logger.debug("CameraNode[%s] disconnect", self)
        if not self.connected() and not force:
            return
        self.stop_streaming()
        if hasattr(self, 'controller') and self.controller is not None:
            self.controller.disconnect()
            self.controller = None
        if self.stats is not None:
            self.stats.stop()
            self.stats = None
        if self.saver is not None:
            self.saver.stop()
            self.saver = None
        if self.frame is not None:
            self.frame.stop()
            self.frame = None
        if self.norm is not None:
            self.norm.stop()
            self.norm = None
        if self.analysis is not None:
            self.analysis.stop()
            self.analysis = None
        if self.camera is not None:
            self.camera.stop()
            self.camera = None

    def restart_acquisition(self):
        self.camera.restart_acquisition()

    def start_process_logs(self, directory):
        if directory is None:
            fn = lambda k: None
        else:
            fn = lambda k: os.path.join(directory, '%s.log' % k)
        if not os.path.exists(directory):
            os.makedirs(directory)
        for k in ('camera', 'analysis', 'frame', 'saver'):
            a = getattr(self, k)
            a.send('set_log', fn(k))

    def process_state(self):
        processes = {}
        for k in ('camera', 'analysis', 'frame', 'saver'):
            a = getattr(self, k)
            if a is None:
                processes[k] = 'attribute is None'
            elif a.process is None:
                processes[k] = 'process is None'
            elif a.process.is_alive():
                processes[k] = 'alive'
            else:
                processes[k] = 'dead'
        return processes

    def connected(self):
        if (
                (self.camera is None) or
                (self.norm is None) or
                (self.analysis is None) or
                (self.frame is None) or
                (self.saver is None) or
                (self.stats is None)):
            return False
        if (
                (self.camera.process is None) or
                (self.norm.process is None) or
                (self.analysis.process is None) or
                (self.frame.process is None) or
                (self.stats.process is None) or
                (self.saver.process is None)):
            return False
        if (
                self.camera.process.is_alive() and
                self.norm.process.is_alive() and
                self.analysis.process.is_alive() and
                self.frame.process.is_alive() and
                self.stats.process.is_alive() and
                self.saver.process.is_alive()):
            return True
        return False

    def check_config(self, cfg=None):
        if cfg is None:
            cfg = self.config()
        [config.checkers.require(cfg, k) for k in
            'loc nframes index nregrabs'.split()]
        # TODO

    # -- cooling --
    def set_cooling(self, value):
        logger.debug("CameraNode[%s] set_cooling: %s", self, value)
        if not self.connected():
            raise IOError("set_cooling called on not connected node")
        self.camera.set_cooling(value)

    def poll_cooling(self):
        logger.debug("CameraNode[%s] poll_cooling", self)
        if not self.connected():
            raise IOError("poll_cooling called on not connected node")
        return self.camera.poll_cooling()

    def broadcast_stats(self, stats):
        logger.debug("CameraNode[%s] broadcast_stats: %s", self, id(stats))
        if self.new_stats_future is not None:
            logger.debug(
                "CameraNode[%s] broadcast_stats: set future %s",
                self, self.new_stats_future)
            self.new_stats_future.set_result(stats)
            self.new_stats_future = None
        self.new_stats.emit(stats)

    def get_new_stats(self):
        if not self.connected():
            raise IOError("get_new_stats called on not connected node")
        logger.debug(
            "CameraNode[%s] get_new_stats: %s", self, self.new_stats_future)
        if self.new_stats_future is not None:
            return self.new_stats_future
        self.new_stats_future = concurrent.futures.Future()
        logger.debug(
            "CameraNode[%s] get_new_stats: %s", self, self.new_stats_future)
        self.start_streaming()
        logger.debug(
            "CameraNode[%s] started streaming", self)
        return self.new_stats_future

    # -- stream --
    def broadcast(self, im, stats=False):
        logger.debug("CameraNode[%s] broadcast: %s", self, id(im))
        bcfg = self.config()['broadcast']
        if not bcfg.get('enable', False):
            return
        ## fake
        #if bcfg.get('fake', False):
        #    # check if image should be set to 1 value
        #    fn = os.path.abspath(os.path.expanduser(bcfg['fakefile']))
        #    if os.path.exists(fn):
        #        with open(fn, 'r') as f:
        #            v = int(f.read())
        #            im[:] = v
        #            im.meta['range'] = (v, v)
        if bcfg.get('frame', True):
            ds = bcfg.get('downsample', 1)
            if ds == 1:
                self.new_image.emit(im)
            else:
                self.new_image.emit(montage.io.Image(
                    cv2.resize(im, None, fx=1./ds, fy=1./ds),
                    im.meta))

    def stop_streaming(self):
        if self._stream_cb is None:
            return  # not streaming
        self.config({'stream': {'enable': False}})
        # remove timeout
        logger.debug("CameraNode[%s] stop_stream", self)
        try:
            if self._stream_cb is not None:
                self.loop.remove_timeout(self._stream_cb)
        except Exception as e:
            import traceback
            logger.debug(
                "CameraNode[%s] stop_stream remove_timeout failed: %s, %s, %s",
                self, self._stream_cb, e, traceback.format_exc())
            if self._stream_cb is not None:
                raise e
        self._stream_cb = None

    def start_streaming(self, grab_type=None):
        if self._stream_cb is not None:
            return  # already streaming
        logger.debug("CameraNode[%s] start_stream: %s", self, grab_type)
        cfg = self.config()['stream']
        if grab_type is None:
            grab_type = cfg.get('grab_type', None)
        if grab_type is None:
            grab_type = 'grab'
        self._stream_cb = self.loop.call_later(
            cfg['delay'], self.stream, grab_type)
        if not cfg.get('enable', False):
            self.config({'stream': {'enable': True}})

    def is_streaming(self):
        return self._stream_cb is not None

    def stream(self, grab_type='grab', in_pool=False):
        if not self.connected():
            raise IOError("stream called on not connected node")
        if in_pool is False:
            return self.pool.submit(
                self.stream, grab_type=grab_type, in_pool=True)
        logger.debug("CameraNode[%s] stream: %s", self, grab_type)
        #im, ff = self.single(grab_type=grab_type, in_pool=in_pool, free=False)
        im, ff = self.single(
            grab_type=grab_type, in_pool=in_pool, broadcast=True, free=False)
        #self.broadcast(im)
        ff()
        if self.config()['stream'].get('enable', False):
            self._stream_cb = None
            self.start_streaming(grab_type)
        else:
            self.stop_streaming()

    # -- background --
    def trigger_background_grab(self, in_pool=False):
        if not self.connected():
            raise IOError(
                "trigger_background_grab called on not connected node")
        if in_pool is False:
            return self.pool.submit(
                self.trigger_background_grab, in_pool=True)
        logger.debug("CameraNode[%s] trigger_background_grab", self)
        im, ff = self.single(in_pool=in_pool, free=False)
        self.image_metrics.process(im)
        # free image/grab
        ff()

    def compute_background(self, scalar=None, save=False):
        logger.debug("CameraNode[%s] compute_background: %s", self, save)
        if scalar is None:
            scalar = numpy.mean(self.image_metrics.mean_image)
        # save the mean
        self.image_metrics.scalar = scalar
        im = self.image_metrics.mean_image.copy()
        ps = self.config().get('broadcast', {}).get('percentiles', [5, 95])
        self.mean_percentiles = numpy.percentile(im, ps)
        im[im == 0] = 1.
        self.set_background(scalar / im)
        self.meta['scalar'] = scalar
        #self.set_background(self.image_metrics.mean_image)
        if save:
            self.save_image_metrics()
        return scalar

    def get_mean_percentiles(self):
        return self.mean_percentiles

    def load_image_metrics(self, directory):
        # mean, min, max, std, bg
        # cam<index>_<metric>
        raise NotImplementedError()

    def save_image_metrics(self):
        logger.debug("CameraNode[%s] save_image_metrics", self)
        if not self.connected():
            raise IOError(
                "save_image_metrics called on not connected node")
        cfg = self.config()
        results = self.image_metrics.result()  # min, max, std, mean
        results['bg'] = self.buffers.bg
        meta = {
            'camera': cfg['index'],
            # 'metric':
            'DateTime': datetime.datetime.now(),
        }
        if hasattr(self.image_metrics, 'scalar'):
            meta['scalar'] = self.image_metrics.scalar
        for metric in results:
            im = results[metric]
            if not isinstance(im, montage.io.Image):
                im = montage.io.Image(im, meta)
            meta['metric'] = metric
            im.meta = meta.copy()
            utils.imwrite(im, cfg, 'metric')

    def set_background(self, im=None):
        logger.debug("CameraNode[%s] set_background: %s", self, id(im))
        if im is None:
            self.buffers.bg[:, :] = 1.
            if hasattr(self.meta, 'scalar'):
                del self.meta['scalar']
            self.clear_image_metrics()
        else:
            self.buffers.bg[:, :] = im

    def clear_image_metrics(self):
        self.image_metrics = montage.ops.measures.running.ImageStats()

    # -- grab --
    def set_controller(self, controller_class):
        logger.debug(
            "CameraNode[%s] set_controller: %s", self, controller_class)
        if not isinstance(self.controller, controller_class):
            if self.controller is not None:
                self.controller.disconnect()
            self.controller = controller_class(self)

    def single(
            self, grab_type='grab', until_done=True, save=False,
            broadcast=False, in_pool=False, free=True):
        if not self.connected():
            raise IOError(
                "single called on not connected node")
        if in_pool is False:
            return self.pool.submit(
                self.single, grab_type=grab_type, until_done=until_done,
                save=save, broadcast=broadcast, in_pool=True)
        logger.debug(
            "CameraNode[%s] single: %s, %s, %s, %s",
            self, grab_type, until_done, save, broadcast)
        if grab_type not in ('grab', 'norm', 'frame'):
            grab_type = 'grab'
        if save:
            until_done = True
        if broadcast:
            until_done = True
        meta = self.meta.copy()
        #if 'grab' not in meta:
        #    meta['grab'] = -1
        self.set_controller(controllers.SingleGrabController)
        if grab_type == 'grab':
            bi = self.controller.get_grab(meta, until_done=until_done)
            im = self.buffers.grabs[bi]
        elif grab_type == 'norm':
            bi = self.controller.get_norm(meta, until_done=until_done)
            im = self.buffers.norms[bi]
        else:
            bi = self.controller.get_frame(meta, until_done=until_done)
            im = self.buffers.frames[bi]
        if im is not None and broadcast:
            self.broadcast(im, stats=True)
        if save:
            cfg = self.config()
            if grab_type == 'grab':
                im = self.buffers.grabs[im[0]]
                if 'grab' not in im.meta:
                    im.meta['grab'] = 9999
            elif grab_type == 'norm':
                im = self.buffers.norms[im[0]]
                if 'grab' not in im.meta:
                    im.meta['grab'] = 9999
            else:
                im = self.buffers.frame
            if 'row' not in im.meta:
                im.meta['row'] = 9999
            if 'col' not in im.meta:
                im.meta['col'] = 9999
            if 'camera' not in im.meta:
                im.meta['camera'] = cfg['index']
            #im.update(self.meta)
            utils.imwrite(im, cfg, grab_type)
        # free buffer
        if grab_type in ('grab', 'norm'):
            ff = lambda i=bi, s=self: s.buffers.unlock_grab(i)
        else:
            ff = lambda i=bi, s=self: s.buffers.unlock_frame(i)
        if free:
            return ff()
        return im, ff

    def ok_to_save(self, directory, n_bytes=None):
        return config.checkers.save_directory_ok(directory, n_bytes)

    def ready_to_grab(self):
        # check if grab buffers are ready
        return self.buffers.is_ready_for_grab()

    def single_grab(self, grab_type='grab', save=False, in_pool=False):
        logger.debug(
            "CameraNode[%s] single_grab: %s, %s",
            self, grab_type, save)
        self.single(
            grab_type=grab_type, until_done=True,
            save=save, broadcast=True, in_pool=in_pool)

    def start_grab(self, meta, until_done=True, in_pool=False):
        if not self.connected():
            raise IOError(
                "start_grab called on not connected node")
        if in_pool is False:
            return self.pool.submit(
                self.start_grab, meta, until_done=until_done, in_pool=True)
        logger.debug("CameraNode[%s] start_grab", self)
        self.set_controller(controllers.GrabController)
        self.controller.run(meta, until_done=until_done)
        if self.controller.nodata_buffer is not None:
            self.controller.veto = True
            self.controller.veto_info['nodata'] = self.controller.nodata_buffer
        logger.debug(
            "CameraNode[%s] start_grab(%s, %s)",
            self, self.controller.veto, self.controller.veto_info)
        return not self.controller.veto, self.controller.veto_info

    def wait_for_save(self, in_pool=False):
        if not isinstance(self.controller, controllers.GrabController):
            raise AttributeError("wait_for_save only valid after start_grab")
        if in_pool is False:
            return self.pool.submit(
                self.wait_for_save, in_pool=True)
        logger.debug("CameraNode[%s] wait_for_save", self)
        self.controller.until(self.controller.done_saving)
        logger.debug("CameraNode[%s] wait_for_save [done]", self)

    def finish_grab(self):
        logger.debug("CameraNode[%s] finish_grab", self)
        if isinstance(self.controller, controllers.GrabController):
            nodata = self.controller.nodatas
            if len(nodata) == 0:
                nodata = None
            self.controller.disconnect()
            self.controller = None
        else:
            nodata = None
        return nodata

    def update_controller(self):  # needs to be run in tight-loop
        #logger.debug("CameraNode[%s] update_controller", self)
        if self.controller is not None:
            self.controller.update()

    def get_buffer_locks(self):
        if self.buffers is None:
            return {}
        return self.buffers.get_locks()
