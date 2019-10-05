#!/usr/bin/env python

import copy
import os
import signal
import socket
import sys
import time

import concurrent.futures
import pizco
import zmq

from .. import config
from .. import log

logger = log.get_logger(__name__)

if not (zmq.zmq_version_info()[0] >= 3):
    logger.error(
        "ZMQ version[%s] is too old [<3]", zmq.zmq_version())
    raise ImportError(
        "ZMQ version[{}] is too old [<3]".format(zmq.zmq_version()))


class PizcoNodeServer(pizco.Server):
    def return_as_remote(self, attr):
        if pizco.Server.return_as_remote(self, attr):
            return True
        if isinstance(attr, IONode):
            return True
        return False


class StateException(Exception):
    pass


class StateMachine(object):
    def __init__(self, node):
        self.node = node
        self._state = None
        self._override = False
        self._conditions = None
        #self._errors = []
        self._running = False
        self._future = None
        self.new_state = pizco.Signal(nargs=1)

    def __repr__(self):
        return "%s.%s[%s](%s)" % (
            self.__module__, self.__class__, self.get_state(), hex(id(self)))

    def is_running(self):
        return self._running

    def override(self, new_state, in_loop=False):
        if not in_loop:
            self.node.loop.add_callback(self.override, new_state, True)
            return
        logger.debug("StateMachine override: %s", new_state)
        self._override = new_state

    def get_state(self):
        #if len(self._errors):
        #    return StateException('%s: %s' % (self._state, self._errors))
        if isinstance(self._state, list):
            return StateException(str(self._state))
        return self._state

    def set_state(self, state):
        if isinstance(state, Exception):
            if not isinstance(self._state, list):
                self._state = [self._state, ]
            self._state.append(state)
        else:  # TODO check other types?
            self._state = state
            if state is None:
                self._running = False
        self.new_state.emit(self.get_state())

    def _teardown(self):
        logger.debug("StateMachine._teardown")

    def _release_node(self):
        logger.debug("StateMachine._release_node")
        self.node = None

    def __del__(self):
        logger.debug("StateMachine.__del__")
        self._release_node()
        del self.node

    def run(self, new_state, in_loop=False):  # run
        if self.node is None:
            e = StateException("_node is None")
            if self._future is not None:
                self._future.set_exception(e)
            self.set_state(e)
            if not in_loop:
                raise e
            #self._errors.append(StateException("_node is None"))
            return
        if not in_loop:
            self._future = concurrent.futures.Future()
            self.node.loop.add_callback(
                self.run, new_state, True)
            return self._future
        if new_state is None:
            self._future.set_result(None)
            self.set_state(None)
            return
        if (
                (not isinstance(new_state, (str, unicode))) or
                (not hasattr(self, new_state))):
            e = StateException(
                "Invalid state, missing attribute: %s" % new_state)
            self.set_state(e)
            #self.set_state(StateException(
            #    "Invalid state, missing attribute: %s" % new_state))
            #self._errors.append(StateException(
            #    "Invalid state, missing attribute: %s" % new_state))
            self._future.set_exception(e)
            self._running = False
            return
        logger.debug("StateMachine run.new_state: %s", new_state)
        # set new state
        self._running = True
        self.set_state(new_state)
        # call new state
        try:
            r = getattr(self, new_state)()
        except Exception as e:
            self._running = False
            self._future.set_exception(e)
            self.set_state(e)
            #self._errors.append(e)
            return
        if not isinstance(r, (tuple, list)):
            next_state = r
            condition = None
        else:
            next_state, condition = r
        if self._override is not False:
            # TODO should this override when there are conditions?
            next_state = self._override
            self._override = False
        logger.debug("StateMachine run.next_state: %s", next_state)
        if condition is None:
            # if no waiting on conditions, then just add callback
            self.node.loop.add_callback(
                self.run, next_state, in_loop)
        else:
            if isinstance(condition, concurrent.futures.Future):
                condition = [condition, ]
            if isinstance(condition, (list, tuple)):  # multiple conditions
                # make sure these are all futures
                for c in condition:
                    if not isinstance(c, concurrent.futures.Future):
                        e = StateException(
                            "Invalid conditions, "
                            "if list, all items must be futures: %s",
                            condition)
                        self._future.set_exception(e)
                        self.set_state(e)
                        self._running = False
                        return
                self._conditional = (next_state, list(condition))
                logger.debug(
                    "StateMachine run: conditionals found: %s", condition)
                for f in condition:
                    # TODO should this be loop.add_future?
                    self.node.loop.add_future(f, self._check_condition)
                    #f.add_done_callback(self._check_condition)
            elif isinstance(condition, (int, float)):
                logger.debug(
                    "StateMachine run: call_later: %s", condition)
                self.node.loop.call_later(
                    float(condition), self.run, next_state, in_loop)
            else:
                e = StateException("Invalid condition: %s" % condition)
                self._future.set_exception(e)
                self.set_state(e)
                #self._errors.append(
                #    StateException("Invalid condition: %s" % condition))
                self._running = False
                return

    def _check_condition(self, f):
        logger.debug(
            "StateMachine _check_condition: %s", f)
        next_state, conditions = self._conditional
        if f.exception() is not None:
            logger.error(
                "StateMachine _check_condition found exception: %s",
                f.exception())
            self._running = False
            self.set_state(f.exception())
            #self._errors.append(f.exception())
        logger.debug(
            "StateMachine _check_condition conditions: %s", conditions)
        conditions.remove(f)
        logger.debug("StateMachine _check_condition: %s left", len(conditions))
        if len(conditions) == 0:
            #if len(self._errors) != 0:
            if isinstance(self.get_state(), Exception):
                self._running = False
                return
            self.node.loop.add_callback(
                self.run, next_state, True)


class IONode(object):
    def __init__(self, cfg=None):
        cfg = config.parser.parse(cfg)
        if cfg is not None:
            if not isinstance(cfg, dict):
                raise TypeError(
                    "Config must be a dict not {}".format(type(cfg)))
            self._config = cfg
        else:
            self._config = {}
        self.loop = None  # will be replaced with server ioloop
        self._server = None
        self._log_handler = None
        self.config_changed = pizco.Signal(nargs=1)
        logger.info("%s[%s] created", type(self), self)

    def set_log_level(self, level):
        log.set_level_for_all_loggers(level)

    def start_logging(self, directory, level=None):
        logger.info(
            "%s[%s] start_logging: %s, %s", type(self), self, directory, level)
        if self._log_handler is not None:
            self.stop_logging()
        fn = os.path.join(
            directory, '_'.join(
                (self.__module__.split('.')[-1],
                 socket.gethostname(), str(os.getpid()),
                 time.strftime('%y%m%d%H%M%S'))) + '.log')
        self._log_handler = log.log_to_filename(fn, level)

    def stop_logging(self):
        if self._log_handler is None:
            return
        logger.info("%s[%s] stop_logging", type(self), self)
        log.stop_logging_to_handler(self._log_handler)
        self._log_handler = None

    def connect(self):
        pass

    def disconnect(self):
        pass

    def connected(self):
        pass

    def __del__(self):
        logger.debug("%s[%s] __del__", type(self), self)
        if self.connected():
            self.disconnect()

    def config_delta(self, delta):
        """Override this to respond to changes in config
        without listening to a signal"""
        pass

    def config(self, value=None, replace=False, prune=False):
        if value is None:
            return self._config
        if replace and prune:
            raise ValueError(
                "Config cannot both replace and prune at the same time")
        if replace:
            logger.info(
                "Configuring %s[%s] replacing with %s",
                type(self), self, value)
        elif prune:
            logger.info(
                "Configuring %s[%s] pruning with %s",
                type(self), self, value)
        else:
            logger.info(
                "Configuring %s[%s] appending %s",
                type(self), self, value)
        if not prune:
            value = config.parser.parse(value)
            if not isinstance(value, dict):
                raise TypeError(
                    "Config must be a dict not {}".format(type(value)))
        if value == self._config:
            return self._config
        if replace:
            new_config = copy.deepcopy(value)
        elif prune:
            new_config = config.parser.prune(self._config, value)
        else:
            new_config = config.parser.cascade(self._config, value)
        # make sure new_config is valid
        delta = config.parser.delta(self._config, new_config)
        try:
            self.check_config(new_config)
            self._config = new_config
        except config.base.ConfigError as e:
            logger.error("Received invalid config {}".format(e), exc_info=e)
            delta = {}
        if delta != {}:
            self.config_delta(delta)
        self.config_changed.emit(self._config)

    def check_config(self, cfg=None):
        pass

    def serve_forever(self):
        # need to generate pub address as it defaults to loopback
        addr = self.config()['addr']
        tokens = addr.split(':')
        pub_addr = ':'.join(tokens[:-1] + [str(int(tokens[-1]) + 100), ])
        self._server = PizcoNodeServer(self, addr, pub_addr)
        self.loop = self._server.loop
        logger.info("Serving %s[%s] on %s", type(self), self,
                    self.config()['addr'])

        def quit_gracefully(*args):
            print("Quitting: %s" % (args, ))
            if self.connected():
                self.disconnect()
            sys.exit(0)

        signal.signal(signal.SIGINT, quit_gracefully)
        signal.signal(signal.SIGTERM, quit_gracefully)
        self._server.serve_forever()

    def save_config(self, fn):
        logger.info("%s[%s] saving config to %s: %s", type(self), self, fn,
                    self.config())
        config.parser.save(self.config(), fn)

    def load_config(self, fn):
        logger.info("%s[%s] loading config from %s", type(self), self, fn)
        return self.config(fn, replace=True)


class StatefulIONode(IONode):
    def __init__(self, cfg=None):
        super(StatefulIONode, self).__init__(cfg)
        self.statemachine = None
        self.new_state = pizco.Signal(nargs=1)
        self._state_cb = None

    def _new_state(self, state):
        if self.statemachine is None:
            smc = None
        else:
            smc = self.statemachine.__class__.__name__
        self.new_state.emit((smc, state))
        if isinstance(state, Exception):
            raise state
        if state is None:
            self.detach_state_machine()

    def detach_state_machine(self):
        if self.statemachine is None:
            return
        logger.debug(
            "%s[%s] detaching statemachine %s",
            type(self), self, type(self.statemachine))
        #check if statemachine is 'running'?
        #if self.statemachine.get_state() is not None:
        if self.statemachine.is_running():
            raise StateException(
                "Attempt to detach running state machine: %s" % (
                    self.statemachine, ))
        if self._state_cb is not None:
            self.statemachine.new_state.disconnect(self._state_cb)
            self._state_cb = None
        try:
            self.statemachine._teardown()
        except Exception as e:
            logger.error(
                "%s[%s] failed to teardown: %s",
                type(self), self.statemachine, e)
        self.statemachine._release_node()
        del self.statemachine
        self.statemachine = None

    def attach_state_machine(self, statemachine, run_state=None):
        #if statemachine is self.statemachine:
        #    return
        self.detach_state_machine()
        logger.debug(
            "%s[%s] attaching statemachine %s",
            type(self), self, statemachine)
        self.statemachine = statemachine(self)
        self._state_cb = self.statemachine.new_state.connect(
            lambda ns: self._new_state(ns))
        if run_state is not None:
            # this will need to be checked for errors
            return self.statemachine.run(run_state)

    def get_state(self):
        if self.statemachine is None:
            return None
        s = self.statemachine.get_state()
        if s is None:
            return None
        return self.statemachine.__class__.__name__, s

    def clear_state_error(self):
        self.set_state(None)
        self.detach_state_machine()

    def set_state(self, state):
        if self.statemachine is None:
            return None
        self.statemachine.override(state)
        #self.statemachine.set_state(state)

    def is_running(self):
        if self.statemachine is None:
            return False
        return self.statemachine.is_running()

    def __del__(self):
        self.detach_state_machine()
        super(StatefulIONode, self).__del__()


def proxy(cfg):
    logger.debug("Creating proxy from %s", cfg)
    ncfg = copy.deepcopy(cfg)
    addr = ncfg.pop('addr')
    node = pizco.Proxy(addr)
    node.config(ncfg)
    logger.info("Proxy[%s] created for address %s: %s", node, addr, ncfg)
    return node


def resolve_module(node_type):
    module_name = 'temcagt.nodes.{}'.format(node_type)
    if module_name not in sys.modules:
        try:
            __import__(module_name)
        except ImportError as e:
            raise ImportError(
                "Failed to import resolved module {} from node name"
                " {} with error {}".format(module_name, node_type, e))
    return sys.modules[module_name]


def resolve_class(node_type, module=None):
    if module is None:
        module = resolve_module(node_type)
    node_name = node_type[0].upper() + node_type[1:] + 'Node'
    if not hasattr(module, node_name):
        raise ValueError(
            "Invalid node name {} does not exist in {}".format(
                node_name, str(module)))
    return getattr(module, node_name)


def resolve_config(node_type, module=None, cfg=None):
    if module is None:
        module = resolve_module(node_type)
    if hasattr(module, 'default_config'):
        node_cfg = copy.deepcopy(getattr(module, 'default_config'))
    else:
        logger.warning("{} missing default config".format(module.__name__))
        node_cfg = {}
    # cascade user config ~/.temcagt/node_type.json
    user_config_filename = os.path.expanduser(
        '~/.temcagt/config/{}.json'.format(node_type))
    if os.path.exists(user_config_filename):
        node_cfg = config.parser.cascade(
            node_cfg, config.parser.parse(user_config_filename))
    else:
        logger.warning("{} user configuration ({}) missing".format(
            node_type, user_config_filename))
        pass
    # cascade local config (cfg) [this could be pre-parsed command line args]
    if cfg is not None:
        node_cfg = config.parser.cascade(node_cfg, cfg)
    return node_cfg


def construct(node_type, cfg=None):
    # launch node
    node_module = resolve_module(node_type)
    node_class = resolve_class(node_type, module=node_module)
    node_cfg = resolve_config(node_type, module=node_module, cfg=cfg)
    logger.info("Launching {} with config {}".format(node_type, node_cfg))
    return node_class(node_cfg)


def connect(node_type, cfg=None):
    node_cfg = resolve_config(node_type, cfg=cfg)
    return pizco.Proxy(node_cfg['addr'])


def launch(node_type, cfg=None):
    node = construct(node_type, cfg)
    node.serve_forever()


def command_line_launch(args=None):
    if args is None:
        args = sys.argv[1:]
    if len(args) < 1:
        raise Exception("Must supply node type as first argument")
    node_type = args.pop(0)
    if len(args):
        cfg = config.parser.parse_command_line(args)
    else:
        cfg = None
    launch(node_type, cfg)
