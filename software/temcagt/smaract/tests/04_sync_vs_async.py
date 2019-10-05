#!/usr/bin/env python

import time

import smaract
import smaract.async

channel = 0
distance = 16000
l = 'usb:id:xxxxxxx'

# first try sync
#locs = smaract.find_systems()
#print locs
#l = locs[0]
#if len(l) == 0:
#    raise Exception("No systems found")

print("Connecting to: %s" % l)

# sync
m = smaract.MCS(l)

t0 = time.time()
m.move_relative(channel, distance)
while m.status(0) != 0:
    pass
t1 = time.time()
print("Sync move: %s" % (t1 - t0))

t0 = time.time()
p = m.position(channel)
t1 = time.time()
print("Sync pos: %s" % (t1 - t0))

t0 = time.time()
m.move_relative(channel, distance)
while m.status(0) != 0:
    pass
p = m.position(channel)
t1 = time.time()
print("Sync pos: %s" % (t1 - t0))

m.disconnect()

# async
m = smaract.AMCS(l)

t0 = time.time()
m.move_relative(channel, -distance)
m.wait(0)
t1 = time.time()
print("ASync move: %s" % (t1 - t0))

t0 = time.time()
position = m.position(channel)
t1 = time.time()
print("ASync pos: %s" % (t1 - t0))

t0 = time.time()
m.move_relative(channel, -distance)
m.wait(0)
p = m.position(0)
t1 = time.time()
print("ASync pos: %s" % (t1 - t0))

m.disconnect()
