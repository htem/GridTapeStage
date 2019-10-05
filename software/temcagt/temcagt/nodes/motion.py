#!/usr/bin/env python
"""
"""

import os

import pizco
import smaract

from . import base
from ..config.checkers import require
from .. import log


default_config = {
    'addr': 'tcp://127.0.0.1:11010',
    'loc': 'fake',
    #'fakeslot': {
    #    'enable': True,
    #    'fakefile': '~/.temcagt/fake/camera',
    #    'x_range': [-1000000, 1000000],
    #    'y_range': [-750000, 750000],
    #},
    'x': {
        'axis': 1,
        #'zero': None,
        'cfg': {
            'max_frequency': 2000,
        },
    },
    'y': {
        'axis': 0,
        #'zero': None,
        'cfg': {
            'max_frequency': 2000,
        },
    },
    'cfg': {
        'sensor_enabled': 1,
    }
}


logger = log.get_logger(__name__)


class MotionNode(base.IONode):
    def __init__(self, cfg=None):
        base.IONode.__init__(self, cfg)
        self._locked = False  # software lock to prevent movement
        self._controller = None
        # setup axes (only on creation)
        self._axes = {}
        for chn in ('x', 'y'):
            if chn in cfg:
                self._axes[chn] = cfg[chn]['axis']
        self.new_position = pizco.Signal(nargs=1)

    def __repr__(self):
        cfg = self.config()
        return "{}.{} at {} addr {} loc {}".format(
            self.__module__, self.__class__, hex(id(self)),
            cfg.get('addr', ''), cfg.get('loc', ''))

    def check_config(self, cfg=None):
        if cfg is None:
            cfg = self.config()
        [require(cfg, k) for k in
            'loc x y'.split()]

    def config_delta(self, delta):
        if not self.connected():
            return
        logger.info("MotionNode[%s] config_delta %s", self, delta)
        if 'loc' in delta:
            self.disconnect()
            self.connect()
            return  # everything else gets set in connect
        for chn in ('x', 'y'):
            if chn not in delta:
                continue
            chcfg = delta[chn]
            if 'axis' in chcfg:
                raise ValueError(
                    "Invalid configuration change: %s: %s" % (chn, chcfg))
        self._configure_controller(delta)

    def connect(self):
        if self.connected():
            logger.warning(
                "MotionNode[%s]: Attempt to connect already connected",
                self)
            return
        self.check_config()
        cfg = self.config()
        logger.debug("MotionNode[%s] creating MCS at %s", self, cfg['loc'])
        # get number and index of channels, order by x y
        channels = []
        for chn in ('x', 'y'):
            if chn in cfg:
                channels.append(cfg[chn]['axis'])
        if cfg['loc'] == 'fake':
            self._controller = smaract.FakeBMCS(cfg['loc'], channels=channels)
            self._write_position = self._write_position_faked
            self._x = 0
            self._y = 0
        else:
            self._controller = smaract.BMCS(cfg['loc'], channels=channels)
        self._configure_controller(cfg)
        logger.info("MotionNode[%s] connected to %s", self, cfg['loc'])

    def disconnect(self):
        if not self.connected():
            logger.warning(
                "MotionNode[%s]: Attempt to disconnect already disconnected",
                self)
            return
        self._controller.set_sensor_enabled(2)
        self._controller.stop()
        self._controller.disconnect()
        self._controller = None
        logger.info("MotionNode[%s] disconnected")

    def connected(self):
        return self._controller is not None

    def lock(self):
        self._locked = True

    def unlock(self):
        self._locked = False

    def is_locked(self):
        return self._locked

    def _configure_controller(self, cfg):
        logger.info("MotionNode[%s] _configure_controller: %s" % (self, cfg))
        # setup base config
        if 'cfg' in cfg:
            for k in cfg['cfg']:
                v = cfg['cfg'][k]
                a = 'set_' + k
                getattr(self._controller, a)(v)
        # setup each axis config
        for chn in ('x', 'y'):
            if chn in cfg and 'cfg' in cfg[chn]:
                c = cfg[chn]['cfg']
                ax = self._axes[chn]
                for k in c:
                    v = c[k]
                    a = 'set_' + k
                    getattr(self._controller, a)(ax, v)

    def wait_till_moved(self):
        if not self.connected:
            msg = 'Attempt to wait_till_moved when un-connected'
            logger.error(msg)
            raise IOError(msg)
        logger.debug("MotionNode[%s] wait_till_moved", self)
        self._controller.wait()

    #def _to_machine_position(self, axis, value):
    #    if value is None:
    #        return value
    #    cfg = self.config()
    #    z = cfg[axis].get('zero', None)
    #    if z is None:
    #        # no offset was set
    #        return int(value)
    #    # value is a ui defined position
    #    return int(value + z)

    #def _from_machine_position(self, axis, value):
    #    if value is None:
    #        return value
    #    cfg = self.config()
    #    z = cfg[axis].get('zero', None)
    #    if z is None:
    #        # no offset was set
    #        return value
    #    # value is a machine defined position
    #    return value - z

    #def return_to_machine_coordinates(self, x=True, y=True):
    #    logger.debug(
    #        "MotionNode[%s] return_to_machine_coordinates: %s, %s",
    #        self, x, y)
    #    if x:
    ##        self.config({'x': {'zero': None}})
    #    if y:
    #        self.config({'y': {'zero': None}})

    #def set_position(self, x=None, y=None):
    #    """
    #    Set the current position (which will be read) to some values (x, y)
    #    """
    #    logger.debug("MotionNode[%s] set_position: %s, %s", self, x, y)
    #    if x is None and y is None:
    #        return
    #    r = self.poll_position(wait=True, machine=True)
    #    if x is not None:
    #        # r['x'] is the current machine position
    #        self.config({'x': {'zero': r['x'] - x}})
    #    if y is not None:
    #        # r['y'] is the current machine position
    #        self.config({'y': {'zero': r['y'] - y}})

    def calibrate(self, axis=0):
        if not self.connected:
            msg = 'Attempt to calibrate when un-connected'
            logger.error(msg)
            raise IOError(msg)
        if self._locked:
            msg = 'Attempt to move locked stage'
            logger.error(msg)
            raise IOError(msg)
        logger.debug("MotionNode[%s] calibrate: %s", self, axis)
        axis = self._axes.get(axis, axis)
        self._controller.calibrate(axis)
        self.wait_till_moved()
        self.poll_position(wait=True)

    def calibrated(self, axis=None):
        if axis is None:
            return {axis: self.calibrated(axis) for axis in self._axes}
        axis = self._axes.get(axis, axis)
        return self._controller.get_physical_known(axis)

    def find_ref(self, axis=0):
        if not self.connected:
            msg = 'Attempt to find_ref when un-connected'
            logger.error(msg)
            raise IOError(msg)
        if self._locked:
            msg = 'Attempt to move locked stage'
            logger.error(msg)
            raise IOError(msg)
        logger.debug("MotionNode[%s] find_ref: %s", self, axis)
        axis = self._axes.get(axis, axis)
        self._controller.find_ref(axis)
        self.wait_till_moved()
        self.poll_position(wait=True)

    #def poll_position(self, wait=True, machine=False):
    def poll_position(self, wait=True):
        if not self.connected:
            msg = 'Attempt to poll_position when un-connected'
            logger.error(msg)
            raise IOError(msg)
        logger.debug("MotionNode[%s] poll_position", self)
        if wait:
            self.wait_till_moved()
        self._controller.poll_position(self._axes['x'], flush=False)
        self._controller.poll_position(self._axes['y'], flush=False)
        self._controller.flush()
        x = self._controller.last_position(self._axes['x'])
        y = self._controller.last_position(self._axes['y'])
        r = {'x': x, 'y': y}
        #if machine:
        #    r = {'x': x, 'y': y, 'system': 'machine'}
        #else:
        #    r = {
        #        'x': self._from_machine_position('x', x),
        #        'y': self._from_machine_position('y', y),
        #        'system': 'ui',
        #    }
        #r = dict([(k, self._axes[k].position(wait=wait)) for k in self._axes])
        logger.debug("MotionNode[%s] new_position %s", self, r)
        self.new_position.emit(r)
        return r

    #def _write_position(self, x, y, relative, machine):
    def _write_position(self, x, y, relative):
        return

    #def _write_position_faked(self, x, y, relative, machine):
    def _write_position_faked(self, x, y, relative):
        cfg = self.config()
        if not cfg.get('fakeslot', {}).get('enable', False):
            return
        #if machine:
        #    raise Exception(
        #        "Machine coordinates not supported for fake motion node")
        if x is None:
            x = self._x
        else:
            if relative:
                x = self._x + x
        if y is None:
            y = self._y
        else:
            if relative:
                y = self._y + y
        self._x = x
        self._y = y

        # check slot bounds
        xr = cfg['fakeslot']['x_range']
        yr = cfg['fakeslot']['y_range']
        blank = False
        if self._x < xr[0] or self._x > xr[1]:
            blank = True
        if self._y < yr[0] or self._y > yr[1]:
            blank = True

        # write out blanking file
        fn = os.path.abspath(os.path.expanduser(cfg['fakeslot']['fakefile']))
        d = os.path.dirname(fn)
        if not os.path.exists(d):
            os.makedirs(d)
        if blank:
            with open(fn, 'w') as f:
                f.write('0')
        else:
            if os.path.exists(fn):
                os.remove(fn)

    #def move(self, x=None, y=None, wait=False, relative=False,
    #         poll=True, machine=False, hold=0):
    def move(self, x=None, y=None, wait=False, relative=False,
             poll=True, hold=0, retries=5):
        if not self.connected:
            msg = 'Attempt to move when un-connected'
            logger.error(msg)
            raise IOError(msg)
        if self._locked:
            msg = 'Attempt to move locked stage'
            logger.error(msg)
            raise IOError(msg)
        #logger.debug("MotionNode[%s] move, %s", self,
        #             (x, y, wait, relative, poll, machine, hold))
        logger.debug("MotionNode[%s] move, %s", self,
                     (x, y, wait, relative, poll, hold))
        #self._write_position(x, y, relative, machine)
        self._write_position(x, y, relative)
        if relative:
            if x is not None:
                self._controller.move_relative(
                    self._axes['x'], int(x), hold_time=hold, flush=False)
            if y is not None:
                self._controller.move_relative(
                    self._axes['y'], int(y), hold_time=hold, flush=False)
        else:
            mx = x
            my = y
            #if machine:
            #    mx = x
            #    my = y
            #else:
            #    mx = self._to_machine_position('x', x)
            #    my = self._to_machine_position('y', y)
            if x is not None:
                self._controller.move_absolute(
                    self._axes['x'], int(mx), hold_time=hold, flush=False)
            if y is not None:
                self._controller.move_absolute(
                    self._axes['y'], int(my), hold_time=hold, flush=False)
        self._controller.flush()
        try:
            if poll:
                return self.poll_position(wait=True)
            if wait:
                self.wait_till_moved()
        except smaract.async.EndStopError as e:
            if retries:
                logger.error(
                    "EndStopError[%s] %s %s %s %s %s %s %s",
                    e, x, y, wait, relative, poll, hold, retries)
                # retry movement and decrease retries
                return self.move(
                    x=x, y=y, wait=wait, relative=relative,
                    poll=poll, hold=hold, retries=retries - 1)
            else:
                raise e
        return


def test_node(config):
    n = MotionNode(config)
    n.connect()
    n.disconnect()

if __name__ == '__main__':
    #serve(config)
    test_node(default_config)
