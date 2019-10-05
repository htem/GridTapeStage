#!/usr/bin/env python

import smaract

sloc = 'usb:id:xxxxxxx'
xch = 1
ych = 0

# montage parameters
dx = 10
dy = 10

# step parameters
xsteps = 100
xamp = 2000
xfreq = 1000
ysteps = 100
yamp = 2000
yfreq = 1000

si = smaract.raw.open_system(sloc)


def move(x, y):
    print "Moving %i %i" % (x, y)
    smaract.raw.step_move(si, xch, x * xsteps, xamp, xfreq)
    smaract.raw.step_move(si, ych, y * ysteps, yamp, yfreq)
    for ch in (xch, ych):
        while True:
            s = smaract.raw.get_status(si, xch)
            if s == 0:
                break

# move to origin
move(-dx / 2, -dx / 2)
direction = 1
for _ in xrange(dy):
    for _ in xrange(dx):
        move(direction, 0)
    move(0, 1)
    direction *= -1

# return to center
move(-dx / 2, -dx / 2)
