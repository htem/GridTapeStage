#!/usr/bin/env python

import os
import time
import threading
import Queue
import weakref

import numpy

from ... import log
from . import raw

thread_timeout = 0.01

logger = log.get_logger(__name__)


def resolve_filename(meta, fn_format, directory=None):
    try:
        fn = fn_format.format(**meta)
    except KeyError as E:
        logger.error("resolve_filename %s meta data missing: %s",
                     meta, fn_format, exc_info=True)
        raise KeyError(
            "Meta data missing {}, cannot form filename {}".format(
                E.message, fn_format))
    if directory is not None:
        return os.path.join(directory, fn)
    return fn


def raw_save(im, fn_format, directory=None):
    raw.write_tif(
        resolve_filename(im.meta, fn_format, directory), im, **im.meta)


class Saver(object):
    def __init__(self, directory=None, dtype=None):
        self._directory = directory
        if dtype is None:
            dtype = numpy.dtype('u2')
        self._dtype = dtype

    @property
    def directory(self):
        return self._directory

    @directory.setter
    def directory(self, value):
        self._directory = value

    def save_image(self, im, fn_format):
        pass

    def save_images(self, ims, fn_format):
        pass


class FakeSaver(Saver):
    pass


class TifSaver(Saver):
    def __init__(self, directory=None, dtype=None):
        super(TifSaver, self).__init__(directory, dtype)

    @Saver.directory.setter
    def directory(self, value):
        if value is not None and not os.path.exists(value):
            os.makedirs(value)
        self._directory = value

    def save_image(self, im, fn_format):
        if im.dtype != self._dtype:
            raw_save(im.astype(self._dtype), fn_format, self.directory)
        else:
            raw_save(im, fn_format, self.directory)

    def save_images(self, ims, fn_format):
        [self.save_image(im, fn_format) for im in ims]


def _save_thread(weak_self, dtype):
    while True:
        self = weak_self()
        if self is None:
            break
        if self._stop.is_set():
            break
        try:
            # get next images in queue
            ims, fnf = self._queue.get(True, thread_timeout)
            for (i, im) in enumerate(ims):
                im.meta['grab'] = i
                im.meta['x'] = im.meta.get('x', 0)
                im.meta['y'] = im.meta.get('y', 0)
                im.meta['row'] = im.meta.get('row', 999)
                im.meta['col'] = im.meta.get('col', 999)
                # save them
                if im.dtype != dtype:
                    raw_save(im.astype(dtype), fnf, self.directory)
                else:
                    raw_save(im, fnf, self.directory)
            self._queue.task_done()
        except Queue.Empty:
            pass
        del self


class ThreadedSaver(TifSaver):
    def __init__(self, directory=None, dtype=None):
        super(ThreadedSaver, self).__init__(directory, dtype)
        self._thread = None
        self._queue = Queue.Queue()
        self._stop = threading.Event()
        self._stop.clear()
        self._start_thread()

    def _start_thread(self):
        if self._thread is not None:
            self._stop_thread()

        self._thread = threading.Thread(
            target=_save_thread, args=(weakref.ref(self), self._dtype))
        self._thread.daemon = True
        logger.debug("ThreadedSaver[%s] starting thread", self)
        self._thread.start()
        logger.debug("ThreadedSaver[%s] thread started", self)

    def _stop_thread(self):
        if self._thread is None:
            return
        logger.debug("ThreadedSaver[%s] stopping thread", self)
        self._stop.set()
        time.sleep(thread_timeout * 2)
        logger.debug("ThreadedSaver[%s] joining thread", self)
        self._thread.join()
        logger.debug("ThreadedSaver[%s] thread joined", self)
        self._thread = None

    def save_image(self, im, fn_format):
        self.save_images([im, ], fn_format)

    def save_images(self, ims, fn_format):
        logger.debug("ThreadedSaver[%s] save_image", self)
        #for i in ims:
        #    logger.debug(
        #        "save_images filename: %s" %
        #        resolve_filename(i.meta, fn_format))
        if not isinstance(ims, (list, tuple)):
            raise ValueError(
                "save_images expects a list or tuple not %s" % (type(ims)))
        #logger.debug(
        #    "ThreadedSaver[%s] metric %s",
        #    self, ims[0].meta.get('metric', None))
        self._queue.put((ims, fn_format))

    def __del__(self):
        logger.debug("ThreadedSaver[%s] __del__", self)
        self._stop_thread()
