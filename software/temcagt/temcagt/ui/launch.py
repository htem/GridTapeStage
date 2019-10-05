#!/usr/bin/env python

import os

from .. import config
from .. import log
from . import nodes


logger = log.get_logger(__name__)

default_config = {
    'node': 'montager',
    'action': 'test',
}

user_config_filename = os.path.expanduser('~/.temcagt/config/ui.json')


def command_line_launch(args=None):
    cfg = default_config.copy()
    if os.path.exists(user_config_filename):
        cfg = config.parser.cascade(
            cfg, config.parser.parse(user_config_filename))
    cfg = config.parser.cascade(
        cfg, config.parser.parse_command_line(args))

    node = cfg.get('node', 'montager')
    action = cfg.get('action', 'test')
    # TODO update actions to take cfg
    logger.debug("Node: %s", node)
    logger.debug("Action: %s", action)
    node = getattr(nodes, node)
    logger.debug("Node: %s", node)
    action = getattr(node, action)
    logger.debug("Action: %s", action)
    logger.debug("Args: %s", (args[2:], ))
    action(*args[2:])
    return
