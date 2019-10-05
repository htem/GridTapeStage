#!/usr/bin/env python

import time

from ... import base
from .... import config
from .. import notification


class MontageSM(base.StateMachine):
    """
    setup montager node with: [overlaps with BakeSM]
        - roi (recentered by slot center)
        - session name
        - notes?
    run montager montage

    monitor incoming images from compute node
    wait till finished
    """
    def setup(self):
        # check tape state
        if (
                self.node.tape.get_state() != 'untensioned'
                or self.node.motion.is_locked()):
            raise IOError(
                "Cannot start montage because tape is not untensioned[%s] "
                "or motion stage is locked[%s]" % (
                    self.node.tape.get_state() != 'untensioned',
                    self.node.motion.is_locked()))

        slot = self.node.config()['slot']
        if 'rois' not in slot or len(slot['rois']) == 0:
            # TODO check that slot is fully defined
            raise ValueError("slot rois not defined")

        # send roi to montager node
        roi = slot['rois'][slot['roi_index']]
        self.node.montager.config({'montage': 'roi'}, prune=True)
        self.node.montager.config({'montage': {'roi': roi}})

        # set session name by block and barcode #
        session_name = ""
        block = self.node.tapecamera.config()['reel'].get('block', None)
        if block is not None:
            session_name += block
        if 'id' in slot:
            if len(session_name):
                session_name += '_'
            session_name += '%04i' % slot['id']
        if len(session_name):
            self.node.montager.config({'session': {'name': session_name}})
            self.node.config({'slot': {'montage': {
                'session_name': session_name}}})

        # set save directory?
        save_cfg = self.node.config()['save']

        r, ed = self.node.montager.check_save_directory(
            save_cfg['directory'], save_cfg['next'])
        if not r:
            raise IOError(ed)

        if ed != save_cfg['directory']:
            self.node.config({'save': {'directory': ed, 'next': None}})
            save_cfg = self.node.config()['save']

        # check disk access & space
        #r, e = config.checkers.save_directory_ok(
        #    save_cfg['directory'])
        #if not r:
        #    # if next is available try that
        #    if save_cfg.get('next', None) is not None:
        #        nr, ne = config.checkers.save_directory_ok(
        #            save_cfg['next'])
        #        if not nr:
        #            raise IOError(ne)
        #        else:
        #            # switch to next
        #            self.config({'save': {'directory': save_cfg['next']}})
        #            save_cfg = self.config()['save']
        #    else:
        #        raise IOError(e)

        self.node.montager.config({
            'save': {'directory': save_cfg['directory']}})

        # save control node config in montager config
        self.node.montager.config({
            'control': self.node.config()})
        # check screen
        if not self.node.scope.screen_is_open():
            self.node.scope.press_button('screen')
            screen_delay = self.node.scope.config().get('screen_delay', 5.0)
            return 'wait_for_screen', screen_delay
        return 'montage'

    def wait_for_screen(self):
        if self.node.scope.screen_is_open():
            return 'montage'
        raise IOError("screen is either not working or is flaky")

    def montage(self):
        self.node.config({'slot': {
            'montage': {
                'start_time': time.time(),
            },
        }})
        notification.send_notification(
            self.node, 'montage_start')
        self.node.montager.montage()
        return 'watch_montage', 1

    def watch_montage(self):
        # TODO monitor incoming images
        r = self.node.montager.get_state()
        if r is None:
            return 'finish'
        if not self.node.scope.screen_is_open():
            # TODO restart?
            self.node.montager.kill()
            raise Exception("Screen dropped during montage, killing")
        if r[0] == 'MontageSM' and isinstance(r[1], (str, unicode)):
            # TODO configure watch_montage timeout
            return 'watch_montage', 1.
        raise Exception("montage error: %s" % (r, ))

    def finish(self):
        mcfg = self.node.montager.config().get(
            'session', {}).get('montage', {})
        # TODO montage stats?
        self.node.config({'slot': {
            'montage': {
                'n_tiles': mcfg.get('n_tiles', -1),
                'n_vetos': mcfg.get('n_vetos', -1),
                'n_nodatas': mcfg.get('n_nodatas', 0),
                'finish_time': time.time(),
            },
        }})
        # notification
        notification.send_notification(
            self.node, 'montage')
        # TODO write to save directory?
        # TODO widen beam?
        return None
