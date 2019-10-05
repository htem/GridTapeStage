#!/usr/bin/env python

import unittest

from .config.tests import suite as config_suite
from .imaging.tests import suite as imaging_suite
from .nodes.tests import suite as nodes_suite


suite = unittest.TestSuite()
suite.addTest(config_suite)
suite.addTest(imaging_suite)
suite.addTest(nodes_suite)


def run(verbosity=2):
    unittest.TextTestRunner(verbosity=verbosity).run(suite)
