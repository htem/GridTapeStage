The temcagt ui uses a Flask webserver and the clients web browser.

As default the server will use a non-standard port 5000
For test setups, the UI host will be 127.0.0.1
For temcagt, the UI host is 10.0.0.20 (control computer)

To access the UI visit one of the following urls:

http://127.0.0.1:5000/control/
http://127.0.0.1:5000/compute/
http://127.0.0.1:5000/montager/
http://127.0.0.1:5000/tape/
http://127.0.0.1:5000/tapecamera/
http://127.0.0.1:5000/scope/
http://127.0.0.1:5000/motion/
http://127.0.0.1:5000/cam0/

Notice the host:port/node/ format for all but the camera nodes.
