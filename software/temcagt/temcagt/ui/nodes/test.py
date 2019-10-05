#!/usr/bin/env python

import inspect
import os

import wsrpc

from . import base

module_folder = os.path.abspath(
    os.path.dirname(inspect.getfile(inspect.currentframe())))


class Foo(object):
    pass


def build_spec(obj, name):
    spec = base.build_spec(obj, name)
    spec['template'] = open(
        os.path.join(module_folder, 'templates', 'roi_test.html'), 'r').read()
    return spec


def test():
    wsrpc.serve.register(build_spec(Foo(), 'test'))
    wsrpc.serve.serve()

if __name__ == '__main__':
    test()
