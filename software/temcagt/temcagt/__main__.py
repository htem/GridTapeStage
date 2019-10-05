#!/usr/bin/env python

import sys

from temcagt import nodes

if __name__ == '__main__':
    args = sys.argv[1:]

    if not len(args):
        raise ValueError("temcagt module must be called with at least 1 arg")

    if args[0] == 'ui':
        from . import ui
        ui.launch.command_line_launch(args[1:])
    else:
        nodes.base.command_line_launch(args)
