#!/usr/bin/env python

import os

from . import base

from .. import log


logger = log.get_logger(__name__)


def require(d, k):
    if k not in d:
        logger.error("Invalid config: %s missing from %s", k, d)
        raise base.ConfigError("{} missing from config {}".format(
            k, d))


def save_directory_ok(directory, n_bytes=None, margin_bytes=1024):
    sdir = os.path.abspath(os.path.expanduser(directory))
    if not os.path.exists(sdir):
        err = "Save directory %s does not exist" % sdir
        logger.warning(err)
        return False, err
    if not os.path.isdir(sdir):
        err = "Save directory %s is not a directory" % sdir
        logger.warning(err)
        return False, err
    if not os.access(sdir, os.X_OK | os.W_OK):
        err = "Save directory %s not writable/executable" % sdir
        logger.warning(err)
        return False, err
    if n_bytes is not None:
        fsi = os.statvfs(sdir)
        bytes_avail = (fsi.f_bsize * fsi.f_bavail)
        if (bytes_avail - margin_bytes < n_bytes):
            err = (
                "Not enough space on disk with save directory [%s]: %s < %s" %
                (sdir, bytes_avail, n_bytes))
            logger.warning(err)
            return False, err
    return True, ''
