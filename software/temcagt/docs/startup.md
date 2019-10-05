temcagt nodes are started, stopped and checked using the temcagt script in:

scripts/temcagt

After you install the temcagt python module, this script should be in your
PATH and available for use (note: if the module is installed as an egg-link
by passing -e to pip, you will need to reinstall the temcagt module after any
updates to the temcagt script).

To start the temcagt motion node run:

temcagt start motion

and a similar command for the camera node:

temcagt start camera

Running "temcagt start" without providing any node names will cause the temcagt
script to look in your ~/.temcagt/configs directory for all available node
config files (e.g. ~/.temcagt/configs/motion.json). The temcagt script will then
start all of these nodes in the appropriate order.

After nodes are running, their status can be checked with:

temcagt status

Example output might look like this:

temcagt pids are:
    camera: 22115
    control: 22219
    motion: 22146
    tape: 22189
    ui: 22250

Listing all running nodes and their associated process ids (pids).

To stop the motion node run:

temcagt kill motion

As with temcagt start, temcagt kill can be run with no node names.

If a node fails to kill after several attempts, a more severe stop signal
can be sent using "temcagt kill9". After a kill9 any child processes that
were started by the node will need to be manually killed. For example, if
a camera node fails to shut down after a kill and a kill9 is issued. Run
something like the following to check for remaining processes:

ps aux | grep camera | grep python | grep temcagt

Then kill the process ids using the kill command line tool:

kill 287403
