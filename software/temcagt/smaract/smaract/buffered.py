#!/usr/bin/env python
"""
Buffered async interface to an MCS controller.

Buffering commands significantly improves speed by
packing multiple commands into one USB packet.

This should also fix bugs in AMCS (erroneous parsing of double polls)
by counting packets.

To simplify things, start with minimal commands

Handle packets in a better way
Any command that 'expects' a packet should register it's interest
with the packet handler. The handler can then keep track of the order
of requested packets so it can correctly deal with situations like:
    move & ask for a packet [0]
    move & ask for a packet [1]
    receive moved packet [0]
    receive moved packet [1]


many commands return a 'report packet' COMPLETED_PACKET_TYPE
step_move
scan_move_abs
scan_move_rel
goto_pos_abs
goto_pos_rel
calibrate_sensor
find_ref
gripper & angle stuff

overwriting these commands (e.g. sending a 2nd move before the 1st is done)
will cause only 1 completed packet to return, so we should only
ever be listening for 1 of these packets


BMCS has a list of default 'channels': [0, 1]
functions can provide a channel index and optionally arguments as lists
    move([0, 1], [32000, 16000]) # moves 0 to 32000, 1 to 16000
    position([1, 2])  # gets position of channels 1 and 2
this way, external functions don't have to worry about buffering
and also won't have to know about packet states. Effectively, this
is turning the async mode into sync. I think this is OK as the currently
used motion functions are:
    physical known
    position
    moving
    calibrate
    find_ref
    move_absolute
    move_relative
    max_frequency
    scale
the only function I might want as async is position so maybe break this out
into sub-functions like:
    poll_position (async, doesn't return)
    last_position (get's position from state, perhaps wait's till valid)

so async sets are simple
async gets require waiting for the required packets to return
"""

import time

from . import async
from . import oo
from . import raw


class PacketHandler(object):
    """
    Keep track of packet requests
    {
        <pid>: {
            <cid>: {
                'count': 0,
                'state': ...
            }
        }
    }
    """
    def __init__(self):
        self.packets = {}

    def digest(self, packet):
        # check if packet is valid
        if packet.packetType == async.SA_NO_PACKET_TYPE:
            return
        if packet.packetType == async.SA_INVALID_PACKET_TYPE:
            raise raw.SmaractError("Smaract Invalid Packet")
        if packet.packetType == async.SA_ERROR_PACKET_TYPE:
            cid, ecode = async.get_packet_data(packet)
            # reset moving state
            if ecode == 142:  # END_STOP_REACHED
                if async.SA_COMPLETED_PACKET_TYPE in self.packets:
                    s = self.packets[async.SA_COMPLETED_PACKET_TYPE]
                    if cid in s:
                        s[cid]['count'] -= 1
                raise async.EndStopError(
                    "Smaract channel %s reached endstop" % (cid,))
            raise raw.SmaractError(
                "Smaract PacketError: %s[%s:%s]" % (
                    cid, ecode, raw.error_codes.get(ecode, "")))
        if packet.packetType not in self.packets:
            d = async.get_packet_data(packet)
            raise raw.SmaractError(
                "Received packet for non-requested packet: %s[%s]" % (
                    packet.packetType, d))
        # all else was requested or completed packet
        s = self.packets[packet.packetType]
        # unpack packet data
        d = async.get_packet_data(packet)
        cid = d[0]
        # reduce requested count by 1
        s[cid]['count'] -= 1
        if s[cid]['count'] < 0:
            raise raw.SmaractError(
                "Smaract buffer tracking error cid count[%s] < 0" %
                (cid, packet))
        if len(d) == 1:
            s[cid]['state'] = True
        elif len(d) == 2:
            s[cid]['state'] = d[1]
        else:
            s[cid]['state'] = d[1:]

    def request(self, pid, cid):
        if pid not in self.packets:
            self.packets[pid] = {}
        if cid not in self.packets[pid]:
            self.packets[pid][cid] = {'count': 0}
        self.packets[pid][cid]['count'] += 1

    def state(self, pid, cid):
        return self.packets.get(pid, {}).get(cid, {}).get('state', None)

    def count(self, pid, cid=None):
        if cid is None:
            cs = self.packets.get(pid, {})
            return sum([cs[c].get('count', 0) for c in cs])
        return self.packets.get(pid, {}).get(cid, {}).get('count', 0)


def bset(f):
    def wrapped(self, *args, **kwargs):
        # extract flush kwarg
        flush = kwargs.pop('flush', self._autoflush)
        # call decorated function
        f(self, *args, **kwargs)
        # flush
        if flush:
            self.flush()
    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__
    return wrapped


def bget(pid):
    def wrapper(f):
        def wrapped(self, cid, *args, **kwargs):
            # call decorated function (polls value)
            f(self, cid, *args, **kwargs)
            self.flush()  # the command must be flushed
            # wait for response packet
            self._wait_for_all_packets(pid, cid)
            # return most recent state
            return self.handler.state(pid, cid)
        wrapped.__name__ = f.__name__
        wrapped.__doc__ = f.__doc__
        return wrapped
    return wrapper


def get_state(pid):
    def wrapper(f):
        def wrapped(self, cid):
            self._wait_for_all_packets(pid, cid)
            return self.handler.state(pid, cid)
        wrapped.__name__ = f.__name__
        wrapped.__doc__ = f.__doc__
        return wrapped
    return wrapper


# TODO base (and fake) classes need lots of update, AMCS can be removed
class BMCS(oo.MCS):
    def __init__(
            self, loc=None, options=None,
            channels=3, buffered=True, autoflush=True):
        self._autoflush = autoflush
        self._buffered = False
        if isinstance(channels, (list, tuple)):
            self._channels = channels
        else:
            self._channels = range(channels)
        super(BMCS, self).__init__(loc, options)
        self.buffered_output(buffered)
        #self._states = {}
        self.handler = PacketHandler()

    def connect(self, loc=None, options='async'):
        if loc is None:
            loc = self._loc
        if not self.connected:
            self.system_index = raw.open_system(loc, options)
            # make sure all channels report movement completion
            for i in self._channels:
                self._set_report_completed(i, True)

    #def disconnect(self):
    #    pass

    def buffered_output(self, enable):
        async.set_buffered_output(self.system_index, enable)
        self.flush()
        self._buffered = enable

    def update(self):
        # handle any incoming packets
        packet = async.receive_next_packet(self.system_index)
        #self.flush()
        # update all packet states
        self.handler.digest(packet)
        while packet.packetType != async.SA_NO_PACKET_TYPE:
            packet = async.receive_next_packet(self.system_index)
            #self.flush()
            self.handler.digest(packet)

    def _wait_for_all_packets(self, pid, cid=None):
        while self.handler.count(pid, cid) != 0:
            self.update()

    def flush(self):
        if self._buffered:
            async.flush_output(self.system_index)

    # -------------- movement -------------
    @bset
    def calibrate(self, channel_index):
        if self.moving(channel_index):
            raise raw.SmaractError("Attempt to calibrate when moving")
        async.calibrate_sensor(self.system_index, channel_index)
        self.handler.request(async.SA_COMPLETED_PACKET_TYPE, channel_index)

    @bset
    def find_ref(self, channel_index, direction=0, hold_time=0, auto_zero=1):
        if self.moving(channel_index):
            raise raw.SmaractError("Attempt to find_ref when moving")
        async.find_reference_mark(
            self.system_index, channel_index, direction, hold_time, auto_zero)
        self.handler.request(async.SA_COMPLETED_PACKET_TYPE, channel_index)

    @bset
    def move_absolute(self, channel_index, position, hold_time=0):
        if self.moving(channel_index):
            raise raw.SmaractError("Attempt to move_absolute when moving")
        async.go_to_position_absolute(
            self.system_index, channel_index, position, hold_time)
        self.handler.request(async.SA_COMPLETED_PACKET_TYPE, channel_index)

    @bset
    def move_relative(self, channel_index, diff, hold_time=0):
        if self.moving(channel_index):
            raise raw.SmaractError("Attempt to move_relative when moving")
        async.go_to_position_relative(
            self.system_index, channel_index, diff, hold_time)
        self.handler.request(async.SA_COMPLETED_PACKET_TYPE, channel_index)

    @bset
    def move_open_loop(
            self, channel_index, steps, amplitude=4092, frequency=1000):
        if self.moving(channel_index):
            raise raw.SmaractError("Attempt to move_open_loop when moving")
        async.step_move(
            self.system_index, channel_index, steps, amplitude,
            frequency)
        self.handler.request(async.SA_COMPLETED_PACKET_TYPE)

    @bset
    def stop(self, channel_index=None):
        if channel_index is None:
            [async.stop(self.system_index, i) for i in self._channels]
        else:
            async.stop(self.system_index, channel_index)

    def moving(self, channel_index=None, update=True):
        if channel_index is None:
            return any(self.moving(i, update) for i in self._channels)
        if update:
            self.update()
        return (
            self.handler.count(
                async.SA_COMPLETED_PACKET_TYPE, channel_index)
            != 0)

    def wait(self, channel_index=None, timeout=10):
        # wait till done moving
        t0 = time.time()
        while self.moving(channel_index, update=True):
            if time.time() - t0 > timeout:
                raise raw.SmaractError(
                    "wait exceeded timeout: %s" % timeout)

    # -------------- configuration -------------
    @bset
    def _set_report_completed(self, channel_index, enable=True):
        async.set_report_on_complete(self.system_index, channel_index, enable)

    @bset
    def set_max_frequency(self, channel_index, frequency):
        async.set_closed_loop_max_frequency(
            self.system_index, channel_index, frequency)

    @bset
    def set_step_while_scan(self, channel_index, enable):
        async.set_step_while_scan(self.system_index, channel_index, enable)

    @bset
    def poll_physical_known(self, channel_index):
        async.get_physical_position_known(self.system_index, channel_index)
        self.handler.request(
            async.SA_PHYSICAL_POSITION_KNOWN_PACKET_TYPE, channel_index)

    @get_state(async.SA_PHYSICAL_POSITION_KNOWN_PACKET_TYPE)
    def last_physical_known(self, channel_index):
        return

    @bget(async.SA_PHYSICAL_POSITION_KNOWN_PACKET_TYPE)
    def get_physical_known(self, channel_index):
        self.poll_physical_known(channel_index)

    @bset
    def poll_position(self, channel_index):
        async.get_position(self.system_index, channel_index)
        self.handler.request(
            async.SA_POSITION_PACKET_TYPE, channel_index)

    @get_state(async.SA_POSITION_PACKET_TYPE)
    def last_position(self, channel_index):
        return

    @bget(async.SA_POSITION_PACKET_TYPE)
    def get_position(self, channel_index):
        self.poll_position(channel_index)

    @bset
    def poll_status(self, channel_index):
        async.get_status(self.system_index, channel_index)
        self.handler.request(
            async.SA_STATUS_PACKET_TYPE, channel_index)

    @get_state(async.SA_STATUS_PACKET_TYPE)
    def last_status(self, channel_index):
        return

    @bget(async.SA_STATUS_PACKET_TYPE)
    def get_status(self, channel_index):
        self.poll_status(channel_index)

    @bset
    def poll_voltage(self, channel_index):
        async.get_voltage_level(self.system_index, channel_index)
        self.handler.request(
            async.SA_VOLTAGE_LEVEL_PACKET_TYPE, channel_index)

    @get_state(async.SA_VOLTAGE_LEVEL_PACKET_TYPE)
    def last_voltage(self, channel_index):
        return

    @bget(async.SA_VOLTAGE_LEVEL_PACKET_TYPE)
    def get_voltage(self, channel_index):
        self.poll_voltage(channel_index)

    @bset
    def set_position_limit(self, channel_index, limit):
        """limit should be (min, max)"""
        assert len(limit) == 2
        async.set_position_limit(self.system_index, channel_index, *limit)

    @bset
    def poll_position_limit(self, channel_index):
        async.get_position_limit(self.system_index, channel_index)
        self.handler.request(
            async.SA_POSITION_LIMIT_PACKET_TYPE, channel_index)

    @get_state(async.SA_POSITION_LIMIT_PACKET_TYPE)
    def last_position_limit(self, channel_index):
        return

    @bget(async.SA_POSITION_LIMIT_PACKET_TYPE)
    def get_position_limit(self, channel_index):
        self.poll_position_limit(channel_index)

    @bset
    def set_scale(self, channel_index, scale):
        """scale should be (offset, inverted?)"""
        assert len(scale) == 2
        async.set_scale(self.system_index, channel_index, *scale)

    @bset
    def poll_scale(self, channel_index):
        async.get_scale(self.system_index, channel_index)
        self.handler.request(
            async.SA_SCALE_PACKET_TYPE, channel_index)

    @get_state(async.SA_SCALE_PACKET_TYPE)
    def last_scale(self, channel_index):
        return

    @bget(async.SA_SCALE_PACKET_TYPE)
    def get_scale(self, channel_index):
        """(offset, inverted)"""
        self.poll_scale(channel_index)

    @bset
    def set_acceleration(self, channel_index, acc):
        """um/s**2"""
        async.set_closed_loop_move_acceleration(
            self.system_index, channel_index, acc)

    @bset
    def poll_acceleration(self, channel_index):
        async.get_closed_loop_move_acceleration(
            self.system_index, channel_index)
        self.handler.request(
            async.SA_MOVE_ACCELERATION_PACKET_TYPE, channel_index)

    @get_state(async.SA_MOVE_ACCELERATION_PACKET_TYPE)
    def last_acceleration(self, channel_index):
        pass

    @bget(async.SA_MOVE_ACCELERATION_PACKET_TYPE)
    def get_acceleration(self, channel_index):
        self.poll_acceleration(channel_index)

    @bset
    def set_speed(self, channel_index, speed):
        """nm/s"""
        async.set_closed_loop_move_speed(
            self.system_index, channel_index, speed)

    @bset
    def poll_speed(self, channel_index):
        async.get_closed_loop_move_speed(
            self.system_index, channel_index)
        self.handler.request(
            async.SA_MOVE_SPEED_PACKET_TYPE, channel_index)

    @get_state(async.SA_MOVE_SPEED_PACKET_TYPE)
    def last_speed(self, channel_index):
        return

    @bget(async.SA_MOVE_SPEED_PACKET_TYPE)
    def get_speed(self, channel_index):
        self.poll_speed(channel_index)

    @bset
    def set_sensor_enabled(self, enable):
        """0: disabled, 1: enabled, 2: powersave"""
        async.set_sensor_enabled(self.system_index, enable)

    @bset
    def poll_sensor_enabled(self):
        async.get_sensor_enabled(self.system_index)
        self.handler.request(
            async.SA_SENSOR_ENABLED_PACKET_TYPE, 0)

    def last_sensor_enabled(self):
        # although the packet has 2 datums, channel index is undefined
        # however it seems to be 0, so just look at that channel to find
        # the system wide configuration value
        self._wait_for_all_packets(async.SA_SENSOR_ENABLED_PACKET_TYPE)
        return self.handler.state(async.SA_SENSOR_ENABLED_PACKET_TYPE, 0)

    def get_sensor_enabled(self):
        self.poll_sensor_enabled(flush=True)
        return self.last_sensor_enabled()


class FakeBMCS(oo.FakeMCS):
    def __init__(
            self, loc=None, options=None, channels=3,
            buffered=True, autoflush=True):
        super(FakeBMCS, self).__init__(loc, options)
        if isinstance(channels, (list, tuple)):
            self._channels = channels
        else:
            self._channels = range(channels)

    def stop(self):
        pass

    def buffered_output(self, enable):
        pass

    def update(self):
        pass

    def flush(self):
        pass

    def moving(self, channel_index=None, **kwargs):
        return False

    def wait(self, channel_index=None, **kwargs):
        return

    def set_max_frequency(self, channel_index, frequency, **kwargs):
        pass

    def set_step_while_scan(self, channel_index, enable, **kwargs):
        pass

    def poll_physical_known(self, channel_index, **kwargs):
        pass

    def last_physical_known(self, ci, **kwargs):
        return True

    def get_physical_known(self, ci, **kwargs):
        return True

    def poll_position(self, ci, **kwargs):
        pass

    def last_position(self, ci, **kwargs):
        return self._position[ci]

    def get_position(self, ci, **kwargs):
        return self._position[ci]

    def poll_status(self, ci, **kwargs):
        pass

    def last_status(self, ci, **kwargs):
        return self._status[ci]

    def get_status(self, ci, **kwarg):
        return self._status[ci]

    def poll_voltage(self, ci, **kwargs):
        pass

    def last_voltage(self, ci, **kwargs):
        return 0

    def get_voltage(self, ci, **kwargs):
        return 0

    def set_position_limit(self, ci, limit, **kwargs):
        self._position_limit[ci] = limit

    def poll_position_limit(self, ci, **kwargs):
        pass

    def last_position_limit(self, ci, **kwargs):
        return self._position_limit[ci]

    def get_position_limit(self, ci, **kwargs):
        return self._position_limit[ci]

    def set_scale(self, ci, scale, **kwargs):
        self._scale = scale

    def poll_scale(self, ci, **kwargs):
        pass

    def last_scale(self, ci, **kwargs):
        return self._scale

    def get_scale(self, ci, **kwargs):
        return self._scale

    def set_acceleration(self, ci, a, **kwargs):
        self._acceleration[ci] = a

    def poll_acceleration(self, ci, **kwargs):
        pass

    def last_acceleration(self, ci, **kwargs):
        return self._acceleration[ci]

    def get_acceleration(self, ci, **kwargs):
        return self._acceleration[ci]

    def set_speed(self, ci, s, **kwargs):
        self._speed[ci] = s

    def poll_speed(self, ci, **kwargs):
        pass

    def last_speed(self, ci, **kwargs):
        return self._speed[ci]

    def get_speed(self, ci, **kwargs):
        return self._speed[ci]

    def set_sensor_enabled(self, e, **kwargs):
        pass

    def poll_sensor_enabled(self, **kwargs):
        pass

    def last_sensor_enabled(self, **kwargs):
        return True

    def get_sensor_enabled(self, **kwargs):
        return True

    def move_absolute(self, i, p, hold_time=0, **kwargs):
        mi, ma = self._position_limit[i]
        if mi == 0 and ma == 0:
            self._position[i] = p
        else:
            self._position[i] = max(mi, min(p, ma))

    def move_relative(self, i, p, hold_time=0, **kwargs):
        mi, ma = self._position_limit[i]
        p = self._position[i] + p
        if mi == 0 and ma == 0:
            self._position[i] = p
        else:
            self._position[i] = max(mi, min(p, ma))
