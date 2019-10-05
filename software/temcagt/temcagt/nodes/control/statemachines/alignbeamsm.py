#!/usr/bin/env python

import time

from ... import base


class AlignBeamSM(base.StateMachine):
    """
    move to center of roi (or other target?)

    widen beam to full wide
    tighten beam until visible shadows [or N clicks]
    equalize shadows with shifts
    widen beam to imaging brightness
    check for aperture errors
    """
    def setup(self):
        self.node.config({'align_beam': 'meta'}, prune=True)
        acfg = self.node.config()['align_beam']
        self.node.config({
            'align_beam': {'meta': {
                'start_time': time.time(),
            }},
        })

        # check screen
        screen_delay = None
        if not self.node.scope.screen_is_open():
            self.node.scope.press_button('screen')
            screen_delay = self.node.scope.config().get('screen_delay', 5.0)

        self.beam_data = []
        self.aperture_data = None
        self.clicks = []
        self.n_retries = acfg['n_retries']
        self.n_adjustments = acfg['n_adjustments']
        # if ROI defined, move to center
        ap = self.node.get_current_align_point()
        if ap is not None:
            kwargs = {
                'x': ap[0],
                'y': ap[1],
                'wait': True, 'relative': False, 'poll': True, 'hold': True}
            self.node.motion.move(**kwargs)
        if screen_delay is None:
            return 'widen_beam'
        return 'wait_for_screen', screen_delay

    def wait_for_screen(self):
        if self.node.scope.screen_is_open():
            return 'widen_beam'
        raise IOError("screen is either not working or is flaky")

    def widen_beam(self):
        cfg = self.node.config()['align_beam']
        self.node.scope.widen_beam()
        return 'setup_beam', cfg['post_widen_delay']

    def setup_beam(self):
        cfg = self.node.config()['align_beam']
        self.node.scope.adjust_brightness(
            cfg['tighten_beam_n_16x_clicks'], 'l', x16=True)
        self.node.scope.adjust_brightness(
            cfg['tighten_beam_n_1x_clicks'], 'l', x16=False)

        # setup stats reporting
        self.old_camera_configs = []
        for c in self.node.cameras:
            self.old_camera_configs.append(c.config())
            c.config({
                'broadcast': {  # disable frame/etc broadcasting
                    'enable': cfg.get('broadcast', False),
                },
                'stream': {
                    'grab_type': 'grab',
                    'delay': cfg['delay'],
                }
            })
        #self.n_clicks = {'x': 0, 'y': 0}
        #self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
        #return 'align_beam', self.stats_futures
        #if not self.node.scope.screen_is_open():
        #    return 'wait_for_screen', 5.0
        return 'settle', cfg['settling_time']

    def settle(self):
        self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
        return 'align_beam', self.stats_futures

    def align_beam(self):
        cfg = self.node.config()['align_beam']
        # check beam shadows
        d = {}
        for (i, sf) in enumerate(self.stats_futures):
            s = sf.result()
            d[i] = s['beam']
            # make sure result contains a valid result
            if d[i]['i'] == -1:  # beam not found
                self.n_retries -= 1
                if self.n_retries < 1:
                    self.node.config({
                        'align_beam': {'meta': {
                            'beam_data': self.beam_data,
                            'aperture_data': self.aperture_data,
                            'clicks': self.clicks,
                        }},
                    })
                    raise ValueError("n_retries exceeded")
                return 'settle'
                #self.stats_futures = [
                #    c.get_new_stats() for c in self.node.cameras]
                #return 'align_beam', self.stats_futures

        self.stats_futures = None

        # this can't be tested with 1 camera
        if len(d) == 1:
            return 'expand'

        # compare 0 to 3 for shift x: knob 'r' moves beam towards 0
        # compare 1 and 2 for shift y: knob 'r' moves beam towards 1
        dx = d[0]['i'] - d[3]['i']
        dy = d[1]['i'] - d[2]['i']
        ex = abs(dx) > cfg['close_enough']['x']
        ey = abs(dy) > cfg['close_enough']['y']

        self.beam_data.append({'dx': dx, 'dy': dy})
        if cfg['include_beam_array']:
            # make beam data 'vs' a list
            for i in d:
                d[i]['vs'] = d[i]['vs'].tolist()
            self.beam_data[-1]['d'] = d

        # adjust or exit
        if not (ex or ey):
            return 'check_aperture', cfg['settling_time']

        adjust = 'xy'
        if (
                abs(dx) < cfg['one_axis_adjust']['x'] or
                abs(dy) < cfg['one_axis_adjust']['y']):
            if abs(dx) > abs(dy):
                adjust = 'x'
            else:
                adjust = 'y'
        # keep track of n clicks
        c = {}
        if ex and 'x' in adjust:
            d = 'r' if dx > 0 else 'l'
            self.node.scope.turn_knob('shiftx', d)
            #self.n_clicks['x'] += 1 if d == 'r' else -1
            c['x'] = d
        if ey and 'y' in adjust:
            d = 'r' if dy > 0 else 'l'
            self.node.scope.turn_knob('shifty', d)
            #self.n_clicks['y'] += 1 if d == 'r' else -1
            c['y'] = d
        self.clicks.append(c)

        # abort on > N adjustments
        self.n_adjustments -= 1
        if self.n_adjustments < 1:
            self.node.config({
                'align_beam': {'meta': {
                    'beam_data': self.beam_data,
                    'aperture_data': self.aperture_data,
                    'clicks': self.clicks,
                }},
            })
            raise ValueError("n_adjustments exceeded")

        return 'settle', cfg['settling_time']

    def check_aperture(self):
        cfg = self.node.config()['align_beam']
        # widen a bit
        self.node.scope.adjust_brightness(
            cfg['check_aperture_n_1x_clicks'], 'r', x16=False)
        # wait for stats
        return 'read_aperture', cfg['aperture_settling_time']

    def read_aperture(self):
        self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
        return 'expand', self.stats_futures

    def expand(self):
        cfg = self.node.config()['align_beam']
        if self.stats_futures is not None:
            # report aperture alignment
            d = {}
            for (i, sf) in enumerate(self.stats_futures):
                s = sf.result()
                d[i] = s['beam']
                # make sure result contains a valid result
                if d[i]['i'] == -1:  # beam not found
                    self.n_retries -= 1
                    if self.n_retries < 1:
                        self.node.config({
                            'align_beam': {'meta': {
                                'beam_data': self.beam_data,
                                'aperture_data': self.aperture_data,
                                'clicks': self.clicks,
                            }},
                        })
                        raise ValueError("n_retries exceeded")
                    return 'read_aperture'
            # compute aperture alignment
            dx = d[0]['i'] - d[3]['i']
            dy = d[1]['i'] - d[2]['i']
            ex = abs(dx) > cfg['aperture_close_enough']['x']
            ey = abs(dy) > cfg['aperture_close_enough']['y']

            self.aperture_data = {'dx': dx, 'dy': dy}

            if cfg['include_beam_array']:
                # make beam data 'vs' a list
                for i in d:
                    d[i]['vs'] = d[i]['vs'].tolist()
                self.aperture_data['d'] = d

            if ex or ey and cfg['aperture_close_enough']['error']:
                # aperture is out of alignment
                self.node.config({
                    'align_beam': {'meta': {
                        'beam_data': self.beam_data,
                        'aperture_data': self.aperture_data,
                        'clicks': self.clicks,
                    }},
                })
                raise IOError(
                    "Aperture is out of alignment: %s, %s" % (dx, dy))

        # expand to imaging dimensions
        self.node.scope.adjust_brightness(
            cfg['expand_beam_n_1x_clicks'], 'r', x16=False)
        return 'finish'

    def finish(self):
        # calculate number of adjustments
        cfg = self.node.config()['align_beam']
        n_adj = cfg['n_adjustments'] - self.n_adjustments

        self.node.config({
            'align_beam': {'meta': {
                'finish_time': time.time(),
                'beam_data': self.beam_data,
                'aperture_data': self.aperture_data,
                'clicks': self.clicks,
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
        self.node.config({
            'align_beam': {'meta': {
                'beam_data': self.beam_data,
                'aperture_data': self.aperture_data,
                'clicks': self.clicks,
            }},
        })

        if hasattr(self, 'old_camera_configs'):
            for (oc, c) in zip(self.old_camera_configs, self.node.cameras):
                c.config(oc)
            del self.old_camera_configs
        [c.stop_streaming() for c in self.node.cameras]
