#!/usr/bin/env python

import time

from ... import base


class FindSlotSM(base.StateMachine):
    """
    verify tape untensioned

    setup stats and beam
    move to approximate center

    find edge(s)

    move to center
    set center
    set roi (outside?)

    state = {
        'center': {
            'x': ..., 'y': ...,  # stage position
            'time': ....,  # time found
        },
    }
    config = {
        'center': {
            'x': ..., 'y': ...,  # stage position
            'time': ....,  # time found
        },
        'start': {'x': ..., 'y': ...},
        'move_size': {'x': ..., 'y': ...},
        'max_moves': {'x': ..., 'y': ...},
        'stats': (stats config, stream config)
        'delay': # stats delay
        'threshold': std threshold
    }
    """
    def setup(self):
        #self.stds = []
        self.data = []
        self.last_move = None
        start_time = time.time()
        self._error = None
        # verify tape untensioned
        if self.node.tape.get_state() != 'untensioned':
            raise IOError(
                "Tape is not untensioned [%s] cannot find slot"
                % self.node.tape.get_state())
        # check motion stage unlocked
        if self.node.motion.is_locked():
            raise IOError("Motion stage is locked cannot find slot")

        # check screen
        screen_delay = None
        if not self.node.scope.screen_is_open():
            self.node.scope.press_button('screen')
            screen_delay = self.node.scope.config().get('screen_delay', 5.0)

        ncfg = self.node.config()
        cfg = self.node.config()['find_slot']
        # move to center
        kwargs = {
            'x': cfg['start']['x'],
            'y': cfg['start']['y'],
            'wait': True, 'relative': False, 'poll': True, 'hold': True}
        self.node.motion.move(**kwargs)
        # setup stats
        self.old_camera_configs = []
        for c in self.node.cameras:
            self.old_camera_configs.append(c.config())
            c.config({
                'broadcast': {  # disable frame/etc broadcasting
                    'enable': cfg['broadcast'],
                },
                'stream': {
                    'grab_type': 'grab',
                    'delay': cfg['delay'],
                }
            })
        # clear stats
        self.directions = [
            ('x', -cfg['move_size']['x']),
            ('y', -cfg['move_size']['y'])]
        self.n_moves = 0
        self.stats_futures = None
        #self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
        #self.node.frame_stats = [None for _ in xrange(len(self.node.cameras))]
        # start streaming
        [c.start_streaming() for c in self.node.cameras]
        # record meta
        self.node.config({'find_slot': 'meta'}, prune=True)
        self.node.config({'find_slot': {'meta': {
            'start_time': start_time,
        }}})
        if screen_delay is not None:
            return 'widen_beam', screen_delay
        return 'widen_beam'

    def error(self):
        # move to 'safe' position
        cfg = self.node.config()
        #cfg = ncfg['find_slot']
        #if cfg['find_slot']['include_stds']:
        if cfg['find_slot']['include_data']:
            #self.node.config({'find_slot': {'meta': {'stds': self.stds}}})
            self.node.config({'find_slot': {'meta': {'data': self.data}}})
        # move to center
        kwargs = {
            'x': cfg['origin']['x'],
            'y': cfg['origin']['y'],
            'wait': True, 'relative': False, 'poll': True, 'hold': True}
        self.node.motion.move(**kwargs)
        # reset camera configs
        for (oc, c) in zip(self.old_camera_configs, self.node.cameras):
            c.config(oc)
        # stop streaming
        [c.start_streaming() for c in self.node.cameras]

        if self._error is not None:
            raise self._error
        raise Exception("find_slot undefined error")

    def widen_beam(self):
        self.node.scope.widen_beam()
        cfg = self.node.config()['find_slot']
        return 'setup_beam', cfg['post_widen_delay']

    def setup_beam(self):
        # tighten by N 16x clicks
        self.tight_n_16x_clicks = self.node.config()[
            'find_slot']['tighten_beam_n_16x_clicks']
        self.node.scope.adjust_brightness(
            self.tight_n_16x_clicks, 'l', x16=True)

        if not self.node.scope.screen_is_open():
            screen_delay = self.node.scope.config().get('screen_delay', 5.0)
            return 'wait_for_screen', screen_delay
        return 'check_stats'

    def wait_for_screen(self):
        if self.node.scope.screen_is_open():
            return 'check_stats'
        raise IOError("screen is either not working or is flaky")

    def move(self):
        if len(self.directions) == 0:
            return 'finish'
        cfg = self.node.config()['find_slot']
        axis, nm = self.directions[0]
        if self.n_moves > cfg['max_moves'][axis]:
            self._error = IOError(
                "find_slot failed to find direction %s in n_moves %s" %
                (axis, self.n_moves))
            return 'error'
        # move
        kwargs = {
            axis: nm, 'wait': True, 'relative': True,
            'poll': True, 'hold': True}
        self.last_move = {axis: nm}
        self.node.motion.move(**kwargs)
        self.n_moves += 1
        # clear stats
        self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
        #self.node.frame_stats = [None for _ in xrange(len(self.node.cameras))]
        return ('check_stats', self.stats_futures)

    def change_direction(self):
        if len(self.directions) == 0:
            return 'finish'
        cfg = self.node.config()['find_slot']
        axis, _ = self.directions.pop(0)

        # check for < minimum moves?
        if self.n_moves < cfg['min_moves'][axis]:
            self._error = IOError(
                "find_slot found %s edge in too few moves %s < %s" %
                (axis, self.n_moves, cfg['min_moves'][axis]))
            return 'error'

        # move to 'center' of direction
        nm = cfg['offset'][axis]
        kwargs = {
            axis: nm, 'wait': True, 'relative': True,
            'poll': True, 'hold': True}
        mr = self.node.motion.move(**kwargs)
        # set center
        self.node.config({'find_slot': {
            'center': {axis: mr[axis]},
            'meta': {axis: {
                'n_moves': self.n_moves,
                'time': time.time(),
            }}}})
        # reset n_moves
        self.n_moves = 0
        return 'move'

    def check_stats(self):
        if self.stats_futures is None:
            self.stats_futures = [c.get_new_stats() for c in self.node.cameras]
            return ('check_stats', self.stats_futures)
        # wait for new stats
        #if any((s is None for s in self.node.frame_stats)):
        #    return (
        #        'check_stats',
        #        self.node.config()['find_slot']['check_timeout'])
        # check for edge of slot
        threshold = self.node.config()['find_slot']['threshold']
        stat = self.node.config()['find_slot'].get('stat', 'std')
        edge = False
        #stds = {}
        datum = {}
        #for s in self.node.frame_stats:
        # TODO check futures for running or errors
        for (i, sf) in enumerate(self.stats_futures):
            s = sf.result()
            datum[i] = s[stat]
            #stds[i] = s['std']
            if datum[i] < threshold:
                edge = True
        if self.last_move is not None:
            self.data.append({
                'move': self.last_move,
                'datum': datum,
            })
            #self.stds.append({
            #    'move': self.last_move,
            #    'stds': stds,
            #})
        self.stats_futures = None
        if edge:
            return 'change_direction'
        return 'move'

    def finish(self):
        if hasattr(self, 'tight_n_16x_clicks'):
            self.node.scope.adjust_brightness(
                self.tight_n_16x_clicks, 'r', x16=True)
            del self.tight_n_16x_clicks
        # reset camera configs
        for (oc, c) in zip(self.old_camera_configs, self.node.cameras):
            c.config(oc)
        del self.old_camera_configs
        # stop streaming
        [c.stop_streaming() for c in self.node.cameras]
        meta = {'finish_time': time.time()}
        #if self.node.config()['find_slot']['include_stds']:
        if self.node.config()['find_slot']['include_data']:
            meta['data'] = self.data
            #meta['stds'] = self.stds
        self.node.config({'find_slot': {'meta': meta}})
        self.node.config({'slot': {
            'center': self.node.config()['find_slot']['center'],
        }})
        # reload rois now that there is a defined center
        self.node.load_rois()
        return None

    def _teardown(self):
        super(FindSlotSM, self)._teardown()
        if hasattr(self, 'tight_n_16x_clicks'):
            self.node.scope.adjust_brightness(
                self.tight_n_16x_clicks, 'r', x16=True)
            del self.tight_n_16x_clicks
        # reset camera configs
        if hasattr(self, 'old_camera_configs'):
            for (oc, c) in zip(self.old_camera_configs, self.node.cameras):
                c.config(oc)
        # stop streaming
        [c.stop_streaming() for c in self.node.cameras]
