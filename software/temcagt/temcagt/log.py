#!/usr/bin/env python


import copy
import json
import logging
import logging.config
import os


config = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'default': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        }
    },
    'loggers': {
        'default': {
            'handlers': ['default'],
            'level': 'INFO',
            'propagate': False,
        },
    }
}


class FastLogger(logging.Logger):
    def setLevel(self, level):
        super(FastLogger, self).setLevel(level)
        if level > logging.CRITICAL:
            self.critical = lambda *args, **kwargs: None
        else:
            self.critical = lambda *args, **kwargs: \
                logging.Logger.critical(self, *args, **kwargs)
        if level > logging.ERROR:
            self.error = lambda *args, **kwargs: None
        else:
            self.error = lambda *args, **kwargs: \
                logging.Logger.error(self, *args, **kwargs)
        if level > logging.WARNING:
            self.warning = lambda *args, **kwargs: None
        else:
            self.warning = lambda *args, **kwargs: \
                logging.Logger.warning(self, *args, **kwargs)
        if level > logging.INFO:
            self.info = lambda *args, **kwargs: None
        else:
            self.info = lambda *args, **kwargs: \
                logging.Logger.info(self, *args, **kwargs)
        if level > logging.DEBUG:
            self.debug = lambda *args, **kwargs: None
        else:
            self.debug = lambda *args, **kwargs: \
                logging.Logger.debug(self, *args, **kwargs)


logging.Logger.manager.setLoggerClass(FastLogger)


overlay_filename = os.path.expanduser('~/.temcagt/config/log.json')


def add_dicts(d0, d1):
    for k in d0:
        if isinstance(d0[k], dict):
            d0[k] = add_dicts(d0[k], d1.get(k, {}))
        else:
            if k in d1:
                d0[k] = copy.deepcopy(d1[k])
    return d0


def load_config(filename, config=None):
    with open(filename, 'r') as f:
        new_config = json.load(f)
    if config is not None:
        config = add_dicts(config, new_config)
    else:
        config = copy.deepcopy(new_config)
    return config

if os.path.exists(overlay_filename):
    config = load_config(overlay_filename, config)

logging.config.dictConfig(config)


def get_logger(name, cfg=None, overwrite=False):
    if name in logging.Logger.manager.loggerDict and cfg is None:
        return logging.getLogger(name)
    #if name not in logging.Logger.manager.loggerDict and cfg is not None:
    #    return logging.getLogger(name)
    if overwrite or (name not in config['loggers']):
        if cfg is None:
            cfg = config['loggers']['default']
        config['loggers'][name] = copy.deepcopy(cfg)
        logging.config.dictConfig(config)
    return logging.getLogger(name)


def set_level_for_all_loggers(level):
    ld = logging.Logger.manager.loggerDict
    for k in ld:
        if not isinstance(ld[k], logging.PlaceHolder):
            ld[k].setLevel(level)


def log_to_filename(filename, level=None):
    filename = os.path.abspath(os.path.expanduser(filename))
    dn, fn = os.path.split(filename)
    if not os.path.exists(dn):
        os.makedirs(dn)
    elif not os.path.isdir(dn):
        raise IOError(
            "cannot log to %s: %s is not a directory" % (filename, dn))
    handler = logging.FileHandler(filename)
    handler.setFormatter(logging.Formatter(
        config['formatters']['standard']['format']))
    if level is None:
        handler.setLevel(logging.WARNING)
    else:
        handler.setLevel(level)
    ld = logging.Logger.manager.loggerDict
    for k in ld:
        if not isinstance(ld[k], logging.PlaceHolder):
            ld[k].addHandler(handler)
    #logging.getLogger().addHandler(handler)
    return handler


def stop_logging_to_handler(handler):
    ld = logging.Logger.manager.loggerDict
    for k in ld:
        if not isinstance(ld[k], logging.PlaceHolder):
            if handler in ld[k].handlers:
                ld[k].removeHandler(handler)
    handler.close()
    #logging.getLogger().removeHandler(handler)
