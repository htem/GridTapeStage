#!/usr/bin/env python
"""
minimal test
 - call SA_GetStatus_A
 - read packets until status
"""

import ctypes

from . import raw


class EndStopError(raw.SmaractError):
    pass


SA_INFINITE_TIMEOUT = 0xFFFFFFFF

SA_UNBUFFERED_OUTPUT = 0
SA_BUFFERED_OUTPUT = 1

SA_NO_PACKET_TYPE = 0
SA_ERROR_PACKET_TYPE = 1
SA_POSITION_PACKET_TYPE = 2
SA_COMPLETED_PACKET_TYPE = 3
SA_STATUS_PACKET_TYPE = 4
SA_ANGLE_PACKET_TYPE = 5
SA_VOLTAGE_LEVEL_PACKET_TYPE = 6
SA_SENSOR_TYPE_PACKET_TYPE = 7
SA_SENSOR_ENABLED_PACKET_TYPE = 8
SA_END_EFFECTOR_TYPE_PACKET_TYPE = 9
SA_GRIPPER_OPENING_PACKET_TYPE = 10
SA_FORCE_PACKET_TYPE = 11
SA_MOVE_SPEED_PACKET_TYPE = 12
SA_PHYSICAL_POSITION_KNOWN_PACKET_TYPE = 13
SA_POSITION_LIMIT_PACKET_TYPE = 14
SA_ANGLE_LIMIT_PACKET_TYPE = 15
SA_SAFE_DIRECTION_PACKET_TYPE = 16
SA_SCALE_PACKET_TYPE = 17
SA_MOVE_ACCELERATION_PACKET_TYPE = 18
SA_CHANNEL_PROPERTY_PACKET_TYPE = 19
SA_CAPTURE_BUFFER_PACKET_TYPE = 20
SA_TRIGGERED_PACKET_TYPE = 21
SA_INVALID_PACKET_TYPE = 255

packet_types = {
    SA_NO_PACKET_TYPE: "SA_NO_PACKET_TYPE",
    SA_ERROR_PACKET_TYPE: "SA_ERROR_PACKET_TYPE",
    SA_POSITION_PACKET_TYPE: "SA_POSITION_PACKET_TYPE",
    SA_COMPLETED_PACKET_TYPE: "SA_COMPLETED_PACKET_TYPE",
    SA_STATUS_PACKET_TYPE: "SA_STATUS_PACKET_TYPE",
    SA_ANGLE_PACKET_TYPE: "SA_ANGLE_PACKET_TYPE",
    SA_VOLTAGE_LEVEL_PACKET_TYPE: "SA_VOLTAGE_LEVEL_PACKET_TYPE",
    SA_SENSOR_TYPE_PACKET_TYPE: "SA_SENSOR_TYPE_PACKET_TYPE",
    SA_SENSOR_ENABLED_PACKET_TYPE: "SA_SENSOR_ENABLED_PACKET_TYPE",
    SA_END_EFFECTOR_TYPE_PACKET_TYPE: "SA_END_EFFECTOR_TYPE_PACKET_TYPE",
    SA_GRIPPER_OPENING_PACKET_TYPE: "SA_GRIPPER_OPENING_PACKET_TYPE",
    SA_FORCE_PACKET_TYPE: "SA_FORCE_PACKET_TYPE",
    SA_MOVE_SPEED_PACKET_TYPE: "SA_MOVE_SPEED_PACKET_TYPE",
    SA_PHYSICAL_POSITION_KNOWN_PACKET_TYPE:
    "SA_PHYSICAL_POSITION_KNOWN_PACKET_TYPE",
    SA_POSITION_LIMIT_PACKET_TYPE: "SA_POSITION_LIMIT_PACKET_TYPE",
    SA_ANGLE_LIMIT_PACKET_TYPE: "SA_ANGLE_LIMIT_PACKET_TYPE",
    SA_SAFE_DIRECTION_PACKET_TYPE: "SA_SAFE_DIRECTION_PACKET_TYPE",
    SA_SCALE_PACKET_TYPE: "SA_SCALE_PACKET_TYPE",
    SA_MOVE_ACCELERATION_PACKET_TYPE: "SA_MOVE_ACCELERATION_PACKET_TYPE",
    SA_CHANNEL_PROPERTY_PACKET_TYPE: "SA_CHANNEL_PROPERTY_PACKET_TYPE",
    SA_CAPTURE_BUFFER_PACKET_TYPE: "SA_CAPTURE_BUFFER_PACKET_TYPE",
    SA_TRIGGERED_PACKET_TYPE: "SA_TRIGGERED_PACKET_TYPE",
    SA_INVALID_PACKET_TYPE: "SA_INVALID_PACKET_TYPE",
}

packet_types_by_name = {packet_types[k]: k for k in packet_types}

packet_types_short = {
    SA_NO_PACKET_TYPE: 'none',
    SA_ERROR_PACKET_TYPE: 'error',
    SA_POSITION_PACKET_TYPE: 'position',
    SA_COMPLETED_PACKET_TYPE: 'completed',
    SA_STATUS_PACKET_TYPE: 'status',
    SA_ANGLE_PACKET_TYPE: 'angle',
    SA_VOLTAGE_LEVEL_PACKET_TYPE: 'voltage',
    SA_SENSOR_TYPE_PACKET_TYPE: 'sensor type',
    SA_SENSOR_ENABLED_PACKET_TYPE: 'sensor enabled',
    SA_END_EFFECTOR_TYPE_PACKET_TYPE: 'end effector type',
    SA_GRIPPER_OPENING_PACKET_TYPE: 'gripper opening',
    SA_FORCE_PACKET_TYPE: 'force',
    SA_MOVE_SPEED_PACKET_TYPE: 'move speed',
    SA_PHYSICAL_POSITION_KNOWN_PACKET_TYPE: 'physical position known',
    SA_POSITION_LIMIT_PACKET_TYPE: 'position limit',
    SA_ANGLE_LIMIT_PACKET_TYPE: 'angle limit',
    SA_SAFE_DIRECTION_PACKET_TYPE: 'safe direction',
    SA_SCALE_PACKET_TYPE: 'scale',
    SA_MOVE_ACCELERATION_PACKET_TYPE: 'move acceleration',
    SA_CHANNEL_PROPERTY_PACKET_TYPE: 'channel property',
    SA_CAPTURE_BUFFER_PACKET_TYPE: 'capture buffer',
    SA_TRIGGERED_PACKET_TYPE: 'triggered',
    SA_INVALID_PACKET_TYPE: 'invalid',
}
packet_types_short_by_name = {
    packet_types_short[k]: k for k in packet_types_short}


def packet_type_to_code(k):
    if isinstance(k, (int, long)):
        return k
    if k in packet_types_by_name:
        return packet_types_by_name[k]
    if k in packet_types_short_by_name:
        return packet_types_short_by_name[k]
    raise KeyError("Unknown packet type: %s", k)


packet_valid_data = {
    SA_NO_PACKET_TYPE: lambda p: (),
    SA_ERROR_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_POSITION_PACKET_TYPE: lambda p: (p.channelIndex, p.data2),
    SA_COMPLETED_PACKET_TYPE: lambda p: (p.channelIndex, ),
    SA_STATUS_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_ANGLE_PACKET_TYPE: lambda p: (p.channelIndex, p.data1, p.data2),
    SA_VOLTAGE_LEVEL_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_SENSOR_TYPE_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_SENSOR_ENABLED_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_END_EFFECTOR_TYPE_PACKET_TYPE:
    lambda p: (p.channelIndex, p.data1, p.data2, p.data3),
    SA_GRIPPER_OPENING_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_FORCE_PACKET_TYPE: lambda p: (p.channelIndex, p.data2),
    SA_MOVE_SPEED_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_PHYSICAL_POSITION_KNOWN_PACKET_TYPE:
    lambda p: (p.channelIndex, p.data1),
    SA_POSITION_LIMIT_PACKET_TYPE:
    lambda p: (p.channelIndex, p.data2, p.data3),
    SA_ANGLE_LIMIT_PACKET_TYPE:
    lambda p: (p.channelIndex, p.data1, p.data2, p.data3, p.data4),
    SA_SAFE_DIRECTION_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_SCALE_PACKET_TYPE:
    lambda p: (p.channelIndex, p.data2, p.data1),  # shift, inversion
    SA_MOVE_ACCELERATION_PACKET_TYPE: lambda p: (p.channelIndex, p.data1),
    SA_CHANNEL_PROPERTY_PACKET_TYPE:
    lambda p: (p.channelIndex, p.data1, p.data2),
    SA_CAPTURE_BUFFER_PACKET_TYPE:
    lambda p: (p.channelIndex, p.data1, p.data2, p.data3, p.data4),  # ?
    SA_TRIGGERED_PACKET_TYPE: lambda p: (p.channelIndex, ),
    SA_INVALID_PACKET_TYPE: lambda p: (),
}


def get_packet_data(packet):
    return packet_valid_data[packet.packetType](packet)


# library function
if hasattr(raw, 'lib'):
    def lfunc(name):
        f = getattr(raw.lib, name)

        def wrapped(*args, **kwargs):
            raw.check_return(f(*args, **kwargs))
        return wrapped
else:
    def lfunc(name):
        fn = name

        def wrapped(*args, **kwargs):
            raise Exception("Smaract lib not found, cannot use %s" % fn)
        return wrapped


# system function
def sfunc(name):
    def wrapper(f):
        lf = lfunc(name)

        def wrapped(system_index, *args):
            assert isinstance(system_index, (int, long))
            lf(ctypes.c_uint(system_index), *f(*args))
        wrapped.__name__ = f.__name__
        wrapped.__doc__ = f.__doc__
        return wrapped
    return wrapper


# channel function
def cfunc(name):
    def wrapper(f):
        lf = lfunc(name)

        def wrapped(system_index, channel_index, *args):
            assert isinstance(system_index, (int, long))
            assert isinstance(channel_index, (int, long))
            lf(
                ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
                *f(*args))
        wrapped.__name__ = f.__name__
        wrapped.__doc__ = f.__doc__
        return wrapped
    return wrapper


class Packet(ctypes.Structure):
    _fields_ = [
        ('packetType', ctypes.c_uint),
        ('channelIndex', ctypes.c_uint),
        ('data1', ctypes.c_uint),
        ('data2', ctypes.c_int),
        ('data3', ctypes.c_int),
        ('data4', ctypes.c_uint),
    ]


def parse_packet(packet):
    return (packet_types_short[packet.packetType], ) + \
        packet_valid_data[packet.packetType](packet)


def receive_next_packet(system_index, timeout=0):
    assert isinstance(system_index, (int, long))
    assert isinstance(timeout, (int, long))
    packet = Packet()
    raw.check_return(raw.lib.SA_ReceiveNextPacket_A(
        ctypes.c_uint(system_index), ctypes.c_uint(timeout),
        ctypes.byref(packet)))
    return packet


def look_at_next_packet(system_index, timeout=0):
    assert isinstance(system_index, (int, long))
    assert isinstance(timeout, (int, long))
    packet = Packet()
    raw.check_return(raw.lib.SA_LookAtNextPacket_A(
        ctypes.c_uint(system_index), ctypes.c_uint(timeout),
        ctypes.byref(packet)))
    return packet


@sfunc('SA_CancelWaitForPacket_A')
def cancel_wait_for_packet():
    return ()


@sfunc('SA_DiscardPacket_A')
def discard_packet():
    return ()


@cfunc('SA_SetReportOnComplete_A')
def set_report_on_complete(enable):
    return (ctypes.c_uint(enable), )


@sfunc('SA_SetBufferedOutput_A')
def set_buffered_output(mode):
    assert isinstance(mode, (int, long))
    return (ctypes.c_uint(mode), )


@sfunc('SA_GetBufferedOutput_A')
def get_buffered_output():
    # TODO this appears to not be async
    # not sure what to do here
    return ()


@sfunc('SA_FlushOutput_A')
def flush_output():
    return ()


@cfunc('SA_AppendTriggeredCommand_A')
def append_triggered_command(trigger_source):
    """
    encode trigger_source using esv
    sel: software trigger or digital in
    sub_sel:
      0/1 for digital in
      0-255 for software
    """
    assert isinstance(trigger_source, (int, long))
    return (ctypes.c_int(trigger_source), )


@cfunc('SA_ClearTriggeredCommandQueue_A')
def clear_triggered_command_queue():
    return ()


@cfunc('SA_GetAngle_A')
def get_angle():
    return ()


@cfunc('SA_GetAngleLimit_A')
def get_angle_limit():
    return ()


@sfunc('SA_GetCaptureBuffer_A')
def get_capture_buffer(buffer_index):
    assert isinstance(buffer_index, (int, long))
    return (ctypes.c_uint(buffer_index), )


@cfunc('SA_GetChannelProperty_A')
def get_channel_property(key):
    assert isinstance(key, (int, long))
    return (ctypes.c_uint(key), )


@cfunc('SA_GetClosedLoopMoveAcceleration_A')
def get_closed_loop_move_acceleration():
    return ()


@cfunc('SA_GetClosedLoopMoveSpeed_A')
def get_closed_loop_move_speed():
    return ()


@cfunc('SA_GetEndEffectorType_A')
def get_end_effector_type():
    return ()


@cfunc('SA_GetForce_A')
def get_force():
    return ()


@cfunc('SA_GetGripperOpening_A')
def get_gripper_opening():
    return ()


@cfunc('SA_GetPhysicalPositionKnown_A')
def get_physical_position_known():
    return ()


@cfunc('SA_GetPosition_A')
def get_position():
    return ()


@cfunc('SA_GetPositionLimit_A')
def get_position_limit():
    return ()


@cfunc('SA_GetSafeDirection_A')
def get_safe_direction():
    return ()


@cfunc('SA_GetScale_A')
def get_scale():
    return ()


@sfunc('SA_GetSensorEnabled_A')
def get_sensor_enabled():
    return ()


@cfunc('SA_GetSensorType_A')
def get_sensor_type():
    return ()


@cfunc('SA_GetStatus_A')
def get_status():
    return ()


@cfunc('SA_GetVoltageLevel_A')
def get_voltage_level():
    return ()


@cfunc('SA_SetReportOnTriggered_A')
def set_report_on_triggered(report):
    assert isinstance(report, (int, long))
    return (ctypes.c_int(report), )


@cfunc('SA_SetAccumulateRelativePositions_A')
def set_accumulate_relative_positions(enable):
    return (ctypes.c_uint(int(enable)), )


@cfunc('SA_SetAngleLimit_A')
def set_angle_limit(min_angle, min_revolution, max_angle, max_revolution):
    assert isinstance(min_angle, (int, long))
    assert isinstance(min_revolution, (int, long))
    assert isinstance(max_angle, (int, long))
    assert isinstance(max_revolution, (int, long))
    return (
        ctypes.c_uint(min_angle),
        ctypes.c_int(min_revolution),
        ctypes.c_uint(max_angle),
        ctypes.c_int(max_revolution),
    )


@cfunc('SA_SetChannelProperty_A')
def set_channel_property(key, value):
    assert isinstance(key, (int, long))
    assert isinstance(value, (int, long))
    return (ctypes.c_uint(key), ctypes.c_int(value))


@cfunc('SA_SetClosedLoopMaxFrequency_A')
def set_closed_loop_max_frequency(frequency):
    assert isinstance(frequency, (int, long))
    return (ctypes.c_uint(frequency), )


@cfunc('SA_SetClosedLoopMoveAcceleration_A')
def set_closed_loop_move_acceleration(acceleration):
    assert isinstance(acceleration, (int, long))
    return (ctypes.c_uint(acceleration), )


@cfunc('SA_SetClosedLoopMoveSpeed_A')
def set_closed_loop_move_speed(speed):
    assert isinstance(speed, (int, long))
    return (ctypes.c_uint(speed), )


@cfunc('SA_SetEndEffectorType_A')
def set_end_effector_type(effector_type, param1, param2):
    assert isinstance(effector_type, (int, long))
    assert isinstance(param1, (int, long))
    assert isinstance(param2, (int, long))
    return (
        ctypes.c_uint(effector_type),
        ctypes.c_int(param1),
        ctypes.c_int(param2),
    )


@cfunc('SA_SetPosition_A')
def set_position(position):
    assert isinstance(position, (int, long))
    return (ctypes.c_int(position), )


@cfunc('SA_SetPositionLimit_A')
def set_position_limit(min_position, max_position):
    assert isinstance(min_position, (int, long))
    assert isinstance(max_position, (int, long))
    return (ctypes.c_int(min_position), ctypes.c_int(max_position))


@cfunc('SA_SetSafeDirection_A')
def set_safe_direction(direction):
    assert isinstance(direction, (int, long))
    return (ctypes.c_uint(direction), )


@cfunc('SA_SetScale_A')
def set_scale(scale, inverted):
    assert isinstance(scale, (int, long))
    return (ctypes.c_int(scale), ctypes.c_uint(int(inverted)))


@sfunc('SA_SetSensorEnabled_A')
def set_sensor_enabled(enable):
    return (ctypes.c_uint(int(enable)), )


@cfunc('SA_SetSensorType_A')
def set_sensor_type(sensor_type):
    assert isinstance(sensor_type, (int, long))
    return (ctypes.c_uint(sensor_type), )


@cfunc('SA_SetStepWhileScan_A')
def set_step_while_scale(step):
    assert isinstance(step, (int, long))
    return (ctypes.c_uint(step), )


@cfunc('SA_SetZeroForce_A')
def set_zero_force():
    return ()


@cfunc('SA_CalibrateSensor_A')
def calibrate_sensor():
    return ()


@cfunc('SA_FindReferenceMark_A')
def find_reference_mark(direction, hold_time, auto_zero):
    assert isinstance(direction, (int, long))
    assert isinstance(hold_time, (int, long))
    assert isinstance(auto_zero, (int, long))
    return (
        ctypes.c_uint(direction), ctypes.c_uint(hold_time),
        ctypes.c_uint(auto_zero))


@cfunc('SA_GotoAngleAbsolute_A')
def go_to_angle_absolute(angle, revolution, hold_time):
    assert isinstance(angle, (int, long))
    assert isinstance(revolution, (int, long))
    assert isinstance(hold_time, (int, long))
    return (
        ctypes.c_uint(angle), ctypes.c_int(revolution),
        ctypes.c_uint(hold_time))


@cfunc('SA_GotoAngleRelative_A')
def go_to_angle_relative(angle_diff, revolution_diff, hold_time):
    assert isinstance(angle_diff, (int, long))
    assert isinstance(revolution_diff, (int, long))
    assert isinstance(hold_time, (int, long))
    return (
        ctypes.c_int(angle_diff), ctypes.c_int(revolution_diff),
        ctypes.c_uint(hold_time))


@cfunc('SA_GotoGripperForceAbsolute_A')
def go_to_gripper_force_absolute(force, speed, hold_time):
    assert isinstance(force, (int, long))
    assert isinstance(speed, (int, long))
    assert isinstance(hold_time, (int, long))
    return (
        ctypes.c_int(force), ctypes.c_uint(speed), ctypes.c_uint(hold_time))


@cfunc('SA_GotoGripperOpeningAbsolute_A')
def go_to_gripper_opening_absolute(opening, speed):
    assert isinstance(opening, (int, long))
    assert isinstance(speed, (int, long))
    return (ctypes.c_uint(opening), ctypes.c_uint(speed))


@cfunc('SA_GotoGripperOpeningRelative_A')
def go_to_gripper_opening_relative(opening, speed):
    assert isinstance(opening, (int, long))
    assert isinstance(speed, (int, long))
    return (ctypes.c_int(opening), ctypes.c_uint(speed))


@cfunc('SA_GotoPositionAbsolute_A')
def go_to_position_absolute(position, hold_time):
    assert isinstance(position, (int, long))
    assert isinstance(hold_time, (int, long))
    return (ctypes.c_int(position), ctypes.c_uint(hold_time))


@cfunc('SA_GotoPositionRelative_A')
def go_to_position_relative(position, hold_time):
    assert isinstance(position, (int, long))
    assert isinstance(hold_time, (int, long))
    return (ctypes.c_int(position), ctypes.c_uint(hold_time))


@cfunc('SA_ScanMoveAbsolute_A')
def scan_move_absolute(target, scan_speed):
    assert isinstance(target, (int, long))
    assert isinstance(scan_speed, (int, long))
    return (ctypes.c_uint(target), ctypes.c_uint(scan_speed))


@cfunc('SA_ScanMoveRelative_A')
def scan_move_relative(target, scan_speed):
    assert isinstance(target, (int, long))
    assert isinstance(scan_speed, (int, long))
    return (ctypes.c_int(target), ctypes.c_uint(scan_speed))


@cfunc('SA_StepMove_A')
def step_move(steps, amplitude, frequency):
    assert isinstance(steps, (int, long))
    assert isinstance(amplitude, (int, long))
    assert isinstance(frequency, (int, long))
    return (
        ctypes.c_int(steps), ctypes.c_uint(amplitude),
        ctypes.c_uint(frequency))


@cfunc('SA_Stop_A')
def stop():
    return ()


@sfunc('SA_TriggerCommand_A')
def trigger_command(trigger_index):
    assert isinstance(trigger_index, (int, long))
    return (ctypes.c_uint(trigger_index), )
