"""
An object-oriented class for accessing a smaract controller
"""

import time

from . import async
from . import raw


class MCS(object):
    def __init__(self, loc=None, options=None):
        self.system_index = None
        self._loc = loc
        if loc is not None:
            if options is not None:
                self.connect(loc, options)
            else:
                self.connect(loc)

    def __del__(self):
        try:
            self.disconnect()
        except:
            pass

    def connect(self, loc=None, options='sync'):
        if loc is None:
            loc = self._loc
        if not self.connected:
            self.system_index = raw.open_system(loc, options)

    def disconnect(self):
        if self.connected:
            raw.close_system(self.system_index)
            self.system_index = None

    @property
    def connected(self):
        return self.system_index is not None

    # -- calibration functions --
    def calibrate(self, channel_index):
        raw.calibrate_sensor(self.system_index, channel_index)

    def find_ref(self, channel_index, direction=0, hold_time=0, auto_zero=1):
        raw.find_reference_mark(
            self.system_index, channel_index, direction, hold_time, auto_zero)
        return self.physical_known(channel_index)

    # -- configuration functions --
    def position_limit(self, channel_index, limit=None):
        if limit is not None:
            raw.set_position_limit(self.system_index, channel_index, *limit)
        return raw.get_position_limit(self.system_index, channel_index)

    def hcm(self, status):
        if isinstance(status, (str, unicode)):
            status = {
                'disabled': 0,
                'enabled': 1,
                'display': 2,
            }.get(status, -1)
        assert status in (0, 1, 2)
        raw.set_hcm_enabled(self.system_index, status)

    def scale(self, channel_index, scale=None):
        """
        scale = (offset[int], invert[bool])
        """
        if scale is None:
            return raw.get_scale(self.system_index, channel_index)
        raw.set_scale(
            self.system_index, channel_index,
            int(scale[0]), int(scale[1]))

    def sensor(self, enabled=None):
        if enabled is None:
            return raw.get_sensor_enabled(self.system_index)
        if isinstance(enabled, (str, unicode)):
            enabled = {
                'disabled': 0,
                'enabled': 1,
                'powersave': 2,
            }.get(enabled, -1)
        assert enabled in {0, 1, 2}
        raw.set_sensor_enabled(self.system_index, enabled)

    # accumulate_relative_positions TODO

    def max_frequency(self, channel_index, frequency):
        """ < 5000 for vacuum """
        raw.set_closed_loop_max_frequency(
            self.system_index, channel_index, frequency)

    def acceleration(self, channel_index, value=None):
        if value is None:
            return raw.get_closed_loop_move_acceleration(
                self.system_index, channel_index)
        raw.set_closed_loop_move_acceleration(
            self.system_index, channel_index, value)

    def speed(self, channel_index, value=None):
        if value is None:
            return raw.get_closed_loop_move_speed(
                self.system_index, channel_index)
        raw.set_closed_loop_move_speed(
            self.system_index, channel_index, value)

    def step_while_scan(self, channel_index, enable):
        raw.set_step_while_scan(self.system_index, channel_index, enable)

    # -- status functions --
    def physical_known(self, channel_index):
        return raw.get_physical_position_known(
            self.system_index, channel_index)

    def position(self, channel_index):
        return raw.get_position(self.system_index, channel_index)

    def status(self, channel_index):
        return raw.get_status(self.system_index, channel_index)

    def voltage(self, channel_index):
        return raw.get_voltage_level(self.system_index, channel_index)

    # -- movement functions --
    def move_absolute(self, channel_index, position, hold_time=0):
        raw.goto_position_absolute(
            self.system_index, channel_index, position, hold_time)

    def move_relative(self, channel_index, diff, hold_time=0):
        raw.goto_position_relative(
            self.system_index, channel_index, diff, hold_time)

    def move_open_loop(
            self, channel_index, steps, amplitude=4092, frequency=1000):
        """
        full amplitude 100V(4092) is ~1.2 um
        need at least 30V for step
        can be ~20% error
        """
        raw.step_move(
            self.system_index, channel_index, steps, amplitude, frequency)

    def stop(self, channel_index):
        raw.stop(self.system_index, channel_index)


class AMCS(MCS):
    def __init__(
            self, loc=None, options=None, wait_for_gets=True,
            packet_delay=0.002):
        self._channel_states = {}
        super(AMCS, self).__init__(loc, options)
        #self._state = state.Stateful(async.packet_types_short.keys())
        self._wait_for_gets = wait_for_gets
        self._packet_delay = packet_delay
        #self._moving = {}

    def connect(self, loc=None, options='async'):
        if loc is None:
            loc = self._loc
        if not self.connected:
            self.system_index = raw.open_system(loc, options)
            try:
                for i in xrange(3):
                    self.report_completed(i, True)
                    self._channel_states[i] = {}
            except raw.SmaractError:
                pass

    def moving(self, channel_index=None):
        # TODO what to do when an error occurs
        if channel_index is None:
            return any([self.moving(i) for i in self._channel_states])
        else:
            if self._channel_states[channel_index].get(3, True):
                return False
            self.process_packets(until_channel=channel_index, until_packet=3)
            return not self._channel_states[channel_index].get(3, True)

    def _digest_packet(self, packet):
        if packet.packetType == 0:
            return None
        if packet.packetType == 1:
            pd = async.get_packet_data(packet)
            # in the event that the stage was moving, reset it's state
            self._channel_states[pd[0]][3] = True
            # TODO what to do when an error occurs
            raise raw.SmaractError(
                "Smaract PacketError: %s[%s]" % (
                    pd, raw.error_codes.get(pd[1], "")))
        if packet.packetType == 255:
            return
        datum = async.get_packet_data(packet)
        #print("Packet[%s]: %s" % (packet.packetType, datum))
        if len(datum) == 1:
            self._channel_states[datum[0]][packet.packetType] = True
        elif len(datum) == 2:
            self._channel_states[datum[0]][packet.packetType] = datum[1]
        else:
            self._channel_states[datum[0]][packet.packetType] = datum[1:]
        return datum[0]
        #self._state.update_state(
        #    packet.packetType, *(async.get_packet_data(packet)[1:]))
        #if packet.packetType == 3:
        #    self._moving[packet.channelIndex] = False

    def process_packets(
            self, until_channel=None, until_packet='none', max_n=10):
        ptype = async.packet_type_to_code(until_packet)
        if until_channel is None:
            ptest = lambda i, p: p.packetType == ptype
        else:
            ptest = lambda i, p: (
                (i == until_channel) and (p.packetType == ptype))
        packet = async.receive_next_packet(self.system_index)
        channel_index = self._digest_packet(packet)
        i = 0
        while not (ptest(channel_index, packet) or i >= max_n):
            time.sleep(self._packet_delay)
            packet = async.receive_next_packet(self.system_index)
            channel_index = self._digest_packet(packet)
            i += 1

    def _check_get(self, channel_index, key, force=False):
        if self._wait_for_gets or force:
            self._channel_states[channel_index][key] = None
            #self._state.clear_state(key)
            self.process_packets(until_channel=channel_index, until_packet=key)
            #return self._state.state[key]
            return self._channel_states[channel_index][key]
            # TODO raise warning or error? didn't wait long enough?

    def report_completed(self, channel_index, enable=True):
        async.set_report_on_complete(self.system_index, channel_index, enable)

    def calibrate(self, channel_index):
        async.calibrate_sensor(self.system_index, channel_index)

    def find_ref(self, channel_index, direction=0, hold_time=0, auto_zero=1):
        async.find_reference_mark(
            self.system_index, channel_index, direction, hold_time, auto_zero)
        return self.physical_known(channel_index)

    def position_limit(self, channel_index, limit=None):
        if limit is not None:
            async.set_position_limit(
                self.system_index, channel_index, *limit)
        async.get_position_limit(self.system_index, channel_index)
        return self._check_get(channel_index, 14)

    def scale(self, channel_index, scale=None):
        """
        scale = (offset[signed int], invert[bool])
        """
        if scale is not None:
            async.set_scale(
                self.system_index, channel_index, scale[0], int(scale[1]))
        async.get_scale(self.system_index, channel_index)
        return self._check_get(channel_index, 17)

    def sensor(self, enabled=None):
        if enabled is not None:
            if isinstance(enabled, (str, unicode)):
                enabled = {
                    'disabled': 0,
                    'enabled': 1,
                    'powersave': 2,
                }.get(enabled, -1)
            assert enabled in {0, 1, 2}
            return async.set_sensor_enabled(self.system_index, enabled)
        async.get_sensor_enabled(self.system_index)
        return self._check_get(until_packet=8)

    def max_frequency(self, channel_index, frequency):
        async.set_closed_loop_max_frequency(
            self.system_index, channel_index, frequency)

    def acceleration(self, channel_index, value=None):
        if value is not None:
            async.set_closed_loop_move_acceleration(
                self.system_index, channel_index, value)
        async.get_closed_loop_move_acceleration(
            self.system_index, channel_index)
        return self._check_get(channel_index, 18)

    def speed(self, channel_index, value=None):
        if value is not None:
            async.set_closed_loop_move_speed(
                self.system_index, channel_index, value)
        async.get_closed_loop_move_speed(
            self.system_index, channel_index)
        return self._check_get(channel_index, 12)

    def step_while_scan(self, channel_index, enable):
        async.set_step_while_scan(self.system_index, channel_index, enable)

    def physical_known(self, channel_index):
        async.get_physical_position_known(self.system_index, channel_index)
        return self._check_get(channel_index, 13)

    def position(self, channel_index):
        async.get_position(self.system_index, channel_index)
        return self._check_get(channel_index, 2)

    def status(self, channel_index):
        async.get_status(self.system_index, channel_index)
        return self._check_get(channel_index, 4)

    def voltage(self, channel_index):
        async.get_voltage_level(self.system_index, channel_index)
        return self._check_get(channel_index, 6)

    def move_absolute(self, channel_index, position, hold_time=0, wait=False):
        async.go_to_position_absolute(
            self.system_index, channel_index, position, hold_time)
        #self._moving[channel_index] = True
        self._channel_states[channel_index][1] = 0
        self._channel_states[channel_index][3] = False
        if wait:
            self.wait(channel_index)

    def move_relative(self, channel_index, diff, hold_time=0, wait=False):
        async.go_to_position_relative(
            self.system_index, channel_index, diff, hold_time)
        #self._moving[channel_index] = True
        self._channel_states[channel_index][1] = 0
        self._channel_states[channel_index][3] = False
        if wait:
            self.wait(channel_index)

    def move_open_loop(
            self, channel_index, steps, amplitude=4092, frequency=1000,
            wait=False):
        async.step_move(
            self.system_index, channel_index, steps, amplitude, frequency)
        #self._moving[channel_index] = True
        self._channel_states[channel_index][1] = 0
        self._channel_states[channel_index][3] = False
        if wait:
            self.wait(channel_index)

    def wait(self, channel_index=None):
        while self.moving(channel_index):
            pass  # TODO max # of waits? or time of wait?

    def stop(self, channel_index):
        async.stop(self.system_index, channel_index)
        #self._moving[channel_index] = False
        self._channel_states[channel_index][1] = 0
        self._channel_states[channel_index][3] = True


class FakeMCS(object):
    def __init__(self, loc=None, options=None):
        self._position_limit = [(0, 0), (0, 0), (0, 0)]
        self._scale = [1, 0]
        self._acceleration = [0, 0, 0]
        self._speed = [0, 0, 0]
        self._position = [0, 0, 0]
        self._status = [0, 0, 0]
        self._connected = False

    def __del__(self):
        pass

    def connect(self, loc=None, options='sync'):
        self._connected = True

    def disconnect(self):
        self._connected = False

    @property
    def connected(self):
        return self._connected

    def calibrate(self, channel_index):
        pass

    def find_ref(self, *args, **kwargs):
        pass

    def position_limit(self, channel_index, limit=None):
        if limit is None:
            return self._position_limit[channel_index]
        self._position_limit[channel_index] = limit

    def hcm(self, status):
        pass

    def max_frequency(self, *args):
        pass

    def scale(self, i, s=None, inv=False):
        if s is None:
            return self._scale
        self._scale = [s, int(inv)]

    def acceleration(self, i, v=None):
        if v is None:
            return self._acceleration[i]
        self._acceleration[i] = v

    def speed(self, i, v=None):
        if v is None:
            return self._speed[i]
        self._speed[i] = v

    def step_while_scan(self, *args):
        pass

    def physical_known(self, i):
        return True

    def position(self, i):
        return self._position[i]

    def status(self, i):
        return self._status[i]

    def voltage(self, i):
        return 4095

    def move_absolute(self, i, p, h=0):
        mi, ma = self._position_limit[i]
        if mi == 0 and ma == 0:
            self._position[i] = p
        else:
            self._position[i] = max(mi, min(p, ma))

    def move_relative(self, i, p, h=0):
        mi, ma = self._position_limit[i]
        p = self._position[i] + p
        if mi == 0 and ma == 0:
            self._position[i] = p
        else:
            self._position[i] = max(mi, min(p, ma))

    def move_open_loop(self, i, s, a=4092, f=1000):
        pass

    def stop(self, i):
        pass
