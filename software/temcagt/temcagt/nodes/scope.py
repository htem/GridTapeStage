#!/usr/bin/env python
"""
Placeholder for scope node

Connections:
    From:
        control node: setup beam parameters

Inputs:
    set scope parameters
        focus
        brightness
        shift X/Y
        mag changes
        objective aperature

Outputs:
    report scope errors
        vacuum fault
        lens fault (drift)
        scope cpu fault
"""
import copy
import os
import time

import pizco
import tornado.ioloop

import pyjeol

from . import base
from ..config.checkers import require
from .. import log


default_config = {
    'addr': 'tcp://127.0.0.1:11070',
    'loc': 'fake',
    'button_delay': 0.15,
    'knob_delay': 0.2,
    'screen_delay': 5.0,
    #'loc': '/dev/ttyACM0:/dev/ttyACM1',
    #'update_rate': 100,  # Hz
    #'autostart': True,  # start auto-updating on connect
    # number of 16x clicks right to widen beam from crossover
    'n_16x_clicks_to_widen': 30,
}


logger = log.get_logger(__name__)


class ScopeNode(base.IONode):
    def __init__(self, cfg=None):
        base.IONode.__init__(self, cfg)
        self._scope = None
        self.response_signal = pizco.Signal(nargs=1)

    def _from_left_panel(self, m):
        mc = copy.deepcopy(m)
        mc['side'] = 'left'
        self.response_signal.emit(mc)

    def _from_right_panel(self, m):
        mc = copy.deepcopy(m)
        mc['side'] = 'right'
        self.response_signal.emit(mc)

    def __repr__(self):
        cfg = self.config()
        return "{}.{} at {} addr {} loc {}".format(
            self.__module__, self.__class__, hex(id(self)),
            cfg.get('addr', ''), cfg.get('loc', ''))

    def check_config(self, cfg=None):
        if cfg is None:
            cfg = self.config()
        #[require(cfg, k) for k in
        #    'loc x y'.split()]

    def connect(self):
        if self.connected():
            logger.warning(
                "ScopeNode[%s]: Attempt to connect already connected",
                self)
            return
        self.check_config()
        cfg = self.config()
        if cfg['loc'] == 'fake':
            self._scope = FakeScope()
        else:
            p0, p1 = cfg['loc'].split(':')
            self._scope = pyjeol.JEOL1200EX1(p0, p1)
            self.loop.add_handler(
                self._scope.left_panel._conn.fileno(),
                lambda fd, ev, o=self._scope.left_panel: o.update(),
                tornado.ioloop.IOLoop.READ)
            self.loop.add_handler(
                self._scope.right_panel._conn.fileno(),
                lambda fd, ev, o=self._scope.right_panel: o.update(),
                tornado.ioloop.IOLoop.READ)
        for k in ('l', 'd'):
            self._scope.attach_callback(self._from_left_panel, k, 'L')
            self._scope.attach_callback(self._from_right_panel, k, 'R')
        #if cfg['autostart'] and cfg['loc'] != 'fake':
        #    self.start_updating()
        logger.info("ScopeNode[%s] connected to %s", self, cfg['loc'])

    def disconnect(self):
        if not self.connected():
            logger.warning(
                "ScopeNode[%s]: Attempt to disconnect already disconnected",
                self)
            return
        self.loop.remove_handler(self._scope.left_panel._conn.fileno())
        self.loop.remove_handler(self._scope.right_panel._conn.fileno())
        self._scope.disconnect()
        del self._scope
        self._scope = None

    def connected(self):
        return self._scope is not None

    def get_lights(self, by_side=True):
        if not self.connected():
            logger.warning(
                "ScopeNode[%s]: Attempt to get_lights on unconnected node",
                self)
        self._scope.update()
        return self._scope.get_lights(by_side=by_side)

    def press_button(self, name, wait=True):
        if not self.connected():
            logger.warning(
                "ScopeNode[%s]: Attempt to press_button on unconnected node",
                self)
        logger.debug("ScopeNode[%s]: press_button %s" % (self, name))
        self._scope.press_button(name)
        if wait:
            if wait is True:
                wait = self.config()['button_delay']
            time.sleep(wait)
            self._scope.update()

    def turn_knob(self, name, direction, wait=True):
        if not self.connected():
            logger.warning(
                "ScopeNode[%s]: Attempt to turn_knob on unconnected node",
                self)
        logger.debug(
            "ScopeNode[%s]: turn_knob %s, %s" % (self, name, direction))
        self._scope.turn_knob(name, direction)
        if wait:
            if wait is True:
                wait = self.config()['knob_delay']
            time.sleep(wait)

    def adjust_focus(self, n_clicks, coarse=False, x16=False):
        if not self.connected():
            logger.warning(
                "ScopeNode[%s]: Attempt to adjust_focus "
                "on unconnected node",
                self)
        logger.debug(
            "ScopeNode[%s]: adjust_focus %s, %s, %s" %
            (self, n_clicks, coarse, x16))
        if n_clicks == 0:
            return
        if x16 ^ ('obj16x' in self.get_lights(by_side=False)):
            #self.press_button('obj16x')
            logger.warning("ScopeNode[%s]: retrying obj16x button", self)
            n_retries = 10
            while x16 ^ ('obj16x' in self.get_lights(by_side=False)):
                self.press_button('obj16x')
                n_retries -= 1
                if n_retries < 1:
                    raise IOError("Failed to set obj16x button")
        knob_name = 'cfocus' if coarse else 'ffocus'
        direction = 'r' if n_clicks > 0 else 'l'
        for _ in xrange(abs(n_clicks)):
            self.turn_knob(knob_name, direction)

    def adjust_brightness(self, n_clicks, direction, x16=False):
        if not self.connected():
            logger.warning(
                "ScopeNode[%s]: Attempt to adjust_brightness "
                "on unconnected node",
                self)
        logger.debug(
            "ScopeNode[%s]: adjust_brightness %s, %s, %s" %
            (self, n_clicks, direction, x16))
        if x16 ^ ('bright16x' in self.get_lights(by_side=False)):
            #self.press_button('bright16x')
            logger.warning("ScopeNode[%s]: retrying bright16x button", self)
            n_retries = 10
            while x16 ^ ('bright16x' in self.get_lights(by_side=False)):
                self.press_button('bright16x')
                n_retries -= 1
                if n_retries < 1:
                    raise IOError("Failed to set bright16x button")
        for _ in xrange(n_clicks):
            self.turn_knob('brightness', direction)

    def widen_beam(self, n_clicks=None):
        if not self.connected():
            logger.warning(
                "ScopeNode[%s]: Attempt to widen_beam on unconnected node",
                self)
        if n_clicks is None:
            n_clicks = self.config()['n_16x_clicks_to_widen']
        logger.debug("ScopeNode[%s]: widen_beam %s" % (self, n_clicks))
        self.adjust_brightness(n_clicks, 'r', x16=True)

    def screen_is_open(self):
        return 'screen' in self.get_lights(by_side=False)


class FakeScope(object):
    def __init__(self):
        self._lights = {
            pyjeol.consts.SIDE_RIGHT: [],
            pyjeol.consts.SIDE_LEFT: []}
        self._cbid = 0
        self._callbacks = {
            pyjeol.consts.SIDE_RIGHT: {},
            pyjeol.consts.SIDE_LEFT: {}}

    def disconnect(self):
        pass

    def update(self):
        pass

    def attach_callback(self, cb, key, side=None):
        cbids = []
        if side in ('r', 'R', 'right'):
            side = pyjeol.consts.SIDE_RIGHT
        if side in ('l', 'L', 'left'):
            side = pyjeol.consts.SIDE_LEFT
        if side is None or side == pyjeol.consts.SIDE_RIGHT:
            if key not in self._callbacks[pyjeol.consts.SIDE_RIGHT]:
                self._callbacks[pyjeol.consts.SIDE_RIGHT][key] = {}
            cbid = self._cbid
            self._cbid += 1
            cbids.append(cbid)
            self._callbacks[pyjeol.consts.SIDE_RIGHT][key][cbid] = cb
        if side is None or side == pyjeol.consts.SIDE_LEFT:
            if key not in self._callbacks[pyjeol.consts.SIDE_LEFT]:
                self._callbacks[pyjeol.consts.SIDE_LEFT][key] = {}
            cbid = self._cbid
            self._cbid += 1
            cbids.append(cbid)
            self._callbacks[pyjeol.consts.SIDE_LEFT][key][cbid] = cb
        if len(cbids) == 1:
            return cbids[0]
        return cbids

    def get_lights(self, by_side=False):
        if by_side:
            return {
                'left': self._lights[pyjeol.consts.SIDE_LEFT],
                'right': self._lights[pyjeol.consts.SIDE_RIGHT],
            }
        return (
            self._lights[pyjeol.consts.SIDE_LEFT] +
            self._lights[pyjeol.consts.SIDE_RIGHT])

    def _toggle_light(self, side, name):
        ls = self._lights[side]
        msg = {'value': name}
        if name not in ls:
            ls.append(name)
            msg['key'] = 'l'
            msg['name'] = 'light_on'
        else:
            ls.remove(name)
            msg['key'] = 'd'
            msg['name'] = 'light_off'
        cbs = self._callbacks.get(side, {}).get(msg['key'], {})
        for cb in cbs.values():
            cb(msg)

    def press_button(self, name):
        s = pyjeol.consts.BUTTON_SIDES[name]
        if s == pyjeol.consts.SIDE_RIGHT:
            self._toggle_light(pyjeol.consts.SIDE_RIGHT, name)
        elif s == pyjeol.consts.SIDE_LEFT:
            self._toggle_light(pyjeol.consts.SIDE_LEFT, name)

    def turn_knob(self, name, direction):
        pass
