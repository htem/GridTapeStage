#!/usr/bin/env python

import unittest

import numpy
#import pylab
import scipy.misc

from . import contrast
from . import cropping
from . import oo
from . import shift

from ...config.checkers import require
from ...config.base import ConfigError


class CropTest(unittest.TestCase):
    def calculate_crop(self):
        lena = scipy.misc.lena()
        self.assertEqual(lena.shape, (512, 512))
        t = [(206, 306), (206, 306)]
        r = cropping.calculate_crop(lena, 100)
        self.assertEqual(t, r)
        r = cropping.calculate_crop(lena, 100.)
        self.assertEqual(t, r)
        r = cropping.calculate_crop(lena, (100., 100.))
        self.assertEqual(t, r)
        r = cropping.calculate_crop(lena, [(206, 306), (206, 306)])
        self.assertEqual(t, r)
        clena = lena[:, :256]
        t = [(206, 306), (78, 178)]
        r = cropping.calculate_crop(clena, 100.)
        self.assertEqual(t, r)

    def crop(self):
        lena = scipy.misc.lena()
        t = lena[206:306, 206:306]
        r = cropping.crop(t, 100)
        self.assertTrue(numpy.all(t == r))
        t = lena[206:306, 231:281]
        r = cropping.crop(t, (100, 50))
        self.assertTrue(numpy.all(t == r))


class ContrastTest(unittest.TestCase):
    def check_contrast(self):
        lena = scipy.misc.lena()
        t = numpy.std(lena)
        r = contrast.check_contrast(lena)
        self.assertEqual(t, r)
        t = numpy.std(lena[206:306, 206:306])
        r = contrast.check_contrast(lena, 100)
        self.assertEqual(t, r)
        t = numpy.std(lena[206:306, 231:281])
        r = contrast.check_contrast(lena, (100, 50))
        self.assertEqual(t, r)


class ShiftTest(unittest.TestCase):
    def parse_shift_results(self):
        a = [numpy.zeros((5, 5)) for _ in xrange(4)]
        a[0][2, 2] = 1
        a[1][3, 3] = 2
        a[2][4, 4] = 3
        a[3][1, 1] = 4
        r = shift.parse_shift_results(a)
        self.assertEqual(len(r), len(a))
        t = [
            dict(x=0, y=0, m=1, d=0),
            dict(x=1, y=1, m=2, d=2 ** 0.5),
            dict(x=2, y=2, m=3, d=8 ** 0.5),
            dict(x=-1, y=-1, m=4, d=2 ** 0.5),
        ]
        for (sr, st) in zip(r, t):
            for k in ('x', 'y', 'd', 'm'):
                self.assertIn(k, sr)
                self.assertEqual(sr[k], st[k])

    def find_shifts(self):
        lena = scipy.misc.lena()
        # no shift
        ims = [lena[206:306, 206:306] for _ in xrange(4)]
        r = shift.find_shifts(
            ims, tcrop=80, mcrop=90, method='TM_CCORR_NORMED')
        self.assertEqual(len(r), len(ims) - 1)
        t = dict(x=0, y=0, d=0, m=1)
        for sr in r:
            for k in t:
                self.assertEqual(t[k], sr[k])
        # shift im[0] (template) 1 pixel
        ims[0] = lena[205:305, 205:305]
        r = shift.find_shifts(
            ims, tcrop=80, mcrop=90, method='TM_CCORR_NORMED')
        t = dict(x=-1, y=-1, m=1)
        for sr in r:
            for k in t:
                self.assertEqual(t[k], sr[k])
        ims[0] = lena[207:307, 207:307]
        r = shift.find_shifts(
            ims, tcrop=80, mcrop=90, method='TM_CCORR_NORMED')
        t = dict(x=1, y=1, m=1)
        for sr in r:
            for k in t:
                self.assertEqual(t[k], sr[k])

        ims[0] = lena[100:200, 100:200]
        r = shift.find_shifts(
            ims, tcrop=80, mcrop=90, method='TM_CCORR_NORMED')
        for sr in r:
            self.assertLess(sr['m'], 0.95)

    def deshift(self):
        lena = scipy.misc.lena()
        c = cropping.calculate_crop(lena, 100)
        crop = lambda dy, dx: lena[
            c[0][0] + dy:c[0][1] + dy,
            c[1][0] + dx:c[1][1] + dx,
        ]
        ims = [crop(0, 0), crop(20, 20), crop(-20, -20), crop(0, 0)]
        shifts = shift.find_shifts(
            ims, tcrop=50, mcrop=100, method='TM_CCORR_NORMED')
        r = shift.deshift(ims, shifts)
        for i in xrange(1, len(r)):
            self.assertTrue(numpy.all(
                cropping.crop(r[i], 50) == cropping.crop(ims[0], 50)))
            #pylab.figure()
            #pylab.subplot(311)
            #pylab.imshow(cropping.crop(ims[0], 50))
            #pylab.subplot(312)
            #pylab.imshow(cropping.crop(ims[i], 50))
            #pylab.subplot(313)
            #pylab.imshow(cropping.crop(r[i], 50))
        #pylab.show()


class OOTest(unittest.TestCase):
    def kwarg_checker(self):
        def foo(a, b=None, c=None):
            pass
        kw = oo.get_kwarg_checker(foo)
        self.assertFalse(kw('a'))
        self.assertTrue(kw('b'))
        self.assertTrue(kw('c'))
        self.assertFalse(kw('d'))

    def validate(self):
        i = oo.ImageProcessor()
        i.valid = True
        self.assertTrue(i.validate())
        i.validate = lambda: True
        i.valid = False
        i.submit([])
        self.assertTrue(i.validate())
        i.validate = lambda: False
        i.valid = True
        i.submit([])
        self.assertFalse(i.validate())

    def configure(self):
        i = oo.ImageProcessor(dict(a=1))
        self.assertEqual(i.config['a'], 1)
        i.configure(dict(a=2))
        self.assertEqual(i.config['a'], 2)

        class IP(oo.ImageProcessor):
            def check_config(self):
                require(self.config, 'a')
                require(self.config, 'b')

        i = IP()
        with self.assertRaises(ConfigError):
            i.check_config()

        with self.assertRaises(ConfigError):
            i.submit([])
        i.configure(dict(a=None, b=None))
        i.check_config()

    def contrast(self):
        a = numpy.zeros((100, 100))
        i = oo.ContrastChecker(dict(crop=100, min=2.0))
        i.submit(a)
        self.assertFalse(i.validate())
        a[25:50, 25:50] = 100.
        i.submit(a)
        self.assertTrue(i.validate())

    def shift(self):
        lena = scipy.misc.lena()
        i = oo.ShiftChecker(dict(
            tcrop=50, mcrop=100, method='TM_CCORR_NORMED',
            max_shift=(2 * 10 ** 2.) ** 0.5,
            min_match=0.95))
        c = cropping.calculate_crop(lena, 100)
        crop = lambda dy, dx: lena[
            c[0][0] + dy:c[0][1] + dy,
            c[1][0] + dx:c[1][1] + dx,
        ]
        ims = [crop(0, 0), crop(5, 5), crop(-5, -5), crop(0, 0)]
        i.submit(ims)
        self.assertTrue(i.validate())
        ims = [crop(0, 0), crop(10, 10), crop(-10, -10), crop(0, 0)]
        i.submit(ims)
        self.assertTrue(i.validate())
        ims = [crop(0, 0), crop(11, 11), crop(-11, -11), crop(0, 0)]
        i.submit(ims)
        self.assertFalse(i.validate())
        ims = [crop(0, 0), crop(110, 110), crop(-5, -5), crop(0, 0)]
        i.submit(ims)
        self.assertFalse(i.validate())
        ims = [crop(0, 0), crop(5, 5), crop(-5, -5), crop(0, 0)]
        i.submit(ims)
        i.result[0]['m'] = 0.8  # fake a bad match
        self.assertFalse(i.validate())


suite = unittest.TestSuite()
suite.addTest(CropTest('calculate_crop'))
suite.addTest(CropTest('crop'))
suite.addTest(ContrastTest('check_contrast'))
suite.addTest(ShiftTest('parse_shift_results'))
suite.addTest(ShiftTest('find_shifts'))
suite.addTest(ShiftTest('deshift'))
suite.addTest(OOTest('kwarg_checker'))
suite.addTest(OOTest('validate'))
suite.addTest(OOTest('configure'))
suite.addTest(OOTest('contrast'))
suite.addTest(OOTest('shift'))
