#!/usr/bin/env python


import datautils.structures.mp
import montage

from .... import log
from .. import utils


logger = log.get_logger(__name__)
#logger.addHandler(logging.StreamHandler())
#logger.setLevel(logging.DEBUG)


class AnalysisSerf(datautils.structures.mp.TimedSerf):
    def setup(self, config, norm_buffers):
        logger.debug(
            "AnalysisSerf[%s] setup: %s, %s",
            self, config, norm_buffers)
        self.config = config
        self.image_size = config['crop'][:2]
        self.norm_buffers = norm_buffers
        self.setup_buffers()
        self.configure_contrast(self.config['contrast'])
        self.configure_shift(self.config['shift'])
        if 'log_serfs' in config:
            utils.log_serf_to_directory(self, config['log_serfs'])

    def set_config(self, config):
        logger.debug("AnalysisSerf[%s] set_config: %s", self, config)
        self.config = config
        self.configure_contrast(self.config['contrast'])
        self.configure_shift(self.config['shift'])

    def setup_buffers(self):
        logger.debug("AnalysisSerf[%s] setup_buffers", self)
        h, w, s = self.config['crop']
        self.norms = [
            utils.buffer_as_array(b, 'f4', (h, w)) for b in self.norm_buffers]

    def configure_contrast(self, cfg):
        logger.debug("AnalysisSerf[%s] configure_contrast: %s", self, cfg)
        self.contrast_results = [None for _ in xrange(len(self.norms))]
        self.contrast_crop = montage.ops.transform.cropping.calculate_crop(
            self.image_size, cfg['crop'])

    def configure_shift(self, cfg):
        logger.debug("AnalysisSerf[%s] configure_shift: %s", self, cfg)
        self.shift_results = [dict() for _ in xrange(len(self.norms))]
        self.shift_measurer = montage.ops.measures.shift.ShiftMeasurer(
            cfg['tcrop'], cfg['mcrop'], cfg['method'], self.image_size)

    def check_contrast(self, buffer_index):
        logger.debug("AnalysisSerf[%s] check_contrast: %s", self, buffer_index)
        result = montage.ops.measures.contrast.check_contrast(
            self.norms[buffer_index], self.contrast_crop)
        self.contrast_results[buffer_index] = result
        self.send('contrast', buffer_index, result)

    def clear_template(self):
        logger.debug("AnalysisSerf[%s] clear_template", self)
        self.shift_measurer.set_template(None)

    def set_template(self, buffer_index):
        logger.debug("AnalysisSerf[%s] set_template: %s", self, buffer_index)
        self.shift_measurer.set_template(self.norms[buffer_index])

    def check_shift(self, buffer_index):
        logger.debug("AnalysisSerf[%s] check_shift: %s", self, buffer_index)
        result = self.shift_measurer.match(
            self.norms[buffer_index])
        result['buffer_index'] = buffer_index
        self.shift_results[buffer_index] = result
        self.send('shift', buffer_index, result)

    def analyze_grab(self, buffer_index):
        logger.debug("AnalysisSerf[%s] analyze_grab: %s", self, buffer_index)
        self.check_contrast(buffer_index)
        if self.shift_measurer.template is None:
            self.set_template(buffer_index)
        else:
            self.check_shift(buffer_index)


class AnalysisLord(datautils.structures.mp.Lord):
    def __init__(self, config, buffers):
        logger.debug(
            "AnalysisLord[%s] __init__: %s, %s", self, config, buffers)
        datautils.structures.mp.Lord.__init__(self)
        self.config = config
        self.buffers = buffers
        self.contrast_results = [None for _ in xrange(len(self.buffers.norms))]
        self.shift_results = [{} for _ in xrange(len(self.buffers.norms))]

    def start(self, wait=True):
        logger.debug("AnalysisLord[%s] start", self)
        datautils.structures.mp.Lord.start(
            self, AnalysisSerf, (
                self.config, self.buffers.norm_buffers), wait=wait)

    def set_config(self, config):
        logger.debug("AnalysisLord[%s] set_config: %s", self, config)
        self.send('set_config', config)

    def clear_template(self):
        logger.debug("AnalysisLord[%s] clear_template", self)
        self.send('clear_template')

    def set_template(self, index):
        logger.debug("AnalysisLord[%s] set_template: %s", self, index)
        self.send('set_template', index)

    def check_shift(self, index):
        logger.debug("AnalysisLord[%s] check_shift: %s", self, index)
        self.send('check_shift', index)

    def analyze_grab(self, index):
        logger.debug("AnalysisLord[%s] analyze_grab: %s", self, index)
        self.send('analyze_grab', index)

    def contrast(self, index, result):
        logger.debug("AnalysisLord[%s] contrast: %s, %s", self, index, result)
        self.contrast_results[index] = result

    def shift(self, index, result):
        logger.debug("AnalysisLord[%s] shift: %s, %s", self, index, result)
        self.shift_results[index] = result
