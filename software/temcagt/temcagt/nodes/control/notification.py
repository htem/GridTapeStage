#!/usr/bin/env python

import datetime
import json
import os
import time

import notifier

from ... import config
from ... import log


logger = log.get_logger(__name__)


def build_montage_start_notification(node, **meta):
    """
    session name, roi, save directory
    roi
    """
    cfg = node.config()
    scfg = cfg.get('slot', {})
    roi_index = scfg.get('roi_index', -1)
    rois = scfg.get('rois', [])
    if roi_index > -1 and roi_index < len(rois):
        roi = rois[roi_index]
    else:
        roi = {}
    mcfg = scfg.get('montage', {})
    session_name = mcfg.get('session_name', '?')
    save_directory = cfg.get('save', {}).get('directory', '?')

    subject = "Montaging %s ROI %i, saving to %s" % (
        session_name, roi_index, save_directory)

    msg = subject
    msg += "\n=== ROI ===\n" + json.dumps(
        roi, cls=config.parser.NumpyAwareParser) + '\n'
    return subject, msg


def build_montage_notification(node, **meta):
    """
        session name, roi, save_directory
        ntiles
        mpix/s during montage
        mpix/s overall

        roi: cfg['slot']['roi']
        n_tiles: ?
        notes: montager.session.notes
        rates?
        all of slot? json.dumps(d, indent=True)
    """
    cfg = node.config()
    scfg = cfg.get('slot', {})
    roi_index = scfg.get('roi_index', -1)
    rois = scfg.get('rois', [])
    if roi_index > -1 and roi_index < len(rois):
        roi = rois[roi_index]
    else:
        roi = {}
    mcfg = scfg.get('montage', {})
    session_name = mcfg.get('session_name', '?')
    save_directory = cfg.get('save', {}).get('directory', '?')

    subject = "Montaging %s ROI %i, saving to %s" % (
        session_name, roi_index, save_directory)

    msg = subject + '\n'

    # start time: move_slot.meta.start_time
    stime = cfg.get('move_slot', {}).get(
        'meta', {}).get('start_time', float('nan'))
    # montage start time: slot.montage.start_time
    mtime = cfg.get('slot', {}).get(
        'montage', {}).get('start_time', float('nan'))
    # finish time: slot.montage.finish_time
    ftime = cfg.get('slot', {}).get(
        'montage', {}).get('finish_time', float('nan'))
    # n tiles: slot.montage.n_tiles
    nt = cfg.get('slot', {}).get('montage', {}).get('n_tiles', float('nan'))
    # n vetos: slot.montage.n_vetos
    nv = cfg.get('slot', {}).get('montage', {}).get('n_vetos', float('nan'))
    # n nodatas:
    nd = cfg.get('slot', {}).get('montage', {}).get('n_nodatas', 0)

    # total time
    msg += "%s tiles, %s vetos, %0.4f seconds\n" % (
        nt, nv, (ftime - stime))
    msg += "%0.4f percent of time montaging\n" % (
        ((ftime - mtime) / (ftime - stime) * 100))
    # tiles / sec (during montage)
    msg += "%0.4f tiles / second during montage\n" % (
        nt / (ftime - mtime))
    # tiles / sec (overall)
    msg += "%0.4f tiles / second overall\n" % (
        nt / (ftime - stime))

    if nd != 0:
        msg += "%i nodata errors\n" % (nd, )

    msg += "\n=== ROI ===\n" + json.dumps(
        roi, cls=config.parser.NumpyAwareParser) + '\n'
    return subject, msg


def build_error_notification(node, **meta):
    cfg = node.config()
    scfg = cfg.get('slot', {})
    mcfg = scfg.get('montage', {})
    subject = "Session %s ERROR: %s" % (
        mcfg.get('session_name', '?'), int(time.time()))
    msg = subject + '\n'
    if 'error' in meta:
        error = meta.pop('error')
        msg += "\n=== ERROR ===\n"
        msg += "%s\n" % (error, )
        # TODO extra error information?
    msg += '\n' + json.dumps(
        scfg, indent=True, cls=config.parser.NumpyAwareParser) + '\n'
    if len(meta):
        msg += '\n=== META ===\n' + json.dumps(
            meta, indent=True, cls=config.parser.NumpyAwareParser) + '\n'
    return subject, msg


def build_make_safe_notification(node, **meta):
    cfg = node.config()
    if meta.get('scope_not_connected', False):
        subject = "CRITICAL ERROR: Unable to make beam safe, unconnected scope"
        msg = subject
        msg += "\nan attempt will be made to reconnect to the scope "
        msg += "but this may fail requiring manual shutoff of the scope.\n"
        msg += "If you do not receive an email saying the beam was made safe "
        msg += "the connection attempt most likly failed."
    else:
        if 'kill_time' not in meta:
            meta['kill_time'] = (
                time.time() + cfg['make_safe']['kill_beam_timeout'])
        kill_time = datetime.datetime.fromtimestamp(meta['kill_time'])
        kill_time_string = kill_time.strftime('%y-%m-%d %H:%M:%S')
        subject = (
            "Beam was made safe, will be shut off at %s"
            % kill_time_string)
        # TODO more information
        msg = subject
        msg += "\nto prevent beam from shutting off "
        msg += "go to the scope and click 'kill' on the control node"
    return subject, msg


def build_kill_beam_notification(node, **meta):
    dt = datetime.datetime.now()
    dts = dt.strftime('%y-%m-%d %H:%M:%S')
    subject = "Beam was shut off at %s" % dts
    # TODO more information
    msg = subject
    return subject, msg


def send_notification(node, event, **meta):
    cfg = node.config()

    # construct notification text
    try:
        if event == 'montage':
            subject, msg = build_montage_notification(node, **meta)
        elif event == 'montage_start':
            subject, msg = build_montage_start_notification(node, **meta)
        elif event == 'error':
            subject, msg = build_error_notification(node, **meta)
        elif event == 'make_safe':
            subject, msg = build_make_safe_notification(node, **meta)
        elif event == 'kill_beam':
            subject, msg = build_kill_beam_notification(node, **meta)
    except Exception as e:
        subject = 'Error: %s' % e
        msg = 'event: %s, %s' % (event, meta)

    if not cfg.get('notification', {}).get('enable', False):
        logger.debug("built notification for %s", event)
        logger.debug("notification subject: %s", subject)
        logger.debug("notification message: %s", msg)
        return

    # send notification
    ncfg = cfg['notification']
    if 'to_email' in ncfg and len(ncfg['to_email']):
        notifier.notify(msg, subject=subject, to_email=ncfg['to_email'])

    if ('slack_channel' in ncfg and hasattr(notifier, 'channel_message')):
        token = ncfg.get(
            'slack_token', os.environ.get('SLACK_TOKEN', None))
        if token is not None:
            notifier.channel_message(
                msg, ncfg['slack_channel'],
                token)
