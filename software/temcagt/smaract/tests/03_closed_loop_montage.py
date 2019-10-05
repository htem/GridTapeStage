#!/usr/bin/env python

import numpy

import smaract

sloc = 'usb:id:xxxxxxx'
xch = 1
ych = 0

# montage parameters
width = 250000  # x
height = 250000  # y

# step parameters
xsteps = 100
ysteps = 100

m = smaract.MCS(sloc)

# calibrate
if not m.physical_known(xch):
    raise IOError("X[%i] not calibrated" % (xch))
if not m.physical_known(ych):
    raise IOError("Y[%i] not calibrated" % (ych))

m.max_frequency(xch, 2000)
m.max_frequency(ych, 2000)


def move(x, y):
    print "Moving %i %i" % (x, y)
    m.move_absolute(xch, x)
    m.move_absolute(ych, y)
    for ch in (xch, ych):
        while True:
            if m.status(ch) == 0:
                print '%i at %i' % (ch, m.position(ch))
                break

xs = numpy.linspace(-width/2, width/2, xsteps).astype('int')
ys = numpy.linspace(-height/2, height/2, ysteps).astype('int')
direction = 1
for y in ys:
    for x in xs[::direction]:
        move(x, y)
    direction *= -1

# return to center
move(0, 0)
m.disconnect()
