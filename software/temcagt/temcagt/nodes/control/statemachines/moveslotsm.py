#!/usr/bin/env python

import datetime
import os
import time
import numpy

import montage

from ... import base


class MoveSlotSM(base.StateMachine):
    """
    Will need to know:
    - tape direction (does + tape movement increase barcodes)
    - tape version (do leader tape slots have [1,2]0XXXX? ids)
    - how many slots per reel (to know leader tape transitions)
    - slot id offset (25)

    verify stage position

    tension tape [lock motion stage]
    adjust to tension
    read and store current barcode

    move in direction
    fine tune movement

    when barcode positioned
    adjust to tension
    untension [unlock motion stage]

    Will produce the following:
        - start time
        - end time
        - distance moved (separate + & - ?)
        - starting barcode (necessary?)
        - ending barcode
    """
    def setup(self):
        start_time = time.time()
        cfg = self.node.config()
        # if motion stage is unlocked, move to move_slot: start
        if (
                not self.node.motion.is_locked() and
                self.node.tape.get_state() == 'untensioned'):
            kwargs = {
                'x': cfg['move_slot']['piezo_position']['x'],
                'y': cfg['move_slot']['piezo_position']['y'],
                'wait': True, 'relative': False, 'poll': True, 'hold': True}
            self.node.motion.move(**kwargs)
        # turn on led
        self.node.tape.set_led(0)

        # widen beam
        self.node.scope.widen_beam()

        # TODO delay here?

        # check screen
        if self.node.scope.screen_is_open():
            self.node.scope.press_button('screen')

        # lock motion stage
        self.node.motion.lock()

        # setup tape
        if self.node.tape.get_state() == 'untensioned':
            self.node.tape.tension_tape()
        if self.node.tape.get_state() != 'tensioned':
            raise IOError(
                "Cannot move slot without tensioned tape: %s"
                % self.node.tape.get_state())
        self.node.tape.adjust_to_tension()

        # turn on led & start tape camera streaming
        self.node.tapecamera.clear_last_barcodes()
        self.node.tapecamera.config({'read_barcodes': True})

        # setup 'expected' barcode reading
        last_slot_id = cfg.get('slot', {}).get('id', None)
        #if last_slot_id is not None:
        #    self.expected_value = last_slot_id
            # TODO add range of expected values? range based on reel info
        #    self.node.tapecamera.config({
        #        'expected_beamslot': last_slot_id})
        #else:
        #    self.expected_value = 0
            #self.node.tapecamera.config({
            #    'expected_beamslot': cfg['move_slot']['target']['id']})

        # clear meta data
        self.node.config({'move_slot': 'meta', 'slot': {}}, prune=True)
        # save meta
        self.node.config({'move_slot': {'meta': {'start_time': start_time}}})
        self.distance = 0
        self.first_barcode = None
        self.n_moves = 0

        return 'get_barcode', cfg['move_slot']['led_delay']

    def get_barcode(self):
        self.barcode = None
        #self.node.tapecamera.clear_last_barcodes()
        self.node.tapecamera.start_streaming()
        self.node.tapecamera.clear_beam_slot()
        self.bcf = self.node.tapecamera.get_barcodes()
        self.n_waits = 0
        cfg = self.node.config()['move_slot']
        self.max_waits = cfg['max_waits']
        return 'wait_for_barcode', self.bcf

    def reget_barcode(self):
        self.barcode = None
        self.node.tapecamera.clear_beam_slot()
        self.node.tapecamera.start_streaming()
        self.bcf = self.node.tapecamera.get_barcodes()
        return 'wait_for_barcode', self.bcf

    def wait_for_barcode(self):
        # TODO check for self.bcf exception
        self.barcode = self.node.tapecamera.get_beam_slot()
        if self.barcode is None:
            self.n_waits += 1
            if self.n_waits > self.max_waits:
                raise IOError("Failed to find barcode")
            return 'reget_barcode'
        self.node.tapecamera.stop_streaming()
        if self.first_barcode is None:
            # record first barcode seen
            self.first_barcode = self.barcode.copy()
            self.node.config({
                'move_slot': {'meta': {'first_barcode': self.first_barcode}}})
        cfg = self.node.config()

        # compare against target
        target_index = self.node.tapecamera.call_reel(
            'slot_id_to_index',
            cfg['move_slot']['target']['id'],
            cfg['move_slot']['target']['type'])
        # the offset is simply the barcode 'y' value
        dp = self.barcode['y']
        dmm = dp / float(cfg['move_slot']['ppmm'])

        # update the expected barcode with what we got
        self.node.tapecamera.set_expected_beamslot( self.barcode['value'] )

        if self.barcode['index'] != target_index:
            # make a large move
            delta_index = target_index - self.barcode['index']
            if abs(delta_index) > cfg['move_slot']['maximum_slot_moves']:
                raise IOError(
                    "Moving from %s to %s requires %s moves "
                    "> maximum_slot_move[%s]" %
                    (
                        self.barcode['value'],
                        cfg['move_slot']['target']['id'],
                        abs(delta_index),
                        cfg['move_slot']['maximum_slot_moves']))
            # possibly swap direction
            rcfg = self.node.tapecamera.config()['reel']
            if rcfg['barcode_side'] == 'right':
                delta_index *= -1
            #delta_index *= rcfg['direction']
            ssmm = cfg['move_slot']['slot_spacing']
            # make sure not to over-shoot
            if delta_index > 1:  # if off by >1 add extra
                dmm += ssmm
            elif delta_index < -1:
                dmm -= ssmm
            elif delta_index == 1:
                if dmm > 0:
                    dmm = ssmm
                else:
                    dmm = (ssmm + dmm) * cfg['move_slot']['move_ratio']
            elif delta_index == -1:
                if dmm > 0:
                    # partial move
                    dmm = (-ssmm + dmm) * cfg['move_slot']['move_ratio']
                else:
                    dmm = -ssmm
            # TODO autotension?
            if self.n_moves > cfg['move_slot']['max_moves']:
                raise IOError("Move slot: too many moves")
            self.node.tapecamera.increment_expected_beamslot(int(numpy.sign(delta_index)))
            self.node.tape.move_tape(dmm)
            self.distance += dmm
            self.n_moves += 1
            self.node.tape.run_reels()
            rt = max(0.5, abs(dmm * 0.5))
            return 'stop_reels', rt
        else:
            # fine tune position
            #delta = target_y - self.barcode['y']
            #dmm = delta / float(cfg['move_slot']['ppmm'])
            if abs(dp) < cfg['move_slot']['target']['close_enough']:
                return 'get_tapecamera_image'
            if self.n_moves > cfg['move_slot']['max_moves']:
                raise IOError("Move slot: too many moves")
            self.n_moves += 1
            if dmm > 0:
                # continue moving
                dmm *= float(cfg['move_slot']['move_ratio'])
                self.node.tape.move_tape(dmm, auto_tension=False)
                self.distance += dmm
                self.node.tape.adjust_to_tension()
                return 'get_barcode'
            else:
                # move backwards + some
                dmm -= cfg['move_slot']['reverse_bump']
                self.node.tape.move_tape(dmm, auto_tension=False)
                self.distance += dmm
                self.node.tape.adjust_to_tension()
                return 'get_barcode'
            return 'get_tapecamera_image'

    def stop_reels(self):
        self.node.tape.stop_reels()
        self.node.tape.adjust_to_tension()
        return 'get_barcode'

    def get_tapecamera_image(self):
        self.tapecamera_image = self.node.tapecamera.get_image()
        return 'finish', self.tapecamera_image

    def finish(self):
        if hasattr(self, 'tapecamera_image'):
            if self.tapecamera_image.exception() is None:
                # save current tapecamera image
                im = self.tapecamera_image.result()
                ts = datetime.datetime.now().strftime('%y%m%d%H%M%S')
                dn = os.path.join(
                    self.node.config()['save']['directory'],
                    'tapecamera_images')
                if not os.path.exists(dn):
                    os.makedirs(dn)
                fn = os.path.join(
                    dn,
                    '%s_%s.png' % (ts, self.barcode['value']))
                montage.io.imwrite(fn, im)
        # turn off led & start tape camera streaming
        self.node.tape.set_led(255)
        self.node.tapecamera.stop_streaming()

        # save meta and barcode
        self.node.config({
            'move_slot': {'meta': {
                'n_moves': self.n_moves,
                'barcode': self.barcode,
                'finish_time': time.time(),
                'distance': self.distance}
            },
            'slot': {
                'barcode': self.barcode,
                'id': self.barcode['value'],
            },
        })
        #self.node.load_rois()

        # untension tape, unlock motion stage
        self.node.tape.untension_tape()
        self.node.motion.unlock()
        return None

    def _teardown(self):
        super(MoveSlotSM, self)._teardown()
        self.node.tape.set_led(255)
        self.node.tape.stop_reels()
        self.node.tapecamera.stop_streaming()
