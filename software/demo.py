#!/usr/bin/env python
"""
Get/Set tape move speed: set_speed (also automatic with step_tape)
Advance/Retract tape position: step_tape
StopTape (abort current movement): stop_all, halt_all (also releases)
IsTapeMoving: get_status['MOT_STATUS']
IsConnected: get_status...
"""

import ctypes
import logging
import sys
import time

import serial

import pycomando
import smaract


port = '/dev/ttyACM0'
if len(sys.argv) > 1:
    port = sys.argv[1]
baud = 115200
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

spmm = 400.
tension_target = 8401600

FR = 0b00
FP = 0b01
PR = 0b10
PP = 0b11

COLLECT = 0
DISPENSE = 1
TENSION = 2
UNTENSION = 3

ST_OPTS_RUN_REELS = 0x01
ST_OPTS_WAIT = 0x02

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
        'args': (ctypes.c_byte, ),
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
        'args': (ctypes.c_byte, ),
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

l = smaract.find_systems()[0]
m = smaract.MCS(l)

c = pycomando.Comando(serial.Serial(port, baud))
echo = pycomando.protocols.EchoProtocol(c)
cmd = pycomando.protocols.CommandProtocol(c)

c.register_protocol(0, echo)
c.register_protocol(1, cmd)

mgr = pycomando.protocols.command.EventManager(cmd, commands)


def throw_error(code):
    raise Exception(code)

mgr.on('error', throw_error)


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


def is_moving(drive=None):
    if drive is None:
        return any((is_moving(d) for d in (FP, PP)))
    s = parse_status(mgr.blocking_trigger('get_status', drive)[0])
    return s['BUSY'] or s['MOT_STATUS'] != 'stopped'


def wait(drive=None):
    while is_moving(drive):
        pass
    #if drive is None:
    #    return [wait(d) for d in (FP, PP)]
    #s = parse_status(mgr.blocking_trigger('get_status', drive)[0])
    #if s['BUSY'] or s['MOT_STATUS'] != 'stopped':
    #    return wait(drive)
    #return


def read_tension(i=1):
    return mgr.blocking_trigger('read_tension', i)[0].value


def run_reels(s=6):
    mgr.trigger('run_reels', s)


def step(fsteps, time=None, psteps=None, opts=ST_OPTS_WAIT):
    if fsteps > 0:
        direction = DISPENSE
    else:
        fsteps = -fsteps
        direction = COLLECT
    if psteps is None:
        psteps = fsteps
    if time is None:
        time = fsteps / 128.
    if opts & ST_OPTS_WAIT:
        return mgr.blocking_trigger(
            'step_tape', direction, fsteps, psteps, time, opts)
    else:
        mgr.trigger('step_tape', direction, fsteps, psteps, time, opts)
    if opts & ST_OPTS_WAIT:
        wait()


def move(mm, time=None, opts=ST_OPTS_WAIT):
    return step(int(mm * spmm), time=time, opts=opts)


def dispense(drive, steps):
    mgr.trigger('move_drive', drive, DISPENSE, steps)
    wait(drive)


def collect(drive, steps):
    mgr.trigger('move_drive', drive, COLLECT, steps)
    wait(drive)


def release_all():
    mgr.trigger('release_all')


def hold_pinch_drives():
    print("Holding pinch drives")
    mgr.trigger('hold_drive', PP)
    mgr.trigger('hold_drive', FP)


def adjust_to_tension(
        slop=10000, step_size=[100, 50], high_threshold=None, drive=FP,
        adir=None):
    if high_threshold is None:
        high_threshold = float('inf')
    t = read_tension(10)
    dt = t - tension_target
    print("Tension: %s[%s], %s" % (t, dt, step_size))
    if abs(dt) > high_threshold:
        raise Exception("Tension too high: %s" % (t, ))
    if drive == FP:
        reduce_tension, increase_tension = dispense, collect
    elif drive == PP:
        reduce_tension, increase_tension = collect, dispense
    else:
        raise Exception("Invalid drive: %s" % drive)
    nsteps = step_size[0]
    if dt > slop and adir != 1:
        # reduce tension
        reduce_tension(drive, nsteps)
        # repeat?
        print("Reducing tension")
        return adjust_to_tension(
            slop, step_size, high_threshold, drive, 0)
    elif dt < -slop and adir != 0:
        # increase tension
        increase_tension(drive, nsteps)
        # repeat?
        print("Increasing tension")
        return adjust_to_tension(
            slop, step_size, high_threshold, drive, 1)
    if len(step_size) > 1:
        return adjust_to_tension(
            slop, step_size[1:], high_threshold, drive)


def adjust_back_tension(slop=10000, step_size=[50], adjusted=False):
    t = read_tension(10)
    dt = t - tension_target
    print("Tension: %s[%s], %s" % (t, dt, step_size))
    if dt > slop:
        # tension too high
        # no way to decrease from back
        # so release the front
        print("Dispensing front...")
        dispense(FP, step_size[0])
        return adjust_back_tension(slop, step_size, adjusted)
    elif dt < -slop:  # tension too small
        adjusted = True
        print("Dispensing back...")
        dispense(PP, step_size[0])
        return adjust_back_tension(slop, step_size, adjusted)
    elif not adjusted:
        dispense(FP, step_size[0])
        return adjust_back_tension(slop, step_size, adjusted)
    if len(step_size) > 1:
        return adjust_back_tension(slop, step_size[1:])


def adjust():
    hold_pinch_drives()
    adjust_back_tension()
    adjust_to_tension()


def untension(nsteps=3200):
    dispense(FP, nsteps)
    collect(PP, nsteps)


def tension(nsteps=3000):
    collect(FP, nsteps)
    dispense(PP, nsteps)


def stop():
    mgr.trigger('stop_all')


def jump(nmm=120000):
    t0 = time.time()
    m.move_relative(1, nmm)
    while m.status(1) != 0:
        pass
    m.move_relative(1, -nmm)
    while m.status(1) != 0:
        pass
    t1 = time.time()
    return t1 - t0


def time_move(mm=12000, axis=1):
    t0 = time.time()
    m.move_relative(axis, mm)
    while m.status(axis) != 0:
        pass
    t1 = time.time()
    return t1 - t0
