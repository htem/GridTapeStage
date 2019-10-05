#!/usr/bin/env python
"""
Montager node

Does the following:
    - controls camera nodes (cooling, config)
    - single grabs (from all cameras)
    - [stateful] background grabbing routine
    - [stateful] streaming
    - controls motion node (move, etc)
    - [stateful] bake
    - [stateful] montage
    - roi configuration

Stream:
    repeated calls to start_streaming
    stop -> remove loop callbacks to stop repeat calls

Background grab: {TODO move during grab}
    1) grab_background
    2) trigger_background_grab
    3) finish_background_grab (if more, goto 2 else 4)
    4) compute background

Bake:
    1) bake
    2) bake_move (also grabs) (if more pts, repeat, else goto 3)
    3) bake_finished

Montage:
    1) montage
    2) montage_start (calls montage_setup)
    3) montage_move (if no pts, goto 6)
    4) montage_queue_grabs
    5) montage_check_grabs (goto 3)
    6) montage_end (if more rois, goto montage_start)

Stateful variables:
    - config
    - _has_bg
    - pts
    - tiles
    - frames
    - frames_stats
    - test_grab_index (?)
    - stop
    - state
    - montaging
    - stream
"""

import copy
import json
import os
import time

import numpy
import pizco

import montage
import smaract

from . import base
from .. import config
from ..config.checkers import require
from ..imaging import montaging
from .. import log


default_config = {
    "addr": 'tcp://127.0.0.1:11000',
    'motion': {
        'addr': 'tcp://127.0.0.1:11010',
    },
    'cameras': [
        {
            'addr': 'tcp://127.0.0.1:11020',
        },
    ],
    'montage': {
        'method': 'pull',  # see montaging.planning.calculate_coordinates
        'fast_axis': 'x',
        #'fov': [15250, 15250],
        #'fov': [17075, 17075],  # based off of ~151030
        'fov': [16000, 16000],  # based off of ~151030
        'overlap': [0.2, 0.2],
        #'roi_index': 0,
        'roi': {
            #'left': -500000, 'right': 500000,
            #'top': -500000, 'bottom': 500000},
            'center': [0, 850000],
            'width': 50000, 'height': 50000,
        },
        'use_vertices': True,
    },
    'settling_time': {
        # 'x': 0.025,
        'x': 0.080,
        # 'y': 0.1,
        'y': 0.3,
        'wait': True,
        'poll': False,
        'hold': 60000,
        'jump': True,
        #'row_jump': False,
        #'jump_steps': [10, ],
        'jump_size': 160000,
    },
    'bake': {
        'time': 0.01,
        'overlap': [0.0, 0.0],
        'skip': 2,
        'grab_background': True,
        'fail_on_n_errors': 5,
        #'auto_montage': False,
    },
    'session': {
        'name': "test",
        'notes': "",
        # 'fresh': True,
        'bake': {},
        'montage': {},
        # other meta data here?
    },
    'background': {
        'nframes': 128,
        'manual_frames': 16,
    },
    'save': {
        'directory': '/data',
        'bytes_per_location': 36000000,  # 9 MB / camera = 36 MB
        'bytes_margin': 1000000000,  # 1 GB
        'frames': True,
        'on_fail': True,
        'log_level': 10,  # 10 = DEBUG
    },
    'slot_center': {
        'x': 0,
        'y': 0,
    },
    'kill_on_nodata': False,  # raise error at end of montage if AT_ERR_NODATA
}


logger = log.get_logger(__name__)


def compute_points(mcfg, bcfg=None):
    if bcfg is None:
        bcfg = {}
    # resolve unknowns of roi
    roi = montaging.roi.resolve(**mcfg['roi'])
    for k in mcfg:
        if k != 'roi':
            roi[k] = bcfg.get(k, mcfg[k])
    pts = montaging.planning.calculate_coordinates(roi)
    return pts


class GrabBackgroundSM(base.StateMachine):
    # TODO slow move while grabbing
    def setup(self):
        return None


class BakeSM(base.StateMachine):
    def setup(self):
        cfg = self.node.config()
        self.node.config({'session': {'bake': {'start': time.time()}}})
        self.n_consecutive_errors = 0
        self.fail_on_n_errors = cfg['bake'].get('fail_on_n_errors', 5)
        # tell cameras to stop streaming
        [c.stop_streaming() for c in self.node.cameras]
        # calculate bake points (with skips) [x, y, r, c, g?]
        pts = compute_points(cfg['montage'], cfg['bake'])
        self.pts = montaging.planning.skip_points(
            pts[::-1], cfg['bake']['skip'])
        # if a background should be grabbed
        grab_indices = []
        if cfg['bake']['grab_background']:
            # clear background
            [c.set_background(None) for c in self.node.cameras]
            grab_indices = montaging.planning.distribute(
                cfg['background']['nframes'], self.pts)
        # mark points that should have a 'grab'
        pts = []
        for (i, p) in enumerate(self.pts):
            pts.append(p + (i in grab_indices, ))
        self.pts = pts
        return 'move'

    def move(self):
        # if no points, return
        if len(self.pts) == 0:
            return 'finish'
        x, y, _, _, g = self.pts.pop(0)
        self.node.motion.move(x, y, wait=False, poll=False, hold=0)
        if g:
            # queue grab
            grabs = [
                c.trigger_background_grab() for c in self.node.cameras]
        # wait till done moving?
        try:
            self.node.motion.poll_position(wait=True)
            self.n_consecutive_errors = 0
        except smaract.async.EndStopError as e:
            # stage didn't make it to the commanded position
            # only error out if > N of these happen in a row
            logger.error("EndStopError[%s] %s %s", e, x, y)
            self.n_consecutive_errors += 1
            if self.n_consecutive_errors > self.fail_on_n_errors:
                raise e
            # otherwise, just continue to move to next location
        if g:
            return 'move', grabs
        return 'move', self.node.config()['bake']['time']

    def finish(self):
        self.node.motion.poll_position(wait=True)
        if self.node.config()['bake']['grab_background']:
            self.node.compute_background()
        self.node.config({'session': {'bake': {'finish': time.time()}}})
        return None


class MontageSM(base.StateMachine):
    def setup(self):
        cfg = self.node.config()
        self.tiles = []
        # record start time
        start_time = time.localtime()
        [c.stop_streaming() for c in self.node.cameras]
        pts = compute_points(cfg['montage'])
        # pre-compute dr dc moves
        self.n_vetos = 0
        self.pts = []
        pp = None
        for (i, p) in enumerate(pts):  # make pts: x, y, r, c, dr, dc, i
            dr = False
            dc = False
            if pp is None or pp[2] != p[2]:
                dr = True
            if pp is None or pp[3] != p[3]:
                dc = True
            self.pts.append(p + (dr, dc, i))
            pp = p

        # move to postion 0
        x, y, _, _, _, _, _ = self.pts[0]
        self.node.motion.move(x, y, wait=True, poll=True, hold=60000)
        # jump?
        if cfg['settling_time']['jump']:
            x2, y2, _, _, _, _, _ = self.pts[1]
            jump_x = cfg['settling_time']['jump_size']
            if x2 < x:  # determine safe direction from next point
                jump_x = -jump_x
            self.node.motion.move(jump_x, wait=True, poll=False, relative=True)
            self.node.motion.move(x, y, wait=True, poll=True, hold=60000)

        # determine session name
        name = cfg['session'].get('name', None)
        session_name = time.strftime('%y%m%d%H%M%S', start_time)
        if name is not None:
            session_name = "_".join((session_name, name))

        # set directory to session name
        save_cfg = cfg.get('save', {}).copy()

        # check save directory
        r, e = self.node.check_save_directory(
            save_cfg['directory'], npts=len(self.pts))
        if not r:
            raise IOError(e)

        ## estimate size of montage
        #n_bytes = len(self.pts) * cfg['save']['bytes_per_location']

        ## check disk access & space
        #r, e = config.checkers.save_directory_ok(
        #    save_cfg['directory'],
        #    n_bytes + save_cfg['bytes_margin'])
        #if not r:
        #    # change to next directory
        #    raise IOError(e)

        # check that all camera nodes see and have ok access to save dir
        #for (i, n) in enumerate(self.node.cameras):
        #    r, e = n.ok_to_save(
        #        save_cfg['directory'],
        #        n_bytes + save_cfg['bytes_margin'])
        #    if not r:
        #        raise IOError("Camera[%i:%s]: %s" % (i, n, e))

        # set save directory to session name
        save_dir = os.path.join(
            cfg['save']['directory'], session_name)
        save_cfg['directory'] = save_dir

        # start logging
        log_level = cfg['save'].get('log_level', None)
        for n in [self.node, self.node.motion] + self.node.cameras:
            n.start_logging(save_dir, log_level)

        # configure cameras
        for c in self.node.cameras:
            c.restart_acquisition()
            c.config({'save': save_cfg})
            c.save_image_metrics()

        # save config files
        config.parser.save(
            self.node.motion.config(), os.path.join(
                save_dir, session_name + '_motion.json'))
        for (i, c) in enumerate(self.node.cameras):
            config.parser.save(
                c.config(), os.path.join(
                    save_dir, session_name + '_cam%i.json' % i))

        # report start of montage, size [nr x nc], etc
        # - name
        # - rows, cols
        # - save_dir
        n_rows = len(set([p[2] for p in self.pts]))
        n_cols = len(set([p[3] for p in self.pts]))
        sd = {
            'name': session_name,
            'directory': save_dir,
            'start': time.mktime(start_time),
            'size': (n_rows, n_cols),
            'n_tiles': len(self.pts),
        }
        self.node.new_session.emit(sd)

        self.node.config({'session': {'montage': sd}})
        #self.node.config({'session': {
        #    'montage': {
        #        'name': session_name,
        #        'directory': save_dir,
        #        'start': time.mktime(start_time),
        #        'size': (n_rows, n_cols),
        #        'n_tiles': len(self.pts),
        #    }}})
        return 'move'

    def move(self):
        if len(self.pts) == 0:
            #if not all([c.ready_to_grab() for c in self.node.cameras]):
            #    logger.warning(
            ##        "Cameras were not ready to grab... delaying finish")
            #    # if not, call check_grabs after a short delay
            #    return 'move', 0.001
            return 'finish'
        cfg = self.node.config()
        x, y, r, c, dr, dc, i = self.pts.pop(0)
        # move only necessary axes
        # get wait, poll, hold from cfg
        mkwargs = {
            'wait': cfg['settling_time']['wait'],
            'poll': cfg['settling_time']['poll'],
            'hold': cfg['settling_time']['hold'],
        }
        settle = None
        if dr and dc:
            mr = self.node.motion.move(x=x, y=y, **mkwargs)
            settle = max(cfg['settling_time']['x'], cfg['settling_time']['y'])
        elif dr:
            mr = self.node.motion.move(y=y, **mkwargs)
            settle = cfg['settling_time']['y']
            # TODO jump?
        elif dc:
            mr = self.node.motion.move(x=x, **mkwargs)
            settle = cfg['settling_time']['x']
        else:
            # TODO error?
            mr = None
        self.meta = {
            'x': x, 'y': y, 'row': r, 'col': c,
            'loc': i,
            'settle': settle}
        if mr is not None:
            self.meta['x'] = mr.get('x', x)
            self.meta['y'] = mr.get('y', y)
        if settle is None:
            return 'grab'
        t0 = time.time()
        while time.time() - t0 < settle:
            [c.update_controller() for c in self.node.cameras]
        #return 'grab', settle
        return 'grab'

    def grab(self):
        # check buffers are available
        if not all([c.ready_to_grab() for c in self.node.cameras]):
            # if not, call check_grabs after a short delay
            logger.warning("Cameras were not ready to grab... delaying grab")
            [c.update_controller() for c in self.node.cameras]
            return 'grab', 0.001
        # start grabs
        meta = self.meta.copy()
        self.grabs = [c.start_grab(meta) for c in self.node.cameras]
        self.grab_results = {}
        # attach done callbacks to store vetos
        for g in self.grabs:
            g.add_done_callback(self.grab_done)
            self.grab_results[g] = None
        #for (i, g) in enumerate(self.grabs):
        #    g.add_done_callback(lambda f, index=i: self.grab_done(f, i))
        return 'check_grabs', self.grabs

    def grab_done(self, grab):
        logger.debug("grab_done: %s", grab)
        if grab.exception() is not None:
            raise grab.exception()
        self.grab_results[grab] = grab.result()
        #self.grab_results[index] = grab.result()

    def check_grabs(self):
        # vetos, regrabs, vetoed
        logger.debug("check_grabs: %s", self.grab_results)
        tile = {
            'vetoed': False, 'regrabs': 0, 'vetos': [],
            'meta': self.meta.copy()}
        for g in self.grabs:
            valid, reason = self.grab_results[g]
            if valid:
                tile['vetos'].append(None)
            else:
                tile['vetos'].append(reason)
                tile['vetoed'] = True
                self.n_vetos += 1
            tile['regrabs'] = max(tile['regrabs'], reason.get('regrabs', 0))
        # send new tile
        self.tiles.append(tile)
        self.node.new_tile.emit(tile)
        return 'move'

    def finish(self):
        cfg = self.node.config()
        nodatas = [c.finish_grab() for c in self.node.cameras]
        n_nodatas = 0
        for n in nodatas:
            if n is not None:
                n_nodatas += len(n)

        end_time = time.localtime()
        # stop logging
        for n in [self.node, self.node.motion] + self.node.cameras:
            n.stop_logging()

        # save tiles
        tiles_fn = os.path.join(
            cfg['session']['montage']['directory'],
            cfg['session']['montage']['name'] + '_tiles.json')
        config.parser.save(self.tiles, tiles_fn)

        # poll position
        self.node.motion.poll_position()

        # get end time
        self.node.config({
            'session': {
                'montage': {
                    'nodatas': nodatas,
                    'n_nodatas': n_nodatas,
                    'tiles': tiles_fn,
                    'n_vetos': self.n_vetos,
                    'finish': time.mktime(end_time)}}})

        cfg = self.node.config()
        # save configs [at_end, finished]
        config.parser.save(
            cfg, os.path.join(
                cfg['session']['montage']['directory'],
                cfg['session']['montage']['name'] + '_finished.json'))

        self.node.new_session.emit(None)
        if cfg.get('kill_on_nodata', False):
            for (i, e) in enumerate(nodatas):
                if e is not None:
                    raise Exception(
                        "Nodata: camera %s buffer %s" % (i, e))
        return None


class MontagerNode(base.StatefulIONode):
    """
    State machines:
        - grab BG
        - bake
        - montage
    """
    def __init__(self, cfg=None):
        super(MontagerNode, self).__init__(cfg)
        cfg = self.config()
        logger.info("MontagerNode[%s] proxying motion %s", self, cfg['motion'])
        self.motion = base.proxy(cfg['motion'])
        logger.info("MontagerNode[%s] proxying cameras %s", self,
                    cfg['cameras'])
        for i in xrange(len(cfg['cameras'])):
            cfg['cameras'][i]['index'] = i  # to make this 0 based
        self.config(cfg)
        self.cameras = [base.proxy(c) for c in cfg['cameras']]
        self.new_position = pizco.Signal(nargs=1)
        self.position_callback = self.motion.new_position.connect(
            lambda p: self.new_position.emit(p))

        #self.tiles = []
        self.new_tile = pizco.Signal(nargs=1)
        self.new_session = pizco.Signal(nargs=1)

    def __del__(self):
        self.motion.new_position.disconnect(self.position_callback)
        super(MontagerNode, self).__del__()

    def __repr__(self):
        cfg = self.config()
        return "{}.{} at {} addr {}".format(
            self.__module__, self.__class__, hex(id(self)),
            cfg.get('addr', ''))

    def check_config(self, cfg=None):
        return

    def config_delta(self, delta):
        pass

    def connect(self, node_type=None, index=None):
        logger.info("MontagerNode[%s] connect", self)
        self.check_config()
        if node_type in (None, 'motion'):
            logger.info("MontagerNode[%s] connecting to motion", self)
            self.motion.connect()
        if node_type in (None, 'camera'):
            logger.info("MontagerNode[%s] connecting to cameras", self)
            if index is None:
                [c.connect() for c in self.cameras]
            else:
                if (not isinstance(index, int)) or (index < 0) or \
                        (index > len(self.cameras)):
                    raise ValueError(
                        "Invalid camera index {} not in [0, {})".format(
                            index, len(self.cameras)))
                self.cameras[index].connect()

    def disconnect(self, node_type=None, index=None):
        logger.info("MontagerNode[%s] disconnect", self)
        #if self.montaging:
        #    logger.warning(
        #        "MontagerNode[%s] is montaging, disconnect canceled")
        #    return
        if node_type in (None, 'motion'):
            logger.info("MontagerNode[%s] disconnecting from motion", self)
            self.motion.disconnect()
        if node_type in (None, 'camera'):
            logger.info("MontagerNode[%s] disconnecting from cameras", self)
            if index is None:
                [c.disconnect() for c in self.cameras]
            else:
                if (not isinstance(index, int)) or (index < 0) or \
                        (index > len(self.cameras)):
                    raise ValueError(
                        "Invalid camera index {} not in [0, {})".format(
                            index, len(self.cameras)))
                self.cameras[index].disconnect()

    def connected(self, node_type=None, index=None):
        if node_type is None:
            return self.motion.connected() and \
                all(c.connected() for c in self.cameras)
        if node_type == 'motion':
            return self.motion.connected()
        if node_type == 'camera':
            if index is None:
                return all(c.connected() for c in self.cameras)
            else:
                if (not isinstance(index, int)) or (index < 0) or \
                        (index > len(self.cameras)):
                    raise ValueError(
                        "Invalid camera index {} not in [0, {})".format(
                            index, len(self.cameras)))
                return self.cameras[index].connected()

    def kill(self):
        self.set_state(None)

    def compute_background(self, save=False):
        logger.debug("MontagerNode[%s] compute_background: %s", self, save)
        scalar = min([
            c.compute_background(save=False) for c in self.cameras])
        # use min of the means of the means to help normalize contrast
        # across cameras
        [c.compute_background(scalar=scalar, save=False) for c in self.cameras]
        self.config({'session': {'montage': {'bg': time.time()}}})

    def grab_background(self):
        self.attach_state_machine(
            GrabBackgroundSM, 'setup')

    def bake(self):
        self.new_tile.emit([])
        self.attach_state_machine(
            BakeSM, 'setup')

    def montage(self):
        self.new_tile.emit([])
        self.attach_state_machine(
            MontageSM, 'setup')

    def check_save_directory(self, directory, next_directory=None, npts=None):
        cfg = self.config()
        if npts is None:
            npts = len(compute_points(cfg['montage']))
        n_bytes = (
            npts * cfg['save']['bytes_per_location']
            + cfg['save']['bytes_margin'])
        r, e = config.checkers.save_directory_ok(
            directory, n_bytes)
        if not r:
            if next_directory is not None:
                # check next
                return self.check_save_directory(
                    next_directory, npts=npts)
            else:  # no next
                return False, e
        # check cameras
        for (i, n) in enumerate(self.cameras):
            r, e = n.ok_to_save(directory, n_bytes)
            if not r:
                if next_directory is not None:
                    # check next
                    return self.check_save_directory(
                        next_directory, npts=npts)
                else:  # no next
                    return False, e
        return True, directory

    # TODO un-pollute this node by removing call-throughs to motion node
    #def poll_position(self, wait=True, machine=False):
    #    return self.motion.poll_position(wait=wait, machine=machine)
    def poll_position(self, wait=True):
        return self.motion.poll_position(wait=wait)

    #def move(self, x=None, y=None, wait=True, relative=False,
    #         poll=True, machine=False, hold=60000, safe=True):
    def move(self, x=None, y=None, wait=True, relative=False,
             poll=True, hold=60000, safe=True):
        if safe:
            if self.is_running():
                raise RuntimeError(
                    "Cannot move while in state: %s" % self.get_state())
        #return self.motion.move(
        #    x=x, y=y, wait=wait, relative=relative, poll=poll,
        #    machine=machine, hold=hold)
        return self.motion.move(
            x=x, y=y, wait=wait, relative=relative, poll=poll,
            hold=hold)

    # --------------------- roi ----------------------
    def clear_roi(self):
        self.config({'montage': 'roi'}, prune=True)
        self.config({'montage': {'roi': {}}})

    def set_roi(self, landmark, x=None, y=None):
        logger.debug(
            "MontagerNode[%s] set_roi %s, %s, %s",
            self, landmark, x, y)
        d = {}
        if landmark == 'center':
            if x is False:
                d['center'] = False
            else:
                d['center'] = [x, y]
                if x is None:
                    d['center'][0] = True
                if y is None:
                    d['center'][1] = True
        else:
            if '_' in landmark:
                i = iter((y, x))
                for k in landmark.split('_'):
                    v = i.next()
                    if v is None:
                        d[k] = True
                    else:
                        d[k] = v
            elif landmark in ('left', 'right', 'height', 'width'):
                d[landmark] = True if x is None else x
            elif landmark in ('top', 'bottom'):
                d[landmark] = True if y is None else y
        return self.set_roi_by_key(**d)

    def set_roi_by_key(
            self, left=None, right=None, top=None, bottom=None,
            center=None, width=None, height=None):
        logger.debug(
            "MontagerNode[%s] set_roi_by_key %s, %s, %s, %s, %s,"
            "%s, %s",
            self, left, right, top, bottom, center, width, height)
        fov = self.config()['montage']['fov']
        roi = self.config()['montage']['roi']
        p = self.motion.poll_position()
        if width is False and 'width' in roi:
            del roi['width']
        elif width is not None:
            roi['width'] = int(width)
        if height is False and 'height' in roi:
            del roi['height']
        elif height is not None:
            roi['height'] = int(height)
        if center is not None:
            if center is True:
                roi['center'] = [int(p['x']), int(p['y'])]
            elif center is False and 'center' in roi:
                del roi['center']
            else:
                roi['center'] = [0, 0]
                if center[0] is True:
                    roi['center'][0] = int(p['x'])
                else:
                    roi['center'][0] = int(center[0])
                if center[1] is True:
                    roi['center'][1] = int(p['y'])
                else:
                    roi['center'][1] = int(center[1])
        if left is not None:
            if left is True:
                roi['left'] = int(p['x'] - fov[0] / 2.)
            elif left is False and 'left' in roi:
                del roi['left']
            else:
                roi['left'] = int(left)
        if right is not None:
            if right is True:
                roi['right'] = int(p['x'] + fov[0] / 2.)
            elif right is False and 'right' in roi:
                del roi['right']
            else:
                roi['right'] = int(right)
        if top is not None:
            if top is True:
                roi['top'] = int(p['y'] - fov[1] / 2.)
            elif top is False and 'top' in roi:
                del roi['top']
            else:
                roi['top'] = int(top)
        if bottom is not None:
            if bottom is True:
                roi['bottom'] = int(p['y'] + fov[1] / 2.)
            elif bottom is False and 'bottom' in roi:
                del roi['bottom']
            else:
                roi['bottom'] = int(bottom)
        self.config({'montage': {'roi': roi}})


def test_node(config):
    n = MontagerNode(config)
    n.connect()
    n.disconnect()

if __name__ == '__main__':
    test_node(default_config)
