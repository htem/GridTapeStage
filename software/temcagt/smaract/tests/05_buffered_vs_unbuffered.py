#!/usr/bin/env python

import time

import smaract
import smaract.async

distance = 16000
l = smaract.find_systems()[0]

# first try sync
#locs = smaract.find_systems()
#print locs
#l = locs[0]
#if len(l) == 0:
#    raise Exception("No systems found")

print("Connecting to: %s" % l)

m = smaract.AMCS(l)

# unbuffered
smaract.async.set_buffered_output(m.system_index, 0)

t0 = time.time()
m.move_relative(0, -distance)
m.move_relative(1, -distance)
m.wait(0)
m.wait(1)
t1 = time.time()
print("Unbuffered move: %s" % (t1 - t0))

t0 = time.time()
p0 = m.position(0)
p1 = m.position(1)
t1 = time.time()
print("Unbuffered pos: %s" % (t1 - t0))
print("\t%s, %s" % (p0, p1))

t0 = time.time()
m.move_relative(0, distance)
m.move_relative(1, distance)
m.wait(0)
m.wait(1)
t1 = time.time()
print("Unbuffered move: %s" % (t1 - t0))

# buffered
smaract.async.set_buffered_output(m.system_index, 1)

t0 = time.time()
m.move_relative(0, -distance)
m.move_relative(1, -distance)
smaract.async.flush_output(m.system_index)
m.wait(0)
m.wait(1)
t1 = time.time()
print("buffered move: %s" % (t1 - t0))

t0 = time.time()
m._channel_states[0][2] = None
m._channel_states[1][2] = None
smaract.async.get_position(m.system_index, 0)
smaract.async.get_position(m.system_index, 1)
smaract.async.flush_output(m.system_index)
while m._channel_states[0][2] is None or m._channel_states[1][2] is None:
    m.process_packets()
p0 = m._channel_states[0][2]
p1 = m._channel_states[1][2]
t1 = time.time()
print("buffered pos: %s" % (t1 - t0))
print("\t%s, %s" % (p0, p1))

t0 = time.time()
m.move_relative(0, distance)
m.move_relative(1, distance)
smaract.async.flush_output(m.system_index)
m.wait(0)
m.wait(1)
t1 = time.time()
print("buffered move: %s" % (t1 - t0))

m.disconnect()
