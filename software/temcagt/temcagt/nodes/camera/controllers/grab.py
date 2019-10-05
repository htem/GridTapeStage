#!/usr/bin/env python
"""
releasing buffers:
    grabs/norms:
        if frame building:
            release after frame is built
        if saving grabs/norms:
            release after save
        if saving grabs/norms & frame building:
            release after save and frame is built
    frames:
        if saving:
            release after save
        if broadcasting (and not saving):
            release after broadcast

state starts off in 'wait'
goes to 'clear'
run -> 'grab' (might go into 'regrab')
    ['success', 'fail']
"""

import logging
import time

from .... import log
from .base import NodeController


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class GrabController(NodeController):
    def __init__(self, node):
        logger.debug("GrabController[%s] __init__: %s", self, node)
        self.nodatas = []
        self.nodata_buffer = None
        NodeController.__init__(self, node)
        cfg = self.node.config()
        self.nframes = cfg['nframes']
        self.contrast_threshold = cfg['contrast']['min']
        self.shift_d_threshold = cfg['shift']['max_shift']
        self.shift_m_threshold = cfg['shift']['min_match']
        self.max_regrabs = cfg['nregrabs']
        # load save, broadcast info, etc... from cfg
        # only build frame if needed for save or broadcast
        # only support frame broadcasting
        self.compute_stats = cfg['stats'].get('enable', False)
        bc = cfg['broadcast']['enable']
        self.broadcast = {
            'grab': bc and cfg['broadcast'].get('grab', False),
            'norm': bc and cfg['broadcast'].get('norm', False),
            'frame': bc and cfg['broadcast'].get('frame', False),
        }
        self.save = {
            'grab': cfg['save'].get('grab', False),
            'norm': cfg['save'].get('norm', False),
            'frame': cfg['save'].get('frame', False),
        }
        self.frame_on_fail = cfg['save']['on_fail']
        self.meta = {}
        self.state = 'wait'
        self.clear()

    def clear(self):
        self.state = 'clear'
        self.nodata_buffer = None
        self.veto = False
        self.veto_info = {}
        self.low_contrasts = {}
        self.indices = []
        self.shifts = {}
        self.nregrabs = 0
        self.ngrabs = 0
        self.node.analysis.clear_template()

    def connect(self):
        logger.debug("GrabController[%s] connect", self)
        NodeController.connect(self)
        self.callbacks['camera'] = [
            self.node.camera.attach('grab', self.on_grab),
            self.node.camera.attach('nodata', self.on_nodata)]
        self.callbacks['norm'] = [
            self.node.norm.attach('norm', self.on_norm), ]
        self.callbacks['analysis'] = [
            # check for vetos
            self.node.analysis.attach('contrast', self.on_contrast),
            self.node.analysis.attach('shift', self.on_shift), ]
        self.callbacks['frame'] = [
            self.node.frame.attach('frame', self.on_frame), ]
        self.callbacks['stats'] = [
            self.node.stats.attach('stats', self.on_stats), ]

    def disconnect(self):
        logger.debug("GrabController[%s] disconnect", self)
        # finish updating things
        if self.node is not None:
            self.update()
            if not self.is_done_saving():
                self.until(self.is_done_saving)
        NodeController.disconnect(self)

    def on_nodata(self, buffer_index):
        logger.debug("GrabController[%s] on_nodata: %s", self, buffer_index)
        self.nodata_buffer = buffer_index
        self.nodatas.append(buffer_index)

    def on_grab(self, meta):
        logger.debug("GrabController[%s] on_grab: %s", self, meta)
        index = meta['buffer_index']
        self.indices.append(index)
        meta['grab'] = self.ngrabs
        self.ngrabs += 1
        self.node.buffers.grabs[index].meta = meta
        if self.broadcast['grab']:
            self.node.broadcast(self.node.buffers.grabs[index])
        if self.save['grab']:
            self.node.saver.save_grab(index)
        self.node.norm.normalize_grab(index)
        #if self.nregrabs == self.max_regrabs:
        #    self.node.camera.flush()

    def on_norm(self, index):
        logger.debug("GrabController[%s] on_norm: %s", self, index)
        self.node.analysis.analyze_grab(index)
        meta = self.node.buffers.grabs[index].meta
        if self.broadcast['norm']:
            self.node.broadcast(self.node.buffers.norms[index])
        if self.save['norm']:
            self.node.saver.save_norm(index)
        self.node.buffers.norms[index].meta = meta

    def on_contrast(self, index, result):
        logger.debug(
            "GrabController[%s] on_contrast: %s, %s", self, index, result)
        self.node.buffers.norms[index].meta['contrast'] = result
        self.low_contrasts[index] = result < self.contrast_threshold

    def on_shift(self, index, result):
        logger.debug(
            "GrabController[%s] on_shift: %s, %s", self, index, result)
        self.node.buffers.norms[index].meta['shift'] = result
        self.shifts[index] = result
        if (
                result['d'] > self.shift_d_threshold or
                result['m'] < self.shift_m_threshold):
            self.veto = True
            self.veto_info.update({'shift': result})
        if len(self.shifts) == (self.nframes - 1):
            if all(self.low_contrasts.values()):
                self.veto = False
                self.veto_info.update({'contrast': 'all low contrast'})
                for bi in self.shifts:
                    self.shifts[bi]['x'] = 0.
                    self.shifts[bi]['y'] = 0.
                    self.node.buffers.norms[bi].meta['shift'] = self.shifts[bi]
            if not self.veto:
                self.success()
            elif self.nregrabs == self.max_regrabs:
                self.fail()
            else:
                self.regrab()

    def success(self):
        logger.debug("GrabController[%s] success", self)
        # build frame?
        if (self.save['frame'] or self.broadcast['frame']):
            shifts = [self.shifts[i] for i in self.indices[1:]]
            self.node.frame.build_frame(shifts, self.indices)
        else:
            # dont' build a frame, release all grabs
            for bi in self.low_contrasts:
                self.node.buffers.unlock_grab(bi)
        # report success (so montager can move)
        self.state = 'success'
        # flush last frame from camera
        if self.nregrabs != self.max_regrabs:
            self.node.camera.flush()
        logger.debug("GrabController[%s] end_success", self)

    def fail(self):
        # build frame?
        logger.debug("GrabController[%s] fail", self)
        if (
                (self.save['frame'] or self.broadcast['frame'])
                and self.frame_on_fail):
            shifts = [self.shifts[i] for i in self.indices[1:]]
            self.node.frame.build_frame(shifts, self.indices)
        else:
            # dont' build a frame, release all grabs
            for bi in self.low_contrasts:
                self.node.buffers.unlock_grab(bi)
        # report fail (so montager can move)
        self.state = 'fail'
        # flush last frame from camera
        #self.node.camera.flush()

    def regrab(self):
        # report regrab (so montager will wait)
        self.state = 'regrab'
        # reset veto
        self.veto = False
        # drop a frame (and results)
        di = self.indices.pop(0)
        del self.low_contrasts[di]
        # release grab buffer
        self.node.buffers.unlock_grab(di)
        # record the regrab
        self.nregrabs += 1
        self.veto_info['regrabs'] = self.nregrabs
        # trigger a regrab
        self.node.camera.regrab(
            self.meta, trigger_next=self.nregrabs != self.max_regrabs)
        # clear the shift template, set to first norm
        self.shifts = {}
        self.node.analysis.set_template(self.indices[0])
        # queue up remaining buffers to shift
        for i in self.indices[1:]:
            self.node.analysis.check_shift(i)

    def on_frame(self, index, meta):
        logger.debug(
            "GrabController[%s] on_frame: %s, %s", self, index, meta)
        #index = meta['buffer_index']
        #self.node.buffers.frames[index].meta.update(meta)
        for bi in meta['buffer_indices']:
            self.node.buffers.unlock_grab(bi)
        if self.nodata_buffer is not None:
            meta['nodata'] = self.nodata_buffer
        if self.broadcast['frame']:
            #logger.debug(
            #    "GrabController[%s] starting broadcast", self)
            self.node.broadcast(self.node.buffers.frames[index])
            #logger.debug(
            #    "GrabController[%s] broadcast done", self)
        if self.save['frame']:
            self.node.saver.save_frame(index)
        if self.compute_stats:
            self.node.stats.compute_stats('frame', index)
        self.node.buffers.unlock_frame(index)

    def on_stats(self, btype, index, stats):
        logger.debug(
            "GrabController[%s] on_stats: %s, %s", self, btype, index)
        self.node.broadcast_stats(stats)

    def is_done_grabbing(self):
        return self.state in ('success', 'fail', 'wait', 'clear')

    def is_running(self):
        return self.state in ('grab', 'regrab')

    def is_done_saving(self):
        return self.is_done_grabbing() and self.node.buffers.is_empty()

    def run(self, meta, until_done=True):
        logger.debug("GrabController[%s] run", self)
        if self.is_running():
            logger.debug(
                "GrabController[%s] run is_running, updating: %s",
                self, self.state)
            self.until(self.is_done_grabbing)
        self.clear()
        self.state = 'grab'
        self.meta = meta
        self.node.camera.start_grab(meta)
        if until_done:
            f = lambda s=self: s.is_done_grabbing()
            self.until(f)

    def update(self, timeout=0.000001):
        self.node.camera.update(timeout=timeout)
        self.node.norm.update(timeout=timeout)
        self.node.analysis.update(timeout=timeout)
        self.node.frame.update(timeout=timeout)
        self.node.saver.update(timeout=timeout)
        self.node.stats.update(timeout=timeout)
