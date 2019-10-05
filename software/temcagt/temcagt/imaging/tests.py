#!/usr/bin/env python


import unittest

from .montaging.tests import suite as montaging_suite
from .processing.tests import suite as processing_suite
from .tifio.tests import suite as tifio_suite

suite = unittest.TestSuite()
suite.addTest(montaging_suite)
suite.addTest(processing_suite)
suite.addTest(tifio_suite)
