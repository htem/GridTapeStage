#!/usr/bin/env python

import unittest

from . import base
from . import checkers
from . import parser


class BaseTest(unittest.TestCase):
    def error(self):
        with self.assertRaises(base.ConfigError):
            raise base.ConfigError


class CheckersTest(unittest.TestCase):
    def require(self):
        with self.assertRaises(base.ConfigError):
            checkers.require({}, 'a')
        checkers.require(dict(a=1), 'a')
        checkers.require(dict(a=None), 'a')


class ParserTest(unittest.TestCase):
    def error(self):
        with self.assertRaises(parser.ArgumentError):
            raise parser.ArgumentError

    def parse_value(self):
        with self.assertRaises(parser.ArgumentError):
            parser.parse_value("a")
        self.assertEqual("a", parser.parse_value('"a"'))
        self.assertEqual("a", parser.parse_value("'a'"))
        self.assertEqual(1, parser.parse_value("1"))
        self.assertEqual([1, 2, 3], parser.parse_value("[1, 2, 3]"))
        self.assertEqual({'a': 1}, parser.parse_value('{"a": 1}'))

    def parse_command_line(self):
        with self.assertRaises(parser.ArgumentError):
            parser.parse_command_line(["a", "1", "b"])
        args = "a 1 b 'a' c.d 2".split()
        t = {"a": 1, "b": "a", "c": {"d": 2}}
        self.assertEqual(parser.parse_command_line(args), t)

    def load(self):
        raise Exception("Not tested")

    def save(self):
        raise Exception("Not tested")

    def parse(self):
        raise Exception("Not tested")

    def cascade(self):
        d0 = dict(a=1)
        d1 = dict(a=2)
        # check cascading order
        r = parser.cascade(d0, d1)
        self.assertEqual(r['a'], 2)
        r = parser.cascade(d1, d0)
        self.assertEqual(r['a'], 1)
        # check that config is copied (not referenced)
        r = parser.cascade(d1, d0)
        r['a'] = 3
        self.assertEqual(d0['a'], 1)
        self.assertEqual(d1['a'], 2)
        del d1['a']
        # check cascading for missing values
        r = parser.cascade(d0, d1)
        self.assertEqual(r['a'], 1)
        r = parser.cascade(d1, d0)
        self.assertEqual(r['a'], 1)
        # check second order cascades
        d0['b'] = dict(a=1)
        d1['b'] = dict(a=2)
        r = parser.cascade(d0, d1)
        self.assertEqual(r['b']['a'], 2)
        r = parser.cascade(d1, d0)
        self.assertEqual(r['b']['a'], 1)
        del d1['b']['a']
        r = parser.cascade(d0, d1)
        self.assertEqual(r['b']['a'], 1)
        r = parser.cascade(d1, d0)
        self.assertEqual(r['b']['a'], 1)
        del d1['b']
        r = parser.cascade(d0, d1)
        self.assertEqual(r['b']['a'], 1)
        r = parser.cascade(d1, d0)
        self.assertEqual(r['b']['a'], 1)
        # check errors when cascading dicts w/non-dicts
        d1['b'] = 1
        with self.assertRaises(parser.CascadeError):
            parser.cascade(d0, d1)
        with self.assertRaises(parser.CascadeError):
            parser.cascade(d1, d0)
        # copied over tests from old base.add_dicts
        a = {'a': 1, 'b': {'c': 1}}
        b = {'a': 2}
        t = {'a': 2, 'b': {'c': 1}}
        c = parser.cascade(a, b)
        self.assertEqual(c, t)
        # make sure it didn't modify a
        self.assertNotEqual(a, t)
        c = parser.cascade(a, b, modify=True)
        # now make sure it modified a
        self.assertEqual(a, t)
        b = {'b': {'d': 1}}
        t = {'a': 2, 'b': {'c': 1, 'd': 1}}
        c = parser.cascade(a, b)
        self.assertEqual(c, t)


suite = unittest.TestSuite()
suite.addTest(BaseTest('error'))
suite.addTest(CheckersTest('require'))
suite.addTest(ParserTest('error'))
suite.addTest(ParserTest('parse_value'))
suite.addTest(ParserTest('parse_command_line'))
suite.addTest(ParserTest('load'))
suite.addTest(ParserTest('save'))
suite.addTest(ParserTest('parse'))
suite.addTest(ParserTest('cascade'))
