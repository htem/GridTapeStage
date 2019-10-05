#!/usr/bin/env python
"""
Stats:
    - focus (on grabs, norms or frames)
    - histogram (on grabs, norms or frames)
Intelligently manage crops
May need to know camera masks...
"""

import numpy

import datautils.structures.mp
import montage

from .... import log
from .. import utils


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class StatsSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, grab_buffers, norm_buffers, frame_buffers):
        logger.debug(
            "StatsSerf[%s] setup: %s, %s, %s, %s",
            self, config, grab_buffers, norm_buffers, frame_buffers)
        # accumulate then save (to give the ability to drop bad frames)
        self.config = config
        self.grab_buffers = grab_buffers
        self.norm_buffers = norm_buffers
        self.frame_buffers = frame_buffers
        self.btypes = {}
        self.setup_buffers()
        if 'log_serfs' in config:
            utils.log_serf_to_directory(self, config['log_serfs'])

    def set_config(self, config):
        logger.debug("StatsSerf[%s] set_config: %s", self, config)
        self.config = config

    def setup_buffers(self):
        logger.debug("StatsSerf[%s] setup_buffers", self)
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
        self.btypes = {
            'grab': self.grabs,
            'norm': self.norms,
            'frame': self.frames}

    def compute_stats(self, btype, index, meta):
        logger.debug(
            "StatsSerf[%s] compute_stats: %s, %s", self, btype, index)
        b = self.btypes[btype][index]
        cfg = self.config['stats']
        logger.debug("StatsSerf[%s] crop: %s", self, cfg['crop'])
        c = montage.ops.transform.cropping.crop(b, cfg['crop'])
        stats = {}
        if cfg.get('focus', False):
            m = cfg.get('focus_method', 'gradient_focus')
            # default to gradient focus
            f = getattr(
                montage.ops.measures.focus,
                m,
                montage.ops.measures.focus.gradient_focus)
            stats['focus'] = float(f(c))
            #stats['focus'] = float(
            #    montage.ops.measures.focus.gradient_focus(c))
            #stats['focus'] = float(montage.ops.measures.focus.fft_focus(c))
        if cfg.get('histogram', False):
            # TODO unstretch histogram?
            # TODO set nbins?
            stats['histogram'] = montage.ops.measures.histogram.cvhistogram(
                c, bins=256)
        if cfg.get('std', False):
            stats['std'] = float(numpy.std(c))
        if cfg.get('mean', False):
            stats['mean'] = float(numpy.mean(c))
        if cfg.get('beam', False):
            i = self.config['index']
            if i == 0:
                vs = b.diagonal()
            elif i == 1:
                vs = b[:, ::-1].diagonal()
            elif i == 2:
                vs = b[:, ::-1].diagonal()[::-1]
            else:
                vs = b.diagonal()[::-1]
            t = vs[len(vs)/2:].max() / 2.
            inds = numpy.where(vs > t)[0]
            if len(inds):
                i = int(inds[0])
            else:
                i = -1
            stats['beam'] = {
                'vs': numpy.array(vs),
                't': float(t),
                'i': i,
            }
        # add stats from meta
        if 'row' in meta:
            stats['row'] = meta['row']
        if 'col' in meta:
            stats['col'] = meta['col']
        if 'grab' in meta:
            stats['grab'] = meta['grab']
        if 'loc' in meta:
            stats['loc'] = meta['loc']
        if 'range' in meta:
            stats['range'] = meta['range']
        stats['btype'] = btype
        stats['buffer_index'] = index
        self.send('stats', btype, index, stats)


class StatsLord(datautils.structures.mp.Lord):
    def __init__(self, config, buffers):
        logger.debug("StatsLord[%s] shift: %s, %s", self, config, buffers)
        datautils.structures.mp.Lord.__init__(self)
        self.config = config
        self.buffers = buffers
        self.btypes = {
            'grab': self.buffers.grabs,
            'norm': self.buffers.norms,
            'frame': self.buffers.frames,
        }
        self.lock_by_btype = {
            'grab': self.buffers.lock_grab,
            'norm': self.buffers.lock_grab,
            'frame': self.buffers.lock_frame,
        }

        self.unlock_by_btype = {
            'grab': self.buffers.unlock_grab,
            'norm': self.buffers.unlock_grab,
            'frame': self.buffers.unlock_frame,
        }

    def set_config(self, config):
        logger.debug("StatsLord[%s] set_config: %s", self, config)
        self.config = config
        self.send('set_config', config)

    def start(self, wait=True):
        logger.debug("StatsLord[%s] start", self)
        datautils.structures.mp.Lord.start(
            self, StatsSerf, (
                self.config, self.buffers.grab_buffers,
                self.buffers.norm_buffers, self.buffers.frame_buffers
            ), wait=wait)

    def compute_stats(self, btype, index):
        logger.debug(
            "StatsLord[%s] compute_stats: %s, %s", self, btype, index)
        self.lock_by_btype[btype](index)
        meta = self.btypes[btype][index].meta
        self.send('compute_stats', btype, index, meta)

    def stats(self, btype, index, stats):
        logger.debug(
            "StatsLord[%s] stats: %s, %s", self, btype, index)
        self.unlock_by_btype[btype](index)
