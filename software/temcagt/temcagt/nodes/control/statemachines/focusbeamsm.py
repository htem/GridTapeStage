#!/usr/bin/env python

import time

import numpy

from ... import base


class FocusBeamSM(base.StateMachine):
    """
    move to center of roi (or other target?)

    set beam wobble?
    adjust focus to minimize blur

    turn off beam wobble?
    """
    def setup(self):
        self.node.config({'focus_beam': 'meta'}, prune=True)
        cfg = self.node.config()['focus_beam']
        self.node.config({
            'focus_beam': {'meta': {
                'start_time': time.time(),
            }},
        })

        # check screen
        screen_delay = None
        if not self.node.scope.screen_is_open():
            self.node.scope.press_button('screen')
            screen_delay = self.node.scope.config().get('screen_delay', 5.0)

        # setup stats reporting
        self.old_camera_configs = []
        for c in self.node.cameras:
            self.old_camera_configs.append(c.config())
            c.config({
                'broadcast': {  # disable frame/etc broadcasting
                    'enable': cfg.get('broadcast', False),
                },
                'stream': {
                    'grab_type': cfg['grab_type'],
                    'delay': cfg['delay'],
                }
            })
        self.n_adjustments = cfg['n_adjustments']

        # save all focus settings (1 coarse = 16 fine)
        self.focus_step = 0
        self.focus_readings = {}

        # if ROI defined, move to center
        fp = self.node.get_current_focus_point()
        if fp is not None:
            kwargs = {
                'x': fp[0],
                'y': fp[1],
                'wait': True, 'relative': False, 'poll': True, 'hold': True}
            self.node.motion.move(**kwargs)

        if screen_delay is not None:
            return 'wait_for_screen', screen_delay
        return 'settle', cfg['settling_time']

    def wait_for_screen(self):
        if self.node.scope.screen_is_open():
            return 'settle'
        raise IOError("screen is either not working or is flaky")

    def settle(self):
        self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
        return 'focus_beam', self.stats_futures

    def focus_beam(self):
        # check image to make sure this is a good region to focus
        # and doesn't contain empty resin, a blood vessel, a tear, etc
        # perhaps check if max focus value is above some threshold
        cfg = self.node.config()['focus_beam']
        min_std = cfg.get('min_std', 0)
        f = {}
        for (i, sf) in enumerate(self.stats_futures):
            r = sf.result()
            f[i] = r['focus']
            if r['std'] < min_std:
                self.node.config({
                    'focus_beam': {'meta': {
                        'focus_step': self.focus_step,
                        'focus_readings': self.focus_readings,
                    }},
                })
                raise ValueError("std[%s] %s < %s" % (i, r['std'], min_std))

        # average focus? single camera?
        if isinstance(cfg['measure'], (str, unicode)):
            if hasattr(numpy, cfg['measure']):
                d = float(getattr(numpy, cfg['measure'])(f.values()))
            else:
                raise ValueError("Unknown measurment: %s" % cfg['measure'])
        else:
            if (
                    cfg['measure'] < 0 or
                    cfg['measure'] > (len(self.node.cameras) - 1)):
                raise ValueError("Unknown measurment: %s" % cfg['measure'])
            d = f[cfg['measure']]
        self.focus_readings[self.focus_step] = d

        # enough readings to calculate slope?
        min_n = (cfg['n_away_from_edge'] + 1) * 2 + 1
        rmoves = min_n / 2
        if len(self.focus_readings) < min_n:
            if len(self.focus_readings) < rmoves:
                # move knob right
                return 'focus_right'
            else:
                return 'focus_left'

        # is max at an edge?
        fis = sorted(self.focus_readings)
        fvs = [self.focus_readings[i] for i in fis]
        fvi = numpy.argmax(fvs)
        # make sure max is N away from edge?
        n_edge = cfg['n_away_from_edge']
        if fvi <= n_edge:  # turn left, repeat
            return 'focus_left'
        elif fvi >= len(fvs) - 1 - n_edge:  # turn right, repeat
            return 'focus_right'
        else:  # go back to max, exit
            fi = fis[fvi]  # find focus_step of max
            self.node.scope.adjust_focus(
                fi - self.focus_step, coarse=False, x16=False)
            self.focus_step = fi
            return 'finish'

    def focus_right(self):
        self.n_adjustments -= 1
        if self.n_adjustments < 1:
            self.node.config({
                'focus_beam': {'meta': {
                    'focus_step': self.focus_step,
                    'focus_readings': self.focus_readings,
                }},
            })
            raise ValueError("n_adjustments exceeded")
        # if focus_step + 1 has been measured, move to max + 1
        if self.focus_step + 1 in self.focus_readings:
            mfi = max(self.focus_readings) + 1
            self.node.scope.adjust_focus(
                mfi - self.focus_step, coarse=False, x16=False)
            self.focus_step = mfi
        else:
            self.node.scope.adjust_focus(1, coarse=False, x16=False)
            self.focus_step += 1
        return 'settle', self.node.config()['focus_beam']['settling_time']
        #self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
        #return 'focus_beam', self.stats_futures

    def focus_left(self):
        self.n_adjustments -= 1
        if self.n_adjustments < 1:
            self.node.config({
                'focus_beam': {'meta': {
                    'focus_step': self.focus_step,
                    'focus_readings': self.focus_readings,
                }},
            })
            raise ValueError("n_adjustments exceeded")
        # if focus_step - 1 has been measured, move to min - 1
        if self.focus_step - 1 in self.focus_readings:
            mfi = min(self.focus_readings) - 1
            self.node.scope.adjust_focus(
                mfi - self.focus_step, coarse=False, x16=False)
            self.focus_step = mfi
        else:
            self.node.scope.adjust_focus(-1, coarse=False, x16=False)
            self.focus_step -= 1
        return 'settle', self.node.config()['focus_beam']['settling_time']
        #self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
        #return 'focus_beam', self.stats_futures

    def finish(self):
        cfg = self.node.config()['focus_beam']
        # underfocus
        if cfg['n_underfocus'] != 0:
            self.node.scope.adjust_focus(
                -cfg['n_underfocus'], coarse=False, x16=False)

        # calculate number of adjustments
        n_adj = cfg['n_adjustments'] - self.n_adjustments

        # record focus data and number of focus_steps
        self.node.config({
            'focus_beam': {'meta': {
                'finish_time': time.time(),
                'focus_step': self.focus_step,
                'focus_readings': self.focus_readings,
                'n_adjustments': n_adj,
            }},
        })

        # expand to imaging dimensions? another state?
        if hasattr(self, 'old_camera_configs'):
            for (oc, c) in zip(self.old_camera_configs, self.node.cameras):
                c.config(oc)
            del self.old_camera_configs
        [c.stop_streaming() for c in self.node.cameras]

    def _teardown(self):
        if hasattr(self, 'old_camera_configs'):
            for (oc, c) in zip(self.old_camera_configs, self.node.cameras):
                c.config(oc)
            del self.old_camera_configs
        [c.stop_streaming() for c in self.node.cameras]
