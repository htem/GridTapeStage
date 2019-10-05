#!/usr/bin/env python
"""
Tape movement procedure:
    - tension tape
    - start reel moving
    - adjust to tension
    - move tape
    - fine tune movement (adjust tension only when out of range?)
    - adjust to tension
    - stop reels
    - untension

What about back tension?

I think I should pull out the camera to a different node, this will mean:
    - pro: no double IO connect/disconnect (arduino + camera)
    - pro: simpler nodes
    - con: more complex control node

Tape control node
    - load/unload tape (independent control of reels, pinch drives, etc...)
    - move tape (coordinated movement of tape [most likely in vacuum])
    - monitor tension (checking for errors or overtension during movement)
    - tension/untension (prepare for movement)
    - report slot number (book-keeping requires camera as barcode reader)
    - set current slot # and direction (are slot #s going up or down?)

Log everything in case of errors, especially tension!!
    - tension
    - position (in linear mm)
    - all movements
    - slot (#)
    - slot spacing

Types of movement
    - tension/untension reel (feed or pickup)
    - feed/pickup pinch drive (feed or pickup)
    - advance N mm (combined feed & pickup, pinch & reel)
    - advance 1 slot (shortcut to advance N mm)

Failure modes (L6470 has stall detection, try this)
    - jam: look for overtension or skipepd steps)
    - broken tape look for undertension
    - slip clutch failure: look for skipped steps
    - pinch drive skipped step: look for skipped steps
    TODO maybe rotary encoders are called for...

Config:
    - port for arduino (for all movement and sensors
    - port for camera (usb address, serial #, etc?)
    - acceptable tension
    - slot # (will be overridden during movements)
    - slot direction
    - reel movement parameters [which of these should be in firmware?]
        - speed
        - accel/decel
        - microstepping
        - k
"""

import ctypes
import json
import os
import time

import serial

import pizco
import pycomando

from . import base
from .. import config
from ..config.checkers import require
from .. import log


default_config = {
    'addr': 'tcp://127.0.0.1:11030',
    #'loc': '/dev/ttyACM0',
    'loc': 'fake',
    #'fakebarcodes': {
    #    'filename': '~/.temcagt/fake/barcodes.json',
    #    'ppmm': 130.0,
    #    'initial': [{'width': 650, 'center': 1055, 'value': 100}, ],
    #    'spacing': 780,
    #    'top': 655,
    #    'bottom': 1455,
    #    'barcode_side': 'right',  # should match tapecamera
    #},
    'baud': 115200,
    'tension_steps': 1600,
    'steps_per_mm': 2075 / 6.,
    'mms_per_second': 0.25,
    'tension_target': 8495000,
    'untensioned_threshold': 8469000,  # untensioned if tension < this
    # untensioned is 8461749, 8461765
    'tension_range': 20000,
    'tension_step_size': 100,
    'tension_tries': 50,
    'reel_speed': 6.,
}

commands = {
    0: {
        'name': 'error',
        'result': (ctypes.c_byte, ),
    },
    1: {
        'name': 'ping',
        'args': (ctypes.c_byte, ),
        'result': (ctypes.c_byte, ),
    },
    5: {
        'name': 'read_tension',
        'args': (ctypes.c_byte, ),  # TODO optional
        'result': (ctypes.c_int32, ),
    },
    6: {
        'name': 'set_led',
        'args': (ctypes.c_byte, ),
    },
    10: {
        'name': 'reset_drives',
    },
    11: {
        'name': 'get_busy',
        'args': (ctypes.c_byte, ),  # TODO optional
        'result': (ctypes.c_byte, ),
    },
    12: {
        'name': 'get_status',
        'args': (ctypes.c_byte, ),
        'result': (ctypes.c_int16, ),
    },
    13: {
        'name': 'get_position',
        'args': (ctypes.c_byte, ),
        'result': (ctypes.c_int32, ),
    },
    14: {
        'name': 'set_position',
        'args': (ctypes.c_byte, ctypes.c_int32),
    },
    15: {
        'name': 'hold_drive',
        'args': (ctypes.c_byte, ),
    },
    16: {
        'name': 'release_drive',
        'args': (ctypes.c_byte, ),
    },
    17: {
        'name': 'rotate_drive',
        'args': (ctypes.c_byte, ctypes.c_byte, ctypes.c_float),
    },
    18: {
        'name': 'set_speed',
        'args': (ctypes.c_byte, ctypes.c_float),
    },
    19: {
        'name': 'get_speed',
        'args': (ctypes.c_byte, ),
        'result': (ctypes.c_float, ),
    },
    20: {
        'name': 'move_drive',
        'args': (ctypes.c_byte, ctypes.c_byte, ctypes.c_uint32),
    },
    21: {
        'name': 'run_reels',
        'args': (ctypes.c_float, ),
    },
    22: {
        'name': 'stop_reels',
    },
    23: {
        'name': 'stop_all',
    },
    24: {
        'name': 'release_all',
    },
    25: {
        'name': 'halt_all',
    },
    30: {
        'name': 'step_tape',
        'args': (
            ctypes.c_byte, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float,
            ctypes.c_byte),
        'result': (ctypes.c_int32, ),
    },
    31: {
        'name': 'set_tension_limits',
        'args': (ctypes.c_int32, ctypes.c_int32),
    },
    32: {
        'name': 'get_tension_limits',
        'result': (ctypes.c_int32, ctypes.c_int32),
    },
}


logger = log.get_logger(__name__)

FEED_REEL = 0b00
FEED_PINCH = 0b01
PICKUP_REEL = 0b10
PICKUP_PINCH = 0b11
drives = [FEED_REEL, FEED_PINCH, PICKUP_REEL, PICKUP_PINCH]

COLLECT = 0
DISPENSE = 1
TENSION = 2
UNTENSION = 3

ST_OPTS_RUN_REELS = 0x01
ST_OPTS_WAIT = 0x02
ST_OPTS_WATCH = 0x04


def parse_motor_status(s):
    if (s & 0x0020):  # B 0x0020
        if (s & 0x0040):  # A 0x0040
            return 'constant speed'
        else:
            return 'accelerating'
    else:
        if (s & 0x0040):  # A 0x0040
            return 'deccelerating'
        else:
            return 'stopped'


status_bits = {
    'HIZ': lambda s: bool(s & 0x0001),
    'BUSY': lambda s: bool(~s & 0x0002),
    'SW_F': lambda s: 'closed' if (s & 0x0004) else 'open',
    'SW_EVN': lambda s: bool(s & 0x0008),
    'DIR': lambda s: 'forward' if (s & 0x0010) else 'reverse',
    'MOT_STATUS': parse_motor_status,
    'NOTPERF_CMD': lambda s: bool(s & 0x0080),
    'WRONG_CMD': lambda s: bool(s & 0x0100),
    'UVLO': lambda s: bool(~s & 0x0200),
    'TH_WRN': lambda s: bool(~s & 0x0400),
    'TH_SD': lambda s: bool(~s & 0x0800),
    'OCD': lambda s: bool(~s & 0x1000),
    'STEP_LOSS_A': lambda s: bool(~s & 0x2000),
    'STEP_LOSS_B': lambda s: bool(~s & 0x4000),
    'SCK_MOD': lambda s: bool(s & 0x8000),
}


def parse_status(status):
    """
    bit name            active
    15: SCK_MOD         1
    14: STEP_LOSS_B     0
    13: STEP_LOSS_A     0
    12: OCD             0
    11: TH_SD           0
    10: TH_WRN          0
    09: UVLO            0
    08: WRONG_CMD       1
    07: NOTPERF_CMD     1
    06: MOT_STATUS_A    X
    05: MOT_STATUS_B    X
    04: DIR             X
    03: SW_EVN          1
    02: SW_F            X
    01: BUSY            0
    00: HIZ             1

    MOT_STATUS:
        AB
        00  stopped
        01  accelerating
        10  decelerating
        11  constant speed

    DIR: 0 = reverse, 1 = forward

    SW_F: 0 = open, 1 = closed
    """
    if isinstance(status, ctypes.c_int16):
        status = int(status.value)
    s = {}
    for n in status_bits:
        t = status_bits[n]
        s[n] = t(status)
    return s


class TapeNodeException(Exception):
    pass


class FakeManager(object):
    def __init__(self, commands, tension_target, tension_range):
        self.commands = commands
        self._tension = tension_target
        #self._tension = 8461749  # 8461765
        htr = tension_range / 2.
        self._tension_limits = [self._tension - htr, self._tension + htr]

    def on(self, name, func):
        pass

    def trigger(self, name, *args):
        # set_tension_limits
        if name == 'set_tension_limits':
            self._tension_limits = [args[0], args[1]]
        # set_position
        # step_tape

    def blocking_trigger(self, cmd, *args):
        return {
            'step_tape': [ctypes.c_int(self._tension), ],
            'get_tension_limits': [
                ctypes.c_int(v) for v in self._tension_limits],
            'read_tension': [ctypes.c_int(self._tension), ],
            'get_status': [ctypes.c_int(0), ],
            'get_position': [ctypes.c_int(0), ],
            'get_speed': [ctypes.c_int(0), ],
        }.get(cmd, None)


class TapeNode(base.IONode):
    def __init__(self, cfg=None):
        base.IONode.__init__(self, cfg)
        cfg = self.config()
        #
        #logger.info("TapeNode[%s] proxying motion %s", self, cfg['motion'])
        self.cmd = None
        self._state = None
        self._barcodes = []
        self.new_state = pizco.Signal(nargs=1)

    def __del__(self):
        # disconnect signals
        base.IONode.__del__(self)

    def __repr__(self):
        cfg = self.config()
        return "{}.{} at {} addr {}".format(
            self.__module__, self.__class__, hex(id(self)),
            cfg.get('addr', ''))

    def check_config(self, cfg=None):
        if cfg is None:
            cfg = self.config()
        [require(cfg, k) for k in
            [
                'loc', 'baud', 'tension_target', 'tension_range',
                'tension_steps', 'steps_per_mm', 'mms_per_second',
                'tension_step_size',
            ]]
        # TODO finish checking config

    def config_delta(self, delta):
        logger.info("TapeNode[%s] config_delta %s", self, delta)
        if 'tension_target' in delta or 'tension_range' in delta:
            self._set_tension_limits()

    def connect(self):
        if self.cmd is not None:
            return
        self.check_config()
        cfg = self.config()
        logger.info(
            "TapeNode[%s] creating serial %s, %s",
            self, cfg['loc'], cfg['baud'])
        # add options for fake tape node
        if cfg['loc'] == 'fake':
            # make fake cmd and fake mgr
            self.cmd = 'fake'
            self.mgr = FakeManager(
                commands, cfg['tension_target'], cfg['tension_range'])
            self._barcodes = cfg.get(
                'fakebarcodes', {}).get('initial', [])
            # save initial barcodes
            self._save_barcodes()
        else:
            self.serial = serial.Serial(cfg['loc'], cfg['baud'])
            self.comando = pycomando.Comando(self.serial)
            self.cmd = pycomando.protocols.CommandProtocol(self.comando)
            self.comando.register_protocol(1, self.cmd)
            self.mgr = pycomando.protocols.command.EventManager(
                self.cmd, commands)
            time.sleep(4)  # wait for the arduino to start
        self.mgr.on('error', self._error)
        self._set_tension_limits()
        #self.guess_state()
        logger.info("TapeNode[%s] connected to %s", self, cfg['loc'])

    def disconnect(self):
        if self.cmd is None:
            return
        if hasattr(self, 'serial'):
            self.serial.close()
            del self.serial
        for a in ('mgr', 'cmd', 'comando'):
            if hasattr(self, a):
                delattr(self, a)
        self.cmd = None
        logger.info("TapeNode[%s] disconnected", self)

    def connected(self):
        if self.cmd is None:
            return False
        return True

    def _error(self, code):
        logger.info("TapeNode[%s] error[%s]", self, code)
        raise TapeNodeException(code)

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, new_state):
        if new_state == self._state:
            return
        self._state = new_state
        self.new_state.emit(self._state)

    def get_state(self):
        return self.state

    def set_state(self, new_state):
        self.state = new_state

    def guess_state(self):
        # only guess if state is None
        if self.state is not None:
            return self.state
        t = self.read_tension(10)
        cfg = self.config()
        if t < cfg['untensioned_threshold']:
            self.state = 'untensioned'
        else:
            self.state = 'tensioned'

    # -- low level --
    def trigger(self, cmd, *args):
        logger.debug("TapeNode[%s] trigger: %s, %s", self, cmd, args)
        if not self.connected():
            raise TapeNodeException(
                "Failed trigger %s, not connected" % cmd)
        self.mgr.trigger(cmd, *args)

    def blocking_trigger(self, cmd, *args):
        logger.debug("TapeNode[%s] blocking_trigger: %s, %s", self, cmd, args)
        if not self.connected():
            raise TapeNodeException(
                "Failed blocking_trigger %s, not connected" % cmd)
        return self.mgr.blocking_trigger(cmd, *args)

    # ---- tape ----
    def read_tension(self, n_samples=1):
        return self.blocking_trigger('read_tension', n_samples)[0].value

    def _set_tension_limits(self):
        cfg = self.config()
        tt = cfg['tension_target']
        tr = cfg['tension_range']
        # hide this behind cfg?
        self.trigger('set_tension_limits', int(tt - tr/2.), int(tt + tr/2.))

    def _get_tension_limits(self):
        # hide this behind cfg?
        low, high = self.blocking_trigger('get_tension_limits')
        return int(low.value), int(high.value)

    def set_led(self, value):
        self.trigger('set_led', value)

    def get_status(self, drive=None):
        if drive is None:
            return {d: self.get_status(d) for d in drives}
        return parse_status(
            self.blocking_trigger('get_status', drive)[0].value)

    def moving(self, drive=None):
        status = self.get_status()
        for m in status:
            if status[m]['MOT_STATUS'] != 'stopped':
                return True
        return False

    def get_position(self, drive):
        return int(self.blocking_trigger('get_position', drive)[0].value)

    def set_position(self, drive, position):
        self.trigger('set_position', drive, position)

    def hold(self, drive=None):
        if drive is None:
            self.trigger('stop_all')
        else:
            self.trigger('hold', drive)

    def halt(self):
        self.trigger('halt_all')

    def release(self, drive=None):
        if drive is None:
            self.trigger('release_all')
        else:
            self.trigger('release', drive)

    def rotate(self, drive, direction, speed):
        self.trigger('rotate_drive', drive, direction, speed)

    def speed(self, drive, value=None):
        if value is None:
            return self.blocking_trigger('get_speed', drive)
        self.trigger('set_speed', drive, value)

    def move_drive(self, drive, direction, steps):
        self.trigger('move_drive', drive, direction, steps)

    def run_reels(self, speed=None):
        if speed is None:
            speed = self.config()['reel_speed']
        self.trigger('run_reels', speed)

    def stop_reels(self):
        self.trigger('stop_reels')

    def step_tape(self, direction, feed_steps, pickup_steps, duration, opts):
        if opts & ST_OPTS_WAIT:
            return self.blocking_trigger(
                'step_tape', direction, feed_steps, pickup_steps, duration,
                opts)
        else:
            self.trigger(
                'step_tape', direction, feed_steps, pickup_steps, duration,
                opts)

    # -- high level --
    def wait_till_done_moving(self, timeout=None):
        logger.info("TapeNode[%s] wait_till_done_moving", self)
        t0 = time.time()
        while self.moving():
            if timeout is not None and time.time() - t0 > timeout:
                return False
        return True

    def tension_tape(self, opts=None):
        logger.info("TapeNode[%s] tension_tape: %s", self, opts)
        if self.state == 'tensioned':
            raise TapeNodeException("Cannot tension, tensioned tape")
        # TODO check tension, make sure this won't over-tension the tape
        cfg = self.config()
        tsteps = cfg['tension_steps']
        tmm = tsteps / cfg['steps_per_mm']
        t = abs(tmm) / float(cfg['mms_per_second'])
        if opts is None:
            #opts = ST_OPTS_RUN_REELS | ST_OPTS_WAIT
            opts = ST_OPTS_WAIT
        self.step_tape(TENSION, tsteps, tsteps, t, opts)
        self.state = 'tensioned'

    def untension_tape(self, opts=None):
        logger.info("TapeNode[%s] untension_tape: %s", self, opts)
        if self.state == 'untensioned':
            raise TapeNodeException("Cannot untension, untensioned tape")
        cfg = self.config()
        tsteps = cfg['tension_steps']
        tmm = tsteps / cfg['steps_per_mm']
        t = abs(tmm) / float(cfg['mms_per_second'])
        if opts is None:
            #opts = ST_OPTS_RUN_REELS | ST_OPTS_WAIT
            opts = ST_OPTS_WAIT
        self.step_tape(UNTENSION, tsteps, tsteps, t, opts)
        self.state = 'untensioned'

    def _shift_barcodes(self, mm):
        if len(self._barcodes) == [] or mm == 0.:
            return
        cfg = self.config().get('fakebarcodes', None)
        if cfg is None:
            return
        delta_pixels = int(mm * cfg['ppmm'])
        if delta_pixels == 0:
            return

        # shift existing barcodes
        max_center = self._barcodes[0]
        min_center = self._barcodes[0]
        for b in self._barcodes:
            b['center'] += delta_pixels
            if b['center'] > max_center['center']:
                max_center = b
            if b['center'] < min_center['center']:
                min_center = b
        if cfg['barcode_side'] == 'right':
            delta = 1
        elif cfg['barcode_side'] == 'left':
            delta = -1
        else:
            raise ValueError(
                "Invalid barcode side %s [not left/right" %
                cfg['barcode_side'])
        while max_center['center'] + cfg['spacing'] < cfg['bottom']:
            nbc = max_center.copy()
            nbc['value'] += delta
            #nbc['value'] -= 1
            nbc['center'] += cfg['spacing']
            self._barcodes.append(nbc)
            max_center = nbc
        while min_center['center'] - cfg['spacing'] > cfg['top']:
            nbc = min_center.copy()
            nbc['value'] -= delta
            #nbc['value'] += 1
            nbc['center'] -= cfg['spacing']
            self._barcodes.append(nbc)
            min_center = nbc

        # remove any out-of-bounds barcodes
        to_remove = []
        for (i, b) in enumerate(self._barcodes):
            if b['center'] < cfg['top'] or b['center'] > cfg['bottom']:
                to_remove.append(i)
        for i in to_remove[::-1]:
            self._barcodes.pop(i)

        self._save_barcodes()

    def _save_barcodes(self):
        cfg = self.config().get('fakebarcodes', None)
        if cfg is None:
            return
        # save barcodes
        fn = os.path.abspath(os.path.expanduser(cfg['filename']))
        d = os.path.dirname(fn)
        if not os.path.exists(d):
            os.makedirs(d)
        with open(fn, 'w') as f:
            json.dump(self._barcodes, f)

    def move_tape(self, mm, auto_tension=True, opts=None):
        logger.info(
            "TapeNode[%s] move_tape: %s, %s, %s", self, mm, auto_tension, opts)
        if opts is None:
            #opts = ST_OPTS_RUN_REELS | ST_OPTS_WAIT
            opts = ST_OPTS_WAIT
        if auto_tension:
            self.adjust_to_tension(opts=opts)
        cfg = self.config()
        if 'fakebarcodes' in cfg:
            # update fake barcodes accordingly
            self._shift_barcodes(mm)
        steps = cfg['steps_per_mm'] * abs(mm)
        f = int(steps)
        p = int(steps)
        t = abs(mm) / float(cfg['mms_per_second'])
        if mm > 0:
            logger.debug(
                "TapeNode[%s] move_tape: dispense: %s, %s, %s",
                self, f, t, opts)
            return self.step_tape(DISPENSE, f, p, t, opts)
        elif mm < 0:
            logger.debug(
                "TapeNode[%s] move_tape: collect: %s, %s, %s",
                self, f, t, opts)
            return self.step_tape(COLLECT, f, p, t, opts)

    def adjust_to_tension(self, step_size=None, tries=None, opts=None):
        logger.info(
            "TapeNode[%s] adjust_to_tension: %s, %s", self, step_size, tries)
        cfg = self.config()
        if tries is None:
            tries = cfg.get('tension_tries', 10)
        if tries < 1:
            raise TapeNodeException(
                "Failed to reach tension: %s [%s]" % (
                    self.config()['tension_target'],
                    self.read_tension(10)))
        if opts is None:
            opts = ST_OPTS_WAIT
        # read tension, check if near target, adjust until close
        t = self.read_tension(10)
        logger.debug(
            "TapeNode[%s] adjust_to_tension: tension: %s", self, t)
        if step_size is None:
            step_size = cfg.get('tension_step_size', 10)
        step_mm = step_size / cfg['steps_per_mm']
        step_time = max(step_mm / float(cfg['mms_per_second']), 0.25)
        dt = t - cfg['tension_target']
        if dt > 0:  # tension is too high, reduce
            logger.debug(
                "TapeNode[%s] adjust_to_tension: untension tape: %s, %s",
                self, step_size, step_time)
            #self.step_tape(
            #    UNTENSION, step_size, 0, step_time,
            #    opts)
            self.move_drive(FEED_PINCH, DISPENSE, step_size)
            #self.adjust_to_tension(step_size, tries-1)
        else:
            logger.debug(
                "TapeNode[%s] adjust_to_tension: tension tape: %s, %s",
                self, step_size, step_time)
            # increase
            self.move_drive(FEED_PINCH, COLLECT, step_size)
            #self.step_tape(
            #    TENSION, step_size, 0, step_time,
            #    opts)
            #self.adjust_to_tension(step_size, tries-1)
        if opts | ST_OPTS_WAIT:
            self.wait_till_done_moving()
        t = self.read_tension(10)
        ndt = t - cfg['tension_target']
        if (dt > 0 and ndt < 0) or (dt < 0 and ndt > 0) or ndt == 0:
            if self.state is None:  # TODO always set to tensioned?
                self.state = 'tensioned'
            return None
        else:
            # recurse
            self.adjust_to_tension(step_size, tries-1, opts=opts)
