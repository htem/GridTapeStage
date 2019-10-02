Hardware Interface
------

The lowest level of interface to the control electronics is a serial
connection running at 115200 baud. A connection to this interface can
be made with pyserial and uses the default connection parameters of

- bytesize=8
- parity='N'
- stopbits=1
- xonxoff=False
- rtscts=False
- dsrdtr=False

```python
import serial

conn = serial.Serial('/dev/ttyACM0', 115200)
```

On connection, the arduino will reset and needs a few (3-4) seconds
to start up before it is able to receive commands.


Message Protocol
------

The serial communication uses a standard message format, part of the
[comando](http://github.com/braingram/comando) library, to allow for
efficient and flexible passing of data back and forth between the
host computer and the control electronics. The low level messages
are described [here](https://github.com/braingram/comando/blob/master/doc/messages.md)
on top of which is built a [protocol format] (https://github.com/braingram/comando/blob/master/doc/protocols.md)
which is used to transmit command following a [command format](https://github.com/braingram/comando/blob/master/doc/commands.md).

These ability to use the same connection for multiple protocols is current not
used. Currently all interaction is through the command protocol which
can be setup as follows:

```python
import pycomando
import serial

conn = serial.Serial('/dev/ttyACM0', 115200)
com = pycomando.Commando(conn)
cmd = pycomando.protocols.CommandProtocol(com)

com.register_protocol(1, cmd)
```

A detailed example of using pycomando commands can be found [here](https://github.com/braingram/comando/blob/master/examples/commands.py). Although the pycomando module is open source,
it is not necessary to use the pycomando module. Briefly, commands can
be sent as follows:

```python
# sent a command of command_id wih 3 arguments (arg0, arg1, arg2)
cmd.send_command(command_id, (arg0, arg1, arg2))

# send a command 0, with args True, 1, 1.5
cmd.send_command(0, (True, 1, 1.5))
```

Receiving commands is done through a callback system.

```python
def ping_received(cmd):
    print("ping received")

# when a command of id 0 is received, call ping_received
cmd.register_callback(0, ping_received)
```

Updating the Comando instance to check for new serial data is done
explicitly by calling: 

```python
com.handle_stream()
```

Additionally, the commands can be called through an EventManager instance
which when initialized with a description of the commands (like that in
the demo, lines 45-142) gives name-based access to commands. For example,
to stop movement of all the motors run:

```python
mgr.trigger('stop_all')
```
