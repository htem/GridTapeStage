#!/usr/bin/env python
"""
TODO

monitoring:
    beam shift (shadows) {camera stats}
    image focus {camera stats}
    beam cut-out {camera stats}
    histograms {camera stats}
per-montage histogram:
    by watching camera stats
mini-readouts:
    vetos {meta}
    n_regrabs {meta}
    std {meta/stats}
    focus {meta/stats}
    shift {meta}
    beam (x, y) {stats}
"""

import os
from cStringIO import StringIO

import cv2
import numpy
from PIL import Image
import pizco
import slackclient
import time

import montage

from . import base
from .. import log
from .. import imaging


default_config = {
    'addr': 'tcp://127.0.0.1:11050',
    'cameras': [
        {
            'addr': 'tcp://127.0.0.1:11020',
        },
    ],
    'montager': {
        'addr': 'tcp://127.0.0.1:11000',

    },
    'coarse_montage': {
        'downsample': 8,
        'broadcast': {
            'downsample': 8,
            #'slack_channel': 'channel',
            'enable': True,
            #'slack_token': '',
        },
        'ntiles': 0,
        'size': 0,
        'session_name': None,
    },
    'save': {
        'directory': '/data/1',  # gets set from montager.new_session
    },
    'stats_delay': 2,  # only report every N stats
}

logger = log.get_logger(__name__)


class CoarseMontager():
    def __init__(self, cfg):
        self.ntiles = cfg['coarse_montage']['n_tiles']
        self.size = cfg['coarse_montage']['size']
        self.session_name = cfg['coarse_montage']['name']
        # self.session_start = cfg['start']
        self.save_fn = os.path.join(
            os.path.abspath(os.path.expanduser(cfg['save']['directory'])),
            self.session_name + '_coarse_montage.tif')
        self.ds = cfg['coarse_montage']['downsample']
        self.dsf = 1. / self.ds
        logger.debug("CoarseMontager setup to save to %s" % (self.save_fn, ))
        self.shape = None
        self.coarse_montage = None
        self.cfg = cfg

    def add_image(self, im, add=True):
        #im = im[::self.ds, ::self.ds]
        meta = im.meta
        im = cv2.resize(im, None, fx=self.dsf, fy=self.dsf)
        if self.coarse_montage is None:
            self.coarse_montage = numpy.empty(
                (im.shape[0]*self.size[0], im.shape[1]*self.size[1]))
            self.shape = im.shape
        row, col = int(meta['row']) - 1, int(meta['col']) - 1
        if row < 0 or col < 0:
            return row, col
        pts = self.to_points(row, col)
        self.coarse_montage[pts[0]:pts[0] + self.shape[0],
                            pts[1]:pts[1] + self.shape[1]] = im
        return row, col

    def to_points(self, r, c):
        row = r * self.shape[0]
        col = c * self.shape[1]
        return (row, col)

    def finish_montage(self):
        im, meta = self.save_im()
        return (im, meta)

    def save_im(self):
        if self.coarse_montage is None:
            return
        # convert to u1, save
        min_value, max_value, _, _ = cv2.minMaxLoc(self.coarse_montage)
        mask_arr = numpy.zeros_like(self.coarse_montage[self.coarse_montage>0])
        cv2.normalize(
            self.coarse_montage[self.coarse_montage>0], mask_arr, 0, 255, cv2.NORM_MINMAX)
        self.coarse_montage[self.coarse_montage>0] = mask_arr
        meta = {
            'ntiles': self.ntiles,
            'size': self.size,
            'name': self.session_name,
            'ds': self.ds,
            'range': (min_value, max_value),
        }
        imaging.tifio.raw.write_tif(
            self.save_fn, self.coarse_montage.astype('u1'), **meta)
        return self.coarse_montage.astype('u1'), meta


class ComputeNode(base.StatefulIONode):
    def __init__(self, cfg=None):
        super(ComputeNode, self).__init__(cfg)
        cfg = self.config()
        logger.info("ComputeNode[%s] proxying cameras %s",
                    self, cfg['cameras'])
        for i in xrange(len(cfg['cameras'])):
            cfg['cameras'][i]['index'] = i
        self.cameras = [base.proxy(c) for c in cfg['cameras']]
        self.frame_callbacks = []
        self.stats_callbacks = []
        self.frames = [None for _ in xrange(len(self.cameras))]
        self.stats = None
        # Setup callbacks
        for (i, c) in enumerate(self.cameras):
            callback = lambda im, index=i: self._receive_frame(im, index)
            stats_callback = lambda stats, index=i: \
                self._receive_stats(stats, index)
            c.new_image.connect(callback)
            c.new_stats.connect(stats_callback)
            self.frame_callbacks.append(callback)
            self.stats_callbacks.append(stats_callback)
        logger.info("ComputeNode[%s] proxying montager %s",
                    self, cfg['montager'])
        self.montager_node = base.proxy(cfg['montager'])
        self.montager_node.new_session.connect(lambda d: self.new_session(d))
        self.montager_node.new_tile.connect(lambda t: self._receive_tile(t))
        self.coarse_montager = None
        self.new_image = pizco.Signal(nargs=1)
        self.new_stats = pizco.Signal(nargs=1)
        self.new_tile = pizco.Signal(nargs=1)
        self.new_coarse_montage = pizco.Signal(nargs=1)
        self.mean_percentiles = None

    def connect(self, index=None):
        logger.info("ComputeNode[%s] connect", self)
        if index is None:
            [c.connect() for c in self.cameras]
        else:
            if (not isinstance(index, int)) or (0 > index > len(self.cameras)):
                raise ValueError("Invalid camera index {} not in "
                                 "[0, {}])".format(index, len(self.cameras)))
            self.cameras[index].connect()

    def __del__(self):
        # disconnect signals
        for i in xrange(len(self.frame_callbacks)):
            self.cameras[i].new_image.disconnect(self.frame_callbacks[i])
            self.cameras[i].new_stats.disconnect(self.stats_callbacks[i])

    def config_changed(self, delta):
        pass

    def disconnect(self, index=None):
        # Nothing Here
        pass

    def connected(self, node_type=None, index=None):
        if node_type is None:
            return self.montager_node.connected() and \
                all(c.connected() for c in self.cameras)
        if node_type == 'camera':
            if index is None:
                return all(c.connected() for c in self.cameras)
            else:
                if (
                        (not isinstance(index, int)) or (index < 0) or
                        (index > len(self.cameras))):
                    raise ValueError("Invalid camera index {} not in "
                                     "[0, {}]".format(index,
                                                      len(self.cameras)))
                return self.cameras[index].connected()

    def start_streaming(self, grab_type=None):
        if not self.connected():
            raise IOError("start_streaming called on not-connected node")
        [c.start_streaming(grab_type) for c in self.cameras]

    def stop_streaming(self):
        if not self.connected():
            raise IOError("stop_streaming called on not-connected node")
        [c.stop_streaming() for c in self.cameras]

    def broadcast_coarse_montage(self, im, meta):
        bcfg = self.config().get('coarse_montage', {}).get('broadcast', {})
        if not bcfg.get('enable', False):
            return
        ds = bcfg.get('downsample', 8)
        dsf = 1. / ds
        dim = cv2.resize(im, None, fx=dsf, fy=dsf)
        meta['downsample'] = meta.get('downsample', 1) * ds
        dim = montage.io.Image(dim, meta)
        self.new_coarse_montage.emit(dim)
        if 'slack_channel' in bcfg and 'slack_token' in bcfg:
            # post to slack
            try:
                c = slackclient.SlackClient(bcfg['slack_token'])
                pil_im = Image.fromarray(dim.astype('u1'))
                io = StringIO()
                pil_im.save(io, format='png')
                io.seek(0)
                fn = '%s.png' % meta['name']
                c.api_call(
                    'files.upload', channels=bcfg['slack_channel'],
                    filename=fn, file=io, initial_comment=meta['name'])
            except Exception as e:
                logger.warning("Failed to post to slack: %s", e)

    def new_session(self, session_cfg):
        # TODO start listening to stats here, ignore otherwise?
        if session_cfg is None:
            im, meta = self.coarse_montager.finish_montage()
            self.broadcast_coarse_montage(im, meta)
            self.coarse_montager = None
            self.stop_emitting_stats()
            self.mean_percentiles = None
        else:
            # compute average mean percentiles
            ps = [c.get_mean_percentiles() for c in self.cameras]
            if any([p is None for p in ps]):
                self.mean_percentiles = None
            else:
                self.mean_percentiles = numpy.array(ps).mean(axis=0)
            self.config({
                'coarse_montage': session_cfg,
                'save': {'directory': session_cfg['directory']}})
            self.start_emitting_stats()
            cfg = self.config()
            self.coarse_montager = CoarseMontager(cfg)

    def _receive_tile(self, tile):
        # for now just re-broadcast tile
        self.new_tile.emit(tile)

    def _receive_frame(self, image, index):
        logger.debug("ComputeNode[%s] _receive_frame: %s, %s", self,
                     index, id(image))
        self.frames[index] = image
        # Check for empty frames
        for f in self.frames:
            if f is None:
                return
        # If none, broadcast frames and reset
        self._broadcast_images(self.frames)
        self.frames = [None] * len(self.frames)

    def start_emitting_stats(self):
        self.stats = {}

    def stop_emitting_stats(self):
        self.stats = None

    def _receive_stats(self, stats, index):
        if self.stats is None:
            return
        cfg = self.config()
        if index not in self.stats:
            self.stats[index] = [stats, ]
        else:
            self.stats[index].append(stats)
        logger.debug(
            "ComputeNode[%s] _receive_stats: %s, %s, %s",
            self, index, len(self.stats),
            [len(self.stats[i]) for i in self.stats])
        if (
                len(self.stats) == len(cfg['cameras']) and
                all(
                    len(self.stats[i]) >= cfg['stats_delay']
                    for i in self.stats)):
            self.emit_stats()

    def emit_stats(self):
        logger.debug("EMITTING STATS")
        focus = 0.0
        count = 0.0
        std = 0.0
        for s in self.stats:
            for stats in self.stats[s]:
                focus += stats['focus']
                std += stats['std']
                count += 1
        avg_focus = float(focus) / float(count)
        avg_std = float(std) / float(count)
        ts = time.time()
        self.new_stats.emit((ts, avg_focus, avg_std))
        self.stats = {}

    def _broadcast_images(self, ims):
        s = ims[0].shape
        for i in ims[1:]:
            if i.shape != s:
                logger.error(
                    "ComputeNode[%s] images must be all the same size "
                    "to broadcast: %s", (self, [i.shape for i in ims]))
                return
        meta = ims[0].meta
        for (i, im) in enumerate(ims):
            if hasattr(im, 'meta') and 'range' in im.meta:
                fmin, fmax = im.meta['range']
                ims[i] = (im / 65535.) * (fmax - fmin) + fmin
        if len(ims) > 1:
            im = numpy.vstack((
                numpy.hstack((ims[0], ims[1])),
                numpy.hstack((ims[2], ims[3]))))
        else:
            im = ims[0]
        im = montage.io.Image(im, meta)
        if self.coarse_montager is None:
            row, col = -1, -1
        else:
            row, col = self.coarse_montager.add_image(im)
        logger.debug("ComputeNode[%s] _broadcast_images done", self)
        if self.mean_percentiles is not None:
            l, h = self.mean_percentiles
            im = (im.clip(l, h) - l) / (h - l) * 255.
        else:
            #minv, maxv, _, _ = cv2.minMaxLoc(im)
            cv2.normalize(im, im, 0, 255, cv2.NORM_MINMAX)
        #_, b = cv2.imencode('.png', im.astype('u1'))
        #e = b.tostring().encode('base64')
        pil_im = Image.fromarray(im.astype('u1'))
        io = StringIO()
        pil_im.save(io, format='jpeg')
        io.seek(0)
        e = io.read().encode('base64')
        # TODO where to find veto info?
        self.new_image.emit((e, row, col))
        logger.debug("ComputeNode[%s] images emitted", self)
