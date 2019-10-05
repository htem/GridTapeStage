#!/usr/bin/env python

import unittest

from . import base


class BaseTest(unittest.TestCase):
    def ionode(self):
        c = {'a': 1}
        n = base.IONode(c)
        self.assertEqual(n._config, c)
        self.assertEqual(n.config(), c)
        n.config({'a': 2})
        self.assertEqual(n.config(), {'a': 2})
        n.config({'b': {'c': 1}})
        self.assertEqual(n.config(), {'a': 2, 'b': {'c': 1}})
        n.config({'b': {'d': 1}})
        self.assertEqual(n.config(), {'a': 2, 'b': {'c': 1, 'd': 1}})
        self._ionode_signaled = 0

        n.config({'a': 0})

        def f(*args):
            self._ionode_signaled += 1
        n.config_changed.connect(f)
        self.assertEqual(self._ionode_signaled, 0)
        n.config({'a': 1})
        self.assertEqual(self._ionode_signaled, 1)
        n.config_changed.disconnect(f)
        n.config({'a': 2})
        self.assertEqual(self._ionode_signaled, 1)
        # TODO serve forever


class CameraTest(unittest.TestCase):
    def connect(self):
        pass

    def disconnect(self):
        pass

    def check_config(self):
        pass

    def start_grab(self):
        pass

    def grab(self):
        pass

    def save_images(self):
        pass

    def new_images_signal(self):
        pass


class ControlTest(unittest.TestCase):
    def connect(self):
        pass

    def disconnect(self):
        pass

    def check_config(self):
        pass

    def calculate_montage(self):
        pass

    def bake(self):
        pass

    def montage(self):
        pass


class MotionTest(unittest.TestCase):
    def connect(self):
        pass

    def disconnect(self):
        pass

    def check_config(self):
        pass

    def configure(self):
        pass

    def move(self):
        pass

    def check_calibrate(self):
        pass

    #def calibrate(self):
    #    pass


suite = unittest.TestSuite()
suite.addTest(BaseTest('ionode'))

suite.addTest(CameraTest('connect'))
suite.addTest(CameraTest('disconnect'))
suite.addTest(CameraTest('check_config'))
suite.addTest(CameraTest('start_grab'))
suite.addTest(CameraTest('grab'))
suite.addTest(CameraTest('save_images'))

suite.addTest(ControlTest('connect'))
suite.addTest(ControlTest('disconnect'))
suite.addTest(ControlTest('check_config'))
suite.addTest(ControlTest('calculate_montage'))
suite.addTest(ControlTest('bake'))
suite.addTest(ControlTest('montage'))

suite.addTest(MotionTest('connect'))
suite.addTest(MotionTest('disconnect'))
suite.addTest(MotionTest('check_config'))
suite.addTest(MotionTest('move'))
suite.addTest(MotionTest('check_calibrate'))
