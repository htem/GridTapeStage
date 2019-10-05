#!/usr/bin/env python
"""
Main control node

Does the following:
    - [stateful] find slot
    - [stateful] advance slot
    - manages montager
    - [stateful] montage
    - compute node?
    - scope node?

Find slot:
    1) move to approximate center
    2) setup stats streaming
    3) clear stats, move in direction
    4) wait for new stats
    5) check if off slot:
        no = goto 3
        yes = more directions?
            yes = change direction goto 3
            no = goto 6
    6) move to center, setup roi, stop stats streaming

Advance slot:
    1) read current barcode
    2) make large move
    3) read new barcode
    4) check if valid, check position, if off make small move and goto 3
"""

import copy
import json
import os
import time

import concurrent.futures
import numpy
import pizco

import montage

from .. import base
from ... import config
from ...config.checkers import require
from ... import imaging
from ... import log

from . import fakemontager
from . import notification
from . import slotreader
from . import statemachines


default_config = {
    "addr": 'tcp://127.0.0.1:11060',
    'montager': {
        #"fake": True,
        "addr": 'tcp://127.0.0.1:11000',
    },
    'motion': {
        'addr': 'tcp://127.0.0.1:11010',
    },
    'cameras': [
        {
            'addr': 'tcp://127.0.0.1:11020',
        },
    ],
    'tape': {
        'addr': 'tcp://127.0.0.1:11030',
    },
    'tapecamera': {
        'addr': 'tcp://127.0.0.1:11040',
    },
    'compute': {
        'addr': 'tcp://127.0.0.1:11050',
    },
    'scope': {
        'addr': 'tcp://127.0.0.1:11070',
    },
    'make_safe': {
        #'location': {'x': 0, 'y': 0},
        'widen_16x_clicks': 30,
        'kill_beam_timeout': 3600,  # seconds until filament is killed
        'ht_up_to_kill': 1,  # if scope is at 120kv, +1 will kill the beam
    },
    'origin': {'x': 0, 'y': 750000},
    'move_slot': {
        #'origin': {'x': 0, 'y': 0},
	'piezo_position': {'x': 0, 'y': 0},
        'led_delay': 0.5,  # n seconds to wait for led to turn on
        'max_waits': 100,
        'max_moves': 100,
        'wait_time': 0.1,
        'target': {
            'id': 9999, 'type': 'slot',
            'y': 1100,
            'close_enough': 20,  # in pixels
        },
        'ppmm': 130.0,  # pixels per mm
        'move_ratio': 0.8,  # ratio to move during fine tuning
        'reverse_bump': 1.0,  # mm to add to move on fine tuning reverse
        'slot_spacing': 6.5,
        'maximum_slot_moves': 10,  # maximum number of slots to move
        'meta': {},
    },
    'find_slot': {
        #'center': {
        #    'x': ..., 'y': ...,  # stage position
        #    'time': ....,  # time found
        #},
        #'include_stds': True,  # include camera stds in meta, slow
        'include_data': True,  # include camera stds in meta, slow
        'stat': 'mean',  # stat to examine for edge finding
        'broadcast': True,  # also broadcast images, will slow things down
        'tighten_beam_n_16x_clicks': 27,
        'start': {'x': 0, 'y': 0},
        'move_size': {'x': 16000, 'y': 16000},
        # min/max moves with offset will set the found 'center' offset
        'max_moves': {'x': 80, 'y': 60},
        'min_moves': {'x': 20, 'y': 15},
        # offset from slot edge to center of slot
        'offset': {'x': 1000000, 'y': 750000},
        'delay': 0.001,  # between stat grabs
        #'check_timeout': 0.025,  # between stat checking
        #'threshold': 200,
        'threshold': 20,  # if stat < threshold = edge
        'meta': {},
        'post_widen_delay': 3.0,  # wait N seconds after widening beam
    },
    'align_beam': {
        'include_beam_array': True,  # include raw beam data in meta, slow
        'tighten_beam_n_16x_clicks': 29,  # for alignment
        'tighten_beam_n_1x_clicks': 15,  # also for alignment
        'check_aperture_n_1x_clicks': 8,  # for checking aperature
        'expand_beam_n_1x_clicks': 10,  # for imaging
        'one_axis_adjust': {  # if < this error, only adjust the worst axis
            'x': 40,
            'y': 40,
        },
        'close_enough': {
            'x': 25,
            'y': 20,
        },
        'aperture_close_enough': {
            'x': 150,
            'y': 150,
            'error': True,
        },
        'broadcast': True,  # also broadcast images, will slow things down
        'delay': 0.001,  # between stat grabs
        'settling_time': 0.1,   # time to settle between adjustments
        'aperture_settling_time': 0.3,
        'n_retries': 10,
        'n_adjustments': 50,
        'post_widen_delay': 3.0,  # wait N seconds after widening beam
    },
    'focus_beam': {
        # stop focusing when the max focus is N steps away from the
        # edge of the scanned focus points
        'min_std': 60,  # minimum pixel std to focus
        'n_away_from_edge': 4,
        'n_underfocus': 1,  # number of fine clicks left to underfocus
        'n_adjustments': 50,  # maximum number of focus settings to try
        'broadcast': True,  # also broadcast images, will slow things down
        'delay': 0.001,  # between stat grabs
        'settling_time': 0.1,  # time to settle between adjustments
        'grab_type': 'norm',
        'measure': 'mean',  # camera index or 'mean' or other numpy function
    },
    'slots': {
        'shift_factor': {'x':0,'y':0},# additional fudge factor 
        'scale_factor': {'x':1.0,'y':1.0}, # scale factor x and y
        'source': '~/slots.json',
        'direction': 1,  # imaging direction
    },
    'save': {
        'directory': '/data',
        'next': '/data1',
        'frame': True,
        # 'grab': False,
        # 'norm': False,
        'on_fail': True,
        'log_level': 20,  # 10 = DEBUG, 20 = INFO, 30 = WARNING
    },
    'slot': {  # current slot info, overwritten at start of move_slot
        'barcode': {},
        #'rois': [{}, ],
        #'focus_points': [],
        #'align_points': [],
        'roi_index': 0,
        'center': {},
    },  # current slot
    'slot_bounds': {
        'left': -1200000,
        'right': 1200000,
        'bottom': 950000,
        'top': -950000
    },
    'notification': {
        'to_email': [],
        #'slack_channel': 'channel',
        'enable': True,
        #'slack_token': '',
        #'enable': False,
    },
}


logger = log.get_logger(__name__)


class ControlNode(base.StatefulIONode):
    def __init__(self, cfg=None):
        super(ControlNode, self).__init__(cfg)
        cfg = self.config()
        # proxy child nodes
        logger.info(
            "ControlNode[%s] proxying tapecamera %s", self, cfg['tapecamera'])
        self.tapecamera = base.proxy(cfg['tapecamera'])
        logger.info("ControlNode[%s] proxying tape %s", self, cfg['tape'])
        self.tape = base.proxy(cfg['tape'])
        logger.info("ControlNode[%s] proxying motion %s", self, cfg['motion'])
        self.motion = base.proxy(cfg['motion'])
        logger.info("ControlNode[%s] proxying cameras %s", self,
                    cfg['cameras'])
        # index is necessary for filename formatting
        for i in xrange(len(cfg['cameras'])):
            #cfg['cameras'][i]['index'] = i + 1  # to make this 1 based
            cfg['cameras'][i]['index'] = i  # to make this 0 based
        self.cameras = [base.proxy(c) for c in cfg['cameras']]
        logger.info(
            "ControlNode[%s] proxying montager %s", self, cfg['montager'])
        if cfg['montager'].get('fake', False):
            logger.info(
                "ControlNode[%s] making fake montager", self)
            self.montager = fakemontager.FakeMontager()
        else:
            self.montager = base.proxy(cfg['montager'])
        logger.info(
            "ControlNode[%s] proxying compute %s", self, cfg['compute'])
        self.compute = base.proxy(cfg['compute'])
        logger.info(
            "ControlNode[%s] proxying scope %s", self, cfg['scope'])
        self.scope = base.proxy(cfg['scope'])

        # store current frames
        self.frame_stats = [None for _ in xrange(len(self.cameras))]
        self.frame_stats_callbacks = []
        for (i, c) in enumerate(self.cameras):
            scbf = lambda stats, index=i: self._receive_frame_stats(
                stats, index)
            c.new_stats.connect(scbf)
            self.frame_stats_callbacks.append(scbf)
        self.new_position = pizco.Signal(nargs=1)
        self.position_callback = self.motion.new_position.connect(
            lambda p: self.new_position.emit(p))

        # setup slot source
        self.slot_source = slotreader.SlotSource(cfg['slots']['source'])
        self._kill = False

        # setup all log levels
        if 'save' in cfg and 'log_level' in cfg['save']:
            # change log level of all nodes
            for n in (
                    self.cameras + [
                        self.tape,  self.tapecamera, self.scope,
                        self.montager, self.compute, self]):
                n.set_log_level(cfg['save']['log_level'])

    def _new_state(self, state):
        if isinstance(state, Exception):
            if self.statemachine is None:
                smc = None
            else:
                smc = self.statemachine.__class__.__name__
            logger.error(
                "Encountered error state: %s %s" %
                (smc, state))
            # only call make_safe when statemachines is not MakeSafe to
            # avoid infinite recursion
            if not isinstance(self.statemachine, statemachines.MakeSafeSM):
                self.make_safe()
            try:
                notification.send_notification(
                    self, 'error', error=state,
                    state_machine=smc)
            except Exception as e:
                logger.error("Failed to send notification: %s" % (e, ))
        super(ControlNode, self)._new_state(state)

    def __del__(self):
        # disconnect signals
        for i in xrange(len(self.frame_stats)):
            self.cameras[i].new_stats.disconnect(self.frame_stats_callbacks[i])
        self.motion.new_position.disconnect(self.position_callback)
        super(ControlNode, self).__del__()

    def __repr__(self):
        cfg = self.config()
        return "{}.{} at {} addr {}".format(
            self.__module__, self.__class__, hex(id(self)),
            cfg.get('addr', ''))

    def check_config(self, cfg=None):
        return

    def config_delta(self, delta):
        if 'tape' in delta:
            logger.error(
                "Changing control config tape values is impossible")
        if 'motion' in delta:
            logger.error(
                "Changing control config motion values is impossible")
        if 'cameras' in delta:
            logger.error(
                "Changing control config camera values is impossible")
        if 'slots' in delta and 'source' in delta['slots']:
            self.slot_source.source = delta['slots']['source']
        if 'slot' in delta and 'center' in delta['slot'] and self.connected():
            self.montager.config({'slot_center': delta['slot']['center']})
        if 'save' in delta and 'log_level' in delta['save']:
            # change log level of all nodes
            for n in (
                    self.cameras + [
                        self.tape,  self.tapecamera, self.scope,
                        self.montager, self.compute, self]):
                n.set_log_level(delta['save']['log_level'])

    def connect(self, node_type=None, index=None):
        logger.info("ControlNode[%s] connect", self)
        self.check_config()
        if node_type in (None, 'tape'):
            logger.info("ControlNode[%s] connecting to tape", self)
            self.tape.connect()
        if node_type in (None, 'tapecamera'):
            logger.info("ControlNode[%s] connecting to tapecamera", self)
            self.tapecamera.connect()
        if node_type in (None, 'motion'):
            logger.info("ControlNode[%s] connecting to motion", self)
            self.motion.connect()
        if node_type in (None, 'camera'):
            logger.info("ControlNode[%s] connecting to cameras", self)
            if index is None:
                [c.connect() for c in self.cameras]
            else:
                if (not isinstance(index, int)) or (index < 0) or \
                        (index > len(self.cameras)):
                    raise ValueError(
                        "Invalid camera index {} not in [0, {})".format(
                            index, len(self.cameras)))
                self.cameras[index].connect()
        if node_type in (None, 'montager'):
            logger.info("ControlNode[%s] connecting to montager", self)
            self.montager.connect()
        if node_type in (None, 'compute'):
            logger.info("ControlNode[%s] connecting to compute", self)
            self.compute.connect()
        if node_type in (None, 'scope'):
            logger.info("ControlNode[%s] connecting to scope", self)
            self.scope.connect()

    def disconnect(self, node_type=None, index=None):
        logger.info("ControlNode[%s] disconnect", self)
        #if node_type in (None, 'tape'):
        #    logger.info("ControlNode[%s] disconnecting from tape", self)
        #    self.tape.disconnect()
        #if node_type in (None, 'tapecamera'):
        #    logger.info("ControlNode[%s] disconnecting from tapecamera", self)
        #    self.tapecamera.disconnect()
        #if node_type in (None, 'motion'):
        #    logger.info("ControlNode[%s] disconnecting from motion", self)
        #    self.motion.disconnect()
        #if node_type in (None, 'camera'):
        #    logger.info("ControlNode[%s] disconnecting from cameras", self)
        #    if index is None:
        #        [c.disconnect() for c in self.cameras]
        #    else:
        #        if (not isinstance(index, int)) or (index < 0) or \
        #                (index > len(self.cameras)):
        #            raise ValueError(
        #                "Invalid camera index {} not in [0, {})".format(
        #                    index, len(self.cameras)))
        #        self.cameras[index].disconnect()
        #if node_type in (None, 'montager'):
        #    logger.info("ControlNode[%s] disconnecting from montager", self)
        #    self.montager.disconnect()
        #if node_type in (None, 'compute'):
        #    logger.info("ControlNode[%s] disconnecting from compute", self)
        #    self.compute.disconnect()

    def connected(self, node_type=None, index=None):
        if node_type is None:
            return self.motion.connected() and \
                self.tape.connected() and \
                self.tapecamera.connected() and \
                self.montager.connected() and \
                self.compute.connected() and \
                self.scope.connected() and \
                all(c.connected() for c in self.cameras)
        if node_type == 'motion':
            return self.motion.connected()
        if node_type == 'tape':
            return self.tape.connected()
        if node_type == 'tapecamera':
            return self.tapecamera.connected()
        if node_type == 'camera':
            if index is None:
                return all(c.connected() for c in self.cameras)
            else:
                if (not isinstance(index, int)) or (index < 0) or \
                        (index > len(self.cameras)):
                    raise ValueError(
                        "Invalid camera index {} not in [0, {})".format(
                            index, len(self.cameras)))
                return self.cameras[index].connected()
        if node_type == 'montager':
            return self.montager.connected()
        if node_type == 'compute':
            return self.compute.connected()
        if node_type == 'scope':
            return self.scope.connected()

    def _receive_frame_stats(self, stats, index):
        # too chatty
        #logger.debug(
        #    "ControlNode[%s] _receive_frame_stats: %s, %s",
        #    self, index, id(stats))
        self.frame_stats[index] = stats

    def wait_till_moved(self):
        if not self.connected():
            msg = 'Attempt to wait_till_moved when un-connected'
            logger.error(msg)
            raise IOError(msg)
        return self.motion.wait_till_moved()

    # --------------------- state machines ------------------
    def make_safe(self):
        logger.info("ControlNode[%s] make_safe", self)
        #if not self.connected():
        #    msg = 'Attempt to make_safe when un-connected'
        #    logger.error(msg)
        #    raise IOError(msg)
        return self.attach_state_machine(
            statemachines.MakeSafeSM, 'setup')

    def move_slot(self):
        logger.info("ControlNode[%s] move_slot", self)
        if not self.connected():
            msg = 'Attempt to move_slot when un-connected'
            logger.error(msg)
            raise IOError(msg)
        return self.attach_state_machine(
            statemachines.MoveSlotSM, 'setup')

    def find_slot(self):
        logger.info("ControlNode[%s] find_slot", self)
        if not self.connected():
            msg = 'Attempt to find_slot when un-connected'
            logger.error(msg)
            raise IOError(msg)
        if isinstance(self.montager, fakemontager.FakeMontager):
            f = concurrent.futures.Future()
            f.set_result(None)
            return f
        return self.attach_state_machine(
            statemachines.FindSlotSM, 'setup')

    def align_beam(self):
        logger.info("ControlNode[%s] align_beam", self)
        if not self.connected():
            msg = 'Attept to align_beam when un-connected'
            logger.error(msg)
            raise IOError(msg)
        return self.attach_state_machine(
            statemachines.AlignBeamSM, 'setup')

    def focus_beam(self):
        logger.info("ControlNode[%s] focus_beam", self)
        if not self.connected():
            msg = 'Attept to focus_beam when un-connected'
            logger.error(msg)
            raise IOError(msg)
        return self.attach_state_machine(
            statemachines.FocusBeamSM, 'setup')

    def bake(self):
        logger.info("ControlNode[%s] bake", self)
        if not self.connected():
            msg = 'Attempt to bake when un-connected'
            logger.error(msg)
            raise IOError(msg)
        if isinstance(self.montager, fakemontager.FakeMontager):
            f = concurrent.futures.Future()
            f.set_result(None)
            return f
        # TODO error if no roi
        return self.attach_state_machine(
            statemachines.BakeSM, 'setup')

    def montage(self):
        logger.info("ControlNode[%s] montage", self)
        if not self.connected():
            msg = 'Attempt to montage when un-connected'
            logger.error(msg)
            raise IOError(msg)
        if isinstance(self.montager, fakemontager.FakeMontager):
            f = concurrent.futures.Future()
            f.set_result(None)
            return f
        # TODO error if no roi
        # TODO warn if not baked
        return self.attach_state_machine(
            statemachines.MontageSM, 'setup')

    def get_current_roi(self):
        cfg = self.config()
        rois = cfg.get('slot', {}).get('rois', [])
        if not len(rois):
            return None
        i = cfg.get('slot', {}).get('roi_index', -1)
        if i < 0 or i >= len(rois):
            return None
        roi = rois[i]
        try:
            roi = imaging.montaging.roi.resolve(**roi)
        except imaging.montaging.roi.ROIError as e:
            msg = 'Failed to resolve roi: %s[%s]' % (roi, e)
            logger.error(msg)
            raise e  # TODO error notification?
        return roi

    def _get_point_or_roi_center(self, slot_key):
        """Return None -> focus at current location"""
        cfg = self.config()
        if 'slot' not in cfg or 'roi_index' not in cfg['slot']:
            return None
        i = cfg['slot']['roi_index']
        roi = self.get_current_roi()
        # check that the roi is valid
        if roi is None:
            return None
        # if key is not defined, default to roi center
        if slot_key not in cfg['slot']:
            return roi['center']
        pts = cfg['slot'][slot_key]
        if i < 0 or i > len(pts) or pts[i] is None:
            return roi['center']
        return pts[i]

    def get_current_focus_point(self):
        """Return None -> focus at current location"""
        return self._get_point_or_roi_center('focus_points')

    def get_current_align_point(self):
        """Return None -> align at current location"""
        return self._get_point_or_roi_center('align_points')

    def _set_point_by_position(self, slot_key):
        """Set point to current location"""
        mr = self.motion.poll_position(wait=True)
        cfg = self.config()
        if 'slot' not in cfg or 'roi_index' not in cfg['slot']:
            raise ValueError("config missing slot or roi_index")
        # get current roi index -> i
        i = cfg['slot']['roi_index']
        if 'rois' not in cfg['slot']:
            raise ValueError("config.slots missing rois")
        nrois = len(cfg['slot']['rois'])
        if i < 0 or i > nrois:
            raise ValueError("Invalid roi_index %s [n rois = %s]" % (i, nrois))
        if slot_key not in cfg['slot']:
            pts = [None for _ in xrange(nrois)]
        else:
            pts = cfg['slot'][slot_key]
            if len(pts) != nrois:
                raise ValueError(
                    "Invalid number of points [%s] != n rois [%s]"
                    % (len(pts), nrois))
        pts[i] = [mr['x'], mr['y']]
        self.config({'slot': {slot_key: pts}})

    def set_focus_point(self):
        """Set focus point to current location"""
        self._set_point_by_position('focus_points')

    def set_align_point(self):
        """Set align point to current location"""
        self._set_point_by_position('align_points')

    def get_montager_roi(self):
        mcfg = self.montager.config()
        if 'montage' not in mcfg or 'roi' not in mcfg['montage']:
            raise ValueError("Montager node doesn't have an roi")
        roi = mcfg['montage']['roi']
        # un-offset by center
        cfg = self.config()
        #if (
        #        'slot' not in cfg or 'center' not in cfg['slot']
        #        or 'x' not in cfg['slot']['center']
        #        or 'y' not in cfg['slot']['center']):
        #    raise ValueError("slot config missing or missing center")
        #rroi = imaging.montaging.roi.unoffset(roi, cfg['slot']['center'])
        imaging.montaging.roi.check_against_bounds(
            roi, cfg['slot_bounds'])
        self.config({'slot': {
            'rois': [roi, ],
            'roi_index': 0,
            'align_points': [None, ],
            'focus_points': [None, ],
        }})

    def load_rois(self):
        # TODO warn if slot and id not defined
        cfg = self.config()
        # TODO error?
        if 'slot' not in cfg:
            return
	if 'slots' not in cfg:
            return
        scfg = cfg['slot']
        # TODO error out if no id
        if 'id' not in scfg:
            return
        sinfo = self.slot_source.get_slot_info(scfg['id'])
        roi_index = 0
        rois = []
        focus_points = []
        align_points = []
        slot_bounds = cfg['slot_bounds']
        if sinfo is not None and 'center' in scfg:
            # offset rois by slot center
            center = scfg['center']
            for i in xrange(len(sinfo['rois'])):
                r = copy.deepcopy(sinfo['rois'][i])
                if 'slots' in cfg:
                    if 'shift_factor' in cfg['slots']:
                        logger.info("SHIFT AMOUNT: %s"%cfg['slots']['shift_factor'])
                        r = imaging.montaging.roi.offset(r,cfg['slots']['shift_factor'])
                    if 'scale_factor' in cfg['slots']:
                        logger.info("SCALE AMOUNT: %s"%cfg['slots']['scale_factor'])
		        r = imaging.montaging.roi.scale(r,cfg['slots']['scale_factor'])
                imaging.montaging.roi.check_against_bounds(
                    r, slot_bounds)
                rois.append(imaging.montaging.roi.offset(r, center))
                if (
                        'focus_points' in sinfo and
                        i < len(sinfo['focus_points']) and
                        sinfo['focus_points'][i] is not None):
                    f = copy.deepcopy(sinfo['focus_points'][i])
                    if len(f) != 2:
                        raise ValueError("Focus point len[%s] != 2" % len(f))
                    if (
                            f[0] < slot_bounds['left'] or
                            f[0] > slot_bounds['right'] or
                            f[1] < slot_bounds['top'] or
                            f[1] > slot_bounds['right']):
                        raise ValueError(
                            "Focus point[%s] out of bounds: %s" % (i, f))
                    f[0] += center['x']
                    f[1] += center['y']
                else:
                    f = None
                focus_points.append(f)
                if (
                        'align_points' in sinfo and
                        i < len(sinfo['align_points']) and
                        sinfo['align_points'][i] is not None):
                    a = copy.deepcopy(sinfo['align_points'][i])
                    if len(a) != 2:
                        raise ValueError("Align point len[%s] != 2" % len(a))
                    if (
                            a[0] < slot_bounds['left'] or
                            a[0] > slot_bounds['right'] or
                            a[1] < slot_bounds['top'] or
                            a[1] > slot_bounds['right']):
                        raise ValueError(
                            "Align point[%s] out of bounds: %s" % (i, a))
                    a[0] += center['x']
                    a[1] += center['y']
                else:
                    a = None
                align_points.append(a)
            #for r in copy.deepcopy(sinfo['rois']):
            #    # check roi extents against slot bounds
            #    imaging.montaging.roi.check_against_bounds(
            #        r, cfg['slot_bounds'])
            #    rois.append(imaging.montaging.roi.offset(r, center))
        # TODO warn on no rois?
        self.config({
            'slot': {
                'rois': rois,
                'align_points': align_points,
                'focus_points': focus_points,
                'roi_index': roi_index}})

    def set_slot_id(self, sid=None):
        if sid is None:
            # first slot
            direction = self.config()['slots']['direction']
            sid = self.slot_source.get_first_id(direction)
        sid = int(sid)
        logger.info("ControlNode[%s] set_slot_id: %s", self, sid)
        self.config({'move_slot': {'target': {'id': sid}}})

    def next_slot_id(self):
        cfg = self.config()
        slot_id = cfg['slot']['id']
        direction = cfg['slots']['direction']
        return self.slot_source.get_next_id(slot_id, direction)

    def _next_roi(self):
        cfg = self.config()['slot']
        if cfg['roi_index'] < len(cfg['rois']) - 1:
            self.config({'slot': {'roi_index': cfg['roi_index'] + 1}})
            return True
        return False

    def _next_slot(self, sid=None):
        if sid is None:
            sid = self.next_slot_id()
        if sid is None:
            return False
        self.set_slot_id(sid)
        return True

    def image_slots(self, in_loop=False, chain=None, future=None):
        """Main run function to image all slots"""
        if not self.connected():
            msg = 'Attempt to image_slots when un-connected'
            logger.error(msg)
            raise IOError(msg)
        if not in_loop:
            self._kill = False  # reset kill signal
            future = concurrent.futures.Future()
            self.loop.add_callback(self.image_slots, True, None, future)
            return future
        if chain is None:
            chain = [
                self.move_slot, self.find_slot,
                self.align_beam, self.bake,
                self.focus_beam, self.montage]

        # kill signal
        if self._kill:
            future.set_result('killed')
            # make safe here?
            return

        if not len(chain):
            # check for more rois
            if self._next_roi():
                chain = [
                    self.align_beam, self.bake,
                    self.focus_beam, self.montage]
            else:
                # check for more slots
                if self._next_slot():
                    return self.image_slots(True, None, future)
                else:
                    future.set_result('done')
                    self.make_safe()
                    return

        # wait for it to finish
        f = chain.pop(0)()

        def run_next(f):
            if f.exception() is not None:
                future.set_exception(f.exception())
                return
            self.image_slots(True, chain, future)

        self.loop.add_future(f, run_next)

    def stop(self, in_loop=False):
        """stop when current state machine running in image_slots is done"""
        #if not self.connected():
        #    msg = 'Attempt to stop when un-connected'
        #    logger.error(msg)
        #    raise IOError(msg)

        self._kill = True

    def kill(self):
        """stop current state machine (after current state finishes)"""
        #if not self.connected():
        #    msg = 'Attempt to kill when un-connected'
        #    logger.error(msg)
        #    raise IOError(msg)

        # set kill to break chain
        self._kill = True  # where to reset this?

        # special state handling
        s = self.get_state()
        if s is not None:
            (sm, state) = s
            # if baking or montaging kill
            if sm in ('MontageSM', 'BakeSM'):
                self.montager.kill()
        self.set_state(None)


def test_node(config):
    n = ControlNode(config)
    n.connect()
    n.disconnect()

if __name__ == '__main__':
    test_node(default_config)
