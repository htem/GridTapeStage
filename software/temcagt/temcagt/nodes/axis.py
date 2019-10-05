#!/usr/bin/env python

import time
import warnings

from .. import log


logger = log.get_logger(__name__)
position_poll_pause = 0.005


class Axis(object):
    def __init__(self, controller):
        self._controller = controller
        self._position = 0.

    def connect(self):
        return self._controller.connect()

    def disconnect(self):
        return self._controller.disconnect()

    @property
    def connected(self):
        return self._controller.connected

    @property
    def moving(self):
        raise NotImplementedError("abstract base class")

    def wait(self):
        while self.moving:
            time.sleep(position_poll_pause)

    def position(self, wait=True):
        raise NotImplementedError("abstract base class")

    def set_position(self, value=0):
        self._position = value

    def calibrate(self):
        pass

    def move_absolute(self, value):
        raise NotImplementedError("abstract base class")

    def move_relative(self, value):
        raise NotImplementedError("abstract base class")

    def configure(self, config):
        raise NotImplementedError("abstract base class")

    def __del__(self):
        # let the controller handle disconnecting
        del self._controller


class AsyncSmaractAxis(Axis):
    """
    configure
    position (with return)
    set_position
    wait
    move_relative
    move_absolute
    """
    def __init__(self, controller, axis):
        super(AsyncSmaractAxis, self).__init__(controller)
        self._axis = axis
        self._zero = 0.
        # TODO check position known
        if not self._controller.physical_known(self._axis):
            self._calibrated = False
            self.wait()
            self._nocal_position = self._controller.position(self._axis)
        else:
            self._calibrated = True

    @property
    def moving(self):
        return self._controller.moving(self._axis)
        #return self._controller.status(self._axis) != 0

    def wait(self):
        # TODO this is a possible infinite loop
        # the problem occurs when movement fails
        # this needs to be handled more gracefully
        while self.moving:
            time.sleep(position_poll_pause)

    def set_position(self, value=0):
        logger.debug("AsyncSmaractAxis[%s] set_position %s", self, value)
        self._zero = 0.
        rp = self.position(wait=True)
        self._zero = rp - value
        logger.debug(
            "AsyncSmaractAxis[%s] set_position zero = %s", self, self._zero)

    def calibrate(self):
        self._controller.calibrate(self._axis)

    def position(self, wait=True):
        if wait:
            self.wait()
        rp = self._controller.position(self._axis)
        if wait:
            self._nocal_position = rp
        return rp - self._zero

    def move_absolute(self, value):
        logger.debug(
            "AsyncSmaractAxis[%s] move_absolute %s[%s]",
            self, value, self._calibrated)
        value += self._zero
        if self._calibrated:
            self._controller.move_absolute(self._axis, int(value), 60000)
        else:
            self.move_relative(value - self._nocal_position)

    def move_relative(self, value):
        logger.debug(
            "AsyncSmaractAxis[%s] move_relative %s[%s]",
            self, value, self._calibrated)
        self._controller.move_relative(self._axis, int(value), 60000)
        if not self._calibrated:
            self._nocal_position += value

    def configure(self, config):
        logger.debug("AsyncSmaractAxis[%s] configure %s", self, config)
        for k in config:
            getattr(self._controller, k)(self._axis, config[k])


class SmaractAxis(Axis):
    def __init__(self, controller, axis):
        super(SmaractAxis, self).__init__(controller)
        # TODO make this configurable
        self._axis = axis
        self._zero = 0.
        # TODO check calibration at other points (not just __init__)?
        if not self._controller.physical_known(self._axis):
            self._calibrated = False
            # used to track position when not calibrated
            self.wait()
            self._nocal_position = self._controller.position(self._axis)
            #self._nocal_position = 0.
        else:
            self._calibrated = True

    @property
    def moving(self):
        return self._controller.status(self._axis) != 0

    def set_position(self, value=0):
        logger.debug("SmaractAxis[%s] set_position %s", self, value)
        self._zero = 0.
        rp = self.position(wait=True)
        self._zero = rp - value
        logger.debug(
            "SmaractAxis[%s] set_position zero = %s", self, self._zero)

    def calibrate(self):
        self._controller.calibrate(self._axis)

    def position(self, wait=True):
        if wait:
            self.wait()
        rp = self._controller.position(self._axis)
        if wait:
            self._nocal_position = rp  # store an updated _nocal_position
        return rp - self._zero

    def move_absolute(self, value):
        logger.debug("SmaractAxis[%s] move_absolute %s", self, value)
        # offset value by z
        value += self._zero
        if self._calibrated:
            self._controller.move_absolute(self._axis, int(value))
        else:
            self.move_relative(value - self._nocal_position)

    def move_relative(self, value):
        logger.debug("SmaractAxis[%s] move_relative %s", self, value)
        self._controller.move_relative(self._axis, int(value))
        if not self._calibrated:
            self._nocal_position += value

    def configure(self, config):
        logger.debug("SmaractAxis[%s] configure %s", self, config)
        for k in config:
            getattr(self._controller, k)(self._axis, config[k])
