"""
'raw' ctypes wrapper of libmcscontrol

All functions return at a minimum a return/error code (see error_codes).

Function parameters are strongly typed.

TODO
 - add checks for unsupported functions
    [old mcs doesn't support newer functions]
 - more error checking
 - e-stop?
 - reorganize to a more logical ordering of functions
"""

import ctypes
import time
import warnings


# == return value ==
error_codes = {
    0: 'SA_OK',
    1: 'SA_INITIALIZATION_ERROR',
    2: 'SA_NOT_INITIALIZED_ERROR',
    3: 'SA_NO_SYSTEMS_FOUND_ERROR',
    4: 'SA_TOO_MANY_SYSTEMS_ERROR',
    5: 'SA_INVALID_SYSTEM_INDEX_ERROR',
    6: 'SA_INVALID_CHANNEL_INDEX_ERROR',
    7: 'SA_TRANSMIT_ERROR',
    8: 'SA_WRITE_ERROR',
    9: 'SA_INVALID_PARAMETER_ERROR',
    10: 'SA_READ_ERROR',
    12: 'SA_INTERNAL_ERROR',
    13: 'SA_WRONG_MODE_ERROR',
    14: 'SA_PROTOCOL_ERROR',
    15: 'SA_TIMEOUT_ERROR',
    16: 'SA_NOTIFICATION_ALREADY_SET_ERROR',
    17: 'SA_ID_LIST_TOO_SMALL_ERROR',
    18: 'SA_SYSTEM_ALREADY_ADDED_ERROR',
    19: 'SA_WRONG_CHANNEL_TYPE_ERROR',
    20: 'SA_CANCELED_ERROR',
    21: 'SA_INVALID_SYSTEM_LOCATOR_ERROR',
    22: 'SA_INPUT_BUFFER_OVERFLOW_ERROR',
    23: 'SA_QUERYBUFFER_SIZE_ERROR',
    24: 'SA_DRIVER_ERROR',
    129: 'SA_NO_SENSOR_PRESENT_ERROR',
    130: 'SA_AMPLITUDE_TOO_LOW_ERROR',
    131: 'SA_AMPLITUDE_TOO_HIGH_ERROR',
    132: 'SA_FREQUENCY_TOO_LOW_ERROR',
    133: 'SA_FREQUENCY_TOO_HIGH_ERROR',
    135: 'SA_SCAN_TARGET_TOO_HIGH_ERROR',
    136: 'SA_SCAN_SPEED_TOO_LOW_ERROR',
    137: 'SA_SCAN_SPEED_TOO_HIGH_ERROR',
    140: 'SA_SENSOR_DISABLED_ERROR',
    141: 'SA_COMMAND_OVERRIDEN_ERROR',
    142: 'SA_END_STOP_REACHED_ERROR',
    143: 'SA_WRONG_SENSOR_TYPE_ERROR',
    144: 'SA_COULD_NOT_FIND_REF_ERROR',
    145: 'SA_WRONG_END_EFFECTOR_TYPE_ERROR',
    146: 'SA_MOVEMENT_LOCKED_ERROR',
    147: 'SA_RANGE_LIMIT_REACHED_ERROR',
    148: 'SA_PHYSICAL_POSITION_UNKNOWN_ERROR',
    149: 'SA_OUTPUT_BUFFER_OVERFLOW_ERROR',
    150: 'SA_COMMAND_NOT_PROCESSABLE_ERROR',
    151: 'SA_WAITING_FOR_TRIGGER_ERROR',
    152: 'SA_COMMAND_NOT_TRIGGERABLE_ERROR',
    153: 'SA_COMMAND_QUEUE_FULL_ERROR',
    154: 'SA_INVALID_COMPONENT_ERROR',
    155: 'SA_INVALID_SUB_COMPONENT_ERROR',
    156: 'SA_INVALID_PROPERTY_ERROR',
    157: 'SA_PERMISSION_DENIED_ERROR',
    240: 'SA_UNKNOWN_COMMAND_ERROR',
    255: 'SA_OTHER_ERROR',
}
error_strings = {v: k for k, v in error_codes.items()}
# == channel status codes ==
channel_status_codes = {
    0: 'SA_STOPPED_STATUS',
    1: 'SA_STEPPING_STATUS',
    2: 'SA_SCANNING_STATUS',
    3: 'SA_HOLDING_STATUS',
    4: 'SA_TARGET_STATUS',
    5: 'SA_MOVE_DELAY_STATUS',
    6: 'SA_CALIBRATING_STATUS',
    7: 'SA_FINDING_REF_STATUS',
    8: 'SA_OPENING_STATUS',
}
channel_status_strings = {v: k for k, v in channel_status_codes.items()}
# == sensor types ==
sensor_type_codes = {
    0: 'None',
    1: 'S',
    2: 'SR',
    4: 'MR',
    5: 'SP',
    6: 'SC',
    7: 'M25',
    8: 'SR20',
    9: 'M',
    10: 'GC',
    11: 'GD',
    12: 'GE',
    13: 'RA',
    14: 'GF',
    15: 'RB',
}
sensor_type_strings = {v: k for k, v in sensor_type_codes.items()}

# == components ==
component_selector_codes = {
    1: 'SA_GENERAL',
    2: 'SA_DIGITAL_IN',
    3: 'SA_ANALOG_IN',
    4: 'SA_COUNTER',
    5: 'SA_CAPTURE_BUFFER',
    6: 'SA_COMMAND_QUEUE',
    7: 'SA_SOFTWARE_TRIGGER',
    8: 'SA_SENSOR',
    9: 'SA_MONITOR'
}
component_selector_strings = {
    v: k for k, v in component_selector_codes.items()}

component_sub_selector_codes = {
    1: 'SA_EMERGENCY_STOP',
    2: 'SA_LOW_VIBRATION',
    4: 'SA_BROADCAST_STOP',
    5: 'SA_POSITION_CONTROL',
    11: 'SA_POWER_SUPPLY',
    22: 'SA_SCALE',
}
component_sub_selector_strings = {
    v: k for k, v in component_sub_selector_codes.items()}

component_property_codes = {
    1: 'SA_OPERATION_MODE',
    2: 'SA_ACTIVE_EDGE',
    3: 'SA_TRIGGER_SOURCE',
    4: 'SA_SIZE',
    5: 'SA_VALUE',
    6: 'SA_CAPACITY',
    7: 'SA_DIRECTION',
    8: 'SA_SETPOINT',
    9: 'SA_P_GAIN',
    10: 'SA_P_RIGHT_SHIFT',
    11: 'SA_I_GAIN',
    12: 'SA_I_RIGHT_SHIFT',
    13: 'SA_D_GAIN',
    14: 'SA_D_RIGHT_SHIFT',
    15: 'SA_ANTI_WINDUP',
    16: 'SA_PID_LIMIT',
    17: 'SA_FORCED_SLIP',
    38: 'SA_THRESHOLD',
    45: 'SA_DEFAULT_OPERATION_MODE',
    47: 'SA_OFFSET',
}
component_property_strings = {
    v: k for k, v in component_property_codes.items()}

SA_SYNCHRONOUS_COMMUNICATION = 0
SA_ASYNCHRONOUS_COMMUNICATION = 1
SA_HARDWARE_RESET = 2

SA_NO_STEP_WHILE_SCAN = 0
SA_STEP_WHILE_SCAN = 1

SA_SENSOR_DISABLED = 0
SA_SENSOR_ENABLED = 1
SA_SENSOR_POWERSAVE = 2

SA_NO_REPORT_ON_COMPLETE = 0
SA_REPORT_ON_COMPLETE = 1

SA_NO_ACCUMULATE_RELATIVE_POSITIONS = 0
SA_ACCUMULATE_RELATIVE_POSITIONS = 0

SA_HCM_DISABLED = 0
SA_HCM_ENABLED = 1
SA_HCM_CONTROLS_DISABLED = 2

SA_FORWARD_DIRECTION = 0
SA_BACKWARD_DIRECTION = 1

SA_NO_AUTO_ZERO = 0
SA_AUTO_ZERO = 1

SA_PHYSICAL_POSITION_UNKNOWN = 0
SA_PHYSICAL_POSITION_KNOWN = 1

SA_POSITIONER_CHANNEL_TYPE = 0
SA_END_EFFECTOR_CHANNEL_TYPE = 1


class SmaractError(IOError):
    pass


# ====== later =======
# SA_GetForce_S
# SA_GetGripperOpening_S
# SA_SetAngleLimit_S
# SA_GetEndEffectorType_S
# SA_SetEndEffectorType_S
# SA_SetZeroForce_S
# SA_GotoAngleAbsolute_S
# SA_GotoAngleRelative_S
# SA_GotoGripperForceAbsolute_S
# SA_GotoGripperOpeningAbsolute_S
# SA_GotoGripperOpeningRelative_S
#
# == async function ==
# == packet type (only for async) ==


# get lib
try:
    lib = ctypes.cdll.LoadLibrary('libmcscontrol.so')
except OSError:
    warnings.warn("Failed to load libmcscontrol.so")


def check_return(r):
    if r == 0:
        return r
    raise SmaractError(error_codes[r])


# == init functions ==
def get_channel_type(system_index, channel_index):
    """Get the channel type (effector or positioner)

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    channel_type : int (unsigned)
        0 = positioner
        1 = effector
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    t = ctypes.c_uint(0)
    check_return(lib.SA_GetChannelType(ctypes.c_uint(
        system_index), ctypes.c_uint(channel_index),
        ctypes.byref(t)))
    # TODO parse type
    #   (SA_POSITIONER_CHANNEL_TYPE or SA_END_EFFECTOR_CHANNEL_TYPE)
    return t.value


def dsv(sv):
    """Decode a selector value (used for get_channel_property)

    Parameters
    ----------
    sv : int
        selector value to decode

    Returns
    -------
    sel : int (unsigned)
        selector
    sub_sel : int (unsigned)
        sub-selector
    """
    assert isinstance(sv, (int, long))
    sel = ctypes.c_uint(0)
    sub_sel = ctypes.c_uint(0)
    lib.SA_DSV(ctypes.c_int(sv), ctypes.byref(sel), ctypes.byref(sub_sel))
    return sel.value, sub_sel.value


def esv(sel, sub_sel):
    """Encode a selector value (used for set_channel_property)

    Parameters
    ----------
    sel : int (unsigned)
        selector
    sub_sel : int (unsigned)
        sub-selector

    Returns
    -------
    sv : int
        encoded selector value
    """
    assert isinstance(sel, (int, long))
    assert isinstance(sub_sel, (int, long))
    return lib.SA_ESV(ctypes.c_uint(sel), ctypes.c_uint(sub_sel))


def epk(sel, sub_sel, prop):
    """Encode a property key (used with get_channel_property)

    Parameters
    ----------
    sel : int (unsigned)
        selector
    sub_sel : int (unsigned)
        sub_selector
    prop : int (unsigned)
        component property

    Returns
    -------
    pk : int (unsigned)
        encoded property key
    """
    assert isinstance(sel, (int, long))
    assert isinstance(sub_sel, (int, long))
    assert isinstance(prop, (int, long))
    return lib.SA_EPK(
        ctypes.c_uint(sel), ctypes.c_uint(sub_sel),
        ctypes.c_uint(prop))


def get_channel_property(system_index, channel_index, key):
    """Get a configuration value for a channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    key : int (unsigned)
        encoded property key (see epk & esv)

    Returns
    -------
    return_code : see error_codes
    value : int
        Configuration value
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(key, (int, long))
    v = ctypes.c_int(0)
    check_return(
        lib.SA_GetChannelProperty_S(
            ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
            ctypes.c_uint(key), ctypes.byref(v)))
    return v.value


def set_channel_property(system_index, channel_index, key, value):
    """Set a configuration value for a channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(key, (int, long))
    assert isinstance(value, (int, long))
    check_return(
        lib.SA_SetChannelProperty_S(
            ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
            ctypes.c_uint(key), ctypes.c_int(value)))


def get_dll_version():
    """Get the high, low, and build version number for the libmcscontrol dll

    Returns
    -------
    return_code : see error_codes
    dll_version : int (unsigned)
        bits 31-24 = high
        bits 16-23 = low
        bits 0-15 = build
    """
    v = ctypes.c_uint(0)
    check_return(lib.SA_GetDLLVersion(ctypes.byref(v)))
    # TODO unpack version (31..24 high, 16..23 low, 0..15 build)
    return v.value


def get_number_of_channels(system_index):
    """Get the number of available channels for a given system

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index

    Returns
    -------
    return_code : see error_codes
    n_channels : int (unsigned)
        number of available channels
    """
    assert isinstance(system_index, (int, long))
    n = ctypes.c_uint(0)
    check_return(lib.SA_GetNumberOfChannels(
        ctypes.c_uint(system_index), ctypes.byref(n)))
    return n.value


def open_system(system_locator, options='sync', retries=10, delay=0.1):
    """ Initialize one MCS with some options

    Parameters
    ----------
    system_locator : string
        in the form of <bus>:<address> such as: "usb:id:1234567"
    options : string
        comma-seperated string of the following:
            - reset : MCS is reset on open
            - async/sync : set mode
            - open-timeout <t> : timeout in ms [only for network interfaces]
    retries : int
        attempt to connect retries number of times before failing
    delay : float
        seconds to wait between connection attempts

    Returns
    -------
    system_index : int (unsigned)
        zero-based system index
    """
    assert isinstance(system_locator, (str, unicode))
    assert isinstance(options, (str, unicode))
    for i in xrange(retries):
        system_index = ctypes.c_uint(0)
        r = lib.SA_OpenSystem(
            ctypes.byref(system_index),
            ctypes.c_char_p(system_locator),
            ctypes.c_char_p(options))
        if r == 0:
            break
        time.sleep(delay)
    check_return(r)
    return system_index.value


def close_system(system_index):
    """Close a system by index

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    check_return(lib.SA_CloseSystem(ctypes.c_uint(system_index)))


def find_systems():
    """
    Get a list of available system locators

    Returns
    -------
    return_code : see error_codes
    systems : list of strings
        list of available system locators
    """
    # options: currently unused in spec
    s = ctypes.create_string_buffer(4096)
    i = ctypes.c_uint(4096)
    check_return(
        lib.SA_FindSystems(ctypes.c_char_p(""), s, ctypes.byref(i)))
    return s.value[:i.value].strip().split('\n')


def get_system_locator(system_index):
    """Return a locator string for a given system index

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index

    Returns
    -------
    return_code : see error_codes
    system_locator : string
        system locator string
    """
    assert isinstance(system_index, (int, long))
    s = ctypes.create_string_buffer(4096)
    i = ctypes.c_uint(4096)
    check_return(
        lib.SA_GetSystemLocator(
            ctypes.c_uint(system_index),
            s, ctypes.byref(i)))
    return s.value[:i.value]


def set_hcm_enabled(system_index, enabled):
    """Enable/disable the hand control module

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    enabled : int (unsigned)
        0 = hcm disabled
        1 = hcm enabled
        2 = hcm controls disabled (shows position on lcd)

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(enabled, (int, long))
    # TODO build enabled
    check_return(lib.SA_SetHCMEnabled(
        ctypes.c_uint(system_index), ctypes.c_uint(enabled)))


# == config functions ==
def get_closed_loop_move_acceleration(system_index, channel_index):
    """Get the movement acceleration for a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    accel : int (unsigned)
        acceleration (in um/s**2)
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    accel = ctypes.c_uint(0)
    check_return(lib.SA_GetClosedLoopMoveAcceleration_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(accel)))
    return accel.value


def get_closed_loop_move_speed(system_index, channel_index):
    """Get the movement speed of the given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    speed : int (unsigned)
        in nm/second from 0 to 100,000,000 (0 means speed control is disabled)
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    speed = ctypes.c_uint(0)
    check_return(lib.SA_GetClosedLoopMoveSpeed_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(speed)))
    return speed.value


def get_physical_position_known(system_index, channel_index):
    """Check if the current physical location is known
    (i.e. the reference has been found: see find_reference_mark)

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    known : int (unsigned)
        0 = position unknown
        1 = position known
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    known = ctypes.c_uint(0)
    check_return(lib.SA_GetPhysicalPositionKnown_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(known)))
    # TODO parse known
    return known.value


def get_scale(system_index, channel_index):
    """Get the logical scaling value for a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    scale : int
        scaling value
    inverted : int (unsigned)
        boolean value (0/1) if scale is inverted
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    scale = ctypes.c_int(0)
    inverted = ctypes.c_uint(0)
    check_return(lib.SA_GetScale_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(scale), ctypes.byref(inverted)))
    return scale.value, inverted.value


def set_scale(system_index, channel_index, scale, inverted):
    """Get the logical scaling value for a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    scale : int
        scaling value
    inverted : int (unsigned)
        boolean value (0/1) if scale is inverted

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(scale, (int, long))
    assert isinstance(inverted, (int, long))
    assert inverted in (0, 1)
    check_return(lib.SA_SetScale_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_int(scale), ctypes.c_uint(inverted)))


def get_position_limit(system_index, channel_index):
    """Get the software limits (if set) for a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    min_position : int
        in nm, 0 if no limit
    max_position : int
        in nm, 0 if no limit
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    min_p = ctypes.c_int(0)
    max_p = ctypes.c_int(0)
    check_return(lib.SA_GetPositionLimit_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(min_p), ctypes.byref(max_p)))
    return min_p.value, max_p.value


def get_safe_direction(system_index, channel_index):
    """Get the safe direction for calibrating sensors with end stops
    Has no effect on sensors with reference marks

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    direction : int (unsigned)
        0 = forward
        1 = backward
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    d = ctypes.c_uint(0)
    check_return(lib.SA_GetSafeDirection_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(d)))
    return d.value


def get_sensor_enabled(system_index):
    """Check if sensors are enabled for a given system

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index

    Returns
    -------
    return_code : see error_codes
    enabled : int (unsigned)
        0 = disabled
        1 = enabled
        2 = powersave
    """
    assert isinstance(system_index, (int, long))
    e = ctypes.c_uint(0)
    check_return(lib.SA_GetSensorEnabled_S(
        ctypes.c_uint(system_index), ctypes.byref(e)))
    # TODO parse enabled
    return e.value


def get_sensor_type(system_index, channel_index):
    """Get the sensor type (or lack of sensor) for a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    sensor_type : int (unsigned)
        see sensor_type_codes/strings
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    t = ctypes.c_uint(0)
    check_return(lib.SA_GetSensorType_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(t)))
    # TODO parse sensor type
    return t.value


def set_accumulate_relative_positions(system_index, channel_index, accumulate):
    """Set if relative closed-loop movements should accumulate.
    This has an effect if a relative movement is sent during an
    ongoing relative movement. See docs for more info

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    accumulate : int (unsigned)
        0 = don't accumulate positions
        1 = accumulate positions

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(accumulate, (int, long))
    # TODO parse accumulate
    check_return(lib.SA_SetAccumulateRelativePositions_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(accumulate)))


def set_closed_loop_max_frequency(system_index, channel_index, frequency):
    """Set the update frequency for closed-loop movements

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    frequency : int (unsigned)
        driving frequency in Hz, range = 50 - 18500

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(frequency, (int, long))
    assert ((frequency > 49) and (frequency < 18501))
    check_return(lib.SA_SetClosedLoopMaxFrequency_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(frequency)))


def set_closed_loop_move_acceleration(system_index, channel_index, accel):
    """Set the movement acceleration for closed-loop movements.

    Not available on all controllers!

    By default this is disabled and max frequency is used
    (see set_closed_loop_max_frequency). Note that the control speed
    may not be reqched if max frequency is too low.

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    accel : int (unsigned)
        in nm/second, range = 0 - 10000000 (0 deactivates speed control)

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(accel, (int, long))
    assert ((accel > -1) and (accel < 10000001))
    check_return(lib.SA_SetClosedLoopMoveAcceleration_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(accel)))


def set_closed_loop_move_speed(system_index, channel_index, speed):
    """Set the movement speed for closed-loop movements.
    By default this is disabled and max frequency is used
    (see set_closed_loop_max_frequency). Note that the control speed
    may not be reqched if max frequency is too low.

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    speed : int (unsigned)
        in nm/second, range = 0 - 100000000 (0 deactivates speed control)

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(speed, (int, long))
    assert ((speed > -1) and (speed < 100000001))
    check_return(lib.SA_SetClosedLoopMoveSpeed_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(speed)))


def set_position(system_index, channel_index, position):
    """Assign a new value to the current physical position.
    Does not produce movement

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    position : int
        new value for the current position

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(position, (int, long))
    check_return(lib.SA_SetPosition_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_int(position)))


def set_position_limit(system_index, channel_index,
                       min_position, max_position):
    """Set the soft limits of a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    min_position : int
        in nm
    max_position : int
        in nm

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(min_position, (int, long))
    assert isinstance(max_position, (int, long))
    check_return(lib.SA_SetPositionLimit_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_int(min_position), ctypes.c_int(max_position)))


def set_safe_direction(system_index, channel_index, direction):
    """Set the safe direction for calibrating sensors with end stops
    Has no effect on sensors with reference marks

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    direction : int (unsigned)
        0 = forward
        1 = backward

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(direction, (int, long))
    # TODO parse direction
    check_return(lib.SA_SetSafeDirection_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(direction)))


def set_sensor_enabled(system_index, enabled):
    """Enable/disable sensors for a given system

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    enabled : int (unsigned)
        0 = disabled
        1 = enabled
        2 = powersave

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(enabled, (int, long))
    # TODO parse enabled
    check_return(lib.SA_SetSensorEnabled_S(
        ctypes.c_uint(system_index), ctypes.c_uint(enabled)))


def set_sensor_type(system_index, channel_index, sensor_type):
    """Set the sensor type (or lack of sensor) for a given channel
    This is stored in non-volatile memory.

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    sensor_type : int (unsigned)
        see sensor_type_codes/strings

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(sensor_type, (int, long))
    # TODO parse sensor_type
    check_return(lib.SA_SetSensorType_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(sensor_type)))


def set_step_while_scan(system_index, channel_index, step):
    """Set option to enable/disable stepping to maintain a position
    during closed-loop motions.

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    step : int (unsigned)
        0 = no step while scan
        1 = step while scan

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(step, (int, long))
    # TODO parse step
    check_return(lib.SA_SetStepWhileScan_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(step)))


def get_angle_limit(system_index, channel_index):
    """Get the soft angular limits for a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    min_angle : int (unsigned)
        in micro-degrees
    min_revolution : int
        in 360 degree increments
    max_angle : int (unsigned)
        in micro-degrees
    max_revolution : int
        in 360 degree increments
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    min_angle = ctypes.c_uint(0)
    min_rev = ctypes.c_int(0)
    max_angle = ctypes.c_uint(0)
    max_rev = ctypes.c_int(0)
    check_return(lib.SA_GetAngleLimit_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(min_angle), ctypes.byref(min_rev),
        ctypes.byref(max_angle), ctypes.byref(max_rev)))
    return min_angle.value, min_rev.value, max_angle.value, max_rev.value


# == movement functions ==
def calibrate_sensor(system_index, channel_index):
    """Calibrate a sensor for a given channel.
    Result is stored in non-volatile memory.

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    check_return(lib.SA_CalibrateSensor_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index)))


def find_reference_mark(system_index, channel_index,
                        direction, hold_time, auto_zero):
    """Move the positioner to the reference mark

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    direction : int (unsigned)
        the initial search direction
        0 = forward
        1 = backward
    hold_time : int (unsigned)
        how long to hold (in ms) at the reference point
        0 (disabled) - 60000 (infinite, until stop is called)
    auto_zero : int (unsigned)
        set the reference mark position to 0
        0 = no auto zero
        1 = auto zero

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(direction, (int, long))
    assert isinstance(hold_time, (int, long))
    assert isinstance(auto_zero, (int, long))
    # TODO parse options
    check_return(lib.SA_FindReferenceMark_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(direction), ctypes.c_uint(hold_time),
        ctypes.c_uint(auto_zero)))


def goto_position_absolute(system_index, channel_index, position, hold_time):
    """Move to an absolute position.
    Only usable with sensor-attached positioners

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    position : int
        in nm
    hold_time : int (unsigned)
        how long to hold (in ms) at the reference point
        0 (disabled) - 60000 (infinite, until stop is called)

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(position, (int, long))
    assert isinstance(hold_time, (int, long))
    assert ((hold_time > -1) and (hold_time < 60001))

    check_return(lib.SA_GotoPositionAbsolute_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_int(position), ctypes.c_uint(hold_time)))


def goto_position_relative(system_index, channel_index, diff, hold_time):
    """Move to an relative position.
    Only usable with sensor-attached positioners

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    diff : int
        in nm
    hold_time : int (unsigned)
        how long to hold (in ms) at the reference point
        0 (disabled) - 60000 (infinite, until stop is called)

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(diff, (int, long))
    assert isinstance(hold_time, (int, long))
    assert ((hold_time > -1) and (hold_time < 60001))

    check_return(lib.SA_GotoPositionRelative_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_int(diff), ctypes.c_uint(hold_time)))


def scan_move_absolute(system_index, channel_index, target, speed):
    """Directly control the piezo to an absolute position

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    target : int (unsigned)
        scan voltage, range = 0 - 4095 [0 - 100 Volts]
    speed : int (unsigned)
        scan speed in units (see target) per second

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(target, (int, long))
    assert isinstance(speed, (int, long))
    assert ((target > -1) and (target < 4096))
    check_return(lib.SA_ScanMoveAbsolute_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_uint(target), ctypes.c_uint(speed)))


def scan_move_relative(system_index, channel_index, diff, speed):
    """Directly control the piezo to an relative position

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    diff : int (unsigned)
        scan voltage, range = -4095 - 4095 [see scan_move_absolute]
    speed : int (unsigned)
        scan speed in units (see target) per second

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(diff, (int, long))
    assert isinstance(speed, (int, long))
    assert ((diff > -4096) and (diff < 4096))
    check_return(lib.SA_ScanMoveRelative_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_int(diff), ctypes.c_uint(speed)))


def step_move(system_index, channel_index, steps, amplitude, frequency):
    """Open-loop command to move a certain number of steps

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index
    steps : int
        number (and direction) of steps, range = -30000 - 30000
        0 = stop positioner
        -30000/30000 = unbounded move
    amplitude : int (unsigned)
        width (voltage) of step, range = 0 - 4095 [0 - 100 Volts]
    frequency : int (unsigned)
        in Hz, range = 1 - 18500

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    assert isinstance(steps, (int, long))
    assert isinstance(amplitude, (int, long))
    assert isinstance(frequency, (int, long))
    assert ((steps > -30001) and (steps < 30001))
    assert ((amplitude > -1) and (amplitude < 4096))
    assert ((frequency > 0) and (frequency < 18501))
    check_return(lib.SA_StepMove_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.c_int(steps), ctypes.c_uint(amplitude),
        ctypes.c_uint(frequency)))


def stop(system_index, channel_index):
    """Stops the movmement (or hold) of a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    check_return(lib.SA_Stop_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index)))


# == feedback functions ==
def get_angle(system_index, channel_index):
    """Get the current angle of a rotary positioner

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    angle : int (unsigned)
        in micro degrees
    revolution : int
        in 360 degree increments
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    angle = ctypes.c_uint(0)
    revolution = ctypes.c_int(0)
    check_return(lib.SA_GetAngle_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(angle), ctypes.byref(revolution)))
    return angle.value, revolution.value


def get_position(system_index, channel_index):
    """Get the current position of a linear positioner

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    position : int
        in nm
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    p = ctypes.c_int(0)
    check_return(lib.SA_GetPosition_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(p)))
    return p.value


def get_status(system_index, channel_index):
    """Get the status of a given channel

    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    status_code : see status_codes/strings
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    s = ctypes.c_uint(0)
    check_return(lib.SA_GetStatus_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(s)))
    # TODO parse status code
    return s.value


def get_voltage_level(system_index, channel_index):
    """Get the voltage level of a given channel
    Parameters
    ----------
    system_index : int (unsigned)
        zero-based system index
    channel_index : int (unsigned)
        zero-based channel index

    Returns
    -------
    return_code : see error_codes
    voltage_level : int (unsigned)
        current voltage, range 0 - 4095 [0 - 100 Volts]
    """
    assert isinstance(system_index, (int, long))
    assert isinstance(channel_index, (int, long))
    l = ctypes.c_uint(0)
    check_return(lib.SA_GetVoltageLevel_S(
        ctypes.c_uint(system_index), ctypes.c_uint(channel_index),
        ctypes.byref(l)))
    return l.value
