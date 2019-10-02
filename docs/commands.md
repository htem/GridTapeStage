List of commands
------

```
<command_id> : <name> : brief description
    arguments : 
    --
    return values :

0 : error : an error occured in the tape movement
    error code [byte] (see below)

1 : ping : send/receive a simple code (test connection)
    code [byte] : an arbitrary code
    --
    code [byte] : an arbitrary code

5 : read_tension : read n_samples of the tension and return the mean
    n_samples [byte] : number of samples to average
    --
    tension_mean [int32] : result of the average

6 : set_led : set the led brightness
    brightness [byte] : (0 full on, 255 off)

10 : reset_drives : reconfigure all drives

12 : get_status : get the status word for a specific motor
    motor_code [byte] : see below
    --
    status_word [int16] : see below

15 : hold_drive : lock a drive in place
    motor_code [byte] : see below

16 : release_drive : release a drive to allow it to spin freely
    motor_code [byte] : see below

17 : rotate_drive : rotate a drive at a fixed number of steps per second
    motor_code [byte] : see below
    direction [byte] : (0 or 1)
    speed [float] : (steps per second)

18 : set_speed : set the maximum speed of a drive
    motor_code [byte] : see below
    speed [float] : (steps per second)

19 : get_speed : get the maximum speed of a drive
    motor_code [byte] : see below
    --
    speed [float] (steps per second)

20 : move_drive : move a drive a certain number of microsteps
    motor_code [byte] : see below
    direction [byte] : (0 or 1) see below
    n_steps [uint32] : number of microsteps to move

21 : run_reels : rotate both reel motors to take up slack at a fixed rpm
    rpm [float]

22 : stop_reels : stop both reel motors (release them)

23 : stop_all : stop motion of all motors (release reels, hold pinch drives)

24 : release_all : release all motors (allowing them to spin freely)

30 : step_tape : move both pinch drives to advance/retract the tape
    direction [byte] : tape direction
    feed_steps [uint32] : number of microsteps to move feed pinch drive
    pickup_steps [uint32] : number of microsteps to move pickup pinch drive
    time [float] : (seconds) duration of movement
    options [byte] : see below
```

Error Codes
------

- 0 : Error, generic error
- 1 : Missing argument, command call was missing a required argument
- 2 : Invalid argument, a command argument was invalid
- 10 : Invalid drive, a command received an invalid drive motor code
- 11 : Invalid direction, a command received an invalid tape direction

Motor Codes
------

Motor codes are bit fields that determine the side and type of motor to be used in a command. The first bit determines the type (0 reel motor, 1 pinch drive) and second determines the side (0 feed, 1 pickup). In total, the four motors are:

- 0b00 : Feed reel motor
- 0b01 : Feed pinch motor
- 0b10 : Pickup reel motor
- 0b11 : Pickup pinch motor

Tape direction
------

In total there are four tape directions (see 504 in temcagt_reel/reel.ino):

- 0 : Collect, send tape out of a side
- 1 : Dispense, pull tape into a side
- 2 : Tension, pull tape into both sides
- 3 : Untension, send tape out of both sides

Status Word
------

The status word is a 16 bit word read from the motor driver (L6470). See the [L6470 datasheet](www.st.com/resource/en/datasheet/l6470.pdf) for more information.

Step Tape Options
------

The step tape command takes an options byte that currently contains only 1 useful option:

- 0b10 : Wait, wait and report when the tape movement is finished
