#!/usr/bin/env python

import os
import tempfile
import unittest

import numpy

from . import raw
from . import oo


class RawReadWriteTest(unittest.TestCase):
    def setUp(self):
        self.fn = tempfile.mktemp() + '.tif'

    def tearDown(self):
        if os.path.exists(self.fn):
            os.remove(self.fn)

    def read_tif(self):
        a = numpy.zeros((100, 100))
        raw.write_tif(self.fn, a, a=1, b='2', Model="abc",
                      bar=[1, 2, 3], baz={'a': 1})
        self.assertTrue(os.path.exists(self.fn))
        im, info = raw.read_tif(self.fn)
        self.assertTrue(numpy.all(a == im))
        self.assertEqual(info['Model'], "abc")
        self.assertEqual(info['a'], 1)
        self.assertEqual(info['b'], '2')
        self.assertEqual(info['bar'], [1, 2, 3])
        self.assertEqual(info['baz'], {'a': 1})

    def write_tif(self):
        a = numpy.zeros((100, 100))
        raw.write_tif(self.fn, a)
        self.assertTrue(os.path.exists(self.fn))
        raw.write_tif(self.fn, a, a=1, b='2', Model="abc")
        self.assertTrue(os.path.exists(self.fn))


class RawTest(unittest.TestCase):
    def encode_description(self):
        d = {
            'a': 1,
            'b': 2,
            'c': [1, 2, 3],
            'e': {'1': 1},
        }
        t = '{"a": 1, "c": [1, 2, 3], "b": 2, "e": {"1": 1}}\x00'
        r = raw.encode_description(d)
        self.assertEqual(t, r)

    def parse_description(self):
        t = {
            'a': 1,
            'b': 2,
            'c': [1, 2, 3],
            'e': {'1': 1},
        }
        s = '{"a": 1, "c": [1, 2, 3], "b": 2, "e": {"1": 1}}'
        r = raw.parse_description(s)
        self.assertEqual(t, r)


class OOTest(unittest.TestCase):
    def setUp(self):
        self.fn_base = tempfile.mktemp()
        self.fns = []

    def tearDown(self):
        for fn in self.fns:
            if os.path.exists(fn):
                os.remove(fn)

    def tif_saver(self):
        t = oo.TifSaver()
        t.filename_format = self.fn_base + '{x}_{y}.tif'
        a = numpy.zeros((100, 100))
        fn = t.filename_format.format(x=1, y=1)
        self.fns.append(fn)
        t.save_image(a, dict(x=1, y=1))
        fn = t.filename_format.format(x=10, y=10)
        self.fns.append(fn)
        t.save_image(a, dict(x=10, y=10))
        fn = t.filename_format.format(x=10, y=10, z=10)
        self.fns.append(fn)
        t.save_image(a, dict(x=10, y=10, z=10))
        with self.assertRaises(KeyError):
            t.save_image(a)
        with self.assertRaises(KeyError):
            t.save_image(a, dict(x=10))
        with self.assertRaises(KeyError):
            t.save_image(a, dict(y=10))


suite = unittest.TestSuite()
suite.addTest(RawTest('encode_description'))
suite.addTest(RawTest('parse_description'))
suite.addTest(RawReadWriteTest('write_tif'))
suite.addTest(RawReadWriteTest('read_tif'))
suite.addTest(OOTest('tif_saver'))
