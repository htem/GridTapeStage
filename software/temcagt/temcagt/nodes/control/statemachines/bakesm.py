#!/usr/bin/env python

import time

from ... import base


class BakeSM(base.StateMachine):
    """
    compute slot roi
    setup montager node with: [overlaps with MontageSM]
        - roi (recentered by slot center)
        - session name
        - notes?

    run montager bake
    wait till finished

    is there anything to monitor here?
    """
    def setup(self):
        # check tape state
        if (
                self.node.tape.get_state() != 'untensioned'
                or self.node.motion.is_locked()):
            raise IOError(
                "Cannot start bake because tape is not untensioned[%s] "
                "or motion stage is locked[%s]" % (
                    self.node.tape.get_state() != 'untensioned',
                    self.node.motion.is_locked()))

        slot = self.node.config()['slot']
        if 'rois' not in slot or len(slot['rois']) == 0:
            # TODO check that slot is fully defined
            raise ValueError("slot rois not defined")
        # propagate roi
        roi = slot['rois'][slot['roi_index']]
        self.node.montager.config({'montage': 'roi'}, prune=True)
        self.node.montager.config({'montage': {'roi': roi}})
        # check screen
        if not self.node.scope.screen_is_open():
            self.node.scope.press_button('screen')
            screen_delay = self.node.scope.config().get('screen_delay', 5.0)
            return 'wait_for_screen', screen_delay
        return 'bake'

    def wait_for_screen(self):
        if self.node.scope.screen_is_open():
            return 'bake'
        raise IOError("screen is either not working or is flaky")

    def bake(self):
        self.node.config({'slot': {
            'bake': {
                'start_time': time.time(),
            },
        }})
        self.node.montager.bake()
        # TODO configure watch_bake timeout
        return 'watch_bake', 1.

    def watch_bake(self):
        r = self.node.montager.get_state()
        if r is None:
            return 'finish'
        if not self.node.scope.screen_is_open():
            # TODO restart?
            self.node.montager.kill()
            raise Exception("Screen dropped during bake, killing")
        if r[0] == 'BakeSM' and isinstance(r[1], (str, unicode)):
            # TODO configure watch_bake timeout
            return 'watch_bake', 1.
        raise Exception("bake error: %s" % (r, ))

    def finish(self):
        self.node.config({'slot': {
            'bake': {
                'finish_time': time.time(),
            },
        }})
        return None
