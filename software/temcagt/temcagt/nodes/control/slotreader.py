#!/usr/bin/env python
"""
find_next:
    given the slot we're on now, which one should we image next?

load info:
    given the slot we're on now, load an roi for that slot
"""

import json
import os


class SlotSource(object):
    def __init__(self, source):
        self.source = source

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, filename):
        self._source = filename
        if self._source is None:
            self.slots = {}
            self._sid_max = 0
            self._sid_min = 1
            return
        fn = os.path.abspath(os.path.expanduser(self._source))
        if not os.path.exists(fn):
            self.slots = {}
            self._sid_max = 0
            self._sid_min = 1
            return
        with open(fn, 'r') as f:
            self.slots = json.load(f)
        self.slots = {int(k): self.slots[k] for k in self.slots}
        if len(self.slots):
            self._sid_max = max(self.slots)
            self._sid_min = min(self.slots)
        else:
            self._sid_min = 0
            self._sid_max = 1

    def get_first_id(self, direction=1):
        if direction == 1:
            return self._sid_min
        return self._sid_max

    def get_slot_info(self, slot_id):
        """
        Returns:
            None - no info found
            dict - {
                'rois': list of rois
                'focus': []  # optional focus point(s)
                'align': []  # optional beam alignment point(s)
            },
        """
        return self.slots.get(slot_id, None)

    def get_next_id(self, slot_id, direction):
        if direction not in (1, -1):
            raise ValueError(
                "Invalid direction[%s] not either 1 or -1" % (direction, ))
        nid = None
        offset = 0
        while nid is None:
            offset += direction
            nid = slot_id + offset
            if nid > self._sid_max or nid < self._sid_min:
                return None
            nid = nid
            if nid in self.slots:
                return nid
            nid = None
        return None
