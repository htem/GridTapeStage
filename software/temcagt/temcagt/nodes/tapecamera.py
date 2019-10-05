#!/usr/bin/env python

import json
import os
import threading
import time
import Queue
import cStringIO as StringIO

import concurrent.futures
import numpy
import PIL.Image
import pizco
import matplotlib
import cv2
import scipy.misc
import scipy.ndimage

import itfbarcode
import itfbarcode.linescan
import montage

from . import base
from . import picam
from ..config import reel
from ..config.checkers import require
from .. import log


default_config = {
    'addr': 'tcp://127.0.0.1:11040',
    # camera parameters
    'fps': 2.,
    # TODO properties
    'properties': {
        'resolution': (2592, 1944),
        'roi': [1770, 0, 110, -1],
    },
    'broadcast': {
        'downsample': 2,
    },
    #'fake': {
    #    'enable': True,
    #    #'barcodes': None,  # set to barcodes list or json filename to fake
    #    'barcodes': '~/.temcagt/fake/barcodes.json',
    #    #'barcodes': [
    #    #    {'width': 650, 'center':  1055, 'value': 100},
    #    #],
    #},
    # barcode parsing parameters
    'linescan': {
        'ral': 300,
        'min_length': None,
        'ndigits': 6,
        'bar_threshold': 21,
        'space_threshold': 19,
    },
    'scan_kwargs': {
        'scan': True,
        'min_length_max': 2,
        'ral_scan': 200,
        'ral_step': 25,
    },
    #'x_range': (910, 1010),
    'read_barcodes': True,
    'dark_threshold': 30,
    'x_range': (-310, -1),
    'slot_image': {
        'enable': False,
        'offset': 320,
        'shape': (300, 300),
    },
    #'y_dir': 1,
    'denom_offset': 20.,
    'directory': '~/Desktop/',
    'reel': {
        'id': 1,  # reel id
        'block': 'fake',  # block name
        'version': 1,  # see reel.py
        'n_slots': 2500,  # number of slots per reel
        'barcode_side': 'right',  # left or right
        #'direction': 1,  # 1: moving tape into scope increases slot id
    },
    'beam': {
        'offset': 25,  # offset from camera to beam
        #'y_threshold': [770, 1200],
        'target_y': 1260,
    },
    'slot_type': 'slot',
    'expected_beamslot': -1,
    'expected_barcodes': [],
    'slot_finding': {
        'x_range' : [600,1200],
        'inter_slot_distance' : 745,
        'max_barcode_distance' : 50,
        # TODO: Will probably need one for trailer / leader too
        'slot_template': '/home/pi/Desktop/slot_average.tif',
    }
}


logger = log.get_logger(__name__)


class FakeBarcode(object):
    def __init__(self, attrs):
        self.width = 0
        self.center = 0
        self.value = -1
        for a in attrs:
            setattr(self, a, attrs[a])


class TapecameraNodeException(Exception):
    pass


class TapecameraNode(base.IONode):
    def __init__(self, cfg=None):
        base.IONode.__init__(self, cfg)
        self.cam = None
        self.streaming = False
        cfg = self.config()
        self.last_barcodes = None
        self._beam_slot = None
        self.new_image = pizco.Signal(nargs=1)
        self.new_barcodes = pizco.Signal(nargs=1)
        self.new_slot_image = pizco.Signal(nargs=1)
        self.new_beam_slot = pizco.Signal(nargs=1)
        self.last_frame_time = time.time()
        self._frame_count = 0
        self._save_next_frame = False
        self._processing = False
        self._bcf = None
        self._imf = None
        self._slot_list = None
        self.t_slot = pizco.Signal(nargs=1)

        self._build_reel()

    def __del__(self):
        # disconnect signals
        base.IONode.__del__(self)

    def __repr__(self):
        cfg = self.config()
        return "{}.{} at {} addr {}".format(
            self.__module__, self.__class__, hex(id(self)),
            cfg.get('addr', ''))

    def check_config(self, cfg=None):
        if cfg is None:
            cfg = self.config()
        [require(cfg, k) for k in
            [
                'addr', 'fps',
            ]]
        if 'reel' in cfg and 'barcode_side' in cfg['reel']:
            if cfg['reel']['barcode_side'] not in ('left', 'right'):
                raise ValueError(
                    "Invalid barcode_side: %s [not left or right]" %
                    cfg['reel']['barcode_side'])
        # TODO finish checking config

    def config_delta(self, delta):
        logger.info("TapecameraNode[%s] config_delta %s", self, delta)
        if 'reel' in delta:
            if 'barcode_side' in delta:
                # TODO set/change ROI?
                pass
            self._build_reel()
        if self.connected() and 'properties' in delta:
            ps = delta['properties']
            for k in ps:
                self.cam.set_property(k, ps[k])

    def _build_reel(self):
        cfg = self.config()['reel']
        self.reel = reel.create_reel(cfg['version'], cfg['n_slots'])
        self.reel.reel_id = cfg['id']
        #self.reel.direction = cfg['direction']

    def connect(self):
        if self.connected():
            return
        logger.info("TapecameraNode[%s] connect", self)
        fcfg = self.config().get('fake', {})
        if fcfg.get('enable', False):
            self.cam = picam.FakeCaptureThread()
        else:
            self.cam = picam.CaptureThread()
        self.cam.start()
        # set properties
        self.cam.set_property('resolution', (2592, 1944))
        #logger.warning(self.cam.get_property('resolution'))
        #self.cam.set_property('roi', [1810, 0, 110, -1])
        ps = self.config()['properties']
        for k in ps:
            self.cam.set_property(k, ps[k])
        #self.start_streaming()
        logger.info("TapecameraNode[%s] connected", self)

    def disconnect(self):
        if not self.connected():
            return
        self.stop_streaming()
        self.cam.stop()
        self.cam.join()
        logger.info("TapecameraNode[%s] disconnected", self)

    def connected(self):
        return not self.cam is None

    def start_streaming(self):
        if not self.connected() or self.streaming:
            return
        logger.info("start_streaming")
        self.streaming = True
        self.stream_grab()

    def stop_streaming(self):
        if not self.connected() or not self.streaming:
            return
        logger.info("stop_streaming")
        self.streaming = False

    def save_frame(self):
        self._save_next_frame = True

    def _save_frame(self, frame):
        cfg = self.config()
        d = os.path.abspath(
            os.path.expanduser(cfg['directory']))
        if not os.path.exists(d):
            os.makedirs(d)
        ts = int(time.time())
        fn = os.path.join(d, '%s_%s.npy' % (ts, self._frame_count))
        numpy.save(fn, frame)

    def stream_grab(self, in_callback=False):
        if not self.connected():
            return
        if not in_callback:
            return self.loop.add_callback(self.stream_grab, True)
        if not self.streaming:
            return
        # try to recover from failed capture thread
        if not self.cam.is_alive():
            logger.error(
                "TapecameraNode[%s] attempting to restart thread", self)
            self.cam = None
            self.connect()
        f = self.cam.get_frame(recent=True)
        dt = time.time() - self.last_frame_time
        tdt = 1. / self.config()['fps']
        if dt < tdt:
            return self.loop.call_later(
                tdt - dt, self.stream_grab, True)
            # return self.loop.add_callback(self.stream_grab, True)
        if f is not None:
            cfg = self.config()
            t0 = time.time()
            s = StringIO.StringIO()
            f = numpy.rot90(f)
            #pim = PIL.Image.fromarray(f[::8, ::8, :])
            ds = cfg['broadcast'].get('downsample', 1)
            pim = PIL.Image.fromarray(f[::ds, ::ds, :])
            t1 = time.time()
            #pim = pim.resize(
            #    (int(pim.size[0] / 8.), int(pim.size[1] / 8.)),
            #    PIL.Image.ANTIALIAS)
            t2 = time.time()
            pim.save(s, format='jpeg')
            if self._save_next_frame:
                # save image
                self._save_frame(f)
                self._save_next_frame = False
            t3 = time.time()
            nb = s.tell()
            s.seek(0)
            self.last_frame_time = time.time()
            # base64 encode
            e = s.read(nb).encode('base64')
            t4 = time.time()
            self.new_image.emit(e)
            t5 = time.time()
            # process frame TODO as callback?
            if not self._processing:
                self.process_frame(f)
            else:
                print("processing taking longer than grabbing, dropping frame")
            if self._imf is not None:
                self._imf.set_result(f)
                self._imf = None

            t6 = time.time()
            if picam.print_timing:
                print("array to pil: %0.4f" % (t1 - t0))
                print("pil resize  : %0.4f" % (t2 - t1))
                print("pil save    : %0.4f" % (t3 - t2))
                print("base64      : %0.4f" % (t4 - t3))
                print("emit        : %0.4f" % (t5 - t4))
                print("process     : %0.4f" % (t6 - t5))
                print("-----")
                print("total       : %0.4f" % (t6 - t0))
        self.loop.add_callback(self.stream_grab, True)
        return

    def set_property(self, name, value):
        if not self.connected():
            return
        self.cam.set_property(name, value)

    def get_property(self, name):
        if not self.connected():
            return
        return self.cam.get_property(name)

    def get_image(self):
        self._imf = concurrent.futures.Future()
        self.start_streaming()
        return self._imf

    def get_last_barcodes(self):
        return self.last_barcodes

    def clear_last_barcodes(self):
        self.last_barcodes = None

    def get_beam_slot(self):
        return self._beam_slot

    def set_beam_slot(self, beam_slot):
        self._beam_slot = beam_slot
        self.new_beam_slot.emit(self._beam_slot)

    def clear_beam_slot(self):
        self._beam_slot = None

    def get_barcodes(self):
        self._bcf = concurrent.futures.Future()
        self.start_streaming()
        return self._bcf

    def set_expected_beamslot( self, value):
        if self.reel.is_valid_barcode_value(value):
            self.config({'expected_beamslot': value})

    def increment_expected_beamslot(self, delta):
        cfg = self.config()
        ex_beam_slot = cfg['expected_beamslot']
        t = cfg['slot_type']
        if cfg['reel']['version'] == 2:
            if (ex_beam_slot > 199999 and ex_beam_slot  < 200170):  # trailer
                t = 'trailer'
            if (ex_beam_slot > 99999 and ex_beam_slot < 100170):  # leader
                t = 'leader'
            else:
                if ex_beam_slot < self.reel.n_slots:
                    t = 'slot'
        else:
            t = cfg['slot_type']

        self.config({'expected_beamslot': self.reel.offset_slot_id(ex_beam_slot,t,delta)[0]})

    def get_slots_list(self):
        return self._slot_list

    def clear_slots_list(self):
        self._slot_list = None

    def _find_template_slot(self, img, ds = .5):
        cfg = self.config()
        method = cv2.TM_CCORR_NORMED
        slot_fn = cfg['slot_finding'].get('slot_template','/home/pi/Desktop/slot_average.tif')
        slot = None
        try:
            slot = cv2.imread(slot_fn)
        except Exception as e:
            logger.info("Error reading slot file  %s. Error: %s" %(slot_fn, e))
            return None
        c,w,h = slot.shape[::-1]
        xr = cfg['slot_finding'].get('x_range', [600,900])
        cropped = img[:,xr[0]:xr[1]]
        rimg = cropped[:,:,0].copy()
        rslot = slot[:,:,0].copy()
        if ds != 1.0:
            rimg = scipy.misc.imresize(rimg,ds).astype(rimg.dtype)
            rslot = scipy.misc.imresize(rslot,ds).astype(rslot.dtype)

        res = cv2.matchTemplate(rimg,rslot,method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        slot_middle = (int(max_loc[0] / ds) + w/2 + xr[0], int(max_loc[1] / ds)+ h/2 )
        return slot_middle

    def _find_slots(self, img):
        cfg = self.config()
        # Want to skip doing this if we do not need to
        template_pos = self._find_template_slot(img)
        if template_pos is None:
            logger.info("No Slots Found")
            #self._t_slot = None
            self._slot_list = []
            return
        logger.info("Slot found at %s %s " % template_pos )
        self.t_slot.emit(template_pos)
        isd = cfg['slot_finding'].get('inter_slot_distance', 745)
        self._slot_list = range(template_pos[1] % isd, img.shape[0], isd)

    def process_frame(self, frame):
        logger.info("Process_frame")
        self._processing = True
        logger.debug(
            "TapecameraNode[%s] process_frame: %i", self, self._frame_count)
        # look for barcodes in frame
        self._frame_count += 1
        if self._frame_count > 65535:
            self._frame_count = 0
        cfg = self.config()
        if not cfg.get('read_barcodes', True):
            self._processing = False
            return
        #xs, xe = cfg.get('x_range', (1600, 1680))
        xs, xe = cfg.get('x_range', (0, 0))
        if xs < 0:
            xs = frame.shape[1] + xs
        if xe <= 0:
            xe = frame.shape[1] + xe
        if cfg.get('fake', {}).get('barcodes', None) is not None:
            # make these into fake barcodes: width, center, value
            fbcs = cfg['fake']['barcodes']
            if isinstance(fbcs, list):
                bcs = [FakeBarcode(bc) for bc in fbcs]
            elif isinstance(fbcs, (str, unicode)):
                fbcs = os.path.abspath(os.path.expanduser(fbcs))
                # treat as a filename
                if os.path.exists(fbcs):
                    with open(fbcs, 'r') as f:
                        bcs = [FakeBarcode(bc) for bc in json.load(f)]
                else:
                    bcs = []
            #bcs = [FakeBarcode(bc) for bc in cfg['fake']['barcodes']]
        else:
            # first find the slot positions

            cim = frame[:, xs:xe, :]
            #cim = frame
            dv = cim.min(axis=2).max()
            #logger.info("dv = %s", dv)
            #logger.info("dv2 = %s", cim.min(axis=2).max())
            #logger.info("dv3 = %s", cim.max(axis=2).min())
            #logger.info("dv4 = %s", cim.max())
            self._slot_list = None
            if dv > cfg['dark_threshold']:
                base = (cim[:,:,2].astype('f4') + cfg['denom_offset'])
                gim = cim[:, :, 0] / base
                
                vs = gim.mean(axis=1)

                #lab = cv2.cvtColor(cim,cv2.COLOR_BGR2LAB)
                #vs = lab[:,:,1].mean(axis=1) - lab[:,:,2].mean(axis=1)
                

                logger.info("Barcodes")
                if cfg['reel']['barcode_side'] == 'left':
                    vs = vs[::-1]
                kwargs = cfg['linescan']
                # configure this based on the reel
                if len(cfg.get('expected_barcodes', [])) == 0:
                    vbc = lambda bc, s=self: s.reel.is_valid_barcode_value(
                        bc.value)
                else:
                    e = cfg['expected_barcodes']
                    e = [int(i) for i in e]
                    vbc = lambda bc, expected=e: (bc.value in expected)
                #vbc = lambda bc: bc.value < 30000
                bcs, nkwargs = itfbarcode.linescan.scan(
                    vbc, vs, kwargs,
                    cfg.get('scan_kwargs', {}))
                if nkwargs != kwargs:
                    self.config({'linescan': nkwargs, 'old_linescan': kwargs})
                #bcs = itfbarcode.linescan.to_barcodes(vs, **kwargs)
                # remove all invalid barcodes
                bcs = [bc for bc in bcs if vbc(bc)]
                # if we do not find any barcodes at this point we will try to read them by the wide spaces
                if not len(bcs) and cfg.get('expected_beamslot',-1) >= 0:
                    logger.info("Attempting approximate")
                    # do convolutional filtering
                    smooth_width = 200                
                    k = numpy.ones(smooth_width) / float(smooth_width)
                    sms = scipy.ndimage.convolve(gim.mean(axis=1), k, mode='mirror')
                    sss = scipy.ndimage.convolve(gim.std(axis=1), k, mode ='mirror')
                    nim = (gim.swapaxes(0,1) - sms) / sss
                    svs = nim.swapaxes(0,1).sum(axis=1)
                    if cfg['reel']['barcode_side'] == 'left':
                    	svs = svs[::-1]
                    ex_beam_slot = cfg.get('expected_beamslot')
                    pbcs = []
                    if ex_beam_slot >= 0 :
	                # infer type if reel is v2
                        if cfg['reel']['version'] == 2:
                            if (ex_beam_slot > 199999 and ex_beam_slot  < 200170):  # trailer
                                t = 'trailer'
                            if (ex_beam_slot > 99999 and ex_beam_slot < 100170):  # leader
                                t = 'leader'
                            else:
                                if ex_beam_slot < self.reel.n_slots:
                                    t = 'slot'
                        else:
                            t = cfg['slot_type']

                        offset = cfg['beam']['offset']
                        if cfg['reel']['barcode_side'] == 'left':
                            pbcs = numpy.array([self.reel.offset_slot_id(ex_beam_slot,t,offset-x)[0] for x in range(9,-7,-1)])
                        else:
                            pbcs = numpy.array([self.reel.offset_slot_id(ex_beam_slot,t,x-offset)[0] for x in range(7,-7,-1)])
                    # approximate barcodes from our range
                    logger.info("%s"%pbcs)
                    bcs = itfbarcode.linescan.scan_approximate(vs,svs,{'possible_bcs': pbcs})
                    # More efficient to list slots here
                    if len(bcs):
                        mid_ind = len(bcs) / 2
                        isd = cfg['slot_finding'].get('inter_slot_distance', 745)
                        if cfg['reel']['barcode_side'] == 'left':
                            bc_c = len(vs) - int(bcs[mid_ind].center)
                        else:
                            bc_c = int(bcs[mid_ind].center)
                        self._slot_list = range(bc_c % isd, len(vs), isd)
                if self._slot_list is None or not len(self._slot_list):
                    #If we found no barcodes we should at least find some slots
                    logger.info("SLOT FINDING")
                    self._find_slots(frame)

            else:
                logger.info("image too dark: %s", dv)
                bcs = []
        

        if not len(bcs) and (self._slot_list is None or not len(self._slot_list)):
            self._processing = False
            if self._bcf is not None:
                self._bcf.set_result([])
                self._bcf = None
            return
        x = (xs + xe) / 2.
       
        # Check if barcodes are lined up with slots
        if len(self._slot_list):
            bc_vals = -1*numpy.ones(len(self._slot_list))
            min_dist = cfg['slot_finding'].get('max_barcode_distance', 200)
            logger.info("VS_SIZE: %s | Barcodes read: %s" %( len(vs), bcs ) )
            for bc in bcs:
                if cfg['reel']['barcode_side'] == 'left':
                    bc_y = len(vs) - bc.center
                else:
                    bc_y = bc.center
                min_index = min(range(len(self._slot_list)), key = lambda i: abs(self._slot_list[i] - bc_y))
                dist = abs(self._slot_list[min_index] - bc_y)
                logger.info("DISTANCE From expected %d"%dist)
                if dist < min_dist:
                    if bc_vals[min_index] == -1:
                        logger.debug("Two bc values found for slot_index %d. %d , %d" % (min_index, bc_vals[min_index], bc.value))
                    bc_vals[min_index] = bc.value
            bci = [{
                # TODO: get this right, not sure who uses it
                'width': 100,
                'y': self._slot_list[i], 'x': x,
                'value': bc_vals[i], 'frame': self._frame_count,
                'time': time.time()} for i in range(len(bc_vals))]
        else:
            bci = [{
                'width': bc.width,
                'y': bc.center, 'x': x,
                'value': bc.value, 'frame': self._frame_count,
                'time': time.time()} for bc in bcs]
        # TODO if > 1 barcode (or reel version 2) define position
        self.last_barcodes = bci
        self.new_barcodes.emit(bci)
        #if not len(bcs):
        #     self._processing = False
        #     if self._bcf is not None:
        #         self._bcf.set_result(bci)
        #         self._bcf = None
        #     logger.info("Return No barcodes")
        #     return
        logger.info("Comput beam Slot")
        self._compute_beam_slot()

        # get image for each slot
        if 'slot_image' in cfg and cfg['slot_image'].get('enable', False):
            x_offset = cfg['slot_image']['offset']
            shape = cfg['slot_image']['shape']
            for bc in bci:
                x, y = bc['x'], bc['y']
                if cfg['reel']['barcode_side'] == 'left':
                    x += x_offset
                else:
                    x -= x_offset
                y -= shape[0] / 2
                x -= shape[1] / 2
                crop = [[y, y + shape[0]], [x, x + shape[1]]]
                ccrop = montage.ops.transform.cropping.clip_crop(
                    crop, frame.shape[:2])
                # only get section images for full crops
                #logger.debug("slot_image crop: %s", crop)
                #logger.debug("slot_image ccrop: %s", ccrop)
                #logger.debug(
                #    "slot_image cal crop: %s",
                #    montage.ops.transform.cropping.calculate_crop(
                #        frame, crop))
                if (crop == ccrop):
                    sim = montage.io.Image(
                        montage.ops.transform.cropping.crop(frame, crop),
                        {'barcode': bc, 'crop': crop})
                    logger.debug("slot_image shape: %s", sim.shape)
                    self.new_slot_image.emit((sim, sim.meta))

        self._processing = False
        # set future
        if self._bcf is not None:
            self._bcf.set_result(bci)
            self._bcf = None

    def _compute_beam_slot(self):
        cfg = self.config()
        bcs = self.last_barcodes
        # if we cant read any barcodes we cant compute a beam slot.
        # This can be done on the MoveSlotSM given the history
        bad_bcs = numpy.array([bc['value'] == -1 for bc in bcs])
        if all(bad_bcs):
            logger.error("TapecameraNode[%s] _compute_beam_slot no barcodes read")
            return
        # first find index of desired barcode
        targ_index = min(range(len(bcs)), key=lambda i: abs(bcs[i]['y'] - cfg['beam']['target_y']) )
        delta_y = cfg['beam']['target_y'] - bcs[targ_index]['y']
        if bcs[targ_index]['value'] != -1:
            logger.info("Ideal barcode read")
            mbc = bcs[targ_index]
            doffset = 0
        else:
            logger.info("WHAT THESE %s" % bad_bcs)
            possible_inds = numpy.where(~bad_bcs)[0]
            new_index = min(possible_inds, key=lambda i: abs(i - targ_index))
            logger.info(new_index)
            logger.info(possible_inds)
            mbc = bcs[new_index]
            # doffset is positive if read index is closer to the reel
            doffset = targ_index - new_index

        logger.info(mbc)
        logger.info(doffset)
        # get the offset
        offset = cfg['beam']['offset']
        if cfg['reel']['barcode_side'] == 'left':
            # offset gets bigger by the delta
            offset = -cfg['beam']['offset'] - doffset
        elif cfg['reel']['barcode_side'] == 'right':
            # offset gets bigger from the delta
            offset = cfg['beam']['offset'] + doffset
        else:
            logger.error(
                "TapecameraNode[%s] _compute_beam_slot "
                "invalid barcode_side: %s",
                self, cfg['reel']['barcode_side'])
            return
        logger.info("OFFSET")
        logger.info(offset)
        cfg = self.config()
        #y_threshold = cfg['beam']['y_threshold']
        #if mbc['y'] < y_threshold[0] or mbc['y'] > y_threshold[1]:
        #    logger.error(
        #        "TapecameraNode[%s] _compute_beam_slot "
        #        "closest barcode near target: %s, %s",
        #        self, mbc['y'], y_threshold)
        #    return

        # infer type if reel is v2
        if cfg['reel']['version'] == 2:
            if (mbc['value'] > 199999 and mbc['value'] < 200170):  # trailer
                mbc['type'] = 'trailer'
            if (mbc['value'] > 99999 and mbc['value'] < 100170):  # leader
                mbc['type'] = 'leader'
            else:
                if mbc['value'] < self.reel.n_slots:
                    mbc['type'] = 'slot'
        else:
            mbc['type'] = cfg['slot_type']

        # validate barcode number against reel version
        try:
            self.reel.validate_slot_id(
                int(mbc['value']), mbc['type'])
        except reel.ReelError as e:
            logger.error(
                "TapecameraNode[%s] _compute_beam_slot "
                "invalid barcode: %s, %s [%s]",
                self, mbc['value'], mbc['type'], e)
            return

        offset_value, offset_type = self.reel.offset_slot_id(
            int(mbc['value']), mbc['type'], offset)

        bc = mbc.copy()
        bc['time'] = time.time()
        bc['value'] = offset_value
        bc['type'] = offset_type
        bc['index'] = self.reel.slot_id_to_index(
            offset_value, offset_type)
        # the y value of this will be the amount the mover has to move
        bc['y'] =  delta_y
        logger.info(
            "TapecameraNode[%s] _compute_beam_slot found barcode %s",
            self, bc)
        self.set_beam_slot(bc)

    # expose reel for other nodes to use
    def call_reel(self, func, *args, **kwargs):
        return getattr(self.reel, func)(*args, **kwargs)
