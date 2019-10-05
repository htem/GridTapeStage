#!/usr/bin/env python

import unittest

from . import planning


class PlanningTest(unittest.TestCase):
    def grid_coordinates(self):
        d = {}
        keys = ('xfov', 'xoverlap', 'xOrigin', 'width', 'yfov',
                'yoverlap', 'yOrigin', 'height')
        for k in keys:
            with self.assertRaises(KeyError):
                planning.grid_coordinates(d)
            d[k] = 1
        d = {'height': 20, 'width': 20, 'xfov': 10, 'yfov': 10,
             'xOrigin': 0, 'yOrigin': 0, 'xoverlap': 0.5, 'yoverlap': 0.5}
        r = planning.grid_coordinates(d)
        t = [
            (-5.0, -5.0), (0.0, -5.0), (5.0, -5.0), (10.0, -5.0),
            (10.0, 0.0), (5.0, 0.0), (0.0, 0.0), (-5.0, 0.0),
            (-5.0, 5.0), (0.0, 5.0), (5.0, 5.0), (10.0, 5.0),
            (10.0, 10.0), (5.0, 10.0), (0.0, 10.0), (-5.0, 10.0)]
        self.assertEqual(r, t)

    def calculate_coordinates(self):
        with self.assertRaises(KeyError):
            planning.calculate_coordinates(dict(method='error'))
        with self.assertRaises(KeyError):
            planning.calculate_coordinates({})
        d = {'height': 20, 'width': 20, 'xfov': 10, 'yfov': 10,
             'xOrigin': 0, 'yOrigin': 0, 'xoverlap': 0.5, 'yoverlap': 0.5}
        gr = planning.grid_coordinates(d)
        d['method'] = 'grid'
        cr = planning.calculate_coordinates(d)
        self.assertEqual(gr, cr)


suite = unittest.TestSuite()
suite.addTest(PlanningTest('grid_coordinates'))
suite.addTest(PlanningTest('calculate_coordinates'))
#suite.addTest(PlanningTest('mask_coordinates'))
