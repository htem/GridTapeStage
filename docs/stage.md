Stage sides
------

The stage is seperated into two parts, a feed side (to the left/front when looking
at the microscope) and a pickup side (to the right/rear). Each side contains
two motors, a pinch drive that can move the tape a linear distance and a reel drive
that rotates to take up extra tape slack during movements.

Stage parts
------

Please see the diagram, gridtape_stage.png.

A. Objective pole piece of microscope
B. Reel motors (outside vacuum)
C. GridTape reels
D. Pinch motors (outside vacuum)
E. Pinch rollers
F. Idle rollers
G. Tension sensor
H. Piezo linear stages
I. Tape channel

The tape path starts at the feed reel (B left), goes between the idle and pinch rollers (E, F), over the tension sensor (G) and into the tape channel (I) that is affixed to the piezo stages (H). While in the channel the tape passes through the objective pole piece (A). From there, the tape exits the channel, enters the pickup pinch drive (right F, E) and is collected onto the pickup reel (right C).

Electronics
------

The stage electronics should be connected in the following order (starting with the power off):

1. connect the stepper motors (these should never be attached or detached when power is on)
2. connect the led and tension sensors (double check they are each in the correct port)
3. connect power
4. connect usb

If power is reset, be sure to disconnect and then reconnect the usb (to reset the arduino).
