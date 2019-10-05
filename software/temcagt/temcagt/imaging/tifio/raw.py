#!/usr/bin/env python
"""
"""

import json
import datetime
import os

import libtiff
import numpy

from ... import config
from ... import __version_full__
from ... import log


logger = log.get_logger(__name__)


tag_names = [
    'Artist',
    'BitsPerSample',
    'Compression',
    'Copyright',
    'DateTime',
    'DocumentName',
    'ExtraSamples',
    'FillOrder',
    'HostComputer',
    #'ImageDescription',  # this gets hijacked
    'Make',
    'MaxSampleValue',
    'MinSampleValue',
    'Model',
    'Orientation',
    #  'PlanarConfiguration',
    'Predictor',
    'ResolutionUnit',
    'RowsPerStrip',
    'SampleFormat',
    'SamplesPerPixel',
    'Software',
    'XPosition',
    'XResolution',
    'YPosition',
    'YResolution',
]

time_format = '{0:%Y:%m:%d %H:%M:%S}\x00'
#software_version = 'dev'  # TODO get software version
software_version = __version_full__


def read_tif(fn, memmap=True):
    logger.debug("read_tif %s memap? %s", fn, memmap)
    if memmap:
        logger.debug("read_tif loading image")
        f = libtiff.TIFFfile(fn)
        im = f.get_tiff_array()[0]
        f.close()
        logger.debug("read_tif loading info")
        f = libtiff.TIFF.open(fn)
        info = {}
        for k in tag_names:
            v = f.GetField(k)
            if v is not None:
                info[k] = v
        v = f.GetField('ImageDescription')
        if (v is not None) and (v != ''):
            info.update(parse_description(v))
        f.close()
        return im, info
    im, info = read_tif(fn, memmap=True)
    return numpy.asarray(im), info


def write_tif(fn, im, **meta):
    """
    Will add the current time as DateTime
    Relevant tags:
        DateTime: <timestamp> "YYYY:MM:DD HH:MM:SS"
        Model: <camera serial number>
        ImageDescription: <anything?>
    """
    fn = os.path.expanduser(fn)
    logger.debug("write_tif %s %s %s", fn, hex(id(im)), meta)
    d = os.path.dirname(fn)
    if (d != '') and (not os.path.exists(d)):
        try:
            os.makedirs(d)
        except Exception as E:
            logger.error("Failed to create directory %s for saving %s",
                         d, fn, exc_info=True)
            raise type(E)(
                "Failed to create directory %s for saving %s [%s]" % (
                    d, fn, E))
    try:
        t = libtiff.TIFF.open(fn, mode='w')
    except Exception as E:
        logger.error("Failed to open file %s for saving", fn, exc_info=True)
        raise type(E)(
            "Failed to open file %s for saving [%s]" % (fn, E))
    # meta data must be written before images
    # libtiff.tiff_data.default_tag_values
    # DateTime: "YYYY:MM:DD HH:MM:SS" = capture time
    # Make: ""
    # Model: "" = camera serial number
    # Software: ""
    # HostComputer: ""
    # ImageDescription: "" can be xml "<?xml ..."
    if 'DateTime' not in meta:
        meta['DateTime'] = time_format.format(datetime.datetime.now())
    elif isinstance(meta['DateTime'], float):
        meta['DateTime'] = time_format.format(
            datetime.datetime.fromtimestamp(meta['DateTime']))
    elif isinstance(meta['DateTime'], datetime.datetime):
        meta['DateTime'] = time_format.format(meta['DateTime'])
    if 'Software' not in meta:
        meta['Software'] = software_version
    for k in meta.keys():
        if k in tag_names:
            t.SetField(k, meta.pop(k))
    t.SetField('ImageDescription', encode_description(meta))
    t.write_image(im)
    t.close()


def encode_description(d):
    logger.debug("encode_description %s", d)
    return json.dumps(d, cls=config.parser.NumpyAwareParser) + '\x00'


def parse_description(s):
    logger.debug("parse_description %s", s)
    return json.loads(s)
