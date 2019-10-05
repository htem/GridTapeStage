#!/usr/bin/env python

import Queue
import threading
import time

import numpy

has_picamera = True
try:
    import picamera
except ImportError as e:
    has_picamera = False

from .. import log

print_timing = False

logger = log.get_logger(__name__)


def round_resolution(r):
    return (
        (r[0] + 31) // 32 * 32,
        (r[1] + 15) // 16 * 16)

if has_picamera:
    class PiCam(picamera.PiCamera):
        def __init__(self, *args, **kwargs):
            super(PiCam, self).__init__(*args, **kwargs)
            r = self.resolution
            self._fmt = 'rgba'
            self._resize = None
            self._roi = (0, 0, r[0], r[1])
            self.resolution = r

        def _setup_buffer(self, res):
            roi = self._roi
            rroi = round_resolution((roi[2], roi[3]))
            rres = round_resolution(res)
            ndim = len(self._fmt)
            self._ro = numpy.empty((rres[1] * rres[0] * ndim), dtype='uint8')
            nroi = rroi[0] * rroi[1] * ndim
            self._o = self._ro.view('uint8')[:nroi].reshape(
                (rroi[1], rroi[0], ndim))[:roi[3], :roi[2], :]
            self._resize = rroi

        @picamera.PiCamera.resolution.setter
        def resolution(self, res):
            picamera.PiCamera.resolution.fset(self, res)
            self.roi = self.roi
            self._setup_buffer(res)

        #@picamera.PiCamera.resolution.getter
        #def resolution(self):
        #    return tuple(picamera.PiCamera.resolution.fget(self))

        #@picamera.PiCamera.framerate.getter
        #def framerate(self):
        #    return tuple(picamera.PiCamera.framerate.fget(self))

        @property
        def roi(self):
            return self._roi

        @roi.setter
        def roi(self, roi):
            # TODO error check
            res = self.resolution
            w, h = (roi[2], roi[3])
            if w == -1:
                w = res[0]
            if h == -1:
                h = res[1]
            # round roi
            w, h = round_resolution((w, h))
            roi = [roi[0], roi[1], w, h]
            self.zoom = (
                roi[0] / float(res[0]),
                roi[1] / float(res[1]),
                roi[2] / float(res[0]),
                roi[3] / float(res[1]),
            )
            self._roi = roi
            self._setup_buffer(res)

        @property
        def fmt(self):
            return self._fmt

        @fmt.setter
        def fmt(self, fmt):
            self._fmt = fmt
            self._setup_buffer(self.resolution)

        def capture(self):
            super(PiCam, self).capture(
                self._ro, self._fmt, resize=self._resize)
            return self._o


class CaptureThread(threading.Thread):
    def __init__(self, capture_id=-1):
        self.stop_event = threading.Event()
        self.capture_id = capture_id
        self.queue = Queue.Queue(maxsize=10)
        self.cmds = Queue.Queue(maxsize=10)
        self.results = Queue.Queue(maxsize=10)
        super(CaptureThread, self).__init__()

    def run(self):
        cam = PiCam()
        last_frame_time = time.time()
        while not self.stop_event.is_set():
            t0 = time.time()
            try:
                a = cam.capture()
            except Exception as e:
                # If the capture fails (timeout) we will try
                # to continue to the next capture. Not sure
                # if this will work.
                logger.error( "PiCam[%s] capture error, continuing %s"
                               , self, e)
                continue
            t1 = time.time()
            if self.queue.full():
                self.queue.get()
            self.queue.put(a)
            t2 = time.time()
            if not self.cmds.empty():
                cmd = self.cmds.get()
                n = cmd[1]
                r = None
                if not hasattr(cam, n):
                    r = Exception("invalid property: %s" % n)
                else:
                    if cmd[0] == 'get':
                        try:
                            r = getattr(cam, n)
                            if n in ('resolution', 'framerate'):
                                r = tuple(r)
                        except Exception as e:
                            r = e
                    else:
                        try:
                            setattr(cam, n, cmd[2])
                        except Exception as e:
                            r = e
                self.results.put((n, r))
            t3 = time.time()
            if print_timing:
                print("capture: %0.4f" % (t1 - t0))
                print("queue  : %0.4f" % (t2 - t1))
                print("cmds   : %0.4f" % (t3 - t2))
                fps = 1. / (t2 - last_frame_time)
                print("fps    : %0.2f" % fps)
                last_frame_time = t2

        print("Releasing capture")
        cam.close()
        del cam

    def get_property(self, name):
        self.cmds.put(('get', name))
        r = self.results.get()
        if r[0] != name:
            raise Exception
        return r[1]

    def set_property(self, name, value):
        self.cmds.put(('set', name, value))
        r = self.results.get()
        if r[1] is not None:
            raise r[1]

    def stop(self):
        print("CaptureThread.stop called")
        self.stop_event.set()

    def get_frame(self, recent=False, wait=False):
        try:
            f = self.queue.get(wait)
            if not recent:
                return f
            while not self.queue.empty():
                f = self.queue.get(wait)
        except Queue.Empty:
            return None
        return f


class FakeCaptureThread(CaptureThread):
    def __init__(self, capture_id=-1):
        super(FakeCaptureThread, self).__init__(capture_id)
        # TODO setup filename property?

    def run(self):
        #n_till_fail = 100
        blank_frame = numpy.zeros((2592, 1944, 3), dtype='uint8')
        while not self.stop_event.is_set():
            #n_till_fail -= 1
            #if n_till_fail < 0:
            #    raise Exception("Fail")
            # TODO read frame from somewhere
            frame = blank_frame
            if self.queue.full():
                self.queue.get()
            self.queue.put(frame)
            if not self.cmds.empty():
                cmd = self.cmds.get()
                self.results.put((cmd[0], None))
            # throttle
            time.sleep(0.10)
