#!/usr/bin/env python

import os
import time

from ... import base
from .... import config
from .... import log
from .. import notification


logger = log.get_logger('temcagt.nodes.control.node')


def save_all_configs(node):
    # save current config(s) to .temcagt/makesafes/<timestamp>/...
    t = time.localtime()
    ts = time.strftime('%y%m%d%H%M%S', t)
    dn = os.path.expanduser('~/.temcagt/makesafes/%s' % ts)
    os.makedirs(dn)
    config.parser.save(node.config(), '%s/control.json' % dn)
    for n in ('scope', 'tape', 'tapecamera', 'compute', 'motion'):
        config.parser.save(
            getattr(node, n).config(), '%s/%s.json' % (dn, n))
    for (i, c) in enumerate(node.cameras):
        config.parser.save(c.config(), '%s/camera_%i.json' % (dn, i))


class MakeSafeSM(base.StateMachine):
    """
    this can get called with a partially connected node
    so verify connection of parts before using them

    move to stage to 'safe' spot?
    widen beam

    wait till move is done
    """
    def setup(self):
        cfg = self.node.config()
        mscfg = cfg['make_safe']

        if not self.node.scope.connected():
            # if the scope is not connected, send critical error
            notification.send_notification(
                self.node, 'make_safe',
                scope_not_connected=True)
            # and try to reconnect
            self.node.scope.connect()
        # widen beam 30 16x clicks
        self.node.scope.widen_beam()
        #if 'bright16x' not in self.node.scope.get_lights(by_side=False):
        #    self.node.scope.press_button('bright16x')
        #for _ in xrange(mscfg['widen_16x_clicks']):
        #    self.node.scope.turn_knob('brightness', 'r')

        # check screen
        if self.node.scope.screen_is_open():
            self.node.scope.press_button('screen')

        # start filament kill timer
        self.setup_time = time.time()

        # notify that beam will be killed at T if no action is taken
        notification.send_notification(
            self.node, 'make_safe',
            kill_time=self.setup_time + mscfg['kill_beam_timeout'])

        try:
            save_all_configs(self.node)
        except Exception as e:
            logger.warning(
                "Failed to save all configs for this makesafe: %s" % e)

        # move stage to 'safe' spot if tape is untensioned
        try:
            if self.node.tape.connected():
                if self.node.tape.get_state() == 'untensioned':
                    kwargs = {
                        'x': cfg['origin']['x'],
                        'y': cfg['origin']['y'],
                        'wait': False, 'relative': False, 'poll': True,
                        'hold': True}
                    self.node.motion.move(**kwargs)
        except Exception as e:
            logger.error("failed to move to origin: %s" % e)

        return 'wait_to_kill_beam'

    def wait_to_kill_beam(self):
        mscfg = self.node.config()['make_safe']
        if (time.time() - self.setup_time) > mscfg['kill_beam_timeout']:
            return 'kill_beam'
        return 'wait_to_kill_beam', 0.5

    def kill_beam(self):
        mscfg = self.node.config()['make_safe']
        # if the scope is at 120 kV
        # going 1 click up will kill the beam
        for _ in xrange(mscfg['ht_up_to_kill']):
            self.node.scope.press_button('ht_up')
        # notify that beam was killed
        notification.send_notification(
            self.node, 'kill_beam')
